"""LLM 生成模块 — 全局政经/智囊团/体检/穿透四大单例函数。

R-198 拆分后职责：
  - 4 个单例生成函数（generate_global_macro 等）
  - 批量编排 → generators_orchestrator.py
  - 新闻关联 → generators_news.py
"""

from __future__ import annotations

from typing import Any

import httpx

from src.python.llm.fingerprint import (
    _build_llm_fingerprint,
    _compute_fingerprint,
)
from src.python.llm.prompts import (
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_GLOBAL_MACRO,
    _SYSTEM_HEALTH_CHECK,
    _SYSTEM_PENETRATION_DEEP,
    _build_expert_review_prompt,
    _build_global_macro_prompt,
    _build_health_check_prompt,
    _build_penetration_deep_prompt,
)
from src.python.llm.skeleton import _generate_llm_module

__all__ = [
    "generate_global_macro",
    "generate_expert_review",
    "generate_health_check",
    "generate_penetration_deep_analysis",
]


def generate_global_macro(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_profit: float,
    categories: dict,
    sector_flow: list[dict[str, Any]] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, bool]:
    """生成全球政经局势。"""
    def _fingerprint():
        return _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    def _prompt():
        return _build_global_macro_prompt(a_indices, us_indices, total_mv, total_profit, categories, sector_flow)
    return _generate_llm_module(
        llm_config, "global_macro",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_GLOBAL_MACRO,
        prompt_builder=_prompt,
        max_tokens_default=800,
        timeout_default=60.0,
        output_brief_limit=200,
    )


def generate_expert_review(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    f_context: dict | None = None,
) -> tuple[str | None, bool]:
    """生成智囊团深度复盘。"""
    def _fingerprint():
        return _build_llm_fingerprint(
            total_mv=total_mv, total_cost=total_cost,
            total_profit=total_profit, total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
        )
    def _prompt():
        return _build_expert_review_prompt(
            total_mv, total_cost, total_profit, total_today_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details,
            f_context=f_context,
        )
    return _generate_llm_module(
        llm_config, "expert_review",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_EXPERT_REVIEW,
        prompt_builder=_prompt,
        max_tokens_default=8192,
        timeout_default=120.0,
        output_brief_limit=300,
    )


def generate_health_check(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    f_context: dict | None = None,
) -> tuple[str | None, bool]:
    """生成持仓体检报告。"""
    def _fingerprint():
        return _build_llm_fingerprint(
            total_mv=total_mv, total_cost=total_cost,
            total_profit=total_profit, total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
        )
    def _prompt():
        return _build_health_check_prompt(
            total_mv, total_cost, total_profit, total_today_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details,
            f_context=f_context,
        )
    return _generate_llm_module(
        llm_config, "health_check",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_HEALTH_CHECK,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=120.0,
        output_brief_limit=300,
    )


def generate_penetration_deep_analysis(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, bool]:
    """生成穿透深度分析。"""
    def _fingerprint():
        return _build_llm_fingerprint(
            total_mv=total_mv, total_cost=total_cost,
            total_profit=total_profit, total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
            full_penetration=True,
        )
    def _prompt():
        return _build_penetration_deep_prompt(
            total_mv, total_cost, total_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details,
        )
    return _generate_llm_module(
        llm_config, "penetration_deep",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_PENETRATION_DEEP,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=90.0,
        output_brief_limit=300,
    )



