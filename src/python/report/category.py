"""持仓分类模块 — 报告第 3 页。

按资产属性（股票/基金/债券/现金）和投资分类（主动/被动/固收等）分组，
统计各类的数量、市值、成本、盈亏、收益率和本日盈亏。
"""

from __future__ import annotations

import logging


from openpyxl.worksheet.worksheet import Worksheet

from src.python.registry import get_report_sheet_name, set_sheet_title
from src.python.models import Holding
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_subtotal_row,
    write_title_row,
    write_total_row,
)
from src.python.report.classification_utils import INDEX_KEYWORDS, is_bond_fund, is_etf, is_offsite_fund, is_qdii, is_stock_code
from src.python.report.market_value import DetailRow
from src.python.report.styles import FMT_MONEY, FMT_PERCENT, profit_font

logger = logging.getLogger("invest")

_NCOLS = 10
_HEADERS = [
    "资产属性", "投资分类", "名称", "代码",
    "市值", "成本", "盈亏", "收益率", "本日盈亏", "年均股息率",
]

# ── 分类映射规则 ──────────────────────────────────────────

# 货币类关键词（category 模块特有，无需集中管理）
_MONEY_KEYWORDS = ("货币", "现金", "增利", "宝")


def _categorize_holding(h: Holding) -> tuple[str, str]:
    """将单条持仓映射到 (资产属性, 投资分类)。

    分类逻辑（按优先级）：
      1. QDII（名称含 QDII）→ 基金 / QDII
      2. 名称含固收关键词 → 债券 / 纯债
      3. 名称含货币关键词 → 现金 / 货币
      4. 场外渠道且名称含指数关键词 → 基金 / 被动
      5. 场外渠道 → 基金 / 主动
      6. 场内ETF（名称含ETF或代码5/1开头）→ 基金 / 指数
      7. 场内股票（代码6/0/3开头）→ 股票 / A股
      8. 其余 → 基金 / 混合

    Args:
        h: 持仓记录

    Returns:
        (资产属性, 投资分类)
    """
    name = h.name.strip()
    code = h.code.strip()
    account = h.account.strip()

    # 1) QDII
    if is_qdii(name):
        return ("基金", "QDII")

    # 2) 固收类
    if is_bond_fund(name):
        return ("债券", "纯债")

    # 3) 货币类
    if any(kw in name for kw in _MONEY_KEYWORDS):
        return ("现金", "货币")

    # 4) 场外渠道
    is_offsite = is_offsite_fund(account)
    if is_offsite:
        if any(kw in name for kw in INDEX_KEYWORDS):
            return ("基金", "被动")
        return ("基金", "主动")

    # 5) 场内 ETF（名称含ETF或代码5/1开头）
    if is_etf(name, code):
        return ("基金", "指数")

    # 6) 场内股票（代码6/0/3开头）
    if is_stock_code(code):
        return ("股票", "A股")

    # 7) 其余归为基金/混合
    return ("基金", "混合")


def _load_dividend_data(holdings: List[Holding]) -> dict:
    """加载分红数据（非关键，失败时返回空字典）。"""
    try:
        from src.python.providers.akshare_extras import get_dividend_data
        stock_codes = [h.code for h in holdings if h.code.strip().startswith(("6", "0", "3"))]
        return get_dividend_data(stock_codes) if stock_codes else {}
    except Exception:
        logger.debug("分红数据加载失败（非关键），年均股息率列显示 --", exc_info=True)
        return {}


def _yield_text(code: str, d, dividend_data: dict) -> str:
    """计算单条持仓的年均股息率文本。"""
    info = dividend_data.get(code)
    if not info:
        return "--"
    avg_div = info.get("avg_dividend")
    if avg_div is None:
        return "--"
    price = d.price if d and d.price > 0 else 0.0
    if price <= 0:
        return "--"
    return f"{avg_div / price * 100:.2f}%"


