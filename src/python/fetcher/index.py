"""A 股 / 美股指数获取（含备用链路）。

主链路 → 备用链路 → 过期缓存降级：
  - A 股指数：腾讯财经 → 新浪财经 → 过期缓存
  - 美股指数：新浪财经 → 腾讯财经 → 过期缓存
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.constants import CACHE_WEEKLY
from src.python.cache import get_ttl
from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.providers import sina, tencent

logger = logging.getLogger("invest")

# ── A 股指数 ─────────────────────────────────────────────────

_A_INDICES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sh000300": "沪深300",
    "sh000688": "科创板50",
    "sz399006": "创业板指",
}

# Sina A 股指数代码与内部代码的映射
_A_SINA_TO_INTERNAL: dict[str, str] = {
    "s_sh000001": "sh000001",
    "s_sz399001": "sz399001",
    "s_sh000300": "sh000300",
    "s_sh000688": "sh000688",
    "s_sz399006": "sz399006",
}

# 反向映射：内部代码 → Sina 代码
_A_INTERNAL_TO_SINA: dict[str, str] = {v: k for k, v in _A_SINA_TO_INTERNAL.items()}


def _index_cache_key(code: str) -> str:
    return f"index_{code}"


def _fetch_indices_from_tencent(uncached: list[str]) -> dict[str, dict[str, Any]]:
    """通过腾讯财经获取 A 股指数（主链路）。"""
    results: dict[str, dict[str, Any]] = {}

    def _fetch_one(index_code: str) -> tuple[str, dict] | None:
        index_name = _A_INDICES[index_code]
        result = tencent.fetch_price(index_code)
        if result and result.get("price", 0) > 0:
            price = result.get("price", 0.0)
            yclose = result.get("yesterday_close", 0.0)
            change = round(price - yclose, 2)
            change_pct = round(change / yclose * 100, 2) if yclose > 0 else 0.0
            data = {
                "name": result.get("name", index_name),
                "code": index_code,
                "price": price,
                "yesterday_close": yclose,
                "price_date": result.get("price_date", ""),
                "change": change,
                "change_pct": change_pct,
                "_source": "tencent",
            }
            cache_set(_index_cache_key(index_code), data)
            return index_code, data
        return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_one, code): code for code in uncached}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                code, data = result
                results[code] = data

    return results


def _fetch_indices_from_sina(uncached: list[str]) -> dict[str, dict[str, Any]]:
    """通过新浪财经获取 A 股指数（备用链路）。"""
    results: dict[str, dict[str, Any]] = {}

    # 将需要获取的内部代码转为 Sina 代码
    sina_codes = [_A_INTERNAL_TO_SINA[code] for code in uncached
                  if code in _A_INTERNAL_TO_SINA]
    if not sina_codes:
        return results

    sina_results = sina.fetch_a_indices()
    if not sina_results:
        return results

    for sina_code, data in sina_results.items():
        internal_code = _A_SINA_TO_INTERNAL.get(sina_code)
        if internal_code and data.get("price", 0) > 0:
            data["_source"] = "sina"
            cache_set(_index_cache_key(internal_code), data)
            results[internal_code] = data

    return results


def fetch_indices() -> dict[str, dict[str, Any]]:
    """获取 A 股主要指数行情。

    链路：腾讯财经 → 新浪财经 → 过期缓存
    """
    indices: dict[str, dict[str, Any]] = {}

    # 先行收集已缓存的指数
    uncached_codes: list[str] = []
    for index_code in _A_INDICES:
        cache_key = _index_cache_key(index_code)
        cached = cache_get(cache_key, get_ttl("index"))
        if cached is not None:
            cached["_source"] = "cache"
            indices[index_code] = cached
        else:
            uncached_codes.append(index_code)

    if not uncached_codes:
        return indices

    # 主链路：腾讯财经
    tencent_results = _fetch_indices_from_tencent(uncached_codes)
    indices.update(tencent_results)

    # 检查哪些还没获取到，尝试备用链路
    still_missing = [c for c in uncached_codes if c not in indices]
    if still_missing:
        logger.warning("[index] A 股指数腾讯链路失败（未获取 %d 个指数），降级至新浪备用链路: %s",
                        len(still_missing), still_missing)
        sina_results = _fetch_indices_from_sina(still_missing)
        indices.update(sina_results)

    # 备用链路仍缺失的，尝试过期缓存
    still_missing = [c for c in uncached_codes if c not in indices]
    if still_missing:
        for code in still_missing:
            stale = cache_get(_index_cache_key(code), CACHE_WEEKLY)
            if stale is not None:
                stale["_source"] = "stale_cache"
                indices[code] = stale
                logger.info("A 股指数 %s 降级为过期缓存数据", code)

    return indices


# ── 美股指数 ─────────────────────────────────────────────────

_US_INDEX_CODES = {
    "gb_dji": "道琼斯",
    "gb_ixic": "纳斯达克",
    "gb_inx": "标普500",
}

# Tencent 美股指数代码（与 _US_INDEX_CODES 键名一致）
_US_TENCENT_CODES: dict[str, str] = {
    "gb_dji": "gb_dji",
    "gb_ixic": "gb_ixic",
    "gb_inx": "gb_inx",
}


def _fetch_us_from_tencent(missing: list[str]) -> dict[str, dict[str, Any]]:
    """通过腾讯财经获取美股指数（备用链路）。"""
    results: dict[str, dict[str, Any]] = {}
    for code in missing:
        result = tencent.fetch_index_price(code)
        if result and result.get("price", 0) > 0:
            price = result.get("price", 0.0)
            yclose = result.get("yesterday_close", 0.0)
            change = round(price - yclose, 2)
            change_pct = round(change / yclose * 100, 2) if yclose > 0 else 0.0
            data = {
                "name": result.get("name", _US_INDEX_CODES.get(code, "")),
                "code": code,
                "price": price,
                "yesterday_close": yclose,
                "price_date": result.get("price_date", ""),
                "change": change,
                "change_pct": change_pct,
                "_source": "tencent",
            }
            cache_set(_index_cache_key(code), data)
            results[code] = data
    return results


def _index_history_cache_key(code: str) -> str:
    """指数历史日线的文件缓存键。"""
    return f"history_index_{code}"


def fetch_index_history(code: str, days: int = 365) -> list[dict] | None:
    """获取指数历史日线（走 history_index chain，C6 约束）。

    通过 history_index chain 路由，复用 tencent/sina 的 K 线能力，
    跳过 is_a_share_code 类型检查。

    C4 约束：同次会话同一代码命中 DataSourceRegistry.session_cache。

    Args:
        code: 指数代码，如 "sh000300" / "gb_inx"
        days: 获取天数（默认 365，最大 3650）

    Returns:
        [{"date": "...", "close": float, "open": float,
          "high": float, "low": float, "volume": int}, ...]
        按日期升序。全链路失败返回 [].
    """
    if not code:
        return None

    from src.python.fetcher.chain import _fetch_with_incremental_fallback

    # 先查会话缓存（C4 约束）
    from src.python.provider_registry import _NOT_FOUND, get_registry
    reg = get_registry()
    cached = reg.session_cache_get("history_index", code)
    if cached is not _NOT_FOUND:
        return cached

    # 通过 history_index chain 获取
    days = min(max(days, 5), 3650)
    try:
        result = _fetch_with_incremental_fallback("history_index", code, days)
    except Exception:
        logger.warning("[index] 指数历史日线获取异常: %s", code, exc_info=True)
        result = []

    # 写入会话缓存（即使为空也缓存，避免重复请求）
    reg.session_cache_set("history_index", code, result, source="api")
    return result


def fetch_us_indices() -> dict[str, dict[str, Any]]:
    """获取美股三大指数行情（带重试和备用链路）。

    链路：新浪财经（带 2 次重试）→ 腾讯财经 → 过期缓存
    """
    indices: dict[str, dict[str, Any]] = {}
    expired_cached: dict[str, dict[str, Any]] = {}

    for code in _US_INDEX_CODES:
        cache_key = _index_cache_key(code)
        cached = cache_get(cache_key, get_ttl("index"))
        if cached is not None:
            cached["_source"] = "cache"
            indices[code] = cached
        else:
            stale = cache_get(cache_key, 604800)
            if stale is not None:
                expired_cached[code] = stale

    if len(indices) == len(_US_INDEX_CODES):
        return indices

    # 主链路：新浪财经（带 2 次重试）
    import time as _time
    for attempt in range(2):
        try:
            sina_data = sina.fetch_us_indices()
            if sina_data:
                for code, data in sina_data.items():
                    data["_source"] = "sina"
                    cache_set(_index_cache_key(code), data)
                    indices[code] = data
                return indices
        except Exception as e:  # noqa: PERF203
            logger.warning("美股指数新浪 API 请求失败（第 %d 次）: %s", attempt + 1, e)
            if attempt == 0:
                _time.sleep(1)
        else:
            break

    # 备用链路：腾讯财经
    missing = [c for c in _US_INDEX_CODES if c not in indices]
    if missing:
        logger.info("美股指数新浪链路失败，尝试腾讯备用链路: %s", missing)
        try:
            tencent_data = _fetch_us_from_tencent(missing)
            indices.update(tencent_data)
        except Exception as e:
            logger.warning("美股指数腾讯备用链路也失败: %s", e)

    # 全部失败 → 降级使用过期缓存
    still_missing = [c for c in _US_INDEX_CODES if c not in indices]
    if still_missing and expired_cached:
        logger.info("美股指数全部 API 不可用，使用过期缓存数据")
        for code, data in expired_cached.items():
            data["_source"] = "stale_cache"
            indices[code] = data
            cache_set(_index_cache_key(code), data)
            logger.info("美股指数 %s 降级为缓存数据", code)
    elif still_missing:
        logger.warning("美股指数全部获取失败（API + 缓存均无数据）")

    return indices
