"""新闻关键词提取模块。

从持仓和穿透 TOP10 资产提取关键词，
用于后续新闻关联匹配。
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from src.models import Holding

logger = logging.getLogger("invest")


def build_holding_keywords(
    holdings: List[Holding],
    penetrated_assets: Optional[List[dict]] = None,
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

    # 常见需要过滤的基金/ETF 后缀
    _suffixes = [
        "ETF", "联接", "A", "C", "(QDII)", "基金", "混合",
        "指数", "开放", "式", "发起", "LOF",
    ]

    # ── 1) 从持仓提取 ──
    for h in holdings:
        name = h.name.strip()
        code = h.code.strip()

        if code:
            keywords.add(code)

        clean = name
        for suffix in _suffixes:
            clean = clean.replace(suffix, "")

        terms = re.findall(r"[一-鿿]{2,}", clean)
        for t in terms:
            keywords.add(t)

        if "ETF" in name:
            core = name.replace("ETF", "").strip()
            core_terms = re.findall(r"[一-鿿]{2,}", core)
            for t in core_terms:
                keywords.add(t)

        if "联接" in name:
            parts = re.findall(r"[一-鿿]{2,}", name)
            if len(parts) >= 2:
                keywords.add(parts[0] if len(parts[0]) >= 2 else "")
                for i in range(1, min(3, len(parts))):
                    if len(parts[i]) >= 2:
                        keywords.add(parts[i])

    # ── 2) 从穿透 TOP10 资产提取 ──
    if penetrated_assets:
        for asset in penetrated_assets:
            asset_name = (asset.get("name") or "").strip()
            asset_codes = asset.get("codes") or []

            for ac in asset_codes:
                if ac.strip():
                    keywords.add(ac.strip())

            if asset_name:
                if re.match(r"^[A-Za-z0-9\s.&]+$", asset_name):
                    keywords.add(asset_name)
                else:
                    clean_name = asset_name
                    for suffix in _suffixes:
                        clean_name = clean_name.replace(suffix, "")
                    terms = re.findall(r"[一-鿿]{2,}", clean_name)
                    for t in terms:
                        keywords.add(t)

    keywords.discard("")
    sorted_kw = sorted(keywords, key=lambda x: (-len(x), x))

    logger.debug(
        "关键词提取: %d 个 (持仓 %d + 穿透 %d)",
        len(sorted_kw[:max_keywords]),
        len(holdings),
        len(penetrated_assets) if penetrated_assets else 0,
    )
    return sorted_kw[:max_keywords]
