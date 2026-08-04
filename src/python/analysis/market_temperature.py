"""市场温度 — 纯计算层（价格分位 + 均线偏离 + 波动率三因子合成）。

职责：接收指数历史 K 线 bars → 提取收盘价序列 → 合成三因子温度分
      → 映射低估/合理/高估三档"温度计"。

- 无数据获取、无报告依赖，纯标准库（日志走 logging，不用 print）。
- **复用** ``valuation_percentile.price_percentile``（价格分位机制，
  本模块不自行重写）。指数 K 线由编排层走 Chain + session_cache
  （report/orchestrator.py），本模块不联网。
- 三因子合成权重：价格分位 0.5 + 均线偏离 0.3 + 波动率 0.2，输出 0~100 温度分。
- **温度计只给刻度，不做仓位硬建议**（"建议几成仓"合规与误导风险高），
  渲染层必须展示 ``TEMPERATURE_DISCLAIMER``。
- 样本不足（< MIN_SAMPLES）或空序列 → available=False（§1.4.5 数据降级治理）。
"""

from __future__ import annotations

import logging
import math

from src.python.analysis.valuation_percentile import (
    MIN_SAMPLES,
    extract_closes,
    price_percentile,
    tier_from_percentile,
)

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  市场温度常量
# ═══════════════════════════════════════════════════════════════

# 默认指数代码（沪深300；编排层可覆盖）
DEFAULT_INDEX_CODE: str = "sh000300"
DEFAULT_INDEX_NAME: str = "沪深300"
# 默认回看窗口（交易日 ≈ 3 年）
DEFAULT_LOOKBACK_DAYS: int = 750
# 均线窗口（交易日）
MA_WINDOW: int = 20
# 波动率窗口（交易日）
VOL_WINDOW: int = 20
# 年化交易日数
TRADING_DAYS_PER_YEAR: int = 252

# 三因子合成权重
W_PERCENTILE: float = 0.5
W_MA_DEVIATION: float = 0.3
W_VOLATILITY: float = 0.2
# 均线偏离映射区间（±20% 线性映射到 0~100）
MA_DEVIATION_SPAN: float = 0.4
# 年化波动率映射上限（50% 对应 100）
VOLATILITY_SPAN: float = 0.5

# 免责声明（渲染层必须展示，合规）
TEMPERATURE_DISCLAIMER: str = "市场温度为价格分位、均线偏离与波动率三因子合成的信号，仅供参考，不构成任何仓位建议"

# 三档刻度中文名（与估值分位一致，文档/UI 统一口径）
TIER_UNDERVALUED = "低估"
TIER_FAIR = "合理"
TIER_OVERVALUED = "高估"


# ═══════════════════════════════════════════════════════════════
#  单因子计算
# ═══════════════════════════════════════════════════════════════


def moving_average(closes: list[float], window: int = MA_WINDOW) -> float | None:
    """最近 window 期简单移动平均。样本不足返回 None。"""
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def ma_deviation(closes: list[float], current: float | None = None, window: int = MA_WINDOW) -> float | None:
    """均线偏离：(当前价 - MA) / MA。样本不足或 MA 为 0 返回 None。"""
    ma = moving_average(closes, window)
    if ma is None or abs(ma) <= 1e-12:
        return None
    cur = closes[-1] if current is None else current
    if not math.isfinite(float(cur)):
        return None
    return (float(cur) - ma) / ma


def returns_volatility(closes: list[float], window: int = VOL_WINDOW) -> float | None:
    """年化波动率：最近 window 期日收益率的样本标准差 × √252。

    样本不足（<2 个收益率）或序列非有限值返回 None。
    """
    if len(closes) < 2:
        return None
    returns: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        cur = closes[i]
        if prev > 0 and math.isfinite(prev) and math.isfinite(cur):
            returns.append((cur - prev) / prev)
    if len(returns) < 2:
        return None
    tail = returns[-window:]
    mean = sum(tail) / len(tail)
    var = sum((r - mean) ** 2 for r in tail) / (len(tail) - 1)
    return math.sqrt(var * TRADING_DAYS_PER_YEAR)


# ═══════════════════════════════════════════════════════════════
#  三因子合成
# ═══════════════════════════════════════════════════════════════


def _ma_component(ma_dev: float) -> float:
    """均线偏离 → 0~100 分量（±20% 线性映射，越正越"热"）。"""
    return max(0.0, min(100.0, (ma_dev + MA_DEVIATION_SPAN / 2) / MA_DEVIATION_SPAN * 100.0))


def _vol_component(vol: float) -> float:
    """年化波动率 → 0~100 分量（0~50% 线性映射，越高越"热"）。"""
    return max(0.0, min(100.0, vol / VOLATILITY_SPAN * 100.0))


def temperature_score(pct: float, ma_dev: float, vol: float) -> float:
    """三因子合成温度分（0~100）。

    score = 0.5×分位 + 0.3×均线偏离分量 + 0.2×波动率分量。
    各分量经 clamp 映射，保证结果在 [0, 100]。
    """
    score = (
        W_PERCENTILE * float(pct)
        + W_MA_DEVIATION * _ma_component(float(ma_dev))
        + W_VOLATILITY * _vol_component(float(vol))
    )
    return round(max(0.0, min(100.0, score)), 2)


def compute_temperature(bars: list[dict], current: float | None = None) -> dict:
    """计算市场温度（数据子契约）。

    Args:
        bars: 指数历史 K 线 bars（date + close）。
        current: 当前点位；None 时取序列末值。

    Returns:
        数据子契约 dict：
        {"available", "price_percentile", "ma_deviation", "volatility",
         "score", "tier", "sample_count", "components", "reason"}
        available=False 时 reason 区分 "no_bars" / "insufficient_samples"。
    """
    closes = extract_closes(bars)
    if not closes:
        return _unavailable("no_bars", 0)

    pct = price_percentile(closes, current)
    if pct is None:
        return _unavailable("insufficient_samples", len(closes))

    cur = closes[-1] if current is None else float(current)
    dev = ma_deviation(closes, cur, MA_WINDOW)
    vol = returns_volatility(closes, VOL_WINDOW)
    if dev is None or vol is None:
        return _unavailable("insufficient_samples", len(closes))

    score = temperature_score(pct, dev, vol)
    return {
        "available": True,
        "price_percentile": pct,
        "ma_deviation": round(dev, 6),
        "volatility": round(vol, 6),
        "score": score,
        "tier": tier_from_percentile(score),
        "sample_count": len(closes),
        "components": {
            "percentile_weight": W_PERCENTILE,
            "ma_deviation_weight": W_MA_DEVIATION,
            "volatility_weight": W_VOLATILITY,
        },
        "reason": None,
    }


def _unavailable(reason: str, sample_count: int) -> dict:
    """返回不可用温度结果（数据子契约）。"""
    return {
        "available": False,
        "price_percentile": None,
        "ma_deviation": None,
        "volatility": None,
        "score": None,
        "tier": None,
        "sample_count": sample_count,
        "components": None,
        "reason": reason,
    }


def unavailable_temperature(status: str) -> dict:
    """返回不可用结果（数据子契约，available=False）。

    Args:
        status: "insufficient"（数据不足）或 "source_failed"（数据源故障）。
    """
    return {
        "available": False,
        "status": status,
        "index_code": DEFAULT_INDEX_CODE,
        "index_name": DEFAULT_INDEX_NAME,
        "price_percentile": None,
        "ma_deviation": None,
        "volatility": None,
        "score": None,
        "tier": None,
        "sample_count": 0,
        "components": None,
        "reason": None,
        "disclaimer": TEMPERATURE_DISCLAIMER,
    }
