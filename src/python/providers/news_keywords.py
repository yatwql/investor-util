"""新闻关键词提取模块。

从持仓和穿透 TOP10 资产提取关键词，
用于后续新闻关联匹配。
"""

from __future__ import annotations

import logging
import re

from src.python.core.code_utils import is_etf_by_name, is_index_link_by_name
from src.python.core.models import Holding

logger = logging.getLogger("invest")


# 常见需要过滤的基金/ETF 后缀
_KEYWORD_FILTER_SUFFIXES = [
    "ETF",
    "联接",
    "A",
    "C",
    "(QDII)",
    "基金",
    "混合",
    "指数",
    "开放",
    "式",
    "发起",
    "LOF",
]


def _clean_name(name: str) -> str:
    """去除名称中的基金/ETF 后缀。"""
    for suffix in _KEYWORD_FILTER_SUFFIXES:
        name = name.replace(suffix, "")
    return name


def _extract_chinese_terms(text: str, min_len: int = 2) -> set[str]:
    """从文本中提取指定最小长度的中文词组。"""
    return {t for t in re.findall(r"[一-鿿]{2,}", text) if len(t) >= min_len}


def _extract_keywords_from_holding(h: Holding) -> set[str]:
    """从单只持仓提取关键词（代码 + 中文名称片段）。"""
    keywords: set[str] = set()
    name = h.name.strip()
    code = h.code.strip()

    if code:
        keywords.add(code)

    clean = _clean_name(name)
    keywords.update(_extract_chinese_terms(clean))

    if is_etf_by_name(name):
        core = name.replace("ETF", "").strip()
        keywords.update(_extract_chinese_terms(core))

    if is_index_link_by_name(name):
        parts = re.findall(r"[一-鿿]{2,}", name)
        if len(parts) >= 2:
            if len(parts[0]) >= 2:
                keywords.add(parts[0])
            for i in range(1, min(3, len(parts))):
                if len(parts[i]) >= 2:
                    keywords.add(parts[i])

    return keywords


def _extract_keywords_from_penetrated(asset: dict) -> set[str]:
    """从单只穿透资产提取关键词（代码 + 英文名称或中文片段）。"""
    keywords: set[str] = set()
    asset_name = (asset.get("name") or "").strip()
    asset_codes = asset.get("codes") or []

    for ac in asset_codes:
        if ac.strip():
            keywords.add(ac.strip())

    if asset_name:
        if re.match(r"^[A-Za-z0-9\s.&]+$", asset_name):
            keywords.add(asset_name)
        else:
            clean_name = _clean_name(asset_name)
            keywords.update(_extract_chinese_terms(clean_name))

    return keywords


def build_holding_keywords(
    holdings: list[Holding],
    penetrated_assets: list[dict] | None = None,
    max_keywords: int = 50,
) -> list[str]:
    """从持仓和穿透 TOP10 资产提取关键词。

    对于每只持仓，提取代码和有意义的中文名称片段；
    对于穿透资产，同样提取代码和名称。

    Args:
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产列表，每个含 name 和 codes 字段
        max_keywords: 最多返回的关键词数量

    Returns:
        关键词列表，按长度降序排列（长关键词优先匹配）
    """
    keywords: set[str] = set()

    for h in holdings:
        keywords.update(_extract_keywords_from_holding(h))

    if penetrated_assets:
        for asset in penetrated_assets:
            keywords.update(_extract_keywords_from_penetrated(asset))

    keywords.discard("")
    sorted_kw = sorted(keywords, key=lambda x: (-len(x), x))

    logger.debug(
        "关键词提取: %d 个 (持仓 %d + 穿透 %d)",
        len(sorted_kw[:max_keywords]),
        len(holdings),
        len(penetrated_assets) if penetrated_assets else 0,
    )
    return sorted_kw[:max_keywords]
