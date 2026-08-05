"""HTML 报告展示映射子模块 — 数据契约 → 模板友好展示 dict。

承载把数据契约（fund_flow_data / market_temperature_data / valuation_data）
转换为 HTML 模板直接消费的展示映射函数。纯函数，无外部副作用。

由 `html_writer.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations


def _build_flow_display(fund_flow_data: dict | None) -> dict | None:
    """将成本流水数据（fund_flow_data）转成 HTML 模板友好展示映射（per-code 展示值）。

    复用 market_value_sheet._weighted_avg_cost / category._tier_label 计算逻辑，
    避免双实现。无数据或开关关闭时返回 None（模板不渲染成本流水列）。

    Args:
        fund_flow_data: 成本流水数据（None = 开关关闭）

    Returns:
        含 xirr_rate/cost_map/tier_map/div_map/div_total 的展示 dict，或 None
    """
    if not fund_flow_data:
        return None
    from src.python.report.category import _tier_label
    from src.python.report.market_value_sheet import _weighted_avg_cost

    cost_tiers = (fund_flow_data.get("cost_tiers") or {}).get("per_code", {})
    dividends = (fund_flow_data.get("dividends") or {}).get("per_code", {})
    xirr = fund_flow_data.get("xirr") or {}
    return {
        "available": bool(fund_flow_data.get("available")),
        "xirr_rate": xirr.get("rate"),
        "cost_map": {code: _weighted_avg_cost(buckets) for code, buckets in cost_tiers.items()},
        "tier_map": {code: _tier_label(buckets) for code, buckets in cost_tiers.items()},
        "div_map": dict(dividends),
        "div_total": float((fund_flow_data.get("dividends") or {}).get("total", 0.0) or 0.0),
    }


def _build_temperature_display(market_temperature_data: dict | None) -> dict | None:
    """将市场温度数据契约（market_temperature_data）转成 HTML 模板友好展示映射。

    Args:
        market_temperature_data: 市场温度数据契约（None = 开关关闭）。

    Returns:
        含 available/score/tier/components/index_name/disclaimer 的展示 dict，或 None。
    """
    from src.python.analysis.market_temperature import TEMPERATURE_DISCLAIMER

    if not market_temperature_data:
        return None
    if not market_temperature_data.get("available"):
        return {
            "available": False,
            "score": None,
            "tier": None,
            "components": None,
            "index_name": market_temperature_data.get("index_name") or "沪深300",
            "disclaimer": market_temperature_data.get("disclaimer") or TEMPERATURE_DISCLAIMER,
        }
    pct = market_temperature_data.get("price_percentile")
    dev = market_temperature_data.get("ma_deviation")
    vol = market_temperature_data.get("volatility")
    components = None
    if all(v is not None for v in (pct, dev, vol)):
        # 分位为 0~100，均线偏离/波动率为小数比例（0.032=3.2%），转百分数展示
        components = {
            "price_percentile": f"{pct:.1f}%",
            "ma_deviation": f"{dev * 100:+.1f}%",
            "volatility": f"{vol * 100:.1f}%",
        }
    return {
        "available": True,
        "score": market_temperature_data.get("score"),
        "tier": market_temperature_data.get("tier") or "合理",
        "components": components,
        "index_name": market_temperature_data.get("index_name") or "沪深300",
        "disclaimer": market_temperature_data.get("disclaimer") or TEMPERATURE_DISCLAIMER,
    }


def _attach_valuation_to_penetration(
    penetration: dict | None,
    valuation_data: dict | None,
) -> dict | None:
    """为穿透 TOP10 数据附加估值分位文本（返回新 dict，不修改原对象）。

    Args:
        penetration: 穿透 TOP10 数据（含 top10/summary）。
        valuation_data: 估值分位数据契约；None 时原样返回（不附加列）。

    Returns:
        新 penetration dict（每个 top10 条目增加 valuation_text 字段），
        或原 penetration（valuation_data 为 None）。
    """
    if not valuation_data or not penetration:
        return penetration
    from src.python.report.penetration_sheet import _get_valuation_text

    display = dict(penetration)
    top10 = []
    for entry in display.get("top10", []):
        e = dict(entry)
        e["valuation_text"] = _get_valuation_text(valuation_data, entry.get("codes", []))
        top10.append(e)
    display["top10"] = top10
    return display
