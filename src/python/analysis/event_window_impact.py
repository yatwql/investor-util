"""事件窗量化对照纯计算（event_window_impact）。

口径唯一定义（先决门槛「窗口口径可判定」的文档化落点）：

1. **事件日 → 交易日映射**：T 为交易日取 T；否则取其后第一个交易日（当日优先、
   前向探测 ≤14 自然日覆盖长假）。交易日判定唯一经
   ``core.trading_calendar.count_trading_days_elapsed``（禁自建日历）。
2. **窗口**：以映射交易日 T0 为中心在行情并集轴（品种 ∪ 基准）上切
   [-5, +5]（默认 11 个交易日）；对齐轴按日期并集，缺口前值填充（LOCF 复用
   ``analysis.whatif_backtest._locf`` 单源实现，不第二套）。
3. **窗口收益** = value(T0+1 位次的前一交易日) 基点：value(T0−1) → value(T0+5)
   ，即 ``end/prev − 1``（事件日前收盘持有到 T0 后第 5 个交易日收盘，覆盖事件日
   价格反应）；**超额** = 品种收益 − 基准收益。
4. **方向与比对**：direction = sign(品种窗口收益)（>0 上 / <0 下 / ==0 持平，
   不设人为容差）；文本极性 利好/利空/中性 与方向比对出
   一致 / 分歧 / 持平不判 / 中性不判 / 不可判。
5. **降级（只降级不硬算）**：品种窗口实测缺失占比 >30%、基准不可得、关键位
   （T0−1 / T0+5）无法解析、窗口越界或事件日无法映射 → ``available=False``
   并给出 reason（编排层据不出行/告警计数）。

零 I/O：行情 bars 与文本极性由编排层备入；函数不取行情、不调 LLM。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from src.python.analysis.whatif_backtest import _locf
from src.python.core.trading_calendar import count_trading_days_elapsed

logger = logging.getLogger("invest")

__all__ = [
    "WINDOW_BEFORE",
    "WINDOW_AFTER",
    "MISSING_RATIO_MAX",
    "map_event_to_trading_day",
    "assess_direction_match",
    "compute_event_impact",
]

#: 窗口：T0 前/后各 5 个交易日（窗口参数单点定义，面板与注入读同一份）
WINDOW_BEFORE = 5
WINDOW_AFTER = 5

#: 窗口内品种实测缺失占比上限（> 即降级不出行）
MISSING_RATIO_MAX = 0.30

_POLARITY利好 = "利好"
_POLARITY利空 = "利空"
_POLARITY中性 = "中性"


def _is_calendar_trading_day(day: str) -> bool:
    """day 是否交易日（唯一经 trading_calendar 计数派生：(day−1, day] 含 day）。"""
    try:
        prev = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return count_trading_days_elapsed(prev, day) == 1


def map_event_to_trading_day(event_date: str, max_lookahead: int = 14) -> str | None:
    """事件日 → 交易日：T 交易日取 T，否则取其后第一个交易日（≤14 自然日回退）。

    Args:
        event_date: YYYY-MM-DD 事件日期（新闻发布时间的日期部分）。
        max_lookahead: 前向探测上限（覆盖长假；覆盖不到返回 None 由调用方降级）。

    Returns:
        YYYY-MM-DD 交易日；映射失败返回 None。
    """
    try:
        base = datetime.strptime(str(event_date).strip(), "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    for i in range(max(0, int(max_lookahead)) + 1):
        cand = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        if _is_calendar_trading_day(cand):
            return cand
    return None


def assess_direction_match(direction: str, text_polarity: str | None) -> str:
    """量化方向 vs 文本极性：一致 / 分歧 / 持平不判 / 中性不判 / 不可判。"""
    if text_polarity is None or not str(text_polarity).strip():
        return "不可判"
    polarity = str(text_polarity).strip()
    if polarity == _POLARITY中性:
        return "中性不判"
    if direction == "持平":
        return "持平不判"
    if polarity not in (_POLARITY利好, _POLARITY利空):
        return "不可判"
    if direction == "上":
        return "一致" if polarity == _POLARITY利好 else "分歧"
    if direction == "下":
        return "一致" if polarity == _POLARITY利空 else "分歧"
    return "不可判"


def _closes(bars: list[dict[str, Any]] | None) -> dict[str, float]:
    """{date: close}，close 须为正的有限数值；坏行静默剔除（缺失降级语义）。"""
    out: dict[str, float] = {}
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        day = bar.get("date")
        if not day:
            continue
        try:
            value = float(bar.get("close"))
        except (TypeError, ValueError):
            continue
        if value > 0 and value == value and value != float("inf") and value != float("-inf"):
            out[str(day)] = value
    return out


def compute_event_impact(
    event_date: str,
    asset_bars: list[dict[str, Any]] | None,
    index_bars: list[dict[str, Any]] | None,
    text_polarity: str | None = None,
    asset_code: str = "",
    window_before: int = WINDOW_BEFORE,
    window_after: int = WINDOW_AFTER,
) -> dict[str, Any]:
    """单事件 × 品种/基准序列 → 窗口对齐、收益、超额、方向一致标记（纯函数）。

    Args:
        event_date: 事件日期 YYYY-MM-DD。
        asset_bars: 品种行情 [{date, close}]（编排层经 chain 备入）。
        index_bars: 基准指数行情 [{date, close}]（同上）。
        text_polarity: 文本判定极性（利好/利空/中性/其他/None）。
        asset_code: 品种代码（仅回显，不参与计算）。
        window_before/window_after: 窗口切分（默认单点定义的 ±5）。

    Returns:
        结果字典（available=False 时带 reason，其余键保持占位形态便于编排层收敛）。
    """
    result: dict[str, Any] = {
        "available": False,
        "reason": "",
        "asset_code": asset_code,
        "event_date": event_date,
        "trading_day": None,
        "window_dates": [],
        "anchor_date": None,
        "prev_date": None,
        "end_date": None,
        "asset_return": None,
        "index_return": None,
        "excess_return": None,
        "direction": "",
        "text_polarity": text_polarity,
        "match": "不可判",
        "missing_ratio": None,
        "index_missing_ratio": None,
        "locf_filled": 0,
    }

    def _fail(reason: str) -> dict[str, Any]:
        result["reason"] = reason
        logger.debug("事件窗降级 [%s %s]: %s", asset_code, event_date, reason)
        return dict(result)

    anchor = map_event_to_trading_day(event_date)
    if anchor is None:
        return _fail("事件日无法映射到交易日")
    result["trading_day"] = anchor

    asset_map = _closes(asset_bars)
    index_map = _closes(index_bars)
    if not asset_map:
        return _fail("品种行情不可得")
    if not index_map:
        return _fail("基准行情不可得")

    axis = sorted(set(asset_map) | set(index_map))
    try:
        anchor_pos = axis.index(anchor)
    except ValueError:
        return _fail("映射交易日不在行情轴")
    if anchor_pos - window_before < 0 or anchor_pos + window_after >= len(axis):
        return _fail("窗口超出行情范围")
    if anchor_pos < 1:
        return _fail("无事件日前基点")

    window = axis[anchor_pos - window_before : anchor_pos + window_after + 1]
    asset_full = dict(zip(axis, _locf(axis, asset_map), strict=True))
    index_full = dict(zip(axis, _locf(axis, index_map), strict=True))
    prev_day = axis[anchor_pos - 1]
    end_day = axis[anchor_pos + window_after]

    asset_prev, asset_end = asset_full[prev_day], asset_full[end_day]
    index_prev, index_end = index_full[prev_day], index_full[end_day]
    if asset_prev is None or asset_end is None:
        return _fail("品种关键位无法解析")
    if index_prev is None or index_end is None:
        return _fail("基准关键位无法解析")

    missing = sum(1 for day in window if day not in asset_map)
    missing_ratio = round(missing / len(window), 4)
    if missing_ratio > MISSING_RATIO_MAX:
        return _fail(f"品种窗口行情缺失 {missing_ratio:.0%} 超过 {MISSING_RATIO_MAX:.0%} 上限")

    asset_return = round(asset_end / asset_prev - 1, 8)
    index_return = round(index_end / index_prev - 1, 8)
    direction = "上" if asset_return > 0 else ("下" if asset_return < 0 else "持平")

    result.update(
        {
            "available": True,
            "reason": "",
            "window_dates": window,
            "anchor_date": anchor,
            "prev_date": prev_day,
            "end_date": end_day,
            "asset_return": asset_return,
            "index_return": index_return,
            "excess_return": round(asset_return - index_return, 8),
            "direction": direction,
            "match": assess_direction_match(direction, text_polarity),
            "missing_ratio": missing_ratio,
            "index_missing_ratio": round(sum(1 for day in window if day not in index_map) / len(window), 4),
            "locf_filled": missing,
        }
    )
    return result
