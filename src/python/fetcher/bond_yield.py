"""无风险利率获取器 — bond_zh_us_rate + 用户配置兜底。

主源：akshare bond_zh_us_rate() → 中国 10Y 国债收益率；
手动兜底：config.json risk_free_rate 字段（非 None 时跳过 fetcher）。
缓存：成功结果缓存 1 天，避免重复 akshare 调用。

返回值为小数（如 0.017404 代表 1.7404%），可直接用于夏普比率等计算。
返回值可能为 None（数据源不可用且无手动配置）。

走独立 fetcher，不绕过 chain 层。
"""

from __future__ import annotations

import logging

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.config import get_config

logger = logging.getLogger("invest")

_CACHE_KEY_RF = "bond_yield_rf"
_CACHE_KEY_HISTORY = "bond_yield_history"
_CACHE_TTL_RF = 86400  # 1 天
_CACHE_TTL_HISTORY = 86400  # 1 天（日频数据）


def get_risk_free_rate(cache_ok: bool = True) -> float | None:
    """获取年化无风险利率（中国 10Y 国债收益率）。

    优先级：
      1. config.json risk_free_rate（手动配置，非 None 时优先）
      2. 缓存（cache_ok=True 时）
      3. akshare bond_zh_us_rate() 实时获取
      4. 上述全部不可用 → None

    Returns:
        小数表示的年化无风险利率（如 0.0174），None 表示不可用。
        注：返回值为小数（1.74% → 0.0174），调用方无需除 100。
    """
    # ── 1. 用户手动配置兜底 ──
    try:
        config = get_config()
        manual_rf = config.get("risk_free_rate")
        if manual_rf is not None:
            rf = float(manual_rf)
            if 0 < rf < 1:
                logger.info("无风险利率: 使用用户配置 risk_free_rate = %.4f (%s)", rf, "手动配置")
                return rf
            elif rf >= 1:
                # 用户可能填的是百分比（如 1.74 而非 0.0174），自动转换
                rf_adj = rf / 100
                logger.info("无风险利率: 用户配置 %.4f 疑似百分比，自动转换为 %.6f", rf, rf_adj)
                return rf_adj
            else:
                logger.warning("无风险利率: 用户配置 risk_free_rate = %.4f 超出合理范围，跳过", rf)
    except (TypeError, ValueError, KeyError) as e:
        logger.debug("无风险利率: 解析用户配置失败: %s", e)

    # ── 2. 缓存 ──
    if cache_ok:
        cached = cache_get(_CACHE_KEY_RF, _CACHE_TTL_RF)
        if cached is not None:
            try:
                rf = float(cached)
                logger.info("无风险利率: 缓存命中 = %.4f", rf)
                return rf
            except (TypeError, ValueError):
                logger.debug("无风险利率: 缓存值解析失败")

    # ── 3. akshare 实时获取（含熔断检查） ──
    from src.python.core.provider_registry import get_registry

    if get_registry().is_circuit_broken("akshare"):
        logger.info("无风险利率: akshare 已被熔断，跳过实时获取")
    else:
        rf = _fetch_from_akshare()
        if rf is not None:
            cache_set(_CACHE_KEY_RF, rf)
            return rf

    logger.warning("无风险利率: 全部数据源不可用，返回 None")
    return None


def _fetch_from_akshare() -> float | None:
    """通过 akshare bond_zh_us_rate() 获取中国 10Y 国债收益率。

    Returns:
        小数表示的年化利率（如 0.017404），失败时返回 None。
    """
    try:
        import pandas as pd

        import akshare as ak
    except ImportError:
        logger.warning("无风险利率: akshare 未安装，无法获取")
        return None

    try:
        df = ak.bond_zh_us_rate()
        if df is None or df.empty:
            logger.warning("无风险利率: bond_zh_us_rate 返回空数据")
            return None

        # 取最后一行（最新日期）的中国国债收益率 10 年
        # 使用列名匹配而非硬编码索引，提高对 akshare 列顺序变化的鲁棒性
        latest_row = df.iloc[-1]
        china_10y_cols = [c for c in df.columns if "10" in str(c) and "中国" in str(c)]
        if not china_10y_cols:
            logger.warning("无风险利率: 无法定位中国10Y国债收益率列（可用列: %s）", list(df.columns))
            return None
        raw_value = latest_row[china_10y_cols[0]]

        if pd.isna(raw_value):
            logger.warning("无风险利率: 最新值缺失（NaN）")
            return None

        # bond_zh_us_rate 返回的值为百分比（如 1.7404），需转为小数
        rf = float(raw_value) / 100.0

        if rf <= 0 or rf >= 1:
            logger.warning("无风险利率: 获取值 %.4f 超出合理范围（期望 0~1）", rf)
            return None

        from src.python.core.provider_registry import get_registry

        get_registry().record_success("akshare")
        logger.info("无风险利率: akshare 获取成功 = %.4f (%s)", rf, latest_row.iloc[0])
        return rf

    except Exception as e:
        from src.python.core.provider_registry import get_registry

        get_registry().record_failure("akshare", "bond_yield:transport")
        logger.warning("无风险利率: akshare bond_zh_us_rate 异常: %s", e)
        return None


