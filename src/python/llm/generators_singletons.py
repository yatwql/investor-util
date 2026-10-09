"""LLM 单例生成函数（语义名 generators_singletons）— 全局政经/智囊团/体检/穿透四生成器。

自 generators 按生成器域下沉：四函数共享「单次模块生成 + 指纹缓存」形态，
与辩论/自审（generators 门面留存）域分离。generators 门面 re-export，
消费方（_llm_dispatch / llm 包）导入面不变；测试 patch 须指向本模块的被解析名字。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from src.python.config.features import is_feature_enabled
from src.python.core.decision_header import structured_header_cache_suffix
from src.python.llm.module_fingerprint import (
    ModuleFingerprintInputs,
    debate_feature_cache_suffix,
    expert_review_fingerprint,
    global_macro_fingerprint,
    health_check_fingerprint,
    penetration_deep_fingerprint,
)
from src.python.llm.prompts import (
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_GLOBAL_MACRO,
    _SYSTEM_HEALTH_CHECK,
    _SYSTEM_PENETRATION_DEEP,
    _build_expert_review_prompt,
    _build_global_macro_prompt,
    _build_health_check_prompt,
    _build_penetration_deep_prompt,
)
from src.python.llm.skeleton import generate_llm_module

logger = __import__("logging").getLogger("invest")

__all__ = [
    "generate_global_macro",
    "generate_expert_review",
    "generate_health_check",
    "generate_penetration_deep_analysis",
]

# ── 单例生成函数（原 generators 定义域） ────────────────────


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
    purchase_constraint_block: str = "",
    holding_change_block: str = "",
    event_impact_block: str = "",
    schedule_replay_block: str = "",
) -> tuple[str | None, bool]:
    """生成全球政经局势。

    Args:
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），可选。
        holdings_details: 持仓明细（可选），用于提供 TOP3 排名，防止 LLM 虚构最大持仓。
    """
    # 指纹构造统一走 llm/module_fingerprint.py（读写同源的唯一事实来源）
    # competitive_context 为调用方渲染好的同一实例（既进指纹又进提示词，
    # 见 module_fingerprint 模块 docstring），此处只透传、不重渲染。
    _global_macro_inputs = ModuleFingerprintInputs(
        a_indices=a_indices,
        us_indices=us_indices,
        total_mv=total_mv,
        total_profit=total_profit,
        categories=categories,
        competitive_context=competitive_context or "",
        purchase_block=purchase_constraint_block or "",
        holding_change_block=holding_change_block or "",
        event_impact_block=event_impact_block or "",
        schedule_replay_block=schedule_replay_block or "",
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
        purchase_constraint_block=purchase_constraint_block,
        holding_change_block=holding_change_block,
        event_impact_block=event_impact_block,
        schedule_replay_block=schedule_replay_block,
    )


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
    purchase_constraint_block: str = "",
    holding_change_block: str = "",
    event_impact_block: str = "",
    schedule_replay_block: str = "",
) -> tuple[str | None, bool]:
    """生成智囊团深度复盘。

    辩论模式的附加功能通过 feature flag 注入 prompt：
      - conditional（条件推理）：追加涨/跌/震荡情景分析段
      - 集中度问答段为辩论流程内建段落（阈值触发，见 _build_concentration_qa_block）

    Args:
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），可选。
        metrics: 量化指标字典，compute_all_metrics() 的输出。
        history_data: 组合历史走势数据（含风险指标），参与缓存指纹。
    """
    _fp_suffix = debate_feature_cache_suffix()
    _enable_conditional = "c" in _fp_suffix
    _enable_signal_digest = is_feature_enabled("deterministic_signal")
    # 结构化决策头（decision_header_parse）：开关判定收敛在 suffix 函数内，
    # 关闭 → "" 且不追加提示词契约段；指纹侧由 module_fingerprint 同源现算。
    _structured_suffix = structured_header_cache_suffix()
    # 指纹输入闭包与预检侧同构；后缀（辩论增强/教训/信号/决策头）统一在
    # module_fingerprint 内拼接，读写键同源由结构保证。
    # competitive_context / metrics 是其提示词正文段（对比块 + 指标表 + 情景分析），
    # 故一并进指纹——两者都是调用方传入的同一实例，此处只透传、不重算。
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
        competitive_context=competitive_context or "",
        metrics=metrics,
        purchase_block=purchase_constraint_block or "",
        holding_change_block=holding_change_block or "",
        event_impact_block=event_impact_block or "",
        schedule_replay_block=schedule_replay_block or "",
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
        purchase_constraint_block=purchase_constraint_block,
        holding_change_block=holding_change_block,
        event_impact_block=event_impact_block,
        schedule_replay_block=schedule_replay_block,
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
    data_quality_text: str | None = None,
    history_data: dict | None = None,
    purchase_constraint_block: str = "",
    holding_change_block: str = "",
    event_impact_block: str = "",
    schedule_replay_block: str = "",
) -> tuple[str | None, bool]:
    """生成持仓体检报告。

    ``data_quality_text`` 为调用方渲染好的数据质量详细状态块：同一实例既进指纹
    又进提示词（否则「源故障期间缓存、恢复后复用」会让报告陈述与此刻事实相反），
    本函数不自行渲染——见 ``llm/module_fingerprint.py`` 模块 docstring。
    """
    _enable_signal_digest = is_feature_enabled("deterministic_signal")
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
        data_quality_text=data_quality_text or "",
        purchase_block=purchase_constraint_block or "",
        holding_change_block=holding_change_block or "",
        event_impact_block=event_impact_block or "",
        schedule_replay_block=schedule_replay_block or "",
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
            data_quality_text=data_quality_text,
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
        purchase_constraint_block=purchase_constraint_block,
        holding_change_block=holding_change_block,
        event_impact_block=event_impact_block,
        schedule_replay_block=schedule_replay_block,
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
    purchase_constraint_block: str = "",
    holding_change_block: str = "",
    event_impact_block: str = "",
    schedule_replay_block: str = "",
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
        purchase_block=purchase_constraint_block or "",
        holding_change_block=holding_change_block or "",
        event_impact_block=event_impact_block or "",
        schedule_replay_block=schedule_replay_block or "",
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
        purchase_constraint_block=purchase_constraint_block,
        holding_change_block=holding_change_block,
        event_impact_block=event_impact_block,
        schedule_replay_block=schedule_replay_block,
    )
