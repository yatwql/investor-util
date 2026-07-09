"""HTML 报告内容渲染函数 — 数据获取 + 子章节渲染。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.cache import get_cache_hit_rate
from src.python.code_utils import is_a_share_code
from src.python.constants import APP_VERSION
from src.python.fetcher.fund import fetch_fund_holdings
from src.python.fetcher.index import fetch_indices, fetch_us_indices
from src.python.models import Holding
from src.python.provider_registry import _NOT_FOUND, get_registry
from src.python.registry import get_llm_module_name, get_llm_module_names
from src.python.report.fund_concentration import compute_concentration
from src.python.report.fund_manager_analysis import build_first_check_summary, detect_manager_changes
from src.python.report.fund_overlap import compute_overlap_matrix
from src.python.report.fund_performance import _is_fund
from src.python.report.fund_style_analysis import analyze_style_for_all_funds
from src.python.report.html_builders import _build_category_data, _build_perf_data, _load_profit_forecast
from src.python.report.market_value import (
    DetailRow,
    _generate_details,
    classify_holdings,
    get_last_trading_day,
    price_update_status,
)
from src.python.report.penetration import compute_penetration_top10
from src.python.report.progress import ProgressReporter
from src.python.providers.akshare_extras import get_dividend_data, get_profit_forecast

logger = logging.getLogger("invest")


def _fetch_fund_holdings_cached(code: str) -> dict | None:
    """基金持仓获取（含会话缓存），同一报告生成中同基金只获取一次。

    消除 _render_overlap_matrix / _render_concentration / _render_style_analysis
    三函数独立调用 fetch_fund_holdings 的冗余文件缓存读取。
    """
    registry = get_registry()
    cached = registry.session_cache_get("fund_hold", code)
    if cached is not _NOT_FOUND:
        return cached
    result = fetch_fund_holdings(code)
    registry.session_cache_set("fund_hold", code, result, source="api")
    return result


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
    return details, (total_mv, total_cost, total_profit, total_today_profit,
                     total_profit_rate, today_profit_rate)


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
    holdings: list[Holding], details: list, prog: ProgressReporter,
) -> tuple[list[dict[str, Any]], bool]:
    """构建基金业绩分析数据。

    Returns:
        (perf_data, profit_success) — profit_success 表示盈利预测数据是否加载成功
    """
    prog.info("正在获取基金业绩排名...")
    perf_data = _build_perf_data(holdings, details, progress=prog)
    try:
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
            fh = _fetch_fund_holdings_cached(code)
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
            fh = _fetch_fund_holdings_cached(code)
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
            fh = _fetch_fund_holdings_cached(code)
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


# ── LLM 模块状态 ────────────────────────────────────────────


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
