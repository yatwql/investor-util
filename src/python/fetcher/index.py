"""A 股 / 美股指数获取。

- A 股指数 Provider: 腾讯财经（新浪备用链路尚未实现）
- 美股指数 Provider: 新浪财经（带重试和缓存降级）
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.python.cache import CACHE_DAILY, CACHE_WEEKLY, get as cache_get, get_ttl, set as cache_set
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


def _index_cache_key(code: str) -> str:
    return f"index_{code}"


def fetch_indices() -> dict[str, dict[str, Any]]:
    """获取 A 股主要指数行情。"""
    indices: dict[str, dict[str, Any]] = {}

    # 先行收集已缓存的指数
    uncached_codes: list[str] = []
    for index_code in _A_INDICES:
        cache_key = _index_cache_key(index_code)
        cached = cache_get(cache_key, get_ttl("index"))
        if cached is not None:
            indices[index_code] = cached
        else:
            uncached_codes.append(index_code)

    if not uncached_codes:
        return indices

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
            }
            cache_set(_index_cache_key(index_code), data)
            return index_code, data
        else:
            stale = cache_get(_index_cache_key(index_code), CACHE_WEEKLY)
            if stale is not None:
                return index_code, stale
        return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_one, code): code for code in uncached_codes}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                code, data = result
                indices[code] = data

    return indices


# ── 美股指数 ─────────────────────────────────────────────────

_US_INDEX_CODES = {
    "gb_dji": "道琼斯",
    "gb_ixic": "纳斯达克",
    "gb_inx": "标普500",
}


def fetch_us_indices() -> dict[str, dict[str, Any]]:
    """获取美股三大指数行情（带重试和缓存降级）。"""
    indices: dict[str, dict[str, Any]] = {}
    expired_cached: dict[str, dict[str, Any]] = {}

    for code in _US_INDEX_CODES:
        cache_key = _index_cache_key(code)
        cached = cache_get(cache_key, get_ttl("index"))
        if cached is not None:
            indices[code] = cached
        else:
            stale = cache_get(cache_key, 604800)
            if stale is not None:
                expired_cached[code] = stale

    if len(indices) == len(_US_INDEX_CODES):
        return indices

    # 调新浪 API（带重试）
    import time as _time
    for attempt in range(2):
        try:
            sina_data = sina.fetch_us_indices()
            if sina_data:
                for code, data in sina_data.items():
                    cache_set(_index_cache_key(code), data)
                    indices[code] = data
                return indices
        except Exception as e:
            logger.warning("美股指数 API 请求失败（第 %d 次）: %s", attempt + 1, e)
            if attempt == 0:
                _time.sleep(1)
        else:
            break

    # API 全部失败 → 降级使用过期缓存
    if expired_cached:
        logger.info("美股指数 API 不可用，使用过期缓存数据")
        for code, data in expired_cached.items():
            indices[code] = data
            cache_set(_index_cache_key(code), data)
            logger.info("美股指数 %s 降级为缓存数据", code)
    else:
        logger.warning("美股指数全部获取失败（API + 缓存均无数据）")

    return indices
