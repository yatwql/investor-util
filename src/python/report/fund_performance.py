"""基金业绩分析模块。

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

from src.python.cache import get_ttl
from src.python.core.code_utils import is_fund_holding
from src.python.fetcher.fund import fetch_fund_benchmark, fetch_fund_rankings, fetch_fund_rankings_batch
from src.python.core.models import Holding
from src.python.core.registry import get_report_sheet_name
from src.python.report.data_status import (
    STATUS_MESSAGES,
    DataStatus,
    DataStatusItem,
    get_tracker,
)
from src.python.report.fund_candidate import build_candidate_compare_data
from src.python.report.excel_writer import (
    _write_data_status_foot,
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.market_value import DetailRow
from src.python.report.penetration import ACTIVE_EQUITY, BOND_FUND, ETF, INDEX_LINK, QDII, classify_penetration
from src.python.report.styles import BLUE_FONT, DARK_GREEN_FONT, GREEN_FONT, RED_FONT

logger = logging.getLogger("invest")

# 模块级降级阈值控制器（单例工厂共享，T0-01-A 统一管理）
_tracker = get_tracker()

_NCOLS = 11
_CANDIDATE_HEADERS = [
    "候选基金",
    "代码",
    "评级",
    "近1月",
    "近3月",
    "近6月",
    "近1年",
    "同类排名",
    "最大回撤",
    "风格",
    "与持仓重合",
]
_HEADERS = [
    "基金",
    "代码",
    "类型",
    "近3月",
    "近6月",
    "近12月",
    "持仓累计盈亏(¥)",
    "持仓收益率",
    "业绩基准",
    "业绩评价",
    "同类排名",
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

# 超额收益评分阈值（用于评级修正，可从 config.json 覆盖）
_DEFAULT_EXCESS_THRESHOLD_UP = 80
_DEFAULT_EXCESS_THRESHOLD_DOWN = 40


def _get_excess_thresholds() -> tuple[int, int]:
    """从 config.json 读取超额收益评分阈值，失败时返回内置默认值。"""
    try:
        from src.python.config import get_config

        cfg = get_config().get("performance_evaluation", {})
        up = int(cfg.get("excess_threshold_up", _DEFAULT_EXCESS_THRESHOLD_UP))
        down = int(cfg.get("excess_threshold_down", _DEFAULT_EXCESS_THRESHOLD_DOWN))
        return up, down
    except (TypeError, ValueError, KeyError):
        return _DEFAULT_EXCESS_THRESHOLD_UP, _DEFAULT_EXCESS_THRESHOLD_DOWN


def _fund_display_type(h: Holding) -> str:
    """用穿透分类逻辑判定基金类型，返回中文显示标签。"""
    ftype = classify_penetration(h)
    return _FUND_TYPE_LABEL.get(ftype, "--")


def is_fund(h: Holding) -> bool:
    """判断持仓是否为基金（需要业绩分析），委托 code_utils。"""
    return is_fund_holding(h.name, h.code, h.account)


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

    up, down = _get_excess_thresholds()

    if excess_score >= up:
        # 超额收益显著 → 上调
        new_idx = min(current_idx + 1, len(_RATING_ORDER) - 1)
    elif excess_score < down:
        # 超额收益较差 → 下调
        new_idx = max(current_idx - 1, 0)
    else:
        # 中间区间 → 不调整
        return peer_rating

    adjusted = _RATING_ORDER[new_idx]
    if adjusted != peer_rating:
        logger.debug("评级调整: %s → %s（超额收益评分 %.0f）", peer_rating, adjusted, excess_score)
    return adjusted


def _write_one_fund_row(
    ws: Worksheet,
    row: int,
    fund: Holding,
    detail_map: dict[str, DetailRow],
    prefetched_rankings: dict[str, dict[str, Any] | None] | None = None,
) -> str | None:
    """获取并写入单只基金的业绩数据行。

    Args:
        ws: 工作表
        row: 当前行号
        fund: 基金持仓
        detail_map: 估值明细映射 {code: DetailRow}
        prefetched_rankings: 预取的批量排名映射，None 时回退到单个获取。

    Returns:
        最终评级（优秀/良好/稳定/偏差/较差），获取失败返回 None
    """
    if prefetched_rankings is not None and fund.code in prefetched_rankings:
        perf_data = prefetched_rankings[fund.code]
    else:
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
        fund.name,
        fund.code,
        fund_type,
        _format_return(rankings.get("近3月", {}).get("return")),
        _format_return(rankings.get("近6月", {}).get("return")),
        _format_return(rankings.get("近1年", {}).get("return")),
        profit_val,
        profit_rate_val,  # 已为小数（如 0.0523），Excel 0.00% 格式自动处理
        benchmark,
        comment,
        _format_rank(rankings.get("同类排名", {})),
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
            f"{k}: {v}只"
            for k, v in sorted(
                rating_counts.items(),
                key=lambda x: _RATING_ORDER.index(x[0]) if x[0] in _RATING_ORDER else 99,
                reverse=True,
            )
        )
        write_data_row(ws, row, [f"评级分布: {summary}"])
        row += 1

    row += 1
    write_data_row(
        ws,
        row,
        [
            "业绩评价标准(5级)：前10%→优秀(红)、10%~30%→良好、30%~50%→稳定(蓝)、50%~75%→偏差(绿)、后25%→较差(深绿) | "
            "超额收益评分≥80上调一级、<40下调一级"
        ],
    )
    return row + 1


def build_perf_data_status(
    adjusted_ratings: dict[str, str],
    total_funds: int,
) -> DataStatus:
    """根据基金业绩数据获取结果构建数据源状态字典。

    Args:
        adjusted_ratings: 成功获取评级的基金 {code: rating}
        total_funds: 需分析的基金总数

    Returns:
        数据源状态字典（可能为空 = 全部正常）
    """
    status: DataStatus = {}

    # 排名数据（T2）— 全部失败
    if not adjusted_ratings and total_funds > 0:
        # 所有基金均未获取到排名数据（无代表性缓存年龄可查）
        ttl = get_ttl("fund_rank")
        degraded, _, _ = _tracker.record(
            "perf_rank",
            "T2",
            success=False,
            failure_type="empty",
            cache_age_hours=None,
            cache_ttl_hours=ttl / 3600 if ttl else 24,
        )
        if degraded:
            status["rank"] = DataStatusItem(
                available=False,
                tier="T2",
                message=STATUS_MESSAGES["rank_unavailable"],
            )

    return status


def write_fund_performance_sheet(
    ws: Worksheet,
    holdings: list[Holding],
    details: list[DetailRow],
) -> None:
    """写入基金业绩分析。

    对每只基金调 API 获取区间收益和同类排名，汇总为 11 列表格。
    评级同时考虑同类排名百分位和业绩比较基准（超额收益评分）。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
    """
    row = write_title_row(ws, 1, get_report_sheet_name("fund_performance"), _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    # 识别基金
    fund_holdings = [h for h in holdings if is_fund(h)]
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
        key=lambda h: detail_map[h.code].market_value if h.code in detail_map else 0.0,
        reverse=True,
    )

    adjusted_ratings: dict[str, str] = {}

    fund_codes = [f.code for f in fund_holdings_sorted]
    prefetched_rankings = fetch_fund_rankings_batch(fund_codes)

    for idx, fund in enumerate(fund_holdings_sorted, 1):
        logger.info("获取基金业绩 [%d/%d]: %s (%s)", idx, len(fund_holdings_sorted), fund.name, fund.code)
        rating = _write_one_fund_row(ws, row, fund, detail_map, prefetched_rankings=prefetched_rankings)
        if rating:
            adjusted_ratings[fund.code] = rating
        row += 1

    row = _write_rating_distribution(ws, row, len(fund_holdings_sorted), adjusted_ratings)

    # 数据源状态
    data_status = build_perf_data_status(adjusted_ratings, len(fund_holdings_sorted))
    _write_data_status_foot(ws, data_status, start_row=row)

    # 候选基金比较子表（report_submodules.candidate_compare 默认关；关闭时 build 返回 None）
    candidate_data = build_candidate_compare_data(holdings)
    if candidate_data is not None and candidate_data.get("available"):
        row = _write_candidate_compare_block(ws, row + 1, candidate_data)

    freeze_header(ws, 2)
    auto_width(ws, min_width=10, max_width=30)

    if not adjusted_ratings:
        logger.warning("[fund_performance] 天天基金排名接口均返回空数据，排名列显示 --")
    else:
        logger.info(
            "%s写入完成，%d/%d 只基金获取成功",
            get_report_sheet_name("fund_performance"),
            len(adjusted_ratings),
            len(fund_holdings_sorted),
        )


def _write_candidate_compare_block(ws, row: int, candidate_data: dict[str, Any]) -> int:
    """写入候选基金比较子表（主业绩表下方子区块）。

    Args:
        ws: 目标工作表
        row: 起始行（数据源状态脚注之后）
        candidate_data: build_candidate_compare_data 返回的候选比较数据

    Returns:
        下一可用行号
    """
    row = write_title_row(ws, row, "候选基金比较（候选来自 config.comparison_candidates）", _NCOLS)
    row = write_header_row(ws, row, _CANDIDATE_HEADERS)
    fmt = _candidate_num_formats()
    for c in candidate_data.get("rows", []):
        if not c.get("available"):
            write_data_row(
                ws,
                row,
                [c.get("name", c["code"]), c["code"], "获取失败", "--", "--", "--", "--", "--", "--", "--", "--"],
                fmt,
            )
            row += 1
            continue
        overlap = "--"
        if c.get("overlap_name") and c.get("overlap_jaccard_raw") is not None:
            overlap = f"{c['overlap_jaccard']}（{c['overlap_name']}）"
        write_data_row(
            ws,
            row,
            [
                c.get("name", c["code"]),
                c["code"],
                c.get("rating", "--"),
                c.get("syl_近1月_raw"),
                c.get("syl_近3月_raw"),
                c.get("syl_近6月_raw"),
                c.get("syl_近1年_raw"),
                c.get("rank_text", "--"),
                c.get("max_drawdown_raw"),
                c.get("style", "--"),
                overlap,
            ],
            fmt,
        )
        row += 1
    if candidate_data.get("exceed_limit"):
        write_data_row(ws, row, ["候选基金超过 10 只，仅比较前 10 只", "", "", "", "", "", "", "", "", "", ""], fmt)
        row += 1
    if candidate_data.get("invalid"):
        write_data_row(
            ws,
            row,
            [f"无效候选代码（忽略）: {'、'.join(candidate_data['invalid'])}", "", "", "", "", "", "", "", "", "", ""],
            fmt,
        )
        row += 1
    return row


def _candidate_num_formats() -> list[str | None]:
    """候选比较子表每列的 Excel 数字格式。"""
    from src.python.report.styles import FMT_PERCENT

    return [
        None,  # 1  候选基金（文本）
        None,  # 2  代码（文本）
        None,  # 3  评级（文本）
        FMT_PERCENT,  # 4  近1月
        FMT_PERCENT,  # 5  近3月
        FMT_PERCENT,  # 6  近6月
        FMT_PERCENT,  # 7  近1年
        None,  # 8  同类排名（文本）
        FMT_PERCENT,  # 9  最大回撤
        None,  # 10 风格（文本）
        None,  # 11 与持仓重合（文本）
    ]


def _write_empty_row(ws, row: int, fund: Holding) -> None:
    """写入获取失败的基金占位行。"""
    vals = [
        fund.name,
        fund.code,
        _fund_display_type(fund),
        "--",
        "--",
        "--",
        "--",
        "--",
        "--",
        "--",
        "--",
    ]
    write_data_row(ws, row, vals, _num_formats())


def _num_formats() -> list[str | None]:
    """每列的 Excel 数字格式。"""
    from src.python.report.styles import FMT_MONEY, FMT_PERCENT

    return [
        None,  # 1  基金（文本）
        None,  # 2  代码（文本）
        None,  # 3  类型（文本）
        FMT_PERCENT,  # 4  近3月
        FMT_PERCENT,  # 5  近6月
        FMT_PERCENT,  # 6  近12月
        FMT_MONEY,  # 7  持仓累计盈亏(¥)
        FMT_PERCENT,  # 8  持仓收益率
        None,  # 9  业绩基准（文本）
        None,  # 10 业绩评价（文本）
        None,  # 11 同类排名（文本）
    ]
