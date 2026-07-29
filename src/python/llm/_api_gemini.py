"""Gemini API 调用实现。

仅包含 call_gemini 一个公开函数，以及完全自包含的 import 依赖。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

from src.python.llm.api_base import (
    _extract_content_from_gemini,
    _check_gemini_truncation,
    _supports_extended_thinking,
    call_llm_with_retry,
)
from src.python.llm.api import (
    _DEFAULT_GEMINI_MODEL,
    _resolve_thinking_budget,
)

logger = logging.getLogger("invest")


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
            resolved_model = model or _DEFAULT_GEMINI_MODEL
            if _supports_extended_thinking(resolved_model):
                budget = _resolve_thinking_budget(llm_config, config_field, max_tokens)
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
