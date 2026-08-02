"""HTML 报告内容渲染函数 — 数据获取 + 子章节渲染。"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.code_utils import is_a_share_code
from src.python.fetcher.akshare import get_dividend_data, get_profit_forecast
from src.python.fetcher.fund import fetch_fund_holdings_cached
from src.python.fetcher.index import fetch_indices, fetch_us_indices
from src.python.core.models import Holding
from src.python.report.fund_concentration import compute_concentration
from src.python.report.fund_manager_analysis import build_first_check_summary, detect_manager_changes
from src.python.report.fund_overlap import compute_overlap_matrix
from src.python.report.fund_performance import is_fund
from src.python.report.fund_style_report import analyze_style_for_all_funds
from src.python.report.html_builders import _build_category_data, _build_perf_data
from src.python.report.llm_module_info import build_llm_module_info
from src.python.report.market_value import (
    DetailRow,
    _generate_details,
    classify_holdings,
    price_update_status,
)
from src.python.report.penetration import compute_penetration_top10
from src.python.report.progress import ProgressReporter

logger = logging.getLogger("invest")


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
            "market_value": acc_mv,
            "cost": acc_cost,
            "profit": acc_profit,
            "profit_rate": acc_rate,
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
    pre_fetched_a: dict | None = None,
    pre_fetched_us: dict | None = None,
) -> tuple[dict, dict, list[dict[str, Any]], list[dict[str, Any]]]:
    """获取市场指数并转为模板可迭代列表。

    支持传入预获取的指数数据（来自 _prepare_report_data），
    避免同一流程中重复 HTTP 请求。

    Returns:
        (a_indices, us_indices, a_indices_list, us_indices_list)
    """
    if pre_fetched_a is not None and pre_fetched_us is not None:
        a_indices = pre_fetched_a
        us_indices = pre_fetched_us
    else:
        prog.info("正在获取市场指数...")
        a_indices = fetch_indices()
        us_indices = fetch_us_indices()

    a_indices_list: list[dict[str, Any]] = []
    for code in ("sh000001", "sz399001", "sh000300", "sh000688", "sz399006"):
        idx = a_indices.get(code)
        if idx:
            a_indices_list.append(
                {
                    "name": idx.get("name", ""),
                    "price": idx.get("price", 0),
                    "change": idx.get("change", 0),
                    "change_pct": idx.get("change_pct", 0),
                }
            )

    us_indices_list: list[dict[str, Any]] = []
    for code in ("gb_dji", "gb_ixic", "gb_inx"):
        idx = us_indices.get(code)
        if idx:
            us_indices_list.append(
                {
                    "name": idx.get("name", ""),
                    "price": idx.get("price", 0),
                    "change": idx.get("change", 0),
                    "change_pct": idx.get("change_pct", 0),
                }
            )
    return a_indices, us_indices, a_indices_list, us_indices_list


def _render_category_table(
    holdings: list[Holding],
    details: list,
    prog: ProgressReporter,
) -> tuple[list[dict[str, Any]], bool]:
    """构建持仓分类表数据。

    Returns:
        (cat_data, dividend_success)
    """
    prog.info("正在生成持仓分类表...")
    cat_data, dividend_success = _build_category_data(holdings, details)
    return cat_data, dividend_success


def _render_penetration_section(
    holdings: list[Holding],
    details: list,
    prog: ProgressReporter,
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
    holdings: list[Holding],
    details: list,
    prog: ProgressReporter,
) -> tuple[list[dict[str, Any]], bool]:
    """构建基金业绩分析数据。

    Returns:
        (perf_data, True) — 第二项为固定值
    """
    prog.info("正在获取基金业绩排名...")
    perf_data = _build_perf_data(holdings, details, progress=prog)
    return perf_data, True


def _render_manager_analysis(
    holdings: list[Holding],
    enable_fund_deep_analysis: bool,
    prog: ProgressReporter,
) -> dict | None:
    """构建基金经理变更监控数据。

    Returns:
        {results: [...], first_check_summary: str | None} 或 None（不启用时）
    """
    if not enable_fund_deep_analysis:
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
    enable_fund_deep_analysis: bool,
    prog: ProgressReporter,
) -> dict | None:
    """构建持仓重合度矩阵数据。

    Returns:
        compute_overlap_matrix() 的结果字典，或 None（不启用时）
    """
    if not enable_fund_deep_analysis:
        return None
    prog.info("正在计算持仓重合度矩阵...")
    try:
        fund_codes = list(dict.fromkeys(h.code for h in holdings if is_fund(h)))
        if len(fund_codes) < 2:
            return {"funds": [], "fund_names": {}, "matrix": [], "pairs": [], "has_mv_data": False}

        fund_holdings: dict[str, list[dict]] = {}
        fund_names: dict[str, str] = {}
        for code in fund_codes:
            fh = fetch_fund_holdings_cached(code)
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
    enable_fund_deep_analysis: bool,
    prog: ProgressReporter,
) -> dict | None:
    """构建持仓集中度监控数据。

    Returns:
        {results: [...], ...} 或 None（不启用时）
    """
    if not enable_fund_deep_analysis:
        return None
    prog.info("正在计算持仓集中度...")
    try:
        fund_codes = list(dict.fromkeys(h.code for h in holdings if is_fund(h)))
        fund_holdings: dict[str, dict] = {}
        for code in fund_codes:
            fh = fetch_fund_holdings_cached(code)
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
    enable_fund_deep_analysis: bool,
    prog: ProgressReporter,
) -> dict | None:
    """构建基金风格分析数据。

    Returns:
        {results: [...], ...} 或 None（不启用时）
    """
    if not enable_fund_deep_analysis:
        return None
    prog.info("正在分析基金风格漂移...")
    try:
        fund_codes = list(dict.fromkeys(h.code for h in holdings if is_fund(h)))
        fund_holdings: dict[str, dict] = {}
        for code in fund_codes:
            fh = fetch_fund_holdings_cached(code)
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
    _default_meta = {
        "llm_enabled": False,
        "llm_cached": False,
        "token_usage": {},
        "cost_estimation": "-",
        "thinking_enabled": False,
    }
    if not include_news:
        return [], _default_meta

    if news_data is not None:
        logger.info("复用调用方传入的新闻数据，共 %d 条", len(news_data))
        return news_data, news_llm_meta or _default_meta

    prog.info("正在获取财经新闻...")
    try:
        penetrated_assets = penetration.get("top10", []) if penetration else []
        from src.python.report.news_correlation import build_news_data

        news_data, _news_llm_meta = build_news_data(holdings, top_n=news_top_count, penetrated_assets=penetrated_assets)
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

    # 注意：此路径不应在正常情况下触发——orchestrator 始终预生成 llm_content
    # 后传入 write_html_report()，enable_llm=True 时 llm_content 不应为 None。
    # 兜底路径：orchestrator 未预生成 llm_content 时返回空值并记录告警。
    logger.warning(
        "_render_llm_content_section: llm_content 未预生成（enable_llm=True），LLM 内容应通过 orchestrator 预生成后传入"
    )
    return False, None, None, None, None


# ── LLM 模块状态 ────────────────────────────────────────────


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
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        _llm_failure = dict(LLM_MODULE_FAILURE)
    except ImportError:
        logger.info("llm/session 模块未就绪，略过用量统计")
    if _llm_session_usage:
        _per_module = _llm_session_usage.get("per_module", {}) or {}

    module_disabled = {
        mk: _llm_failure.get(mk) == FAIL_REASON_DISABLED
        for mk in ["global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation"]
    }

    llm_module_info = build_llm_module_info(_llm_failure, _per_module)

    _llm_endpoint = next((mi["endpoint"] for mi in llm_module_info if mi.get("endpoint")), "")
    return llm_module_info, _llm_endpoint, module_disabled, _llm_session_usage
