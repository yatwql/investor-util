"""Provider Chain 定义与通用 Fallback 获取器。

每类数据（price/index/rank/holding）对应一个 Provider Chain，
chain 中按优先级列出 provider，主链路失败后自动递补。
用户可通过 config.json 的 preferred_provider 手动指定首选链路。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from src.python.constants import CACHE_WEEKLY
from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.config import get_config

logger = logging.getLogger("invest")

# ── Provider Chain 定义 ──────────────────────────────────────

_DEFAULT_CHAINS: dict[str, list[str]] = {
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


# ── 会话级 Provider 熔断 ────────────────────────────────────
# 同一 provider 连续失败 _PROVIDER_SKIP_THRESHOLD 次后，
# 本会话剩余请求跳过该 provider，避免每次等待超时/断连。
# 跳过时记录时间戳，冷却期满（_PROVIDER_COOLDOWN_SECS）后允许
# 一次试探请求，成功则恢复，失败则重新计时。
_PROVIDER_CONSECUTIVE_FAILURES: dict[str, int] = {}
_PROVIDER_SKIP: set[str] = set()
_PROVIDER_SKIP_TIME: dict[str, float] = {}  # provider_name → 进入熔断的时间戳
_PROVIDER_SKIP_THRESHOLD = 3
_PROVIDER_COOLDOWN_SECS = 300  # 5 分钟后允许试探恢复
# 线程锁：熔断计数器被 batch_fetch_industry_data 等从多线程写入
_PROVIDER_LOCK = threading.Lock()


def reset_provider_skip() -> None:
    """重置 Provider 熔断状态（测试用）。"""
    with _PROVIDER_LOCK:
        _PROVIDER_CONSECUTIVE_FAILURES.clear()
        _PROVIDER_SKIP.clear()
        _PROVIDER_SKIP_TIME.clear()


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
    with _PROVIDER_LOCK:
        return all(p in _PROVIDER_SKIP for p in chain)

_ProviderFunc = Callable[..., dict[str, Any] | None]

# 熔断计数器增量标记：_try_provider_fetch 返回此值表示传输级异常
# （非代码级空结果），应计入熔断计数器。
_TRANSPORT_FAILURE: object = object()


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
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str or "rate" in err_str.lower():
            logger.warning("[%s] %s API 限速(429): %s", data_type, provider_name, err_str)
        else:
            logger.warning("[%s] %s 调用异常: %s", data_type, provider_name, err_str)
        return _TRANSPORT_FAILURE  # type: ignore[return-value]  # 传输级异常 → 应计入熔断

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
        # 会话级熔断：连续失败已达阈值 → 跳过（冷却期后允许试探恢复）
        with _PROVIDER_LOCK:
            _skip = provider_name in _PROVIDER_SKIP
            _skip_time = _PROVIDER_SKIP_TIME.get(provider_name, 0) if _skip else 0
        if _skip:
            if time.time() - _skip_time >= _PROVIDER_COOLDOWN_SECS:
                # 冷却期满 → 移除熔断标记，放行一次试探请求
                with _PROVIDER_LOCK:
                    _PROVIDER_SKIP.discard(provider_name)
                    _PROVIDER_SKIP_TIME.pop(provider_name, None)
                logger.info("[%s] %s 冷却期满，允许试探请求",
                            data_type, provider_name)
            else:
                logger.debug("[%s] %s 已被熔断（连续 %d 次失败），跳过",
                              data_type, provider_name, _PROVIDER_SKIP_THRESHOLD)
                continue

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
        if result is not None and result is not _TRANSPORT_FAILURE:
            # 成功 → 恢复熔断计数器
            with _PROVIDER_LOCK:
                _PROVIDER_CONSECUTIVE_FAILURES.pop(provider_name, None)
                _PROVIDER_SKIP.discard(provider_name)
            cache_set(cache_key, result)
            return result

        if result is _TRANSPORT_FAILURE:
            # 传输级异常（超时/断连/DNS/5xx）→ 累计连续失败计数
            with _PROVIDER_LOCK:
                count = _PROVIDER_CONSECUTIVE_FAILURES.get(provider_name, 0) + 1
                _PROVIDER_CONSECUTIVE_FAILURES[provider_name] = count
                if count >= _PROVIDER_SKIP_THRESHOLD:
                    _PROVIDER_SKIP.add(provider_name)
                    _PROVIDER_SKIP_TIME[provider_name] = time.time()
            if count >= _PROVIDER_SKIP_THRESHOLD:
                logger.warning("[%s] %s 连续 %d 次失败，本会话后续请求跳过",
                               data_type, provider_name, count)
        # else: 代码级空结果（API 不识别该代码）→ 不计入熔断计数器

    # 3) 降级：全部 Provider 失败时尝试过期缓存
    stale = cache_get(cache_key, CACHE_WEEKLY)
    if stale is not None:
        logger.info("[%s] 全部 Provider 不可用，降级使用过期缓存", data_type)
        return stale

    return None
