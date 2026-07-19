"""Rf 无风险利率获取器 — bond_zh_us_rate + 用户配置兜底。

主源：akshare bond_zh_us_rate() → 中国 10Y 国债收益率；
手动兜底：config.json risk_free_rate 字段（非 None 时跳过 fetcher）。
"""
  - 缓存：成功结果缓存 1 天，避免重复 akshare 调用

返回值为小数（如 0.017404 代表 1.7404%），可直接用于夏普比率等计算。
返回值可能为 None（数据源不可用且无手动配置）。

C6 约束：走独立 fetcher，不绕过 chain 层。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.config import get_config

logger = logging.getLogger("invest")

_CACHE_KEY_RF = "bond_yield_rf"
_CACHE_TTL_RF = 86400  # 1 天


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
                logger.info("Rf: 使用用户配置 risk_free_rate = %.4f (%s)", rf, "手动配置")
                return rf
            elif rf >= 1:
                # 用户可能填的是百分比（如 1.74 而非 0.0174），自动转换
                rf_adj = rf / 100
                logger.info("Rf: 用户配置 %.4f 疑似百分比，自动转换为 %.6f", rf, rf_adj)
                return rf_adj
            else:
                logger.warning("Rf: 用户配置 risk_free_rate = %.4f 超出合理范围，跳过", rf)
    except (TypeError, ValueError, KeyError) as e:
        logger.debug("Rf: 解析用户配置失败: %s", e)

    # ── 2. 缓存 ──
    if cache_ok:
        cached = cache_get(_CACHE_KEY_RF, _CACHE_TTL_RF)
        if cached is not None:
            try:
                rf = float(cached)
                logger.info("Rf: 缓存命中 = %.4f", rf)
                return rf
            except (TypeError, ValueError):
                logger.debug("Rf: 缓存值解析失败")

    # ── 3. akshare 实时获取 ──
    try:
        rf = _fetch_from_akshare()
        if rf is not None:
            cache_set(_CACHE_KEY_RF, rf)
            return rf
    except Exception as e:
        logger.warning("Rf: akshare 获取失败: %s", e)

    logger.warning("Rf: 全部数据源不可用，返回 None")
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
        logger.warning("Rf: akshare 未安装，无法获取")
        return None

    try:
        df = ak.bond_zh_us_rate()
        if df is None or df.empty:
            logger.warning("Rf: bond_zh_us_rate 返回空数据")
            return None

        # 取最后一行（最新日期）的中国国债收益率 10 年
        # DataFrame 列顺序稳定：col 0=日期, col 3=中国国债收益率10年
        latest_row = df.iloc[-1]
        china_10y_col = df.columns[3]  # 中国国债收益率10年
        raw_value = latest_row[china_10y_col]

        if pd.isna(raw_value):
            logger.warning("Rf: 最新值缺失（NaN）")
            return None

        # bond_zh_us_rate 返回的值为百分比（如 1.7404），需转为小数
        rf = float(raw_value) / 100.0

        if rf <= 0 or rf >= 1:
            logger.warning("Rf: 获取值 %.4f 超出合理范围（期望 0~1）", rf)
            return None

        logger.info("Rf: akshare 获取成功 = %.4f (%s)", rf, latest_row.iloc[0])
        return rf

    except Exception as e:
        logger.warning("Rf: akshare bond_zh_us_rate 异常: %s", e)
        return None


__all__ = [
    "get_risk_free_rate",
    "_CACHE_KEY_RF",
    "_CACHE_TTL_RF",
    "_fetch_from_akshare",
]
