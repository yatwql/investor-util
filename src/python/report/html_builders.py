"""HTML 报告数据构建器 — 为模板渲染准备结构化数据。

包含持仓分类表、基金业绩分析等数据的构建函数，从 html_writer.py
拆分而来，降低主模块体积。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.fetcher.fund import fetch_fund_benchmark, fetch_fund_rankings
from src.python.models import Holding
from src.python.report.category import _categorize_holding
from src.python.report.fund_performance import (
    _RATING_COMMENT,
    _format_rank,
    _format_return,
    _fund_display_type,
    _is_fund,
)
from src.python.report.market_value import DetailRow
from src.python.report.progress import ProgressReporter, SilentProgressReporter

logger = logging.getLogger("invest")


def _build_category_data(
    holdings: list[Holding],
    details: list[DetailRow],
) -> list[dict[str, Any]]:
    """构建持仓分类表数据结构。

    按 (资产属性, 投资分类) 分组，汇总每组内的明细数据，
    按 股票→基金→债券→现金 顺序排列。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        持仓分类数据列表，每个元素含 property / sub_category / items / 小计字段
    """
    detail_map: Dict[str, DetailRow] = {d.code: d for d in details}

    cat_groups: dict[tuple[str, str], list[Holding]] = {}
    for h in holdings:
        prop, sub = _categorize_holding(h)
        cat_groups.setdefault((prop, sub), []).append(h)

    _PROP_ORDER = {"股票": 0, "基金": 1, "债券": 2, "现金": 3, "其他": 4}
    _SUB_ORDER = {
        "A股": 0, "QDII": 1, "主动": 2, "被动": 3,
        "指数": 4, "混合": 5, "纯债": 6, "货币": 7, "其他": 8,
    }
    sorted_groups = sorted(
        cat_groups.items(),
        key=lambda x: (
            _PROP_ORDER.get(x[0][0], 99),
            _SUB_ORDER.get(x[0][1], 99),
        ),
    )

    result: List[Dict[str, Any]] = []
    for (prop, sub), group in sorted_groups:
        items: list[dict[str, Any]] = []
        for h in group:
            d = detail_map.get(h.code)
            items.append({
                "name": h.name,
                "code": h.code,
                "market_value": d.market_value if d else 0.0,
                "cost": d.cost if d else 0.0,
                "profit": d.profit if d else 0.0,
                "profit_rate": d.profit_rate if d else 0.0,
                "today_profit": d.today_profit if d else 0.0,
            })

        sub_mv = sum(i["market_value"] for i in items)
        sub_cost = sum(i["cost"] for i in items)
        sub_profit = sum(i["profit"] for i in items)
        sub_today = sum(i["today_profit"] for i in items)
        sub_rate = sub_profit / sub_cost if sub_cost > 0 else 0.0

        result.append({
            "property": prop,
            "sub_category": sub,
            "items": items,
            "sub_mv": sub_mv,
            "sub_cost": sub_cost,
            "sub_profit": sub_profit,
            "sub_rate": sub_rate,
            "sub_today": sub_today,
        })

    return result


def _build_single_perf_item(
    idx: int, fund: Holding, detail_map: dict,
    prog: ProgressReporter, fund_count: int,
) -> dict[str, Any]:
    """构建单只基金的业绩分析条目。"""
    logger.info(
        "获取基金业绩 [%d/%d]: %s (%s)",
        idx, fund_count, fund.name, fund.code,
    )
    prog.info(f"基金业绩 [{idx}/{fund_count}]: {fund.name}")

    d = detail_map.get(fund.code)

    perf_data = fetch_fund_rankings(fund.code)
    rankings: dict[str, Any] = {}
    rating: str = ""

    if perf_data and perf_data.get("rankings"):
        rankings = perf_data.get("rankings", {})
        rating = perf_data.get("rating", "")
    else:
        logger.warning("基金 %s (%s) 业绩数据获取失败", fund.name, fund.code)

    type_label = _fund_display_type(fund)
    benchmark = fetch_fund_benchmark(fund.code)

    if d:
        profit_val = d.profit
        profit_rate_val = d.profit_rate
        profit_str = f"{profit_val:+,.2f}"
        profit_rate_str = f"{profit_rate_val * 100:+.2f}%"
    else:
        profit_val = 0.0
        profit_rate_val = 0.0
        profit_str = "--"
        profit_rate_str = "--"

    syl_3m = _format_return(rankings.get("近3月", {}).get("return"))
    syl_6m = _format_return(rankings.get("近6月", {}).get("return"))
    syl_1y = _format_return(rankings.get("近1年", {}).get("return"))

    syl_3m_raw = _parse_return_raw(rankings.get("近3月", {}).get("return"))
    syl_6m_raw = _parse_return_raw(rankings.get("近6月", {}).get("return"))
    syl_1y_raw = _parse_return_raw(rankings.get("近1年", {}).get("return"))

    rating_comment = _RATING_COMMENT.get(rating, "--")
    rank_str = _format_rank(rankings.get("同类排名", {}))

    return {
        "name": fund.name,
        "code": fund.code,
        "type_label": type_label,
        "syl_3m": syl_3m,
        "syl_6m": syl_6m,
        "syl_1y": syl_1y,
        "syl_3m_raw": syl_3m_raw,
        "syl_6m_raw": syl_6m_raw,
        "syl_1y_raw": syl_1y_raw,
        "profit": profit_str,
        "profit_rate": profit_rate_str,
        "profit_raw": profit_val,
        "profit_rate_raw": profit_rate_val,
        "benchmark": benchmark,
        "rating": rating_comment,
        "rating_tag": rating,
        "rank": rank_str,
    }


def _build_perf_data(
    holdings: list[Holding],
    details: list[DetailRow],
    progress: ProgressReporter | None = None,
) -> list[dict[str, Any]]:
    """构建基金业绩分析数据。

    筛选出基金持仓，对每只基金调用 API 获取区间收益和同类排名，
    按市值降序排列。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        业绩分析数据列表，每项含名称/代码/类型/收益率/排名等字符串值
    """
    prog = progress if progress is not None else SilentProgressReporter()
    fund_holdings = [h for h in holdings if _is_fund(h)]
    detail_map: Dict[str, DetailRow] = {d.code: d for d in details}

    fund_holdings_sorted = sorted(
        fund_holdings,
        key=lambda h: detail_map.get(h.code, DetailRow()).market_value,
        reverse=True,
    )

    result: List[Dict[str, Any]] = []
    for idx, fund in enumerate(fund_holdings_sorted, 1):
        result.append(_build_single_perf_item(idx, fund, detail_map, prog, len(fund_holdings_sorted)))

    if result:
        logger.info("基金业绩分析完成，%d 只基金获取成功", len(result))
    else:
        logger.info("基金业绩分析：无基金持仓")

    return result


def _parse_return_raw(val: Any) -> float | None:
    """解析收益率原始数值，用于着色判断。

    Args:
        val: 可为 None, "--", float, int

    Returns:
        数值，None 表示无法解析
    """
    if val is None or val == "--":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
