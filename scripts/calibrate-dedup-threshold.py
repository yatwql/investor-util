#!/usr/bin/env python3
"""去重阈值校准工具 — 基于锚点数据分析**当前规则**的判定分布与边界风险。

用法：
  python scripts/calibrate-dedup-threshold.py             # 分析全部锚点
  python scripts/calibrate-dedup-threshold.py --summary   # 仅汇总统计
  python scripts/calibrate-dedup-threshold.py --compact   # 压缩锚点文件（每个标题对保留最新一条）
  python scripts/calibrate-dedup-threshold.py --file X    # 指定锚点文件

**口径（关键）**：锚点文件 append-only、跨规则时代累积，故本工具**不信任记录里的
``ratio`` / ``bigram_overlap`` / ``rule``**，而是拿 ``title_a`` / ``title_b`` 用当前代码
重算相似度与实体重叠（``news_dedup._pair_similarity``），再按当前阈值重新判定分支——
结论始终反映**当前**规则。阈值同样从 ``news_dedup`` 读取，本文件不自写一份数字
（两处各写一份会漂移：如工具正文写 0.30 而代码为 0.35）。记录时的规则指纹与当前
不同的样本单列「历史规则时代」，仅作参照、不参与结论。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any

# ── 项目路径（脚本独立运行，需先把仓库根加入 sys.path） ──
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 晚导入：sys.path 就绪后再引用项目模块
from src.python.core.atomic_write import write_text_atomic  # noqa: E402
from src.python.providers.news_dedup import (  # noqa: E402
    ANCHOR_RULES_FIELD,
    _ANCHOR_RULES_VERSION,
    _ANCHOR_SIZE_WARN_BYTES,
    _CROSS_BG2_RATIO,
    _CROSS_BIGRAM_MIN,
    _CROSS_CANDIDATE_RATIO,
    _CROSS_DIRECT_RATIO,
    _CROSS_SAFE_RATIO,
    _RATIO_CLEAN,
    _SAME_SRC_BIGRAM_MIN,
    _TOKEN_LIKE,
    _has_opposite_direction,
    _normalize_title,
    _pair_similarity,
)

#: 默认锚点文件（与 news_dedup._ANCHOR_PATH 同源，不再各写一份路径）
_ANCHOR_PATH = os.path.join(_PROJECT_ROOT, "data", "calibration", "dedup_anchors.jsonl")

#: 本次运行实际读取的文件（main 按 --file 赋值；报告内的体积/压缩提示随之指向同一文件）
_ACTIVE_FILE = _ANCHOR_PATH


# ═══════════════════════════════════════════════════════════════
#  锚点读取与压缩
# ═══════════════════════════════════════════════════════════════


def _anchor_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    """锚点去重键：source 对 + 标题对（顺序无关，与 news_dedup._anchor_key 同口径）。"""
    a = (record.get("source_a", "") or "", record.get("title_a", "") or "")
    b = (record.get("source_b", "") or "", record.get("title_b", "") or "")
    sa, ta = (a, b) if a <= b else (b, a)
    return (sa[0], sa[1], ta[0], ta[1])


def load_anchors(path: str = _ANCHOR_PATH) -> list[dict[str, Any]]:
    """加载并按键去重（保留每个标题对的**最早**一条）的锚点记录。

    保留最早一条的理由：它附带当时的规则判定与规则指纹，便于与「当前规则重判」
    对比（漂移量）；压缩场景另走 :func:`compact_anchors`（保留最新一条）。

    Returns:
        去重后的记录列表；文件不存在时返回空列表（调用方决定是否退出）。
    """
    if not os.path.exists(path):
        return []
    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            buckets.setdefault(_anchor_key(record), record)
    return list(buckets.values())


def compact_anchors(path: str = _ANCHOR_PATH, *, dry_run: bool = False) -> dict[str, Any]:
    """压缩锚点文件：每个标题对只保留**最后一条**（append-only → 最后即最新）。

    文件是 append-only 累积，写侧去重机制生效前的批量校准轮次留下了大量重复行
    （实测 456,546 行 / 152 MB 中仅 51,718 个唯一对）。重复行对校准无信息量，
    却让每次 flush 的「读全文 → 整文件替换」与每次加载的全文解析白白放大数倍。

    两遍扫描实现：第一遍只记「每个 key 的最后行号」（内存只放 key → int），
    第二遍按行号挑选直接透写原文（不重新序列化，保留原始记录逐字不变），
    最后原子替换（``core.atomic_write.write_text_atomic``）。

    Returns:
        ``{before_lines, after_lines, before_bytes, after_bytes, unique_keys, legacy_era}``
        —— ``legacy_era`` 为被丢弃行中规则指纹与当前不一致（或缺失）的条数。
    """
    if not os.path.exists(path):
        return {
            "before_lines": 0,
            "after_lines": 0,
            "before_bytes": 0,
            "after_bytes": 0,
            "unique_keys": 0,
            "legacy_era": 0,
        }

    before_bytes = os.path.getsize(path)
    last_line_of: dict[tuple[str, str, str, str], int] = {}
    before_lines = 0
    with open(path, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            before_lines += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            last_line_of[_anchor_key(record)] = idx

    kept: list[str] = []
    legacy_era = 0
    with open(path, encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            record = json.loads(line)
            if last_line_of.get(_anchor_key(record), -1) == idx:
                kept.append(line if line.endswith("\n") else line + "\n")
            elif record.get(ANCHOR_RULES_FIELD, "") != _ANCHOR_RULES_VERSION:
                legacy_era += 1

    result = {
        "before_lines": before_lines,
        "after_lines": len(kept),
        "before_bytes": before_bytes,
        "after_bytes": len("".join(kept).encode("utf-8")),
        "unique_keys": len(last_line_of),
        "legacy_era": legacy_era,
    }
    if dry_run or not kept:
        return result
    write_text_atomic(
        path,
        "".join(kept),
        prefix=".dedup_anchors_compact_",
        log_tag="dedup",
        noun="锚点文件",
    )
    return result


# ═══════════════════════════════════════════════════════════════
#  当前规则重判
# ═══════════════════════════════════════════════════════════════


def classify_pair(ratio: float, overlap: int, same_source: bool, title_a: str, title_b: str) -> str:
    """按**当前**阈值重判一对标题会走哪个分支（与 ``_dedup_by_title`` 同序）。

    Returns:
        分支名：``same_src_merged`` / ``same_src_kept`` / ``cross_safe_merged`` /
        ``cross_safe_kept`` / ``cross_opposite`` / ``cross_merge`` /
        ``cross_merge_bg2`` / ``cross_skip`` / ``below_candidate``。
    """
    if same_source:
        return "same_src_merged" if overlap >= _SAME_SRC_BIGRAM_MIN else "same_src_kept"
    if ratio >= _CROSS_SAFE_RATIO:
        if ratio >= _CROSS_DIRECT_RATIO and overlap >= 1:
            return "cross_safe_merged"
        if overlap >= 2:
            return "cross_safe_merged"
        return "cross_safe_kept"
    if ratio >= _CROSS_CANDIDATE_RATIO:
        if overlap >= 1 and _has_opposite_direction(_normalize_title(title_a), _normalize_title(title_b)):
            return "cross_opposite"
        if overlap >= _CROSS_BIGRAM_MIN:
            return "cross_merge"
        if overlap >= 2 and ratio >= _CROSS_BG2_RATIO and _shared_carries_proper_noun(title_a, title_b):
            return "cross_merge_bg2"
        return "cross_skip"
    return "below_candidate"


def _shared_carries_proper_noun(title_a: str, title_b: str) -> bool:
    """共享项中是否含真专名证据（英数 token 含字母，或 _tk 虚拟专名）。"""
    from src.python.providers.news_dedup import _extract_entity_bigrams

    shared = _extract_entity_bigrams(_normalize_title(title_a)) & _extract_entity_bigrams(_normalize_title(title_b))
    return any(_TOKEN_LIKE.match(s) for s in shared)


def _shared_proper_nouns(title_a: str, title_b: str) -> list[str]:
    """共享项里的专名证据清单（展示用）。"""
    from src.python.providers.news_dedup import _extract_entity_bigrams

    shared = _extract_entity_bigrams(_normalize_title(title_a)) & _extract_entity_bigrams(_normalize_title(title_b))
    return sorted(s for s in shared if _TOKEN_LIKE.match(s))


def analyze(records: list[dict[str, Any]]) -> dict[str, Any]:
    """对全部锚点做「当前规则重判」并汇总。"""
    branches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    era_current = 0
    drift = 0
    for record in records:
        title_a = record.get("title_a", "") or ""
        title_b = record.get("title_b", "") or ""
        if not title_a or not title_b:
            continue  # 缺标题的残行不参与判定（空串相似度恒为 1，会误进安全区）
        ratio, overlap = _pair_similarity(title_a, title_b)
        same_source = bool(record.get("source_a")) and record.get("source_a") == record.get("source_b")
        branch = classify_pair(ratio, overlap, same_source, record.get("title_a", ""), record.get("title_b", ""))
        if record.get(ANCHOR_RULES_FIELD, "") == _ANCHOR_RULES_VERSION:
            era_current += 1
        # 记录时的 rule 与重判分支口径不同（如记录 cross_skip vs 重判 cross_merge）
        stored = record.get("rule", "")
        if stored and not _branch_matches_stored(branch, stored):
            drift += 1
        branches[branch].append({**record, "_ratio_now": ratio, "_overlap_now": overlap})
    return {"branches": branches, "era_current": era_current, "era_legacy": len(records) - era_current, "drift": drift}


def _branch_matches_stored(branch: str, stored: str) -> bool:
    """重判分支与记录时 ``rule`` 是否同类（历史时代的分支命名有差异，只做粗对齐）。"""
    if stored == "cross_merge_bg2":
        return branch == "cross_merge_bg2"
    if stored == "cross_safe":
        return branch.startswith("cross_safe")
    if stored == "same_src":
        return branch.startswith("same_src")
    return branch == stored


# ═══════════════════════════════════════════════════════════════
#  报告
# ═══════════════════════════════════════════════════════════════


def report(records: list[dict[str, Any]], *, summary_only: bool = False, sample: int = 10) -> None:
    """分析锚点数据，输出当前规则下的判定分布与边界风险。"""
    if not records:
        print("[!] 锚点文件为空，尚无数据可用于校准。")
        return
    size = os.path.getsize(_ACTIVE_FILE) if os.path.exists(_ACTIVE_FILE) else 0

    data = analyze(records)
    branches: dict[str, list[dict[str, Any]]] = data["branches"]

    print(f"锚点文件: {_ACTIVE_FILE}")
    print(f"  体积: {size / 1e6:.1f} MB（告警线 {_ANCHOR_SIZE_WARN_BYTES / 1e6:.0f} MB）")
    print(f"唯一标题对: {len(records)}")
    print(
        f"规则时代: 当前指纹 {_ANCHOR_RULES_VERSION} = {data['era_current']} 条；"
        f"历史时代 = {data['era_legacy']} 条（旧样本按当前代码重算，仍计入下方分布）"
    )
    print(f"与记录时判定不一致: {data['drift']} 条（规则已调整，属正常）")
    print()
    print("── 当前规则重判分布 ──")
    for name in (
        "same_src_merged",
        "same_src_kept",
        "cross_safe_merged",
        "cross_safe_kept",
        "cross_merge",
        "cross_merge_bg2",
        "cross_opposite",
        "cross_skip",
        "below_candidate",
    ):
        print(f"  {name:18s} {len(branches.get(name, [])):6d}")
    print()

    _report_skip_edges(branches.get("cross_skip", []), summary_only, sample)
    _report_merge_edges(branches.get("cross_merge", []), summary_only, sample)
    _report_bg2_merges(branches.get("cross_merge_bg2", []), sample)
    _report_safe_edges(branches.get("cross_safe_merged", []))
    _report_same_src(branches.get("same_src_kept", []), branches.get("same_src_merged", []))
    _print_advice(branches)
    _print_current_rules()


def _report_skip_edges(skips: list[dict[str, Any]], summary_only: bool, sample: int) -> None:
    """cross_skip：进候选区但未合并 —— 关注「有实体重叠却没过线」的漏判候选。"""
    print(f"=== cross_skip（进候选区但未合并，当前阈值 {_CROSS_CANDIDATE_RATIO}）===")
    print(f"  数量: {len(skips)}")
    if not skips:
        print()
        return
    by_bg: dict[int, int] = defaultdict(int)
    for r in skips:
        by_bg[min(r["_overlap_now"], 3)] += 1
    print("  实体重叠分布: " + "  ".join(f"bg={k}{'+' if k == 3 else ''}:{v}" for k, v in sorted(by_bg.items())))
    bg_le1 = [r for r in skips if r["_overlap_now"] <= 1 and r["_ratio_now"] >= 0.40]
    print(f"  bg≤1 且 ratio≥0.40: {len(bg_le1)} 条")
    print("    多数不是重复：共享日期/财经骨架（如板块指数行情句式）抬高 ratio，实体无重叠")
    print("    少数是同一主体的多篇报道（如一公司两篇财报快讯，公司名只贡献 1~2 个 bigram）")
    print("    —— 属规则有意保守（实体证据不足不合并）：误合并会静默丢掉一篇独立报道，故不因这类样例降阈值")
    print(f"    ratio 侧已剥离: {_RATIO_CLEAN.pattern}；实体侧模板词已掩码")
    if not summary_only and bg_le1:
        for r in bg_le1[:3]:
            print(f"      r={r['_ratio_now']:.3f} bg={r['_overlap_now']}")
            print(f"        [{r['source_a']}] {r['title_a'][:44]}")
            print(f"        [{r['source_b']}] {r['title_b'][:44]}")
    below_bg2 = [r for r in skips if r["_overlap_now"] >= 2 and r["_ratio_now"] < _CROSS_BG2_RATIO]
    if below_bg2:
        print()
        print(f"[?] bg≥2 且 ratio 落在 {_CROSS_CANDIDATE_RATIO:.3f}~{_CROSS_BG2_RATIO:.3f}: {len(below_bg2)} 条")
        print(
            f"    若把 _CROSS_BG2_RATIO 降到 {_CROSS_CANDIDATE_RATIO:.3f}，这些会新增合并；"
            "含真专名的才是漏判候选，纯数字/中文共享不算"
        )
        proper = [r for r in below_bg2 if _shared_carries_proper_noun(r["title_a"], r["title_b"])]
        print(f"    其中含真专名证据: {len(proper)} 条")
        if not summary_only:
            for r in proper[:sample]:
                print(f"      r={r['_ratio_now']:.3f} shared={_shared_proper_nouns(r['title_a'], r['title_b'])}")
                print(f"        [{r['source_a']}] {r['title_a'][:46]}")
                print(f"        [{r['source_b']}] {r['title_b'][:46]}")
    print()


def _report_merge_edges(merges: list[dict[str, Any]], summary_only: bool, sample: int) -> None:
    """cross_merge：高实体重叠已合并 —— 关注 bg=3 边界（误合并风险）。"""
    print(f"=== cross_merge（共享 ≥{_CROSS_BIGRAM_MIN} 实体 bigram 已合并）===")
    print(f"  数量: {len(merges)}")
    if not merges:
        print()
        return
    edge = [r for r in merges if r["_overlap_now"] == _CROSS_BIGRAM_MIN]
    if edge:
        high_ratio = [r for r in edge if r["_ratio_now"] >= 0.40]
        print(f"  bg={_CROSS_BIGRAM_MIN} 边界: {len(edge)} 条（其中 ratio≥0.40: {len(high_ratio)} 条）")
        print(
            "    样本需人工判读：bg=3 靠实体重叠合并，模板词已掩码，但同领域不同事件"
            "（共 3 个实体名）仍可能误合并 → 出现误合并样例时优先扩模板词表/方向对，而非抬高阈值"
        )
        if not summary_only:
            for r in edge[:sample]:
                print(f"      r={r['_ratio_now']:.3f} bg={r['_overlap_now']}")
                print(f"        [{r['source_a']}] {r['title_a'][:44]}")
                print(f"        [{r['source_b']}] {r['title_b'][:44]}")
    print()


def _report_bg2_merges(bg2: list[dict[str, Any]], sample: int) -> None:
    """cross_merge_bg2：bg=2 + 中高 ratio + 真专名 —— 展示共享证据类型。"""
    print(f"=== cross_merge_bg2（bg=2 + ratio≥{_CROSS_BG2_RATIO} + 真专名）===")
    print(f"  数量: {len(bg2)}")
    if not bg2:
        print()
        return
    for r in bg2[:sample]:
        print(f"    r={r['_ratio_now']:.3f} shared={_shared_proper_nouns(r['title_a'], r['title_b'])}")
        print(f"      [{r['source_a']}] {r['title_a'][:44]}")
        print(f"      [{r['source_b']}] {r['title_b'][:44]}")
    print()


def _report_safe_edges(safe_merged: list[dict[str, Any]]) -> None:
    """cross_safe_merged：ratio ≥ 0.50 —— 关注 0.50~0.65 且实体证据仅 2 的擦边。"""
    print(f"=== cross_safe_merged（ratio ≥ {_CROSS_SAFE_RATIO}）===")
    print(f"  数量: {len(safe_merged)}")
    if not safe_merged:
        print()
        return
    edge = [
        r for r in safe_merged if _CROSS_SAFE_RATIO <= r["_ratio_now"] < _CROSS_DIRECT_RATIO and r["_overlap_now"] < 3
    ]
    print(f"  擦边区（{_CROSS_SAFE_RATIO}~{_CROSS_DIRECT_RATIO} 且 bg<3）: {len(edge)} 条")
    print("    靠 ratio 合并、实体证据少 → 误合并风险集中区，新增误合并样例时优先查这里")
    print()


def _report_same_src(kept: list[dict[str, Any]], merged: list[dict[str, Any]]) -> None:
    """同源：合并阈值只依赖实体重叠（同源不出现方向对立报道）。"""
    print(f"=== 同源（阈值 bg≥{_SAME_SRC_BIGRAM_MIN}）===")
    print(f"  已合并: {len(merged)} 条；未达阈值: {len(kept)} 条")
    if not kept:
        print()
        return
    by_bg: dict[int, int] = defaultdict(int)
    for r in kept:
        by_bg[min(r["_overlap_now"], 3)] += 1
    print("  未达阈值的重叠分布: " + "  ".join(f"bg={k}{'+' if k == 3 else ''}:{v}" for k, v in sorted(by_bg.items())))
    print(
        "    bg=2/3 与阈值的差距较大，但同源新闻多为模板差异"
        "（模板词已掩码），不因此降阈值；出现真重复样例时优先扩模板词表"
    )
    print()


def _print_advice(branches: dict[str, list[dict[str, Any]]]) -> None:
    """数据驱动的建议（不写死结论）。"""
    print("=" * 60)
    print("校准建议")
    print("=" * 60)
    cross_total = sum(
        len(branches.get(b, []))
        for b in (
            "cross_skip",
            "cross_merge",
            "cross_merge_bg2",
            "cross_safe_merged",
            "cross_safe_kept",
            "cross_opposite",
        )
    )
    same_total = len(branches.get("same_src_kept", [])) + len(branches.get("same_src_merged", []))
    skips = branches.get("cross_skip", [])
    missed = [
        r
        for r in skips
        if r["_overlap_now"] >= 2
        and r["_ratio_now"] >= _CROSS_BG2_RATIO
        and _shared_carries_proper_noun(r["title_a"], r["title_b"])
    ]
    if missed:
        print(f"[!!] 规则异常：{len(missed)} 条满足 bg=2 梯度条件却未合并 —— 检查 classify_pair 与判定链是否同序")
    else:
        print("[OK] bg=2 梯度无漏判：满足条件的样本都已合并")

    below = [
        r
        for r in skips
        if r["_overlap_now"] >= 2
        and r["_ratio_now"] < _CROSS_BG2_RATIO
        and _shared_carries_proper_noun(r["title_a"], r["title_b"])
    ]
    if below:
        print(
            f"[?] 降 _CROSS_BG2_RATIO 至 {_CROSS_CANDIDATE_RATIO:.3f} 会新增合并 {len(below)} 条，"
            "需人工判读真伪（纯数字 token 常见误合并，故当前要求含字母 + 0.375 双门槛）"
        )
    edges = branches.get("cross_merge", [])
    edge3 = [r for r in edges if r["_overlap_now"] == _CROSS_BIGRAM_MIN]
    if edge3:
        print(f"[!] 跨源 bg={_CROSS_BIGRAM_MIN} 边界 {len(edge3)} 条：误合并风险集中区，需抽样人工判读")
    print(f"[i] 有效跨源样本 {cross_total} 条（≥100 条建议校准一次）；同源样本 {same_total} 条（≥50 条建议校准一次）")
    if os.path.exists(_ACTIVE_FILE) and os.path.getsize(_ACTIVE_FILE) > _ANCHOR_SIZE_WARN_BYTES:
        print(
            f"[!] 锚点文件超过 {_ANCHOR_SIZE_WARN_BYTES / 1e6:.0f} MB："
            f"运行 `python scripts/calibrate-dedup-threshold.py --compact` 压缩"
        )
    print()


def _print_current_rules() -> None:
    """打印当前阈值（全部取自 news_dedup 常量，无硬编码数字）。"""
    print("─" * 60)
    print("当前阈值规则（来源：news_dedup 常量）")
    print("─" * 60)
    print(f"  跨源候选区入口: ratio ≥ {_CROSS_CANDIDATE_RATIO}")
    print(f"  跨源主规则: 共享 ≥ {_CROSS_BIGRAM_MIN} 实体 bigram → 合并")
    print(
        f"  跨源专名梯度: 共享 = 2 且 ratio ≥ {_CROSS_BG2_RATIO} 且共享项含真专名"
        f"（英数需含字母，pattern={_TOKEN_LIKE.pattern}）→ 合并"
    )
    print(
        f"  跨源安全区: ratio ≥ {_CROSS_DIRECT_RATIO} 且专名 bg≥1 → 合并；"
        f"{_CROSS_SAFE_RATIO}~{_CROSS_DIRECT_RATIO} 需专名 bg≥2"
    )
    print(f"  同源: 共享 ≥ {_SAME_SRC_BIGRAM_MIN} 实体 bigram → 合并")
    print("  方向对立（上涨/下跌、站稳/跌破…）→ 不合并")
    print(f"  规则指纹: {_ANCHOR_RULES_VERSION}（写入锚点字段 {ANCHOR_RULES_FIELD}）")
    print()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="仅显示汇总统计")
    parser.add_argument("--compact", action="store_true", help="压缩锚点文件（每个标题对保留最新一条）")
    parser.add_argument("--dry-run", action="store_true", help="兼容保留：本工具从不修改阈值，仅 --compact 会写盘")
    parser.add_argument("--file", default=_ANCHOR_PATH, help=f"锚点文件路径（默认 {_ANCHOR_PATH}）")
    args = parser.parse_args()
    global _ACTIVE_FILE
    _ACTIVE_FILE = args.file

    if args.compact:
        before = os.path.getsize(args.file) if os.path.exists(args.file) else 0
        result = compact_anchors(args.file, dry_run=args.dry_run)
        if not result["before_lines"]:
            print(f"[!] 锚点文件不存在或为空: {args.file}")
            return
        print(f"锚点文件: {args.file}")
        print(f"  压缩前: {result['before_lines']} 行 / {before / 1e6:.1f} MB")
        print(
            f"  压缩后: {result['after_lines']} 行 / {result['after_bytes'] / 1e6:.1f} MB"
            f"（唯一标题对 {result['unique_keys']}）"
        )
        print(f"  丢弃重复行中被判为历史规则时代的: {result['legacy_era']} 条")
        print("  " + ("[..] --dry-run：未写盘" if args.dry_run else "[OK] 已原子替换（每个标题对保留最新一条）"))
        return

    records = load_anchors(args.file)
    if not records:
        print(f"[!] 锚点文件不存在或为空: {args.file}")
        print("    请先运行一次报告生成（触发新闻获取），积累数据后再校准。")
        sys.exit(0)
    report(records, summary_only=args.summary)


if __name__ == "__main__":
    main()
