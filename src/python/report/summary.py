"""汇总模块 — 报告第 1 页。

显示当前日期、持仓概况（分类统计+价格更新状态）、盈亏汇总、市场指数。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from src.python.registry import get_llm_module_name, get_report_sheet_name
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.market_value import get_last_trading_day
from src.python.report.styles import profit_font

# 指数涨跌颜色
_INDEX_UP_FONT = Font(size=10, bold=True, color="CC0000")    # 涨→红
_INDEX_DOWN_FONT = Font(size=10, bold=True, color="009900")  # 跌→绿

# 单元格对齐
_CENTER_ALIGN = Alignment(horizontal="center", vertical="center")

logger = logging.getLogger("invest")

_NCOLS = 8
_HEADERS = ["指标", "数值"]

# 样式
_SECTION_FONT = Font(size=11, bold=True, color="2E75B6")  # 章节标题：深蓝
_BLUE_FONT = Font(size=10, bold=True, color="2E75B6")      # 更新完成：蓝色
_RED_FONT = Font(size=10, bold=True, color="CC0000")        # 未完成：红色
_NORMAL_FONT = Font(size=10)


def _write_section(ws, row: int, label: str) -> int:
    """写入章节标题行（如 【持仓概况】），占 2 列合并。"""
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=_NCOLS)
    cell = ws.cell(row=row, column=1, value=label)
    cell.font = _SECTION_FONT
    cell.alignment = _CENTER_ALIGN
    return row + 1


def _write_kv_row(ws, row: int, key: str, value: Any) -> int:
    """写入一个指标=数值行（标准 2 列）。"""
    write_data_row(ws, row, [key, value])
    return row + 1


def _write_kv_row_colored(ws, row: int, key: str, value: Any,
                           font: Font) -> int:
    """写入带颜色的指标行。"""
    write_data_row(ws, row, [key, value])
    for col in (1, 2):
        ws.cell(row=row, column=col).font = font
    return row + 1


def _write_index_row(ws, row: int, name: str, price: float, change_pct: float) -> int:
    """写入指数行，涨跌幅自动着色（涨红跌绿）。

    Args:
        ws: 工作表
        row: 当前行号
        name: 指数中文名
        price: 当前点数
        change_pct: 涨跌幅百分数（如 0.35 表示 +0.35%）

    Returns:
        下一行号
    """
    sign = "+" if change_pct >= 0 else ""
    label = f"  {name}"
    value = f"{price:.2f}  ({sign}{change_pct:.2f}%)"
    write_data_row(ws, row, [label, value])
    font = _INDEX_UP_FONT if change_pct >= 0 else _INDEX_DOWN_FONT
    ws.cell(row=row, column=2).font = font
    return row + 1


def _write_blanks(ws, row: int, n: int = 1) -> int:
    """写入 n 行空白。"""
    return row + n


def _write_basic_info(ws: Worksheet, row: int, now: datetime | None = None) -> int:
    """写入基本信息和所属交易日。

    Args:
        ws: 工作表
        row: 当前行号
        now: 当前时间（允许外部注入便于测试）
    """
    now = now or datetime.now()
    row = _write_kv_row(ws, row, "统计时间", now.strftime("%Y-%m-%d %H:%M:%S"))
    row = _write_kv_row(ws, row, "所属交易日", get_last_trading_day())
    row = _write_blanks(ws, row)
    return row


def _write_holdings_overview(
    ws: Worksheet, row: int,
    categories: dict[str, list] | None,
    update_status: tuple[int, int, bool] | None,
) -> int:
    """写入持仓概况分类计数和价格更新状态。"""
    row = _write_section(ws, row, "【持仓概况】")
    total_count = 0
    if categories:
        for cat_label in ("场内股票", "场内ETF", "国内场外", "QDII"):
            count = len(categories.get(cat_label, []))
            total_count += count
            row = _write_kv_row(ws, row, f"  {cat_label}", count)
        row = _write_kv_row(ws, row, "持仓总数", total_count)
    else:
        row = _write_kv_row(ws, row, "持仓总数", "--")

    if update_status:
        updated, total, all_done = update_status
        if total > 0:
            status_text = f"{updated}/{total}  (全部已更新)" if all_done else f"{updated}/{total}  (尚有缺失)"
            status_font = _BLUE_FONT if all_done else _RED_FONT
        else:
            status_text = "--"
            status_font = _NORMAL_FONT
        row = _write_kv_row_colored(ws, row, "价格更新状态", status_text, status_font)
    else:
        row = _write_kv_row(ws, row, "价格更新状态", "--")
    row = _write_blanks(ws, row)
    return row


def _write_profit_summary(
    ws: Worksheet, row: int,
    total_mv: float, total_cost: float, total_profit: float, today_profit: float,
) -> int:
    """写入盈亏汇总（数值以原始小数/金额写入，由 Excel 数字格式控制显示）。"""
    profit_rate = (total_profit / total_cost) if total_cost > 0 else 0.0  # 小数，0.00% 格式
    denominator = total_cost + total_profit - today_profit
    today_rate = (today_profit / denominator) if denominator > 0 else 0.0  # 小数，0.00% 格式

    from src.python.report.styles import FMT_MONEY, FMT_PERCENT
    row = _write_section(ws, row, "【盈亏汇总】")
    summary_data: list[tuple[str, float, str]] = [
        ("总市值 (元)", total_mv, FMT_MONEY),
        ("总成本 (元)", total_cost, FMT_MONEY),
        ("总盈亏 (元)", total_profit, FMT_MONEY),
        ("总收益率", profit_rate, FMT_PERCENT),
        ("本日盈亏 (元)", today_profit, FMT_MONEY),
        ("本日收益率", today_rate, FMT_PERCENT),
    ]
    for label, val, fmt in summary_data:
        write_data_row(ws, row, [label, val])
        ws.cell(row=row, column=2).number_format = fmt
        if "盈亏" in label and isinstance(val, (int, float)):
            ws.cell(row=row, column=2).font = profit_font(val)
        elif "收益率" in label and isinstance(val, (int, float)):
            ws.cell(row=row, column=2).font = profit_font(val)
        row += 1

    row = _write_blanks(ws, row)
    return row


def _write_a_share_indices(ws: Worksheet, row: int, a_indices: dict[str, dict[str, Any]] | None) -> int:
    """写入 A 股指数（本日 + 上日）。"""
    if not a_indices:
        return _write_kv_row(ws, row, "── A股指数 ──", "暂无数据")

    row = _write_kv_row(ws, row, "── A股指数（本日）──", "")
    a_list = [
        ("sh000001", "上证指数"), ("sz399001", "深证成指"),
        ("sh000300", "沪深300"), ("sh000688", "科创板50"),
        ("sz399006", "创业板指"),
    ]
    for code, cname in a_list:
        idx = a_indices.get(code)
        if idx and idx.get("price", 0) > 0:
            row = _write_index_row(ws, row, cname, idx["price"], idx.get("change_pct", 0))
        else:
            row = _write_kv_row(ws, row, f"  {cname}", "--")

    row = _write_kv_row(ws, row, "── A股指数（上日）──", "")
    for code, cname in a_list:
        idx = a_indices.get(code)
        yclose = idx.get("yesterday_close", 0) if idx else 0
        if yclose > 0:
            row = _write_kv_row(ws, row, f"  {cname}", f"{yclose:.2f}")
        else:
            row = _write_kv_row(ws, row, f"  {cname}", "--")
    return row


def _write_us_indices(ws: Worksheet, row: int, us_indices: dict[str, dict[str, Any]] | None) -> int:
    """写入美股指数（最新 + 上日）。"""
    if not us_indices:
        return _write_kv_row(ws, row, "── 美股指数 ──", "暂无数据")

    row = _write_kv_row(ws, row, "── 美股指数（最新）──", "")
    us_list = [
        ("gb_dji", "道琼斯"), ("gb_ixic", "纳斯达克"), ("gb_inx", "标普500"),
    ]
    for code, cname in us_list:
        idx = us_indices.get(code)
        if idx and idx.get("price", 0) > 0:
            row = _write_index_row(ws, row, cname, idx["price"], idx.get("change_pct", 0))
        else:
            row = _write_kv_row(ws, row, f"  {cname}", "--")

    row = _write_kv_row(ws, row, "── 美股指数（上日）──", "")
    for code, cname in us_list:
        idx = us_indices.get(code)
        yclose = idx.get("yesterday_close", 0) if idx else 0
        if yclose > 0:
            row = _write_kv_row(ws, row, f"  {cname}", f"{yclose:.2f}")
        else:
            row = _write_kv_row(ws, row, f"  {cname}", "--")
    return row


def write_summary_sheet(
    ws: Worksheet,
    total_mv: float,
    total_cost: float,
    total_profit: float,
    today_profit: float,
    categories: dict[str, list] | None = None,
    update_status: tuple[int, int, bool] | None = None,
    a_indices: dict[str, dict[str, Any]] | None = None,
    us_indices: dict[str, dict[str, Any]] | None = None,
) -> None:
    """写入投资分析汇总。

    Args:
        ws: 目标工作表
        total_mv: 总市值
        total_cost: 总成本
        total_profit: 总盈亏
        today_profit: 本日总盈亏
        categories: 分类结果 {类型: [Holdings]}，来自 classify_holdings()
        update_status: (已更新数, 总数, 是否全部更新)，来自 price_update_status()
        a_indices: A 股指数 {代码: {name, price, yesterday_close, change_pct}}
        us_indices: 美股指数 {代码: {name, price, yesterday_close, change_pct}}
    """
    ws.title = f"1.{get_report_sheet_name('summary')}"

    row = write_title_row(ws, 1, get_report_sheet_name('summary'), _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    row = _write_basic_info(ws, row)
    row = _write_holdings_overview(ws, row, categories, update_status)
    row = _write_profit_summary(ws, row, total_mv, total_cost, total_profit, today_profit)
    row = _write_blanks(ws, row)

    # ── 市场指数 ──
    row = _write_section(ws, row, "【市场指数】")
    row = _write_a_share_indices(ws, row, a_indices)
    row = _write_blanks(ws, row)
    row = _write_us_indices(ws, row, us_indices)

    freeze_header(ws, 2)
    auto_width(ws)
    logger.info("投资分析汇总写入完成，共 %d 行", row)



def _init_llm_usage_sheet(wb: Any, title: str) -> tuple[Any, int]:
    """创建 LLM 用量页签并移动到最右侧，返回 (ws, row)。"""
    ws = wb.create_sheet()
    ws.title = title
    sheets = wb.sheetnames
    current_idx = sheets.index(title)
    last_idx = len(sheets) - 1
    if current_idx != last_idx:
        wb.move_sheet(title, offset=last_idx - current_idx)
    row = write_title_row(ws, 1, title, 10)
    row += 1
    _SUB_FONT = Font(size=9, color="666666")
    ws.cell(row=row, column=1,
            value="以下展示本次 LLM 全量生成的 API 调用统计和模块明细，帮助了解 Token 消耗和费用构成。")
    ws.cell(row=row, column=1).font = _SUB_FONT
    row += 2
    return ws, row


def _write_llm_summary_section(ws: Any, row: int, session_usage: dict) -> int:
    """写入 LLM 用量汇总数据区，返回下一行号。"""
    if not session_usage or not session_usage.get("has_usage"):
        return row

    _SECTION_FILL = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")
    _SECTION_FONT = Font(size=10, bold=True, color="1A1A1A")
    _KV_KEY_FONT = Font(size=10, bold=True, color="2E75B6")
    _KV_VAL_FONT = Font(size=10)

    for ci in range(1, 3):
        ws.cell(row=row, column=ci).fill = _SECTION_FILL
    ws.cell(row=row, column=1, value="▎汇总数据").font = _SECTION_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    row += 1

    pairs = [
        ("API 调用次数", f"{session_usage.get('call_count', 0)} 次"),
        ("模型", session_usage.get("model_display", "未指定")),
        ("输入 Token", f"{session_usage.get('input_tokens', 0):,}"),
        ("输出 Token", f"{session_usage.get('output_tokens', 0):,}"),
        ("总 Token", f"{session_usage.get('total_tokens', 0):,}"),
    ]
    _cache_hit = session_usage.get("cache_hit_tokens", 0)
    if _cache_hit:
        pairs.append(("缓存命中 Token", f"{_cache_hit:,}"))
    pairs.append(("累计费用", session_usage.get("cost_display", "—")))

    for key, val in pairs:
        ws.cell(row=row, column=1, value=key).font = _KV_KEY_FONT
        ws.cell(row=row, column=2, value=val).font = _KV_VAL_FONT
        row += 1
    return row + 1  # 汇总区与明细区之间的空行


def _write_module_table_header(ws: Any, row: int, headers: list[str]) -> int:
    """写入「各模块明细」区域标题 + 列头，返回下一行号。"""
    from openpyxl.styles import Border, PatternFill, Side
    ncols = len(headers)
    _SECTION_FILL = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")
    _SECTION_FONT = Font(size=10, bold=True, color="1A1A1A")
    _HEADER_FILL = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    _THIN_BORDER = Border(bottom=Side(style="thin", color="d0d0d0"))

    for ci in range(1, ncols + 1):
        ws.cell(row=row, column=ci).fill = _SECTION_FILL
    ws.cell(row=row, column=1, value="▎各模块明细").font = _SECTION_FONT
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    row += 1

    header_font = Font(size=10, bold=True, color="333333")
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col_idx, value=h)
        cell.font = header_font
        cell.alignment = center_align
        cell.fill = _HEADER_FILL
        cell.border = _THIN_BORDER
    return row + 1


def _write_module_data_rows(ws: Any, row: int, module_info: list[dict]) -> int:
    """写入各模块明细行，返回下一行号。"""
    from openpyxl.styles import Border, Side
    _KV_VAL_FONT = Font(size=10)
    _STATUS_COLORS = {
        "disabled": "9ca3af", "failed": "c0392b",
        "cached": "2e86c1", "success": "27ae60",
    }
    _THIN_BORDER = Border(bottom=Side(style="thin", color="d0d0d0"))
    ncols = 10

    for mi in module_info:
        if not mi.get("status_label"):
            continue

        ws.cell(row=row, column=1, value=mi.get("name", "")).font = Font(size=10, bold=True)
        ws.cell(row=row, column=1).alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

        _sc = _STATUS_COLORS.get(mi.get("status", ""), "999999")
        ws.cell(row=row, column=2, value=mi.get("status_label", "")).font = Font(size=10, color=_sc)
        ws.cell(row=row, column=2).alignment = Alignment(horizontal="center", vertical="center")

        ws.cell(row=row, column=3, value=mi.get("model") or "—").font = _KV_VAL_FONT
        ws.cell(row=row, column=3).alignment = Alignment(horizontal="left", vertical="center")

        _token_fields = ["total_tokens", "input_tokens", "output_tokens", "cache_hit_tokens"]
        right_align = Alignment(horizontal="right", vertical="center")
        for ci, tf in enumerate(_token_fields, 4):
            val = mi.get(tf, 0)
            if val:
                ws.cell(row=row, column=ci, value=f"{val:,}").font = _KV_VAL_FONT
            else:
                ws.cell(row=row, column=ci, value="—").font = Font(size=9, color="cccccc")
            ws.cell(row=row, column=ci).alignment = right_align

        # 费用 (column 8)
        _cost = mi.get("cost", 0.0)
        _status_val = mi.get("status", "")
        if _cost > 0:
            from src.python.llm.pricing import _CURRENCY_SYMBOLS, _PRICING_CURRENCY
            _sym = _CURRENCY_SYMBOLS.get(_PRICING_CURRENCY, "¥")
            ws.cell(row=row, column=8, value=f"{_sym}{_cost:.4f}").font = _KV_VAL_FONT
            ws.cell(row=row, column=8).alignment = right_align
        elif _status_val == "cached":
            ws.cell(row=row, column=8, value="已计入原调用").font = Font(size=9, color="999999")
            ws.cell(row=row, column=8).alignment = Alignment(horizontal="center", vertical="center")
        else:
            ws.cell(row=row, column=8, value="—").font = Font(size=9, color="cccccc")
            ws.cell(row=row, column=8).alignment = Alignment(horizontal="center", vertical="center")

        # LLM 缓存 (column 9)
        _cached = mi.get("cached", False)
        if _cached:
            ws.cell(row=row, column=9, value="✓").font = Font(size=10, color="2e86c1")
        else:
            ws.cell(row=row, column=9, value="—").font = Font(size=9, color="cccccc")
        ws.cell(row=row, column=9).alignment = Alignment(horizontal="center", vertical="center")

        # Thinking (column 10)
        _thinking = mi.get("thinking", False)
        if _thinking:
            ws.cell(row=row, column=10, value="✓").font = Font(size=10, color="8e44ad")
        else:
            ws.cell(row=row, column=10, value="—").font = Font(size=9, color="cccccc")
        ws.cell(row=row, column=10).alignment = Alignment(horizontal="center", vertical="center")

        for ci in range(1, ncols + 1):
            ws.cell(row=row, column=ci).border = _THIN_BORDER
        row += 1
    return row


def _write_legend(ws: Any, row: int) -> None:
    """写入底部状态颜色图例。"""
    row += 1
    ws.cell(row=row, column=1, value="状态标色说明：").font = Font(size=9, bold=True, color="999999")
    row += 1
    legends = [
        ("成功  ", "27ae60", "API 调用成功，生成正常"),
        ("缓存  ", "2e86c1", "结果来自 LLM 缓存，未发起 API 请求"),
        ("已禁用  ", "9ca3af", "该模块在配置中未启用"),
        ("已失败  ", "c0392b", "API 调用失败/超时/熔断/未配置"),
    ]
    for lbl, clr, desc in legends:
        ws.cell(row=row, column=1, value=lbl).font = Font(size=9, color=clr)
        ws.cell(row=row, column=2, value=desc).font = Font(size=8, color="999999")
        row += 1


def _set_column_widths(ws: Any, widths: list[int]) -> None:
    """设置列宽并冻结标题行。"""
    from openpyxl.utils import get_column_letter
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A1"


def write_llm_usage_sheet(
    wb: Any,
    llm_session_usage: dict[str, Any] | None,
    llm_module_info: list[dict[str, Any]] | None,
    llm_endpoint: str = "",
) -> None:
    """创建并写入 'LLM API 用量' 页签（放至最右侧）。

    Args:
        wb: 工作簿
        llm_session_usage: format_session_usage() 返回值
        llm_module_info: 合并后的模块明细列表
        llm_endpoint: 全局 LLM endpoint
    """
    if not llm_module_info:
        return

    from openpyxl.styles import Alignment, Border, Side, PatternFill

    _HEADERS = [
        "模块", "状态", "模型",
        "总 Token 用量", "输入 Token", "输出 Token",
        "缓存命中 Token", "费用", "LLM 缓存", "Thinking",
    ]

    ws, row = _init_llm_usage_sheet(wb, "12.LLM API 用量")
    row = _write_llm_summary_section(ws, row, llm_session_usage)

    # 补充 endpoint 到汇总区（如果 llm_session_usage 没有 has_usage，添加在明细上方）
    if llm_endpoint and not (llm_session_usage or {}).get("has_usage"):
        _KV_KEY_FONT = Font(size=10, bold=True, color="2E75B6")
        ws.cell(row=row, column=1, value="Endpoint").font = _KV_KEY_FONT
        ws.cell(row=row, column=2, value=llm_endpoint).font = Font(size=10)
        row += 2

    row = _write_module_table_header(ws, row, _HEADERS)
    row = _write_module_data_rows(ws, row, llm_module_info)
    _write_legend(ws, row)
    _set_column_widths(ws, [20, 16, 26, 16, 14, 14, 18, 16, 12, 12])

    logger.info("LLM API 用量页签写入完成")
