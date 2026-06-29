"""分类汇总模块 — 报告第 3 页。

按资产属性（股票/基金/债券/现金）和投资分类（主动/被动/固收等）分组，
统计各类的数量、市值、成本、盈亏、收益率和本日盈亏。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from openpyxl.worksheet.worksheet import Worksheet

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
from src.python.report.market_value import DetailRow
from src.python.report.styles import FMT_MONEY, FMT_PERCENT, profit_font

logger = logging.getLogger("invest")

_NCOLS = 10
_HEADERS = [
    "资产属性", "投资分类", "名称", "代码",
    "市值", "成本", "盈亏", "收益率", "本日盈亏", "年均股息率",
]

# ── 分类映射规则 ──────────────────────────────────────────

# 场外基金渠道关键词
_FUND_ACCOUNT_KEYWORDS = ("基金", "支付宝", "微信", "银行")

# 固收类关键词（名称中包含）
_BOND_KEYWORDS = ("债", "纯债", "短债", "中短债", "信用")

# 货币类关键词
_MONEY_KEYWORDS = ("货币", "现金", "增利", "宝")

# 指数类关键词
_INDEX_KEYWORDS = ("指数", "ETF联接", "ETF 联接", "中证", "沪深300",
                   "中证500", "中证1000", "科创50", "创业板", "上证")


def _categorize_holding(h: Holding) -> Tuple[str, str]:
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
    name_upper = name.upper()

    # 1) QDII
    if "QDII" in name_upper:
        return ("基金", "QDII")

    # 2) 固收类
    if any(kw in name for kw in _BOND_KEYWORDS):
        return ("债券", "纯债")

    # 3) 货币类
    if any(kw in name for kw in _MONEY_KEYWORDS):
        return ("现金", "货币")

    # 4) 场外渠道
    is_offsite = any(kw in account for kw in _FUND_ACCOUNT_KEYWORDS)
    if is_offsite:
        if any(kw in name for kw in _INDEX_KEYWORDS):
            return ("基金", "被动")
        return ("基金", "主动")

    # 5) 场内 ETF（名称含ETF或代码5/1开头）
    if "ETF" in name_upper or code.startswith(("5", "1")):
        return ("基金", "指数")

    # 6) 场内股票（代码6/0/3开头）
    if code.startswith(("6", "0", "3")):
        return ("股票", "A股")

    # 7) 其余归为基金/混合
    return ("基金", "混合")


def write_category_sheet(
    ws: Worksheet,
    holdings: List[Holding],
    details: List[DetailRow],
) -> None:
    """写入分类汇总页签。

    分类层级：
      资产属性 → 投资分类 → 持仓明细 → 小计 → 总计
    每行含市值、成本、盈亏、收益率、本日盈亏、年均股息率。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
    """
    ws.title = "3. 分类汇总"

    # 建立 code → detail 映射
    detail_map: dict[str, DetailRow] = {}
    for d in details:
        detail_map[d.code] = d

    # 分类并聚合
    cat_groups: dict[Tuple[str, str], List[Holding]] = {}
    for h in holdings:
        prop, sub = _categorize_holding(h)
        cat_groups.setdefault((prop, sub), []).append(h)

    # 排序：先按资产属性（股票→基金→债券→现金），再按投资分类
    _PROP_ORDER = {"股票": 0, "基金": 1, "债券": 2, "现金": 3, "其他": 4}
    _SUB_ORDER = {"A股": 0, "QDII": 1, "主动": 2, "被动": 3, "指数": 4,
                  "混合": 5, "纯债": 6, "货币": 7, "其他": 8}
    sorted_groups = sorted(
        cat_groups.items(),
        key=lambda x: (_PROP_ORDER.get(x[0][0], 99), _SUB_ORDER.get(x[0][1], 99)),
    )

    # 写入标题和表头
    row = write_title_row(ws, 1, "分类汇总表", _NCOLS)
    row = write_header_row(ws, row, _HEADERS)
    data_start = row

    # 遍历分组，写入明细+小计
    grand_mv = grand_cost = grand_profit = grand_today = 0.0

    # ── 加载分红数据（用于年均股息率） ──
    try:
        from src.python.providers.akshare_extras import get_dividend_data
        stock_codes = [h.code for h in holdings if h.code.strip().startswith(("6", "0", "3"))]
        dividend_data = get_dividend_data(stock_codes) if stock_codes else {}
    except Exception:
        logger.debug("分红数据加载失败（非关键），年均股息率列显示 --")
        dividend_data = {}

    def _yield_text(code: str, d) -> str:
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

    for (prop, sub), group in sorted_groups:
        # 分组明细行
        for h in group:
            d = detail_map.get(h.code)
            if d:
                vals = [
                    prop, sub, h.name, h.code,
                    d.market_value, d.cost, d.profit, d.profit_rate,
                    d.today_profit, _yield_text(h.code, d),
                ]
            else:
                vals = [prop, sub, h.name, h.code, 0.0, 0.0, 0.0, 0.0, 0.0, "--"]
            write_data_row(ws, row, vals, _num_formats())
            row += 1

        # 小计
        sub_mv = sum(detail_map.get(h.code, DetailRow()).market_value
                     for h in group if h.code in detail_map)
        sub_cost = sum(detail_map.get(h.code, DetailRow()).cost
                       for h in group if h.code in detail_map)
        sub_profit = sum(detail_map.get(h.code, DetailRow()).profit
                         for h in group if h.code in detail_map)
        sub_today = sum(detail_map.get(h.code, DetailRow()).today_profit
                        for h in group if h.code in detail_map)
        sub_rate = sub_profit / sub_cost if sub_cost > 0 else 0.0

        subtotal_vals = [
            f"{prop} - {sub} 小计",
            "", "",
            len(group), sub_mv, sub_cost, sub_profit, sub_rate, sub_today, "--",
        ]
        write_subtotal_row(ws, row, f"{prop} - {sub} 小计",
                           subtotal_vals[1:], _NCOLS, _num_formats())
        row += 1

        grand_mv += sub_mv
        grand_cost += sub_cost
        grand_profit += sub_profit
        grand_today += sub_today

    # 总计行
    grand_rate = grand_profit / grand_cost if grand_cost > 0 else 0.0
    total_vals = [
        "总计", "", "",
        "-", grand_mv, grand_cost, grand_profit, grand_rate, grand_today, "--",
    ]
    write_total_row(ws, row, "总计", total_vals[1:], _NCOLS, _num_formats())

    # 对盈亏列着色
    _apply_profit_colors(ws, data_start, row)

    freeze_header(ws, 2)
    auto_width(ws)

    logger.info("分类汇总页签写入完成，共 %d 个分组，%d 条持仓",
                len(sorted_groups), len(holdings))


def _num_formats() -> List[str]:
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
