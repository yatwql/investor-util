"""穿透 TOP10 Excel 写入模块 — 从 penetration.py 拆分而来。

包含 write_penetration_sheet 及辅助函数，依赖 penetration.py 的
compute_penetration_top10 进行计算。
"""

from __future__ import annotations

import logging
from datetime import datetime

from openpyxl.worksheet.worksheet import Worksheet

from src.python.cache import get_cache_age_by_data_type, get_ttl
from src.python.code_utils import is_a_share_code
from src.python.models import Holding
from src.python.registry import get_llm_module_name, get_report_sheet_name
from src.python.report.data_status import (
    STATUS_MESSAGES,
    DataStatus,
    DataStatusItem,
    DegradationTracker,
)
from src.python.report.excel_writer import (
    _write_data_status_foot,
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

# 模块级降级阈值控制器（单会话内共享）
_tracker = DegradationTracker()

_NCOLS = 10
_CURRENT_YEAR = datetime.now().year
_HEADERS = [
    "排名", "名称", "代码", "穿透市值", "占比", "板块", "概念",
    f"预测EPS({_CURRENT_YEAR}E)", "年均股息", "来源明细",
]


def _get_eps_text(forecast: dict, codes: list[str]) -> str:
    """根据盈利预测数据和代码列表，查找匹配的预测 EPS 文本。"""
    if not forecast:
        return "--"
    for code in codes:
        info = forecast.get(code)
        if info:
            eps = info.get("eps_2026e")
            if eps is not None:
                return f"¥{eps:.2f}"
    return "--"


def _get_dividend_text(dividend_data: dict, codes: list[str]) -> str:
    """根据分红数据和代码列表，查找匹配的年均股息文本。"""
    if not dividend_data:
        return "--"
    for code in codes:
        info = dividend_data.get(code)
        if info and info.get("avg_dividend"):
            return f"{info['avg_dividend']:.4f}元/年"
    return "--"


def _load_profit_forecast_safe() -> tuple[dict, bool]:
    """加载盈利预测数据，失败时返回空字典。

    Returns:
        (forecast_dict, success) — success=False 表示 API 调用异常。
    """
    try:
        from src.python.fetcher.akshare import get_profit_forecast
        return get_profit_forecast(), True
    except Exception:
        logger.warning("[penetration] 盈利预测获取失败（非关键），EPS 列显示 --", exc_info=True)
        return {}, False


def _load_dividend_data_safe(result: dict) -> tuple[dict, bool]:
    """加载分红数据，失败时返回空字典。

    Returns:
        (dividend_dict, success) — success=False 表示 API 调用异常。
    """
    try:
        from src.python.fetcher.akshare import get_dividend_data
        all_top10_codes = list(set().union(*(entry.get("codes", []) for entry in result["top10"])))
        a_stock_codes = [c for c in all_top10_codes if is_a_share_code(c)]
        data = get_dividend_data(a_stock_codes) if a_stock_codes else {}
        return data, True
    except Exception:
        logger.warning("[penetration] 分红数据获取失败（非关键），年均股息列显示 --", exc_info=True)
        return {}, False


def build_penetration_data_status(
    result: dict,
    profit_success: bool = True,
    dividend_success: bool = True,
) -> DataStatus:
    """根据数据获取结果构建数据源状态字典。

    综合利用 DegradationTracker 阈值判断和缓存新鲜度，
    仅当超过阈值时才标记为不可用。

    Args:
        result: compute_penetration_top10 返回的结果字典
        profit_success: 盈利预测 API 是否成功
        dividend_success: 分红 API 是否成功

    Returns:
        数据源状态字典（可能为空 = 全部正常）
    """
    status: DataStatus = {}

    # 行业分类（T3，push2）
    if not result.get("industry_success", True):
        # 行业缓存按股票代码存储，取第一个可用代码检查缓存新鲜度
        _first_code = next(
            (_code for _entry in result.get("top10", []) for _code in (_entry.get("codes") or [])),
            None,
        )
        cache_age = get_cache_age_by_data_type("industry", _first_code) if _first_code else None
        _ind_ttl = get_ttl("industry")
        degraded, _, _ = _tracker.record(
            "penetration_industry", "T3", success=False,
            failure_type="unreachable",
            cache_age_hours=cache_age / 3600 if cache_age else None,
            cache_ttl_hours=_ind_ttl / 3600 if _ind_ttl else 24,
        )
        if degraded:
            status["industry"] = DataStatusItem(
                available=False, tier="T3",
                message=STATUS_MESSAGES["industry_unavailable"],
            )

    # 盈利预测（T4，akshare）
    if not profit_success:
        degraded, _, _ = _tracker.record(
            "penetration_profit_forecast", "T4", success=False,
        )
        if degraded:
            status["profit_forecast"] = DataStatusItem(
                available=False, tier="T4",
                message=STATUS_MESSAGES["profit_forecast_unavailable"],
            )

    # 分红数据（T4，akshare）
    if not dividend_success:
        degraded, _, _ = _tracker.record(
            "penetration_dividend", "T4", success=False,
        )
        if degraded:
            status["dividend"] = DataStatusItem(
                available=False, tier="T4",
                message=STATUS_MESSAGES["dividend_unavailable"],
            )

    return status


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

    result = penetration_data if penetration_data is not None else compute_penetration_top10(holdings, details)

    if not result["top10"]:
        write_data_row(ws, row, ["暂无穿透数据"])
        # 即使无 TOP10 数据，也检查是否有数据源失败需要展示状态
        data_status = build_penetration_data_status(result)
        _write_data_status_foot(ws, data_status, start_row=row + 1)
        freeze_header(ws, 2)
        auto_width(ws)
        logger.warning("%s无数据", get_llm_module_name("penetration_deep"))
        return

    summary = result["summary"]
    profit_forecast, profit_success = _load_profit_forecast_safe()
    dividend_data, dividend_success = _load_dividend_data_safe(result)

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

    row = _write_penetration_footer(ws, row, summary)
    data_status = build_penetration_data_status(result, profit_success, dividend_success)
    _write_data_status_foot(ws, data_status, start_row=row)
    freeze_header(ws, 2)
    auto_width(ws, min_width=10, max_width=40)

    logger.info("%s写入完成，合并 %d 个标的",
                get_report_sheet_name('penetration'), summary["merged_count"])


def _num_formats() -> list[str | None]:
    """每列的 Excel 数字格式。"""
    return [
        "",           # 1  排名
        "",           # 2  名称
        "",           # 3  代码
        FMT_MONEY,    # 4  穿透市值
        FMT_PERCENT,  # 5  占比
        "",           # 6  板块
        "",           # 7  概念
        "",           # 8  预测EPS(动态年份)
        "",           # 9  年均股息
        "",           # 10 来源明细
    ]
