"""报告模块加载器 — 模块发现 + ImportError 兜底。

职责：统一管理报告各模块的 import，提供 ImportError 降级/占位函数。
"""

from __future__ import annotations

from typing import Any

from src.python.core.logger import setup_logger
from src.python.core.registry import get_llm_module_name
from src.python.report.progress import ProgressReporter

logger = setup_logger()


def load_report_modules(prog: ProgressReporter) -> dict[str, Any]:
    """导入各报告模块（单独捕获），返回模块引用字典。"""
    try:
        from src.python.fetcher.index import fetch_indices, fetch_us_indices
    except ImportError:

        def fetch_indices() -> dict[str, dict[str, Any]]:
            return {}

        def fetch_us_indices() -> dict[str, dict[str, Any]]:
            return {}

        prog.add_error("市场指数模块缺失 (fetcher)")

    try:
        from src.python.report.excel_writer import create_workbook, save_workbook
    except ImportError:
        prog.add_error("Excel 报告核心模块缺失 (excel_writer)，无法生成报告")
        return {}

    modules: dict[str, Any] = {
        "fetch_indices": fetch_indices,
        "fetch_us_indices": fetch_us_indices,
        "create_workbook": create_workbook,
        "save_workbook": save_workbook,
    }

    try:
        from src.python.report.summary import write_summary_sheet

        modules["write_summary_sheet"] = write_summary_sheet
    except ImportError:
        modules["write_summary_sheet"] = None
        prog.add_error("汇总页模块缺失 (summary)")

    try:
        from src.python.report.category import write_category_sheet

        modules["write_category_sheet"] = write_category_sheet
    except ImportError:
        modules["write_category_sheet"] = None
        prog.add_error("持仓分类模块缺失 (category)")

    try:
        from src.python.report.market_value import (
            _generate_details,
            classify_holdings,
            get_last_trading_day,
            price_update_status,
        )

        modules.update(
            classify_holdings=classify_holdings,
            get_last_trading_day=get_last_trading_day,
            price_update_status=price_update_status,
            _generate_details=_generate_details,
        )
    except ImportError:
        modules.update(
            classify_holdings=lambda _: {},
            get_last_trading_day=lambda: "",
            price_update_status=lambda _a, _b: (0, 0, True),
            _generate_details=None,
        )
        prog.add_error("行情市值计算模块缺失 (market_value)")

    try:
        from src.python.report.market_value_sheet import write_market_value_sheet

        modules["write_market_value_sheet"] = write_market_value_sheet
    except ImportError:
        modules["write_market_value_sheet"] = None
        prog.add_error("行情市值写入模块缺失 (market_value_sheet)")

    try:
        from src.python.report.penetration import compute_penetration_top10
        from src.python.report.penetration_sheet import write_penetration_sheet

        modules["write_penetration_sheet"] = write_penetration_sheet
        modules["compute_penetration_top10"] = compute_penetration_top10
    except ImportError:
        modules["write_penetration_sheet"] = None
        modules["compute_penetration_top10"] = lambda _a, _b: {}
        prog.add_error(f"{get_llm_module_name('penetration_deep')}模块缺失 (penetration)")

    try:
        from src.python.report.fund_performance import write_fund_performance_sheet

        modules["write_fund_performance_sheet"] = write_fund_performance_sheet
    except ImportError:
        modules["write_fund_performance_sheet"] = None
        prog.add_error("基金业绩模块缺失 (fund_performance)")

    try:
        from src.python.report.fund_manager_analysis import build_first_check_summary, detect_manager_changes
        from src.python.report.fund_manager_sheet import write_fund_manager_sheet

        modules["detect_manager_changes"] = detect_manager_changes
        modules["write_fund_manager_sheet"] = write_fund_manager_sheet
        modules["build_first_check_summary"] = build_first_check_summary
    except ImportError:
        modules["detect_manager_changes"] = lambda _h: []
        modules["write_fund_manager_sheet"] = None
        prog.add_error("基金经理变更监控模块缺失 (fund_manager)")

    try:
        from src.python.report.fund_overlap import compute_overlap_matrix
        from src.python.report.fund_overlap_sheet import write_overlap_matrix_sheet

        modules["compute_overlap_matrix"] = compute_overlap_matrix
        modules["write_overlap_matrix_sheet"] = write_overlap_matrix_sheet
    except ImportError:
        modules["compute_overlap_matrix"] = lambda _fh, _mv=None: {}
        modules["write_overlap_matrix_sheet"] = None
        prog.add_error("持仓重合度矩阵模块缺失 (fund_overlap)")

    try:
        from src.python.report.fund_concentration import compute_concentration
        from src.python.report.fund_concentration_sheet import write_concentration_sheet

        modules["compute_concentration"] = compute_concentration
        modules["write_concentration_sheet"] = write_concentration_sheet
    except ImportError:
        modules["compute_concentration"] = lambda _fh: []
        modules["write_concentration_sheet"] = None
        prog.add_error("持仓集中度监控模块缺失 (fund_concentration)")

    try:
        from src.python.report.fund_style_report import analyze_style_for_all_funds
        from src.python.report.fund_style_sheet import write_style_sheet

        modules["analyze_style_for_all_funds"] = analyze_style_for_all_funds
        modules["write_style_sheet"] = write_style_sheet
    except ImportError:
        modules["analyze_style_for_all_funds"] = lambda _fh: {"results": []}
        modules["write_style_sheet"] = None
        prog.add_error("基金风格分析模块缺失 (fund_style)")

    try:
        from src.python.report.factor_exposure_sheet import write_factor_exposure_sheet

        modules["write_factor_exposure_sheet"] = write_factor_exposure_sheet
    except ImportError:
        modules["write_factor_exposure_sheet"] = None
        prog.add_error("因子暴露分析模块缺失 (factor_exposure)")

    return modules
