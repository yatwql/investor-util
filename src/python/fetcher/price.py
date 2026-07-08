"""市场行情数据获取（场内/场外价格）。

Provider Chain（可配置）：腾讯财经 → 东方财富
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from src.python.cache import get_ttl
from src.python.fetcher.chain import _fetch_with_fallback
from src.python.providers import eastmoney, tencent

logger = logging.getLogger("invest")

# ── 名称匹配 ─────────────────────────────────────────────────


def _name_matches(a: str, b: str) -> bool:
    """判断两个证券名称是否指向同一标的。"""
    a = a.strip()
    b = b.strip()
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return True
    a_chars = set(re.findall(r"[一-鿿]", a))
    b_chars = set(re.findall(r"[一-鿿]", b))
    if not a_chars or not b_chars:
        return False
    overlap = len(a_chars & b_chars) / min(len(a_chars), len(b_chars))
    return overlap >= 0.7


# ── 缓存键 ───────────────────────────────────────────────────


def _price_cache_key(code: str) -> str:
    return f"price_{code}"


# ── Provider 映射与 Transformer ──────────────────────────────

_ProviderFunc = Callable[..., dict[str, Any] | None]

_PRICE_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tencent": ("腾讯财经", tencent.fetch_price),
    "eastmoney": ("东方财富", eastmoney.fetch_nav),
}


def _price_transform_tencent(raw: dict, source: str) -> dict | None:
    """腾讯财经原始数据 → 统一价格格式。"""
    return {
        "name": raw.get("name", ""),
        "code": raw.get("code", ""),
        "price": raw.get("price", 0.0),
        "yesterday_close": raw.get("yesterday_close", 0.0),
        "price_date": raw.get("price_date", ""),
        "source_api": "tencent",
        "source": source,
    }


def _price_transform_eastmoney(raw: dict, source: str) -> dict | None:
    """东方财富原始数据 → 统一价格格式。"""
    nav = raw.get("nav", 0.0)
    if nav <= 0:
        return None
    return {
        "name": raw.get("name", ""),
        "code": raw.get("code", ""),
        "price": nav,
        "yesterday_close": raw.get("yesterday_nav", 0.0),
        "price_date": raw.get("nav_date", ""),
        "source_api": "eastmoney",
        "source": source,
    }


_PRICE_TRANSFORMS: dict[str, Callable] = {
    "tencent": _price_transform_tencent,
    "eastmoney": _price_transform_eastmoney,
}


# ── 公开接口 ─────────────────────────────────────────────────


def _price_cache_fresh(data: dict) -> bool:
    """收市后验证价格缓存数据是否来自当前交易日。

    缓存命中的缓存若 price_date 早于最近交易日，说明是跨日残留的过时数据
    （例如盘中 Tencent 降级到 EastMoney 写入的上一交易日净值），应强制刷新。
    盘中不验证（短 TTL 已保证实时性）。
    """
    try:
        from src.python.market_hours import is_market_open as _mh_open
        from src.python.report.market_value import get_last_trading_day as _gtd
        if _mh_open():
            return True
        pd = data.get("price_date", "")
        if not pd:
            return False
        td = _gtd()
        return pd >= td
    except Exception:
        logger.warning("[price] _is_cache_fresh 校验异常，保守视作新鲜", exc_info=True)
        return True


def fetch_market_data(code: str, expected_name: str = "") -> dict[str, Any] | None:
    """获取一只证券的市场行情（含自动/手动备用链路切换）。

    Args:
        code: 6 位证券代码
        expected_name: 持仓名称（用于代码重叠识别）

    Returns:
        {name, code, price, yesterday_close, price_date, source_api, source}
        None: 全部接口失败
    """
    code = code.strip()
    cache_key = _price_cache_key(code)

    def _validate(raw: dict, provider_name: str) -> bool:
        if provider_name == "tencent":
            if not raw.get("name"):
                return False
            tencent_name = raw.get("name", "").strip()
            return not (expected_name and tencent_name and not _name_matches(tencent_name, expected_name))
        if provider_name == "eastmoney":
            return bool(raw.get("nav") and raw.get("nav", 0.0) > 0)
        return True

    result = _fetch_with_fallback(
        data_type="price",
        provider_fn_map=_PRICE_PROVIDERS,
        cache_key=cache_key,
        cache_ttl=get_ttl("price"),
        fn_kwargs={"code": code},
        transform=_PRICE_TRANSFORMS,
        validate=_validate,
    )

    # 收市后验证：缓存 price_date 是否仍是当前交易日
    # 盘中命中缓存时短 TTL 已保证实时性，收市后长 TTL 可能导致跨日残留
    if result is not None and not _price_cache_fresh(result):
        from src.python.cache import clear as _cache_clear
        from src.python.report.market_value import get_last_trading_day as _gtd
        _td = _gtd()
        logger.debug("价格缓存来自 %s（交易日 %s），跨日残留，强制刷新",
                     result.get("price_date", "?"), _td)
        _cache_clear(cache_key)
        result = _fetch_with_fallback(
            data_type="price",
            provider_fn_map=_PRICE_PROVIDERS,
            cache_key=cache_key,
            cache_ttl=get_ttl("price"),
            fn_kwargs={"code": code},
            transform=_PRICE_TRANSFORMS,
            validate=_validate,
        )

    return result
