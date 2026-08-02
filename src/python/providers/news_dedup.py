"""新闻去重模块 — 标题模糊去重 + 实体 bigram 辅助判定 + 锚点采集。

包含 _dedup_by_title 去重核心逻辑及其依赖的所有常量和辅助函数。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 锚点采集（阈值校准用） ──────────────────────────────────────
# 每次 _dedup_by_title 运行后，边界案例收集到此列表，
# aggregate_news() 结束时追写至 data/cache/dedup_anchors.jsonl。
# 一条记录为一个 JSON 行，append-only。格式：
#   {"ts","title_a","title_b","source_a","source_b",
#    "ratio","bigram_overlap","decision","rule"}
_ANCHOR_RECORDS: list[dict[str, Any]] = []
_ANCHOR_LOCK = threading.Lock()
_ANCHOR_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "calibration",
    "dedup_anchors.jsonl",
)


def _record_anchor(record: dict[str, Any]) -> None:
    """线程安全地追加一条锚点记录。"""
    with _ANCHOR_LOCK:
        _ANCHOR_RECORDS.append(record)


def _normalize_title(title: str) -> str:
    """标准化标题：去标点、去空格、去常见前缀，过滤通用数字模式降虚高。

    数字模式（百分比、金额、年份、排名标记）在不同新闻中可能无意共享，导致
    SequenceMatcher 比率虚高和实体 bigram 中数字 token 的虚假重叠。
    过滤后同时降低 bigram 提取噪声和比率比较的误判。

    用于跨源标题去重，消除"快讯：""收评"等差异。
    """
    for prefix in (
        "快讯",
        "收评",
        "收盘",
        "早评",
        "午评",
        "盘中",
        "盘后",
        "数据图解",
        "CCI快报",
        "市场动态",
        "市场洞察",
        "行业深度",
        "周刊提前读",
        "公司观察",
        "量化观察",
        "刷屏",
        "尾盘",
        "华尔街见闻早餐",
    ):
        if title.startswith(prefix):
            title = title[len(prefix) :]
            break
    # 过滤通用数字模式，避免跨源去重时不同新闻因共享
    # "20%""25亿"等数字模式而获得虚高 SequenceMatcher 比率。
    # 日期模式（2026年/7月/8日）已在 _dedup_by_title 的 _RATIO_CLEAN 中处理，
    # 但前导日期（如 "7月18日美股成交额前20"）在 bigram 提取前剥离。
    title = re.sub(r"\d+(?:\.?\d+)?%", "", title)  # 20%、2.5%
    title = re.sub(r"\d+(?:\.?\d+)?[万亿]", "", title)  # 25亿、1.2万亿
    # 孤立 4 位年份数字（如 "WAIC 2026" → "WAIC"），避免不同年报道因共享英文
    # 事件名 + 不同年份标识导致 SequenceMatcher 比率虚高。
    title = re.sub(r"(?<=[a-zA-Z])\s*\d{4}\b", "", title)
    # 排名/列表标记（"前20""前10"），可安全移除的修饰语
    title = re.sub(r"前\d+", "", title)
    # 孤立 4 位年份数字（1900-2099），避免不同新闻因共享"2026"等年份数字
    # 在实体 bigram 提取和 SequenceMatcher 中产生虚假重叠。
    title = re.sub(r"\b(?:19|20)\d{2}\b", "", title)
    title = re.sub(r"[^\w一-鿿]", "", title)
    return title.strip().lower()


def _make_anchor(
    item_a: dict[str, Any],
    item_b: dict[str, Any],
    ratio: float,
    bigram_overlap: int,
    merged: bool,
    rule: str,
) -> dict[str, Any]:
    """构建一条锚点记录（边界案例），用于后续阈值校准。"""
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
    }


def _flush_anchors() -> None:
    """将内存中的锚点记录追写到 JSONL 文件，然后清空列表。

    一次运行产生数十条记录（~200 字节/条），文件写入发生在去重完成后，
    不影响新闻获取和报告生成的主流程。
    """
    global _ANCHOR_RECORDS
    if not _ANCHOR_RECORDS:
        return
    with _ANCHOR_LOCK:
        records = _ANCHOR_RECORDS
        _ANCHOR_RECORDS = []  # 先清空再写，防止递归写入
    try:
        os.makedirs(os.path.dirname(_ANCHOR_PATH), exist_ok=True)
        with open(_ANCHOR_PATH, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("锚点文件写入失败: %s", e)


# ── 高频财经常见动词/形容词/副垫 — 不作为实体判定依据 ──────
_STOP_BIGRAMS: set[str] = {
    "上调",
    "下跌",
    "上涨",
    "超越",
    "低于",
    "高于",
    "首次",
    "今日",
    "昨日",
    "本周",
    "上周",
    "本月",
    "上月",
    "盘中",
    "盘后",
    "早盘",
    "午盘",
    "收盘",
    "开盘",
    "不会",
    "将会",
    "成为",
    "宣布",
    "公布",
    "发布",
    "推动",
    "发力",
    "实现",
    "加大",
    "降低",
    "回升",
    "有望",
    "再度",
    "时隔",
    # 高频噪声：常见数理/报道用词
    "同比",
    "环比",
    "预计",
    "累计",
    "显示",
    "预期",
    "影响",
    "明显",
    "相关",
    "报告",
    "数据",
    "来源",
    "表示",
    "认为",
    "其中",
    "分别",
    "总额",
    "规定",
}


def _extract_entity_bigrams(text: str) -> set[str]:
    """提取标题中的实体特征：中文 bigram + 英数 token + 长英文专名加权。

    中文实体判定依赖 2-gram 重叠；英数 token 补全"AI""AMD"等被中文
    正则过滤的专名；长度 ≥ 4 的英文专名（Anthropic/Meta/Helios 等）
    额外插入 _tk: 前缀虚拟 bigram，使共享专名在 bigram 计数中获得
    权重加成，避免因英文专名占比高但 token 条数少而漏过候选区。
    """
    # 英数 token：长度 ≥ 2 避免单字符噪声
    tokens = re.findall(r"[a-zA-Z]+|[0-9]+", text)
    result: set[str] = set()
    for t in tokens:
        t_lower = t.lower()
        if len(t_lower) >= 2:
            result.add(t_lower)
            # 长英文专名（≥4 字符）额外插入虚拟 bigram 占用位，
            # 提升共享专名在实体重叠计数中的权重（如 Anthropic+Meta
            # 在 bg 计数中额外贡献 2 点，使 bg=2+2=4 进入合并区）。
            if t_lower.isalpha() and len(t_lower) >= 4:
                result.add(f"_tk:{t_lower}")
    # 中文 bigram
    chinese_only = re.sub(r"[^一-鿿]", "", text)
    for i in range(len(chinese_only) - 1):
        bg = chinese_only[i : i + 2]
        if bg not in _STOP_BIGRAMS:
            result.add(bg)
    return result


# 用于 SequenceMatcher 的归一化——剥离通用日期模式，避免
# "2026年7月票房破25亿" 与 "2026年7月经营质量因子" 等完全不同的
# 新闻因共享日期格式而获得虚高 ratio，进入不必要的候选区。
# ⚠ 仅用于 ratio 计算，不影响 kept_norms（后者用于 bigram 提取）。
_RATIO_CLEAN = re.compile(r"\d{4}年|\d+月|\d+日")
# 英文词占位化：用于 ratio 比较时降权共享英文专名（Anthropic/Meta 等），
# 避免 SequenceMatcher 比率虚高。英文专名在 _extract_entity_bigrams
# 中已有独立处理，不影响 bigram 提取。
_ENG_PLACEHOLDER = re.compile(r"[a-z]+")


def _dedup_by_title(
    items: list[dict[str, Any]],
    cross_threshold: float = 0.30,
) -> list[dict[str, Any]]:
    """基于标准化标题模糊去重 + 中文实体 bigram 辅助判定。

    四档阈值策略（基于 10.6 万条锚点校准，2026-07-30 更新）：
      - 同源：共享实体 bigram ≥ 4 即合并。
        同源不会同时出现方向对立报道（如"突破3万亿"vs"跌破3万亿"），
        所以不依赖 SequenceMatcher 阈值，只检查实体重叠。
      - 跨源：采用梯度阈值——
        ① ratio ≥ 0.50 安全区，直接合并
        ② cross_threshold ≤ ratio < 0.50，阶梯判定：
           - 共享 ≥ 3 个实体 bigram → 合并（高实体重叠，低 ratio 门槛）
           - 共享 ≥ 2 个实体 bigram 且 ratio ≥ 0.40 → 合并（中高 ratio 补偿）
           - 否则跳过（实体重叠不足或 ratio 太低）

    _normalize_title 剥离通用数字模式（百分比、金额、年份等）和前缀修饰语。
    ratio 比较前额外剥离日期模式和英文专名，避免虚高。英文专名的实体重叠
    由 _extract_entity_bigrams 独立处理。

    实体 bigram：
      - 提取中文 2-gram，过滤常见财经动词（上调/下跌/超越等）
      - 目的是确保双方有实质性公司/产品/概念实体重叠
    """
    from difflib import SequenceMatcher

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

            # ① 同源：共享实体 bigram ≥ 4 即合并
            if same_source:
                bg1 = _extract_entity_bigrams(norm)
                bg2 = _extract_entity_bigrams(existing)
                overlap = len(bg1 & bg2)
                if overlap >= 4:
                    is_dup = True
                    break
                # 锚点：同源 bigram 接近阈值
                if 2 <= overlap <= 5:
                    _record_anchor(_make_anchor(item, existing_item, 0.0, overlap, False, "same_src"))

            # ② 跨源安全区：ratio ≥ 0.50 直接合并
            #    剥离通用日期模式后比较，避免不同新闻因共享"2026年7月"等虚高
            _norm_clean = _RATIO_CLEAN.sub("", norm)
            _exist_clean = _RATIO_CLEAN.sub("", existing)
            # 英文专名占位化，避免共享专名（Anthropic/Meta/AMD）导致
            # SequenceMatcher 比率虚高（英文专名在 _extract_entity_bigrams
            # 中已有独立处理，ratio 中可降权）。
            _norm_clean = _ENG_PLACEHOLDER.sub("_tk_", _norm_clean)
            _exist_clean = _ENG_PLACEHOLDER.sub("_tk_", _exist_clean)
            ratio = SequenceMatcher(None, _norm_clean, _exist_clean).ratio()
            if ratio >= 0.50:
                is_dup = True
                # 锚点：跨源安全区擦边
                if ratio < 0.60:
                    _record_anchor(_make_anchor(item, existing_item, ratio, 0, True, "cross_safe"))
                break

            # ③ 跨源候选区：0.30 ≤ ratio < 0.50，需共享 ≥ 3 实体 bigram
            if not same_source and ratio >= cross_threshold:
                bg1 = _extract_entity_bigrams(norm)
                bg2 = _extract_entity_bigrams(existing)
                overlap = len(bg1 & bg2)
                if overlap >= 3:
                    is_dup = True
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_merge"))
                    break
                # ④ bg=2 梯度规则：中高 ratio + 有实体重叠 → 合并
                # 阈值 0.40 基于校准报告：bg≥2+ratio≥0.35 有 580 条含实体重叠被跳过，
                # 0.40 可额外捕获约 300-400 条真实重复，bg=2 已提供实体重叠安全垫
                if overlap >= 2 and ratio >= 0.40:
                    is_dup = True
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_merge_bg2"))
                    break
                # 锚点：跨源候选区但 bigram 不足
                _record_anchor(_make_anchor(item, existing_item, ratio, overlap, False, "cross_skip"))

            # ⑤ 子串包含
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
