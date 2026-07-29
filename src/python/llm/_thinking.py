"""Extended Thinking 配置。

提供 Claude/Gemini 的 thinking 参数注入功能，
包含默认模型名常量和认知预算解析函数。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from src.python.llm.api_base import _is_effort_model, _supports_extended_thinking

logger = logging.getLogger("invest")

# ── 默认模型名（Provider 未指定时使用） ─────────────────
_DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"
_DEFAULT_OPENAI_MODEL = "gpt-4o"
_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _resolve_thinking_budget(llm_config: dict, config_field: str, max_tokens: int) -> int:
    """从 llm_config 解析 Extended Thinking budget_tokens，失败时自动兜底。

    Args:
        llm_config: LLM 配置字典
        config_field: 如 ``"max_tokens_expert_review"``
        max_tokens: 模块 max_tokens 值，用于兜底计算

    Returns:
        budget_tokens 值
    """
    module_suffix = config_field.replace("max_tokens_", "")
    budget_key = f"thinking_budget_{module_suffix}"
    budget = llm_config.get(budget_key)
    if not budget or budget < max_tokens + 1024:
        budget = max_tokens + 4096  # 自动兜底
    return budget


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

    Args:
        payload: API 请求体（原地修改）
        llm_config: LLM 合并配置
        config_field: 如 ``"max_tokens_expert_review"``
        model: 模型名
        max_tokens: max_tokens 值
    """
    if not llm_config:
        return

    module_suffix = config_field.replace("max_tokens_", "")
    thinking_key = f"thinking_enabled_{module_suffix}"
    if not llm_config.get(thinking_key, False):
        return

    resolved_model = model or _DEFAULT_CLAUDE_MODEL
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
        budget = _resolve_thinking_budget(llm_config, config_field, max_tokens)
        payload["thinking"]["budget_tokens"] = budget
        logger.info("Extended Thinking 已开启 [%s]: budget=%d", module_suffix, budget)
