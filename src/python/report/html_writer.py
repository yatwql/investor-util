"""HTML 报告生成引擎 — 将持仓分析数据渲染为 HTML 报告。

调用现有的计算模块获取所有分析数据，通过 Jinja2 模板
渲染为完整的单页 HTML 报告，支持最新版和归档版双重输出。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.python.cache import get_cache_hit_rate
from src.python.code_utils import is_qdii_extended
from src.python.constants import APP_VERSION
from src.python.fetcher.fund import fetch_fund_holdings
from src.python.fetcher.index import fetch_indices, fetch_us_indices
from src.python.models import Holding
from src.python.registry import get_llm_module_name, get_llm_module_names, get_report_section_order
from src.python.report.category import _build_category_data_status
from src.python.report.data_status import DataStatus
from src.python.report.fund_concentration import compute_concentration
from src.python.report.fund_manager_analysis import build_first_check_summary, detect_manager_changes
from src.python.report.fund_overlap import compute_overlap_matrix
from src.python.report.fund_performance import _build_perf_data_status, _is_fund
from src.python.report.fund_style_analysis import analyze_style_for_all_funds
from src.python.report.html_builders import _build_category_data, _build_perf_data
from src.python.report.market_value import (
    DetailRow,
    _generate_details,
    classify_holdings,
    get_last_trading_day,
    price_update_status,
)
from src.python.report.penetration import compute_penetration_top10
from src.python.report.penetration_sheet import _build_penetration_data_status
from src.python.report.progress import ProgressReporter, SilentProgressReporter
from src.python.report.summary import _build_index_data_status

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  文件导览
# ═══════════════════════════════════════════════════════════════
#
#   路径 + Jinja2 环境         L46  ~ L52
#   Jinja2 自定义过滤器         L54  ~ L165
#     过滤器函数                L57  ~ L134
#     全局函数                  L136 ~ L150
#     注册                      L153 ~ L164
#   辅助函数                    L167 ~ L190
#   核心生成函数                L192 ~ L351
#     write_html_report()       L195 ~ L350
#   子渲染函数                  L353 ~ L919
#     时间辅助                  L356 ~ L362
#     市场行情                  L365 ~ L393
#     账户分组                  L396 ~ L423
#     分类信息                  L426 ~ L444
#     市场指数                  L447 ~ L476
#     持仓分类表                L479 ~ L489
#     穿透 TOP10                L492 ~ L553
#     基金业绩                  L556 ~ L571
#     基金经理变更              L574 ~ L594
#     持仓重合度矩阵            L597 ~ L640
#     集中度                    L643 ~ L675
#     风格分析                  L678 ~ L713
#     新闻关联                  L716 ~ L753
#     LLM 内容                  L756 ~ L820
#     LLM 模块信息              L823 ~ L918
#   报告保存（已迁出 → html_save.py）
#
# ═══════════════════════════════════════════════════════════════

# ── 路径 ─────────────────────────────────────────────────────

_TEMPLATE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "tmpl")
)
_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)


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


def _jinja_price_type_color(price_type: str, name: str = "") -> str:
    """取价方式颜色：蓝色代表数据时效性高/可靠。

    着色规则同 Excel 端 _apply_price_type_colors：
      - "场内收盘价(T)"、"场内午市收盘(T)"、"官方净值(T)" → #0066CC
      - QDII 基金 "官方净值(T-1)" → #0066CC
    """
    if price_type in ("场内收盘价(T)", "场内午市收盘(T)", "官方净值(T)"):
        return "#0066CC"
    if price_type == "官方净值(T-1)" and name and is_qdii_extended(name):
        return "#0066CC"
    return ""


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


def _jinja_thousands(value: Any) -> str:
    """格式化整数：1,234"""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def _jinja_section_visible(key: str) -> bool:
    """Jinja2 全局函数：判断报告模块是否可见。

    依赖模板上下文中的 section_visible_dict，在渲染前由
    write_html_report 设置。

    Usage in template:
        {% if section_visible("fund_manager") %}
        ...
        {% endif %}
    """
    sv_dict = _ENV.globals.get("section_visible_dict", {})
    if not isinstance(sv_dict, dict):
        return False
    return bool(sv_dict.get(key, False))


# 注册过滤器
_ENV.filters["money"] = _jinja_money
_ENV.filters["pct"] = _jinja_pct
_ENV.filters["price"] = _jinja_price
_ENV.filters["shares"] = _jinja_shares
_ENV.filters["change"] = _jinja_change
_ENV.filters["profit_color"] = _jinja_profit_color
_ENV.filters["price_type_color"] = _jinja_price_type_color
_ENV.filters["thousands"] = _jinja_thousands

# 注册全局函数
_ENV.globals["section_visible"] = _jinja_section_visible


# ── 辅助函数 ──────────────────────────────────────────────


def _safe_build_data_status(builder, *args, label: str = "", **kwargs) -> DataStatus:
    """安全构建数据状态，异常时返回空字典并记录日志。

    统一处理 data_status 构建中的 try/except/log 三步骤，
    避免 3 个 try 块重复此模式。

    Args:
        builder: 状态构建函数（如 _build_index_data_status）
        label: 模块名称（用于日志消息），如 "指数"/"穿透"/"基金业绩"
        *args, **kwargs: 透传给 builder 的参数

    Returns:
        构建成功返回 DataStatus 字典，异常返回 {}
    """
    try:
        result = builder(*args, **kwargs)
        return result if isinstance(result, dict) else {}
    except Exception:
        logger.debug("HTML 报告构建%s数据状态失败（非关键）", label, exc_info=True)
        return {}


# ── 核心生成函数 ────────────────────────────────────────────


def write_html_report(holdings: list[Holding], output_dir: str = "reports", news_top_count: int = 100, enable_llm: bool = False, include_news: bool = True, force_llm: bool = False, llm_content: tuple[str | None, str | None, str | None, str | None] | None = None, details: list | None = None, news_data: list | None = None, news_llm_meta: dict | None = None, sector_flow: list | None = None, early_warnings: dict | None = None, progress: ProgressReporter | None = None, section_order: list[dict] | None = None) -> str:
    """生成 HTML 分析报告并保存到文件。

    通过各子函数获取分析数据，渲染 Jinja2 模板，
    写入 {output_dir}/ 目录（最新版 + 归档版）。

    Args:
        llm_content: 可选预生成内容 (global_macro_html, expert_review_html, health_check_html, penetration_deep_html)，
            传入时跳过内部 LLM 生成直接使用此内容。
        details: 可选预计算市值核算明细，传入时跳过内部行情获取。
        news_data: 可选预获取新闻数据，传入时跳过内部新闻获取。
        news_llm_meta: 与 news_data 对应的 LLM 元数据字典。
        sector_flow: 行业资金流向数据（可选），注入全球政经局势 LLM prompt

    Returns:
        最新版报告的绝对路径
    """
    prog = progress if progress is not None else SilentProgressReporter()
    now_str, today_str, trading_day = _time_strings()

    # ── 1) 市值核算 ──
    details, totals = _render_market_value_section(holdings, details, today_str, prog)
    total_mv, total_cost, total_profit, total_today_profit = totals[:4]
    total_profit_rate, today_profit_rate = totals[4:]

    # ── 2) 按账户分组 ──
    accounts, account_totals = _render_account_grouping(details, prog)

    # ── 3) 分类信息 + 指数 ──
    cat_counts, update_status_dict = _render_category_info(holdings, details, trading_day)

    # ── 4) 市场指数 ──
    a_indices, us_indices, a_indices_list, us_indices_list = _render_index_section(prog)

    # ── 5~7) 分类表 / 穿透 / 基金业绩 ──
    cat_data, cat_dividend_ok = _render_category_table(holdings, details, prog)
    penetration, penetration_profit_ok, penetration_dividend_ok = _render_penetration_section(holdings, details, prog)
    perf_data, perf_profit_ok = _render_fund_performance_section(holdings, details, prog)

    # ── 13) 基金经理变更监控（B 系列） ──
    enable_b_series = include_news  # B/L 菜单含基金深度分析
    manager_analysis = _render_manager_analysis(holdings, enable_b_series, prog)

    # ── 14) 持仓重合度矩阵（B 系列） ──
    overlap_matrix = _render_overlap_matrix(holdings, details, enable_b_series, prog)

    # ── 15) 持仓集中度监控（B 系列） ──
    concentration_analysis = _render_concentration(holdings, enable_b_series, prog)

    # ── 16) 基金风格分析（B 系列） ──
    style_analysis = _render_style_analysis(holdings, enable_b_series, prog)

    # ── 8) 财经新闻 ──
    news_data, _news_llm_meta = _render_news_section(
        include_news, news_data, news_llm_meta, holdings, news_top_count, penetration, prog)

    # ── 9) LLM 智能分析内容 ──
    llm_enabled_flag, global_macro_content, expert_review_content, health_check_content, penetration_deep_content = _render_llm_content_section(
        enable_llm, llm_content, force_llm, a_indices, us_indices,
        total_mv, total_cost, total_profit, total_today_profit,
        holdings, cat_counts, penetration, details, sector_flow, prog)

    # ── LLM 模块状态收集 ──
    llm_module_info, llm_endpoint, module_disabled, _llm_session_usage = _render_llm_module_info(llm_enabled_flag)

    # ── 10) 渲染模板 ──
    prog.info("正在渲染 HTML...")
    has_llm_analysis = any(item.get("llm_analysis") for item in (news_data or []))

    # 报告模块序号 & 可见性（优先使用传入的 section_order，避免影子覆盖参数）
    order = section_order or get_report_section_order()
    section_numbers = {sec["key"]: sec["number"] for sec in order}

    raw_data_flags = {
        # B 系列：返回非 None = 模块已启用 → section 始终可见（空数据时显示占位）
        "manager_data": manager_analysis is not None,
        "overlap_data": overlap_matrix is not None,
        "concentration_data": concentration_analysis is not None,
        "style_data": style_analysis is not None,
        "include_news": include_news,
        "early_warnings": bool(early_warnings),
        "llm_enabled": llm_enabled_flag,
    }
    section_visible_dict = {}
    for sec in order:
        flag_name = sec.get("data_flag")
        if not flag_name:
            section_visible_dict[sec["key"]] = True
        else:
            section_visible_dict[sec["key"]] = raw_data_flags.get(flag_name, False)

    _ENV.globals["section_visible_dict"] = section_visible_dict

    # ── 11) 构建各章节数据源状态摘要 ──
    data_status_summary: DataStatus = _safe_build_data_status(
        _build_index_data_status, a_indices, us_indices, label="指数",
    )
    data_status_penetration: DataStatus = {}
    if penetration:
        data_status_penetration = _safe_build_data_status(
            _build_penetration_data_status, penetration,
            penetration_profit_ok, penetration_dividend_ok, label="穿透",
        )
    # 从 perf_data 提取真实 adjusted_ratings（无异常风险，放外面不吞）
    _adj_ratings: dict[str, str] = {}
    if perf_data:
        for _entry in perf_data:
            _code = _entry.get("code")
            _tag = _entry.get("rating_tag")
            if _code and _tag:
                _adj_ratings[_code] = _tag
    data_status_perf: DataStatus = _safe_build_data_status(
        _build_perf_data_status, _adj_ratings,
        sum(1 for h in holdings if _is_fund(h)),
        profit_success=perf_profit_ok, label="基金业绩",
    )
    data_status_category: DataStatus = _safe_build_data_status(
        _build_category_data_status, cat_dividend_ok, label="持仓分类",
    )

    html = _ENV.get_template("report_template.html").render(
        now=now_str, today=today_str, trading_day=trading_day,
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_profit_rate=total_profit_rate,
        total_today_profit=total_today_profit, today_profit_rate=today_profit_rate,
        categories=cat_counts, update_status=update_status_dict,
        a_indices=a_indices_list, us_indices=us_indices_list,
        accounts=accounts, account_totals=account_totals,
        cat_data=cat_data, penetration=penetration, perf_data=perf_data,
        # SAC: news_data[*].enriched_keywords[*].display 来自外部 API
        # 模板中已禁用 |safe 过滤器，依赖 autoescape 防 XSS —— 勿加 |safe
        news_data=news_data, news_llm_meta=_news_llm_meta,
        has_llm_analysis=has_llm_analysis,
        manager_analysis=manager_analysis,
        overlap_matrix=overlap_matrix,
        concentration_analysis=concentration_analysis,
        style_analysis=style_analysis,
        llm_enabled=llm_enabled_flag,
        global_macro=global_macro_content, expert_review=expert_review_content,
        health_check=health_check_content, penetration_deep=penetration_deep_content,
        llm_session_usage=_llm_session_usage, early_warnings=early_warnings,
        module_labels=get_llm_module_names(), module_disabled=module_disabled,
        llm_module_info=llm_module_info, llm_endpoint=llm_endpoint,
        cache_stats=get_cache_hit_rate(),
        app_version=APP_VERSION,
        # C 迭代：序号 & 可见性（模板使用 section_numbers/section_visible_dict）
        section_order=order, section_numbers=section_numbers,
        section_visible_dict=section_visible_dict,
        # D 迭代：数据源状态摘要
        data_status_summary=data_status_summary,
        data_status_penetration=data_status_penetration,
        data_status_perf=data_status_perf,
        data_status_category=data_status_category,
        # 报告年份（穿透表预测EPS列使用）
        report_year=datetime.now().year,
        # 数据不可用标记 — 模板用于显示/隐藏 暂无数据 横幅
        data_unavailable=bool(total_mv == 0 and total_cost > 0),
    )

    return _save_html_report(html, output_dir, total_mv, total_profit, prog)


# ── 子渲染函数 ───────────────────────────────────────────


def _time_strings() -> tuple[str, str, str]:
    """返回 (now_str, today_str, trading_day)。"""
    return (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        datetime.now().strftime("%Y-%m-%d"),
        get_last_trading_day(),
    )


def _render_market_value_section(
    holdings: list[Holding],
    details: list | None,
    today_str: str,
    prog: ProgressReporter,
) -> tuple[list, tuple[float, float, float, float, float, float]]:
    """市值核算：生成明细并计算汇总值。

    Returns:
        (details, (total_mv, total_cost, total_profit, total_today_profit,
                   total_profit_rate, today_profit_rate))
    """
    if details is not None:
        logger.info("复用外部传入的市值核算数据，共 %d 条", len(details))
    else:
        prog.info("正在获取行情数据...")
        logger.info("HTML 报告生成开始，共 %d 条持仓", len(holdings))
        prog.info("正在计算市值核算...")
        details = _generate_details(holdings, today_str)
        logger.info("市值核算明细生成完成，共 %d 条", len(details))

    total_mv = sum(d.market_value for d in details)
    total_cost = sum(d.cost for d in details)
    total_profit = sum(d.profit for d in details)
    total_today_profit = sum(d.today_profit for d in details)
    total_profit_rate = total_profit / total_cost if total_cost > 0 else 0.0
    today_denom = total_cost + total_profit - total_today_profit
    today_profit_rate = total_today_profit / today_denom if today_denom > 0 else 0.0
    return details, (total_mv, total_cost, total_profit, total_today_profit, total_profit_rate, today_profit_rate)


def _render_account_grouping(
    details: list,
    prog: ProgressReporter,
) -> tuple[dict[str, list[DetailRow]], dict[str, dict[str, float]]]:
    """按账户分组并计算小计。

    Returns:
        (accounts: {账户名: [DetailRow]},
         account_totals: {账户名: {market_value, cost, profit, profit_rate, today_profit}})
    """
    prog.info("正在分组统计...")
    accounts: dict[str, list[DetailRow]] = {}
    for d in details:
        accounts.setdefault(d.account, []).append(d)

    account_totals: dict[str, dict[str, float]] = {}
    for acc_name, acc_details in accounts.items():
        acc_mv = sum(d.market_value for d in acc_details)
        acc_cost = sum(d.cost for d in acc_details)
        acc_profit = sum(d.profit for d in acc_details)
        acc_today = sum(d.today_profit for d in acc_details)
        acc_rate = acc_profit / acc_cost if acc_cost > 0 else 0.0
        account_totals[acc_name] = {
            "market_value": acc_mv, "cost": acc_cost,
            "profit": acc_profit, "profit_rate": acc_rate,
            "today_profit": acc_today,
        }
    return accounts, account_totals


def _render_category_info(
    holdings: list[Holding],
    details: list,
    trading_day: str,
) -> tuple[dict[str, int], dict[str, Any]]:
    """分类信息 + 价格更新状态。

    Returns:
        (cat_counts, update_status_dict)
    """
    categories = classify_holdings(holdings)
    cat_counts: dict[str, int] = {k: len(v) for k, v in categories.items()}
    up_status = price_update_status(details, trading_day)
    update_status_dict: dict[str, Any] = {
        "updated": up_status[0],
        "total": up_status[1],
        "all_updated": up_status[2],
    }
    return cat_counts, update_status_dict


def _render_index_section(
    prog: ProgressReporter,
) -> tuple[dict, dict, list[dict[str, Any]], list[dict[str, Any]]]:
    """获取市场指数并转为模板可迭代列表。

    Returns:
        (a_indices, us_indices, a_indices_list, us_indices_list)
    """
    prog.info("正在获取市场指数...")
    a_indices: dict = fetch_indices()
    us_indices: dict = fetch_us_indices()

    a_indices_list: list[dict[str, Any]] = []
    for code in ("sh000001", "sz399001", "sh000300", "sh000688", "sz399006"):
        idx = a_indices.get(code)
        if idx:
            a_indices_list.append({
                "name": idx.get("name", ""), "price": idx.get("price", 0),
                "change": idx.get("change", 0), "change_pct": idx.get("change_pct", 0),
            })

    us_indices_list: list[dict[str, Any]] = []
    for code in ("gb_dji", "gb_ixic", "gb_inx"):
        idx = us_indices.get(code)
        if idx:
            us_indices_list.append({
                "name": idx.get("name", ""), "price": idx.get("price", 0),
                "change": idx.get("change", 0), "change_pct": idx.get("change_pct", 0),
            })
    return a_indices, us_indices, a_indices_list, us_indices_list


def _render_category_table(
    holdings: list[Holding], details: list, prog: ProgressReporter,
) -> tuple[list[dict[str, Any]], bool]:
    """构建持仓分类表数据。

    Returns:
        (cat_data, dividend_success)
    """
    prog.info("正在生成持仓分类表...")
    cat_data, dividend_success = _build_category_data(holdings, details)
    return cat_data, dividend_success


def _render_penetration_section(
    holdings: list[Holding], details: list, prog: ProgressReporter,
) -> tuple[dict | None, bool, bool]:
    """计算资产穿透TOP10，附加盈利预测和股息率。

    Returns:
        (pen_result, profit_success, dividend_success)
    """
    prog.info("正在计算资产穿透TOP10...")
    pen_result = compute_penetration_top10(holdings, details)
    if not pen_result or not pen_result.get("top10"):
        return pen_result, True, True

    # 加载盈利预测（独立 try）
    profit_success = True
    profit_forecast: dict[str, dict] = {}
    try:
        from src.python.providers.akshare_extras import get_profit_forecast
        profit_forecast = get_profit_forecast()
        if not profit_forecast:
            profit_success = False
            logger.warning("[penetration] 盈利预测数据为空（API 返回空结果），EPS 列将显示 --")
    except Exception:
        profit_success = False
        logger.warning("[penetration] 盈利预测加载异常（非关键），EPS 列显示 --", exc_info=True)

    # 加载股息率（独立 try）
    dividend_success = True
    dividend_data: dict[str, dict] = {}
    try:
        from src.python.code_utils import is_a_share_code
        from src.python.providers.akshare_extras import get_dividend_data
        all_codes = list(set().union(*(e.get("codes", []) for e in pen_result["top10"])))
        a_codes = [c for c in all_codes if is_a_share_code(c)]
        dividend_data = get_dividend_data(a_codes) if a_codes else {}
        if not dividend_data and a_codes:
            dividend_success = False
            logger.warning("[penetration] 股息率数据为空（API 返回空结果）")
    except Exception:
        dividend_success = False
        logger.warning("[penetration] 股息率加载异常（非关键），股息率列显示 --", exc_info=True)

    for entry in pen_result["top10"]:
        codes = entry.get("codes", [])
        # EPS
        eps_text = "--"
        for c in codes:
            info = profit_forecast.get(c)
            if info and info.get("eps_2026e") is not None:
                eps_text = f"¥{info['eps_2026e']:.2f}"
                break
        entry["eps_text"] = eps_text
        # 股息率
        div_text = "--"
        for c in codes:
            info = dividend_data.get(c)
            if info and info.get("avg_dividend"):
                div_text = f"{info['avg_dividend']:.4f}元/年"
                break
        entry["dividend_text"] = div_text

    return pen_result, profit_success, dividend_success


def _render_fund_performance_section(
    holdings: list[Holding], details: list, prog: ProgressReporter,
) -> tuple[list[dict[str, Any]], bool]:
    """构建基金业绩分析数据。

    Returns:
        (perf_data, profit_success) — profit_success 表示盈利预测数据是否加载成功
    """
    prog.info("正在获取基金业绩排名...")
    perf_data = _build_perf_data(holdings, details, progress=prog)
    try:
        from src.python.report.html_builders import _load_profit_forecast
        profit_success = bool(_load_profit_forecast())
    except Exception:
        profit_success = False
    return perf_data, profit_success


def _render_manager_analysis(
    holdings: list[Holding], enable_b_series: bool, prog: ProgressReporter,
) -> dict | None:
    """构建基金经理变更监控数据。

    Returns:
        {results: [...], first_check_summary: str | None} 或 None（不启用时）
    """
    if not enable_b_series:
        return None
    prog.info("正在分析基金经理变更...")
    try:
        results = detect_manager_changes(holdings)
        if not results:
            return {"results": [], "first_check_summary": None}
        summary = build_first_check_summary(results) if any(r.get("is_first_check") for r in results) else None
        prog.ok("基金经理变更分析完成")
        return {"results": results, "first_check_summary": summary}
    except Exception as e:
        logger.warning("基金经理变更分析失败: %s", e)
        return {"results": [], "first_check_summary": None}


def _render_overlap_matrix(
    holdings: list[Holding],
    details: list,
    enable_b_series: bool,
    prog: ProgressReporter,
) -> dict | None:
    """构建持仓重合度矩阵数据。

    Returns:
        compute_overlap_matrix() 的结果字典，或 None（不启用时）
    """
    if not enable_b_series:
        return None
    prog.info("正在计算持仓重合度矩阵...")
    try:
        fund_codes = list(dict.fromkeys(
            h.code for h in holdings if _is_fund(h)
        ))
        if len(fund_codes) < 2:
            return {"funds": [], "fund_names": {}, "matrix": [], "pairs": [], "has_mv_data": False}

        fund_holdings: dict[str, list[dict]] = {}
        fund_names: dict[str, str] = {}
        for code in fund_codes:
            fh = fetch_fund_holdings(code)
            if fh and fh.get("holdings"):
                fund_holdings[code] = fh["holdings"]
                fund_names[code] = fh.get("name", code)

        if len(fund_holdings) < 2:
            return {"funds": [], "fund_names": {}, "matrix": [], "pairs": [], "has_mv_data": False}

        fund_mv_map: dict[str, float] = {}
        for d in details:
            if d.code in fund_codes:
                fund_mv_map[d.code] = fund_mv_map.get(d.code, 0.0) + d.market_value

        result = compute_overlap_matrix(fund_holdings, fund_mv_map=fund_mv_map if fund_mv_map else None)
        result["fund_names"] = fund_names
        prog.ok("持仓重合度矩阵计算完成")
        return result
    except Exception as e:
        logger.warning("持仓重合度矩阵计算失败: %s", e)
        return {"funds": [], "fund_names": {}, "matrix": [], "pairs": [], "has_mv_data": False}


def _render_concentration(
    holdings: list[Holding],
    enable_b_series: bool,
    prog: ProgressReporter,
) -> dict | None:
    """构建持仓集中度监控数据。

    Returns:
        {results: [...], ...} 或 None（不启用时）
    """
    if not enable_b_series:
        return None
    prog.info("正在计算持仓集中度...")
    try:
        fund_codes = list(dict.fromkeys(
            h.code for h in holdings if _is_fund(h)
        ))
        fund_holdings: dict[str, dict] = {}
        for code in fund_codes:
            fh = fetch_fund_holdings(code)
            if fh and fh.get("holdings"):
                fund_holdings[code] = {
                    "name": fh.get("name", code),
                    "holdings": fh["holdings"],
                }
        if not fund_holdings:
            return {"results": []}
        results = compute_concentration(fund_holdings)
        prog.ok("持仓集中度计算完成")
        return {"results": results}
    except Exception as e:
        logger.warning("持仓集中度计算失败: %s", e)
        return {"results": []}


def _render_style_analysis(
    holdings: list[Holding],
    enable_b_series: bool,
    prog: ProgressReporter,
) -> dict | None:
    """构建基金风格分析数据。

    Returns:
        {results: [...], ...} 或 None（不启用时）
    """
    if not enable_b_series:
        return None
    prog.info("正在分析基金风格漂移...")
    try:
        fund_codes = list(dict.fromkeys(
            h.code for h in holdings if _is_fund(h)
        ))
        fund_holdings: dict[str, dict] = {}
        for code in fund_codes:
            fh = fetch_fund_holdings(code)
            if fh and fh.get("holdings"):
                fund_holdings[code] = {
                    "name": fh.get("name", code),
                    "holdings": fh["holdings"],
                }
            else:
                _name = fh.get("name", code) if fh else code
                logger.debug("基金风格分析跳过（无持仓数据）: %s (%s)", _name, code)
        if not fund_holdings:
            return {"results": []}
        result = analyze_style_for_all_funds(fund_holdings)
        prog.ok("基金风格分析完成")
        return result
    except Exception as e:
        logger.warning("基金风格分析失败: %s", e)
        return {"results": []}


def _render_news_section(
    include_news: bool,
    news_data: list | None,
    news_llm_meta: dict | None,
    holdings: list[Holding],
    news_top_count: int,
    penetration: dict | None,
    prog: ProgressReporter,
) -> tuple[list, dict]:
    """财经新闻热点与持仓关联分析数据。

    Returns:
        (news_data, news_llm_meta)
    """
    _default_meta = {"llm_enabled": False, "llm_cached": False, "token_usage": {},
                     "cost_estimation": "-", "thinking_enabled": False}
    if not include_news:
        return [], _default_meta

    if news_data is not None:
        logger.info("复用调用方传入的新闻数据，共 %d 条", len(news_data))
        return news_data, news_llm_meta or _default_meta

    prog.info("正在获取财经新闻...")
    try:
        penetrated_assets = penetration.get("top10", []) if penetration else []
        from src.python.report.news_correlation import build_news_data
        news_data, _news_llm_meta = build_news_data(
            holdings, top_n=news_top_count, penetrated_assets=penetrated_assets)
        if not news_data:
            news_data = []
            logger.info("财经新闻热点与持仓关联分析：无数据")
        else:
            logger.info("财经新闻热点与持仓关联分析完成，%d 条", len(news_data))
        return news_data, _news_llm_meta
    except Exception as e:
        logger.warning("新闻获取失败: %s", e)
        return [], _default_meta


def _render_llm_content_section(
    enable_llm: bool,
    llm_content: tuple | None,
    force_llm: bool,
    a_indices: dict,
    us_indices: dict,
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings: list[Holding],
    cat_counts: dict[str, int],
    penetration: dict | None,
    details: list,
    sector_flow: list | None,
    prog: ProgressReporter,
) -> tuple[bool, str | None, str | None, str | None, str | None]:
    """LLM 智能分析内容生成。

    Returns:
        (llm_enabled_flag, global_macro, expert_review, health_check, penetration_deep)
    """
    if llm_content is not None:
        gm, er, hc, pd = llm_content
        return (bool(gm or er or hc or pd), gm, er, hc, pd)

    if not enable_llm:
        return False, None, None, None, None

    prog.info("正在调用 LLM 生成智能分析...")
    try:
        from src.python.llm import generate_all_llm
        pen_top10 = penetration.get("top10", []) if penetration else []
        _holdings_details = [
            {
                "name": d.name, "code": d.code,
                "market_value": d.market_value, "cost": d.cost,
                "profit": d.profit, "profit_rate": d.profit_rate,
                "change_pct": (
                    (d.price - d.yesterday_close) / d.yesterday_close * 100
                    if d.yesterday_close and abs(d.yesterday_close) > 1e-10 else 0.0),
            } for d in details
        ]
        from src.python.providers.akshare_extras import get_sector_fund_flow
        _sector_flow = sector_flow if sector_flow is not None else get_sector_fund_flow()

        gm, er, hc, pd, _, _, _, _ = generate_all_llm(
            a_indices, us_indices, total_mv, total_cost, total_profit,
            total_today_profit, len(holdings), cat_counts,
            penetrated_assets=pen_top10, holdings_details=_holdings_details,
            sector_flow=_sector_flow, force=force_llm,
        )
        enabled = False
        if gm:
            enabled = True; logger.info("%s LLM 生成完成", get_llm_module_name("global_macro"))
        if er:
            enabled = True; logger.info("%s LLM 生成完成", get_llm_module_name("expert_review"))
        if hc:
            enabled = True; logger.info("%s LLM 生成完成", get_llm_module_name("health_check"))
        if pd:
            enabled = True; logger.info("%s LLM 生成完成", get_llm_module_name("penetration_deep"))
        return enabled, gm, er, hc, pd
    except Exception as e:
        logger.warning("LLM 生成失败: %s", e)
        return False, None, None, None, None


def _build_module_info_list(
    llm_failure: dict,
    per_module: dict,
) -> list[dict[str, Any]]:
    """构建 LLM 模块信息列表（状态、Token 用量、费用等）。"""
    try:
        from src.python.llm import (
            FAIL_REASON_API_ERROR,
            FAIL_REASON_CIRCUIT_OPEN,
            FAIL_REASON_DISABLED,
            FAIL_REASON_NETWORK_ERROR,
            FAIL_REASON_NOT_CONFIGURED,
            FAIL_REASON_TIMEOUT,
        )
    except ImportError:
        FAIL_REASON_DISABLED = FAIL_REASON_NOT_CONFIGURED = "disabled"
        FAIL_REASON_API_ERROR = FAIL_REASON_NETWORK_ERROR = FAIL_REASON_TIMEOUT = FAIL_REASON_CIRCUIT_OPEN = "error"

    _NAMES = get_llm_module_names()
    _DISPLAY_REASON = {
        FAIL_REASON_NOT_CONFIGURED: "LLM 未配置",
        FAIL_REASON_API_ERROR: "LLM API 调用失败",
        FAIL_REASON_NETWORK_ERROR: "LLM API 网络连接失败",
        FAIL_REASON_TIMEOUT: "LLM API 请求超时",
        FAIL_REASON_CIRCUIT_OPEN: "LLM API 暂时不可用（熔断冷却中）",
    }

    _MODULE_KEYS = ["global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation"]
    llm_module_info: list[dict[str, Any]] = []
    for mk in _MODULE_KEYS:
        entry: dict[str, Any] = {"key": mk, "name": _NAMES.get(mk, mk)}
        reason = llm_failure.get(mk)
        pm = per_module.get(mk)
        if reason == FAIL_REASON_DISABLED:
            entry.update(status="disabled", status_label="已禁用",
                         model="", input_tokens=0, output_tokens=0, total_tokens=0,
                         cache_hit_tokens=0, cost=0.0, cached=False, thinking=False, endpoint="")
        elif reason:
            entry.update(status="failed", status_label=_DISPLAY_REASON.get(reason, reason),
                         model="", input_tokens=0, output_tokens=0, total_tokens=0,
                         cache_hit_tokens=0, cost=0.0, cached=False, thinking=False, endpoint="")
        elif pm:
            _inp = pm.get("input_tokens", 0)
            _out = pm.get("output_tokens", 0)
            entry.update(
                status="cached" if pm.get("cached") else "success",
                status_label="缓存" if pm.get("cached") else "成功",
                model=pm.get("model", ""), input_tokens=_inp, output_tokens=_out,
                total_tokens=_inp + _out, cache_hit_tokens=pm.get("cache_hit_tokens", 0),
                cost=pm.get("cost", 0.0), cached=pm.get("cached", False),
                thinking=pm.get("thinking", False), endpoint=pm.get("endpoint", ""),
            )
        else:
            entry.update(status="unknown", status_label="",
                         model="", input_tokens=0, output_tokens=0, total_tokens=0,
                         cache_hit_tokens=0, cost=0.0, cached=False, thinking=False, endpoint="")
        llm_module_info.append(entry)
    return llm_module_info


def _render_llm_module_info(
    llm_enabled_flag: bool,
) -> tuple[list[dict[str, Any]], str, dict[str, bool], dict | None]:
    """收集 LLM 模块状态并合并模块明细。

    Returns:
        (llm_module_info, llm_endpoint, module_disabled, llm_session_usage)
    """
    _llm_session_usage = None
    if llm_enabled_flag:
        try:
            from src.python.llm import format_session_usage, get_session_usage
            _llm_session_usage = format_session_usage(get_session_usage())
        except (ImportError, TypeError, AttributeError):
            logger.debug("获取 LLM 会话用量失败（非关键）")

    _llm_failure = {}
    _per_module: dict[str, Any] = {}
    from src.python.llm import FAIL_REASON_DISABLED as _FAIL_REASON_DISABLED_IMPORT
    FAIL_REASON_DISABLED: str | None = _FAIL_REASON_DISABLED_IMPORT
    try:
        from src.python.llm.prompts import _LLM_MODULE_FAILURE
        _llm_failure = dict(_LLM_MODULE_FAILURE)
    except ImportError:
        logger.info("llm/session 模块未就绪，略过用量统计")
    if _llm_session_usage:
        _per_module = _llm_session_usage.get("per_module", {}) or {}

    module_disabled = {
        mk: _llm_failure.get(mk) == FAIL_REASON_DISABLED
        for mk in ["global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation"]}

    llm_module_info = _build_module_info_list(_llm_failure, _per_module)

    _llm_endpoint = next((mi["endpoint"] for mi in llm_module_info if mi.get("endpoint")), "")
    return llm_module_info, _llm_endpoint, module_disabled, _llm_session_usage

# ── 桥接 import：Step 1 外迁后保留向后兼容 ──────────────────
from src.python.report.html_save import _save_html_report  # noqa: E402, F401
