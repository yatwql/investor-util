"""统一财经新闻聚合器 — 多源获取 + 去重 + 关键词关联。

聚合四大财经新闻源，多源去重合并后按关键词关联度排序。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.constants import PROJECT_ROOT
from src.python.providers.news_correlator import correlate_news_with_holdings
from src.python.providers.news_sources import (
    _FETCH_MAP,
    _SOURCE_LABELS,
)

logger = logging.getLogger("invest")

# ── 锚点采集（阈值校准用） ──────────────────────────────────────
# 每次 _dedup_by_title 运行后，边界案例收集到此列表，
# aggregate_news() 结束时追写至 data/cache/dedup_anchors.jsonl。
# 一条记录为一个 JSON 行，append-only。格式：
#   {"ts","title_a","title_b","source_a","source_b",
#    "ratio","bigram_overlap","decision","rule"}
_ANCHOR_RECORDS: list[dict[str, Any]] = []
_ANCHOR_PATH = os.path.join(
    PROJECT_ROOT, "data", "cache", "dedup_anchors.jsonl",
)


def get_enabled_sources() -> list[str]:
    """返回当前启用的新闻来源名称列表。

    启停状态从 config.json 的 news_sources 字段读取。
    """
    from src.python.config import get_config

    config = get_config()
    enabled_map: dict[str, bool] = config.get("news_sources") or {}
    return [name for name in _SOURCE_LABELS if enabled_map.get(name, False)]


def _compute_cache_key(
    keywords: list[str],
    top_n: int,
    sources: list[str],
    per_source: int,
) -> str:
    """计算新闻缓存键。"""
    raw = json.dumps([keywords, top_n, sources, per_source], sort_keys=True, ensure_ascii=False)
    return "news_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _check_news_cache(cache_key: str, sources: list[str]) -> list[dict] | None:
    """检查新闻缓存，命中则直接返回缓存结果。"""
    from src.python.cache import get as _nget
    from src.python.cache import get_ttl as _get_news_ttl

    cached = _nget(cache_key, _get_news_ttl("news"))
    if cached is not None:
        logger.info("新闻缓存命中，跳过 %d 个源获取", len(sources))
    return cached


def _save_news_cache(cache_key: str, result: list[dict]) -> None:
    """保存新闻结果到缓存。"""
    from src.python.cache import set as _nset

    _nset(cache_key, result)


# ── 上次获取的各源状态（用于 D-7b 空态占位） ──────────────────

_last_src_results: dict[str, tuple[int, str]] = {}


def get_last_source_status() -> dict[str, dict]:
    """返回上次 aggregate_news() 调用的各源状态字典。

    Returns:
        {source_key: {"label": str, "success": bool, "count": int, "error": str | None}}
        source_key 是内部键名（如 "sina"、"eastmoney"），label 是中文标签。
    """
    result: dict[str, dict] = {}
    for src, (count, status) in _last_src_results.items():
        label = _SOURCE_LABELS.get(src, src)
        result[src] = {
            "label": label,
            "success": status == "OK",
            "count": count,
            "error": None if status == "OK" else status,
        }
    return result


def _fetch_from_all_sources(
    sources: list[str],
    per_source: int,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, str]]]:
    """从多个新闻源并行获取，去重合并。返回 (all_raw, src_results)。"""
    all_raw: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    src_results: dict[str, tuple[int, str]] = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        fut_to_src: dict[Any, str] = {}
        for src in sources:
            fetch_fn = _FETCH_MAP.get(src)
            if not fetch_fn:
                src_results[src] = (0, "未知源")
                continue
            fut = executor.submit(fetch_fn, per_source)
            fut_to_src[fut] = src

        for future in as_completed(fut_to_src):
            src = fut_to_src[future]
            label = _SOURCE_LABELS.get(src, src)
            try:
                items = future.result()
                count = 0
                for item in items:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_raw.append(item)
                        item["_source"] = label
                        count += 1
                src_results[src] = (count, "OK")
                if progress_callback:
                    progress_callback(label, count, "OK")
            except Exception as e:
                err_msg = f"失败({e})"
                src_results[src] = (0, err_msg)
                if progress_callback:
                    progress_callback(label, 0, err_msg)

    return all_raw, src_results


def _log_source_status(src_results: dict[str, tuple[int, str]]) -> None:
    """输出各新闻源状态汇总日志。"""
    status_parts = []
    for s, (n, st) in src_results.items():
        label = _SOURCE_LABELS.get(s, s)
        if st == "OK":
            status_parts.append(f"{label} {n}条")
        else:
            status_parts.append(f"{label} {st}")
    logger.info("新闻源状态: %s", " | ".join(status_parts))


def _normalize_title(title: str) -> str:
    """标准化标题：去标点、去空格、去常见前缀。

    用于跨源标题去重，消除"快讯：""收评"等差异。
    """
    import re

    for prefix in ("快讯", "收评", "收盘", "早评", "午评", "盘中", "盘后"):
        if title.startswith(prefix):
            title = title[len(prefix) :]
            break
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
    records = _ANCHOR_RECORDS
    _ANCHOR_RECORDS = []  # 先清空再写，防止递归写入
    try:
        os.makedirs(os.path.dirname(_ANCHOR_PATH), exist_ok=True)
        with open(_ANCHOR_PATH, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError:
        pass  # best effort，不影响主流程


def _dedup_by_title(
    items: list[dict[str, Any]],
    cross_threshold: float = 0.30,
) -> list[dict[str, Any]]:
    """基于标准化标题模糊去重 + 中文实体 bigram 辅助判定。

    两档阈值策略（基于 37 条真实新闻 24 对重复 + 23 对非重复校准）：
      - 同源：共享实体 bigram ≥ 2 即合并。
        同源不会同时出现方向对立报道（如"突破3万亿"vs"跌破3万亿"），
        所以不依赖 SequenceMatcher 阈值，只检查实体重叠。
      - 跨源：分成两段——
        ① ratio ≥ 0.50 安全区，直接合并
        ② cross_threshold ≤ ratio < 0.50，需共享 ≥ 2 个实体 bigram 防误杀

    实体 bigram：
      - 提取中文 2-gram，过滤常见财经动词（上调/下跌/超越等）
      - 目的是确保双方有实质性公司/产品/概念实体重叠
    """
    from difflib import SequenceMatcher
    import re

    if not items:
        return items

    # 中文财经常用动词/形容词 — 不作为实体判定依据
    _STOP_BIGRAMS: set[str] = {
        "上调", "下跌", "上涨", "超越", "低于", "高于",
        "首次", "今日", "昨日", "本周", "上周", "本月", "上月",
        "盘中", "盘后", "早盘", "午盘", "收盘", "开盘",
        "不会", "将会", "成为", "宣布", "公布", "发布",
        "推动", "发力", "实现", "加大", "降低", "回升",
        "有望", "再度", "时隔",
    }

    def _extract_entity_bigrams(text: str) -> set[str]:
        """提取标题中的中文实体 bigram，去掉动词/形容词 STOP。"""
        chinese_only = re.sub(r"[^一-鿿]", "", text)
        bigrams: set[str] = set()
        for i in range(len(chinese_only) - 1):
            bg = chinese_only[i : i + 2]
            if bg not in _STOP_BIGRAMS:
                bigrams.add(bg)
        return bigrams

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
                    _ANCHOR_RECORDS.append(_make_anchor(item, existing_item, 0.0, overlap, False, "same_src"))

            # ② 跨源安全区：ratio ≥ 0.50 直接合并
            ratio = SequenceMatcher(None, norm, existing).ratio()
            if ratio >= 0.50:
                is_dup = True
                # 锚点：跨源安全区擦边
                if ratio < 0.60:
                    _ANCHOR_RECORDS.append(_make_anchor(item, existing_item, ratio, 0, True, "cross_safe"))
                break

            # ③ 跨源候选区：0.30 ≤ ratio < 0.50，需共享 ≥ 3 实体 bigram
            if not same_source and ratio >= cross_threshold:
                bg1 = _extract_entity_bigrams(norm)
                bg2 = _extract_entity_bigrams(existing)
                overlap = len(bg1 & bg2)
                if overlap >= 3:
                    is_dup = True
                    _ANCHOR_RECORDS.append(_make_anchor(item, existing_item, ratio, overlap, True, "cross_merge"))
                    break
                # 锚点：跨源候选区但 bigram 不足
                _ANCHOR_RECORDS.append(_make_anchor(item, existing_item, ratio, overlap, False, "cross_skip"))

            # ④ 子串包含
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


def _finalize_news_results(
    all_raw: list[dict[str, Any]],
    keywords: list[str],
    top_n: int,
    lightweight_keywords: set[str] | None = None,
) -> list[dict[str, Any]]:
    """排序、关联关键词、确保 matched_keywords 字段、截取 TOP N。"""
    if not all_raw:
        return []

    # 按时间排序
    all_raw.sort(key=lambda item: item.get("ctime", ""), reverse=True)

    # 标题模糊去重（同一新闻跨源不同 URL）
    all_raw = _dedup_by_title(all_raw)

    # 与关键词关联
    correlated = correlate_news_with_holdings(
        all_raw,
        keywords,
        top_n=top_n,
        lightweight_keywords=lightweight_keywords,
    )

    # 确保 matched_keywords 字段
    for item in correlated:
        if "matched_keywords" not in item:
            item["matched_keywords"] = []

    return correlated[:top_n]


def aggregate_news(
    keywords: list[str],
    top_n: int = 100,
    sources: list[str] | None = None,
    per_source: int = 100,
    progress_callback: Callable[[str, int, str], None] | None = None,
    lightweight_keywords: set[str] | None = None,
) -> list[dict[str, Any]]:
    """从多个新闻源获取新闻，去重后按关键词关联度排序。

    流程：
      1. 从各源获取原始新闻（并行）
      2. 按 URL 去重合并
      3. 按发布时间排序 + 标题模糊去重
      4. 与关键词关联匹配
      5. 按匹配度降序返回 TOP N

    Args:
        keywords: 关键词列表
        top_n: 最多返回的关联新闻条数
        sources: 要使用的新闻源名称列表，默认使用全部启用的源
        per_source: 每个源获取的原始新闻条数
        progress_callback: 可选进度回调，签名为 (source_label, count, status)
            每次源获取完成后调用。status 为 "OK" 或 "失败原因"
        lightweight_keywords: 轻量级关键词集合（行业/概念），
            匹配此类关键词需要至少 2 个命中才视为关联。

    Returns:
        关联后的新闻列表，每项含 matched_keywords 字段
    """
    global _last_src_results

    if sources is None:
        sources = get_enabled_sources()

    cache_key = _compute_cache_key(keywords, top_n, sources, per_source)
    cached = _check_news_cache(cache_key, sources)
    if cached is not None:
        _last_src_results = {s: (0, "cache") for s in sources}
        return cached

    all_raw, src_results = _fetch_from_all_sources(sources, per_source, progress_callback)
    _last_src_results = src_results

    if not all_raw:
        logger.warning("所有新闻源均获取失败，请检查网络连接")
        return []

    logger.info("新闻汇总: 去重后共 %d 条 (来自 %d 个源)", len(all_raw), len(sources))

    result = _finalize_news_results(all_raw, keywords, top_n, lightweight_keywords=lightweight_keywords)
    _save_news_cache(cache_key, result)
    _flush_anchors()
    return result
