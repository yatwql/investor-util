"""基金业绩分析模块 — 报告第 5 页。

调天天基金 API 获取每只基金在同类中的排名和区间收益率，
按排名百分位打标签（优秀/良好/稳定/偏差/较差），生成结构化 Sheet。

评级逻辑（P2：5 级评级 + 类型差异化阈值）：
  1. 同类排名百分位 → 基础评级（默认 10%/30%/50%/75% 四道阈值）
  2. 类型差异化：债券型/QDII 使用宽松阈值(15%/35%/55%/80%)，指数型使用严格阈值(10%/25%/45%/70%)
  3. 超额收益评分（Data_performanceEvaluation）→ 调整评级
  4. 最终评级 = 基础评级 + 基准比较修正

输出列：
  基金 | 代码 | 类型 | 近3月 | 近6月 | 近12月 | 持仓累计盈亏(¥) | 持仓收益率 | 业绩基准 | 业绩评价 | 同类排名
"""

from __future__ import annotations

import logging
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet

from src.python.fetcher.fund import fetch_fund_benchmark, fetch_fund_rankings
from src.python.models import Holding
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.market_value import DetailRow
from src.python.registry import get_report_sheet_name, set_sheet_title
from src.python.report.penetration import classify_penetration, QDII, ETF, INDEX_LINK, BOND_FUND, ACTIVE_EQUITY
from src.python.report.styles import BLUE_FONT, DARK_GREEN_FONT, GREEN_FONT, RED_FONT

logger = logging.getLogger("invest")

_NCOLS = 12
_HEADERS = [
    "基金", "代码", "类型", "近3月", "近6月", "近12月",
    "持仓累计盈亏(¥)", "持仓收益率", "业绩基准", "业绩评价", "同类排名", "机构覆盖",
]

# 基础业绩评价 -> 标签 + 描述（P2：5 级评级，新增"较差"）
_RATING_COMMENT: dict[str, str] = {
    "优秀": "优秀 持续跑赢基准，超额收益显著",
    "良好": "良好 稳定跑赢基准，组合管理得当",
    "稳定": "稳定 收益率稳健，波动控制良好",
    "偏差": "偏差 近期表现欠佳，需关注持仓变化",
    "较差": "较差 同类排名靠后，建议评估持续持有理由",
}


# 穿透分类 → 基金类型显示标签
_FUND_TYPE_LABEL = {
    QDII: "场外QDII基金",
    ETF: "场内ETF",
    INDEX_LINK: "场外指数基金",
    BOND_FUND: "场外债券基金",
    ACTIVE_EQUITY: "场外主动型基金",
}

# 评级权重（最差→最好）
_RATING_ORDER = ["较差", "偏差", "稳定", "良好", "优秀"]

# 超额收益评分阈值（用于评级修正）
_EXCESS_THRESHOLD_UP = 80    # 超额收益 ≥ 80 → 评级上调一级
_EXCESS_THRESHOLD_DOWN = 40  # 超额收益 < 40 → 评级下调一级


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


def _format_return(val: Any) -> float | str:
    """格式化收益率为小数（供 Excel 百分比格式使用）。

    Returns:
        小数（如 0.0523 表示 5.23%），或 "--" 表示无数据
    """
    if val is None or val == "--":
        return "--"
    try:
        return float(val) / 100  # 转为小数供 Excel 0.00% 格式使用
    except (ValueError, TypeError):
        return "--"


def _format_rank(entry: dict) -> str:
    """格式化排名为 '排名/总数' 格式。"""
    rank = entry.get("rank", "--")
    total = entry.get("total", "--")
    if rank is None or rank == "--" or total is None or total == "--":
        return "--"
    return f"{rank}/{total}"


def _calc_rating_comment(rating: str, perf_eval: dict | None, benchmark: str) -> str:
    """根据评级 + 超额收益数据 + 业绩基准，生成带具体描述的业绩评价文本。

    Args:
        rating: 最终评级（优秀/良好/稳定/偏差/较差）
        perf_eval: Data_performanceEvaluation 的 JSON 对象，含 categories/data
        benchmark: 业绩比较基准名称

    Returns:
        完整业绩评价字符串
    """
    base = _RATING_COMMENT.get(rating, "--")

    # 如果有超额收益评分，追加说明
    if perf_eval:
        categories = perf_eval.get("categories") or []
        scores = perf_eval.get("data") or []
        # 找到"超额收益"对应的分值
        excess_idx = next((i for i, c in enumerate(categories) if c and ("超额" in c or "超额收益" in c)), -1)
        if excess_idx >= 0 and excess_idx < len(scores):
            excess_score = scores[excess_idx]
            if isinstance(excess_score, (int, float)):
                base += f"（超额收益评分{excess_score:.0f}）"
                return base

    # 没有超额收益评分但有基准名，附加基准信息
    if benchmark and benchmark != "--":
        base += f"（基准：{benchmark}）"

    return base


