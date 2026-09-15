"""估值分位纯计算层单元测试（价格分位代理层 + 真实历史估值分位 TTM 口径）。

覆盖：收盘价提取 / 价格分位解析解 / 三档刻度映射 / 数据不足 / 显式局限标注；
以及 TTM 每股收益差分构造 / 法定披露截止日生效 / 历史 PE·PB 序列对齐（无前视）/
真实分位与口径标注（PE 优先、PB 兜底）。
"""

from __future__ import annotations

import pytest

from src.python.analysis.valuation_percentile import (
    DISCLAIMER,
    DISCLAIMER_REAL,
    MIN_SAMPLES,
    MIN_VALUATION_SAMPLES,
    build_fundamental_points,
    build_valuation_series,
    compute_price_percentile,
    compute_real_valuation,
    disclosure_date,
    extract_closes,
    price_percentile,
    tier_from_percentile,
    ttm_eps_by_period,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


class TestExtractCloses:
    def test_close_key_preferred(self):
        """股票 K 线优先取 close 字段。"""
        bars = [
            {"date": "2024-01-01", "close": 10.0, "nav": 11.0},
            {"date": "2024-01-02", "close": 10.5, "nav": 11.2},
        ]
        assert extract_closes(bars) == [10.0, 10.5]

    def test_nav_fallback_for_fund(self):
        """场外基金净值 bars 无 close 时回退 nav。"""
        bars = [{"date": "2024-01-01", "nav": 1.2}, {"date": "2024-01-02", "nav": 1.3}]
        assert extract_closes(bars) == [1.2, 1.3]

    def test_filters_none_and_nan(self):
        """过滤 None/NaN/非数值字段。"""
        bars = [
            {"date": "2024-01-01", "close": 10.0},
            {"date": "2024-01-02", "close": None},
            {"date": "2024-01-03", "close": float("nan")},
            {"date": "2024-01-04", "close": 11.0},
        ]
        assert extract_closes(bars) == [10.0, 11.0]

    def test_empty_bars(self):
        assert extract_closes([]) == []


class TestPricePercentile:
    def test_analytic_series_midpoint(self):
        """固定 fixture：严格递增 750 日序列，第 375 个值分位恰为 50.0%。"""
        closes = [float(i) for i in range(1, 751)]
        pct = price_percentile(closes, current=375.0)
        assert pct is not None
        assert abs(pct - 50.0) < 0.5  # 解析解误差 < 0.5%

    def test_analytic_series_quarter(self):
        """递增 400 日序列，第 100 个值分位 = 100/400 = 25.0%。"""
        closes = [float(i) for i in range(1, 401)]
        pct = price_percentile(closes, current=100.0)
        assert pct is not None
        assert abs(pct - 25.0) < 0.5

    def test_current_last_by_default(self):
        """current 缺省时取序列末值 → 分位 100%。"""
        closes = [1.0, 2.0, 3.0, 4.0, 5.0] * 20  # 100 个样本
        assert price_percentile(closes) == 100.0

    def test_insufficient_samples_returns_none(self):
        """样本不足（< MIN_SAMPLES）返回 None。"""
        assert price_percentile([1.0, 2.0]) is None

    def test_min_samples_threshold(self):
        """恰好达到 MIN_SAMPLES 可计算。"""
        closes = [float(i) for i in range(MIN_SAMPLES)]
        assert price_percentile(closes) is not None

    def test_low_end(self):
        """最低价 → 分位 ~1%（含自身）。"""
        closes = [float(i) for i in range(1, 101)]
        assert abs(price_percentile(closes, current=1.0) - 1.0) < 0.5

    def test_high_end(self):
        """最高价 → 分位 100%。"""
        closes = [float(i) for i in range(1, 101)]
        assert price_percentile(closes, current=100.0) == 100.0


class TestTierFromPercentile:
    def test_low(self):
        assert tier_from_percentile(10.0) == "低估"

    def test_fair(self):
        assert tier_from_percentile(50.0) == "合理"

    def test_high(self):
        assert tier_from_percentile(85.0) == "高估"

    def test_low_boundary_below(self):
        assert tier_from_percentile(29.99) == "低估"

    def test_high_boundary_above(self):
        assert tier_from_percentile(70.01) == "高估"

    def test_boundary_30_is_fair(self):
        assert tier_from_percentile(30.0) == "合理"

    def test_boundary_70_is_fair(self):
        assert tier_from_percentile(70.0) == "合理"


class TestComputePricePercentile:
    def test_available_with_tier(self):
        """正常返回：分位 + 三档刻度 + 样本数。"""
        bars = [{"date": f"d{i}", "close": float(i)} for i in range(1, 101)]
        result = compute_price_percentile(bars)
        assert result["available"] is True
        assert result["price_percentile"] == 100.0
        assert result["tier"] == "高估"
        assert result["sample_count"] == 100
        assert result["reason"] is None

    def test_insufficient(self):
        """样本不足 → available=False + 原因。"""
        result = compute_price_percentile([{"date": "d1", "close": 1.0}])
        assert result["available"] is False
        assert result["reason"] == "insufficient_samples"

    def test_no_bars(self):
        """空序列 → available=False + 原因。"""
        result = compute_price_percentile([])
        assert result["available"] is False
        assert result["reason"] == "no_bars"


class TestDisclaimer:
    def test_proxy_disclaimer_present(self):
        """显式局限标注必须出现（合规断言）。"""
        assert "价格分位代理" in DISCLAIMER
        assert "非真实历史估值分位" in DISCLAIMER


def _bars(start_price: float, days: int, start_day: int = 1) -> list[dict]:
    """构造逐日收盘价序列（线性递增，日期为 2024 年内递增）。"""
    import datetime

    base = datetime.date(2025, 4, 30)
    return [
        {
            "date": (base + datetime.timedelta(days=start_day + i)).isoformat(),
            "close": start_price + i * 0.01,
        }
        for i in range(days)
    ]


def _records(*specs) -> list[dict]:
    """构造多期指标记录：``(报告期, eps, bvps)``。"""
    return [{"report_period": period, "doc_type": "x", "eps": eps, "bvps": bvps} for period, eps, bvps in specs]


class TestDisclosureDate:
    def test_deadline_mapping(self):
        """生效日 = 法定披露截止日（年报为次年）。"""
        assert disclosure_date("2025-12-31") == "2026-04-30"
        assert disclosure_date("2025-03-31") == "2025-04-30"
        assert disclosure_date("2025-06-30") == "2025-08-31"
        assert disclosure_date("2025-09-30") == "2025-10-31"

    def test_non_standard_period_has_no_date(self):
        assert disclosure_date("2025-02-29") is None
        assert disclosure_date("2025-12-31日") is None
        assert disclosure_date("") is None
        assert disclosure_date(None) is None


class TestTtmEps:
    def test_annual_uses_reported_eps(self):
        assert ttm_eps_by_period(_records(("2024-12-31", 2.0, 10.0)))["2024-12-31"] == 2.0

    def test_quarterly_uses_cumulative_difference(self):
        """一季报 TTM = 上年年报 + 本期累计 − 去年同期累计。"""
        recs = _records(
            ("2024-12-31", 4.0, 10.0),
            ("2025-03-31", 1.2, 10.5),
            ("2024-03-31", 1.0, 9.0),
        )
        assert ttm_eps_by_period(recs)["2025-03-31"] == pytest.approx(4.0 + 1.2 - 1.0)

    def test_half_and_third_quarter_differences(self):
        recs = _records(
            ("2024-12-31", 4.0, 10.0),
            ("2024-06-30", 2.0, 9.5),
            ("2024-09-30", 3.0, 9.8),
            ("2025-06-30", 2.4, 10.6),
            ("2025-09-30", 3.6, 11.0),
        )
        ttm = ttm_eps_by_period(recs)
        assert ttm["2025-06-30"] == pytest.approx(4.0 + 2.4 - 2.0)
        assert ttm["2025-09-30"] == pytest.approx(4.0 + 3.6 - 3.0)

    def test_missing_prior_period_gives_none(self):
        """缺去年年报或去年同期 → 该期 TTM 不产（不猜）。"""
        ttm = ttm_eps_by_period(_records(("2025-03-31", 1.2, 10.5)))
        assert ttm["2025-03-31"] is None


class TestFundamentalPoints:
    def test_points_sorted_by_disclosure_date(self):
        recs = _records(("2025-03-31", 1.0, 10.0), ("2024-12-31", 4.0, 9.9))
        points = build_fundamental_points(recs)
        # 同日生效（4-30）：按报告期升序，末位恒为更新的一期
        assert [p.report_period for p in points] == ["2024-12-31", "2025-03-31"]
        assert [p.available_date for p in points] == ["2025-04-30", "2025-04-30"]

    def test_unknown_period_dropped(self):
        assert build_fundamental_points(_records(("2025-02-29", 1.0, 10.0))) == []


class TestValuationSeries:
    def test_no_lookahead_before_disclosure(self):
        """生效日之前的历史价格不参与估值序列（避免用未来财报解释过去价格）。"""
        recs = _records(("2024-12-31", 2.0, 10.0))  # 生效 2025-04-30
        bars = [
            {"date": "2025-04-29", "close": 20.0},
            {"date": "2025-04-30", "close": 22.0},
            {"date": "2025-05-06", "close": 24.0},
        ]
        pe, pb = build_valuation_series(bars, build_fundamental_points(recs))
        assert pe == [pytest.approx(11.0), pytest.approx(12.0)]
        assert pb == [pytest.approx(2.2), pytest.approx(2.4)]

    def test_pb_uses_point_in_time_bvps(self):
        recs = _records(("2024-12-31", 2.0, 10.0), ("2025-06-30", 2.4, 12.0))
        bars = [{"date": "2025-09-30", "close": 24.0}]
        _, pb = build_valuation_series(bars, build_fundamental_points(recs))
        assert pb == [pytest.approx(2.0)]  # 取已生效最新一期（半年报）净资产 12.0

    def test_loss_period_excluded_from_pe_series(self):
        recs = _records(("2024-12-31", -1.0, 10.0))
        bars = [{"date": "2025-05-06", "close": 20.0}]
        pe, pb = build_valuation_series(bars, build_fundamental_points(recs))
        assert pe == []
        assert pb == [pytest.approx(2.0)]


class TestComputeRealValuation:
    def _series(self, days=120, price_from=10.0):
        return _bars(price_from, days)

    def test_pe_basis_with_rising_price(self):
        """价格单边上行 → 当前 PE 位于历史高位（分位 100），档位高估。"""
        recs = _records(("2024-12-31", 1.0, 10.0))
        out = compute_real_valuation(self._series(120), recs)
        assert out["available"] is True
        assert out["basis"] == "pe_ttm"
        assert out["pe_percentile"] == 100.0
        assert out["tier"] == "高估"
        assert out["sample_count"] == 120
        assert out["report_period"] == "2024-12-31"
        assert out["pe_ttm"] == pytest.approx(1.0)

    def test_pb_fallback_when_loss(self):
        """亏损（TTM EPS ≤ 0）→ PE 不可用，回落 PB 口径并标注 basis。"""
        recs = _records(("2024-12-31", -0.5, 10.0))
        out = compute_real_valuation(self._series(120), recs)
        assert out["available"] is True
        assert out["basis"] == "pb"
        assert out["pe_ttm"] is None
        assert out["tier"] == "高估"

    def test_insufficient_samples(self):
        recs = _records(("2024-12-31", 1.0, 10.0))
        out = compute_real_valuation(self._series(MIN_VALUATION_SAMPLES - 1), recs)
        assert out["available"] is False
        assert out["reason"] == "insufficient_samples"

    def test_missing_inputs_reasons(self):
        assert compute_real_valuation([], _records(("2024-12-31", 1.0, 10.0)))["reason"] == "no_bars"
        assert compute_real_valuation(self._series(120), [])["reason"] == "no_fundamentals"

    def test_declared_disclaimer_marks_ttm(self):
        assert "TTM" in DISCLAIMER_REAL
        assert "法定披露截止日" in DISCLAIMER_REAL
