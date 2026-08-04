"""核心内容页签写入模块。

职责：写入汇总 / 分类 / 穿透 / 基金业绩 4 个核心页签。
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
) -> dict:
    """写入汇总 / 分类 / 穿透 / 基金业绩页签，返回穿透结果。

    Args:
        enable_cost_lots: 成本流水子模块开关。关闭时 fund_flow_data 不传
            （汇总/分类两章保持既有输出）；开启时透传 data["fund_flow_data"]
            （C19 契约：成本分档 + XIRR + 分红累计，无流水时 available=False）。
    """
    fund_flow_data = data.get("fund_flow_data") if enable_cost_lots else None

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
    )

    prog.call_sheet(
        get_report_sheet_name("category"),
        modules.get("write_category_sheet"),
        sheets["category"],
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
    )

    prog.call_sheet(
        get_report_sheet_name("fund_performance"),
        modules.get("write_fund_performance_sheet"),
        sheets["fund_performance"],
        holdings,
        data["details"],
    )

    return pen_result
