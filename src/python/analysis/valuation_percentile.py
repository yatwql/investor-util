"""估值分位 — 纯计算层（价格分位代理估值分位）。

职责：接收历史 K 线 bars → 提取收盘价序列 → 计算当前价格分位
      → 映射低估/合理/高估三档刻度。

- 无数据获取、无报告依赖，纯标准库（日志走 logging，不用 print）。
- 价格分位 ≠ 真实历史估值分位（盈利增长未纳入），作为"贵不贵"近似信号，
  渲染层必须显式标注 ``DISCLAIMER``（"价格分位代理，非真实历史估值分位"）。
- 样本不足（< MIN_SAMPLES）或空序列 → available=False（绝不硬算，
  §1.4.5 数据降级治理）。PE/PB 当前值由编排层从东财 push2 扩展字段获取
  （复用 ``providers/eastmoney_industry.make_push2_request`` 通道），本模块不联网。
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  估值分位常量
# ═══════════════════════════════════════════════════════════════

# 默认回看窗口（交易日 ≈ 3 年）
DEFAULT_LOOKBACK_DAYS: int = 750
# 有效样本下限：低于此判数据不足，不接受硬算（与因子暴露一致）
MIN_SAMPLES: int = 60
# 三档刻度边界（价格分位 %）
LOW_BOUND: float = 30.0  # 分位 < 此值 → 低估
HIGH_BOUND: float = 70.0  # 分位 > 此值 → 高估
# 显式局限标注（渲染层必须展示，合规/误导风险）
DISCLAIMER: str = "价格分位代理，非真实历史估值分位"

# 三档刻度中文名（文档/UI 统一口径）
TIER_UNDERVALUED = "低估"
TIER_FAIR = "合理"
TIER_OVERVALUED = "高估"


def tier_from_percentile(pct: float) -> str:
    """价格分位（0~100）→ 三档刻度。

    分位 < LOW_BOUND → 低估；> HIGH_BOUND → 高估；其余合理。
    阈值边界（=30 / =70）归入合理档。
    """
    if pct < LOW_BOUND:
        return TIER_UNDERVALUED
    if pct > HIGH_BOUND:
        return TIER_OVERVALUED
    return TIER_FAIR


def extract_closes(bars: list[dict]) -> list[float]:
    """从 K 线/净值 bars 提取收盘价序列（过滤 None/NaN）。

    字段优先顺序：close → nav → price（覆盖股票 K 线与场外基金净值两种结构）。

    Args:
        bars: [{"date", "close"/"nav"/"price", ...}, ...]

    Returns:
        数值收盘价列表；空序列返回 []。
    """
    closes: list[float] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        value = None
        for key in ("close", "nav", "price"):
            v = bar.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                value = float(v)
                break
        if value is None or not math.isfinite(value):
            continue
        closes.append(value)
    return closes


def price_percentile(closes: list[float], current: float | None = None) -> float | None:
    """计算当前价格在历史收盘价序列中的分位（0~100）。

    分位定义：``count(closes <= current) / len(closes) * 100``。
    固定 fixture 下与解析解一致（严格递增序列，第 k+1 个值分位 = (k+1)/N*100）。

    Args:
        closes: 历史收盘价序列（升序日期对应）。
        current: 当前价格；None 时取序列末值。

    Returns:
        分位百分数（0~100，保留 2 位）；样本不足或 current 非法返回 None。
    """
    if len(closes) < MIN_SAMPLES:
        return None
    if current is None:
        if not closes:
            return None
        current = closes[-1]
    if not math.isfinite(float(current)):
        return None
    below = sum(1.0 for c in closes if c <= float(current))
    return round(below / len(closes) * 100.0, 2)


def compute_price_percentile(bars: list[dict], current: float | None = None) -> dict:
    """计算价格分位并映射三档刻度（数据子契约）。

    Args:
        bars: 历史 K 线/净值 bars。
        current: 当前价格；None 时取序列末值。

    Returns:
        数据子契约 dict：
        {"available", "price_percentile", "tier", "sample_count", "reason"}
        available=False 时 reason 区分 "no_bars" / "insufficient_samples"。
    """
    closes = extract_closes(bars)
    if not closes:
        return {"available": False, "price_percentile": None, "tier": None, "sample_count": 0, "reason": "no_bars"}
    pct = price_percentile(closes, current)
    if pct is None:
        return {
            "available": False,
            "price_percentile": None,
            "tier": None,
            "sample_count": len(closes),
            "reason": "insufficient_samples",
        }
    return {
        "available": True,
        "price_percentile": pct,
        "tier": tier_from_percentile(pct),
        "sample_count": len(closes),
        "reason": None,
    }


def unavailable_valuation(status: str) -> dict:
    """返回不可用结果（数据子契约，available=False）。

    Args:
        status: "insufficient"（数据不足）或 "source_failed"（数据源故障）。
    """
    return {
        "available": False,
        "status": status,
        "by_code": {},
    }
