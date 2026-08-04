"""因子暴露分析纯计算层单元测试。

覆盖：
  1. 满秩已知答案 OLS（精确还原 β/α）
  2. 单因子与 np.polyfit 交叉验证
  3. 高共线性诊断（factor_correlations + correlation_note）
  4. 有效样本 < 36 → 数据不足分支（available=False，绝不硬算）
  5. NaN/dropna 后 sample_count 反映真实有效期数
  6. 停更因子剔除（filter_stale_factor_klines）
  7. as-if 组合收益口径（小数收益、前值>0、LOCF）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/analysis/test_factor_exposure.py -v
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from src.python.analysis.factor_exposure import (
    FACTOR_STALE_DAYS,
    asif_portfolio_daily_returns,
    compute_factor_exposure,
    filter_stale_factor_klines,
    klines_to_returns,
    unavailable_result,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

_MIN_SAMPLES = 36


def _dates(n: int, start: str = "2026-01-05") -> list[str]:
    """生成 n 个连续的 ISO 日期（升序）。"""
    d = date.fromisoformat(start)
    out: list[str] = []
    for _ in range(n):
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _returns(series: list[float], n: int = 60) -> list[dict]:
    """将数值序列包装为 [{"date", "return"}]。"""
    dates = _dates(n)
    return [{"date": dates[i], "return": float(series[i])} for i in range(n)]


class TestKnownAnswerOLS:
    """满秩设计矩阵下的 OLS 精确还原。"""

    def test_full_rank_exact_recovery(self):
        """y = 0.001 + 2*x_value - x_growth（满秩）→ β/α 精确还原。"""
        rng = np.random.default_rng(42)
        x1 = np.round(rng.normal(0, 0.01, 60), 6)
        # x2 与 x1 满秩（避免共线性导致 lstsq 最小范数解劈分系数）
        x2 = np.round(rng.normal(0, 0.01, 60), 6)
        # 确保非共线（相关系数远离 ±1）
        assert abs(np.corrcoef(x1, x2)[0, 1]) < 0.2

        y = 0.001 + 2.0 * x1 - 1.0 * x2

        result = compute_factor_exposure(
            _returns(y.tolist()),
            {"value": _returns(x1.tolist()), "growth": _returns(x2.tolist())},
            window=60,
            min_samples=_MIN_SAMPLES,
        )

        assert result["available"] is True
        assert result["status"] == "ok"
        assert result["betas"]["value"] == pytest.approx(2.0, abs=1e-3)
        assert result["betas"]["growth"] == pytest.approx(-1.0, abs=1e-3)
        assert result["alpha"] == pytest.approx(0.001, abs=1e-4)
        assert result["sample_count"] == 60
        assert result["significant"]["value"] is True

    def test_single_factor_matches_polyfit(self):
        """单因子 y = 0.002 + 1.5*x 与 np.polyfit 交叉验证。"""
        rng = np.random.default_rng(7)
        x = np.round(rng.normal(0, 0.01, 60), 6)
        y = 0.002 + 1.5 * x

        result = compute_factor_exposure(
            _returns(y.tolist()),
            {"value": _returns(x.tolist())},
            window=60,
            min_samples=_MIN_SAMPLES,
        )

        slope, intercept = np.polyfit(x, y, 1)
        assert result["betas"]["value"] == pytest.approx(float(slope), abs=1e-6)
        assert result["alpha"] == pytest.approx(float(intercept), abs=1e-6)


class TestCollinearityDiagnostic:
    """因子高共线性诊断路径。"""

    def test_high_collinearity_sets_note(self):
        """|r|≥0.9 的因子对写入 factor_correlations 且生成 correlation_note。"""
        rng = np.random.default_rng(3)
        x1 = np.round(rng.normal(0, 0.01, 60), 6)
        x2 = np.round(x1 + rng.normal(0, 0.0005, 60), 6)  # 高度共线
        assert abs(np.corrcoef(x1, x2)[0, 1]) >= 0.9

        y = 0.001 + 1.0 * x1 + 0.5 * x2
        result = compute_factor_exposure(
            _returns(y.tolist()),
            {"value": _returns(x1.tolist()), "growth": _returns(x2.tolist())},
            window=60,
            min_samples=_MIN_SAMPLES,
        )

        assert result["available"] is True
        assert "价值-成长" in result["factor_correlations"]
        assert abs(result["factor_correlations"]["价值-成长"]) >= 0.9
        assert result["correlation_note"], "高度相关应生成 correlation_note"
        assert "高度相关" in result["correlation_note"]


class TestInsufficientData:
    """数据不足分支（§1.4.5 ①）——绝不硬算。"""

    def test_below_min_samples_returns_unavailable(self):
        """有效样本 < 36 → available=False + status=insufficient。"""
        rng = np.random.default_rng(1)
        x = np.round(rng.normal(0, 0.01, 20), 6)
        y = 0.001 + 1.5 * x

        result = compute_factor_exposure(
            _returns(y.tolist(), n=20),
            {"value": _returns(x.tolist(), n=20)},
            window=60,
            min_samples=_MIN_SAMPLES,
        )

        assert result["available"] is False
        assert result["status"] == "insufficient"
        assert result["sample_count"] == 20
        assert result["betas"] == {}
        assert result["t_stats"] == {}
        assert result["significant"] == {}

    def test_nan_dropna_reduces_sample_count(self):
        """收益序列含 None → dropna 后 sample_count 反映真实有效期数。"""
        rng = np.random.default_rng(2)
        n = 40
        x = np.round(rng.normal(0, 0.01, n), 6)
        y = 0.001 + 1.5 * x

        # 构造 portfolio 序列：中间插一个 None（无效日，dropna 剔除）
        dates = _dates(n)
        port = [{"date": dates[i], "return": float(y[i])} for i in range(n)]
        port[10]["return"] = None

        result = compute_factor_exposure(
            port,
            {"value": _returns(x.tolist(), n=n)},
            window=60,
            min_samples=_MIN_SAMPLES,
        )

        assert result["sample_count"] == n - 1, "dropna 后有效样本应为 n-1"
        assert result["available"] is True


class TestStaleFactorFilter:
    """停更因子剔除。"""

    def test_stale_factor_excluded(self):
        """末根 K 线距今超过 FACTOR_STALE_DAYS → 剔除并返回 stale 列表。"""
        today = "2026-08-01"
        stale_bar = [{"date": "2023-02-17", "close": 100.0}]
        fresh_bar = [{"date": "2026-07-30", "close": 100.0}]

        fresh, stale = filter_stale_factor_klines(
            {"value": fresh_bar, "growth": stale_bar},
            today,
        )

        assert "growth" in stale
        assert "value" not in stale
        assert set(fresh.keys()) == {"value"}

    def test_fresh_factor_kept(self):
        """近期有数据的因子保留。"""
        fresh, stale = filter_stale_factor_klines(
            {"value": [{"date": "2026-07-31", "close": 1.0}]},
            "2026-08-01",
        )
        assert fresh == {"value": [{"date": "2026-07-31", "close": 1.0}]}
        assert stale == []


class TestAsifReturns:
    """as-if 组合日收益口径（与 portfolio_history 一致）。"""

    def test_decimal_returns_prev_gt0_gate(self):
        """小数收益；前值=0 首日不计算；前值>0 才计算。"""
        holdings_bars = {
            "600900": {
                "shares": 100,
                "bars": [
                    {"date": "2026-01-05", "close": 10.0},
                    {"date": "2026-01-06", "close": 12.0},
                    {"date": "2026-01-07", "close": 13.0},
                ],
            }
        }
        result = asif_portfolio_daily_returns(holdings_bars)

        assert len(result) == 2
        assert result[0]["date"] == "2026-01-06"
        assert result[0]["return"] == pytest.approx((1200 - 1000) / 1000, abs=1e-9)
        assert result[1]["return"] == pytest.approx((1300 - 1200) / 1200, abs=1e-9)

    def test_locf_carries_forward_value(self):
        """多标的日期错开时，未更新标的沿用上次值（LOCF）。"""
        holdings_bars = {
            "A": {
                "shares": 10,
                "bars": [
                    {"date": "2026-01-05", "close": 100.0},
                    {"date": "2026-01-07", "close": 110.0},  # 06 日无更新
                ],
            },
            "B": {
                "shares": 10,
                "bars": [
                    {"date": "2026-01-05", "close": 50.0},
                    {"date": "2026-01-06", "close": 60.0},
                    {"date": "2026-01-07", "close": 60.0},
                ],
            },
        }
        result = asif_portfolio_daily_returns(holdings_bars)

        # 06 日 A 沿用 1000，B 更新 600 → 总值 1600；07 日 A 1100 + B 600 = 1700
        by_date = {r["date"]: r["return"] for r in result}
        assert by_date["2026-01-06"] == pytest.approx((1600 - 1500) / 1500, abs=1e-9)
        assert by_date["2026-01-07"] == pytest.approx((1700 - 1600) / 1600, abs=1e-9)

    def test_klines_to_returns_decimal(self):
        """K 线 → 小数日收益；无效价不跨日计算。"""
        bars = [
            {"date": "2026-01-05", "close": 10.0},
            {"date": "2026-01-06", "close": 0.0},  # 无效日
            {"date": "2026-01-07", "close": 12.0},
        ]
        result = klines_to_returns(bars)
        assert len(result) == 1
        assert result[0]["return"] == pytest.approx((12.0 - 10.0) / 10.0, abs=1e-9)


class TestUnavailableResult:
    """不可用结果工厂（数据契约）。"""

    def test_contract_keys_present(self):
        """unavailable_result 返回全部数据契约键，available=False。"""
        r = unavailable_result("insufficient", sample_count=5, stale_factors=["growth"])
        expected = {
            "available",
            "status",
            "betas",
            "t_stats",
            "significant",
            "style_allocation",
            "baseline_betas",
            "factor_correlations",
            "correlation_note",
            "alpha",
            "window",
            "sample_count",
            "stale_factors",
        }
        assert set(r.keys()) == expected
        assert r["available"] is False
        assert r["status"] == "insufficient"
        assert r["sample_count"] == 5
        assert r["stale_factors"] == ["growth"]
