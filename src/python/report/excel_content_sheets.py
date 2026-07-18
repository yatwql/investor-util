"""核心内容页签写入模块。

职责：写入汇总 / 分类 / 穿透 / 基金业绩 4 个核心页签。
提取自 excel_generator.py 的 _write_content_sheets。
"""

from __future__ import annotations

from typing import Any

from src.python.registry import get_report_sheet_name
from src.python.report.progress import ProgressReporter


def write_content_sheets(
    sheets: dict[str, Any],
    holdings: list,
    data: dict[str, Any],
    a_indices: dict,
    us_indices: dict,
    modules: dict[str, Any],
    prog: ProgressReporter,
) -> dict:
    """写入汇总 / 分类 / 穿透 / 基金业绩页签，返回穿透结果。"""
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
    )

    prog.call_sheet(
        get_report_sheet_name("category"),
        modules.get("write_category_sheet"),
        sheets["category"],
        holdings,
        data["details"],
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
