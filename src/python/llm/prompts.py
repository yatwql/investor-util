"""LLM 提示词模块 — 重新导出门户。

本文件为向后兼容的重新导出门户。
具体实现已拆分到以下子模块：

  - prompts_core.py  — System Prompt 常量、基础设施、上下文构建块
  - prompts_tables.py — 格式化和摘要构建函数
  - prompts_action.py — 各模块 Prompt 构建函数

所有外部代码保持 from src.python.llm.prompts import ... 不变。
"""

from __future__ import annotations

# ── 从 prompts_core 重新导出 ──────────────────────────────────
from src.python.llm.prompts_core import (
    CACHE_PREFIX_LLM,
    FAIL_REASON_API_ERROR,
    FAIL_REASON_CIRCUIT_OPEN,
    FAIL_REASON_DISABLED,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_TIMEOUT,
    LLM_MODULE_FAILURE,
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_GLOBAL_MACRO,
    _SYSTEM_HEALTH_CHECK,
    _SYSTEM_NEWS_CORRELATION,
    _SYSTEM_PENETRATION_DEEP,
    _build_competitive_context_block,
    _build_concept_sector_block,
    _build_data_degradation_block,
    _build_difpipeline_data_block,
    _build_profit_attribution_block,
    _build_rebalance_block,
    _fmt_holding_line,
    _fmt_wan,
)

# ── 从 prompts_tables 重新导出 ────────────────────────────────
from src.python.llm.prompts_tables import (
    _build_holdings_summary,
    _build_news_correlation_summary,
    _calc_country_exposure,
    _format_holdings_block,
    _format_penetration_block,
)

# ── 从 prompts_action 重新导出 ────────────────────────────────
from src.python.llm.prompts_action import (
    _build_expert_review_prompt,
    _build_global_macro_prompt,
    _build_health_check_prompt,
    _build_penetration_deep_prompt,
)

__all__ = [
    # 常量
    "CACHE_PREFIX_LLM",
    "FAIL_REASON_NOT_CONFIGURED",
    "FAIL_REASON_API_ERROR",
    "FAIL_REASON_NETWORK_ERROR",
    "FAIL_REASON_TIMEOUT",
    "FAIL_REASON_CIRCUIT_OPEN",
    "FAIL_REASON_DISABLED",
    "LLM_MODULE_FAILURE",
    # System Prompts
    "_SYSTEM_GLOBAL_MACRO",
    "_SYSTEM_EXPERT_REVIEW",
    "_SYSTEM_HEALTH_CHECK",
    "_SYSTEM_PENETRATION_DEEP",
    "_SYSTEM_NEWS_CORRELATION",
    # 格式化函数
    "_fmt_wan",
    "_fmt_holding_line",
    "_format_holdings_block",
    "_format_penetration_block",
    "_calc_country_exposure",
    # 上下文构建块
    "_build_difpipeline_data_block",
    "_build_data_degradation_block",
    "_build_profit_attribution_block",
    "_build_concept_sector_block",
    "_build_rebalance_block",
    "_build_competitive_context_block",
    # Prompt 构建函数
    "_build_global_macro_prompt",
    "_build_expert_review_prompt",
    "_build_health_check_prompt",
    "_build_penetration_deep_prompt",
    # 新闻关联分析
    "_build_holdings_summary",
    "_build_news_correlation_summary",
]
