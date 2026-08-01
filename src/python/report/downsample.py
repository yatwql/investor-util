"""P1 服务端下采样（§4.9）— 将日频净值 bars 聚合为周/月频。

chart_data_builder 调用本模块，避免其超过行数预算（≤400 行，§4.11 O4）。
下采样仅作用于 Chart.js 数据集，不改动 history_data.bars 原值。

契约（§4.9 验收标准）：
- len(bars) ≤ 500 → 保留日频原样
- len(bars) > 500 → 周聚合（取每周最后一条）
- 周聚合后点数仍 > 200 → 月聚合兜底
- 取周期末值而非平均，保证曲线形态不畸变
"""

from __future__ import annotations

from datetime import datetime

# ── 下采样阈值（§4.9）─────────────────────────────────────
DOWNSAMPLE_WEEK_THRESHOLD = 500  # 日频 > 500 点（约 2 年）→ 周聚合
DOWNSAMPLE_MONTH_THRESHOLD = 200  # 周聚合仍 > 200 点 → 月聚合兜底


def aggregate_bars_last(bars: list, key_fn) -> list:
    """按 key_fn 分组合并，每组取最后一条（bars 已按日期升序）。

    保证曲线形态不畸变：取周期末值而非平均（§4.9）。
    """
    result: list = []
    last_key = None
    for b in bars:
        k = key_fn(b["date"])
        if k != last_key:
            result.append(b)
            last_key = k
        else:
            result[-1] = b  # 同组内覆盖为最后一条
    return result


def week_key(date_str: str) -> tuple:
    """按 ISO 年-周分组键。"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    iso = d.isocalendar()
    return (iso[0], iso[1])


def month_key(date_str: str) -> str:
    """按 年-月 分组键。"""
    return date_str[:7]


def downsample_bars(bars: list) -> list:
    """P1 服务端下采样（§4.9 验收标准）。

    - len(bars) ≤ 500 → 保留日频原样
    - len(bars) > 500 → 周聚合（取每周最后一条）
    - 周聚合后点数仍 > 200 → 月聚合兜底
    """
    n = len(bars)
    if n <= DOWNSAMPLE_WEEK_THRESHOLD:
        return bars
    weekly = aggregate_bars_last(bars, week_key)
    if len(weekly) > DOWNSAMPLE_MONTH_THRESHOLD:
        return aggregate_bars_last(bars, month_key)
    return weekly
