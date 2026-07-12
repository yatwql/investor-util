"""Provider Chain 定义与通用 Fallback 获取器。

每类数据（price/index/rank/holding）对应一个 Provider Chain，
chain 中按优先级列出 provider，主链路失败后自动递补。
用户可通过 config.json 的 preferred_provider 手动指定首选链路。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from src.python.constants import CACHE_WEEKLY
from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.config import get_config
from src.python.provider_registry import get_registry, _TRANSPORT_FAILURE

logger = logging.getLogger("invest")

# ── Provider Chain 定义 ──────────────────────────────────────

_DEFAULT_CHAINS: dict[str, list[str]] = {
    "price_stock": ["tencent", "sina"],
    "price_fund_otc": ["eastmoney"],
    "price": ["tencent", "eastmoney"],
    "fund_rank": ["tiantian"],
    "fund_hold": ["tiantian"],
    "industry": ["eastmoney_industry", "eastmoney_industry_rest"],
}


def _get_chain(data_type: str) -> list[str]:
    """获取指定数据类型的 Provider Chain（考虑用户配置）。

    用户可在 config.json 中通过 preferred_provider.<data_type> 指定首选。
    """
    chain = list(_DEFAULT_CHAINS.get(data_type, []))
    try:
        config = get_config()
        preferred = (config.get("preferred_provider") or {}).get(data_type)
        if preferred and preferred in chain and chain[0] != preferred:
            chain.remove(preferred)
            chain.insert(0, preferred)
            logger.info("%s Provider Chain: 根据配置首选 '%s'", data_type, preferred)
    except (KeyError, TypeError):
        logger.debug("[chain] preferred_provider 配置解析失败，使用默认链")
    return chain


# ── 会话级 Provider 熔断（委托 DataSourceRegistry） ──────
# 熔断逻辑集中在 provider_registry.py：
#   - 连续 3 次传输级失败 → 熔断 300s → 冷却期满自动恢复
#   - record_failure(provider, context) / record_success(provider)
#   - is_circuit_broken(provider) → bool
#   - is_chain_broken(chain) → bool


def reset_provider_skip() -> None:
    """重置 Provider 熔断状态（测试用）。委托 DataSourceRegistry.reset()。"""
    get_registry().reset()


def is_provider_chain_broken(data_type: str) -> bool:
    """检查指定数据类型的全部 Provider 是否都已熔断。

    batch 入口调用一次即可预判全链不可用，避免逐条重复尝试。

    Returns:
        True — 链上所有 provider 均在熔断中，全链不可用
        False — 至少有一个 provider 可用
    """
    chain = _get_chain(data_type)
    if not chain:
        return True
    return get_registry().is_chain_broken(chain)

_ProviderFunc = Callable[..., dict[str, Any] | None]

# _TRANSPORT_FAILURE sentinel 定义于 provider_registry.py，
# 跨模块共享用于 _try_provider_fetch 的传输级异常标记。


# ── 通用带缓存的 Fallback 调用 ──────────────────────────────


def _try_provider_fetch(
    data_type: str,
    provider_name: str,
    source_label: str,
    fetch_fn: _ProviderFunc,
    kwargs: dict,
    validate: Callable[[dict[str, Any], str], bool] | None,
    transform: Callable[[dict[str, Any], str], dict[str, Any] | None]
              | dict[str, Callable[[dict[str, Any], str], dict[str, Any] | None]]
              | None,
) -> dict[str, Any] | None:
    """尝试调用单个 provider 的 fetch 函数，返回转换后的结果或 None。"""
    _code_tag = f" [{kwargs.get('code', '')}]" if kwargs.get("code") else ""
    try:
        raw = fetch_fn(**kwargs)
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str or "rate" in err_str.lower():
            logger.warning("[%s]%s %s API 限速(429): %s", data_type, _code_tag, provider_name, err_str)
        else:
            logger.warning("[%s]%s %s 调用异常: %s", data_type, _code_tag, provider_name, err_str)
        return cast("dict[str, Any] | None", _TRANSPORT_FAILURE)  # 传输级异常 → 应计入熔断

    if raw is None:
        logger.info("[%s]%s %s 返回空，尝试下一链路", data_type, _code_tag, provider_name)
        return None

    # 数据验证
    if validate:
        try:
            if not validate(raw, provider_name):
                logger.info("[%s] %s 数据验证未通过，尝试下一链路", data_type, provider_name)
                return None
        except Exception as e:
            logger.warning("[%s] %s 数据验证异常: %s", data_type, provider_name, e)
            return None

    # 应用数据转换
    try:
        if isinstance(transform, dict):
            fn = transform.get(provider_name)
            result = fn(raw, source_label) if fn else raw
        elif transform:
            result = transform(raw, source_label)
        else:
            result = raw
    except Exception as e:
        logger.warning("[%s] %s 数据转换失败: %s", data_type, provider_name, e)
        return None

    if result is not None:
        logger.info("[%s]%s %s 成功", data_type, _code_tag, provider_name)
    return result


def _fetch_with_fallback(
    data_type: str,
    provider_fn_map: dict[str, tuple[str, _ProviderFunc]],
    cache_key: str,
    cache_ttl: float,
    fn_kwargs: dict[str, Any] | None = None,
    transform: Callable[[dict[str, Any], str], dict[str, Any] | None]
              | dict[str, Callable[[dict[str, Any], str], dict[str, Any] | None]]
              | None = None,
    validate: Callable[[dict[str, Any], str], bool] | None = None,
) -> dict[str, Any] | None:
    """通用 Fallback 获取器。

    对于指定数据类型，依次尝试 chain 中的每个 provider，
    第一个成功的返回结果，全部失败返回 None。

    熔断逻辑委托 DataSourceRegistry，取代旧版 _PROVIDER_SKIP 等全局变量。
    """
    chain = _get_chain(data_type)

    # 1) 读缓存
    cached = cache_get(cache_key, cache_ttl)
    if cached is not None:
        return cached

    # 2) 遍历 chain 尝试（熔断委托 registry）
    kwargs = fn_kwargs or {}
    _code_tag = f" [{kwargs.get('code', '')}]" if kwargs.get("code") else ""
    reg = get_registry()
    for provider_name in chain:
        # 熔断检查（含自动冷却恢复）
        if reg.is_circuit_broken(provider_name):
            logger.debug("[%s]%s %s 已被熔断，跳过", data_type, _code_tag, provider_name)
            continue

        entry = provider_fn_map.get(provider_name)
        if not entry:
            logger.warning("[%s]%s 未知 Provider '%s'，跳过", data_type, _code_tag, provider_name)
            continue

        source_label, fetch_fn = entry
        logger.info("[%s]%s 尝试 %s (%s)", data_type, _code_tag, source_label, provider_name)

        if fetch_fn is None:
            logger.warning("[%s] %s 没有注册的 fetch 函数", data_type, provider_name)
            continue

        result = _try_provider_fetch(data_type, provider_name, source_label, fetch_fn, kwargs, validate, transform)
        if result is not None and result is not _TRANSPORT_FAILURE:
            # 成功 → 恢复熔断计数器
            reg.record_success(provider_name)
            cache_set(cache_key, result)
            return result

        if result is _TRANSPORT_FAILURE:
            # 传输级异常（超时/断连/DNS/5xx）→ 累计连续失败计数
            reg.record_failure(provider_name, f"{data_type}:transport")
            if reg.is_circuit_broken(provider_name):
                logger.warning("[%s] %s 连续失败，本会话后续请求跳过",
                               data_type, provider_name)
        # else: 代码级空结果（API 不识别该代码）→ 不计入熔断计数器

    # 3) 降级：全部 Provider 失败时尝试过期缓存
    stale = cache_get(cache_key, CACHE_WEEKLY)
    if stale is not None:
        logger.info("[%s] 全部 Provider 不可用，降级使用过期缓存", data_type)
        return stale

    return None


# 模块加载时自动注册默认 Provider Chain，使 registry.get_chain() 和策略选择器生效
get_registry().register_default_chains()
