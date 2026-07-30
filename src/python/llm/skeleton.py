"""LLM 骨架模块 — 共享的生成骨架与批量处理逻辑。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from src.python.cache import get as cache_get  # noqa: F401
from src.python.cache import set as cache_set
from src.python.config import get_llm_config
from src.python.llm.api import call_llm
from src.python.llm.api_base import (
    AUTO_INCREASE_FACTOR,
    LLM_TIMEOUT,
    TRUNCATION_MARKER,
    _build_cache_hint_and_record,
    _get_last_llm_failure,
    clear_last_llm_failure,
)
from src.python.llm.fingerprint import get_cache_ttl_llm
from src.python.llm.markdown import markdown_to_html
from src.python.llm.pricing import estimate_cost
from src.python.llm.prompts import (
    CACHE_PREFIX_LLM,
    FAIL_REASON_API_ERROR,
    FAIL_REASON_DISABLED,
    FAIL_REASON_NOT_CONFIGURED,
    LLM_MODULE_FAILURE,
)
from src.python.llm.prompts_tables import _build_prompt_appendix
from src.python.llm.session import record_per_module
from src.python.core.registry import get_llm_module_name

_MN = get_llm_module_name

logger = logging.getLogger("invest")

__all__ = [
    "is_llm_module_enabled",
    "generate_llm_content",
    "generate_llm_module",
    "run_batch_mode",
]


def is_llm_module_enabled(llm_config: dict | None, module_suffix: str) -> bool:
    """检查 LLM 模块是否已启用。

    读取 enabled_llm 嵌套字典，模块默认启用。

    Args:
        llm_config: LLM 配置字典
        module_suffix: 模块后缀名（global_macro / expert_review / health_check /
                       penetration_deep / news_correlation）

    Returns:
        模块是否启用了 LLM 生成
    """
    if llm_config is None:
        return False
    enabled_map = llm_config.get("enabled_llm") or {}
    return bool(enabled_map.get(module_suffix, True))


def _handle_cache_hit(
    cached: str,
    cache_key: str,
    module_key: str,
    model: str | None,
    llm_config: dict,
    thinking_enabled: bool,
    endpoint: str = "",
) -> str:
    """处理 LLM 缓存命中：格式化缓存 HTML 并记录模块用量。

    Returns:
        带缓存标记的 HTML 字符串
    """
    logger.info("LLM 缓存命中: %s", cache_key)
    return _build_cache_hint_and_record(
        cached, module_key, llm_config, thinking_enabled, endpoint=endpoint, model_hint=model
    )


def _finalize_and_cache(
    result: str,
    usage: dict | None,
    cache_key: str,
    module_key: str,
    model: str | None,
    llm_config: dict,
    thinking_enabled: bool,
    endpoint: str = "",
    duration: float = 0.0,
) -> tuple[str | None, bool]:
    """处理 LLM 返回结果：Markdown→HTML → 拼接页脚 → 缓存 → 记录。

    Args:
        duration: API 调用耗时（秒），由调用方计时传入。

    Returns:
        (HTML 文本, False)
    """
    html = markdown_to_html(result)
    if not html.strip():
        logger.warning("LLM 返回内容为空，跳过缓存")
        if module_key:
            LLM_MODULE_FAILURE[module_key] = FAIL_REASON_API_ERROR
        return (None, False)

    _model_name = model or llm_config.get("model", "") or "未指定"
    if usage:
        inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        out = usage.get("output_tokens", usage.get("completion_tokens", 0))
        cache_hit = usage.get("cache_read_input_tokens", 0)
        _footer = f"模型：{_model_name} | Token 用量：输入 {inp:,} / 输出 {out:,} = {inp + out:,}"
        if duration > 0:
            _footer += f" | 耗时: {duration:.1f}s"
        _cost = estimate_cost(_model_name, inp, out, cache_hit_input_tokens=cache_hit)
        if _cost != "-":
            _footer += f" | 估算费用：{_cost}"
        if cache_hit:
            _footer += f" | 缓存命中：{cache_hit:,} tokens"
        if thinking_enabled:
            _footer += " | Extended Thinking"
        html += f'<p style="color:#888;font-size:12px">{_footer}</p>'
        if module_key:
            _inp = usage.get("input_tokens", usage.get("prompt_tokens", 0)) if usage else 0
            _out = usage.get("output_tokens", usage.get("completion_tokens", 0)) if usage else 0
            _cost_val = 0.0
            if _cost != "-":
                try:
                    _cost_val = float(_cost.lstrip("$¥€£"))
                except ValueError:
                    logger.warning("LLM 费用字符串解析失败: %s", _cost)
            _endpoint_for_record = endpoint or llm_config.get("endpoint", "") or ""
            _cache_hit = usage.get("cache_read_input_tokens", 0)
            record_per_module(
                module_key,
                _model_name,
                inp=_inp,
                out=_out,
                thinking=thinking_enabled,
                cost=_cost_val,
                endpoint=_endpoint_for_record,
                cache_hit_tokens=_cache_hit,
                duration=duration,
            )

    cache_set(cache_key, html)
    logger.info("LLM 内容生成完成: %s", cache_key)
    return (html, False)


def _handle_truncation(
    result: str | None,
    usage: dict | None,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
    llm_config: dict,
    timeout: float,
    http_client: httpx.Client | None,
    config_field: str,
    temperature: float | None,
    model: str | None,
) -> tuple[str | None, dict | None]:
    """检测截断并自动增大 max_tokens 重试。

    Returns:
        (result, usage) — 重试后的结果与用量，或原结果与用量（未截断时）
    """
    if not result or TRUNCATION_MARKER not in result:
        return result, usage

    new_max = int(max_tokens * AUTO_INCREASE_FACTOR)
    logger.warning("输出被截断（max_tokens=%d），自动以 %d 重新生成...", max_tokens, new_max)
    result2, usage2, _ = call_llm(
        system_prompt,
        user_prompt,
        llm_config,
        timeout=timeout,
        http_client=http_client,
        max_tokens=new_max,
        config_field=config_field,
        temperature=temperature,
        model=model,
    )
    if result2:
        if TRUNCATION_MARKER in result2:
            logger.warning("增大 max_tokens=%d 后仍被截断，请手动增大配置", new_max)
        return result2, usage2
    return result, None


def _build_provider_cache_key(
    cache_key: str,
    llm_config: dict,
    module_key: str,
    resolved_first_name: str | None = None,
) -> str:
    """在 chain 模式下为 cache_key 附加 provider name 后缀。

    Args:
        cache_key: 原始缓存 key（格式：llm_{module_key}_{fingerprint}）
        llm_config: LLM 配置（含 _provider_list 等）
        module_key: 当前模块键
        resolved_first_name: 可选，已解析的首位 provider name

    Returns:
        chain 模式返回 "{cache_key}_{provider_name}"，否则返回原 cache_key
    """
    provider_list = llm_config.get("_provider_list")
    if not provider_list or not module_key:
        return cache_key
    if resolved_first_name:
        name = resolved_first_name
    elif module_key:
        strategy = llm_config.get("_strategy", "priority")
        preferred = llm_config.get("_preferred_providers", {})
        try:
            from src.python.llm.strategy import resolve_provider_chain

            chain = resolve_provider_chain(provider_list, strategy, module_key, preferred)
            name = chain[0]["name"] if chain else "unknown"
        except Exception:
            logger.debug("[skeleton] Provider chain 解析异常，使用默认缓存键", exc_info=True)
            name = "unknown"
    else:
        name = "unknown"
    return f"{cache_key}_{name}"


def _resolve_first_provider(
    llm_config: dict,
    module_key: str,
) -> tuple[str | None, str | None, str]:
    """在多链模式下乐观预检 chain 首位 provider 的凭据。

    Returns:
        (provider_name, model, endpoint)
    """
    provider_list = llm_config.get("_provider_list")
    if not provider_list or not module_key:
        return (None, None, "")

    strategy = llm_config.get("_strategy", "priority")
    preferred = llm_config.get("_preferred_providers", {})
    try:
        from src.python.llm.strategy import resolve_provider_chain

        chain = resolve_provider_chain(provider_list, strategy, module_key, preferred)
        first_entry = chain[0] if chain else None
        first_name = first_entry["name"] if first_entry else None
        if first_entry:
            from src.python.llm.api import _resolve_entry_credentials

            _, first_model, first_endpoint = _resolve_entry_credentials(first_entry, llm_config)
        return (first_name, first_model, first_endpoint)
    except Exception:
        logger.debug("[skeleton] Provider 凭据解析异常", exc_info=True)
        return (None, None, "")


def _execute_llm_with_finalize(
    system_prompt: str,
    user_prompt: str,
    llm_config: dict,
    timeout: float,
    http_client: httpx.Client | None,
    max_tokens: int,
    config_field: str,
    temperature: float | None,
    model: str | None,
    cache_key: str,
    module_key: str,
    thinking_enabled: bool,
) -> tuple[str | None, bool]:
    """调用 LLM → 截断重试 → 处理结果并写入缓存。"""
    clear_last_llm_failure()
    _t0 = time.monotonic()
    result, usage, provider_info = call_llm(
        system_prompt,
        user_prompt,
        llm_config,
        timeout=timeout,
        http_client=http_client,
        max_tokens=max_tokens,
        config_field=config_field,
        temperature=temperature,
        model=model,
    )
    _duration = time.monotonic() - _t0
    result, usage = _handle_truncation(
        result,
        usage,
        max_tokens,
        system_prompt,
        user_prompt,
        llm_config,
        timeout,
        http_client,
        config_field,
        temperature,
        model,
    )

    if result:
        provider_name = provider_info.get("name") if provider_info else None
        resolved_model = provider_info.get("model") if provider_info else model
        resolved_endpoint = provider_info.get("endpoint", "") if provider_info else ""
        # 按实际 provider_name 落盘（可能与乐观预检不同——回退场景）
        provider_list = llm_config.get("_provider_list")
        write_key = cache_key
        if provider_list and provider_name:
            write_key = f"{cache_key}_{provider_name}"
        return _finalize_and_cache(
            result,
            usage,
            write_key,
            module_key,
            resolved_model,
            llm_config,
            thinking_enabled,
            endpoint=resolved_endpoint,
            duration=_duration,
        )

    logger.warning("LLM 内容生成失败: %s", cache_key)
    if module_key:
        existing = LLM_MODULE_FAILURE.get(module_key)
        if not isinstance(existing, dict):
            failure_reason = _get_last_llm_failure() or FAIL_REASON_API_ERROR
            LLM_MODULE_FAILURE[module_key] = failure_reason
    return (None, False)


def generate_llm_content(
    llm_config: dict,
    cache_key: str,
    cache_ttl: float,
    system_prompt: str,
    user_prompt: str,
    cache_enabled: bool,
    force: bool,
    max_tokens: int,
    timeout: float,
    temperature: float | None,
    model: str | None,
    config_field: str,
    http_client: httpx.Client | None = None,
    thinking_enabled: bool = False,
    module_key: str = "",
) -> tuple[str | None, bool]:
    """通用 LLM 内容生成骨架，带缓存检查与写入。"""
    if module_key:
        LLM_MODULE_FAILURE.pop(module_key, None)

    # ── 多链：乐观预检 chain 首位 provider ──
    first_name, first_model, first_endpoint = _resolve_first_provider(llm_config, module_key)
    precheck_key = _build_provider_cache_key(cache_key, llm_config, module_key, first_name)

    # ── 缓存检查 ──
    if cache_enabled and not force:
        cached = cache_get(precheck_key, cache_ttl)
        if cached:
            return (
                _handle_cache_hit(
                    cached,
                    precheck_key,
                    module_key,
                    first_model or model,
                    llm_config,
                    thinking_enabled,
                    endpoint=first_endpoint,
                ),
                True,
            )

    # ── LLM 调用 → 截断重试 → 处理结果 ──
    return _execute_llm_with_finalize(
        system_prompt,
        user_prompt,
        llm_config,
        timeout,
        http_client,
        max_tokens,
        config_field,
        temperature,
        model,
        cache_key,
        module_key,
        thinking_enabled,
    )


def _run_standard_mode(
    llm_config: dict,
    module_key: str,
    force: bool,
    http_client: httpx.Client | None,
    fingerprint_fn: Any,
    system_prompt_default: str,
    prompt_builder: Any,
    max_tokens_default: int,
    timeout_default: float,
    output_brief_limit: int,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    # ── 统一 prompt 附录数据 ──
    holdings_details: list[dict] | None = None,
    total_mv: float = 0.0,
    total_cost: float = 0.0,
    total_profit: float = 0.0,
) -> tuple[str | None, bool]:
    """标准 LLM 单篇生成模式：缓存 → 调用 → 处理结果。

    Args:
        system_prompt: 不为 None 时覆盖 system prompt（不走 llm_config 配置）。
        user_prompt: 不为 None 时跳过 prompt_builder，直接使用此值。
    """
    cache_enabled = llm_config.get(f"cache_enabled_{module_key}", True)

    if system_prompt is not None:
        _system = system_prompt
    else:
        _system = llm_config.get(f"system_prompt_{module_key}") or system_prompt_default
        if llm_config.get(f"output_brief_{module_key}", False):
            _system += f"\n（精简模式，输出 {output_brief_limit} 字以内。）"

    if user_prompt is not None:
        _user = user_prompt
    else:
        _user = prompt_builder() if prompt_builder else ""

    # ── 统一注入 prompt 附录（TOP3 + 数据速查表 + 代码白名单） ──
    if _user:
        appendix = _build_prompt_appendix(holdings_details, total_mv, total_cost, total_profit)
        if appendix:
            _user = _user + "\n\n" + appendix

    fingerprint = fingerprint_fn() if fingerprint_fn else ""
    cache_key = CACHE_PREFIX_LLM + f"{module_key}_{fingerprint}"

    return generate_llm_content(
        llm_config,
        cache_key,
        get_cache_ttl_llm(module_key),
        _system,
        _user,
        cache_enabled,
        force,
        max_tokens=llm_config.get(f"max_tokens_{module_key}", max_tokens_default),
        timeout=llm_config.get(f"timeout_{module_key}", timeout_default),
        temperature=llm_config.get(f"temperature_{module_key}"),
        model=llm_config.get(f"model_{module_key}"),
        config_field=f"max_tokens_{module_key}",
        http_client=http_client,
        thinking_enabled=llm_config.get(f"thinking_enabled_{module_key}", False),
        module_key=module_key,
    )


def generate_llm_module(
    llm_config: dict | None,
    module_key: str,
    *,
    force: bool = False,
    http_client: httpx.Client | None = None,
    fingerprint_fn: Any = None,
    system_prompt_default: str = "",
    prompt_builder: Any = None,
    max_tokens_default: int = 4096,
    timeout_default: float = 120.0,
    output_brief_limit: int = 300,
    # ── 辩论模式覆盖参数（None 时使用默认行为） ──
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    # ── 批量模式 hooks（用于 news_correlation 类模块） ──
    batch_preparer: Any = None,  # fn() → (items, context) or None（None=标准模式）
    per_item_cache_fn: Any = None,  # fn(index, item, context_fp) → cache_key or None
    batch_prompt_fn: Any = None,  # fn(batch_items, context) → user_prompt 字符串
    response_parser: Any = None,  # fn(batch_items, llm_response) → [parsed 列表]
    # ── 统一 prompt 附录数据（自动注入 TOP3/速查表/白名单） ──
    holdings_details: list[dict] | None = None,
    total_mv: float = 0.0,
    total_cost: float = 0.0,
    total_profit: float = 0.0,
) -> Any:
    """通用 LLM 模块生成骨架。

    标准模式（无 batch_preparer）：生成单篇分析内容。
    批量模式（有 batch_preparer）：逐条缓存、分批并行、JSON 解析。

    标准模式返回 (HTML 或 None, 是否来自缓存)。
    批量模式返回 (results_dict, all_cached, token_usage, cached_count)。
    """
    if llm_config is None:
        llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，%s 使用占位文本", _MN(module_key))
        LLM_MODULE_FAILURE[module_key] = FAIL_REASON_NOT_CONFIGURED
        if batch_preparer:
            return ({}, False, {}, 0)
        return (None, False)

    if not is_llm_module_enabled(llm_config, module_key):
        logger.info("%s LLM 分析已禁用（enabled_llm.%s = false）", _MN(module_key), module_key)
        LLM_MODULE_FAILURE[module_key] = FAIL_REASON_DISABLED
        if batch_preparer:
            return ({}, False, {}, 0)
        return (None, False)

    # ── 批量模式分支 ─────────────────────────────────────
    if batch_preparer is not None:
        return run_batch_mode(
            llm_config,
            module_key,
            force=force,
            batch_preparer=batch_preparer,
            per_item_cache_fn=per_item_cache_fn,
            batch_prompt_fn=batch_prompt_fn,
            response_parser=response_parser,
            system_prompt_default=system_prompt_default,
            max_tokens_default=max_tokens_default,
            timeout_default=timeout_default,
        )

    # ── 标准模式（4 个分析模块） ───────────────────────────
    return _run_standard_mode(
        llm_config,
        module_key,
        force,
        http_client,
        fingerprint_fn,
        system_prompt_default,
        prompt_builder,
        max_tokens_default,
        timeout_default,
        output_brief_limit,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        holdings_details=holdings_details,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
    )


# bridge import — run_batch_mode 批量处理入口
from src.python.llm._batch_mode import run_batch_mode  # noqa: F811, E402, E501
