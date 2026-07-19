"""LLM 提示词表格模块 — 格式化和摘要构建函数。

P1-08-B 从 prompts.py 拆分，包含：
  - _format_holdings_block — 持仓明细格式化
  - _format_penetration_block — 穿透 TOP10 格式化
  - _calc_country_exposure — 国别/币种暴露计算
  - _build_holdings_summary — 持仓摘要构建（新闻关联分析用）
  - _build_news_correlation_summary — 新闻摘要构建
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.code_utils import is_a_share_code, is_hk_stock_code
from src.python.llm.prompts_core import _fmt_holding_line, _fmt_wan

logger = logging.getLogger("invest")



def _format_holdings_block(
    holdings_details: list[dict] | None, show_cost: bool = False, compact: bool = False, limit: int = 30
) -> str:
    """将持仓明细格式化为紧凑文本块（共享函数，消除 3 模块重复循环）。

    Args:
        holdings_details: 持仓明细列表
        show_cost: 是否显示成本
        compact: 是否省略今日涨跌幅（减少 token + 缓存更稳定）
        limit: 最大行数

    Returns:
        格式化的持仓明细文本块
    """
    if not holdings_details:
        return ""
    return "\n".join(_fmt_holding_line(h, show_cost=show_cost, compact=compact) for h in holdings_details[:limit])


def _format_penetration_block(penetrated_assets: list[dict] | None, limit: int = 10) -> str:
    """将穿透 TOP10 格式化为紧凑文本块（共享函数）。

    Args:
        penetrated_assets: 穿透资产列表
        limit: 最大条目数

    Returns:
        格式化的穿透文本块
    """
    if not penetrated_assets:
        return ""
    assets = []
    for asset in penetrated_assets[:limit]:
        name = asset.get("name", "")
        codes = ",".join(asset.get("codes", []))
        mv = asset.get("mv", 0)
        sector = asset.get("sector", "--")
        assets.append(f"{name}({codes}){_fmt_wan(mv)}/{sector}")
    return " | 穿透:" + " ".join(assets)


def _calc_country_exposure(holdings_details: list[dict] | None) -> list[str]:
    """从持仓明细计算国别/币种分布，返回格式化行列表。"""
    exposure: dict[str, float] = {}
    if holdings_details:
        for h in holdings_details:
            code = h.get("code", "")
            mv = h.get("market_value", 0)

            if is_a_share_code(code):
                country = "A股"
            elif is_hk_stock_code(code):
                country = "港股"
            elif code.upper().endswith(".US"):
                country = "美股"
            else:
                country = "其他"

            exposure[country] = exposure.get(country, 0) + mv
    return [f"{k}: {_fmt_wan(v)}" for k, v in sorted(exposure.items(), key=lambda x: -x[1])]


# ═══════════════════════════════════════════════════════════
#  新闻关联分析
# ═══════════════════════════════════════════════════════════


def _build_holdings_summary(
    holdings: list,
    penetrated_assets: list | None = None,
    industry_data: dict[str, dict] | None = None,
) -> str:
    """构建持仓摘要文本（紧凑格式），供财经新闻热点与持仓关联分析 Prompt 使用。

    可选注入行业分类和概念板块信息（industry_data），
    使 LLM 能更准确判断新闻对持仓的利好/利空影响。

    Args:
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产（可选）
        industry_data: 行业/概念数据 {code: {industry, concepts, ...}}（可选）

    Returns:
        紧凑格式的持仓摘要文本
    """
    lines: list[str] = []
    for i, h in enumerate(holdings[:20]):
        code = (h.code or "").strip()
        line = f"{i + 1}. {h.name} ({code})"
        if industry_data and code in industry_data:
            idata = industry_data[code]
            tags = []
            if idata.get("industry"):
                tags.append(idata["industry"])
            if idata.get("concepts"):
                tags.extend(idata["concepts"][:3])
            if tags:
                line += f" [{'·'.join(tags)}]"
        lines.append(line)
    if penetrated_assets:
        for a in penetrated_assets[:10]:
            name = a.get("name", "")
            codes = ",".join(a.get("codes", []))
            line = f"    [穿透] {name} ({codes})"
            if industry_data:
                tags = []
                for ac in a.get("codes") or []:
                    ac = ac.strip()
                    if ac in industry_data:
                        idata = industry_data[ac]
                        if idata.get("industry"):
                            tags.append(idata["industry"])
                        if idata.get("concepts"):
                            tags.extend(idata["concepts"][:2])
                if tags:
                    line += f" [{'·'.join(tags)}]"
            lines.append(line)
    return "\n".join(lines)


def _build_news_correlation_summary(news_data: list[dict]) -> str:
    """构建新闻摘要文本（紧凑格式），供财经新闻热点与持仓关联分析 Prompt 使用。

    Args:
        news_data: 关键词匹配后的新闻列表，取前 30 条

    Returns:
        紧凑格式的新闻摘要文本
    """
    parts: list[str] = []
    for i, item in enumerate(news_data[:30]):
        title = (item.get("title") or "")[:120]
        intro = (item.get("intro") or "")[:150]
        keywords = ", ".join(item.get("matched_keywords", []))
        parts.append(f"[{i}] 标题: {title}\n    摘要: {intro}\n    关键词: {keywords or '--'}")
    return "\n".join(parts)


__all__ = [
    "_format_holdings_block",
    "_format_penetration_block",
    "_calc_country_exposure",
    "_build_holdings_summary",
    "_build_news_correlation_summary",
]
