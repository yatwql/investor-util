"""基金业绩分析模块 — 报告第 5 页。

调天天基金 API 获取每只基金在同类中的排名和区间收益率，
按排名百分位打标签（优秀/良好/稳定/偏差），生成结构化 Sheet。

输出列：
  基金 | 代码 | 类型 | 近3月 | 近6月 | 近12月 | 持仓累计盈亏(¥) | 持仓收益率 | 业绩基准 | 业绩评价 | 同类排名
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from openpyxl.worksheet.worksheet import Worksheet

from src.fetcher import fetch_fund_benchmark, fetch_fund_rankings
from src.models import Holding
from src.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.report.market_value import DetailRow
from src.report.penetration import classify_penetration, QDII, ETF, INDEX_LINK, BOND_FUND, ACTIVE_EQUITY
from src.report.styles import BLUE_FONT, GREEN_FONT, RED_FONT

logger = logging.getLogger("invest")

_NCOLS = 11
_HEADERS = [
    "基金", "代码", "类型", "近3月", "近6月", "近12月",
    "持仓累计盈亏(¥)", "持仓收益率", "业绩基准", "业绩评价", "同类排名",
]

# 业绩评价 -> 标签 + 描述
_RATING_COMMENT: Dict[str, str] = {
    "优秀": "优秀 持续跑赢基准，超额收益显著",
    "良好": "良好 稳定跑赢基准，组合管理得当",
    "稳定": "稳定 收益率稳健，波动控制良好",
    "偏差": "偏差 近期表现欠佳，需关注持仓变化",
}


# 穿透分类 → 基金类型显示标签
_FUND_TYPE_LABEL = {
    QDII: "场外QDII基金",
    ETF: "场内ETF",
    INDEX_LINK: "场外指数基金",
    BOND_FUND: "场外债券基金",
    ACTIVE_EQUITY: "场外主动型基金",
}


def _fund_display_type(h: Holding) -> str:
    """用穿透分类逻辑判定基金类型，返回中文显示标签。"""
    ftype = classify_penetration(h)
    return _FUND_TYPE_LABEL.get(ftype, "--")


def _is_fund(h: Holding) -> bool:
    """判断持仓是否为基金（需要业绩分析）。"""
    name = h.name.strip().upper()
    code = h.code.strip()

    # 纯股票直接排除
    if code.startswith(("6", "0", "3")) and "ETF" not in name:
        # 双重确认：A股渠道
        account = h.account.strip()
        fund_keywords = ("基金", "支付宝", "微信", "银行")
        if not any(kw in account for kw in fund_keywords):
            return False

    return True


def _format_return(val: Any) -> str:
    """格式化收益率为带正负号的百分比字符串。"""
    if val is None or val == "--":
        return "--"
    try:
        v = float(val)
        return f"{v:+.2f}%"
    except (ValueError, TypeError):
        return "--"


def _format_rank(entry: dict) -> str:
    """格式化排名为 '排名/总数' 格式。"""
    rank = entry.get("rank", "--")
    total = entry.get("total", "--")
    if rank == "--" or total == "--":
        return "--"
    return f"{rank}/{total}"


def write_fund_performance_sheet(
    ws: Worksheet,
    holdings: List[Holding],
    details: List[DetailRow],
) -> None:
    """写入基金业绩分析页签。

    对每只基金调 API 获取区间收益和同类排名，汇总为 11 列表格。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
    """
    ws.title = "基金业绩分析"

    row = write_title_row(ws, 1, "基金业绩分析", _NCOLS)
    row = write_header_row(ws, row, _HEADERS)
    data_start = row

    # 识别基金
    fund_holdings = [h for h in holdings if _is_fund(h)]
    detail_map = {d.code: d for d in details}

    if not fund_holdings:
        write_data_row(ws, row, ["未检测到基金持仓"])
        logger.info("基金业绩分析：无基金持仓")
        freeze_header(ws, 2)
        auto_width(ws)
        return

    # 按市值降序排列（市值大的基金排在前面）
    def _fund_sort_key(h: Holding) -> float:
        d = detail_map.get(h.code)
        return d.market_value if d else 0.0

    fund_holdings_sorted = sorted(fund_holdings, key=_fund_sort_key, reverse=True)

    # 遍历每只基金获取业绩数据
    fund_count = len(fund_holdings_sorted)
    success_count = 0
    perf_results: dict[str, dict] = {}

    for idx, fund in enumerate(fund_holdings_sorted, 1):
        logger.info("获取基金业绩 [%d/%d]: %s (%s)", idx, fund_count, fund.name, fund.code)
        print(f"  [..] 基金业绩 [{idx}/{fund_count}]: {fund.name}")

        perf_data = fetch_fund_rankings(fund.code)

        if perf_data is None or not perf_data.get("rankings"):
            # 获取失败，写入兜底数据
            _write_empty_row(ws, row, fund)
            row += 1
            logger.warning("基金 %s (%s) 业绩数据获取失败", fund.name, fund.code)
            continue

        rankings = perf_data.get("rankings", {})
        rating = perf_data.get("rating", "")
        fund_type = _fund_display_type(fund)
        benchmark = fetch_fund_benchmark(fund.code)

        # 从估值明细中获取持仓盈亏数据
        d = detail_map.get(fund.code)
        profit_val = d.profit if d else 0.0
        profit_rate_val = d.profit_rate if d else 0.0

        # 写入该基金的行
        vals = [
            fund.name,
            fund.code,
            fund_type,
            _format_return(rankings.get("近3月", {}).get("return")),
            _format_return(rankings.get("近6月", {}).get("return")),
            _format_return(rankings.get("近1年", {}).get("return")),  # 近1年 → 近12月
            f"{profit_val:+,.2f}",                                   # 累计盈亏(¥)
            f"{profit_rate_val * 100:+.2f}%",                        # 收益率
            benchmark,                                               # 业绩比较基准
            _RATING_COMMENT.get(rating, "--"),                      # 业绩评价
            _format_rank(rankings.get("同类排名", {})),              # 同类排名
        ]
        write_data_row(ws, row, vals, _num_formats())

        # 业绩评价标色：优秀→红，偏差→绿，稳定→蓝
        _rating_font = ""
        if rating == "优秀":
            _rating_font = RED_FONT
        elif rating == "偏差":
            _rating_font = GREEN_FONT
        elif rating == "稳定":
            _rating_font = BLUE_FONT
        if _rating_font:
            ws.cell(row=row, column=10).font = _rating_font

        row += 1
        success_count += 1
        perf_results[fund.code] = perf_data

    # 底部统计
    row += 1
    write_data_row(ws, row, [
        f"共 {fund_count} 只基金，{success_count} 只获取到业绩数据",
    ])
    row += 1

    # 评级分布
    rating_counts: Dict[str, int] = {}
    for fund_code, perf_data in perf_results.items():
        if perf_data:
            rating = perf_data.get("rating", "")
            if rating:
                rating_counts[rating] = rating_counts.get(rating, 0) + 1

    if rating_counts:
        rating_summary = " | ".join(
            f"{k}: {v}只" for k, v in sorted(rating_counts.items(),
                                              key=lambda x: list(_RATING_COMMENT.keys()).index(x[0])
                                              if x[0] in _RATING_COMMENT else 99)
        )
        write_data_row(ws, row, [f"评级分布: {rating_summary}"])

    freeze_header(ws, 2)
    auto_width(ws, min_width=10, max_width=30)

    logger.info("基金业绩分析页签写入完成，%d/%d 只基金获取成功",
                success_count, fund_count)


def _write_empty_row(ws, row: int, fund: Holding) -> None:
    """写入获取失败的基金占位行。"""
    vals = [
        fund.name,
        fund.code,
        _fund_display_type(fund),
        "--", "--", "--",
        "--", "--",
        "--",
        "--",
        "--",
    ]
    write_data_row(ws, row, vals, _num_formats())


def _num_formats() -> List[str]:
    """每列的 Excel 数字格式。"""
    return [
        "",           # 1  基金
        "",           # 2  代码
        "",           # 3  类型
        "",           # 4  近3月（字符串 %）
        "",           # 5  近6月
        "",           # 6  近12月
        "",           # 7  持仓累计盈亏(¥)（字符串 ¥）
        "",           # 8  持仓收益率（字符串 %）
        "",           # 9  业绩基准
        "",           # 10 业绩评价
        "",           # 11 同类排名
    ]
