"""HTML 报告生成引擎 — 将持仓分析数据渲染为 HTML 报告。

调用现有的计算模块获取所有分析数据，通过 Jinja2 模板
渲染为完整的单页 HTML 报告，支持最新版和归档版双重输出。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

from jinja2 import Environment, FileSystemLoader

from src.fetcher import fetch_fund_benchmark, fetch_fund_rankings, fetch_indices, fetch_us_indices
from src.models import Holding
from src.report.category import _categorize_holding
from src.report.fund_performance import (
    _RATING_COMMENT,
    _format_rank,
    _format_return,
    _fund_display_type,
    _is_fund,
)
from src.report.market_value import (
    DetailRow,
    _generate_details,
    classify_holdings,
    get_last_trading_day,
    price_update_status,
)
from src.report.penetration import compute_penetration_top10

logger = logging.getLogger("invest")

# ── 路径 ─────────────────────────────────────────────────────

_TEMPLATE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "tmpl")
)
_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))


# ── Jinja2 自定义过滤器 ─────────────────────────────────────


def _jinja_money(value: Any) -> str:
    """格式化金额：1,234.56"""
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return "--"


def _jinja_pct(value: Any) -> str:
    """格式化比率 (0.15 → +15.00%)"""
    try:
        v = float(value)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v * 100:.2f}%"
    except (ValueError, TypeError):
        return "--"


def _jinja_price(value: Any) -> str:
    """格式化价格：四位小数"""
    try:
        return f"{float(value):.4f}"
    except (ValueError, TypeError):
        return "--"


def _jinja_shares(value: Any) -> str:
    """格式化份额：两位小数"""
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return "--"


def _jinja_change(value: Any) -> str:
    """格式化涨跌幅：百分数"""
    try:
        v = float(value)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.2f}%"
    except (ValueError, TypeError):
        return "--"


def _jinja_profit_color(value: Any) -> str:
    """盈亏颜色：盈利红 #CC0000，亏损绿 #009900"""
    try:
        v = float(value)
        if v > 0:
            return "#CC0000"
        elif v < 0:
            return "#009900"
        return ""
    except (ValueError, TypeError):
        return ""


# 注册过滤器
_ENV.filters["money"] = _jinja_money
_ENV.filters["pct"] = _jinja_pct
_ENV.filters["price"] = _jinja_price
_ENV.filters["shares"] = _jinja_shares
_ENV.filters["change"] = _jinja_change
_ENV.filters["profit_color"] = _jinja_profit_color


# ── 核心生成函数 ────────────────────────────────────────────


