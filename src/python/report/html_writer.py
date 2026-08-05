"""HTML 报告生成引擎 — 将持仓分析数据渲染为 HTML 报告。

调用现有的计算模块获取所有分析数据，通过 Jinja2 模板
渲染为完整的单页 HTML 报告，支持最新版和归档版双重输出。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from src.python.cache import get_cache_hit_rate
from src.python.core.constants import APP_VERSION
from src.python.core.models import Holding
from src.python.core.registry import get_llm_module_names, get_report_section_order
from src.python.analysis.drawdown_events import MIN_SPAN as DRAW_DOWN_MIN_SPAN
from src.python.report.category import build_category_data_status
from src.python.report.data_status import STATUS_MESSAGES, DataStatus, DataStatusItem
from src.python.report.fund_performance import build_perf_data_status, is_fund
from src.python.report.market_value import get_last_trading_day
from src.python.report.penetration_sheet import build_penetration_data_status
from src.python.report.progress import ProgressReporter, SilentProgressReporter
from src.python.report.summary import build_index_data_status

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
        builder: 状态构建函数（如 build_index_data_status）
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
    llm_enabled_flag: bool,
    # ↓↓↓ board 层新增参数 ↓↓↓
    enable_news: bool = True,  # board 层：市场新闻是否开启（配置驱动，不是 include_news！）
    enable_fund_deep_analysis: bool = True,  # board 层：基金深度分析是否开启
    enable_history: bool = True,  # board 层：历史走势章节是否开启
    enable_portfolio_evolution: bool = True,  # board 层：组合演进章节是否开启
    enable_action: bool = False,  # board 层：行动建议章节是否开启（默认关）
    enable_llm: bool = True,  # board 层：LLM 分析章节是否开启
    style_factor_data: dict | None = None,  # data 层：风格与因子 dict（None=无数据，章节隐藏）
    position_relationship_data: dict | None = None,  # data 层：持仓关系矩阵 dict（相关性区块数据源）
    evolution_data: dict | None = None,  # data 层：组合演进 dict（None=无数据，章节隐藏）
) -> tuple[dict[str, int], dict[str, bool], Any]:
    """计算报告模块序号 + 可见性字典 + 闭包函数。

    两层可见性模型：
      board 层：用户配置的章节开关（enable_xxx）
      data 层：各子模块返回的数据可用状态

    返回的闭包不写入 _ENV.globals。
    """
    # board 层：内联 dict（与 Excel 端结构一致）
    board_flags: dict[str, bool] = {
        "always": True,
        "fund_deep_analysis": enable_fund_deep_analysis,
        "news": enable_news,  # ← 配置字段（不是 include_news/data 层）
        "history": enable_history,
        "evolution": enable_portfolio_evolution,  # ← board 层：组合演进
        "action": enable_action,  # ← board 层：行动建议（默认关）
        "llm": enable_llm,  # ← board 层
    }
    # data 层：各模块数据就绪状态
    data_flags: dict[str, bool] = {
        "manager_data": manager_analysis is not None,
        "concentration_data": concentration_analysis is not None,
        "style_data": style_analysis is not None,
        "news_data_available": include_news,  # ← data 层（菜单类型+数据状态）
        "llm_data_available": llm_enabled_flag,  # ← data 层（LLM 生成成功？）
        # 风格与因子章可见性：风格表（渲染期派生）或因子数据（数据契约）任一就绪即可见；
        # 模板依据 available/status 在"完整内容/数据不足/数据源暂不可用"间切换（§1.4.5）
        "style_factor_data": style_factor_data is not None or style_analysis is not None,
        # 持仓关系矩阵 = 重合度区块（render 时计算）∪ 相关性区块（数据契约 数据源）：
        # 任一区块有数据即章节可见，区块各自独立降级（§1.4.5）
        "position_relationship_data": overlap_matrix is not None or position_relationship_data is not None,
        # evolution_data 同上：始终由编排层计算注入（非 None）→ 章节可见，
        # available=False 时模板写占位文本（快照不足，§1.4.5）
        "evolution_data": evolution_data is not None,
    }

    # 两层合并：section_visible = board_ok AND data_ok
    section_visible_dict: dict[str, bool] = {}
    for sec in order:
        board_ok = board_flags.get(sec.get("type", ""), True)
        if not board_ok:
            section_visible_dict[sec["key"]] = False
            continue
        flag_name = sec.get("data_flag")
        if not flag_name:
            section_visible_dict[sec["key"]] = True
        else:
            section_visible_dict[sec["key"]] = data_flags.get(flag_name, False)

    # 连续重新编号：基于可见模块分配连续序号，llm_usage 强制末位
    visible_list = [sec for sec in order if section_visible_dict.get(sec["key"], False)]
    llm_sec = [s for s in visible_list if s["key"] == "llm_usage"]
    other_secs = [s for s in visible_list if s["key"] != "llm_usage"]
    ordered_visible = other_secs + llm_sec
    visible_numbers = {sec["key"]: idx for idx, sec in enumerate(ordered_visible, start=1)}

    # 创建渲染期 section_visible 闭包（不写入 _ENV.globals）
    _sv_fn = lambda key, _d=section_visible_dict: bool(_d.get(key, False))
    return visible_numbers, section_visible_dict, _sv_fn


# ── HTML 目录分组导航（「基础/基金深度/风险/历史/LLM」五组，导航折叠收尾） ──

# 分组展示顺序（组名, 组 key），空组不渲染
_NAV_GROUP_LABELS: list[tuple[str, str]] = [
    ("基础", "basic"),
    ("基金深度", "fund_deep"),
    ("风险", "risk"),
    ("历史", "history"),
    ("LLM", "llm"),
]

# 章节 → 分组映射（语义分组；与报告模块注册表 key 一一对应，未知 key 回退「基础」组）
_SECTION_NAV_GROUP_MAP: dict[str, str] = {
    # 基础：汇总/明细/分类/穿透/数据源可用性
    "summary": "basic",
    "market_value": "basic",
    "category": "basic",
    "penetration": "basic",
    "data_source_status": "basic",
    # 基金深度：基金业绩 + 基金深度分析系列章节
    "fund_performance": "fund_deep",
    "fund_manager": "fund_deep",
    "position_relationship": "fund_deep",
    "fund_concentration": "fund_deep",
    "style_factor": "fund_deep",
    # 风险：行动建议（再平衡信号/交易纪律/调仓建议/收益归因）
    "action": "risk",
    # 历史：组合历史走势与回撤 + 组合演进
    "portfolio_history_drawdown": "history",
    "portfolio_evolution": "history",
    # LLM：新闻关联 + LLM 文本分析系列 + API 用量
    "news_correlation": "llm",
    "global_macro": "llm",
    "expert_review": "llm",
    "health_check": "llm",
    "penetration_deep": "llm",
    "llm_usage": "llm",
}

# LLM 支持章节：与「LLM」导航组同源派生（新闻关联 + LLM 文本分析系列 + API 用量），
# 单一数据源防漂移；目录/横向导航据此橙色加粗 + 🧠 图标标记。
_LLM_SUPPORTED_SECTIONS: frozenset[str] = frozenset(
    key for key, group in _SECTION_NAV_GROUP_MAP.items() if group == "llm"
)


def _build_section_nav_groups(
    order: list[dict],
    section_visible,
    section_numbers: dict,
) -> list[dict]:
    """按「基础/基金深度/风险/历史/LLM」五组构建 HTML 目录分组导航数据。

    仅收录当前可见章节；组序固定为五组顺序，组内按报告序号升序。
    返回 [{key, name, sections: [{key, number, name, llm_supported}, ...]}, ...]；
    llm_supported 标记该章节是否有 LLM 支持（与 LLM 导航组同源），模板据此加橙色/图标；
    空组（无可见章节）保留在返回列表中，模板端跳过渲染（无 `<details>`）。
    """
    groups: dict[str, list[dict]] = {gk: [] for _, gk in _NAV_GROUP_LABELS}
    for sec in order:
        key = sec.get("key", "")
        if not section_visible(key):
            continue
        group_key = _SECTION_NAV_GROUP_MAP.get(key, "basic")
        groups.setdefault(group_key, []).append(
            {
                "key": key,
                "number": section_numbers.get(key, 0),
                "name": sec.get("name", key),
                "llm_supported": key in _LLM_SUPPORTED_SECTIONS,
            }
        )
    result: list[dict] = []
    for label, group_key in _NAV_GROUP_LABELS:
        sections = sorted(groups.get(group_key, []), key=lambda s: s["number"])
        result.append({"key": group_key, "name": label, "sections": sections})
    return result


def _build_data_status_sections(
    a_indices: dict,
    us_indices: dict,
    penetration: dict | None,
    penetration_profit_ok: bool,
    penetration_dividend_ok: bool,
    perf_data: list[dict] | None,
    holdings: list[Holding],
    cat_dividend_ok: bool,
) -> tuple[DataStatus, DataStatus, DataStatus, DataStatus]:
    """构建 4 个 data_status 摘要字典（指数/穿透/基金业绩/持仓分类）。

    各模块的 data_status 构建互相独立，任一模块失败不影响其他。
    """
    data_status_summary: DataStatus = _safe_build_data_status(
        build_index_data_status, a_indices, us_indices, label="指数"
    )
    data_status_penetration: DataStatus = {}
    if penetration:
        data_status_penetration = _safe_build_data_status(
            build_penetration_data_status, penetration, penetration_profit_ok, penetration_dividend_ok, label="穿透"
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
        build_perf_data_status, _adj_ratings, sum(1 for h in holdings if is_fund(h)), label="基金业绩"
    )
    data_status_category: DataStatus = _safe_build_data_status(
        build_category_data_status, cat_dividend_ok, label="持仓分类"
    )
    return data_status_summary, data_status_penetration, data_status_perf, data_status_category


def _build_history_data_status(history_data: dict | None) -> DataStatus:
    """从 history_data 构建历史走势数据状态字典。"""
    data_status_history: DataStatus = {}
    if not history_data:
        return data_status_history
    status = history_data.get("status", "unavailable")
    warnings = history_data.get("warnings", [])
    if status == "unavailable":
        data_status_history["history_source"] = DataStatusItem(
            available=False,
            tier="T3",
            message=STATUS_MESSAGES.get("history_price_unavailable", "历史走势数据暂不可用"),
        )
    else:
        if status == "degraded":
            data_status_history["history_degraded"] = DataStatusItem(
                available=True,
                tier="T3",
                message=STATUS_MESSAGES.get("history_degraded", "历史走势部分数据来自降级链路"),
            )
        for w in warnings:
            if "收盘价为 0" in w or "零收盘" in w:
                key = "history_zero_value"
            elif "修正" in w or "重叠" in w:
                key = "history_correction"
            else:
                continue
            data_status_history[key] = DataStatusItem(
                available=True,
                tier="T3",
                message=STATUS_MESSAGES.get(key, w),
            )
    return data_status_history


def _build_flow_display(fund_flow_data: dict | None) -> dict | None:
    """将成本流水数据（fund_flow_data）转成 HTML 模板友好展示映射（per-code 展示值）。

    复用 market_value_sheet._weighted_avg_cost / category._tier_label 计算逻辑，
    避免双实现。无数据或开关关闭时返回 None（模板不渲染成本流水列）。

    Args:
        fund_flow_data: 成本流水数据（None = 开关关闭）

    Returns:
        含 xirr_rate/cost_map/tier_map/div_map/div_total 的展示 dict，或 None
    """
    if not fund_flow_data:
        return None
    from src.python.report.category import _tier_label
    from src.python.report.market_value_sheet import _weighted_avg_cost

    cost_tiers = (fund_flow_data.get("cost_tiers") or {}).get("per_code", {})
    dividends = (fund_flow_data.get("dividends") or {}).get("per_code", {})
    xirr = fund_flow_data.get("xirr") or {}
    return {
        "available": bool(fund_flow_data.get("available")),
        "xirr_rate": xirr.get("rate"),
        "cost_map": {code: _weighted_avg_cost(buckets) for code, buckets in cost_tiers.items()},
        "tier_map": {code: _tier_label(buckets) for code, buckets in cost_tiers.items()},
        "div_map": dict(dividends),
        "div_total": float((fund_flow_data.get("dividends") or {}).get("total", 0.0) or 0.0),
    }


def _build_temperature_display(market_temperature_data: dict | None) -> dict | None:
    """将市场温度数据契约（market_temperature_data）转成 HTML 模板友好展示映射。

    Args:
        market_temperature_data: 市场温度数据契约（None = 开关关闭）。

    Returns:
        含 available/score/tier/components/index_name/disclaimer 的展示 dict，或 None。
    """
    from src.python.analysis.market_temperature import TEMPERATURE_DISCLAIMER

    if not market_temperature_data:
        return None
    if not market_temperature_data.get("available"):
        return {
            "available": False,
            "score": None,
            "tier": None,
            "components": None,
            "index_name": market_temperature_data.get("index_name") or "沪深300",
            "disclaimer": market_temperature_data.get("disclaimer") or TEMPERATURE_DISCLAIMER,
        }
    pct = market_temperature_data.get("price_percentile")
    dev = market_temperature_data.get("ma_deviation")
    vol = market_temperature_data.get("volatility")
    components = None
    if all(v is not None for v in (pct, dev, vol)):
        # 分位为 0~100，均线偏离/波动率为小数比例（0.032=3.2%），转百分数展示
        components = {
            "price_percentile": f"{pct:.1f}%",
            "ma_deviation": f"{dev * 100:+.1f}%",
            "volatility": f"{vol * 100:.1f}%",
        }
    return {
        "available": True,
        "score": market_temperature_data.get("score"),
        "tier": market_temperature_data.get("tier") or "合理",
        "components": components,
        "index_name": market_temperature_data.get("index_name") or "沪深300",
        "disclaimer": market_temperature_data.get("disclaimer") or TEMPERATURE_DISCLAIMER,
    }


def _attach_valuation_to_penetration(
    penetration: dict | None,
    valuation_data: dict | None,
) -> dict | None:
    """为穿透 TOP10 数据附加估值分位文本（返回新 dict，不修改原对象）。

    Args:
        penetration: 穿透 TOP10 数据（含 top10/summary）。
        valuation_data: 估值分位数据契约；None 时原样返回（不附加列）。

    Returns:
        新 penetration dict（每个 top10 条目增加 valuation_text 字段），
        或原 penetration（valuation_data 为 None）。
    """
    if not valuation_data or not penetration:
        return penetration
    from src.python.report.penetration_sheet import _get_valuation_text

    display = dict(penetration)
    top10 = []
    for entry in display.get("top10", []):
        e = dict(entry)
        e["valuation_text"] = _get_valuation_text(valuation_data, entry.get("codes", []))
        top10.append(e)
    display["top10"] = top10
    return display


def _render_template(
    *,
    now_str: str,
    today_str: str,
    trading_day: str,
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_profit_rate: float,
    total_today_profit: float,
    today_profit_rate: float,
    cat_counts: dict,
    update_status_dict: dict,
    a_indices_list: list,
    us_indices_list: list,
    accounts: list,
    account_totals: list,
    cat_data: list,
    penetration: dict,
    perf_data: list,
    candidate_data: dict | None,
    news_data: list,
    _news_llm_meta: dict | None,
    has_llm_analysis: bool,
    manager_analysis: dict,
    overlap_matrix: dict,
    concentration_analysis: dict,
    style_analysis: dict,
    llm_enabled_flag: bool,
    global_macro_content: str | None,
    expert_review_content: str | None,
    health_check_content: str | None,
    penetration_deep_content: str | None,
    _llm_session_usage: dict,
    _llm_module_info: list,
    llm_endpoint: str | None,
    module_disabled: list,
    _debate_mode_label: str,
    debate_info: dict | None,
    _debate_mode_combination: str,
    order: list,
    section_numbers: dict,
    section_visible_dict: dict,
    _sv_fn,
    data_status_summary: DataStatus,
    data_status_penetration: DataStatus,
    data_status_perf: DataStatus,
    data_status_category: DataStatus,
    history_data: dict | None,
    data_status_history: DataStatus,
    data_source_matrix: dict,
    chart_datasets: dict | None = None,
    enable_interactive_charts: bool = False,
    style_factor_data: dict | None = None,
    factor_names: dict | None = None,
    industry_beta: dict | None = None,
    position_relationship_data: dict | None = None,
    evolution_data: dict | None = None,
    drawdown_min_span: int = DRAW_DOWN_MIN_SPAN,
    data_quality_enabled: bool = False,  # 子模块：数据质量仪表盘开关
    position_status: dict | None = None,  # 品种覆盖诊断 position_status
    data_freshness: dict | None = None,  # 可信度摘要 data_freshness
    action_data: dict | None = None,  # 行动建议单一数据源 action_data（行动板块 + 智囊团深度复盘行动摘要）
    crisis_annotation_data: dict | None = None,  # 危机区间标注 crisis_annotation_data
    tail_risk_data: dict | None = None,  # 尾部风险统计 tail_risk_data（指标卡）
    snapshot_diff_data: dict | None = None,  # 快照差异摘要 snapshot_diff_data（组合演进章顶部）
    fund_flow_data: dict | None = None,  # 成本流水数据 fund_flow_data（三页签 HTML 渲染数据源）
    valuation_data: dict | None = None,  # 估值分位数据契约 valuation_data（穿透估值列，None=开关关闭）
    market_temperature_data: dict
    | None = None,  # 市场温度数据契约 market_temperature_data（汇总温度行，None=开关关闭）
) -> str:
    """渲染 Jinja2 模板并返回 HTML。"""
    from src.python.report.chart_data_builder import build_evolution_chart_data

    # 估值分位 + 市场温度：开关关闭时为 None（模板保持既有输出）
    valuation_enabled = valuation_data is not None
    penetration_display = _attach_valuation_to_penetration(penetration, valuation_data)
    market_temperature = _build_temperature_display(market_temperature_data)
    # 目录分组导航：按「基础/基金深度/风险/历史/LLM」五组折叠（_sv_fn 闭包过滤不可见章节）
    section_groups = _build_section_nav_groups(order, _sv_fn, section_numbers)

    return _ENV.get_template("report_template.html").render(
        flow_display=_build_flow_display(fund_flow_data),
        section_groups=section_groups,
        llm_supported_sections=_LLM_SUPPORTED_SECTIONS,
        valuation_enabled=valuation_enabled,
        market_temperature=market_temperature,
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
        a_indices=a_indices_list,
        us_indices=us_indices_list,
        accounts=accounts,
        account_totals=account_totals,
        cat_data=cat_data,
        penetration=penetration_display,
        perf_data=perf_data,
        candidate_data=candidate_data,
        # SAC: news_data[*].enriched_keywords[*].display 来自外部 API
        # 模板中已禁用 |safe 过滤器，依赖 autoescape 防 XSS —— 勿加 |safe
        news_data=news_data,
        news_llm_meta=_news_llm_meta,
        has_llm_analysis=has_llm_analysis,
        manager_analysis=manager_analysis,
        overlap_matrix=overlap_matrix,
        concentration_analysis=concentration_analysis,
        style_analysis=style_analysis,
        llm_enabled=llm_enabled_flag,
        global_macro=global_macro_content,
        expert_review=expert_review_content,
        health_check=health_check_content,
        penetration_deep=penetration_deep_content,
        llm_session_usage=_llm_session_usage,
        module_labels=get_llm_module_names(),
        module_disabled=module_disabled,
        llm_module_info=_llm_module_info,
        llm_endpoint=llm_endpoint,
        cache_stats=get_cache_hit_rate(),
        app_version=APP_VERSION,
        debate_mode_label=_debate_mode_label,
        debate_info=debate_info,
        debate_mode_combination=_debate_mode_combination,
        section_order=order,
        section_numbers=section_numbers,
        section_visible_dict=section_visible_dict,
        section_visible=_sv_fn,
        data_status_summary=data_status_summary,
        data_status_penetration=data_status_penetration,
        data_status_perf=data_status_perf,
        data_status_category=data_status_category,
        history_data=history_data,
        data_status_history=data_status_history,
        data_source_matrix=data_source_matrix,
        report_year=datetime.now().year,
        data_unavailable=bool(total_mv == 0 and total_cost > 0),
        chart_datasets=chart_datasets,
        enable_interactive_charts=enable_interactive_charts,
        style_factor_data=style_factor_data,
        factor_names=factor_names or {},
        industry_beta=industry_beta,
        position_relationship_data=position_relationship_data,
        evolution_data=evolution_data,
        evolution_chart_data=build_evolution_chart_data(evolution_data),
        drawdown_min_span=drawdown_min_span,
        data_quality_enabled=data_quality_enabled,
        position_status=position_status,
        data_freshness=data_freshness,
        action_data=action_data,
        crisis_annotation_data=crisis_annotation_data,
        tail_risk_data=tail_risk_data,
        snapshot_diff_data=snapshot_diff_data,
    )


# ── 核心生成函数 ────────────────────────────────────────────


def write_html_report(
    holdings: list[Holding],
    output_dir: str = "reports",
    news_top_count: int = 100,
    enable_llm: bool = False,
    include_news: bool = True,
    force_llm: bool = False,
    llm_content: tuple[str | None, str | None, str | None, str | None] | None = None,
    details: list | None = None,
    news_data: list | None = None,
    news_llm_meta: dict | None = None,
    sector_flow: list | None = None,
    progress: ProgressReporter | None = None,
    section_order: list[dict] | None = None,
    history_data: dict | None = None,
    a_indices: dict | None = None,
    us_indices: dict | None = None,
    enable_fund_deep_analysis: bool = True,
    enable_news: bool = True,
    enable_history: bool = True,
    enable_portfolio_evolution: bool = True,
    enable_action: bool = False,  # 行动建议独立章（enable_action 默认关）
    enable_data_quality: bool = False,  # 子模块：数据质量仪表盘（report_submodules.data_quality）
    position_status: dict | None = None,  # 品种覆盖诊断 position_status（品种覆盖区块）
    data_freshness: dict | None = None,  # 可信度摘要 data_freshness（可信度区块 + 头部摘要行）
    action_data: dict | None = None,  # 行动建议单一数据源 action_data（行动板块 + 智囊团深度复盘行动摘要）
    debate_info: dict | None = None,
    chart_datasets: dict | None = None,
    enable_interactive_charts: bool = False,
    style_factor_data: dict | None = None,
    position_relationship_data: dict | None = None,
    evolution_data: dict | None = None,
    drawdown_min_span: int = DRAW_DOWN_MIN_SPAN,
    crisis_annotation_data: dict | None = None,  # 危机区间标注 crisis_annotation_data
    tail_risk_data: dict | None = None,  # 尾部风险统计 tail_risk_data（指标卡）
    snapshot_diff_data: dict | None = None,  # 快照差异摘要 snapshot_diff_data（组合演进章顶部变化摘要）
    fund_flow_data: dict | None = None,  # 成本流水数据 fund_flow_data（三页签 HTML 渲染数据源，None=开关关闭）
    valuation_data: dict | None = None,  # 估值分位数据契约 valuation_data（「资产穿透TOP10」估值分位列，None=开关关闭）
    market_temperature_data: dict
    | None = None,  # 市场温度数据契约 market_temperature_data（「投资分析汇总」温度行，None=开关关闭）
) -> str:
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
        history_data: 组合历史走势数据（来自 PortfolioHistoryCalculator），
            包含 bars、max_drawdown、annualized_volatility、total_return、warnings 等。
            None 时历史章节显示占位文本。
        a_indices: 可选预获取 A 股指数数据，传入时跳过 HTTP 请求。
        us_indices: 可选预获取美股指数数据，传入时跳过 HTTP 请求。
        chart_datasets: Chart.js 数据集（chart_data_builder 输出），经 context 传递。
            默认 None → 图表章节回退旧 Canvas 渲染。
        enable_interactive_charts: Chart.js 交互图表总开关（Feature Flag）。
            默认 False → 模板不加载 chart.min.js / canvas 容器。

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
    a_indices, us_indices, a_indices_list, us_indices_list = _render_index_section(prog, a_indices, us_indices)

    # ── 5~7) 分类表 / 穿透 / 基金业绩 ──
    cat_data, cat_dividend_ok = _render_category_table(holdings, details, prog)
    penetration, penetration_profit_ok, penetration_dividend_ok = _render_penetration_section(holdings, details, prog)
    perf_data, candidate_data = _render_fund_performance_section(holdings, details, prog)

    # ── 5b) Chart.js 数据集补齐：category_doughnut / industry_bar / penetration_bar ──
    # 这三张图的数据源（cat_data / penetration）只在 write_html_report 内计算，
    # 调用侧传入的 chart_datasets 拿不到它们，导致图表误显示"暂不可用"。
    # 此处用权威数据重建并覆盖，保证图表与表格同源（单图失败仅跳过该图）。
    if enable_interactive_charts and chart_datasets is not None:
        from src.python.report.chart_data_builder import (
            _build_category_doughnut_dataset,
            _build_industry_bar_dataset,
            _build_penetration_bar_dataset,
        )

        try:
            chart_datasets["category_doughnut"] = _build_category_doughnut_dataset(None, cat_data)
        except Exception:
            logger.warning("[chart] category_doughnut 数据补齐失败，保留原数据集", exc_info=True)
        try:
            chart_datasets["industry_bar"] = _build_industry_bar_dataset(penetration)
        except Exception:
            logger.warning("[chart] industry_bar 数据补齐失败，保留原数据集", exc_info=True)
        try:
            chart_datasets["penetration_bar"] = _build_penetration_bar_dataset(penetration)
        except Exception:
            logger.warning("[chart] penetration_bar 数据补齐失败，保留原数据集", exc_info=True)

    # ── 13) 基金经理变更监控 ──
    manager_analysis = _render_manager_analysis(holdings, enable_fund_deep_analysis, prog)

    # ── 14) 持仓关系矩阵·重合度区块 ──
    overlap_matrix = _render_overlap_matrix(holdings, details, enable_fund_deep_analysis, prog)

    # ── 15) 持仓集中度监控 ──
    concentration_analysis = _render_concentration(holdings, enable_fund_deep_analysis, prog)

    # ── 16) 风格与因子分析 ──
    style_analysis = _render_style_analysis(holdings, enable_fund_deep_analysis, prog)

    # ── 8) 财经新闻 ──
    news_data, _news_llm_meta = _render_news_section(
        include_news, news_data, news_llm_meta, holdings, news_top_count, penetration, prog
    )

    # ── 9) LLM 智能分析内容 ──
    llm_enabled_flag, global_macro_content, expert_review_content, health_check_content, penetration_deep_content = (
        _render_llm_content_section(
            enable_llm,
            llm_content,
            force_llm,
            a_indices,
            us_indices,
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings,
            cat_counts,
            penetration,
            details,
            sector_flow,
            prog,
        )
    )

    # ── LLM 模块状态收集 ──
    llm_module_info, llm_endpoint, module_disabled, _llm_session_usage = _render_llm_module_info(llm_enabled_flag)

    # ── 辩论模式标签 ──
    from src.python.report._debate_utils import detect_debate_mode

    _debate_mode_label, _debate_mode_combination = detect_debate_mode(debate_info)

    # 辩论模式启用时覆盖 llm_module_info 中 expert_review 的状态标签
    if _debate_mode_label:
        for _mi in llm_module_info:
            if _mi.get("key") == "expert_review" and _mi.get("status") in ("success", "cached"):
                _mi["status_label"] = _debate_mode_label

    # ── 10) 渲染模板 ──
    prog.info("正在渲染 HTML...")
    has_llm_analysis = any(item.get("llm_analysis") for item in (news_data or []))

    # ── 10a) 报告模块序号 & 可见性 ──
    order = section_order or get_report_section_order()
    section_numbers, section_visible_dict, _sv_fn = _compute_section_visibility(
        order,
        manager_analysis,
        overlap_matrix,
        concentration_analysis,
        style_analysis,
        include_news,
        llm_enabled_flag,
        enable_news=enable_news,
        enable_fund_deep_analysis=enable_fund_deep_analysis,
        enable_history=enable_history,
        enable_portfolio_evolution=enable_portfolio_evolution,
        enable_action=enable_action,
        enable_llm=enable_llm,  # enable_llm is the board param for LLM
        style_factor_data=style_factor_data,
        position_relationship_data=position_relationship_data,
        evolution_data=evolution_data,
    )

    # ── 10b) 数据源状态摘要 ──
    (data_status_summary, data_status_penetration, data_status_perf, data_status_category) = (
        _build_data_status_sections(
            a_indices,
            us_indices,
            penetration,
            penetration_profit_ok,
            penetration_dividend_ok,
            perf_data,
            holdings,
            cat_dividend_ok,
        )
    )

    # ── 10c) 组合历史走势数据状态 ──
    data_status_history = _build_history_data_status(history_data)

    # ── 10d) 数据源可用性矩阵 ──
    from src.python.report.data_source_matrix import build_data_source_matrix

    data_source_matrix = build_data_source_matrix()

    # 因子中文名映射（单一数据源：analysis 层常量，经 context 传递）
    _factor_names: dict = {}
    if style_factor_data:
        try:
            from src.python.analysis.style_factor_regression import FACTOR_NAMES

            _factor_names = FACTOR_NAMES
        except Exception:
            _factor_names = {}

    html = _render_template(
        now_str=now_str,
        today_str=today_str,
        trading_day=trading_day,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_profit_rate=total_profit_rate,
        total_today_profit=total_today_profit,
        today_profit_rate=today_profit_rate,
        cat_counts=cat_counts,
        update_status_dict=update_status_dict,
        a_indices_list=a_indices_list,
        us_indices_list=us_indices_list,
        accounts=accounts,
        account_totals=account_totals,
        cat_data=cat_data,
        penetration=penetration,
        perf_data=perf_data,
        candidate_data=candidate_data,
        news_data=news_data,
        _news_llm_meta=_news_llm_meta,
        has_llm_analysis=has_llm_analysis,
        manager_analysis=manager_analysis,
        overlap_matrix=overlap_matrix,
        concentration_analysis=concentration_analysis,
        style_analysis=style_analysis,
        style_factor_data=style_factor_data,
        factor_names=_factor_names,
        industry_beta=(style_factor_data or {}).get("industry_beta"),
        position_relationship_data=position_relationship_data,
        evolution_data=evolution_data,
        drawdown_min_span=drawdown_min_span,
        llm_enabled_flag=llm_enabled_flag,
        global_macro_content=global_macro_content,
        expert_review_content=expert_review_content,
        health_check_content=health_check_content,
        penetration_deep_content=penetration_deep_content,
        _llm_session_usage=_llm_session_usage,
        _llm_module_info=llm_module_info,
        llm_endpoint=llm_endpoint,
        module_disabled=module_disabled,
        _debate_mode_label=_debate_mode_label,
        debate_info=debate_info,
        _debate_mode_combination=_debate_mode_combination,
        order=order,
        section_numbers=section_numbers,
        section_visible_dict=section_visible_dict,
        _sv_fn=_sv_fn,
        data_status_summary=data_status_summary,
        data_status_penetration=data_status_penetration,
        data_status_perf=data_status_perf,
        data_status_category=data_status_category,
        history_data=history_data,
        data_status_history=data_status_history,
        data_source_matrix=data_source_matrix,
        chart_datasets=chart_datasets,
        enable_interactive_charts=enable_interactive_charts,
        data_quality_enabled=enable_data_quality,
        position_status=position_status,
        data_freshness=data_freshness,
        action_data=action_data,
        crisis_annotation_data=crisis_annotation_data,
        tail_risk_data=tail_risk_data,
        snapshot_diff_data=snapshot_diff_data,
        fund_flow_data=fund_flow_data,
        valuation_data=valuation_data,
        market_temperature_data=market_temperature_data,
    )

    if enable_interactive_charts:
        _copy_js_assets(output_dir)

    return _save_html_report(html, output_dir, total_mv, total_profit, prog)


# ── Chart.js JS 资产复制（src/static/ → 输出目录）───────────────


def _copy_js_assets(output_dir: str) -> None:
    """将 src/static/ 下 Chart.js 前端 JS 资产复制到报告输出目录（本地 bundle）。

    模板以相对路径引用（chart.min.js / chart-print.js / chart-config.js /
    chart-export.js / chart-common.js / chart-init.js / toc.js / theme.js），
    报告完全离线自包含。文件缺失时仅告警，不阻断报告生成（防御性）。

    Args:
        output_dir: 报告输出目录（与 HTML 同目录）
    """
    import shutil

    from src.python.core.constants import PROJECT_ROOT

    _JS_ASSETS = (
        "chart.min.js",
        "chart-print.js",
        "chart-config.js",
        "chart-export.js",
        "chart-common.js",
        "chart-init.js",
        "toc.js",
        "theme.js",
    )
    src_dir = os.path.join(PROJECT_ROOT, "src", "static")
    os.makedirs(output_dir, exist_ok=True)
    for fname in _JS_ASSETS:
        src = os.path.join(src_dir, fname)
        if not os.path.exists(src):
            logger.warning("[chart] JS 资产缺失（跳过复制）: %s", src)
            continue
        try:
            shutil.copy2(src, os.path.join(output_dir, fname))
        except OSError as e:
            logger.warning("[chart] JS 资产复制失败: %s", e)


# ── 桥接 import：外部子模块 ─────────────────────────────────
from src.python.report.html_renderers import (  # noqa: E402, F401
    _render_account_grouping,
    _render_category_info,
    _render_category_table,
    _render_concentration,
    _render_fund_performance_section,
    _render_index_section,
    _render_llm_content_section,
    _render_llm_module_info,
    _render_manager_analysis,
    _render_market_value_section,
    _render_news_section,
    _render_overlap_matrix,
    _render_penetration_section,
    _render_style_analysis,
)
from src.python.report.html_save import _save_html_report  # noqa: E402, F401
