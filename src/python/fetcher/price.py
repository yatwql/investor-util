"""市场行情数据获取（场内/场外价格）。

Provider Chain（按代码类型路由）：
  股票/ETF: 腾讯财经 → 新浪财经
  场外基金: 东方财富
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from src.python.cache import get_ttl
from src.python.code_utils import is_a_share_code, is_exchange_fund_code, is_otc_code_overlap
from src.python.fetcher.chain import fetch_with_fallback
from src.python.providers import eastmoney, tencent
from src.python.providers import sina as sina_provider

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
    "sina": ("新浪财经", sina_provider.fetch_price),
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
        # 扩展字段（用于基金风格分析等下游模块）
        "market_cap": raw.get("market_cap", 0.0),
        "pe": raw.get("pe", 0.0),
    }


def _price_transform_sina(raw: dict, source: str) -> dict | None:
    """新浪财经原始数据 → 统一价格格式。"""
    return {
        "name": raw.get("name", ""),
        "code": raw.get("code", ""),
        "price": raw.get("price", 0.0),
        "yesterday_close": raw.get("yesterday_close", 0.0),
        "price_date": raw.get("price_date", ""),
        "source_api": "sina",
        "source": source,
        # 新浪数据不含 market_cap/pe，下游使用前需判 None
        "market_cap": None,
        "pe": None,
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
    "sina": _price_transform_sina,
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
    """获取一只证券的市场行情（按代码类型自动路由 Provider Chain）。

    股票/ETF → 腾讯财经 → 新浪财经（备用）
    场外基金 → 东方财富

    Args:
        code: 6 位证券代码
        expected_name: 持仓名称（用于代码重叠识别）

    Returns:
        {name, code, price, yesterday_close, price_date, source_api, source}
        None: 全部接口失败
    """
    code = code.strip()
    cache_key = _price_cache_key(code)

    # 按代码类型选择专属 Provider Chain
    # 股票/ETF → tencent → sina（同质 fallback）
    # 场外基金 → eastmoney（直达，无备用）
    if is_exchange_fund_code(code) or is_a_share_code(code):
        data_type = "price_stock"
    else:
        data_type = "price_fund_otc"

    # 降级标记：00 开头同时存在 A 股和 OTC 基金，代码前缀无法区分
    # 若股票链路全失败，降级到场外基金链路尝试
    _needs_degrade = data_type == "price_stock" and is_otc_code_overlap(code)

    def _validate(raw: dict, provider_name: str) -> bool:
        if provider_name in ("tencent", "sina"):
            if not raw.get("name"):
                return False
            pname = raw.get("name", "").strip()
            return not (expected_name and pname and not _name_matches(pname, expected_name))
        if provider_name == "eastmoney":
            return bool(raw.get("nav") and raw.get("nav", 0.0) > 0)
        return True

    def _fetch_with_cache_refresh(dt: str) -> dict[str, Any] | None:
        """一次 fetch + 收市后新鲜度校验（跨日残留缓存清仓重试）。"""
        from src.python.report.data_status import get_tracker

        _t = get_tracker()
        _src_key = f"price_{dt}_{code}"

        r = fetch_with_fallback(
            data_type=dt,
            provider_fn_map=_PRICE_PROVIDERS,
            cache_key=cache_key,
            cache_ttl=get_ttl("price", cache_key),
            fn_kwargs={"code": code},
            transform=_PRICE_TRANSFORMS,
            validate=_validate,
        )
        if r is not None:
            _t.record(_src_key, "T2", success=True)
        else:
            _t.record(_src_key, "T2", success=False, failure_type="unreachable")

        if r is not None and not _price_cache_fresh(r):
            from src.python.cache import clear as _cache_clear
            from src.python.report.market_value import get_last_trading_day as _gtd

            _td = _gtd()
            logger.debug("价格缓存来自 %s（交易日 %s），跨日残留，强制刷新", r.get("price_date", "?"), _td)
            _cache_clear(cache_key)
            r = fetch_with_fallback(
                data_type=dt,
                provider_fn_map=_PRICE_PROVIDERS,
                cache_key=cache_key,
                cache_ttl=get_ttl("price", cache_key),
                fn_kwargs={"code": code},
                transform=_PRICE_TRANSFORMS,
                validate=_validate,
            )
            if r is not None:
                _t.record(f"{_src_key}_refresh", "T2", success=True)
            else:
                _t.record(f"{_src_key}_refresh", "T2", success=False, failure_type="unreachable")
        return r

    result = _fetch_with_cache_refresh(data_type)

    # ── 降级：00 代码在股票链路全失败 → 尝试场外基金链路 ──
    if result is None and _needs_degrade:
        _tag = f"  [{code} {expected_name}]" if expected_name else f"  [{code}]"
        logger.info("[price]%s 股票链路全部失败（该代码可能为场外基金），降级尝试东方财富净值链路", _tag)
        result = _fetch_with_cache_refresh("price_fund_otc")
        if result is not None:
            logger.info("[price]%s 降级成功——通过场外基金链路获取到净值", _tag)
        else:
            logger.warning("[price]%s 降级也失败——场外基金链路亦无数据", _tag)

    return result
