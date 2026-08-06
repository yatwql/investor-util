"""Claude API 调用实现。

仅包含 call_claude 一个公开函数，以及完全自包含的 import 依赖。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

from src.python.llm.api_base import (
    _extract_content,
    _check_claude_truncation,
    _get_last_thinking_exhausted,
    _is_effort_model,
    clear_last_thinking_exhausted,
    call_llm_with_retry,
)
from src.python.llm.api import (
    _DEFAULT_CLAUDE_MODEL,
    configure_extended_thinking,
)

logger = logging.getLogger("invest")


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

    实际 HTTP 重试逻辑委托给 call_llm_with_retry。
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
        "model": model or _DEFAULT_CLAUDE_MODEL,
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

    def _do_call(p: dict) -> tuple[str | None, dict | None]:
        return call_llm_with_retry(
            label="Claude",
            client=client,
            url=url,
            headers=headers,
            payload=p,
            timeout=timeout,
            max_retries=max_retries,
            max_tokens=max_tokens,
            config_field=config_field,
            extract_fn=_extract_content,
            check_truncation_fn=lambda d, mt: _check_claude_truncation(d, mt, "Claude", config_field),
            provider="claude",
            model_name=model,
        )

    # ── 空响应安全网：DeepSeek 等强制推理模型在以下场景返回无正文时，
    #    关闭 thinking 同 provider 重试一次，保证有正文产出，避免直接切 provider 丢模块内容。
    #    A. 思考耗尽：max_tokens（thinking+正文共享预算）被思考占满，响应仅含 thinking
    #       block、无正文（stop_reason=max_tokens）
    #    B. 偶发空 content：DeepSeek 端点在多模块并发下偶发返回 HTTP 200 但 content
    #       为空（stop_reason 非 max_tokens），直接切 provider 会丢模块整章（gemini
    #       不支持 thinking → 模块整章降级占位）。对强制推理模型同样触发重试兜底。 ──
    thinking_was_enabled = "thinking" in payload
    call_result = _do_call(payload)
    # 触发条件放宽到 DeepSeek 强制推理模型：即使 thinking_enabled=false（payload 无
    # thinking 参数），DeepSeek 兼容端点也会落入默认思考模式（effort=high）并占满
    # max_tokens 耗尽，同样需要安全网兜底。非 effort 模型仍需显式开启 thinking 才重试。
    _is_forced_reasoning = bool(model) and _is_effort_model(model)
    _thinking_exhausted = _get_last_thinking_exhausted()
    if call_result[0] is None and (_is_forced_reasoning or (_thinking_exhausted and thinking_was_enabled)):
        if _thinking_exhausted:
            logger.warning(
                "Extended Thinking 思考部分耗尽 max_tokens 预算（无正文），关闭 thinking 重试一次，避免模块整体失败"
            )
        else:
            logger.warning(
                "LLM 返回空 content（非思考耗尽，疑似服务端偶发空响应），关闭 thinking 重试一次，避免模块整体失败"
            )
        # 构建全新 payload，避免污染首次请求记录
        retry_payload = dict(payload)
        if _is_forced_reasoning:
            # DeepSeek Anthropic 兼容端点思考默认开启：仅移除 thinking 参数会回到默认
            # 思考模式，必须显式 disabled 才能真正关闭；且 thinking:disabled 与
            # output_config.effort / reasoning_effort 互斥（并存报 HTTP 400），一并移除。
            retry_payload["thinking"] = {"type": "disabled"}
            retry_payload.pop("output_config", None)
            retry_payload.pop("reasoning_effort", None)
        else:
            retry_payload.pop("thinking", None)
        # thinking 非 enabled（已禁用/已移除）时恢复 temperature（与 temperature 互斥
        # 的仅是思考开启状态，禁用后应允许温度生效）
        if temperature is not None and retry_payload.get("thinking", {}).get("type") != "enabled":
            retry_payload["temperature"] = temperature
        clear_last_thinking_exhausted()
        call_result = _do_call(retry_payload)
    return call_result
