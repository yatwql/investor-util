"""LLM 生成模块 — 全局政经/智囊团/体检/穿透四大单例函数 + 辩论模式生成。

职责：
  - 4 个单例生成函数（generate_global_macro 等）
  - 辩论模式白脸/黑脸/综合生成（generate_debate_procon）
  - 批量编排 → generators_orchestrator.py
  - 新闻关联 → generators_news.py
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.llm.fingerprint import get_cache_ttl_llm
from src.python.llm.module_fingerprint import (
    ModuleFingerprintInputs,
    debate_feature_cache_suffix,
    expert_review_fingerprint,
    global_macro_fingerprint,
    health_check_fingerprint,
    penetration_deep_fingerprint,
)
from src.python.llm.prompts import (
    _SYSTEM_DEBATE_CON,
    _SYSTEM_DEBATE_PRO,
    _build_system_debate_synthesis,
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_GLOBAL_MACRO,
    _SYSTEM_HEALTH_CHECK,
    _SYSTEM_PENETRATION_DEEP,
    _build_debate_synthesis_prompt,
    _build_expert_review_prompt,
    _build_global_macro_prompt,
    _build_health_check_prompt,
    _build_penetration_deep_prompt,
)
from src.python.config.features import is_feature_enabled
from src.python.core.decision_header import structured_header_cache_suffix
from src.python.llm._hallucination_filter import _filter_hallucinated_codes
from src.python.llm.skeleton import generate_llm_module

logger = logging.getLogger("invest")

__all__ = [
    "generate_global_macro",
    "generate_expert_review",
    "generate_health_check",
    "generate_penetration_deep_analysis",
    "generate_debate_procon",
    "_filter_hallucinated_codes",
]


def generate_global_macro(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_profit: float,
    total_cost: float,
    categories: dict,
    sector_flow: list[dict[str, Any]] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    competitive_context: str | None = None,
    holdings_details: list[dict] | None = None,
) -> tuple[str | None, bool]:
    """生成全球政经局势。

    Args:
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），可选。
        holdings_details: 持仓明细（可选），用于提供 TOP3 排名，防止 LLM 虚构最大持仓。
    """
    # 指纹构造统一走 llm/module_fingerprint.py（读写同源的唯一事实来源）
    _global_macro_inputs = ModuleFingerprintInputs(
        a_indices=a_indices,
        us_indices=us_indices,
        total_mv=total_mv,
        total_profit=total_profit,
        categories=categories,
    )

    def _fingerprint():
        return global_macro_fingerprint(_global_macro_inputs)

    def _prompt():
        return _build_global_macro_prompt(
            a_indices,
            us_indices,
            total_mv,
            total_profit,
            total_cost,
            categories,
            sector_flow,
            competitive_context=competitive_context,
        )

    return generate_llm_module(
        llm_config,
        "global_macro",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_GLOBAL_MACRO,
        prompt_builder=_prompt,
        max_tokens_default=800,
        timeout_default=60.0,
        output_brief_limit=200,
        holdings_details=holdings_details,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
    )


def _compute_industry_concentration(
    penetrated_assets: list[dict] | None,
    total_mv: float,
) -> dict[str, float] | None:
    """从穿透资产数据计算行业集中度字典。

    按 sector 字段聚合穿透资产的市值占比，结果形如
    {"银行": 0.35, "消费": 0.25}，供集中度问答模块使用。

    Args:
        penetrated_assets: 穿透资产列表（每项含 sector/mv 字段）。
        total_mv: 持仓总市值。

    Returns:
        行业集中度字典，数据不足时返回 None。
    """
    if not penetrated_assets or total_mv <= 0:
        return None
    ind_mv: dict[str, float] = {}
    for _a in penetrated_assets:
        _s = _a.get("sector", "--")
        _m = _a.get("mv", 0) or 0
        ind_mv[_s] = ind_mv.get(_s, 0) + _m
    return {k: round(v / total_mv, 4) for k, v in ind_mv.items()}


def generate_expert_review(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    pipeline_data: dict | None = None,
    competitive_context: str | None = None,
    metrics: dict | None = None,
    history_data: dict | None = None,
) -> tuple[str | None, bool]:
    """生成智囊团深度复盘。

    辩论模式的附加功能通过 feature flag 注入 prompt：
      - conditional（条件推理）：追加涨/跌/震荡情景分析段
      - qa_concentration（集中度问答）：追加集中度反问引导段

    Args:
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），可选。
        metrics: 量化指标字典，compute_all_metrics() 的输出。
        history_data: 组合历史走势数据（含风险指标），参与缓存指纹。
    """
    _fp_suffix = debate_feature_cache_suffix()
    _enable_conditional = "c" in _fp_suffix
    _enable_qa_concentration = "q" in _fp_suffix
    _enable_signal_digest = is_feature_enabled("signal_pre_digest")
    # 结构化决策头（decision_header_parse）：开关判定收敛在 suffix 函数内，
    # 关闭 → "" 且不追加提示词契约段；指纹侧由 module_fingerprint 同源现算。
    _structured_suffix = structured_header_cache_suffix()
    _industry_conc = _compute_industry_concentration(penetrated_assets, total_mv) if _enable_qa_concentration else None
    # 指纹输入闭包与预检侧同构；后缀（辩论增强/教训/信号/决策头）统一在
    # module_fingerprint 内拼接，读写键同源由结构保证。
    _fingerprint_inputs = ModuleFingerprintInputs(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
        history_data=history_data,
        pipeline_data=pipeline_data,
    )

    def _fingerprint():
        return expert_review_fingerprint(_fingerprint_inputs)

    def _prompt():
        return _build_expert_review_prompt(
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
            pipeline_data=pipeline_data,
            competitive_context=competitive_context,
            metrics=metrics,
            enable_conditional=_enable_conditional,
            enable_qa_concentration=_enable_qa_concentration,
            industry_concentration=_industry_conc,
            enable_signal_digest=_enable_signal_digest,
            enable_structured_header=bool(_structured_suffix),
        )

    return generate_llm_module(
        llm_config,
        "expert_review",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_EXPERT_REVIEW,
        prompt_builder=_prompt,
        max_tokens_default=8192,
        timeout_default=120.0,
        output_brief_limit=300,
        holdings_details=holdings_details,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
    )


def generate_health_check(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    pipeline_data: dict | None = None,
    degradation_events: list[dict] | None = None,
    history_data: dict | None = None,
) -> tuple[str | None, bool]:
    """生成持仓体检报告。"""
    _enable_signal_digest = is_feature_enabled("signal_pre_digest")
    # 指纹输入闭包与预检侧同构（见 generate_expert_review 同名注释）。
    _fingerprint_inputs = ModuleFingerprintInputs(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
        history_data=history_data,
        pipeline_data=pipeline_data,
    )

    def _fingerprint():
        return health_check_fingerprint(_fingerprint_inputs)

    def _prompt():
        return _build_health_check_prompt(
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
            pipeline_data=pipeline_data,
            degradation_events=degradation_events,
            enable_signal_digest=_enable_signal_digest,
        )

    return generate_llm_module(
        llm_config,
        "health_check",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_HEALTH_CHECK,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=120.0,
        output_brief_limit=300,
        holdings_details=holdings_details,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
    )


def generate_penetration_deep_analysis(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    history_data: dict | None = None,
) -> tuple[str | None, bool]:
    """生成穿透深度分析。"""
    # 穿透深度分析的提示词不含信号块，指纹无后缀；风险信号摘要与其余
    # 承接模块同口径（见 llm/module_fingerprint.py）。
    _fingerprint_inputs = ModuleFingerprintInputs(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
        history_data=history_data,
    )

    def _fingerprint():
        return penetration_deep_fingerprint(_fingerprint_inputs)

    def _prompt():
        return _build_penetration_deep_prompt(
            total_mv,
            total_cost,
            total_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
        )

    return generate_llm_module(
        llm_config,
        "penetration_deep",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_PENETRATION_DEEP,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=90.0,
        output_brief_limit=300,
        holdings_details=holdings_details,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
    )


# ── 辩论模式：白脸/黑脸/综合生成 ───────────────────────────


def generate_debate_procon(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    pipeline_data: dict | None = None,
    competitive_context: str | None = None,
    metrics: dict | None = None,
    *,  # 以下为关键字参数
    session_cache: dict | None = None,
) -> tuple[str | None, str | None, str | None]:
    """生成白脸/黑脸辩论 + 综合结果。

    辩论模式下附加功能通过 feature flag 注入 pro/con/syn 的 prompt：
      - conditional（条件推理）：pro/con 各自含情景分析段
      - qa_concentration（集中度问答）：pro/con 各自含集中度反问引导段
    组合后缀隔离所有缓存键，不同 feature 组合不串扰。

    pro 或 con 失败时返回 (None, None, None) — 由调用方决定是否回退普通模式。
    synthesis 失败时返回 (pro_text, con_text, None) — 调用方可使用拼接结果。

    Returns:
        (pro_text, con_text, synthesis_text) 三元组，均为 None 表示完全失败。
    """
    import threading as _threading
    from src.python.config._llm_settings import get_llm_config
    from src.python.llm.fingerprint import build_llm_fingerprint

    # ── 辩论模式 feature 组合 ──────────────────────────
    _fp_suffix = debate_feature_cache_suffix()
    _enable_conditional = "c" in _fp_suffix
    _enable_qa_concentration = "q" in _fp_suffix
    _industry_conc = _compute_industry_concentration(penetrated_assets, total_mv) if _enable_qa_concentration else None

    # ── 构建基础 user prompt（辩论模式跳过情景分析，避免双重输出） ──
    _user = _build_expert_review_prompt(
        total_mv,
        total_cost,
        total_profit,
        total_today_profit,
        holdings_count,
        categories,
        penetrated_assets,
        holdings_details=holdings_details,
        pipeline_data=pipeline_data,
        competitive_context=competitive_context,
        metrics=metrics,
        enable_conditional=_enable_conditional,
        enable_qa_concentration=_enable_qa_concentration,
        industry_concentration=_industry_conc,
        skip_scenarios=True,  # 辩论模式下 pro/con 不写情景分析，避免双重输出
    )

    # ── 指纹计算 ────────────────────────────────────────
    _fingerprint = build_llm_fingerprint(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
    )

    # ── Session 级缓存（线程安全） ──────────────────────
    _cache_lock = _threading.Lock()

    def _check_session_cache(key: str) -> str | None:
        if session_cache is not None:
            with _cache_lock:
                return session_cache.get(key)
        return None

    def _set_session_cache(key: str, value: str) -> None:
        if session_cache is not None:
            with _cache_lock:
                session_cache[key] = value

    # ── 获取 debate 配置 ────────────────────────────────
    _lc = llm_config or get_llm_config()
    debate_cfg = (_lc or {}).get("debate", {})
    procon_cfg = debate_cfg.get("procon", {})
    _per_call_max_tokens = procon_cfg.get("per_call_max_tokens")
    _synthesis_temperature = procon_cfg.get("synthesis_temperature", 0.5)

    _max_tokens = _per_call_max_tokens if _per_call_max_tokens is not None else 8192
    _timeout = debate_cfg.get("per_call_timeout_override", 90)

    # ── Token 预算守卫 ─────────────────────────────────
    _max_total_tokens_budget = debate_cfg.get("max_total_tokens_per_report", 48000)
    # 中文+Markdown 混排输出约 1 字符 ≈ 1 token，按 1:1 折算字符级阈值；
    # 若按 1.5 token/字符估算，守卫会在真实预算 ~65% 处过早触发。
    _budget_char_threshold = int(_max_total_tokens_budget)
    _cumulative_chars: int = 0

    # ── 构建有效持仓代码集合（幻觉过滤用） ────────────
    # 穿透 TOP10 底层资产代码同样合法（如 QDII 基金穿透到 AAPL/MSFT），
    # 与 news_correlation 关键词构建（_extract_keywords_from_penetrated）保持一致。
    # 否则 LLM 在辩论中合理引用穿透代码会被误判为虚构，导致整句删除。
    _valid_codes: set[str] = set()
    if holdings_details:
        for _h in holdings_details:
            _code = _h.get("code", "")
            if _code:
                _valid_codes.add(str(_code))
    if penetrated_assets:
        for _a in penetrated_assets:
            for _c in _a.get("codes") or []:
                if _c and str(_c).strip():
                    _valid_codes.add(str(_c).strip())

    # ── Step 1: 白脸（Pro） ────────────────────────────
    _pro_cache_key = f"llm_debate_pro_{_fingerprint}{_fp_suffix}"
    _session_pro_key = f"debate_pro_{_fingerprint}{_fp_suffix}"
    pro_text = _check_session_cache(_session_pro_key)

    if pro_text is None and not force:
        pro_text = cache_get(_pro_cache_key, get_cache_ttl_llm("debate_pro"))

    if pro_text is None:
        pro_result = generate_llm_module(
            _lc,
            "expert_review",
            force=force,
            http_client=http_client,
            fingerprint_fn=lambda: f"{_fingerprint}{_fp_suffix}_debate_pro",
            system_prompt_default=_SYSTEM_DEBATE_PRO,
            prompt_builder=lambda: _user,
            max_tokens_default=_max_tokens,
            max_tokens_override=_max_tokens,
            timeout_default=_timeout,
            output_brief_limit=300,
            system_prompt=_SYSTEM_DEBATE_PRO,
            user_prompt=_user,
            holdings_details=holdings_details,
            total_mv=total_mv,
            total_cost=total_cost,
            total_profit=total_profit,
            raw_filter_fn=lambda t: _filter_hallucinated_codes(t, _valid_codes),
        )
        pro_text = pro_result[0] if pro_result and isinstance(pro_result, tuple) else None
        if pro_text:
            cache_set(_pro_cache_key, pro_text)
            _set_session_cache(_session_pro_key, pro_text)

    if not pro_text:
        logger.warning("[debate] 白脸生成失败，回退普通模式")
        return (None, None, None)

    # 追踪白脸 token 消耗
    _cumulative_chars += len(pro_text)
    logger.info("[debate] Token budget: 已用 %d chars（阈值 %d）", _cumulative_chars, _budget_char_threshold)

    # 超过 2× 预算：跳过所有 debate 调用，回退普通模式
    if _cumulative_chars > _budget_char_threshold * 2:
        logger.warning(
            "[debate] 超过 2× Token 预算（%d chars > %d），跳过所有 debate 调用",
            _cumulative_chars,
            _budget_char_threshold * 2,
        )
        return (None, None, None)

    # ── Step 2: 黑脸（Con） ────────────────────────────
    _con_cache_key = f"llm_debate_con_{_fingerprint}{_fp_suffix}"
    _session_con_key = f"debate_con_{_fingerprint}{_fp_suffix}"
    con_text = _check_session_cache(_session_con_key)

    if con_text is None and not force:
        con_text = cache_get(_con_cache_key, get_cache_ttl_llm("debate_con"))

    if con_text is None:
        con_result = generate_llm_module(
            _lc,
            "expert_review",
            force=force,
            http_client=http_client,
            fingerprint_fn=lambda: f"{_fingerprint}{_fp_suffix}_debate_con",
            system_prompt_default=_SYSTEM_DEBATE_CON,
            prompt_builder=lambda: _user,
            max_tokens_default=_max_tokens,
            max_tokens_override=_max_tokens,
            timeout_default=_timeout,
            output_brief_limit=300,
            system_prompt=_SYSTEM_DEBATE_CON,
            user_prompt=_user,
            holdings_details=holdings_details,
            total_mv=total_mv,
            total_cost=total_cost,
            total_profit=total_profit,
            raw_filter_fn=lambda t: _filter_hallucinated_codes(t, _valid_codes),
        )
        con_text = con_result[0] if con_result and isinstance(con_result, tuple) else None
        if con_text:
            cache_set(_con_cache_key, con_text)
            _set_session_cache(_session_con_key, con_text)

    if not con_text:
        logger.warning("[debate] 黑脸生成失败，回退普通模式")
        return (None, None, None)

    # 追踪黑脸 token 消耗
    _cumulative_chars += len(con_text)
    logger.info("[debate] Token budget: 已用 %d chars（阈值 %d）", _cumulative_chars, _budget_char_threshold)

    # 超过预算：跳过 synthesis，返回 pro+con 拼接
    if _cumulative_chars > _budget_char_threshold:
        logger.warning(
            "[debate] 超过 Token 预算（%d chars > %d），跳过 synthesis，返回 pro+con 拼接",
            _cumulative_chars,
            _budget_char_threshold,
        )
        return (pro_text, con_text, None)

    # ── Step 3: 综合（Synthesis） ──────────────────────
    _synthesis_user = _build_debate_synthesis_prompt(
        pro_text,
        con_text,
        enable_conditional=_enable_conditional,
        enable_qa_concentration=_enable_qa_concentration,
        industry_concentration=_industry_conc,
        holdings_details=holdings_details,
        total_mv=total_mv,
    )
    _pro_digest = hashlib.sha256(pro_text[:200].encode()).hexdigest()[:8]
    _con_digest = hashlib.sha256(con_text[:200].encode()).hexdigest()[:8]
    _syn_fingerprint = f"{_fingerprint}{_fp_suffix}_{_pro_digest}_{_con_digest}"
    _syn_cache_key = f"llm_debate_synthesis_{_syn_fingerprint}"
    _session_syn_key = f"debate_syn_{_syn_fingerprint}"
    synthesis_text = _check_session_cache(_session_syn_key)

    if synthesis_text is None and not force:
        synthesis_text = cache_get(_syn_cache_key, get_cache_ttl_llm("debate_synthesis"))

    if synthesis_text is None:
        # conditional 开启时用强化版 system prompt（允许情景分析但约束不复述
        # 白脸/黑脸观点，避免 user prompt 的情景指令与 system prompt 的
        # "禁止插入情景分析" 直接冲突）。
        _synthesis_system = _build_system_debate_synthesis(
            _enable_conditional,
            _enable_qa_concentration,
        )
        synthesis_result = generate_llm_module(
            _lc,
            "expert_review",
            force=force,
            http_client=http_client,
            fingerprint_fn=lambda: f"{_fingerprint}{_fp_suffix}_debate_syn_{_pro_digest}_{_con_digest}",
            system_prompt_default=_synthesis_system,
            prompt_builder=lambda: _synthesis_user,
            max_tokens_default=_max_tokens,
            max_tokens_override=_max_tokens,
            timeout_default=_timeout,
            output_brief_limit=300,
            system_prompt=_synthesis_system,
            user_prompt=_synthesis_user,
            raw_filter_fn=lambda t: _filter_hallucinated_codes(t, _valid_codes),
        )
        synthesis_text = synthesis_result[0] if synthesis_result and isinstance(synthesis_result, tuple) else None
        if synthesis_text:
            cache_set(_syn_cache_key, synthesis_text)
            _set_session_cache(_session_syn_key, synthesis_text)

    if not synthesis_text:
        logger.warning("[debate] 综合生成失败，返回 pro+con 拼接")
        return (pro_text, con_text, None)

    return (pro_text, con_text, synthesis_text)
