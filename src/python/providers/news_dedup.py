"""新闻去重主流程 — 标题模糊去重 + 锚点采集。

判定口径（阈值常量 / 模板词表 / 归一化 / 实体 bigram / 相似度 / 方向词对 / 规则指纹）
在 ``providers/news_dedup_rules.py``；本模块负责锚点采集与比较循环，并原面
re-export 规则原语（``from ...news_dedup import _normalize_title`` 等既有引用不受影响）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

from src.python.core.constants import PROJECT_ROOT
from src.python.core.jsonl_store import append_jsonl_atomic_many

from src.python.providers.news_dedup_rules import (  # noqa: F401
    # 规则原语全部再导出：既有 import 面（测试 / 校准工具 / 报告层）保持不变
    ANCHOR_RULES_FIELD,
    _ANCHOR_RULES_VERSION,
    _CROSS_BG2_RATIO,
    _CROSS_BIGRAM_MIN,
    _CROSS_CANDIDATE_RATIO,
    _CROSS_DIRECT_RATIO,
    _CROSS_SAFE_RATIO,
    _ENG_PLACEHOLDER,
    _OPPOSITE_PAIRS,
    _RATIO_CLEAN,
    _SAME_SRC_BIGRAM_MIN,
    _STOP_BIGRAMS,
    _STOP_MASK_RE,
    _TOKEN_LIKE,
    _eng_len_placeholder,
    _extract_entity_bigrams,
    _has_opposite_direction,
    _mask_stop,
    _normalize_title,
    _overlap_of_norms,
    _pair_similarity,
    _ratio_of_norms,
    _rules_fingerprint,
)

logger = logging.getLogger("invest")

# ── 锚点采集（阈值校准用） ──────────────────────────────────────
# 每次 _dedup_by_title 运行后，边界案例收集到此列表，
# aggregate_news() 结束时追写至 data/calibration/dedup_anchors.jsonl。
# 一条记录为一个 JSON 行，append-only。格式：
#   {"ts","title_a","title_b","source_a","source_b",
#    "ratio","bigram_overlap","merged","rule","anchor_rules_version"}
_ANCHOR_RECORDS: list[dict[str, Any]] = []
_ANCHOR_LOCK = threading.Lock()
_ANCHOR_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "calibration",
    "dedup_anchors.jsonl",
)
#: 体积告警线：超过此值在加载时提醒压缩（flush 写全文、加载解析全文件，均是全文成本）
_ANCHOR_SIZE_WARN_BYTES = 32 * 1024 * 1024

# 进程级"已写锚点 key"集合 — 防止同一对 (source,title) 在多轮运行中重复追加。
# 背景：锚点文件 append-only，同一对新闻在每次真实抓取进入候选区时都会重新记录，
# 多轮后同一对重复数十次（实测 calibration 文件 61.6% 为重复记录），使校准报告
# 绝对数字严重失真（如 cross_skip bg=0 从 279 虚增至 13800）。
# 方案：首次 flush 时惰性加载现有文件 key 到内存集合，之后每次 flush 只写
# 不在集合中的新 key、写后加入。跨会话、跨轮次均拦截重复，避免每次读全文件。
_WRITTEN_ANCHOR_KEYS: set[str] = set()
_WRITTEN_KEYS_LOADED = False
_WRITTEN_KEYS_LOCK = threading.Lock()


def _anchor_key(record: dict[str, Any]) -> str:
    """锚点去重键：source 对 + 标题对（顺序无关）。"""
    a = (record.get("source_a", "") or "", record.get("title_a", "") or "")
    b = (record.get("source_b", "") or "", record.get("title_b", "") or "")
    # 排序使 (A,B) 与 (B,A) 视为同一对，避免来源顺序不同产生重复
    sa, ta = (a, b) if a <= b else (b, a)
    return f"{sa[0]}|{sa[1]}|{ta[0]}|{ta[1]}"


def _load_written_keys() -> None:
    """惰性加载锚点文件已有 key 到 _WRITTEN_ANCHOR_KEYS（进程生命周期内一次）。

    首次 flush 前调用，读一次现有文件，之后所有 flush 仅内存比对。文件不存在或
    为空时静默返回空集合。

    **体积关注**：本文件 append-only 且历史累积（曾达数百 MB、重复行占近九成），
    而 flush 走 ``append_jsonl_atomic_many``（读全文 → 整文件替换）——文件越大，
    每轮报告写盘成本越高。超过 ``_ANCHOR_SIZE_WARN_BYTES`` 时告警并指向压缩入口。
    """
    global _WRITTEN_KEYS_LOADED
    with _WRITTEN_KEYS_LOCK:
        if _WRITTEN_KEYS_LOADED:
            return
        _WRITTEN_KEYS_LOADED = True
        if not os.path.exists(_ANCHOR_PATH):
            return
        try:
            size = os.path.getsize(_ANCHOR_PATH)
        except OSError:
            size = 0
        if size > _ANCHOR_SIZE_WARN_BYTES:
            logger.warning(
                "[dedup] 锚点文件已 %.1f MB（超过 %.0f MB 建议线）：flush 需读写全文、加载需解析全文件。"
                "建议运行 `python scripts/calibrate-dedup-threshold.py --compact` 压缩（保留每个标题对最新一条）：%s",
                size / 1e6,
                _ANCHOR_SIZE_WARN_BYTES / 1e6,
                _ANCHOR_PATH,
            )
        try:
            with open(_ANCHOR_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    _WRITTEN_ANCHOR_KEYS.add(_anchor_key(rec))
        except OSError:
            logger.warning("锚点 key 加载失败: %s", _ANCHOR_PATH)


def _record_anchor(record: dict[str, Any]) -> None:
    """线程安全地追加一条锚点记录。"""
    with _ANCHOR_LOCK:
        _ANCHOR_RECORDS.append(record)


def _make_anchor(
    item_a: dict[str, Any],
    item_b: dict[str, Any],
    ratio: float,
    bigram_overlap: int,
    merged: bool,
    rule: str,
) -> dict[str, Any]:
    """构建一条锚点记录（边界案例），用于后续阈值校准。

    记录带 ``anchor_rules_version``（:data:`_ANCHOR_RULES_VERSION`）——校准工具
    据此区分「哪个规则时代」的样本；同一标题对也可用标题重算（见
    :func:`_pair_similarity`）。
    """
    return {
        "ts": item_a.get("ctime", "") or item_b.get("ctime", ""),
        "title_a": item_a.get("title", ""),
        "title_b": item_b.get("title", ""),
        "source_a": item_a.get("_source", ""),
        "source_b": item_b.get("_source", ""),
        "ratio": round(ratio, 3),
        "bigram_overlap": bigram_overlap,
        "merged": merged,
        "rule": rule,
        ANCHOR_RULES_FIELD: _ANCHOR_RULES_VERSION,
    }


def _flush_anchors() -> None:
    """将内存中的锚点记录追写到 JSONL 文件，然后清空列表。

    一次运行产生数十条记录（~200 字节/条），文件写入发生在去重完成后，
    不影响新闻获取和报告生成的主流程。

    写入前按 (source,title) 对去重：只写本次尚未写入文件的记录（查
    _WRITTEN_ANCHOR_KEYS），写后加入集合。防止同一对新闻多轮运行重复
    追加导致校准数字失真（见 _WRITTEN_ANCHOR_KEYS 注释）。

    落盘走 ``core/jsonl_store.append_jsonl_atomic_many``（一次批量原子追加）。
    """
    global _ANCHOR_RECORDS
    if not _ANCHOR_RECORDS:
        return
    with _ANCHOR_LOCK:
        records = _ANCHOR_RECORDS
        _ANCHOR_RECORDS = []  # 先清空再写，防止递归写入
    _load_written_keys()
    new_records: list[dict[str, Any]] = []
    with _WRITTEN_KEYS_LOCK:
        for r in records:
            key = _anchor_key(r)
            if key in _WRITTEN_ANCHOR_KEYS:
                continue
            _WRITTEN_ANCHOR_KEYS.add(key)
            new_records.append(r)
    if not new_records:
        return
    # 一次性批量原子追加（`open(..., "a")` 逐行写在中途中断会留下半行，
    # 而本文件的读取方要求逐行完整）。必须用批量入口：`append_jsonl_atomic`
    # 的原子性来自「读全文 → 拼接 → 整文件替换」，逐行调用等价于每行重写一次
    # 整个文件（锚点文件已达数万行，O(n²) 不可接受）。
    if append_jsonl_atomic_many(
        _ANCHOR_PATH,
        [json.dumps(r, ensure_ascii=False) + "\n" for r in new_records],
        prefix=".dedup_anchors_",
        log_tag="dedup",
        noun="锚点文件",
    ):
        return
    # 写盘失败：撤回本次登记的 key，否则这些锚点会被永久判为"已写"而丢失
    with _WRITTEN_KEYS_LOCK:
        for r in new_records:
            _WRITTEN_ANCHOR_KEYS.discard(_anchor_key(r))


def _dedup_by_title(
    items: list[dict[str, Any]],
    cross_threshold: float = _CROSS_CANDIDATE_RATIO,
) -> list[dict[str, Any]]:
    """基于标准化标题模糊去重 + 中文实体 bigram 辅助判定。

    五档阈值策略（2026-08-17 基于 42560 条锚点分层采样校准）：
      - 同源：共享实体 bigram ≥ ``_SAME_SRC_BIGRAM_MIN``(4) 即合并。
        同源不会同时出现方向对立报道（如"突破3万亿"vs"跌破3万亿"），
        所以不依赖 SequenceMatcher 阈值，只检查实体重叠。
      - 跨源安全区：
        ① ratio ≥ ``_CROSS_DIRECT_RATIO``(0.65) 且专名 bg ≥ 1 直接合并（高相似改写重复，
           如"英国央行如期维持利率不变"vs"英国央行以6比3票数维持利率不变"）
        ② 0.50 ≤ ratio < 0.65 需专名 bg ≥ 2 才合并——旧规则直接合并导致
           40-50% 误合并（"行云科技签算力合同"vs"亿田智能签算力合同"共享模板骨架）
      - 跨源候选区：``_CROSS_CANDIDATE_RATIO``(0.35) ≤ ratio < 0.50，阶梯判定：
        ③ 共享 ≥ ``_CROSS_BIGRAM_MIN``(3) 个实体 bigram → 合并（高实体重叠，低 ratio 门槛）
        ④ 共享 ≥ 2 个实体 bigram 且 ratio ≥ bg=2 梯度阈值（0.375）且共享项含**真专名**
           （英数 token 需含字母，纯数字不算；见 ``_TOKEN_LIKE``）→ 合并
           （CPI/PPI、荣耀IPO 类共享专名 token 的真重复；纯中文公司名共享
           如"英伟达/伟达"、仅共享数字如"某指数 100 vs 另一指数 100"不代表同一事件）
        ⑤ 方向对立（上涨vs下跌/加息vs降息/站稳vs跌破分属两标题）且共享实体 → 不合并
        ⑥ 否则跳过（实体重叠不足或 ratio 太低）

    阈值全部取自本模块常量（``_CROSS_*`` / ``_SAME_SRC_BIGRAM_MIN``），校准工具
    从同一处读取；相似度口径的唯一实现在 :func:`_pair_similarity`。

    模板词治理：_STOP_BIGRAMS 扩充财报/回购/指数/预警/地震/目标价等模板词，
    提取 bigram 前整体掩码替换（_mask_stop），消除同类新闻共享模板骨架的虚高
    重叠。英文专名占位按长度分桶（_tk2_/_tk4_/_tk6_），不同长度英文词不再
    共享相似度。_normalize_title 保留空格防英文 token 粘连。
    """
    if not items:
        return items

    kept: list[dict[str, Any]] = []
    kept_norms: list[str] = []
    kept_sources: list[str] = []
    for item in items:
        norm = _normalize_title(item.get("title", ""))
        if not norm:
            kept.append(item)
            continue
        is_dup = False
        source = item.get("_source", "") or ""
        for idx, existing in enumerate(kept_norms):
            existing_src = kept_sources[idx]
            existing_item = kept[idx]
            same_source = bool(source) and bool(existing_src) and source == existing_src

            # ① 同源：共享实体 bigram ≥ 阈值即合并
            if same_source:
                overlap = _overlap_of_norms(norm, existing)
                if overlap >= _SAME_SRC_BIGRAM_MIN:
                    is_dup = True
                    break
                # 锚点：同源 bigram 接近阈值
                if 2 <= overlap <= 5:
                    _record_anchor(_make_anchor(item, existing_item, 0.0, overlap, False, "same_src"))

            # ② 跨源安全区：ratio ≥ 0.65 直接合并；0.50~0.65 需专名 bg ≥ 2
            #    剥离通用日期模式后比较，避免不同新闻因共享"2026年7月"等虚高；
            #    英文专名按长度分桶占位，避免共享专名（Anthropic/Meta/AMD）导致
            #    SequenceMatcher 比率虚高（英文专名在 _extract_entity_bigrams
            #    中已有独立处理，ratio 中可降权）。口径实现见 _ratio_of_norms。
            ratio = _ratio_of_norms(norm, existing)
            if ratio >= _CROSS_SAFE_RATIO:
                overlap = _overlap_of_norms(norm, existing)
                # ratio ≥ 0.65 直接合并也要求专名 bg ≥ 1：不同公司同模板
                # （"XX：2026年半年度净利润同比增长N%"）ratio 可高达 0.7+，
                # 但掩码后 bg=0（公司名不同），不能当作改写型重复。
                if ratio >= _CROSS_DIRECT_RATIO and overlap >= 1:
                    is_dup = True
                    break
                if overlap >= 2:
                    is_dup = True
                    # 锚点：跨源安全区合并样本（含擦边 0.50~0.65）
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_safe"))
                    break
                # 安全区但实体不足：跳过（记录锚点供校准，继续子串包含判定）
                _record_anchor(_make_anchor(item, existing_item, ratio, overlap, False, "cross_safe"))

            # ③ 跨源候选区：候选区入口 ≤ ratio < 0.50，需共享 ≥ 3 实体 bigram
            if not same_source and ratio >= cross_threshold:
                bg1 = _extract_entity_bigrams(norm)
                bg2 = _extract_entity_bigrams(existing)
                shared = bg1 & bg2
                overlap = len(shared)
                # ④ 方向对立检测：共享实体 + 相反方向词分属两标题 → 不合并
                #    （"美联储或暂缓加息"vs"城堡证券预计美联储将加息"）
                if overlap >= 1 and _has_opposite_direction(norm, existing):
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, False, "cross_opposite"))
                elif overlap >= _CROSS_BIGRAM_MIN:
                    is_dup = True
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_merge"))
                    break
                # ⑤ bg=2 梯度：中高 ratio + 共享**真专名** → 合并
                #    英数 token 需含字母（纯数字共享不算专名证据）、或 _tk 虚拟专名；
                #    CPI/PPI、荣耀IPO 等共享专名 token 的真重复靠此规则捕获。
                elif overlap >= 2 and ratio >= _CROSS_BG2_RATIO and any(_TOKEN_LIKE.match(s) for s in shared):
                    is_dup = True
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_merge_bg2"))
                    break
                # 锚点：跨源候选区但 bigram 不足
                _record_anchor(_make_anchor(item, existing_item, ratio, overlap, False, "cross_skip"))

            # ⑥ 子串包含
            if not is_dup:
                short, long = (norm, existing) if len(norm) <= len(existing) else (existing, norm)
                if len(short) >= 6 and short in long:
                    is_dup = True
                    break

        if not is_dup:
            kept_norms.append(norm)
            kept_sources.append(source)
            kept.append(item)
    return kept
