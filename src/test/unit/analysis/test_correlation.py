"""持仓相关性矩阵纯计算层单元测试。

覆盖：
  1. 已知答案：完全正相关（r=1）、完全负相关（r=-1）、缩放不改变 r
  2. 不显著配对：sin vs cos → p≥0.05，significant=False
  3. 矩阵布局：下三角（row>col 有值）、对角=1.0、上三角 None
  4. 配对明细按 |r| 降序
  5. 数据不足分支：重叠样本 <60 / 单品种 → available=False，status="insufficient"
  6. 名称回退：names_by_code 缺失时回退 code 本身
  7. C19 契约键完整性（含 unavailable_result 工厂）
  8. 常数序列 → (0.0, 1.0) 不显著（绝不硬算）

运行：
  python -m pytest src/test/unit/analysis/test_correlation.py -v
"""

from __future__ import annotations

import math

import pytest

from src.python.analysis.correlation import (
    DEFAULT_WINDOW,
    MIN_HOLDINGS,
    MIN_SAMPLES,
    SIGNIFICANCE_LEVEL,
    _pearson_pvalue,
    compute_correlation_matrix,
    unavailable_result,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

_C19_KEYS = {
    "available",
    "status",
    "window",
    "sample_count",
    "codes",
    "names",
    "matrix",
    "p_values",
    "pairs",
    "insufficient_codes",
    "note",
}


def _dates(n: int, start: str = "2026-01-05") -> list[str]:
    """生成 n 个连续 ISO 日期（升序）。"""
    from datetime import date, timedelta

    d = date.fromisoformat(start)
    out: list[str] = []
    for _ in range(n):
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _returns(series: list[float], n: int | None = None) -> list[dict]:
    """将数值序列包装为 [{"date", "return"}]（升序）。"""
    dates = _dates(len(series) if n is None else n)
    if n is not None and len(series) < n:
        # 头部补零对齐长度（等价于无交易日期收益 0）
        series = [0.0] * (n - len(series)) + list(series)
    return [{"date": dates[i], "return": float(series[i])} for i in range(len(series))]


def _sin(n: int, freq: float = 5.0) -> list[float]:
    return [math.sin(i / freq) for i in range(n)]


class TestKnownAnswerCorrelation:
    """完全正/负相关已知答案验证。"""

    def test_identical_sequences_corr_is_one(self):
        """完全相同序列 → r=1.0，p=0，显著。"""
        x = _sin(80)
        res = compute_correlation_matrix(
            {"a": _returns(x), "b": _returns(x)},
            {"a": "A", "b": "B"},
        )
        assert res["available"] is True
        # 下三角：matrix[1][0] = r(a, b)
        assert abs(res["matrix"][1][0] - 1.0) < 1e-9
        pair = res["pairs"][0]
        assert pair["code_a"] == "b" and pair["code_b"] == "a"
        assert abs(pair["pearson"] - 1.0) < 1e-9
        assert pair["significant"] is True

    def test_negated_sequences_corr_is_minus_one(self):
        """完全相反序列 → r=-1.0，p=0，显著。"""
        x = _sin(80)
        y = [-v for v in x]
        res = compute_correlation_matrix(
            {"a": _returns(x), "b": _returns(y)},
            {"a": "A", "b": "B"},
        )
        assert res["available"] is True
        assert abs(res["matrix"][1][0] + 1.0) < 1e-9
        pair = res["pairs"][0]
        assert abs(pair["pearson"] + 1.0) < 1e-9
        assert pair["significant"] is True

    def test_scale_and_shift_do_not_change_r(self):
        """y = a + b*x 线性变换不改变相关系数。"""
        x = _sin(80)
        y = [3.0 + 2.0 * v for v in x]
        res = compute_correlation_matrix({"a": _returns(x), "b": _returns(y)})
        assert abs(res["matrix"][1][0] - 1.0) < 1e-9

    def test_pearson_pvalue_constant_series(self):
        """常数序列 → (0.0, 1.0) 不显著，绝不硬算。"""
        const = [0.01] * 60
        noise = _sin(60)
        r, p = _pearson_pvalue(const, noise)
        # 容差断言：CPython sum 实现差异（3.12+ 误差补偿求和 vs 3.11 朴素累加）
        # 使常数序列标准差可能是 ~1e-17 的极小非零值而非精确 0.0，
        # 断言应验证"行为"（不硬算）而非精确等于 0.0
        assert abs(r) < 1e-12 and p == 1.0

    def test_pearson_pvalue_near_constant_series(self):
        """近常数序列（波动 ~1e-14）→ 仍判常数返回 (0.0, 1.0)，不因浮点误差硬算。"""
        const = [0.01] * 60
        # 叠加 1e-14 量级抖动，模拟均值舍入误差导致的极小非零标准差
        const = [v + 1e-14 * (i % 3) for i, v in enumerate(const)]
        noise = _sin(60)
        r, p = _pearson_pvalue(const, noise)
        assert abs(r) < 1e-12 and p == 1.0


class TestInsignificantPair:
    """不显著配对（p≥0.05 → 白色格）。"""

    def test_sin_cos_pair_insignificant(self):
        """sin vs cos（正交近零相关）→ p≥0.05，significant=False。"""
        x = _sin(80, 7.0)
        y = [math.cos(i / 7.0) for i in range(80)]
        res = compute_correlation_matrix(
            {"a": _returns(x), "b": _returns(y)},
            {"a": "A", "b": "B"},
        )
        assert res["available"] is True
        r_val = res["matrix"][1][0]
        p_val = res["p_values"][1][0]
        assert p_val >= SIGNIFICANCE_LEVEL
        assert abs(r_val) < 0.5
        assert res["pairs"][0]["significant"] is False


class TestMatrixLayout:
    """下三角矩阵布局。"""

    def _three_code_result(self):
        x = _sin(80)
        y = [math.cos(i / 7.0) for i in range(80)]
        z = [-v for v in x]
        return compute_correlation_matrix(
            {"a": x and _returns(x), "b": _returns(y), "c": _returns(z)},
            {"a": "A", "b": "B", "c": "C"},
        )

    def test_lower_triangular_layout(self):
        """row>col 有值、对角=1.0、上三角 None。"""
        res = self._three_code_result()
        matrix = res["matrix"]
        n = len(res["codes"])
        for i in range(n):
            assert matrix[i][i] == 1.0  # 对角
            for j in range(i + 1, n):
                assert matrix[i][j] is None  # 上三角留空
        # 下三角非 None
        for i in range(n):
            for j in range(i):
                assert matrix[i][j] is not None

    def test_pairs_sorted_by_abs_r_desc(self):
        """配对明细按 |r| 降序。"""
        res = self._three_code_result()
        rs = [abs(p["pearson"]) for p in res["pairs"]]
        assert rs == sorted(rs, reverse=True)

    def test_each_pair_has_required_fields(self):
        """每条配对含 code_a/name_a/code_b/name_b/pearson/p_value/significant/samples。"""
        res = self._three_code_result()
        for p in res["pairs"]:
            for field in ("code_a", "name_a", "code_b", "name_b", "pearson", "p_value", "significant", "samples"):
                assert field in p, f"配对缺少字段 {field}: {p}"


class TestInsufficientData:
    """数据不足（§1.4.5 降级治理）。"""

    def test_overlap_below_min_samples(self):
        """重叠样本 < MIN_SAMPLES → available=False，status="insufficient"。"""
        # a 只有 30 期、b 有 80 期，但日期完全错开（无重叠）
        dates_a = _dates(30, "2026-01-05")
        dates_b = _dates(80, "2026-03-05")
        a = [{"date": d, "return": 0.01} for d in dates_a]
        b = [{"date": d, "return": 0.02} for d in dates_b]
        res = compute_correlation_matrix({"a": a, "b": b})
        assert res["available"] is False
        assert res["status"] == "insufficient"
        assert res["pairs"] == []
        assert "a" in res["insufficient_codes"] and "b" in res["insufficient_codes"]

    def test_single_holding(self):
        """单品种（<MIN_HOLDINGS）→ 数据不足。"""
        x = _sin(80)
        res = compute_correlation_matrix({"a": _returns(x)})
        assert res["available"] is False
        assert res["status"] == "insufficient"

    def test_no_valid_returns(self):
        """全部品种无有效收益 → 数据不足。"""
        res = compute_correlation_matrix({"a": [], "b": []})
        assert res["available"] is False
        assert res["status"] == "insufficient"


class TestNameFallback:
    """名称回退。"""

    def test_missing_names_fall_back_to_code(self):
        """names_by_code 缺失 → 回退 code 本身。"""
        x = _sin(80)
        y = [-v for v in x]
        res = compute_correlation_matrix({"AAA": _returns(x), "BBB": _returns(y)})
        assert res["names"]["AAA"] == "AAA"
        pair = res["pairs"][0]
        assert pair["name_a"] == "BBB" and pair["name_b"] == "AAA"


class TestC19Contract:
    """C19 契约键完整性。"""

    def test_result_has_all_c19_keys(self):
        x = _sin(80)
        y = [-v for v in x]
        res = compute_correlation_matrix({"a": _returns(x), "b": _returns(y)})
        assert set(res.keys()) >= _C19_KEYS

    def test_unavailable_result_has_all_c19_keys(self):
        res = unavailable_result("insufficient", sample_count=10, insufficient_codes=["a"])
        assert set(res.keys()) >= _C19_KEYS
        assert res["available"] is False
        assert res["status"] == "insufficient"
        assert res["sample_count"] == 10
        assert res["insufficient_codes"] == ["a"]

    def test_window_and_sample_count(self):
        """window 不超过实际重叠样本数。"""
        x = _sin(80)
        y = [math.cos(i / 7.0) for i in range(80)]
        res = compute_correlation_matrix({"a": _returns(x), "b": _returns(y)})
        assert res["sample_count"] >= MIN_SAMPLES
        assert res["window"] <= DEFAULT_WINDOW
