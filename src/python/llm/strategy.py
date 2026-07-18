"""Provider 策略引擎 — resolve_provider_chain() 与各策略实现。

策略类型：
  - priority（默认）：按 priority 字段升序，同 priority 保持原序
  - weighted（R5）：按 weight 权重随机排序
  - cost_first（R9）：按模型定价升序
  - fallback_only（R3）：与 priority 同，语义表示为失败回退场景

后置步骤：
  - _apply_module_preferred()：模块偏好 provider 排首
  - _apply_proxy_preferred()（R4）：有代理时 proxy_preferred 排首
"""

from __future__ import annotations

import logging
import os
import random
from typing import Any

logger = logging.getLogger("invest")

_VALID_STRATEGIES = frozenset({"priority", "weighted", "cost_first", "fallback_only"})


def resolve_provider_chain(
    provider_list: list[dict],
    strategy: str = "priority",
    module_key: str = "",
    preferred: dict[str, str] | None = None,
) -> list[dict]:
    """返回按策略排序的 provider 尝试列表。

    Args:
        provider_list: _parse_providers_list() 输出的 provider 列表
        strategy: 策略名（"priority" / "weighted" / "cost_first" / "fallback_only"）
        module_key: 当前模块键（用于 preferred 匹配）
        preferred: {module_key: provider_name} 偏好映射

    Returns:
        排序后的 provider 尝试列表，空输入返回 []
    """
    if not provider_list:
        return []

    # 未知策略 → WARNING + 回退 priority
    if strategy not in _VALID_STRATEGIES:
        logger.warning("未知策略 '%s'，回退到 'priority'", strategy)
        strategy = "priority"

    # step 1: 策略排序
    if strategy in ("priority", "fallback_only"):
        chain = sorted(provider_list, key=lambda p: p.get("priority", 99))
    elif strategy == "weighted":
        chain = _apply_weighted(provider_list)
    elif strategy == "cost_first":
        chain = _apply_cost_first(provider_list)
    else:
        chain = list(provider_list)

    # step 2: 模块偏好注入
    chain = _apply_module_preferred(chain, module_key, preferred or {})

    # step 3: 代理偏好注入（R4 扩展点）
    chain = _apply_proxy_preferred(chain)

    return chain


# ── Module Preferred ─────────────────────────────────────────


def _apply_module_preferred(
    chain: list[dict],
    module_key: str,
    preferred: dict[str, str],
) -> list[dict]:
    """模块偏好 provider 移至列表首位。"""
    if not module_key or not preferred:
        return chain
    preferred_name = preferred.get(module_key)
    if not preferred_name:
        return chain

    matched = [p for p in chain if p["name"] == preferred_name]
    others = [p for p in chain if p["name"] != preferred_name]
    if not matched:
        logger.warning("模块 '%s' 偏好的 provider '%s' 不存在于 provider 列表中", module_key, preferred_name)
        return chain

    return matched + others


# ── Proxy Preferred ──────────────────────────────────────────


def _detect_proxy() -> bool:
    """检测系统代理环境变量，任一非空即返回 True。"""
    return any(os.environ.get(v, "") for v in
               ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"])


def _apply_proxy_preferred(chain: list[dict]) -> list[dict]:
    """有代理时，proxy_preferred=True 的 provider 排在无标记之前。"""
    if not _detect_proxy():
        return chain
    preferred = [p for p in chain if p.get("proxy_preferred")]
    others = [p for p in chain if not p.get("proxy_preferred")]
    if not preferred:
        return chain
    return preferred + others


# ── Weighted ─────────────────────────────────────────────────


def _apply_weighted(provider_list: list[dict]) -> list[dict]:
    """根据 weight 权重随机排序。

    - 权重 0 的 provider 不参与选择
    - 全部权重为 0 → WARNING + 回退 priority 排序
    """
    nonzero = [(i, p) for i, p in enumerate(provider_list) if p.get("weight", 1) > 0]
    if not nonzero:
        logger.warning("Weighted 策略所有 provider 权重全为 0，回退到 priority 排序")
        return sorted(provider_list, key=lambda p: p.get("priority", 99))

    indices, candidates = zip(*nonzero)
    weights = [p.get("weight", 1) for p in candidates]

    # random.choices 不保证包含全部元素，改用 shuffle + 权重的排列策略：
    # 1. 按权重出现概率：将元素按权重展开放入池
    # 2. 打乱后去重取序
    pool: list[int] = []
    for idx_in_group, w in enumerate(weights):
        pool.extend([idx_in_group] * max(w, 1))
    random.shuffle(pool)
    seen: set[int] = set()
    order: list[int] = []
    for idx_in_group in pool:
        if idx_in_group not in seen:
            seen.add(idx_in_group)
            order.append(idx_in_group)
    # 补上未在 pool 中出现的原序（理论上不会发生，但防御性编程）
    for i in range(len(candidates)):
        if i not in seen:
            order.append(i)

    result = [candidates[i] for i in order]
    return result


# ── Cost First ────────────────────────────────────────────────


def _apply_cost_first(provider_list: list[dict]) -> list[dict]:
    """按模型 input_price + output_price 升序排列。

    未知模型（定价表无数据）cost_score = float("inf")，排末尾。
    全部未知时保持原序。
    """
    try:
        from src.python.llm.pricing import PRICING_MERGED, reload_pricing
        if not PRICING_MERGED:
            reload_pricing()
    except ImportError:
        pass

    def _get_cost_score(p: dict) -> float:
        model = p.get("model", "")
        try:
            from src.python.llm.pricing import PRICING_MERGED
            pricing = PRICING_MERGED.get(model)
            if pricing:
                return pricing.get("input_price", 0) + pricing.get("output_price", 0)
        except (ImportError, AttributeError):
            pass
        return float("inf")

    # 已知与未知分组，已知按 cost 升序，未知保持原序
    known = [p for p in provider_list if _get_cost_score(p) != float("inf")]
    unknown = [p for p in provider_list if _get_cost_score(p) == float("inf")]
    known.sort(key=_get_cost_score)
    return known + unknown
