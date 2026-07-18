"""LLM API 调用模块 — Provider 路由、Extended Thinking、调用实现。

R-198 拆分后：仅包含 Provider 路由 + Thinking 注入 + 5 个核心函数。
基础设施（常量/重试/截断/内容提取/失败追踪）位于 api_base.py。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

from src.python.llm.api_base import (
    _check_claude_truncation,
    _check_gemini_truncation,
    _check_openai_truncation,
    _extract_content,
    _extract_content_from_gemini,
    _get_last_llm_failure,
    _get_retry_max,
    _is_effort_model,
    _supports_extended_thinking,
    call_llm_with_retry,
)
from src.python.llm.prompts import (
    FAIL_REASON_API_ERROR,
    FAIL_REASON_CIRCUIT_OPEN,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_TIMEOUT,
    LLM_MODULE_FAILURE,
)
from src.python.llm.strategy import resolve_provider_chain

logger = logging.getLogger("invest")

__all__ = [
    "call_llm",
    "call_single_provider",
    "call_claude",
    "call_openai",
    "call_gemini",
    "configure_extended_thinking",
]

# ── 内容过滤安抚重试 ────────────────────────────────

_CONTENT_FILTER_RECOVERY = (
    "\n\n注意：请确保你的回答包含实质性的分析内容。"
    "如果前一版本未输出任何内容，请提供完整的分析结果。"
    "所有数据均基于公开市场信息，请客观分析即可。"
)
"""当 API 返回空内容（可能被内容过滤机制拦截）时，
追加到 system prompt 尾部重新请求。"""


def _resolve_entry_credentials(
    entry: dict,
    llm_config: dict | None,
) -> tuple[str, str, str]:
    """从 provider entry 解析 api_key / model / endpoint。

    优先 credentials_ref → llm_key.json 多键凭据，entry 级字段可叠加覆盖。
    无 credentials_ref 时回退 entry 内联字段。

    Returns:
        (api_key, model, endpoint)
    """
    api_key = entry.get("api_key", "")
    model = entry.get("model", "")
    endpoint = entry.get("endpoint") or ""

    creds_ref = entry.get("credentials_ref")
    if creds_ref and llm_config:
        all_creds = llm_config.get("_llm_credentials", {})
        ref_creds = all_creds.get(creds_ref, {})
        if isinstance(ref_creds, dict):
            if not api_key:
                api_key = ref_creds.get("api_key", "")
            if not model:
                model = ref_creds.get("model", "")
            if not endpoint:
                endpoint = ref_creds.get("endpoint", "") or ""

    return (api_key, model, endpoint)


def _resolve_first_provider_model_endpoint(
    llm_config: dict,
    module_key: str,
) -> tuple[str | None, str]:
    """从多链配置的首个 chain entry 解析 model 和 endpoint。

    仅当存在 _provider_list 且 module_key 非空时生效。
    非多链模式返回 (None, "")。

    Returns:
        (model_name, endpoint) — model 为解析后的模型名（含 credentials_ref），
        endpoint 为解析后的 API 地址
    """
    provider_list = llm_config.get("_provider_list")
    if not provider_list or not module_key:
        return (None, "")
    strategy = llm_config.get("_strategy", "priority")
    preferred = llm_config.get("_preferred_providers", {})
    try:
        from src.python.llm.strategy import resolve_provider_chain

        chain = resolve_provider_chain(provider_list, strategy, module_key, preferred)
        entry = chain[0] if chain else None
        if entry:
            _, model, endpoint = _resolve_entry_credentials(entry, llm_config)
            return (model, endpoint or "")
    except Exception:
        pass
    return (None, "")


def _infer_module_key(config_field: str) -> str:
    """从 config_field 推导 module_key。

    "max_tokens_global_macro" → "global_macro"
    "max_tokens" → ""（用不到 inference 的模块）
    "max_tokens_expert_review" → "expert_review"
    """
    if not config_field or not config_field.startswith("max_tokens_"):
        return ""
    return config_field[len("max_tokens_") :]


def _call_provider_entry(
    entry: dict,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout: float,
    max_retries: int,
    http_client: httpx.Client | None,
    config_field: str,
    temperature: float | None,
    llm_config: dict | None,
) -> tuple[str | None, dict | None]:
    """从 provider entry dict 提取参数，委托给 call_single_provider。

    内部处理空内容安抚重试（限制在当前 provider 内，不触发 chain 切换）。

    凭据解析优先级：
      credentials_ref → llm_key.json 中同名键 → entry 内联字段覆盖。
    """
    name = entry.get("name", "unknown")
    resolved_api_key, resolved_model, resolved_endpoint = _resolve_entry_credentials(entry, llm_config)
    provider_type = entry["provider"]
    entry_timeout = entry.get("timeout", timeout)

    def _do_call(sys: str, usr: str) -> tuple[str | None, dict | None]:
        return call_single_provider(
            provider=provider_type,
            system_prompt=sys,
            user_prompt=usr,
            api_key=resolved_api_key,
            resolved_model=resolved_model,
            endpoint=resolved_endpoint,
            max_tokens=max_tokens,
            timeout=entry_timeout,
            max_retries=max_retries,
            http_client=http_client,
            config_field=config_field,
            temperature=temperature,
            llm_config=llm_config,
        )

    result, usage = _do_call(system_prompt, user_prompt)
    # 空内容 → 安抚重试（仅一次）
    if result is not None and result == "":
        logger.warning("%s API 返回空内容，追加安抚指令重试一次", name)
        calmed_system = system_prompt + _CONTENT_FILTER_RECOVERY
        result2, usage2 = _do_call(calmed_system, user_prompt)
        if result2 and result2.strip():
            logger.info("%s 安抚重试成功", name)
            return result2, usage2
        logger.warning("%s 安抚重试后仍返回空内容，切换下一 provider", name)
        return (None, None)
    return result, usage


def call_single_provider(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    resolved_model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float,
    max_retries: int,
    http_client: httpx.Client | None,
    config_field: str,
    temperature: float | None,
    llm_config: dict | None,
) -> tuple[str | None, dict | None]:
    """调用单个 LLM provider。"""
    if provider == "claude":
        return call_claude(
            system_prompt,
            user_prompt,
            api_key,
            resolved_model,
            endpoint,
            max_tokens,
            timeout,
            max_retries=max_retries,
            http_client=http_client,
            config_field=config_field,
            temperature=temperature,
            llm_config=llm_config,
        )
    elif provider == "openai":
        return call_openai(
            system_prompt,
            user_prompt,
            api_key,
            resolved_model,
            endpoint,
            max_tokens,
            timeout,
            max_retries=max_retries,
            http_client=http_client,
            config_field=config_field,
            temperature=temperature,
        )
    elif provider == "gemini":
        return call_gemini(
            system_prompt,
            user_prompt,
            api_key,
            resolved_model,
            endpoint,
            max_tokens,
            timeout,
            max_retries=max_retries,
            http_client=http_client,
            config_field=config_field,
            temperature=temperature,
            llm_config=llm_config,
        )
    else:
        logger.warning("不支持的 LLM provider: %s", provider)
        return (None, None)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    llm_config: dict,
    timeout: float = 60.0,
    http_client: httpx.Client | None = None,
    max_tokens: int | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
    model: str | None = None,
) -> tuple[str | None, dict | None, dict | None]:
    """调用 LLM API 生成文本（多 Provider 链式）。

    按 provider 链依次尝试，第一个成功即返回。
    全部失败返回 (None, None, None)。

    Args:
        同前，新增返回值第三元组 provider_info。

    Returns:
        (content, usage, provider_info)
        — provider_info dict: {"name": entry名, "model": 解析后的模型名, "endpoint": 解析后的 endpoint}
          全部失败时为 None
    """
    provider_list = llm_config.get("_provider_list")
    if not provider_list:
        # 无多链配置，回退旧模式（兼容过渡期）
        return _call_llm_legacy(
            system_prompt, user_prompt, llm_config, timeout, http_client, max_tokens, config_field, temperature, model
        )

    # 多链模式
    strategy = llm_config.get("_strategy", "priority")
    preferred = llm_config.get("_preferred_providers", {})
    module_key = _infer_module_key(config_field)

    chain = resolve_provider_chain(provider_list, strategy, module_key, preferred)
    if not chain:
        logger.warning("resolve_provider_chain 返回空列表")
        return (None, None, None)

    max_retries = _get_retry_max(llm_config)
    resolved_max_tokens = max_tokens or 2500

    attempted: list[str] = []

    for entry in chain:
        name = entry.get("name", "unknown")
        entry_api_key, entry_model, entry_endpoint = _resolve_entry_credentials(entry, llm_config)
        provider_type = entry["provider"]
        _entry_desc = f"{name}({provider_type}/{entry_model})"
        if entry_endpoint:
            _entry_desc += f" [{entry_endpoint}]"
        logger.info("尝试 provider: %s", _entry_desc)
        try:
            result, usage = _call_provider_entry(
                entry,
                system_prompt,
                user_prompt,
                resolved_max_tokens,
                timeout,
                max_retries,
                http_client,
                config_field,
                temperature,
                llm_config,
            )
            if result is not None:
                logger.info("provider 成功: %s", _entry_desc)
                attempted.append(f"{name}: SUCCESS")
                if module_key:
                    LLM_MODULE_FAILURE[module_key] = {
                        "attempted": attempted,
                        "final_status": "success",
                    }
                return (result, usage, {"name": name, "model": entry_model, "endpoint": entry_endpoint or ""})
            else:
                reason = _get_last_llm_failure() or FAIL_REASON_API_ERROR
                logger.warning("provider %s 失败（%s），切换下一 provider", _entry_desc, reason)
                attempted.append(f"{name}: {reason}")
        except Exception:
            logger.warning("provider %s 异常，切换下一 provider", _entry_desc, exc_info=True)
            attempted.append(f"{name}: EXCEPTION")

    logger.warning("全部 provider 尝试失败")
    if module_key:
        # 从最后一次失败推论 final_status
        final_status = FAIL_REASON_API_ERROR
        if attempted:
            last_reason = attempted[-1].split(": ", 1)[-1]
            _known_reasons = {
                FAIL_REASON_TIMEOUT,
                FAIL_REASON_NETWORK_ERROR,
                FAIL_REASON_API_ERROR,
                FAIL_REASON_CIRCUIT_OPEN,
            }
            if last_reason in _known_reasons:
                final_status = last_reason
        LLM_MODULE_FAILURE[module_key] = {
            "attempted": attempted,
            "final_status": final_status,
        }
    return (None, None, None)


def _call_llm_legacy(
    system_prompt: str,
    user_prompt: str,
    llm_config: dict,
    timeout: float = 60.0,
    http_client: httpx.Client | None = None,
    max_tokens: int | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
    model: str | None = None,
) -> tuple[str | None, dict | None, dict | None]:
    """旧模式兼容（无 _provider_list 配置时回退）。"""
    provider = llm_config.get("provider", "")
    api_key = llm_config.get("api_key", "")
    resolved_model = model or llm_config.get("model", "")
    endpoint = llm_config.get("endpoint", "")
    resolved_max_tokens = max_tokens or 2500
    max_retries = _get_retry_max(llm_config)

    result, usage = call_single_provider(
        provider,
        system_prompt,
        user_prompt,
        api_key,
        resolved_model,
        endpoint,
        resolved_max_tokens,
        timeout,
        max_retries,
        http_client,
        config_field,
        temperature,
        llm_config,
    )
    if result is not None:
        if result != "":
            return result, usage, {"name": provider or None, "model": resolved_model, "endpoint": endpoint or ""}
        # 空内容 → 安抚重试
        logger.warning("%s API 返回空内容，追加安抚指令重试一次", provider)
        calmed_system = system_prompt + _CONTENT_FILTER_RECOVERY
        result2, usage2 = call_single_provider(
            provider,
            calmed_system,
            user_prompt,
            api_key,
            resolved_model,
            endpoint,
            resolved_max_tokens,
            timeout,
            max_retries,
            http_client,
            config_field,
            temperature,
            llm_config,
        )
        if result2 and result2.strip():
            logger.info("安抚重试成功")
            return result2, usage2, {"name": provider or None, "model": resolved_model, "endpoint": endpoint or ""}
        logger.warning("安抚重试后仍返回空内容")

    # 回退 provider（旧 fallback 字段）
    fallback_provider = llm_config.get("fallback_provider", "")
    if fallback_provider and fallback_provider != provider:
        fb_api_key = llm_config.get("fallback_api_key", api_key)
        fb_endpoint = llm_config.get("fallback_endpoint", endpoint)
        fb_model = llm_config.get("fallback_model", resolved_model)
        logger.warning("主 provider (%s) 已失败，回退到 %s", provider, fallback_provider)
        result, usage = call_single_provider(
            fallback_provider,
            system_prompt,
            user_prompt,
            fb_api_key,
            fb_model,
            fb_endpoint,
            resolved_max_tokens,
            timeout,
            max_retries,
            http_client,
            config_field,
            temperature,
            llm_config,
        )
        if result is not None:
            return result, usage, {"name": fallback_provider or None, "model": fb_model, "endpoint": fb_endpoint or ""}
        logger.warning("回退 provider (%s) 同样失败", fallback_provider)

    return (None, None, None)


def configure_extended_thinking(
    payload: dict,
    llm_config: dict | None,
    config_field: str,
    model: str,
    max_tokens: int,
) -> None:
    """如果开启，在 payload 中注入 Extended Thinking 参数（原地修改）。

    根据模型类型选择 effort（DeepSeek）或 budget_tokens（Anthropic）控制思考深度。
    若模型不支持则自动降级跳过。
    """
    if not llm_config:
        return

    module_suffix = config_field.replace("max_tokens_", "")
    thinking_key = f"thinking_enabled_{module_suffix}"
    if not llm_config.get(thinking_key, False):
        return

    resolved_model = model or "claude-sonnet-4-20250514"
    if not _supports_extended_thinking(resolved_model):
        logger.warning(
            "模型 %s 不支持 Extended Thinking，已自动降级跳过 [%s]",
            resolved_model,
            module_suffix,
        )
        return

    payload["thinking"] = {"type": "enabled"}
    payload.pop("temperature", None)  # Extended Thinking 与 temperature 互斥

    if _is_effort_model(resolved_model):
        effort_key = f"reasoning_effort_{module_suffix}"
        effort = llm_config.get(effort_key, "high")
        payload["output_config"] = {"effort": effort}
        logger.info("Extended Thinking 已开启 [%s]: effort=%s", module_suffix, effort)
    else:
        budget_key = f"thinking_budget_{module_suffix}"
        budget = llm_config.get(budget_key)
        if not budget or budget < max_tokens + 1024:
            budget = max_tokens + 4096  # 自动兜底
        payload["thinking"]["budget_tokens"] = budget
        logger.info("Extended Thinking 已开启 [%s]: budget=%d", module_suffix, budget)


def call_claude(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
    max_retries: int = 2,
    http_client: httpx.Client | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, dict | None]:
    """调用 Claude API (Messages API)，带重试 + 用量日志。

    实际 HTTP 重试逻辑委托给 _call_llm_with_retry。
    system prompt 使用数组格式 + cache_control 以支持 Anthropic Prompt Caching
    （同一 system prompt 在 5 分钟内多次调用时节省输入 token）。

    支持 Extended Thinking（thinking 参数），通过 llm_settings.json 中
    thinking_enabled_{模块} / thinking_budget_{模块} 配置开启。
    推荐仅在智囊团深度复盘（expert_review）场景开启，全球政经局势和财经新闻热点与持仓关联分析收益有限。
    若模型不支持 Extended Thinking（如 claude-sonnet-3-5），自动降级跳过。

    Args:
        max_retries: 最大重试次数，从 llm_config 读取
        temperature: 若不为 None，覆盖 payload 中的 temperature 字段
        llm_config: LLM 合并配置，用于读取 thinking 配置项

    Returns:
        (content, usage) — usage 为 API 返回的用量字典，失败时均为 None
    """
    url = endpoint or "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    # 数组格式 + cache_control 支持 Prompt Caching
    payload = {
        "model": model or "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }
    # ── Extended Thinking（根据模型类型 + 模块配置） ──
    configure_extended_thinking(payload, llm_config, config_field, model, max_tokens)
    if temperature is not None and "thinking" not in payload:
        payload["temperature"] = temperature
    client = http_client
    assert client is not None

    return call_llm_with_retry(
        label="Claude",
        client=client,
        url=url,
        headers=headers,
        payload=payload,
        timeout=timeout,
        max_retries=max_retries,
        max_tokens=max_tokens,
        config_field=config_field,
        extract_fn=_extract_content,
        check_truncation_fn=lambda d, mt: _check_claude_truncation(d, mt, "Claude", config_field),
        provider="claude",
        model_name=model,
    )


def call_openai(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
    max_retries: int = 2,
    http_client: httpx.Client | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
) -> tuple[str | None, dict | None]:
    """调用 OpenAI API (Chat Completions)，带重试 + 用量日志。

    实际 HTTP 重试逻辑委托给 _call_llm_with_retry。

    Args:
        max_retries: 最大重试次数，从 llm_config 读取
        temperature: 若不为 None，覆盖 payload 中的 temperature 字段

    Returns:
        (content, usage) — usage 为 API 返回的用量字典，失败时均为 None
    """
    url = endpoint or "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model or "gpt-4o",
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    client = http_client
    assert client is not None

    def _extract_openai(data: dict) -> str | None:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

    return call_llm_with_retry(
        label="OpenAI",
        client=client,
        url=url,
        headers=headers,
        payload=payload,
        timeout=timeout,
        max_retries=max_retries,
        max_tokens=max_tokens,
        config_field=config_field,
        extract_fn=_extract_openai,
        check_truncation_fn=lambda d, mt: _check_openai_truncation(d, mt, "OpenAI", config_field),
        provider="openai",
        model_name=model,
    )


def call_gemini(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
    max_retries: int = 2,
    http_client: httpx.Client | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, dict | None]:
    """调用 Google Gemini API (generateContent)，带重试 + 用量日志。

    Gemini API 使用 x-goog-api-key header 认证，模型名嵌入 URL 路径。
    支持 system instruction（通过 systemInstruction 字段）和 generationConfig。

    Args:
        max_retries: 最大重试次数，从 llm_config 读取
        temperature: 若不为 None，覆盖 generationConfig 中的 temperature 字段

    Returns:
        (content, usage) — usage 为标准化后的用量字典，失败时均为 None
    """
    url = (
        f"{endpoint.rstrip('/')}/models/{model}:generateContent"
        if endpoint
        else f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": user}]},
        ],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "maxOutputTokens": max_tokens,
        },
    }
    if temperature is not None:
        payload["generationConfig"]["temperature"] = temperature

    # ── Gemini Extended Thinking（通过 generationConfig.thinkingConfig） ──
    if llm_config:
        module_suffix = config_field.replace("max_tokens_", "")
        if llm_config.get(f"thinking_enabled_{module_suffix}", False):
            resolved_model = model or "gemini-2.5-flash"
            if _supports_extended_thinking(resolved_model):
                budget_key = f"thinking_budget_{module_suffix}"
                budget = llm_config.get(budget_key)
                if not budget or budget < max_tokens + 1024:
                    budget = max_tokens + 4096
                payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": budget}
                payload["generationConfig"].pop("temperature", None)
                logger.info("Gemini Extended Thinking 已开启 [%s]: budget=%d", module_suffix, budget)
            else:
                logger.warning("模型 %s 不支持 Extended Thinking，已自动降级跳过 [%s]", resolved_model, module_suffix)

    client = http_client
    assert client is not None

    return call_llm_with_retry(
        label="Gemini",
        client=client,
        url=url,
        headers=headers,
        payload=payload,
        timeout=timeout,
        max_retries=max_retries,
        max_tokens=max_tokens,
        config_field=config_field,
        extract_fn=_extract_content_from_gemini,
        check_truncation_fn=lambda d, mt: _check_gemini_truncation(d, mt, "Gemini", config_field),
        provider="gemini",
        model_name=model,
    )