def _adjust_rating_with_benchmark(peer_rating: str, perf_eval: dict | None = None) -> str:
    """用基准比较数据修正纯同类排名评级。

    修正规则：
      - 超额收益评分 ≥ 80  → 评级上调一级（如 良好→优秀）
      - 超额收益评分 < 40  → 评级下调一级（如 稳定→偏差）
      - 无超额收益数据或评分居中 → 保持原评级

    Args:
        peer_rating: 纯同类排名评级（优秀/良好/稳定/偏差/较差）
        perf_eval: Data_performanceEvaluation 对象，含"超额收益"评分

    Returns:
        修正后的最终评级
    """
    if not perf_eval or peer_rating not in _RATING_ORDER:
        return peer_rating

    categories = perf_eval.get("categories") or []
    scores = perf_eval.get("data") or []

    # 找到"超额收益"在 categories 中的索引
    excess_idx = -1
    for i, cat in enumerate(categories):
        if cat and ("超额" in cat or "超额收益" in cat):
            excess_idx = i
            break

    if excess_idx < 0 or excess_idx >= len(scores):
        return peer_rating

    excess_score = scores[excess_idx]
    if not isinstance(excess_score, (int, float)):
        return peer_rating

    current_idx = _RATING_ORDER.index(peer_rating)

    if excess_score >= _EXCESS_THRESHOLD_UP:
        # 超额收益显著 → 上调
        new_idx = min(current_idx + 1, len(_RATING_ORDER) - 1)
    elif excess_score < _EXCESS_THRESHOLD_DOWN:
        # 超额收益较差 → 下调
        new_idx = max(current_idx - 1, 0)
    else:
        # 中间区间 → 不调整
        return peer_rating

    adjusted = _RATING_ORDER[new_idx]
    if adjusted != peer_rating:
        logger.debug("评级调整: %s → %s（超额收益评分 %.0f）",
                     peer_rating, adjusted, excess_score)
    return adjusted


def _load_profit_forecast() -> dict[str, Any]:
    """加载盈利预测数据（非关键，失败时返回空字典）。

    Returns:
        盈利预测字典 {code: {reports, eps_2025e}} 或空字典
    """
    try:
        from src.python.providers.akshare_extras import get_profit_forecast
        return get_profit_forecast()
    except Exception:
        logger.debug("盈利预测加载失败（非关键），机构覆盖列显示 --", exc_info=True)
        return {}


def _coverage_text(code: str, profit_forecast: dict[str, Any]) -> str:
    """根据基金代码查找机构覆盖信息。

    Args:
        code: 基金代码
        profit_forecast: 盈利预测字典

    Returns:
        机构覆盖文本（如"5家研报 EPS¥1.23"）或 "--"
    """
    info = profit_forecast.get(code)
    if info:
        reports = info.get("reports", 0)
        eps = info.get("eps_2025e")
        if reports and eps is not None:
            return f"{reports}家研报 EPS¥{eps:.2f}"
        elif reports:
            return f"{reports}家研报"
        elif eps is not None:
            return f"EPS¥{eps:.2f}"
    return "--"


def _write_one_fund_row(
    ws: Worksheet, row: int, fund: Holding,
    detail_map: dict[str, DetailRow],
    profit_forecast: dict[str, Any],
) -> str | None:
    """获取并写入单只基金的业绩数据行。

    Args:
        ws: 工作表
        row: 当前行号
        fund: 基金持仓
        detail_map: 估值明细映射 {code: DetailRow}
        profit_forecast: 盈利预测字典

    Returns:
        最终评级（优秀/良好/稳定/偏差/较差），获取失败返回 None
    """
    perf_data = fetch_fund_rankings(fund.code)

    if perf_data is None or not perf_data.get("rankings"):
        _write_empty_row(ws, row, fund)
        logger.warning("基金 %s (%s) 业绩数据获取失败", fund.name, fund.code)
        return None

    rankings = perf_data.get("rankings", {})
    peer_rating = perf_data.get("rating", "")
    perf_eval = perf_data.get("perf_evaluation")
    fund_type = _fund_display_type(fund)
    benchmark = fetch_fund_benchmark(fund.code)

    final_rating = _adjust_rating_with_benchmark(peer_rating, perf_eval)
    comment = _calc_rating_comment(final_rating, perf_eval, benchmark)

    d = detail_map.get(fund.code)
    profit_val = d.profit if d else 0.0
    profit_rate_val = d.profit_rate if d else 0.0

    vals = [
        fund.name, fund.code, fund_type,
        _format_return(rankings.get("近3月", {}).get("return")),
        _format_return(rankings.get("近6月", {}).get("return")),
        _format_return(rankings.get("近1年", {}).get("return")),
        profit_val,
        profit_rate_val,  # 已为小数（如 0.0523），Excel 0.00% 格式自动处理
        benchmark, comment,
        _format_rank(rankings.get("同类排名", {})),
        _coverage_text(fund.code, profit_forecast),
    ]
    write_data_row(ws, row, vals, _num_formats())

    # 业绩评价标色：优秀→红，较差→深绿，偏差→绿，稳定→蓝
    _rating_font = ""
    if final_rating == "优秀":
        _rating_font = RED_FONT
    elif final_rating == "较差":
        _rating_font = DARK_GREEN_FONT
    elif final_rating == "偏差":
        _rating_font = GREEN_FONT
    elif final_rating == "稳定":
        _rating_font = BLUE_FONT
    if _rating_font:
        ws.cell(row=row, column=10).font = _rating_font

    return final_rating


