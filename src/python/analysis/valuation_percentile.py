"""估值分位 — 纯计算层（价格分位代理估值分位）。

职责：接收历史 K 线 bars → 提取收盘价序列 → 计算当前价格分位
      → 映射低估/合理/高估三档刻度。

- 无数据获取、无报告依赖，纯标准库（日志走 logging，不用 print）。
- 价格分位 ≠ 真实历史估值分位（盈利增长未纳入），作为"贵不贵"近似信号，
  渲染层必须显式标注 ``DISCLAIMER``（"价格分位代理，非真实历史估值分位"）。
- 样本不足（< MIN_SAMPLES）或空序列 → available=False（绝不硬算，
  §1.4.5 数据降级治理）。PE/PB 当前值由编排层经网关
  ``fetcher/industry.py::fetch_valuation_fields``（Provider Chain + 缓存）取用，
  本模块不联网。
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


# ═══════════════════════════════════════════════════════════════
#  真实历史估值分位（TTM 口径）
# ═══════════════════════════════════════════════════════════════
#
# 与上方“价格分位代理”并列的第二套口径：价格分位衡量「价格自身处在历史什么位置」，
# 未纳入盈利增长；真实估值分位用「历史 PE/PB 序列」衡量「贵不贵」，需两个输入：
#   1. 历史收盘价序列（编排层经 K 线链取用）；
#   2. 多期基本面（每股收益 / 每股净资产，来自 ``financial_indicator`` 域）。
#
# **每股收益取 TTM（滚动四季）口径**：年报直接取当年 EPS；一季报/半年报/三季报按
# 「上年年报 + 本期累计 − 去年同期累计」差分。所需期数不全时不产该期 TTM（不猜）。
#
# **生效日取法定披露截止日**（年报/一季报 4-30、半年报 8-31、三季报 10-31）——
# 避免前视偏差：某期数据只在该日之后的历史价格上生效，绝不用「未来财报」解释过去价格。

#: 报告期（月-日）→ 法定披露截止日（月, 日）
_DISCLOSURE_DEADLINES: dict[str, tuple[int, int]] = {
    "1231": (4, 30),  # 年报：次年 4-30
    "0331": (4, 30),  # 一季报：同年 4-30
    "0630": (8, 31),  # 半年报：同年 8-31
    "0930": (10, 31),  # 三季报：同年 10-31
}

#: 真实估值分位的显式口径标注（渲染层与代理口径并列展示）
DISCLAIMER_REAL: str = "真实历史估值分位（TTM 口径，按法定披露截止日生效）"
DISCLAIMER_PROXY: str = DISCLAIMER

#: 单只标的历史估值序列的有效样本下限
MIN_VALUATION_SAMPLES: int = 60


class _Point:
    """一期基本面在时间轴上的生效点。"""

    __slots__ = ("report_period", "doc_type", "available_date", "ttm_eps", "bvps")

    def __init__(
        self, report_period: str, doc_type: str, available_date: str, ttm_eps: float | None, bvps: float | None
    ):
        self.report_period = report_period
        self.doc_type = doc_type
        self.available_date = available_date
        self.ttm_eps = ttm_eps
        self.bvps = bvps


def _finite(value: object) -> float | None:
    """取有限数值；NaN/±inf/缺失返回 None。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    num = float(value)
    return num if math.isfinite(num) else None


def disclosure_date(report_period: str) -> str | None:
    """报告期 → 法定披露截止日（``YYYY-MM-DD``）；口径不明返回 None。"""
    text = str(report_period or "")
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return None
    mmdd = f"{text[5:7]}{text[8:10]}"
    deadline = _DISCLOSURE_DEADLINES.get(mmdd)
    if deadline is None:
        return None
    year = int(text[:4]) + (1 if mmdd == "1231" else 0)
    return f"{year:04d}-{deadline[0]:02d}-{deadline[1]:02d}"


def ttm_eps_by_period(records: list[dict] | None) -> dict[str, float | None]:
    """逐报告期的 TTM 每股收益（所需期数不全 → None，不猜）。"""
    by_period: dict[str, dict] = {}
    for rec in records or []:
        period = str(rec.get("report_period") or "")
        if len(period) == 10:
            by_period[period] = rec

    out: dict[str, float | None] = {}
    for period, rec in by_period.items():
        eps = _finite(rec.get("eps"))
        mmdd = period[5:7] + period[8:10]
        if eps is None:
            out[period] = None
            continue
        if mmdd == "1231":
            out[period] = eps
            continue
        prev_year = int(period[:4]) - 1
        prev_annual = _finite((by_period.get(f"{prev_year:04d}-12-31") or {}).get("eps"))
        same_prev = _finite((by_period.get(f"{prev_year:04d}-{period[5:]}") or {}).get("eps"))
        out[period] = prev_annual + eps - same_prev if prev_annual is not None and same_prev is not None else None
    return out


def build_fundamental_points(records: list[dict] | None) -> list[_Point]:
    """多期指标 → 按生效日升序的基本面点（口径不明或不可用者剔除）。"""
    ttm = ttm_eps_by_period(records)
    points: list[_Point] = []
    for rec in records or []:
        period = str(rec.get("report_period") or "")
        available = disclosure_date(period)
        if available is None:
            continue
        points.append(
            _Point(
                report_period=period,
                doc_type=str(rec.get("doc_type") or ""),
                available_date=available,
                ttm_eps=ttm.get(period),
                bvps=_finite(rec.get("bvps")),
            )
        )
    # 同日生效（如年报与一季报同在 4-30 生效）时按报告期升序，使「已生效最新一期」
    # 恒为报告期更新者——否则同日并列会退化为输入顺序，可能取到更旧的年报口径
    points.sort(key=lambda p: (p.available_date, p.report_period))
    return points


