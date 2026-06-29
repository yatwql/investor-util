"""LLM 智能分析客户端 — 兼容存根，从 llm/ 包重新导出所有符号。"""

from __future__ import annotations

# ── httpx (module-level for test patch compatibility) ────────
import httpx  # noqa: F401 — used by tests as llm_client.httpx.Client

# ── cache (re-exported for test patching) ───────────────────
from src.python.cache import get as cache_get, set as cache_set  # noqa: F401

# ── content ────────────────────────────────────────────────
from src.python.llm.content import (  # noqa: F401
    _SYSTEM_GLOBAL_MACRO,
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_HEALTH_CHECK,
    _SYSTEM_PENETRATION_DEEP,
    _SYSTEM_NEWS_CORRELATION,
    _build_global_macro_prompt,
    _build_expert_review_prompt,
    _build_health_check_prompt,
    _build_penetration_deep_prompt,
    _build_holdings_summary,
    _build_news_correlation_summary,
    _apply_llm_news_correlation,
    _generate_llm_content,
    _is_qdii,
    _fmt_wan,
    _fmt_holding_line,
    _CACHE_PREFIX_LLM,
    _LLM_MODULE_FAILURE,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_API_ERROR,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_TIMEOUT,
    FAIL_REASON_CIRCUIT_OPEN,
    generate_all_llm,
    enhance_news_correlation,
)

# ── api ────────────────────────────────────────────────────
from src.python.llm.api import (  # noqa: F401
    _call_claude,
    _call_llm,
    _call_openai,
    _call_single_provider,
    _call_llm_with_retry,
    _extract_content,
    _check_claude_truncation,
    _check_openai_truncation,
    _sanitize_endpoint,
    _supports_extended_thinking,
    _is_effort_model,
    _log_token_usage,
    _truncation_warning,
    _strip_token_line,
    _extract_model_from_cached,
    _get_retry_max,
    _LLM_TIMEOUT,
    _RETRY_DELAYS,
    _TRUNCATION_MARKER,
    _AUTO_INCREASE_FACTOR,
    _CONTENT_FILTER_RECOVERY,
    _TOKEN_LINE_RE,
    _CACHE_LINE_HTML,
    _CACHE_LINE_MODEL_TPL,
    _MODEL_LINE_RE,
    _THINKING_SUPPORTED_PREFIXES,
    _THINKING_EFFORT_MODEL_PREFIXES,
)

# ── fingerprint ────────────────────────────────────────────
from src.python.llm.fingerprint import (  # noqa: F401
    _compute_fingerprint,
    _get_cache_ttl_llm,
    _expert_review_fingerprint,
    _health_check_fingerprint,
    _penetration_deep_fingerprint,
    _extract_stable_holdings,
    _extract_stable_penetration,
)

# ── circuit_breaker ────────────────────────────────────────
from src.python.llm.circuit_breaker import (  # noqa: F401
    _cb_endpoint,
    _cb_is_open,
    _cb_record_failure,
    _cb_record_success,
    _CIRCUIT_BREAKER_THRESHOLD,
    _CIRCUIT_BREAKER_RECOVERY,
    _circuit_failures,
    _circuit_open_until,
    _circuit_lock,
)

# ── session ────────────────────────────────────────────────
from src.python.llm.session import (  # noqa: F401
    reset_session_usage,
    get_session_usage,
    format_session_usage,
    _session_usage,
    _track_session_usage,
    _record_per_module,
)

# ── concurrent.futures (for test patch compatibility) ──────
from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: F401

# ── markdown ───────────────────────────────────────────────
from src.python.llm.markdown import (  # noqa: F401
    _markdown_to_html,
)

# ── pricing ────────────────────────────────────────────────
from src.python.llm.pricing import (  # noqa: F401
    _estimate_cost,
    _reload_pricing,
    _PRICING_MERGED,
    _PRICING_CURRENCY,
    _CURRENCY_SYMBOLS,
)

# ── Module-level __getattr__ for test patch compatibility ──
# These 4 functions are defined in content.py and may be patched
# at either src.python.llm.content or src.python.llm_client level
# by different test classes. Dynamic lookup ensures both work.
_LLM_CONTENT_GEN_FUNCS = frozenset({
    "generate_global_macro", "generate_expert_review",
    "generate_health_check", "generate_penetration_deep_analysis",
})


def __getattr__(name: str) -> Any:
    if name in _LLM_CONTENT_GEN_FUNCS:
        from src.python.llm import content as _content
        return getattr(_content, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