def _write_rating_distribution(ws: Worksheet, row: int, fund_count: int, adjusted_ratings: dict[str, str]) -> int:
    """写入评级分布统计和业绩评价标准说明。

    Args:
        ws: 工作表
        row: 当前行号
        fund_count: 基金总数
        adjusted_ratings: {基金代码: 最终评级} 字典（仅成功获取业绩的基金）

    Returns:
        写入后的下一个行号
    """
    success_count = len(adjusted_ratings)
    row += 1
    write_data_row(ws, row, [f"共 {fund_count} 只基金，{success_count} 只获取到业绩数据"])
    row += 1

    rating_counts: dict[str, int] = {}
    for adj_rating in adjusted_ratings.values():
        if adj_rating:
            rating_counts[adj_rating] = rating_counts.get(adj_rating, 0) + 1

    if rating_counts:
        summary = " | ".join(
            f"{k}: {v}只" for k, v in sorted(
                rating_counts.items(),
                key=lambda x: _RATING_ORDER.index(x[0]) if x[0] in _RATING_ORDER else 99,
                reverse=True,
            )
        )
        write_data_row(ws, row, [f"评级分布: {summary}"])
        row += 1

    row += 1
    write_data_row(ws, row, [
        "业绩评价标准(5级)：前10%→优秀(红)、10%~30%→良好、30%~50%→稳定(蓝)、50%~75%→偏差(绿)、后25%→较差(深绿) | "
        "超额收益评分≥80上调一级、<40下调一级"
    ])
    return row + 1


def write_fund_performance_sheet(
    ws: Worksheet,
    holdings: list[Holding],
    details: List[DetailRow],
) -> None:
    """写入基金业绩分析。

    对每只基金调 API 获取区间收益和同类排名，汇总为 11 列表格。
    评级同时考虑同类排名百分位和业绩比较基准（超额收益评分）。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
    """
    row = write_title_row(ws, 1, get_report_sheet_name('fund_performance'), _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    # 识别基金
    fund_holdings = [h for h in holdings if _is_fund(h)]
    detail_map = {d.code: d for d in details}

    if not fund_holdings:
        write_data_row(ws, row, ["未检测到基金持仓"])
        logger.info("基金业绩分析：无基金持仓")
        freeze_header(ws, 2)
        auto_width(ws)
        return

    # 按市值降序排列
    fund_holdings_sorted = sorted(
        fund_holdings,
        key=lambda h: detail_map.get(h.code).market_value if detail_map.get(h.code) else 0.0,
        reverse=True,
    )

    profit_forecast = _load_profit_forecast()
    adjusted_ratings: dict[str, str] = {}

    for idx, fund in enumerate(fund_holdings_sorted, 1):
        logger.info("获取基金业绩 [%d/%d]: %s (%s)", idx, len(fund_holdings_sorted), fund.name, fund.code)
        rating = _write_one_fund_row(ws, row, fund, detail_map, profit_forecast)
        if rating:
            adjusted_ratings[fund.code] = rating
        row += 1

    row = _write_rating_distribution(ws, row, len(fund_holdings_sorted), adjusted_ratings)
    freeze_header(ws, 2)
    auto_width(ws, min_width=10, max_width=30)

    logger.info("%s写入完成，%d/%d 只基金获取成功",
                get_report_sheet_name('fund_performance'),
                len(adjusted_ratings), len(fund_holdings_sorted))


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
        "--",
    ]
    write_data_row(ws, row, vals, _num_formats())


def _num_formats() -> list[str | None]:
    """每列的 Excel 数字格式。"""
    from src.python.report.styles import FMT_PERCENT, FMT_MONEY
    return [
        None,          # 1  基金（文本）
        None,          # 2  代码（文本）
        None,          # 3  类型（文本）
        FMT_PERCENT,   # 4  近3月
        FMT_PERCENT,   # 5  近6月
        FMT_PERCENT,   # 6  近12月
        FMT_MONEY,     # 7  持仓累计盈亏(¥)
        FMT_PERCENT,   # 8  持仓收益率
        None,          # 9  业绩基准（文本）
        None,          # 10 业绩评价（文本）
        None,          # 11 同类排名（文本）
        None,          # 12 机构覆盖（文本）
    ]
