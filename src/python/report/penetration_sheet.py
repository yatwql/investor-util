"""穿透 TOP10 Excel 写入模块 — 从 penetration.py 拆分而来。

包含 write_penetration_sheet 及辅助函数，依赖 penetration.py 的
compute_penetration_top10 进行计算。
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from src.python.code_utils import is_a_share_code
from src.python.models import Holding
from src.python.registry import get_llm_module_name, get_report_sheet_name, set_sheet_title
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.market_value import DetailRow
from src.python.report.penetration import compute_penetration_top10
from src.python.report.styles import FMT_MONEY, FMT_PERCENT

logger = logging.getLogger("invest")

_NCOLS = 10
_HEADERS = [
    "排名", "名称", "代码", "穿透市值", "占比", "板块", "概念",
    "预测EPS(2026E)", "年均股息率", "来源明细",
]


def _get_eps_text(forecast: dict, codes: list[str]) -> str:
    """根据盈利预测数据和代码列表，查找匹配的预测 EPS 文本。"""
    if not forecast:
        return "--"
    for code in codes:
        info = forecast.get(code)
        if info:
            eps = info.get("eps_2025e")
            if eps is not None:
                return f"¥{eps:.2f}"
    return "--"


def _get_dividend_text(dividend_data: dict, codes: list[str]) -> str:
    """根据分红数据和代码列表，查找匹配的年均股息率文本。"""
    if not dividend_data:
        return "--"
    for code in codes:
        info = dividend_data.get(code)
        if info and info.get("avg_dividend"):
            return f"{info['avg_dividend']:.4f}元/年"
    return "--"


def _load_profit_forecast_safe() -> dict:
    """加载盈利预测数据，失败时返回空字典。"""
    try:
        from src.python.providers.akshare_extras import get_profit_forecast
        return get_profit_forecast()
    except Exception:
        logger.debug("盈利预测加载失败（非关键），EPS 列显示 --", exc_info=True)
        return {}


def _load_dividend_data_safe(result: dict) -> dict:
    """加载分红数据，失败时返回空字典。"""
    try:
        from src.python.providers.akshare_extras import get_dividend_data
        all_top10_codes = list(set().union(*(entry.get("codes", []) for entry in result["top10"])))
        a_stock_codes = [c for c in all_top10_codes if is_a_share_code(c)]
        return get_dividend_data(a_stock_codes) if a_stock_codes else {}
    except Exception:
        logger.debug("分红数据加载失败（非关键），年均股息率列显示 --", exc_info=True)
        return {}


def _write_penetration_footer(ws: Worksheet, row: int, summary: dict) -> int:
    """写入穿透页签底部备注和统计信息。返回写入后的行号。"""
    row += 1
    if summary["unknown_mv"] > 0:
        write_data_row(ws, row,
                       [f"* {summary['total_funds']} 只基金中，有 "
                        f"{summary['failed_funds']} 只无法获取穿透数据，"
                        f"合计市值 {summary['unknown_mv']:,.2f} 元未计入穿透 TOP10"],
                       [])
        row += 1
        failed_details = summary.get("failed_fund_details", [])
        if failed_details:
            failed_names = "；".join(
                f"{f['name']}({f['code']})" for f in failed_details
            )
            write_data_row(ws, row, [f"  无法获取穿透的基金：{failed_names}"])
            row += 1

    info_line = (
        f"基金 {summary['total_funds']} 只（{summary['fund_breakdown']}）"
        f" + 直接持股 {summary['total_stocks']} 只 → "
        f"穿透合并 {summary['merged_count']} 个标的，"
        f"TOP10 覆盖 {summary['top10_coverage_pct']:.1f}%"
    )
    write_data_row(ws, row, [info_line])
    return row


def write_penetration_sheet(
    ws: Worksheet,
    holdings: list[Holding],
    details: list[DetailRow],
    penetration_data: dict | None = None,
) -> None:
    """写入资产穿透TOP10。

    用 :func:`compute_penetration_top10` 计算数据后写入 Excel 行。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
        penetration_data: 预计算穿透数据。为 None 时自动计算，提供时跳过
                          内部重复计算，用于调用方已算过一轮的场景
    """
    row = write_title_row(ws, 1, get_report_sheet_name('penetration'), _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    if penetration_data is not None:
        result = penetration_data
    else:
        result = compute_penetration_top10(holdings, details)

    if not result["top10"]:
        write_data_row(ws, row, ["暂无穿透数据"])
        freeze_header(ws, 2)
        auto_width(ws)
        logger.warning("%s无数据", get_llm_module_name("penetration_deep"))
        return

    summary = result["summary"]
    profit_forecast = _load_profit_forecast_safe()
    dividend_data = _load_dividend_data_safe(result)

    for entry in result["top10"]:
        concepts = entry.get("concepts", [])
        concepts_str = " / ".join(concepts) if concepts else "--"
        codes = entry.get("codes", [])
        eps_text = _get_eps_text(profit_forecast, codes)
        div_text = _get_dividend_text(dividend_data, codes)
        vals = [
            entry["rank"],
            entry["name"],
            ", ".join(codes) if codes else "--",
            entry["mv"],
            entry["ratio_pct"] / 100.0,
            entry.get("sector", "--"),
            concepts_str,
            eps_text,
            div_text,
            "; ".join(entry["sources"]),
        ]
        write_data_row(ws, row, vals, _num_formats())
        row += 1

    _write_penetration_footer(ws, row, summary)
    freeze_header(ws, 2)
    auto_width(ws, min_width=10, max_width=40)

    logger.info("%s写入完成，合并 %d 个标的",
                get_report_sheet_name('penetration'), summary["merged_count"])


def _num_formats() -> list[str]:
    """每列的 Excel 数字格式。"""
    return [
        "",           # 1  排名
        "",           # 2  名称
        "",           # 3  代码
        FMT_MONEY,    # 4  穿透市值
        FMT_PERCENT,  # 5  占比
        "",           # 6  板块
        "",           # 7  概念
        "",           # 8  预测EPS(2026E)
        "",           # 9  年均股息率
        "",           # 10 来源明细
    ]
