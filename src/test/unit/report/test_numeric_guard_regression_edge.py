"""数值归一回归的边缘用例 —— 聚合/渲染链路不得被脏值污染。

关注「脏值混入合法值」：单个 NaN 不应让整列合计变成 NaN，也不应改变
合法值之间的相对比较（如成本分档的低/高档位判定）。
"""

from __future__ import annotations

import math

import pytest

from src.python.core.num_utils import finite_or
from src.python.report.category import _tier_label
from src.python.report.chart_data_builder import _build_penetration_bar_dataset

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


@pytest.mark.unit
@pytest.mark.unit_report
@pytest.mark.edge
class TestTierLabelSurvivesDirtyShares:
    """成本分档：脏份额不得污染档位判定。"""

    def test_nan_low_bucket_does_not_flip_tier(self):
        """低档份额为 NaN 时，不得因 NaN 参与比较而误判档位。"""
        buckets = {"low": {"shares": float("nan")}, "high": {"shares": 300.0}, "unpriced": {"shares": 0.0}}
        assert _tier_label(buckets) == "高成本"

    def test_inf_bucket_does_not_flip_tier(self):
        """inf 归零后只剩高档有值 —— 判为高成本，而非让 inf 参与比较。"""
        buckets = {"low": {"shares": float("inf")}, "high": {"shares": 1.0}, "unpriced": {"shares": 0.0}}
        assert _tier_label(buckets) == "高成本"

    def test_all_dirty_buckets_fall_back_to_placeholder(self):
        buckets = {"low": {"shares": float("nan")}, "high": {"shares": float("inf")}, "unpriced": {"shares": float("nan")}}
        assert _tier_label(buckets) == "--"

    def test_legitimate_buckets_unchanged(self):
        """合法输入行为逐字不变（不变量）。"""
        assert _tier_label({"low": {"shares": 100.0}, "high": {"shares": 300.0}}) == "高成本"
        assert _tier_label({"low": {"shares": 300.0}, "high": {"shares": 100.0}}) == "低成本"


@pytest.mark.unit
@pytest.mark.unit_report
@pytest.mark.edge
class TestPenetrationBarSurvivesDirtyValues:
    """穿透 TOP10 柱状图：脏市值不得污染绘图数值。"""

    def _values(self, entries):
        dataset = _build_penetration_bar_dataset({"top10": entries})
        return dataset["datasets"][0]["data"]

    def test_mixed_column_keeps_legitimate_values(self):
        values = self._values([{"name": "A", "mv": 100.0}, {"name": "B", "mv": float("nan")}, {"name": "C", "mv": 200.0}])
        assert all(math.isfinite(v) for v in values)
        assert values == [100.0, 0.0, 200.0]

    def test_all_dirty_column_is_finite(self):
        """全脏列退化为全 0，而非全 NaN（NaN 会破坏 ECharts 渲染）。"""
        values = self._values([{"name": "A", "mv": float("nan")}, {"name": "B", "mv": float("inf")}])
        assert values == [0.0, 0.0]

    def test_negative_values_preserved(self):
        """负市值是合法有限值，不得被兜底吃掉。"""
        values = self._values([{"name": "A", "mv": -250.5}])
        assert values == [-250.5]
        assert finite_or(-250.5) == -250.5
