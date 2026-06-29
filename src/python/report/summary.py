"""汇总模块 — 报告第 1 页。

显示当前日期、持仓概况（分类统计+价格更新状态）、盈亏汇总、市场指数。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

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
    """写入汇总页签。

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
    ws.title = "1.投资分析汇总"

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # 计算盈亏数据
    profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0.0
    denominator = total_cost + total_profit - today_profit
    today_rate = (today_profit / denominator * 100) if denominator > 0 else 0.0

    row = write_title_row(ws, 1, "投资分析汇总", _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    # ── 基本信息 ────────────────────────────────────────────
    row = _write_kv_row(ws, row, "统计时间", now.strftime("%Y-%m-%d %H:%M:%S"))
    row = _write_kv_row(ws, row, "所属交易日", get_last_trading_day())
    row = _write_blanks(ws, row)

    # ── 持仓概况 ────────────────────────────────────────────
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

    # 价格更新状态
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

    # ── 盈亏汇总 ────────────────────────────────────────────
    row = _write_section(ws, row, "【盈亏汇总】")
    summary_data = [
        ("总市值 (元)", total_mv),
        ("总成本 (元)", total_cost),
        ("总盈亏 (元)", total_profit),
        ("总收益率", profit_rate),
        ("本日盈亏 (元)", today_profit),
        ("本日收益率", today_rate),
    ]
    for label, val in summary_data:
        # 收益率行在显示时格式化为百分数，着色用原始数值
        display_val = f"{val:+.2f}%" if "收益率" in label else val
        write_data_row(ws, row, [label, display_val])
        # 对盈亏/收益率行着色
        if "盈亏" in label and isinstance(val, (int, float)):
            ws.cell(row=row, column=2).font = profit_font(val)
        elif "收益率" in label and isinstance(val, (int, float)):
            ws.cell(row=row, column=2).font = profit_font(val)
        row += 1

    row = _write_blanks(ws, row)

    # ── 市场指数 ────────────────────────────────────────────
    row = _write_section(ws, row, "【市场指数】")

    # A 股指数 - 本交易日
    if a_indices:
        row = _write_kv_row(ws, row, "── A股指数（本日）──", "")
        a_list = [
            ("sh000001", "上证指数"),
            ("sz399001", "深证成指"),
            ("sh000300", "沪深300"),
            ("sh000688", "科创板50"),
            ("sz399006", "创业板指"),
        ]
        for code, cname in a_list:
            idx = a_indices.get(code)
            if idx and idx.get("price", 0) > 0:
                price = idx["price"]
                change = idx.get("change_pct", 0)
                row = _write_index_row(ws, row, cname, price, change)
            else:
                row = _write_kv_row(ws, row, f"  {cname}", "--")

        # A 股指数 - 上一交易日
        row = _write_blanks(ws, row, 0)
        row = _write_kv_row(ws, row, "── A股指数（上日）──", "")
        for code, cname in a_list:
            idx = a_indices.get(code)
            if idx and idx.get("yesterday_close", 0) > 0:
                yclose = idx["yesterday_close"]
                row = _write_kv_row(ws, row, f"  {cname}", f"{yclose:.2f}")
            else:
                row = _write_kv_row(ws, row, f"  {cname}", "--")
    else:
        row = _write_kv_row(ws, row, "── A股指数 ──", "暂无数据")

    row = _write_blanks(ws, row)

    # 美股指数
    if us_indices:
        row = _write_kv_row(ws, row, "── 美股指数（最新）──", "")
        us_list = [
            ("gb_dji", "道琼斯"),
            ("gb_ixic", "纳斯达克"),
            ("gb_inx", "标普500"),
        ]
        for code, cname in us_list:
            idx = us_indices.get(code)
            if idx and idx.get("price", 0) > 0:
                price = idx["price"]
                change = idx.get("change_pct", 0)
                row = _write_index_row(ws, row, cname, price, change)
            else:
                row = _write_kv_row(ws, row, f"  {cname}", "--")

        # 美股指数 - 上一交易日
        row = _write_blanks(ws, row, 0)
        row = _write_kv_row(ws, row, "── 美股指数（上日）──", "")
        for code, cname in us_list:
            idx = us_indices.get(code)
            if idx and idx.get("yesterday_close", 0) > 0:
                yclose = idx["yesterday_close"]
                row = _write_kv_row(ws, row, f"  {cname}", f"{yclose:.2f}")
            else:
                row = _write_kv_row(ws, row, f"  {cname}", "--")
    else:
        row = _write_kv_row(ws, row, "── 美股指数 ──", "暂无数据")

    # ── LLM 用量（由 write_llm_usage_block 在 LLM 生成后追加） ─

    freeze_header(ws, 2)
    auto_width(ws)
    logger.info("汇总页签写入完成，共 %d 行", row)


def write_llm_usage_block(ws: Worksheet,
                           llm_session_usage: dict[str, Any] | None) -> None:
    """在汇总页追加写入 LLM 用量区块（应在 LLM 生成完成后调用）。

    Args:
        ws: 汇总页工作表
        llm_session_usage: get_session_usage() 返回值
    """
    from src.python.llm_client import format_session_usage
    u = format_session_usage(llm_session_usage)
    if not u.get("has_usage"):
        return
    row = ws.max_row + 1
    row = _write_blanks(ws, row)
    row = _write_section(ws, row, "【LLM 用量】")
    row = _write_kv_row(ws, row, "  API 调用次数", f"{u['call_count']} 次")
    row = _write_kv_row(ws, row, "  模型", u["model"])
    row = _write_kv_row(ws, row, "  输入 token", f"{u['input_tokens']:,}")
    row = _write_kv_row(ws, row, "  输出 token", f"{u['output_tokens']:,}")
    row = _write_kv_row(ws, row, "  总 token", f"{u['total_tokens']:,}")
    if u["cache_hit_tokens"]:
        row = _write_kv_row(ws, row, "  缓存命中", f"{u['cache_hit_tokens']:,}")
    row = _write_kv_row(ws, row, "  累计费用", u["cost_display"])
