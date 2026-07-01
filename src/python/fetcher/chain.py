"""Provider Chain 定义与通用 Fallback 获取器。

每类数据（price/index/rank/holding）对应一个 Provider Chain，
chain 中按优先级列出 provider，主链路失败后自动递补。
用户可通过 config.json 的 preferred_provider 手动指定首选链路。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from src.python.cache import CACHE_WEEKLY, get as cache_get, set as cache_set
from src.python.config import get_config

logger = logging.getLogger("invest")

# ── Provider Chain 定义 ──────────────────────────────────────

_DEFAULT_CHAINS: dict[str, list[str]] = {
    "price": ["tencent", "eastmoney"],
    "index": ["tencent", "sina"],
    "us_index": ["sina"],
    "fund_rank": ["tiantian"],
    "fund_hold": ["tiantian"],
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
        pass
    return chain


# ── Provider 注册表（核心类型） ──────────────────────────────

_ProviderFunc = Callable[..., dict[str, Any] | None]

_PROVIDER_REGISTRY: dict[str, tuple[str, _ProviderFunc]] = {
    "tencent": ("腾讯财经", None),
    "eastmoney": ("东方财富", None),
    "sina": ("新浪财经", None),
    "tiantian": ("天天基金", None),
}


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
    try:
        raw = fetch_fn(**kwargs)
    except Exception as e:
        logger.warning("[%s] %s 调用异常: %s", data_type, provider_name, e)
        return None

    if raw is None:
        logger.info("[%s] %s 返回空，尝试下一链路", data_type, provider_name)
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
        logger.info("[%s] %s 成功", data_type, provider_name)
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
    """
    chain = _get_chain(data_type)

    # 1) 读缓存
    cached = cache_get(cache_key, cache_ttl)
    if cached is not None:
        logger.debug("缓存命中: %s", cache_key)
        return cached

    # 2) 遍历 chain 尝试
    kwargs = fn_kwargs or {}
    for provider_name in chain:
        entry = provider_fn_map.get(provider_name)
        if not entry:
            logger.warning("[%s] 未知 Provider '%s'，跳过", data_type, provider_name)
            continue

        source_label, fetch_fn = entry
        logger.info("[%s] 尝试 %s (%s)", data_type, source_label, provider_name)

        if fetch_fn is None:
            logger.warning("[%s] %s 没有注册的 fetch 函数", data_type, provider_name)
            continue

        result = _try_provider_fetch(data_type, provider_name, source_label, fetch_fn, kwargs, validate, transform)
        if result is not None:
            cache_set(cache_key, result)
            return result

    # 3) 降级：全部 Provider 失败时尝试过期缓存
    stale = cache_get(cache_key, CACHE_WEEKLY)
    if stale is not None:
        logger.info("[%s] 全部 Provider 不可用，降级使用过期缓存", data_type)
        return stale

    return None
