"""LLM API 调用模块 — Provider 路由、Extended Thinking、调用实现。

R-198 拆分后：仅包含 Provider 路由 + Thinking 注入 + 5 个核心函数。
基础设施（常量/重试/截断/内容提取/失败追踪）位于 api_base.py。
"""

from __future__ import annotations

import logging

import httpx

from src.python.llm.api_base import (
    call_llm_with_retry,
    _check_claude_truncation,
    _check_openai_truncation,
    _extract_content,
    _get_retry_max,
    _is_effort_model,
    _supports_extended_thinking,
)

logger = logging.getLogger("invest")

__all__ = [
    "call_llm",
    "call_single_provider",
    "call_claude",
    "call_openai",
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
        return call_claude(system_prompt, user_prompt, api_key, resolved_model, endpoint,
                                max_tokens, timeout, max_retries=max_retries,
                                http_client=http_client, config_field=config_field,
                                temperature=temperature, llm_config=llm_config)
    elif provider == "openai":
        return call_openai(system_prompt, user_prompt, api_key, resolved_model, endpoint,
                                max_tokens, timeout, max_retries=max_retries,
                                http_client=http_client, config_field=config_field,
                                temperature=temperature)
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
) -> tuple[str | None, dict | None]:
    """调用 LLM API 生成文本。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        llm_config: LLM 配置字典
        timeout: API 超时秒数，默认 60s
        http_client: 可选的 httpx.Client 实例
        max_tokens: 可选覆盖值，优先级高于 llm_config 中的对应字段
        config_field: llm_settings.json 中的配置字段名，截断时在日志中提示用户增大该字段
        temperature: 可选覆盖值，优先级高于 llm_config 中的对应字段，None 表示使用 API 默认值
        model: 可选模型覆盖，优先级高于 llm_config 中的 model 字段（用于 per-module 路由）

    Returns:
        (content, usage) — content 为文本，usage 为 API 用量字典，失败时均为 None
    """
    provider = llm_config.get("provider", "")
    api_key = llm_config.get("api_key", "")
    resolved_model = model or llm_config.get("model", "")
    endpoint = llm_config.get("endpoint", "")
    max_tokens = max_tokens or 2500
    max_retries = _get_retry_max(llm_config)

    # ── 主 provider ──
    result, usage = call_single_provider(
        provider, system_prompt, user_prompt, api_key, resolved_model, endpoint,
        max_tokens, timeout, max_retries, http_client, config_field, temperature, llm_config,
    )
    if result is not None:
        if result != "":
            return result, usage
        # result == "" → 内容过滤导致空返回，尝试安抚重试
        logger.warning("%s API 返回空内容，追加安抚指令重试一次", provider)
        print(f"  [..] {provider} API 返回空内容，追加安抚指令重试...")
        calmed_system = system_prompt + _CONTENT_FILTER_RECOVERY
        result2, usage2 = call_single_provider(
            provider, calmed_system, user_prompt, api_key, resolved_model, endpoint,
            max_tokens, timeout, max_retries, http_client, config_field, temperature, llm_config,
        )
        if result2 and result2.strip():
            print("  [OK] 安抚重试成功")
            return result2, usage2
        logger.warning("安抚重试后仍返回空内容，继续尝试回退 provider")

    # ── 主 provider 失败 → 尝试回退 provider（若已配置） ──
    fallback_provider = llm_config.get("fallback_provider", "")
    if fallback_provider and fallback_provider != provider:
        fb_api_key = llm_config.get("fallback_api_key", api_key)
        fb_endpoint = llm_config.get("fallback_endpoint", endpoint)
        fb_model = llm_config.get("fallback_model", resolved_model)
        logger.warning("主 provider (%s) 已失败，回退到 %s", provider, fallback_provider)
        print(f"  [..] LLM 主 provider ({provider}) 失败，正在回退到 {fallback_provider}...")
        result, usage = call_single_provider(
            fallback_provider, system_prompt, user_prompt, fb_api_key, fb_model, fb_endpoint,
            max_tokens, timeout, max_retries, http_client, config_field, temperature, llm_config,
        )
        if result is not None:
            return result, usage
        logger.warning("回退 provider (%s) 同样失败", fallback_provider)

    return (None, None)


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
            resolved_model, module_suffix,
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
        label="Claude", client=client, url=url, headers=headers,
        payload=payload, timeout=timeout, max_retries=max_retries,
        max_tokens=max_tokens, config_field=config_field,
        extract_fn=_extract_content,
        check_truncation_fn=lambda d, mt: _check_claude_truncation(d, mt, "Claude", config_field),
        provider="claude", model_name=model,
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
        label="OpenAI", client=client, url=url, headers=headers,
        payload=payload, timeout=timeout, max_retries=max_retries,
        max_tokens=max_tokens, config_field=config_field,
        extract_fn=_extract_openai,
        check_truncation_fn=lambda d, mt: _check_openai_truncation(d, mt, "OpenAI", config_field),
        provider="openai", model_name=model,
    )
