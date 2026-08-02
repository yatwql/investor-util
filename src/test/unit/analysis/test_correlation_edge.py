"""持仓相关性矩阵边缘场景测试 — 异常/极端值。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - NaN/Inf/None 收益值过滤（NaN 曾产生虚假 r=1.0、p=0.0 显著相关，回归防护）
  - _is_valid_return 判定边界
  - 恰好达到/低于 MIN_SAMPLES 边界
  - 重复日期去重对齐
  - 日期缺口对齐（缺失中间日期）
  - 常数序列（零方差不硬算）
  - 多品种大矩阵 sanity
  - 极大幅值相关系数钳位
"""

from __future__ import annotations

import math

import pytest

from src.python.analysis.correlation import (
    DEFAULT_WINDOW,
    MIN_HOLDINGS,
    MIN_SAMPLES,
    _is_valid_return,
    _pearson_pvalue,
    compute_correlation_matrix,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


def _dates(n: int, start: str = "2026-01-05") -> list[str]:
    """生成 n 个连续 ISO 日期（升序）。"""
    from datetime import date, timedelta

    d = date.fromisoformat(start)
    out: list[str] = []
    for _ in range(n):
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _seq(values: list[float], dates: list[str]) -> list[dict]:
    """将数值序列包装为 [{"date", "return"}]（与 dates 等长）。"""
    return [{"date": dates[i], "return": float(values[i])} for i in range(len(values))]


class TestIsValidReturn:
    """_is_valid_return 判定边界。"""

    def test_none_rejected(self):
        assert _is_valid_return(None) is False

    def test_nan_rejected(self):
        assert _is_valid_return(float("nan")) is False

    def test_inf_rejected(self):
        assert _is_valid_return(float("inf")) is False
        assert _is_valid_return(float("-inf")) is False

    def test_valid_numeric_accepted(self):
        assert _is_valid_return(0.0) is True
        assert _is_valid_return(0.05) is True
        assert _is_valid_return(0) is True

    def test_non_numeric_rejected(self):
        assert _is_valid_return("abc") is False


class TestNaNReturnRegression:
    """回归防护：NaN 收益不得产生虚假完美相关。"""

    def test_single_nan_filtered_no_spurious_one(self):
        """非恒定序列含 1 个 NaN → 过滤后 r 贴近干净数据，绝不虚假为 1.0。"""
        import random

        random.seed(7)
        n = 80
        dates = _dates(n)
        base = [math.sin(i / 6.0) for i in range(n)]
        # 独立噪声使干净相关明显小于 1.0
        y_clean = [v + random.uniform(-0.3, 0.3) for v in base]
        clean = compute_correlation_matrix({"a": _seq(base, dates), "b": _seq(y_clean, dates)})
        r_clean = clean["matrix"][1][0]
        assert r_clean < 0.999, "测试数据相关过高，无法区分虚假相关"

        y_nan = list(y_clean)
        y_nan[30] = float("nan")
        res = compute_correlation_matrix({"a": _seq(base, dates), "b": _seq(y_nan, dates)})
        r_nan = res["matrix"][1][0]
        p_nan = res["p_values"][1][0]
        assert not math.isnan(r_nan) and not math.isnan(p_nan)
        assert r_nan < 1.0, "NaN 仍致虚假 r=1.0"
        # 与干净数据相关性偏差小（仅剔除一个离群点）
        assert abs(r_clean - r_nan) < 0.05, f"NaN 过滤后偏差过大: {r_clean} vs {r_nan}"

    def test_all_nan_series_dropped(self):
        """全 NaN 序列 → 整条剔除；跌破 MIN_HOLDINGS → 数据不足降级。"""
        dates = _dates(80)
        res = compute_correlation_matrix({"a": _seq([0.01] * 80, dates), "b": _seq([float("nan")] * 80, dates)})
        assert res["available"] is False
        assert res["status"] == "insufficient"
        # 全 NaN 的 b 被剔除，剩余仅 a 不足 2 品种；unavailable_result 契约 codes=[]
        assert res["codes"] == []
        assert res["insufficient_codes"] == ["a"]

    def test_nan_in_constant_series_still_guarded(self):
        """NaN 混入常数序列（会触发 sx==0 早退的另一分支）→ 过滤后安全返回。"""
        n = 70
        dates = _dates(n)
        x = [0.01] * n
        y = [0.02] * n
        y[10] = float("nan")
        res = compute_correlation_matrix({"a": _seq(x, dates), "b": _seq(y, dates)})
        r = res["matrix"][1][0]
        assert r == 0.0
        assert res["p_values"][1][0] == 1.0


class TestSampleBoundary:
    """重叠样本边界（MIN_SAMPLES=60）。"""

    def test_exactly_min_samples_available(self):
        """恰好 60 个重叠样本 → 计算（不判数据不足）。"""
        n = 60
        dates = _dates(n)
        x = [math.sin(i / 5.0) for i in range(n)]
        y = [math.cos(i / 5.0) for i in range(n)]
        res = compute_correlation_matrix({"a": _seq(x, dates), "b": _seq(y, dates)})
        assert res["available"] is True
        assert res["sample_count"] >= MIN_SAMPLES

    def test_below_min_samples_insufficient(self):
        """重叠样本 59 < MIN_SAMPLES → available=False + insufficient_codes。"""
        # a 60 期、b 60 期但头部错开 2 天 → 重叠 58 < 60
        dates_a = _dates(60, "2026-01-05")
        dates_b = _dates(60, "2026-01-07")
        x = [0.01] * 60
        y = [0.02] * 60
        res = compute_correlation_matrix({"a": _seq(x, dates_a), "b": _seq(y, dates_b)})
        assert res["available"] is False
        assert res["status"] == "insufficient"
        assert res["matrix"] == []  # unavailable_result 工厂空矩阵
        assert set(res["insufficient_codes"]) == {"a", "b"}


class TestDateHandling:
    """日期对齐边界。"""

    def test_duplicate_dates_deduped(self):
        """序列含重复日期 → 对齐按日期去重，不崩溃、可计算。"""
        n = 70
        dates = _dates(n)
        x = [0.01 * i for i in range(1, n + 1)]
        y = [-v for v in x]
        # b 中间插入一天重复日期
        b_dates = dates[:35] + [dates[35]] + dates[35:]
        b_vals = [v for i, v in enumerate(y) for _ in (range(2) if i == 35 else range(1))]
        b = [{"date": b_dates[i], "return": b_vals[i]} for i in range(len(b_dates))]
        res = compute_correlation_matrix({"a": _seq(x, dates), "b": b})
        assert res["available"] is True
        assert abs(res["matrix"][1][0] + 1.0) < 1e-6  # 反相关仍成立

    def test_missing_middle_dates_aligned(self):
        """日期缺口（缺失中间若干天）→ 仅用交集对齐，不崩溃。"""
        n = 80
        dates_a = _dates(n)
        dates_b = dates_a[:30] + dates_a[33:]  # 同一天列表去掉中间 3 天
        x = [math.sin(i / 6.0) for i in range(n)]
        y = [math.cos(i / 6.0) for i in range(n)]
        y_short = y[:30] + y[33:]  # 与 dates_b 按位置对齐
        res = compute_correlation_matrix({"a": _seq(x, dates_a), "b": _seq(y_short, dates_b)})
        assert res["available"] is True
        assert res["sample_count"] >= MIN_SAMPLES


class TestExtremeValues:
    """极大幅值/常数序列。"""

    def test_huge_magnitudes_clamped(self):
        """极大/极小数值 → 相关系数钳位 [-1, 1]，不产生 NaN。"""
        n = 70
        dates = _dates(n)
        big = [1e9 * (i + 1) for i in range(n)]
        small = [-(i + 1) / 1e9 for i in range(n)]
        res = compute_correlation_matrix({"a": _seq(big, dates), "b": _seq(small, dates)})
        r = res["matrix"][1][0]
        assert not math.isnan(r)
        assert -1.0 <= r <= 1.0
        # 单调反向 → 强负相关
        assert r <= -0.9

    def test_one_constant_one_varying(self):
        """一序列常数、另一变化 → (0, 1.0) 不显著，绝不硬算。"""
        n = 70
        dates = _dates(n)
        x = [0.01] * n
        y = [0.02 * i for i in range(1, n + 1)]
        r, p = _pearson_pvalue(x, y)
        assert r == 0.0 and p == 1.0


class TestLargeMatrix:
    """多品种矩阵 sanity。"""

    def test_ten_holdings_matrix_dimensions(self):
        """10 品种 → 10×10 下三角、对角 1.0、全部配对计算。"""
        n = 70
        dates = _dates(n)
        series: dict[str, list[dict]] = {}
        for k in range(10):
            code = f"c{k}"
            series[code] = _seq([math.sin(i / 6.0 + k) + 0.01 * k for i in range(n)], dates)
        res = compute_correlation_matrix(series)
        assert res["available"] is True
        matrix = res["matrix"]
        assert len(matrix) == 10 and all(len(row) == 10 for row in matrix)
        for i in range(10):
            assert matrix[i][i] == 1.0
            for j in range(i + 1, 10):
                assert matrix[i][j] is None  # 上三角留空
        # 下三角全部有值
        for i in range(10):
            for j in range(i):
                assert matrix[i][j] is not None
        # 配对按 |r| 降序且数量 = C(10,2)=45
        assert len(res["pairs"]) == 45
        rs = [abs(p["pearson"]) for p in res["pairs"]]
        assert rs == sorted(rs, reverse=True)
        assert res["window"] <= DEFAULT_WINDOW