def _write_category_group(
    ws: Worksheet, row: int, group: List[Holding], prop: str, sub: str,
    detail_map: dict, dividend_data: dict,
) -> tuple[int, float, float, float, float]:
    """写入一个分类分组的明细行和小计，返回 (next_row, mv, cost, profit, today)。"""
    for h in group:
        d = detail_map.get(h.code)
        if d:
            vals = [prop, sub, h.name, h.code,
                    d.market_value, d.cost, d.profit, d.profit_rate,
                    d.today_profit, _yield_text(h.code, d, dividend_data)]
        else:
            vals = [prop, sub, h.name, h.code, 0.0, 0.0, 0.0, 0.0, 0.0, "--"]
        write_data_row(ws, row, vals, _num_formats())
        row += 1

    sub_mv = sum(detail_map.get(h.code, DetailRow()).market_value for h in group if h.code in detail_map)
    sub_cost = sum(detail_map.get(h.code, DetailRow()).cost for h in group if h.code in detail_map)
    sub_profit = sum(detail_map.get(h.code, DetailRow()).profit for h in group if h.code in detail_map)
    sub_today = sum(detail_map.get(h.code, DetailRow()).today_profit for h in group if h.code in detail_map)
    sub_rate = sub_profit / sub_cost if sub_cost > 0 else 0.0

    subtotal_vals = ["", "", len(group), sub_mv, sub_cost, sub_profit, sub_rate, sub_today, "--"]
    write_subtotal_row(ws, row, f"{prop} - {sub} 小计", subtotal_vals, _NCOLS, _num_formats())
    return row + 1, sub_mv, sub_cost, sub_profit, sub_today


def write_category_sheet(
    ws: Worksheet,
    holdings: list[Holding],
    details: List[DetailRow],
) -> None:
    """写入持仓分类表。

    分类层级：
      资产属性 → 投资分类 → 持仓明细 → 小计 → 总计
    每行含市值、成本、盈亏、收益率、本日盈亏、年均股息率。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
    """
    detail_map: dict[str, DetailRow] = {d.code: d for d in details}

    cat_groups: dict[Tuple[str, str], List[Holding]] = {}
    for h in holdings:
        prop, sub = _categorize_holding(h)
        cat_groups.setdefault((prop, sub), []).append(h)

    _PROP_ORDER = {"股票": 0, "基金": 1, "债券": 2, "现金": 3, "其他": 4}
    _SUB_ORDER = {"A股": 0, "QDII": 1, "主动": 2, "被动": 3, "指数": 4,
                  "混合": 5, "纯债": 6, "货币": 7, "其他": 8}
    sorted_groups = sorted(
        cat_groups.items(),
        key=lambda x: (_PROP_ORDER.get(x[0][0], 99), _SUB_ORDER.get(x[0][1], 99)),
    )

    row = write_title_row(ws, 1, get_report_sheet_name('category'), _NCOLS)
    row = write_header_row(ws, row, _HEADERS)
    data_start = row

    dividend_data = _load_dividend_data(holdings)
    grand_mv = grand_cost = grand_profit = grand_today = 0.0

    for (prop, sub), group in sorted_groups:
        row, smv, scost, sprofit, stoday = _write_category_group(
            ws, row, group, prop, sub, detail_map, dividend_data,
        )
        grand_mv += smv
        grand_cost += scost
        grand_profit += sprofit
        grand_today += stoday

    grand_rate = grand_profit / grand_cost if grand_cost > 0 else 0.0
    total_vals = ["", "", "-", grand_mv, grand_cost, grand_profit, grand_rate, grand_today, "--"]
    write_total_row(ws, row, "总计", total_vals, _NCOLS, _num_formats())

    _apply_profit_colors(ws, data_start, row)
    freeze_header(ws, 2)
    auto_width(ws)
    logger.info("%s写入完成，共 %d 个分组，%d 条持仓",
                get_report_sheet_name('category'), len(sorted_groups), len(holdings))


def _num_formats() -> list[str]:
    """每列的 Excel 数字格式。"""
    return [
        "",           # 1  资产属性
        "",           # 2  投资分类
        "",           # 3  名称
        "",           # 4  代码
        FMT_MONEY,    # 5  市值
        FMT_MONEY,    # 6  成本
        FMT_MONEY,    # 7  盈亏
        FMT_PERCENT,  # 8  收益率
        FMT_MONEY,    # 9  本日盈亏
        "",           # 10 年均股息率（字符串格式）
    ]


def _apply_profit_colors(ws, start_row: int, end_row: int) -> None:
    """对盈亏列 (7)、收益率列 (8)、本日盈亏列 (9) 着色。"""
    for r in range(start_row, end_row + 1):
        # 盈亏列 (7) 和本日盈亏列 (9)：数值型
        for col in (7, 9):
            cell = ws.cell(row=r, column=col)
            if isinstance(cell.value, (int, float)):
                cell.font = profit_font(cell.value)
        # 收益率列 (8)：可能是百分比数值
        rate_cell = ws.cell(row=r, column=8)
        if isinstance(rate_cell.value, (int, float)):
            rate_cell.font = profit_font(rate_cell.value)
