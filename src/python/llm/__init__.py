"""LLM 智能分析包 — 拆分子模块的公共入口。

子模块（按职责分层）：
  prompts.py          — System Prompt 常量与构建函数
  generators.py       — LLM 调用编排与批量生成
  api.py              — Claude / OpenAI 双通道底层调用
  fingerprint.py      — 缓存指纹计算
  pricing.py          — Token 定价与费用估算
  session.py          — 会话统计（Token 累计、模块级用量）
  circuit_breaker.py  — 熔断器（连续失败自动暂停）
  markdown.py         — Markdown → HTML 转换
"""

from __future__ import annotations

from src.python.llm.prompts import (  # noqa: F401
    _CACHE_PREFIX_LLM, _LLM_MODULE_FAILURE,
    FAIL_REASON_NOT_CONFIGURED, FAIL_REASON_API_ERROR, FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_TIMEOUT, FAIL_REASON_CIRCUIT_OPEN, FAIL_REASON_DISABLED,
    _SYSTEM_GLOBAL_MACRO, _SYSTEM_EXPERT_REVIEW, _SYSTEM_HEALTH_CHECK,
    _SYSTEM_PENETRATION_DEEP, _SYSTEM_NEWS_CORRELATION,
    _is_qdii, _fmt_wan, _fmt_holding_line,
    _build_global_macro_prompt, _build_expert_review_prompt, _build_health_check_prompt,
    _build_penetration_deep_prompt, _build_holdings_summary, _build_news_correlation_summary,
)
from src.python.llm.generators import (  # noqa: F401
    _generate_llm_content, _apply_llm_news_correlation,
    generate_global_macro, generate_expert_review, generate_health_check,
    generate_penetration_deep_analysis, enhance_news_correlation, generate_all_llm,
)
from src.python.llm.api import (  # noqa: F401
    _CACHE_LINE_HTML, _CACHE_LINE_MODEL_TPL, _LLM_TIMEOUT, _RETRY_DELAYS,
    _TRUNCATION_MARKER, _AUTO_INCREASE_FACTOR,
    _TOKEN_LINE_RE, _MODEL_LINE_RE, _THINKING_SUPPORTED_PREFIXES,
    _THINKING_EFFORT_MODEL_PREFIXES,
    _supports_extended_thinking, _is_effort_model, _truncation_warning,
    _check_claude_truncation, _check_openai_truncation, _extract_content,
    _strip_token_line, _extract_model_from_cached, _log_token_usage,
    _get_retry_max, _call_llm_with_retry, _call_single_provider,
    _call_llm, _call_claude, _call_openai,
)
from src.python.llm.circuit_breaker import (  # noqa: F401
    _CIRCUIT_BREAKER_THRESHOLD, _CIRCUIT_BREAKER_RECOVERY,
    _circuit_failures, _circuit_open_until, _circuit_lock,
    _cb_endpoint, _cb_record_failure, _cb_record_success, _cb_is_open,
)
from src.python.llm.fingerprint import (  # noqa: F401
    _compute_fingerprint,
    _build_llm_fingerprint,
    _get_cache_ttl_llm,
)
from src.python.llm.markdown import _markdown_to_html  # noqa: F401
from src.python.llm.pricing import (  # noqa: F401
    _PRICING_MERGED, _PRICING_CURRENCY, _CURRENCY_SYMBOLS,
    _reload_pricing, _estimate_cost,
)
from src.python.llm.session import (  # noqa: F401
    _session_usage,
    reset_session_usage, get_session_usage, format_session_usage,
    _track_session_usage, _record_per_module,
)
