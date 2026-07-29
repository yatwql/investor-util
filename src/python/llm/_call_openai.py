"""OpenAI API 调用实现。

包含 call_openai 单 Provider 调用函数。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

from src.python.llm._thinking import _DEFAULT_OPENAI_MODEL
from src.python.llm.api_base import _check_openai_truncation, call_llm_with_retry

logger = logging.getLogger("invest")


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

    实际 HTTP 重试逻辑委托给 :func:`call_llm_with_retry`。

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
        "model": model or _DEFAULT_OPENAI_MODEL,
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
