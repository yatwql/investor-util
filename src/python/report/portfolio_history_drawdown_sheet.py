"""组合历史走势与回撤 Excel 写入模块 — 走势表 + 回撤矩阵合一页签（一章两区块）。

物理合并原「组合历史走势」+「历史回撤分析」两个页签（§阶段 C 轮 9）：
  一、走势表（upper）—— 净值时间线 + 基准归一化 + 指标汇总（组合 vs 基准对比矩阵，仅一份）
  二、回撤矩阵（lower）—— 独立回撤事件明细（含恢复耗时）
  三、危机区间标注 —— 2015/2018/2020/2022 静态日期表 + 区间统计（区间回撤/恢复天数）

指标区（累计收益/最大回撤/波动率/起止日）在合并章中**只出现一次**（组合 vs 基准矩阵，
组合为第一列，天然包含原两章各自展示的组合指标）。数据不可用时整页写占位。
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from src.python.core.registry import get_report_section_number, get_report_sheet_name
from src.python.report.excel_writer import (
    _write_placeholder,
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.styles import FMT_MONEY, FMT_PERCENT

logger = logging.getLogger("invest")

# 回撤明细表列数（危机区间表、指标矩阵均 ≤ 此列数时可复用 ncols）
_DD_NCOLS = 8
# 危机区间表列数
_CRISIS_NCOLS = 6

# 危机标注说明行（C20：区间数据出 → 说明出）
_CRISIS_NOTE = (
    "说明：阴影/高亮区间为历史上 A 股主要危机时段（2015 股灾 / 2018 贸易摩擦 / "
    "2020 疫情冲击 / 2022 市场调整）；区间与报告数据窗口重叠时统计区间最大回撤与恢复耗时"
)


def _data_ok(history_data: dict | None) -> bool:
    """判断历史数据是否可渲染（非 None、非 unavailable、有 bars）。"""
    return bool(history_data and history_data.get("status") != "unavailable" and history_data.get("bars"))


def _compute_ncols(history_data: dict | None) -> int:
    """计算标题栏跨列数：走势表（4 + 基准数）与回撤明细（8）取最大。"""
    n_bm = len((history_data or {}).get("benchmarks", [])) if history_data else 0
    return max(4 + n_bm, _DD_NCOLS, _CRISIS_NCOLS)


def _apply_italic(ws: Worksheet, row: int, ncols: int) -> None:
    """将指定行整行字体置为斜体（说明/注释行，C20 图下说明）。"""
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = Font(italic=True)


def _write_trend_block(
    ws: Worksheet,
    row: int,
    history_data: dict,
    ncols: int,
) -> int:
    """写入一、走势表区块（净值时间线 + 指标汇总），返回下一行起始行号。"""
    write_title_row(ws, row, "一、走势表", ncols=ncols)
    row += 1

    bars = history_data.get("bars", [])
    benchmarks = history_data.get("benchmarks", [])
    n_bm = len(benchmarks)
    first_value = bars[0]["total_value"] if bars and bars[0].get("total_value") else 0

    headers = ["日期", "组合市值", "组合收益(%)", "组合归一化(%)"]
    for bm in benchmarks:
        headers.append(bm.get("name", bm.get("code", "基准")))
    row = write_header_row(ws, row, headers)

    for i, bar in enumerate(bars):
        tv = bar.get("total_value", 0)
        cum_return = (tv - first_value) / first_value if first_value > 0 else 0
        norm_value = tv / first_value * 100 if first_value > 0 else 0

        values = [bar.get("date", ""), tv, cum_return, round(norm_value, 2)]
        for bm in benchmarks:
            bm_bars = bm.get("bars", [])
            bm_value = bm_bars[i].get("value") if i < len(bm_bars) else None
            values.append(bm_value)

        fmts: list[str | None] = [None, FMT_MONEY, FMT_PERCENT, "0.00"]
        for _ in range(n_bm):
            fmts.append("0.00")
        row = write_data_row(ws, row, values, formats=fmts)

    # ── 指标汇总（组合 vs 基准对比矩阵，仅此一份） ──
    row += 1
    row = write_title_row(ws, row, "指标汇总（组合 vs 基准）", ncols=ncols)
    matrix_headers = ["指标", "组合"]
    for bm in benchmarks:
        matrix_headers.append(bm.get("name", bm.get("code", "基准")))
    row = write_header_row(ws, row, matrix_headers)

    pd = history_data
    metrics: list[tuple[str, Any, str | None, str, str | None]] = [
        ("累计收益率(%)", round(pd.get("total_return_pct", 0) / 100, 4), FMT_PERCENT, "total_return_pct", FMT_PERCENT),
        ("累计收益(元)", pd.get("total_return", 0), FMT_MONEY, None, None),
        ("最大回撤(%)", round(pd.get("max_drawdown_pct", 0) / 100, 4), FMT_PERCENT, "max_drawdown_pct", FMT_PERCENT),
        ("年化波动率", pd.get("annualized_volatility", 0), FMT_PERCENT, None, None),
        ("起算日", pd.get("data_start", ""), None, "data_start", None),
        ("终止日", pd.get("data_end", ""), None, "data_end", None),
    ]
    for metric_name, portfolio_val, portfolio_fmt, bm_key, bm_fmt in metrics:
        values = [metric_name, portfolio_val]
        for bm in benchmarks:
            if bm_key and bm.get(bm_key) is not None:
                raw = bm[bm_key]
                bm_val = round(raw / 100, 4) if bm_fmt == FMT_PERCENT else raw
            else:
                bm_val = None
            values.append(bm_val)
        flist: list[str | None] = [None, portfolio_fmt]
        for _ in range(n_bm):
            flist.append(bm_fmt if bm_key else None)
        row = write_data_row(ws, row, values, formats=flist)

    row += 1
    return row


def _write_drawdown_block(
    ws: Worksheet,
    row: int,
    history_data: dict,
    ncols: int,
) -> int:
    """写入二、回撤矩阵区块（独立回撤事件明细），返回下一行起始行号。"""
    write_title_row(ws, row, "二、回撤矩阵", ncols=ncols)
    row += 1

    dd_events = history_data.get("drawdown_events") or []
    ncols_eff = max(ncols, _DD_NCOLS)
    dd_headers = ["序号", "起峰日", "最深日", "恢复日", "最大回撤(%)", "持续天数", "恢复耗时(天)", "当前状态"]
    dd_headers += [""] * (ncols_eff - _DD_NCOLS)
    row = write_header_row(ws, row, dd_headers)
    if not dd_events:
        row = write_data_row(ws, row, ["未检测到显著回撤事件（或历史数据不足）"] + [None] * (ncols_eff - 1))
    else:
        for idx, e in enumerate(dd_events, start=1):
            cells: list[Any] = [
                idx,
                e.get("peak_date", ""),
                e.get("trough_date", ""),
                e.get("recovery_date") or "未恢复",
                round(e.get("drawdown_pct", 0.0) / 100, 4),
                e.get("duration_days", 0),
                e.get("recovery_days") if e.get("recovery_days") is not None else "--",
                "已恢复" if e.get("recovered") else "未恢复",
            ]
            cells += [None] * (ncols_eff - _DD_NCOLS)
            dd_fmts: list[str | None] = [None] * 4 + [FMT_PERCENT] + [None] * 3
            dd_fmts += [None] * (ncols_eff - _DD_NCOLS)
            row = write_data_row(ws, row, cells, formats=dd_fmts)

    row += 1
    return row


def _write_crisis_block(
    ws: Worksheet,
    row: int,
    crisis_annotation: dict[str, Any] | None,
    ncols: int,
) -> int:
    """写入三、危机区间标注区块（静态日期表 + 区间统计），返回下一行起始行号。"""
    write_title_row(ws, row, "三、危机区间标注", ncols=ncols)
    row += 1

    intervals = (crisis_annotation or {}).get("intervals", []) if crisis_annotation else []
    ncols_eff = max(ncols, _CRISIS_NCOLS)
    headers = ["危机名称", "区间", "区间最大回撤(%)", "最深日", "恢复耗时(天)", "状态"]
    headers += [""] * (ncols_eff - _CRISIS_NCOLS)
    row = write_header_row(ws, row, headers)

    in_range = [it for it in intervals if it.get("in_range")]
    if not intervals:
        row = write_data_row(ws, row, ["危机区间数据不可用"] + [None] * (ncols_eff - 1))
    elif not in_range:
        row = write_data_row(
            ws, row, ["报告数据窗口内无历史危机区间（2015/2018/2020/2022）"] + [None] * (ncols_eff - 1)
        )
    else:
        for it in in_range:
            dd_pct = it.get("interval_drawdown_pct")
            cells: list[Any] = [
                it.get("name", ""),
                f"{it.get('start', '')} ~ {it.get('end', '')}",
                round(dd_pct / 100, 4) if dd_pct is not None else None,
                it.get("trough_date", ""),
                it.get("recovery_days") if it.get("recovery_days") is not None else "--",
                "已恢复" if it.get("recovered") else "未恢复",
            ]
            cells += [None] * (ncols_eff - _CRISIS_NCOLS)
            fmts: list[str | None] = [None] * 2 + [FMT_PERCENT] + [None] * 3
            fmts += [None] * (ncols_eff - _CRISIS_NCOLS)
            row = write_data_row(ws, row, cells, formats=fmts)
        # 未重叠的危机区间以说明形式补充（供读者了解完整危机清单）
        out_of_range = [it for it in intervals if not it.get("in_range")]
        if out_of_range:
            names = "、".join(it.get("name", "") for it in out_of_range)
            row += 1
            row = write_data_row(ws, row, [f"数据窗口外（未重叠）：{names}"] + [None] * (ncols_eff - 1))
            _apply_italic(ws, row - 1, ncols_eff)

    row += 1
    row = write_data_row(ws, row, [_CRISIS_NOTE] + [None] * (ncols_eff - 1))
    _apply_italic(ws, row - 1, ncols_eff)
    return row


def write_portfolio_history_drawdown_sheet(
    ws: Worksheet,
    history_data: dict | None = None,
    crisis_annotation: dict[str, Any] | None = None,
) -> None:
    """写入组合历史走势与回撤页签（一章两区块：走势表 + 回撤矩阵 + 危机区间标注）。

    Args:
        ws: openpyxl Worksheet 对象。
        history_data: `history_data` C19 契约 dict（bars / 指标 / drawdown_events / benchmarks）。
            None、status=unavailable 或 bars 为空时整页写占位。
        crisis_annotation: `crisis_annotation_data` C19 契约 dict（危机区间标注）；
            None 时危机区块写"数据不可用"占位。
    """
    _name = get_report_sheet_name("portfolio_history_drawdown")
    ncols = _compute_ncols(history_data)
    write_title_row(ws, 1, f"{get_report_section_number('portfolio_history_drawdown')}. {_name}", ncols=ncols)

    if not _data_ok(history_data):
        _write_placeholder(ws, "组合历史走势与回撤数据暂不可用（配置或网络原因）", max_cols=ncols)
        auto_width(ws)
        logger.info("组合历史走势与回撤：数据不可用，写入整页占位")
        return

    row = 2
    row = _write_trend_block(ws, row, history_data, ncols)
    row = _write_drawdown_block(ws, row, history_data, ncols)
    row = _write_crisis_block(ws, row, crisis_annotation, ncols)

    freeze_header(ws, row=2)
    auto_width(ws, min_width=10, max_width=28)
    logger.info("组合历史走势与回撤页签写入完成")
