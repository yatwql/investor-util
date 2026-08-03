"""调仓 What-if 指定生效日时序回测纯计算测试。

覆盖 `analysis/whatif_backtest.py`：
  - compute_backtest_days 自然日→交易日折算 / 最小最大钳位 / 坏格式 / 未来日期
  - _align_series 并集日期 + pairwise LOCF + 首个双方有正值锚点 / 无锚点 / 0 值跳过
  - _normalize / _returns_from_values / _drawdown_series / _period_return / _vol_pct / _neg_dd
  - _build_metrics 5 行指标 + delta/arrow
  - compute_backtest_metrics 正常 / 数据不足 / 两侧空 / 无可对齐 / status 降级

数值断言使用 pytest.approx（浮点）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.python.analysis.whatif_backtest import (
    _align_series,
    _build_metrics,
    _drawdown_series,
    _locf,
    _neg_dd,
    _normalize,
    _period_return,
    _returns_from_values,
    _vol_pct,
    compute_backtest_days,
    compute_backtest_metrics,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _bars(dates: list[str], values: list[float]) -> list[dict]:
    """构造 [{date, total_value}] bars。"""
    return [{"date": d, "total_value": v} for d, v in zip(dates, values)]


def _daily_dates(start: str, n: int) -> list[str]:
    """从 start 生成 n 个连续日期（YYYY-MM-DD）。"""
    d = datetime.strptime(start, "%Y-%m-%d").date()
    return [(d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


# ── compute_backtest_days ──────────────────────────────────────


def test_compute_backtest_days_typical():
    """2026-07-01 → 44 天（33 自然日×5/7≈24 交易日 + 热身 20）。"""
    assert compute_backtest_days("2026-07-01", today=date(2026, 8, 3)) == 44


def test_compute_backtest_days_clamp_min():
    """生效日临近今日 → 钳位到最小 30 天。"""
    assert compute_backtest_days("2026-08-02", today=date(2026, 8, 3)) == 30


def test_compute_backtest_days_clamp_max():
    """生效日很遥远 → 钳位到最大 365 天。"""
    assert compute_backtest_days("2025-01-01", today=date(2026, 8, 3)) == 365


@pytest.mark.parametrize(
    "bad",
    ["2026/07/01", "07-01", "garbage", "", None],
)
def test_compute_backtest_days_invalid_format(bad):
    """格式无效 → None（不抛出）。"""
    assert compute_backtest_days(bad, today=date(2026, 8, 3)) is None


def test_compute_backtest_days_future_or_today_none():
    """生效日不早于今日（当天/未来）→ None。"""
    assert compute_backtest_days("2026-08-03", today=date(2026, 8, 3)) is None
    assert compute_backtest_days("2026-08-04", today=date(2026, 8, 3)) is None


# ── _locf / _align_series ─────────────────────────────────────


def test_locf():
    """前值填充：无值时沿用上一次已知值。"""
    assert _locf(["a", "b", "c"], {"a": 1.0, "c": 3.0}) == [1.0, 1.0, 3.0]
    assert _locf(["a", "b"], {"b": 2.0}) == [None, 2.0]
    assert _locf(["a"], {}) == [None]


def test_align_series_union_locf_anchor():
    """并集日期 + 各自 LOCF + 首个双方有正值锚点；生效日前 bars 丢弃。"""
    base = _bars(
        ["2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03"],
        [50.0, 100.0, 105.0, 110.0],
    )
    cand = _bars(["2026-07-01", "2026-07-03", "2026-07-04"], [200.0, 210.0, 220.0])
    labels, b_vals, c_vals = _align_series(base, cand, "2026-07-01")
    assert labels == ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"]
    assert b_vals == [100.0, 105.0, 110.0, 110.0], "基准 07-04 无值应 LOCF"
    assert c_vals == [200.0, 200.0, 210.0, 220.0], "目标 07-02 无值应 LOCF"


def test_align_series_skips_zero_anchor():
    """首值 0 → 锚点后移到双方首个正值。"""
    base = _bars(["2026-07-01", "2026-07-02", "2026-07-03"], [0.0, 100.0, 120.0])
    cand = _bars(["2026-07-01", "2026-07-02", "2026-07-03"], [50.0, 60.0, 70.0])
    labels, b_vals, c_vals = _align_series(base, cand, "2026-07-01")
    assert labels == ["2026-07-02", "2026-07-03"]
    assert b_vals == [100.0, 120.0]
    assert c_vals == [60.0, 70.0]


def test_align_series_no_common_anchor_none():
    """一侧无数据 → 无共同锚点 → None。"""
    base = _bars(["2026-07-01", "2026-07-02"], [100.0, 110.0])
    assert _align_series(base, [], "2026-07-01") is None
    assert _align_series([], [], "2026-07-01") is None


def test_align_series_all_before_effective_none():
    """两侧 bars 均早于生效日 → 空日期集 → None。"""
    base = _bars(["2026-06-28", "2026-06-29"], [10.0, 20.0])
    cand = _bars(["2026-06-29"], [5.0])
    assert _align_series(base, cand, "2026-07-01") is None


# ── 序列变换 ──────────────────────────────────────────────────


def test_normalize_to_100():
    """归一化到 100 基点，保留 4 位小数。"""
    assert _normalize([50.0, 100.0, 150.0], 100.0) == [50.0, 100.0, 150.0]
    assert _normalize([100.0, 200.0], 200.0) == [50.0, 100.0]


def test_returns_from_values():
    """相邻日收益率序列；前值 0 跳过。"""
    assert _returns_from_values([100.0, 110.0, 121.0]) == pytest.approx([0.1, 0.1])
    assert _returns_from_values([0.0, 100.0, 200.0]) == pytest.approx([1.0])


def test_drawdown_series_peak_tracking():
    """回撤序列（负百分比）：连续新高 → 0；回落 → 负值。"""
    assert _drawdown_series([100.0, 110.0, 121.0]) == [0.0, 0.0, 0.0]
    assert _drawdown_series([100.0, 110.0, 99.0]) == [0.0, 0.0, -10.0]
    assert _drawdown_series([100.0, 50.0]) == [0.0, -50.0]


def test_period_return():
    """区间收益（%）；空序列/首值非正 → None。"""
    assert _period_return([100.0, 125.0]) == 25.0
    assert _period_return([100.0, 99.0]) == -1.0
    assert _period_return([]) is None
    assert _period_return([0.0, 100.0]) is None


def test_vol_pct_constant_zero():
    """常量序列 → 零波动。"""
    assert _vol_pct([0.01] * 25) == 0.0


def test_vol_pct_insufficient_none():
    """长度不足 2 → None。"""
    assert _vol_pct([]) is None
    assert _vol_pct([0.01]) is None


def test_vol_pct_known_value():
    """年化波动率 = std(ddof=1) × √252（对照手算值）。"""
    rets = [0.1, -0.1, 0.1, -0.1]
    mean = 0.0
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    expected = (var**0.5) * (252**0.5) * 100
    assert _vol_pct(rets) == pytest.approx(round(expected, 2), abs=0.011)


def test_neg_dd():
    """正数幅度 → 负百分比；None → None。"""
    assert _neg_dd(0.123) == -12.3
    assert _neg_dd(None) is None


# ── _build_metrics ────────────────────────────────────────────


def test_build_metrics_rows_and_arrows():
    """5 行指标 + delta/arrow；样本不足的指标为 None。"""
    b_norm = [100.0, 105.0, 110.0]
    c_norm = [100.0, 103.0, 106.0]
    b_ret = _returns_from_values(b_norm)
    c_ret = _returns_from_values(c_norm)
    rows = _build_metrics(b_ret, c_ret, b_norm, c_norm)
    assert [r["key"] for r in rows] == [
        "period_return_pct",
        "annualized_return_pct",
        "annualized_volatility_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
    ]
    by_key = {r["key"]: r for r in rows}
    # 区间收益
    assert by_key["period_return_pct"]["base"] == 10.0
    assert by_key["period_return_pct"]["candidate"] == 6.0
    assert by_key["period_return_pct"]["delta"] == -4.0
    assert by_key["period_return_pct"]["arrow"] == "↓"
    # 单位映射
    assert by_key["period_return_pct"]["unit"] == "pct"
    assert by_key["sharpe_ratio"]["unit"] == "ratio"
    # 样本不足 → 指标 None，delta None，箭头 →
    assert by_key["sharpe_ratio"]["base"] is None
    assert by_key["max_drawdown_pct"]["delta"] is None
    assert by_key["max_drawdown_pct"]["arrow"] == "→"


# ── compute_backtest_metrics ──────────────────────────────────


def test_compute_backtest_metrics_normal():
    """正常路径：5 指标 + 序列 + 归一化到 100 + status ok。"""
    eff = "2026-07-01"
    dates = _daily_dates(eff, 25)
    base = _bars(dates, [100.0 + i for i in range(25)])
    cand = _bars(dates, [100.0 + 2 * i for i in range(25)])
    res = compute_backtest_metrics(base, cand, eff)

    assert res["available"] is True
    assert res["status"] == "ok"
    assert res["effective_date"] == eff
    assert res["reason"] == ""
    assert len(res["metrics"]) == 5
    assert len(res["series"]["labels"]) == 25
    assert res["series"]["base"][0] == 100.0
    assert res["series"]["candidate"][0] == 100.0
    assert res["series"]["base"][-1] == 124.0
    assert res["series"]["candidate"][-1] == 148.0

    by_key = {m["key"]: m for m in res["metrics"]}
    assert by_key["period_return_pct"]["base"] == 24.0
    assert by_key["period_return_pct"]["candidate"] == 48.0
    assert by_key["period_return_pct"]["delta"] == 24.0
    assert by_key["period_return_pct"]["arrow"] == "↑"
    # 单调上涨 → 最大回撤 0（-0.0 == 0.0）
    assert by_key["max_drawdown_pct"]["base"] == 0.0
    assert by_key["max_drawdown_pct"]["candidate"] == 0.0
    # 年化收益为正
    assert by_key["annualized_return_pct"]["base"] is not None
    assert by_key["annualized_return_pct"]["base"] > 0


def test_compute_backtest_metrics_insufficient_data():
    """生效日后交易日不足 20 → available=False 降级。"""
    eff = "2026-07-01"
    dates = _daily_dates(eff, 15)  # 15 天 → 14 个交易日
    base = _bars(dates, [100.0 + i for i in range(15)])
    cand = _bars(dates, [100.0 + 2 * i for i in range(15)])
    res = compute_backtest_metrics(base, cand, eff)
    assert res["available"] is False
    assert res["status"] == "unavailable"
    assert "不足" in res["reason"]


def test_compute_backtest_metrics_empty_both_sides():
    """两侧 bars 均空 → unavailable。"""
    res = compute_backtest_metrics([], [], "2026-07-01")
    assert res["available"] is False
    assert res["status"] == "unavailable"
    assert "无历史数据" in res["reason"]


def test_compute_backtest_metrics_no_align():
    """生效日后无可对齐锚点（目标侧全在生效日前）→ unavailable。"""
    eff = "2026-07-01"
    dates = _daily_dates(eff, 25)
    base = _bars(dates, [100.0 + i for i in range(25)])
    cand = _bars(["2026-06-20", "2026-06-21"], [50.0, 60.0])
    res = compute_backtest_metrics(base, cand, eff)
    assert res["available"] is False
    assert res["status"] == "unavailable"
    assert "可对齐" in res["reason"]


def test_compute_backtest_metrics_status_degraded():
    """任一侧 degraded → status=degraded + 提示文案。"""
    eff = "2026-07-01"
    dates = _daily_dates(eff, 25)
    base = _bars(dates, [100.0 + i for i in range(25)])
    cand = _bars(dates, [100.0 + 2 * i for i in range(25)])
    res = compute_backtest_metrics(base, cand, eff, base_status="degraded", cand_status="ok")
    assert res["available"] is True
    assert res["status"] == "degraded"
    assert "部分持仓" in res["reason"]
