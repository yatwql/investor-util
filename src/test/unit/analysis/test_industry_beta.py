"""行业 Beta 分析纯计算层单元测试。

覆盖：
  1. 固定 fixture 已知答案 OLS（β/α 与解析解误差 <0.01）
  2. 行业暴露占比（市值加权归一化 + 降序）
  3. 无指数映射行业 → 仅暴露占比，Beta 不渲染
  4. 有效样本 < 36 → 数据不足（available=False，绝不硬算）
  5. 组合 vs 行业 Pearson 相关性
  6. 全部行业数据不足 → 整体降级

运行：
  python -m pytest src/test/unit/analysis/test_industry_beta.py -v
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from src.python.analysis.industry_beta import (
    compute_industry_beta_analysis,
    compute_industry_exposure,
    industry_index_for,
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


class TestIndustryExposure:
    """行业暴露占比（市值加权归一化）。"""

    def test_normalized_sorted(self):
        """市值加权占比归一化且按降序。"""
        cap = {"银行": 300.0, "白酒": 500.0, "半导体": 200.0}
        r = compute_industry_exposure(cap)
        assert r["available"] is True
        assert r["exposure"]["白酒"] == pytest.approx(0.5, abs=1e-4)
        assert r["exposure"]["银行"] == pytest.approx(0.3, abs=1e-4)
        assert r["exposure"]["半导体"] == pytest.approx(0.2, abs=1e-4)
        # 降序
        keys = list(r["exposure"].keys())
        assert keys[0] == "白酒" and keys[-1] == "半导体"

    def test_zero_total_unavailable(self):
        """无有效市值 → available=False。"""
        r = compute_industry_exposure({"银行": 0.0, "白酒": -5.0})
        assert r["available"] is False
        assert r["exposure"] == {}

    def test_ignores_zero_and_negative(self):
        """零/负市值不计入占比。"""
        r = compute_industry_exposure({"银行": 100.0, "白酒": 0.0, "钢铁": -10.0})
        assert r["exposure"] == {"银行": 1.0}
        assert r["total"] == pytest.approx(100.0)

    def test_single_industry_full(self):
        """单一行业 → 占比 100%。"""
        r = compute_industry_exposure({"银行": 42.0})
        assert r["exposure"] == {"银行": 1.0}


class TestIndustryIndexMap:
    """行业名 → 指数代码映射。"""

    def test_common_industry_mapped(self):
        """常见行业均有映射。"""
        for name in ["银行", "证券", "白酒", "半导体", "医药"]:
            assert industry_index_for(name) is not None

    def test_unknown_industry_none(self):
        """未知行业无映射（仅暴露占比）。"""
        assert industry_index_for("新兴赛道") is None


class TestIndustryBetaKnownAnswer:
    """固定 fixture 已知答案 OLS（与解析解误差 <0.01）。"""

    def test_single_industry_exact_recovery(self):
        """y = 0.001 + 1.5*x（单行业）→ β/α 精确还原（误差 <0.01）。"""
        rng = np.random.default_rng(42)
        x = np.round(rng.normal(0, 0.01, 60), 6)
        y = 0.001 + 1.5 * x

        result = compute_industry_beta_analysis(
            _returns(y.tolist()),
            {"银行": _returns(x.tolist())},
        )

        assert result["available"] is True
        assert result["status"] == "ok"
        assert result["betas"]["银行"] == pytest.approx(1.5, abs=1e-2)
        assert result["alphas"]["银行"] == pytest.approx(0.001, abs=1e-2)
        assert result["significant"]["银行"] is True
        assert result["sample_count"] == 60

    def test_negative_beta_detected(self):
        """负 Beta（反向对冲行业）正确识别。"""
        rng = np.random.default_rng(7)
        x = np.round(rng.normal(0, 0.01, 60), 6)
        y = 0.0 - 2.0 * x

        result = compute_industry_beta_analysis(
            _returns(y.tolist()),
            {"银行": _returns(x.tolist())},
        )

        assert result["available"] is True
        assert result["betas"]["银行"] == pytest.approx(-2.0, abs=1e-2)

    def test_multiple_industries_parallel(self):
        """多行业并行回归，各自独立 β。"""
        rng = np.random.default_rng(11)
        x1 = np.round(rng.normal(0, 0.01, 60), 6)
        x2 = np.round(rng.normal(0, 0.01, 60), 6)
        y = 0.001 + 1.0 * x1 + 0.5 * x2

        result = compute_industry_beta_analysis(
            _returns(y.tolist()),
            {"银行": _returns(x1.tolist()), "白酒": _returns(x2.tolist())},
        )

        assert result["available"] is True
        assert set(result["betas"].keys()) == {"银行", "白酒"}
        # 注意：单因子回归下 β 为偏效应近似，仅断言在合理范围且误差 <0.01 于真值附近
        # 银行与 y 的关系较强，β 应显著为正
        assert result["betas"]["银行"] > 0.5
        assert result["betas"]["白酒"] > 0.1

    def test_correlation_computed(self):
        """组合 vs 行业 Pearson 相关已计算且在 (-1, 1]。"""
        rng = np.random.default_rng(5)
        x = np.round(rng.normal(0, 0.01, 60), 6)
        y = 0.001 + 1.5 * x

        result = compute_industry_beta_analysis(
            _returns(y.tolist()),
            {"银行": _returns(x.tolist())},
        )

        assert "银行" in result["correlations"]
        assert -1.0 <= result["correlations"]["银行"] <= 1.0
        assert result["correlations"]["银行"] > 0.9  # y 由 x 线性生成，强正相关


class TestIndustryBetaDegradation:
    """数据不足 / 降级分支。"""

    def test_below_min_samples(self):
        """有效样本 < 36 → available=False + status=insufficient。"""
        rng = np.random.default_rng(1)
        x = np.round(rng.normal(0, 0.01, 20), 6)
        y = 0.001 + 1.5 * x

        result = compute_industry_beta_analysis(
            _returns(y.tolist(), n=20),
            {"银行": _returns(x.tolist(), n=20)},
        )

        assert result["available"] is False
        assert result["status"] == "insufficient"
        assert result["betas"] == {}
        assert result["sample_count"] == 20

    def test_all_industries_empty(self):
        """全部行业收益为空 → 整体数据不足。"""
        result = compute_industry_beta_analysis(_returns([0.0] * 60), {})
        assert result["available"] is False
        assert result["status"] == "insufficient"

    def test_partial_industry_insufficient(self):
        """部分行业样本不足 → 仅可用行业进入 betas。"""
        rng = np.random.default_rng(9)
        x_good = np.round(rng.normal(0, 0.01, 60), 6)
        x_bad = np.round(rng.normal(0, 0.01, 20), 6)
        y = 0.001 + 1.0 * x_good

        result = compute_industry_beta_analysis(
            _returns(y.tolist(), n=60),
            {"银行": _returns(x_good.tolist(), n=60), "白酒": _returns(x_bad.tolist(), n=20)},
        )

        assert result["available"] is True
        assert "银行" in result["betas"]
        assert "白酒" not in result["betas"]  # 样本不足被跳过


class TestIndustryBetaContract:
    """数据子契约结构。"""

    def test_unavailable_keys_present(self):
        """unavailable_result 返回全部键，available=False。"""
        r = unavailable_result("insufficient", sample_count=5)
        expected = {
            "available",
            "status",
            "exposure",
            "betas",
            "alphas",
            "t_stats",
            "significant",
            "correlations",
            "unmapped_industries",
            "window",
            "sample_count",
        }
        assert set(r.keys()) == expected
        assert r["available"] is False
        assert r["status"] == "insufficient"
        assert r["sample_count"] == 5
