"""HTML 报告生成引擎 — 将持仓分析数据渲染为 HTML 报告。

调用现有的计算模块获取所有分析数据，通过 Jinja2 模板
渲染为完整的单页 HTML 报告，支持最新版和归档版双重输出。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.cache import get_cache_hit_rate
from src.python.constants import APP_VERSION
from src.python.models import Holding
from src.python.registry import get_llm_module_names, get_report_section_order
from src.python.report.category import _build_category_data_status
from src.python.report.data_status import DataStatus
from src.python.report.market_value import get_last_trading_day
from src.python.report.fund_performance import _build_perf_data_status, _is_fund
from src.python.report.penetration_sheet import _build_penetration_data_status
from src.python.report.progress import ProgressReporter, SilentProgressReporter
from src.python.report.summary import _build_index_data_status

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  文件导览
# ═══════════════════════════════════════════════════════════════
#
#   _ENV + 过滤器                  → html_jinja_env.py
#   14 渲染函数 + LLM 模块信息    → html_renderers.py
#   _save_html_report              → html_save.py
#   辅助函数                      _safe_build_data_status, _time_strings,
#                                  _compute_section_visibility,
#                                  _build_data_status_sections
#   核心生成函数                  write_html_report()
#   桥接 import（子渲染器 + 读写器）
#
# ═══════════════════════════════════════════════════════════════

# ── 桥接 import：_ENV + 过滤器已在 html_jinja_env.py ────────
from src.python.report.html_jinja_env import _ENV  # noqa: E402

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


def _time_strings() -> tuple[str, str, str]:
    """返回 (now_str, today_str, trading_day)。"""
    return (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        datetime.now().strftime("%Y-%m-%d"),
        get_last_trading_day(),
    )


def _compute_section_visibility(
    order: list[dict],
    manager_analysis: dict | None,
    overlap_matrix: dict | None,
    concentration_analysis: dict | None,
    style_analysis: dict | None,
    include_news: bool,
    early_warnings: dict | None,
    llm_enabled_flag: bool,
) -> tuple[dict[str, int], dict[str, bool], Any]:
    """计算报告模块序号 + 可见性字典 + 闭包函数。

    根据各模块返回的数据状态决定 section 是否可见，
    返回的闭包遵守 C14 约束（不写入 _ENV.globals）。
    """
    section_numbers = {sec["key"]: sec["number"] for sec in order}
    raw_data_flags: dict[str, bool] = {
        "manager_data": manager_analysis is not None,
        "overlap_data": overlap_matrix is not None,
        "concentration_data": concentration_analysis is not None,
        "style_data": style_analysis is not None,
        "include_news": include_news,
        "early_warnings": bool(early_warnings),
        "llm_enabled": llm_enabled_flag,
    }
    section_visible_dict: dict[str, bool] = {}
    for sec in order:
        flag_name = sec.get("data_flag")
        if not flag_name:
            section_visible_dict[sec["key"]] = True
        else:
            section_visible_dict[sec["key"]] = raw_data_flags.get(flag_name, False)
    # 创建渲染期 section_visible 闭包（不写入 _ENV.globals，遵守 C14 约束）
    _sv_fn = lambda key, _d=section_visible_dict: bool(_d.get(key, False))
    return section_numbers, section_visible_dict, _sv_fn


def _build_data_status_sections(
    a_indices: dict,
    us_indices: dict,
    penetration: dict | None,
    penetration_profit_ok: bool,
    penetration_dividend_ok: bool,
    perf_data: list[dict] | None,
    perf_profit_ok: bool,
    holdings: list[Holding],
    cat_dividend_ok: bool,
) -> tuple[DataStatus, DataStatus, DataStatus, DataStatus]:
    """构建 4 个 data_status 摘要字典（指数/穿透/基金业绩/持仓分类）。

    各模块的 data_status 构建互相独立，任一模块失败不影响其他。
    """
    data_status_summary: DataStatus = _safe_build_data_status(
        _build_index_data_status, a_indices, us_indices, label="指数")
    data_status_penetration: DataStatus = {}
    if penetration:
        data_status_penetration = _safe_build_data_status(
            _build_penetration_data_status, penetration,
            penetration_profit_ok, penetration_dividend_ok, label="穿透")
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
        profit_success=perf_profit_ok, label="基金业绩")
    data_status_category: DataStatus = _safe_build_data_status(
        _build_category_data_status, cat_dividend_ok, label="持仓分类")
    return data_status_summary, data_status_penetration, data_status_perf, data_status_category


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

    # ── 10a) 报告模块序号 & 可见性 ──
    order = section_order or get_report_section_order()
    section_numbers, section_visible_dict, _sv_fn = _compute_section_visibility(
        order, manager_analysis, overlap_matrix, concentration_analysis,
        style_analysis, include_news, early_warnings, llm_enabled_flag)

    # ── 10b) 数据源状态摘要 ──
    (data_status_summary, data_status_penetration,
     data_status_perf, data_status_category) = _build_data_status_sections(
        a_indices, us_indices, penetration, penetration_profit_ok,
        penetration_dividend_ok, perf_data, perf_profit_ok, holdings,
        cat_dividend_ok)

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
        # PF 修复：section_visible 函数由 context 变量传入，不写入 _ENV.globals
        section_visible=_sv_fn,
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


# ── 桥接 import：已迁出的子模块 ─────────────────────────────
from src.python.report.html_renderers import (  # noqa: E402, F401
    _render_market_value_section,
    _render_account_grouping,
    _render_category_info,
    _render_index_section,
    _render_category_table,
    _render_penetration_section,
    _render_fund_performance_section,
    _render_manager_analysis,
    _render_overlap_matrix,
    _render_concentration,
    _render_style_analysis,
    _render_news_section,
    _render_llm_content_section,
    _render_llm_module_info,
)
from src.python.report.html_save import _save_html_report  # noqa: E402, F401