def write_html_report(holdings: List[Holding], output_dir: str = "reports", news_top_count: int = 100) -> str:
    """生成 HTML 分析报告并保存到文件。

    1. 通过各计算模块获取全部分析数据
    2. 渲染 Jinja2 模板
    3. 写入 {output_dir}/ 目录（最新版 + 归档版）

    Args:
        holdings: 持仓记录列表
        output_dir: 报告输出根目录，默认 "reports"
        news_top_count: 财经新闻 TOP N 条数，默认 100

    Returns:
        最新版报告的绝对路径

    Raises:
        Exception: 任何计算或 IO 错误，由调用方处理
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")
    trading_day = get_last_trading_day()

    print("  [..] 正在获取行情数据...")
    logger.info("HTML 报告生成开始，共 %d 条持仓", len(holdings))

    # ── 1) 市值核算 ────────────────────────────────────────
    print("  [..] 正在计算市值核算...")
    details = _generate_details(holdings, today_str)
    logger.info("市值核算明细生成完成，共 %d 条", len(details))

    total_mv = sum(d.market_value for d in details)
    total_cost = sum(d.cost for d in details)
    total_profit = sum(d.profit for d in details)
    total_today_profit = sum(d.today_profit for d in details)
    total_profit_rate = total_profit / total_cost if total_cost > 0 else 0.0
    today_denom = total_cost + total_profit - total_today_profit
    today_profit_rate = total_today_profit / today_denom if today_denom > 0 else 0.0

    # ── 2) 按账户分组 + 小计 ────────────────────────────────
    print("  [..] 正在分组统计...")
    accounts: Dict[str, List[DetailRow]] = {}
    for d in details:
        accounts.setdefault(d.account, []).append(d)

    account_totals: Dict[str, Dict[str, float]] = {}
    for acc_name, acc_details in accounts.items():
        acc_mv = sum(d.market_value for d in acc_details)
        acc_cost = sum(d.cost for d in acc_details)
        acc_profit = sum(d.profit for d in acc_details)
        acc_today = sum(d.today_profit for d in acc_details)
        acc_rate = acc_profit / acc_cost if acc_cost > 0 else 0.0
        account_totals[acc_name] = {
            "market_value": acc_mv,
            "cost": acc_cost,
            "profit": acc_profit,
            "profit_rate": acc_rate,
            "today_profit": acc_today,
        }

    # ── 3) 分类信息 ─────────────────────────────────────────
    categories = classify_holdings(holdings)
    cat_counts: Dict[str, int] = {k: len(v) for k, v in categories.items()}
    up_status = price_update_status(details, trading_day)
    update_status_dict: Dict[str, Any] = {
        "updated": up_status[0],
        "total": up_status[1],
        "all_updated": up_status[2],
    }

    # ── 4) 市场指数 ─────────────────────────────────────────
    print("  [..] 正在获取市场指数...")
    a_indices_dict = fetch_indices()
    us_indices_dict = fetch_us_indices()

    a_indices: List[Dict[str, Any]] = []
    for code in ("sh000001", "sz399001", "sh000300", "sh000688", "sz399006"):
        idx = a_indices_dict.get(code)
        if idx:
            a_indices.append({
                "name": idx.get("name", ""),
                "price": idx.get("price", 0),
                "change": idx.get("change", 0),
                "change_pct": idx.get("change_pct", 0),
            })

    us_indices: List[Dict[str, Any]] = []
    for code in ("gb_dji", "gb_ixic", "gb_inx"):
        idx = us_indices_dict.get(code)
        if idx:
            us_indices.append({
                "name": idx.get("name", ""),
                "price": idx.get("price", 0),
                "change": idx.get("change", 0),
                "change_pct": idx.get("change_pct", 0),
            })

    # ── 5) 分类汇总数据 ─────────────────────────────────────
    print("  [..] 正在生成分类汇总...")
    cat_data = _build_category_data(holdings, details)

    # ── 6) 资产穿透 TOP10 ──────────────────────────────────
    print("  [..] 正在计算资产穿透 TOP10...")
    penetration = compute_penetration_top10(holdings, details)

    # ── 7) 基金业绩分析 ─────────────────────────────────────
    print("  [..] 正在获取基金业绩排名...")
    perf_data = _build_perf_data(holdings, details)

    # ── 8) 财经新闻热点（可选）─────────────────────────────
    print("  [..] 正在获取财经新闻...")
    try:
        from src.providers.sina_news import build_holding_keywords, fetch_and_correlate
        keywords = build_holding_keywords(holdings)
        news_data = fetch_and_correlate(keywords, top_n=news_top_count)
        if not news_data:
            news_data = []
            logger.info("新闻关联分析：无数据")
        else:
            logger.info("新闻关联分析完成，%d 条", len(news_data))
    except Exception as e:
        logger.warning("新闻获取失败: %s", e)
        news_data = []

    # ── 9) 渲染模板 ─────────────────────────────────────────
    print("  [..] 正在渲染 HTML...")
    template = _ENV.get_template("report_template.html")
    html = template.render(
        now=now_str,
        today=today_str,
        trading_day=trading_day,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_profit_rate=total_profit_rate,
        total_today_profit=total_today_profit,
        today_profit_rate=today_profit_rate,
        categories=cat_counts,
        update_status=update_status_dict,
        a_indices=a_indices,
        us_indices=us_indices,
        accounts=accounts,
        account_totals=account_totals,
        cat_data=cat_data,
        penetration=penetration,
        perf_data=perf_data,
        news_data=news_data,
    )

    # ── 9) 保存文件 ─────────────────────────────────────────
    print("  [..] 正在保存报告文件...")

    # 确保目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 最新版
    latest_path = os.path.join(output_dir, "个人投资分析报告.html")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("最新 HTML 报告已保存: %s", latest_path)
    print(f"  [OK] 最新版报告: {latest_path}")

    # 归档版
    archive_dir = os.path.join(
        output_dir,
        datetime.now().strftime("%Y%m%d"),
    )
    os.makedirs(archive_dir, exist_ok=True)
    archive_filename = "个人投资分析报告-{}.html".format(
        datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    archive_path = os.path.join(archive_dir, archive_filename)
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("归档 HTML 报告已保存: %s", archive_path)
    print(f"  [OK] 归档版报告: {archive_path}")

    print(f"  [OK] HTML 报告生成完成！总市值: {total_mv:,.2f}元, "
          f"总盈亏: {total_profit:,.2f}元")

    return os.path.abspath(latest_path)


# ── 辅助构建函数 ────────────────────────────────────────────


def _build_category_data(
    holdings: List[Holding],
    details: List[DetailRow],
) -> List[Dict[str, Any]]:
    """构建分类汇总数据结构。

    按 (资产属性, 投资分类) 分组，汇总每组内的明细数据，
    按 股票→基金→债券→现金 顺序排列。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        分类汇总数据列表，每个元素含 property / sub_category / items / 小计字段
    """
    detail_map: Dict[str, DetailRow] = {d.code: d for d in details}

    cat_groups: Dict[Tuple[str, str], List[Holding]] = {}
    for h in holdings:
        prop, sub = _categorize_holding(h)
        cat_groups.setdefault((prop, sub), []).append(h)

    _PROP_ORDER = {"股票": 0, "基金": 1, "债券": 2, "现金": 3, "其他": 4}
    _SUB_ORDER = {
        "A股": 0, "QDII": 1, "主动": 2, "被动": 3,
        "指数": 4, "混合": 5, "纯债": 6, "货币": 7, "其他": 8,
    }
    sorted_groups = sorted(
        cat_groups.items(),
        key=lambda x: (
            _PROP_ORDER.get(x[0][0], 99),
            _SUB_ORDER.get(x[0][1], 99),
        ),
    )

    result: List[Dict[str, Any]] = []
    for (prop, sub), group in sorted_groups:
        items: List[Dict[str, Any]] = []
        for h in group:
            d = detail_map.get(h.code)
            items.append({
                "name": h.name,
                "code": h.code,
                "market_value": d.market_value if d else 0.0,
                "cost": d.cost if d else 0.0,
                "profit": d.profit if d else 0.0,
                "profit_rate": d.profit_rate if d else 0.0,
                "today_profit": d.today_profit if d else 0.0,
            })

        sub_mv = sum(i["market_value"] for i in items)
        sub_cost = sum(i["cost"] for i in items)
        sub_profit = sum(i["profit"] for i in items)
        sub_today = sum(i["today_profit"] for i in items)
        sub_rate = sub_profit / sub_cost if sub_cost > 0 else 0.0

        result.append({
            "property": prop,
            "sub_category": sub,
            "items": items,
            "sub_mv": sub_mv,
            "sub_cost": sub_cost,
            "sub_profit": sub_profit,
            "sub_rate": sub_rate,
            "sub_today": sub_today,
        })

    return result


def _build_perf_data(
    holdings: List[Holding],
    details: List[DetailRow],
) -> List[Dict[str, Any]]:
    """构建基金业绩分析数据。

    筛选出基金持仓，对每只基金调用 API 获取区间收益和同类排名，
    按市值降序排列。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        业绩分析数据列表，每项含名称/代码/类型/收益率/排名等字符串值
    """
    fund_holdings = [h for h in holdings if _is_fund(h)]
    detail_map: Dict[str, DetailRow] = {d.code: d for d in details}

    # 按市值降序
    fund_holdings_sorted = sorted(
        fund_holdings,
        key=lambda h: detail_map.get(h.code, DetailRow()).market_value,
        reverse=True,
    )

    result: List[Dict[str, Any]] = []
    fund_count = len(fund_holdings_sorted)

    for idx, fund in enumerate(fund_holdings_sorted, 1):
        logger.info(
            "获取基金业绩 [%d/%d]: %s (%s)",
            idx, fund_count, fund.name, fund.code,
        )
        print(f"  [..] 基金业绩 [{idx}/{fund_count}]: {fund.name}")

        d = detail_map.get(fund.code)

        perf_data = fetch_fund_rankings(fund.code)
        rankings: Dict[str, Any] = {}
        rating: str = ""

        if perf_data and perf_data.get("rankings"):
            rankings = perf_data.get("rankings", {})
            rating = perf_data.get("rating", "")
        else:
            logger.warning("基金 %s (%s) 业绩数据获取失败", fund.name, fund.code)

        type_label = _fund_display_type(fund)
        benchmark = fetch_fund_benchmark(fund.code)

        # 持仓盈亏
        if d:
            profit_val = d.profit
            profit_rate_val = d.profit_rate
            profit_str = f"{profit_val:+,.2f}"
            profit_rate_str = f"{profit_rate_val * 100:+.2f}%"
        else:
            profit_val = 0.0
            profit_rate_val = 0.0
            profit_str = "--"
            profit_rate_str = "--"

        # 区间收益（格式化字符串）
        syl_3m = _format_return(rankings.get("近3月", {}).get("return"))
        syl_6m = _format_return(rankings.get("近6月", {}).get("return"))
        syl_1y = _format_return(rankings.get("近1年", {}).get("return"))

        # 解析 raw 数值用于着色（兼容 None / "--"）
        syl_3m_raw = _parse_return_raw(rankings.get("近3月", {}).get("return"))
        syl_6m_raw = _parse_return_raw(rankings.get("近6月", {}).get("return"))
        syl_1y_raw = _parse_return_raw(rankings.get("近1年", {}).get("return"))

        # 业绩评价
        rating_comment = _RATING_COMMENT.get(rating, "--")

        # 同类排名
        rank_str = _format_rank(rankings.get("同类排名", {}))

        result.append({
            "name": fund.name,
            "code": fund.code,
            "type_label": type_label,
            "syl_3m": syl_3m,
            "syl_6m": syl_6m,
            "syl_1y": syl_1y,
            "syl_3m_raw": syl_3m_raw,
            "syl_6m_raw": syl_6m_raw,
            "syl_1y_raw": syl_1y_raw,
            "profit": profit_str,
            "profit_rate": profit_rate_str,
            "profit_raw": profit_val,
            "profit_rate_raw": profit_rate_val,
            "benchmark": benchmark,
            "rating": rating_comment,
            "rating_tag": rating,
            "rank": rank_str,
        })

    if result:
        logger.info("基金业绩分析完成，%d 只基金获取成功", len(result))
    else:
        logger.info("基金业绩分析：无基金持仓")

    return result


def _parse_return_raw(val: Any) -> float | None:
    """解析收益率原始数值，用于着色判断。

    Args:
        val: 可为 None, "--", float, int

    Returns:
        数值，None 表示无法解析
    """
    if val is None or val == "--":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