def _bar_date(bar: object) -> str | None:
    """K 线 bar 的日期（``YYYY-MM-DD``）；不可解析返回 None。"""
    if not isinstance(bar, dict):
        return None
    for key in ("date", "day", "time", "datetime", "trade_date"):
        raw = bar.get(key)
        if raw is None:
            continue
        text = str(raw)[:10]
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return text
    return None


def _bar_close(bar: object) -> float | None:
    if not isinstance(bar, dict):
        return None
    for key in ("close", "nav", "price"):
        value = _finite(bar.get(key))
        if value is not None:
            return value
    return None


def _latest_point(points: list[_Point], date: str) -> _Point | None:
    """该日期已生效的最新一期基本面（生效日 ≤ date）。"""
    found: _Point | None = None
    for point in points:
        if point.available_date <= date:
            found = point
        else:
            break
    return found


def build_valuation_series(
    bars: list[dict] | None,
    points: list[_Point],
) -> tuple[list[float], list[float]]:
    """历史 PE / PB 序列（与交易日对齐，逐日取已生效的最近一期基本面）。

    亏损期（TTM 每股收益 ≤ 0）与非正净资产不产对应倍数（不参与分位）。
    """
    pe_values: list[float] = []
    pb_values: list[float] = []
    for bar in bars or []:
        date, close = _bar_date(bar), _bar_close(bar)
        if date is None or close is None or close <= 0:
            continue
        point = _latest_point(points, date)
        if point is None:
            continue
        if point.ttm_eps is not None and point.ttm_eps > 0:
            pe_values.append(close / point.ttm_eps)
        if point.bvps is not None and point.bvps > 0:
            pb_values.append(close / point.bvps)
    return pe_values, pb_values


def value_percentile(values: list[float], current: float | None) -> float | None:
    """当前值在历史序列中的分位（0~100）；样本不足或当前值不可用返回 None。"""
    if not values or len(values) < MIN_VALUATION_SAMPLES:
        return None
    current_num = _finite(current)
    if current_num is None or current_num <= 0:
        return None
    below = sum(1.0 for v in values if v <= current_num)
    return round(below / len(values) * 100.0, 2)


def compute_real_valuation(
    bars: list[dict] | None,
    records: list[dict] | None,
    current_price: float | None = None,
) -> dict:
    """真实历史估值分位（TTM 口径）—— PE 优先、PB 兜底。

    Args:
        bars: 历史 K 线（需 ``date`` + ``close``）
        records: ``financial_indicator`` 多期记录（需 ``report_period``/``eps``/``bvps``）
        current_price: 当前价；None 时取 K 线末值

    Returns:
        数据子契约 dict：``available`` / ``pe_ttm`` / ``pb`` / ``pe_percentile`` /
        ``pb_percentile`` / ``tier`` / ``basis``（``pe_ttm`` 或 ``pb``）/ ``sample_count`` /
        ``report_period`` / ``reason``；样本不足或输入缺失 → ``available=False``。
    """
    points = build_fundamental_points(records)
    base = {
        "available": False,
        "pe_ttm": None,
        "pb": None,
        "pe_percentile": None,
        "pb_percentile": None,
        "tier": None,
        "basis": None,
        "sample_count": 0,
        "report_period": "",
        "reason": None,
    }
    if not bars:
        base["reason"] = "no_bars"
        return base
    if not points:
        base["reason"] = "no_fundamentals"
        return base

    price = _finite(current_price)
    if price is None or price <= 0:
        price = _bar_close((bars or [])[-1])
    if price is None or price <= 0:
        base["reason"] = "no_price"
        return base

    pe_series, pb_series = build_valuation_series(bars, points)
    latest = points[-1]
    pe_ttm = latest.ttm_eps if latest.ttm_eps is not None and latest.ttm_eps > 0 else None
    pb = latest.bvps if latest.bvps is not None and latest.bvps > 0 else None
    current_pe = price / pe_ttm if pe_ttm else None
    current_pb = price / pb if pb else None
    pe_pct = value_percentile(pe_series, current_pe)
    pb_pct = value_percentile(pb_series, current_pb)

    if pe_pct is not None:
        tier, basis, sample_count = tier_from_percentile(pe_pct), "pe_ttm", len(pe_series)
    elif pb_pct is not None:
        tier, basis, sample_count = tier_from_percentile(pb_pct), "pb", len(pb_series)
    else:
        base.update(
            {
                "pe_ttm": round(pe_ttm, 4) if pe_ttm else None,
                "pb": round(pb, 4) if pb else None,
                "sample_count": max(len(pe_series), len(pb_series)),
                "report_period": latest.report_period,
                "reason": "insufficient_samples" if (pe_series or pb_series) else "no_overlap",
            }
        )
        return base

    return {
        "available": True,
        "pe_ttm": round(pe_ttm, 4) if pe_ttm else None,
        "pb": round(pb, 4) if pb else None,
        "pe_percentile": pe_pct,
        "pb_percentile": pb_pct,
        "tier": tier,
        "basis": basis,
        "sample_count": sample_count,
        "report_period": latest.report_period,
        "reason": None,
    }
