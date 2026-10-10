"""指数估值历史序列（PE/PB 月频）— 乐咕 akshare + 熔断 + 缓存 + 缺席降级。

主源：akshare ``stock_index_pe_lg`` / ``stock_index_pb_lg``（月频，2005 年起，
覆盖两轮牛熊）——市场温度第一因子（估值分位）与股债性价比的数据底座。
缓存：``idx_valuation_{code}``，1 周（月频数据日内几乎不变，随基础类菜单刷新）。
缺席：akshare 未安装 / 熔断 / 异常 / 空数据 → None（消费方回落价格分位代理，
      不阻塞主链路）；仅支持有乐咕 symbol 映射的指数（当前 sh000300）。

走独立 fetcher，不绕过 registry 熔断层。
"""

from __future__ import annotations

import logging
import math

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.core.constants import CACHE_MONTHLY, CACHE_WEEKLY

logger = logging.getLogger("invest")

#: 内部指数代码 → 乐咕乐股接口 symbol（无映射的指数不支持，返回 None）
_SYMBOL_MAP: dict[str, str] = {
    "sh000300": "沪深300",
}

#: PE/PB 列名（akshare 返回中文列，按名匹配而非硬编码索引）
_COL_DATE = "日期"
_COL_PE = "滚动市盈率"
_COL_PB = "市净率"


def _cache_key(index_code: str) -> str:
    """估值历史缓存键。"""
    return f"idx_valuation_{index_code}"


def _stale_fallback(index_code: str) -> list[dict] | None:
    """过期缓存兕底（月频估值数据容忍 30 天陈旧）。

    源“时好时坏”时避免口径在估值分位/点位分位之间来回跳
    （tier 翻转会导致同一市场的报告结论不一致）。
    """
    stale = cache_get(_cache_key(index_code), CACHE_MONTHLY)
    return stale if isinstance(stale, list) and stale else None


def fetch_index_valuation_history(index_code: str = "sh000300") -> list[dict] | None:
    """获取指数 PE/PB 月频历史序列（升序）。

    Args:
        index_code: 内部指数代码（当前仅支持 sh000300，其余返回 None）。

    Returns:
        [{"date": "YYYY-MM-DD", "pe": float|None, "pb": float|None}, ...]
        按日期升序；PE/PB 任一不可得时对应字段为 None（另一字段保留）；
        全链路不可得返回 None（缺席，不抛异常）。
    """
    symbol = _SYMBOL_MAP.get(index_code)
    if not symbol:
        logger.info("指数估值历史: 无 %s 的 symbol 映射，缺席", index_code)
        return None

    cached = cache_get(_cache_key(index_code), CACHE_WEEKLY)
    if isinstance(cached, list) and cached:
        logger.debug("指数估值历史: %s 缓存命中（%d 行）", index_code, len(cached))
        return cached

    from src.python.core.provider_registry import get_registry

    # 只读熔断检查（不写失败/成功）：本源是可选辅助源（月频 + 1 周缓存，
    # 每周至多尝试 1 次），与分红/盈利预测等可选 akshare 消费方同口径——
    # 若向共享 "akshare" 熔断键计失败会连坐无风险利率（bond_yield 同键），
    # 计成功则会重置其连续失败计数掩盖真实故障
    if get_registry().is_circuit_broken("akshare"):
        stale = _stale_fallback(index_code)
        logger.info("指数估值历史: akshare 已被熔断，%s", "用过期缓存兜底" if stale else "缺席")
        return stale

    pe_rows = _fetch_pe(symbol)
    pb_rows = _fetch_pb(symbol)
    merged = _merge_pe_pb(pe_rows, pb_rows) if (pe_rows or pb_rows) else []
    if not merged:
        stale = _stale_fallback(index_code)
        logger.warning(
            "指数估值历史: %s PE/PB 不可得，%s",
            index_code,
            "用过期缓存兜底（月频数据容忍陈旧）" if stale else "缺席",
        )
        return stale

    cache_set(_cache_key(index_code), merged)
    logger.info(
        "指数估值历史: %s 获取成功（%d 行，%s ~ %s）", index_code, len(merged), merged[0]["date"], merged[-1]["date"]
    )
    return merged


def _fetch_pe(symbol: str) -> list[dict]:
    """乐咕指数 PE 历史（滚动市盈率 TTM）；不可得返回 []。"""
    rows = _fetch_lg_frame(symbol, "stock_index_pe_lg", _COL_PE)
    return rows


def _fetch_pb(symbol: str) -> list[dict]:
    """乐咕指数 PB 历史（市净率）；不可得返回 []。"""
    rows = _fetch_lg_frame(symbol, "stock_index_pb_lg", _COL_PB)
    return rows


def _fetch_lg_frame(symbol: str, api_name: str, value_col: str) -> list[dict]:
    """调用乐咕接口并抽取 (date, value) 行（列名匹配 + 非法值过滤）。"""
    try:
        import akshare as ak
    except ImportError:
        logger.warning("指数估值历史: akshare 未安装，无法获取")
        return []

    try:
        fn = getattr(ak, api_name)
        df = fn(symbol=symbol)
    except Exception:
        logger.warning("指数估值历史: akshare %s(%s) 异常", api_name, symbol, exc_info=True)
        return []
    if df is None or getattr(df, "empty", True):
        logger.warning("指数估值历史: akshare %s(%s) 返回空数据", api_name, symbol)
        return []
    if _COL_DATE not in df.columns or value_col not in df.columns:
        logger.warning("指数估值历史: %s 列缺失（可用列: %s）", api_name, list(df.columns))
        return []

    rows: list[dict] = []
    for _, r in df.iterrows():
        date = str(r[_COL_DATE]).strip()[:10]
        raw = r[value_col]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = None  # type: ignore[assignment]
        if value is not None and (not math.isfinite(value) or value <= 0):
            value = None  # PE/PB 非正（亏损期/异常）视为缺失
        rows.append({"date": date, "value": value})
    return rows


def _merge_pe_pb(pe_rows: list[dict], pb_rows: list[dict]) -> list[dict]:
    """按日期外连接 PE/PB 行（任一侧缺失保留另一侧，两侧皆缺的日期剔除）。"""
    pb_by_date = {r["date"]: r["value"] for r in pb_rows}
    pe_by_date = {r["date"]: r["value"] for r in pe_rows}
    dates = sorted(set(pe_by_date) | set(pb_by_date))
    merged: list[dict] = []
    for d in dates:
        pe, pb = pe_by_date.get(d), pb_by_date.get(d)
        if pe is None and pb is None:
            continue
        merged.append({"date": d, "pe": pe, "pb": pb})
    return merged


__all__ = [
    "fetch_index_valuation_history",
]
