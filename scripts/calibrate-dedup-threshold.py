#!/usr/bin/env python3
"""去重阈值校准工具 — 基于锚点数据分析阈值合理性。

用法：
  python scripts/calibrate-dedup-threshold.py            # 分析全部锚点
  python scripts/calibrate-dedup-threshold.py --summary  # 仅汇总统计
  python scripts/calibrate-dedup-threshold.py --dry-run  # 不修改，仅输出建议
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

# ── 项目路径 ──────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 注意：与 src/python/providers/news_dedup.py 的 _ANCHOR_PATH 保持一致——
# 2026-07-30 起代码写入路径为 data/calibration/dedup_anchors.jsonl
# （commit 4e95d595 起锚点路径拆分至校准目录），此处不再读 data/cache/ 旧文件。
_ANCHOR_PATH = os.path.join(_PROJECT_ROOT, "data", "calibration", "dedup_anchors.jsonl")
# 当前代码中的阈值常量（与 news_aggregator.py 保持一致）
# 算法同时使用中文 bigram + 英数 token 匹配，
# 跨源采用梯度阈值：
#   - bg≥3: ratio≥0.30 合并（主规则）
#   - bg=2: ratio≥0.40 合并（中高 ratio 梯度补偿）
#   - bg≤1: 不合并（即使 ratio 较高也是虚假重叠）
_CROSS_THRESHOLD = 0.30  # cross_threshold
_SAME_SRC_BIGRAM = 4  # 同源 bigram 阈值
_CROSS_BIGRAM = 3  # 跨源 bigram 阈值
_CROSS_BG2_RATIO = 0.40  # bg=2 梯度补偿阈值


def load_anchors(path: str = _ANCHOR_PATH) -> list[dict[str, Any]]:
    """从 JSONL 文件加载锚点记录。

    按 (source_a, source_b, title_a, title_b) 对去重：锚点文件 append-only，
    2026-08 前同一对新闻在多轮运行中重复追加（实测 61.6% 为重复记录），
    直接统计会虚增绝对数字（如 cross_skip bg=0 从 279 虚增至 13800）。
    去重后校准结论反映真实边界样本分布，而非重复计数。
    """
    if not os.path.exists(path):
        print(f"[!] 锚点文件不存在: {path}")
        print("    请先运行一次报告生成（触发新闻获取），积累数据后再校准。")
        sys.exit(0)
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (
                r.get("source_a", "") or "",
                r.get("source_b", "") or "",
                r.get("title_a", "") or "",
                r.get("title_b", "") or "",
            )
            # 顺序无关：调换源顺序的同一对视为重复
            key_b = (key[1], key[0], key[3], key[2])
            if key in seen or key_b in seen:
                continue
            seen.add(key)
            records.append(r)
    return records


def report(records: list[dict[str, Any]], summary_only: bool = False, dry_run: bool = True) -> None:
    """分析锚点数据，评估当前阈值效果，输出校准建议。"""
    if not records:
        print("[!] 锚点文件为空，尚无数据可用于校准。")
        return

    # ── 分组统计 ──
    by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_rule[r.get("rule", "unknown")].append(r)

    print(f"锚点总数: {len(records)}")
    print(f"覆盖规则: {', '.join(sorted(by_rule.keys()))}")
    print()

    # ── 各规则分析 ──
    # cross_skip: 跨源 ratio ≥ 0.30 但 bigram < 3，被跳过
    # 这些是"可能漏判"的候选
    skip_records = by_rule.get("cross_skip", [])
    if skip_records:
        ratios = [r["ratio"] for r in skip_records]
        overlaps = [r["bigram_overlap"] for r in skip_records]
        print(f"=== cross_skip（跨源 ≥0.30 但 bigram<3 被跳过 — 潜在漏判）===")
        print(f"  数量: {len(skip_records)}")
        print(f"  ratio 范围: {min(ratios):.3f} ~ {max(ratios):.3f}")
        print(f"  bigram 范围: {min(overlaps)} ~ {max(overlaps)}")
        print(f"  各 bigram 分布: ", end="")
        dist = sorted(set(overlaps))
        for d in dist:
            cnt = sum(1 for o in overlaps if o == d)
            print(f"{d}:{cnt} ", end="")
        print()
        if not summary_only:
            print(f"  {'详细列表（前10条）':-^60}")
            for r in skip_records[:10]:
                print(f"  ratio={r['ratio']:.3f} bg={r['bigram_overlap']} [{r['source_a']}] {r['title_a'][:35]}")
                print(f"  {'':>15s}     [{r['source_b']}] {r['title_b'][:35]}")
                print()
    else:
        print("=== cross_skip: 无记录 ===")
    print()

    # cross_merge: 跨源 ratio ≥ 0.30 且 bigram ≥ 3 被合并
    # 这些是"正确合并"的样本
    merge_records = by_rule.get("cross_merge", [])
    if merge_records:
        ratios = [r["ratio"] for r in merge_records]
        overlaps = [r["bigram_overlap"] for r in merge_records]
        print(f"=== cross_merge（跨源 ≥0.30 且 bigram≥3 已合并 — 验证样本）===")
        print(f"  数量: {len(merge_records)}")
        print(f"  ratio 范围: {min(ratios):.3f} ~ {max(ratios):.3f}")
        print(f"  bigram 范围: {min(overlaps)} ~ {max(overlaps)}")
        # 检查 bigram=3 的边界样本
        edge = [r for r in merge_records if r["bigram_overlap"] == 3]
        if edge:
            print(f"  [!!] bigram=3 边界样本: {len(edge)} 条（降低阈值风险较大）")
            if not summary_only:
                for r in edge[:5]:
                    print(f"    [{r['source_a']}] {r['title_a'][:30]}")
                    print(f"    [{r['source_b']}] {r['title_b'][:30]}")
    else:
        print("=== cross_merge: 无记录 ===")
    print()

    print()

    # cross_safe: 跨源 ratio ≥ 0.50 直接合并
    safe_records = by_rule.get("cross_safe", [])
    if safe_records:
        ratios = [r["ratio"] for r in safe_records]
        print(f"=== cross_safe（跨源 ≥0.50 安全区擦边 — 0.50~0.60）===")
        print(f"  数量: {len(safe_records)}")
        print(f"  ratio 范围: {min(ratios):.3f} ~ {max(ratios):.3f}")
    else:
        print("=== cross_safe: 无记录 ===")
    print()

    # same_src: 同源 bigram 接近阈值
    same_records = by_rule.get("same_src", [])
    if same_records:
        overlaps = [r["bigram_overlap"] for r in same_records]
        print(f"=== same_src（同源 bigram 接近阈值 4 — 边界样本）===")
        print(f"  数量: {len(same_records)}")
        print(f"  bigram 范围: {min(overlaps)} ~ {max(overlaps)}")
        dist = sorted(set(overlaps))
        for d in dist:
            cnt = sum(1 for o in overlaps if o == d)
            print(f"    bigram={d}: {cnt} 条")
    else:
        print("=== same_src: 无记录 ===")
    print()

    # ── 校准建议 ──
    _print_calibration_advice(by_rule, summary_only, dry_run)


def _print_calibration_advice(
    by_rule: dict[str, list[dict[str, Any]]],
    summary_only: bool,
    dry_run: bool,
) -> None:
    """基于锚点数据生成阈值调整建议。"""
    print("=" * 60)
    print("校准建议")
    print("=" * 60)

    skip = by_rule.get("cross_skip", [])
    merge = by_rule.get("cross_merge", [])
    same = by_rule.get("same_src", [])
    safe = by_rule.get("cross_safe", [])

    # 跨源 candidate 总数
    cross_candidates = len(skip) + len(merge) + len(safe)

    # 1. cross_threshold (0.30)
    if skip:
        # ── 按 bigram 重叠度分档分析 ──
        skip_bg0 = [r for r in skip if r["bigram_overlap"] == 0]
        skip_bg1 = [r for r in skip if r["bigram_overlap"] == 1]
        skip_bg2 = [r for r in skip if r["bigram_overlap"] >= 2]
        print()
        print(f"  cross_skip 按 bigram 分档:")
        print(f"    bg=0: {len(skip_bg0)} 条（无实体重叠，财经虚高，安全跳过）")
        print(f"    bg=1: {len(skip_bg1)} 条（几乎无实体重叠，安全跳过）")
        print(f"    bg>=2: {len(skip_bg2)} 条（有实体重叠但未达阈值，需审查）")

        # bg≥2 的 skip — 有实体重叠但未达 bg≥3 合并门槛
        skip_bg2_high = [r for r in skip_bg2 if r["ratio"] >= 0.35]
        if skip_bg2_high:
            print()
            print(f"[?] bg≥2 且 ratio≥0.35 被跳过: {len(skip_bg2_high)} 条")
            print(f"    有实体重叠但未达 bg≥3 合并条件，需审查是否应为重复")

        # bg=0,1 但 ratio 很高 → 说明归一化不够，不是阈值问题
        high_skip_noise = [r for r in skip if r["bigram_overlap"] <= 1 and r["ratio"] >= 0.40]
        if high_skip_noise:
            print()
            print(f"[+] bg≤1 但 ratio≥0.40: {len(high_skip_noise)} 条")
            print(f"    这些不是重复，是共享日期/事件名/财经关键词导致 SequenceMatcher 比率虚高")
            print(f"    _normalize_title 用 \\\\b(?:19|20)\\\\d{2}\\\\b 剥离孤立年份数字")
            print(f'    可过滤共享"2026""2025"等年份导致的 ratio 虚高（如"2026年炒股"vs"2026年展会"）')
            if not summary_only:
                for r in high_skip_noise[:3]:
                    print(
                        f"      ratio={r['ratio']:.3f} bg={r['bigram_overlap']} [{r['source_a']}] {r['title_a'][:30]}"
                    )
                    print(f"      → [{r['source_b']}] {r['title_b'][:30]}")

        # 绝大多数 skip 都在边界内 → 阈值合适
        if not any(r["bigram_overlap"] >= 2 and r["ratio"] >= 0.35 for r in skip):
            print(f"[OK] cross_threshold=0.30 当前合适（无非重复漏判）")
    else:
        print(f"[OK] cross_threshold=0.30: 无 skips，阈值安全")

    # 2. 跨源 bigram 阈值 (3)
    if merge:
        edge_merge = [r for r in merge if r["bigram_overlap"] == 3]
        if edge_merge:
            ratio_ok = sum(1 for r in edge_merge if r["ratio"] >= 0.40)
            print()
            print(f"[!] 跨源 bigram=3: {len(edge_merge)} 条在边界上")
            print(f"    其中 {ratio_ok}/{len(edge_merge)} 条 ratio>=0.40")
            print(f"    降低 bigram=3 阈值的需求不大。")

        bigram_4plus = [r for r in merge if r["bigram_overlap"] >= 4]
        if bigram_4plus:
            print(f"[OK] 跨源 bigram>=4: {len(bigram_4plus)} 条已合并，阈值安全")
    else:
        print(f"[OK] 跨源 bigram=3: 无边界样本")

    # 3. 同源 bigram 阈值 (4)
    if same:
        bg2 = [r for r in same if r["bigram_overlap"] == 2]
        if bg2:
            print()
            print(f"[!] 同源 bigram=2: {len(bg2)} 条在边界下（当前阈值 4，差距较大）")
            print(f"    其中部分可能是不同产品/事件误判风险，建议审查后标注")
            if not summary_only:
                for r in bg2[:5]:
                    print(f"      [{r['source_a']}] {r['title_a'][:30]}")
                    print(f"      [{r['source_b']}] {r['title_b'][:30]}")

    # 4. 汇总
    print()
    print(f"有效跨源样本: {cross_candidates} 条（建议 ≥100 条后校准一次）")
    print(f"有效同源样本: {len(same)} 条（建议 ≥50 条后校准一次）")

    # 5. 当前阈值规则摘要
    print()
    print("─" * 60)
    print("当前阈值规则")
    print("─" * 60)
    print(f"  跨源：bg≥3 + ratio≥0.30 → 合并（主规则）")
    print(f"  跨源：bg=2 + ratio≥0.40 → 合并（梯度补偿）")
    print(f"  跨源安全区：ratio≥0.50 → 直接合并")
    print(f"  同源：bigram≥4 → 合并")
    print(f"  清理模式：日期(年/月/日)、英文专名占位化")
    print(f"  _normalize_title 过滤模式：%、万亿、前N、\\\\b(?:19|20)\\\\d{{2}}\\\\b、字母后缀年份")

    if not dry_run:
        print()
        print("[..] --dry-run 模式，未实际修改任何设置")
        print("    去掉 --dry-run 不执行任何修改，本工具仅分析不自动修改阈值")


def main() -> None:
    # 强制 stdout 使用 UTF-8，确保输出重定向到文件时中文不丢失
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="仅显示汇总统计")
    parser.add_argument("--dry-run", action="store_true", default=True, help="仅分析不修改（默认）")
    parser.add_argument("--file", default=_ANCHOR_PATH, help="锚点文件路径（默认 data/calibration/dedup_anchors.jsonl）")
    args = parser.parse_args()

    records = load_anchors(args.file)
    report(records, summary_only=args.summary, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
