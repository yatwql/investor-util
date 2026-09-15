"""核心内容页签写入模块。

职责：写入汇总 / 持仓明细与分类 / 穿透 / 基金业绩 4 个核心页签。
"""

from __future__ import annotations

from typing import Any

from src.python.core.registry import get_report_sheet_name
from src.python.report.progress import ProgressReporter


def write_content_sheets(
    sheets: dict[str, Any],
    holdings: list,
    data: dict[str, Any],
    a_indices: dict,
    us_indices: dict,
    modules: dict[str, Any],
    prog: ProgressReporter,
    enable_cost_lots: bool = False,
    valuation_data: dict | None = None,
    market_temperature_data: dict | None = None,
    enable_fund_deep_analysis: bool = False,
) -> dict:
    """写入汇总 / 持仓明细与分类 / 穿透 / 基金业绩页签，返回穿透结果。

    Args:
        enable_cost_lots: 成本流水子模块开关。关闭时 fund_flow_data 不传
            （汇总/持仓明细与分类两章保持既有输出）；开启时透传 data["fund_flow_data"]
            （数据契约：成本分档 + XIRR + 分红累计，无流水时 available=False）。
        valuation_data: 估值分位数据契约（「资产穿透TOP10」估值分位列），
            开关关闭或 None 时穿透页签保持既有输出（10 列）。
        market_temperature_data: 市场温度数据契约（「投资分析汇总」温度刻度行），
            开关关闭或 None 时汇总页签保持既有输出。
    """
    fund_flow_data = data.get("fund_flow_data") if enable_cost_lots else None

    # 基金经理变更监控：作为「基金业绩分析」章节的子区块（随 enable_fund_deep_analysis 显隐）。
    # 若不开启基金深度分析则传 None（区块整体不写）。
    manager_data: list | None = None
    if enable_fund_deep_analysis:
        detect = modules.get("detect_manager_changes")
        if detect is not None:
            prog.info("正在分析基金经理变更...")
            try:
                manager_data = detect(holdings)
            except Exception as e:  # noqa: BLE001 - 保持既有隔离：数据失败不影响主表
                import logging

                logging.getLogger("invest").warning("基金经理变更监控数据获取失败: %s", e)
                prog.add_error("基金经理变更监控数据获取失败")
                manager_data = None

    prog.call_sheet(
        get_report_sheet_name("summary"),
        modules.get("write_summary_sheet"),
        sheets["summary"],
        data["total_mv"],
        data["total_cost"],
        data["total_profit"],
        data["today_profit"],
        categories=data["categories"],
        update_status=data["update_status"],
        a_indices=a_indices,
        us_indices=us_indices,
        fund_flow_data=fund_flow_data,
        market_temperature_data=market_temperature_data,
    )

    prog.call_sheet(
        get_report_sheet_name("holdings_detail"),
        modules.get("write_holdings_detail_sheet"),
        sheets["holdings_detail"],
        holdings,
        data["details"],
        fund_flow_data=fund_flow_data,
    )

    compute_pen = modules.get("compute_penetration_top10", lambda _a, _b: {})
    pen_result = compute_pen(holdings, data["details"])
    prog.ok("资产穿透TOP10 计算完成")
    prog.call_sheet(
        get_report_sheet_name("penetration"),
        modules.get("write_penetration_sheet"),
        sheets["penetration"],
        holdings,
        data["details"],
        penetration_data=pen_result,
        valuation_data=valuation_data,
    )

    prog.call_sheet(
        get_report_sheet_name("fund_performance"),
        modules.get("write_fund_performance_sheet"),
        sheets["fund_performance"],
        holdings,
        data["details"],
        manager_data=manager_data,
    )

    return pen_result
