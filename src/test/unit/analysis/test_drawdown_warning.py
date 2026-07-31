"""回撤历史分位预警模块测试。

测试策略：
  - rolling_max_drawdown() 覆盖空/正常/短窗口
  - current_drawdown_percentile() 覆盖空/正常/预警/严重预警
  - compute_drawdown_warning() 集成验证预警等级
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

from src.python.analysis.drawdown_warning import (
    compute_drawdown_warning,
    current_drawdown_percentile,
    rolling_max_drawdown,
)


# ── rolling_max_drawdown 测试 ─────────────────────────────────


class TestRollingMaxDrawdown:
    """滚动窗口最大回撤计算测试。"""

    def test_empty_series(self):
        """空序列 → 空列表。"""
        assert rolling_max_drawdown([], 252) == []

    def test_single_value(self):
        """单值 → 自身。"""
        assert rolling_max_drawdown([-0.05], 252) == [-0.05]

    def test_window_larger_than_data(self):
        """窗口大于数据长度 → 全部作为最小值。"""
        result = rolling_max_drawdown([-0.01, -0.05, -0.03], 252)
        assert len(result) == 3
        assert result[-1] == -0.05  # 全量最负值

    def test_basic_rolling(self):
        """正常滚动计算。"""
        series = [-0.01, -0.03, -0.02, -0.05, -0.04]
        result = rolling_max_drawdown(series, 3)
        assert len(result) == 5
        # i=0: [-0.01] → min = -0.01
        assert result[0] == -0.01
        # i=1: [-0.01, -0.03] → min = -0.03
        assert result[1] == -0.03
        # i=2: [-0.01, -0.03, -0.02] → min = -0.03
        assert result[2] == -0.03
        # i=3: [-0.03, -0.02, -0.05] → min = -0.05
        assert result[3] == -0.05
        # i=4: [-0.02, -0.05, -0.04] → min = -0.05
        assert result[4] == -0.05

    def test_window_1(self):
        """窗口=1 → 每个值自身为最大值回撤（最负值即自身）。"""
        series = [-0.01, -0.05, -0.02]
        result = rolling_max_drawdown(series, 1)
        assert result == [-0.01, -0.05, -0.02]

    def test_mixed_sign_values(self):
        """混合正负值 → 回撤取最负值。"""
        series = [0.01, -0.02, 0.005, -0.05, -0.01]
        result = rolling_max_drawdown(series, 3)
        # i=2: [0.01, -0.02, 0.005] → min = -0.02
        assert result[2] == -0.02
        # i=3: [-0.02, 0.005, -0.05] → min = -0.05
        assert result[3] == -0.05


# ── current_drawdown_percentile 测试 ──────────────────────────


class TestCurrentDrawdownPercentile:
    """当前回撤在历史中的分位计算测试。"""

    def test_empty_series(self):
        """空序列 → 全 0 + 无预警。"""
        result = current_drawdown_percentile([])
        assert result["current_drawdown"] == 0.0
        assert result["below_warning"] is False
        assert result["below_critical"] is False

    def test_use_last_value_default(self):
        """不传 current_drawdown → 使用序列最后一个值。"""
        series = [-0.01, -0.02, -0.03, -0.04, -0.05]
        result = current_drawdown_percentile(series)
        assert result["current_drawdown"] == -0.05

    def test_custom_current_drawdown(self):
        """传入 current_drawdown。"""
        series = [-0.01, -0.02, -0.03, -0.04, -0.05]
        result = current_drawdown_percentile(series, current_drawdown=-0.02)
        assert result["current_drawdown"] == -0.02

    def test_below_warning(self):
        """当前回撤在 80%+ 分位 → below_warning=True。"""
        # 4/5 的值 <= -0.05 → current_pct = 0.80 → 触发预警
        series = [-0.05] * 4 + [-0.01]
        result = current_drawdown_percentile(series)
        assert result["below_warning"] is True

    def test_below_critical(self):
        """当前回撤在 95%+ 分位 → below_critical=True。"""
        # 19/20 的值 <= -0.05 → current_pct = 0.95 → 触发严重预警
        series = [-0.05] * 19 + [-0.01]
        result = current_drawdown_percentile(series)
        assert result["below_warning"] is True
        assert result["below_critical"] is True

    def test_normal_range(self):
        """当前回撤在正常范围 → 无预警。"""
        # 1/5 的值 <= -0.05 → current_pct = 0.20 < 0.80 → 无预警
        series = [-0.01, -0.02, -0.03, -0.04, -0.05]
        result = current_drawdown_percentile(series)
        assert result["below_warning"] is False
        assert result["below_critical"] is False


# ── compute_drawdown_warning 集成测试 ─────────────────────────


class TestComputeDrawdownWarning:
    """完整回撤预警分析集成测试。"""

    def test_empty_bars(self):
        """空 bars → 默认返回。"""
        result = compute_drawdown_warning([], name="测试组合")
        assert result["name"] == "测试组合"
        assert result["alert_level"] == "normal"

    def test_no_drawdown_series(self):
        """bars 缺 drawdown_pct 键 → 全 0 → 全部百分位 = 1.0 → critical。"""
        bars = [{"date": "2026-01-01"}, {"date": "2026-01-02"}]
        result = compute_drawdown_warning(bars)
        # drawdown_series = [0, 0], current=0, 100% 的值 <= 0 → critical
        assert result["alert_level"] == "critical"

    def test_normal_drawdown_bars(self):
        """正常波动范围 → alert_level=normal。"""
        bars = [
            {"date": f"2026-01-{d:02d}", "drawdown_pct": -0.01 + i * 0.001}
            for i, d in enumerate(range(1, 20))
        ]
        result = compute_drawdown_warning(bars, name="组合A")
        assert result["name"] == "组合A"
        assert "windows" in result
        assert "all_time" in result

    def test_warning_level(self):
        """触发预警 → alert_level=warning。"""
        # 10 bar: [-0.10]*6 + [-0.08, -0.08, -0.01, -0.08]
        # 最后 bar drawdown_pct=-0.08 → current_dd=-0.08, 9/10 的值 ≤ -0.08 → pct=0.90
        # all_time: below_warning=True, below_critical=False
        # windows(252/756): rolling_max=-0.10 → pct=0.60 → 无 window 预警
        # → any_warning=False 但 all_time.below_warning=True → "warning"
        series = [-0.10, -0.10, -0.10, -0.10, -0.10, -0.10, -0.08, -0.08, -0.01, -0.08]
        bars = [{"date": f"2026-01-{d:02d}", "drawdown_pct": v} for d, v in enumerate(series)]
        result = compute_drawdown_warning(bars)
        assert result["alert_level"] == "warning"