def get_risk_free_rate_history(cache_ok: bool = True) -> list[dict] | None:
    """获取中国 10Y 国债收益率**历史序列**（日频，升序）。

    与 :func:`get_risk_free_rate` 同源（``bond_zh_us_rate`` 本身返回全历史
    DataFrame，单值版只取末行）；供股债性价比（ERP = 1/PE − Rf）
    分位因子等需要历史对照的消费方使用。

    Args:
        cache_ok: 是否读缓存（True）或强制实时获取（False）。

    Returns:
        [{"date": "YYYY-MM-DD", "rate": float}, ...] 按日期升序，rate 为小数
        （0.0174 = 1.74%）；不可得返回 None（缺席，不抛异常）。
    """
    if cache_ok:
        cached = cache_get(_CACHE_KEY_HISTORY, _CACHE_TTL_HISTORY)
        if isinstance(cached, list) and cached:
            logger.debug("无风险利率历史: 缓存命中（%d 行）", len(cached))
            return cached

    from src.python.core.provider_registry import get_registry

    reg = get_registry()
    if reg.is_circuit_broken("akshare"):
        stale = _stale_history_fallback()
        logger.info("无风险利率历史: akshare 已被熔断，%s", "用过期缓存兜底" if stale else "缺席")
        return stale

    rows = _fetch_history_from_akshare()
    if not rows:
        # 注：空数据/列缺失属代码级结果，不计熔断失败（传输异常已在
        # _fetch_history_from_akshare 内部按异常路径记录）
        stale = _stale_history_fallback()
        logger.warning(
            "无风险利率历史: 全部数据源不可用，%s",
            "用过期缓存兜底（rf 日变动仅数 bp，7 天陈旧可容忍）" if stale else "返回 None",
        )
        return stale

    reg.record_success("akshare")
    cache_set(_CACHE_KEY_HISTORY, rows)
    logger.info("无风险利率历史: akshare 获取成功（%d 行，%s ~ %s）", len(rows), rows[0]["date"], rows[-1]["date"])
    return rows


def _stale_history_fallback() -> list[dict] | None:
    """过期缓存兜底：rf 日变动仅数 bp，7 天陈旧对 ERP 分位几乎无影响。"""
    from src.python.core.constants import CACHE_WEEKLY

    stale = cache_get(_CACHE_KEY_HISTORY, CACHE_WEEKLY)
    return stale if isinstance(stale, list) and stale else None


def _fetch_history_from_akshare() -> list[dict]:
    """通过 akshare bond_zh_us_rate() 获取中国 10Y 国债收益率全历史序列。

    Returns:
        [{"date": "YYYY-MM-DD", "rate": float}, ...] 升序；失败返回 []。
    """
    try:
        import pandas as pd

        import akshare as ak
    except ImportError:
        logger.warning("无风险利率历史: akshare 未安装，无法获取")
        return []

    try:
        df = ak.bond_zh_us_rate()
    except Exception as e:
        # 调用异常（超时/断连/接口失效）：计入共享 akshare 熔断（与
        # get_risk_free_rate 同键同故障域——同一端点）
        from src.python.core.provider_registry import get_registry

        get_registry().record_failure("akshare", "bond_yield_history:transport")
        logger.warning("无风险利率历史: akshare bond_zh_us_rate 异常: %s", e)
        return []

    try:
        if df is None or df.empty:
            logger.warning("无风险利率历史: bond_zh_us_rate 返回空数据")
            return []

        china_10y_cols = [c for c in df.columns if "10" in str(c) and "中国" in str(c)]
        if not china_10y_cols:
            logger.warning("无风险利率历史: 无法定位中国10Y国债收益率列（可用列: %s）", list(df.columns))
            return []
        value_col = china_10y_cols[0]

        rows: list[dict] = []
        for _, r in df.iterrows():
            raw_date, raw_value = r.iloc[0], r[value_col]
            if pd.isna(raw_value):
                continue  # 早期年份常为 NaN，跳过
            rate = float(raw_value) / 100.0
            if not (0 < rate < 1):
                continue
            rows.append({"date": str(raw_date).strip()[:10], "rate": rate})
        return rows

    except Exception as e:
        logger.warning("无风险利率历史: akshare bond_zh_us_rate 异常: %s", e)
        return []


__all__ = [
    "get_risk_free_rate",
    "get_risk_free_rate_history",
    "_CACHE_KEY_RF",
    "_CACHE_TTL_RF",
    "_fetch_from_akshare",
]
