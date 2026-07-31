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
