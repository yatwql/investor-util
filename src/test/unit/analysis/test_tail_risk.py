"""尾部风险统计模块测试 — VaR / 最大单日跌幅 / 连续下跌 / 恢复天数。

测试策略：
  - 固定 fixture（21 个日收益）校验计算精度（期望值与手算一致，偏差 <0.01%）
  - compute_tail_risk() 覆盖 VaR(95/99)、最大单日跌幅、连续下跌、恢复天数
  - 样本不足 / 空输入 → available=False 占位
  - 无下跌日序列 → var=0、连续下跌 0 天、恢复状态 none

边缘/异常场景见 test_tail_risk_edge.py。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

from src.python.analysis.tail_risk import compute_tail_risk


def _bars_from_returns(returns: list[float], start: str = "2026-01-01", base: float = 100.0) -> list[dict]:
    """从日收益率序列（小数）生成 bars（v[i] = v[i-1] * (1 + r[i-1])）。"""
    out: list[dict] = []
    d = date.fromisoformat(start)
    value = float(base)
    out.append({"date": d.isoformat(), "total_value": value})
    d += timedelta(days=1)
    for r in returns:
        value *= 1.0 + r
        out.append({"date": d.isoformat(), "total_value": value})
        d += timedelta(days=1)
    return out


# 21 个日收益的固定 fixture。
# 手算期望值：
#   - VaR95：q=0.05, k=ceil(0.05*21)-1=1 → 第二差收益 -0.04 → 4.0%
#   - VaR99：q=0.01, k=ceil(0.21)-1=0 → 最差收益 -0.05 → 5.0%
#   - 最大单日跌幅：-0.05（索引 8）→ 5.0%，对应 bars[9]
#   - 最长连续下跌：索引 1~3（-0.01/-0.02/-0.03）→ 3 天，区间 bars[2]~bars[4]
#   - 最大跌幅后恢复：bars[9] 前值 = bars[8]，bars[10] 已回到该水平 → 1 天
FIXED_RETURNS: list[float] = [
    0.02,
    -0.01,
    -0.02,
    -0.03,
    0.05,
    -0.04,
    0.03,
    0.01,
    -0.05,
    0.06,
    0.02,
    0.04,
    0.01,
    -0.03,
    -0.02,
    0.02,
    0.03,
    -0.01,
    0.04,
    0.01,
    0.02,
]


class TestVarMetrics:
    """VaR(95/99) 计算测试。"""

    def test_var95_var99_fixed_fixture(self):
        """固定 fixture → VaR95=4.0%、VaR99=5.0%（手算值，偏差 <0.01%）。"""
        result = compute_tail_risk(_bars_from_returns(FIXED_RETURNS))
        assert result["available"] is True
        assert result["var95"] == pytest.approx(4.0, abs=0.01)
        assert result["var99"] == pytest.approx(5.0, abs=0.01)

    def test_var_confidence_ordering(self):
        """多组 fixture：VaR99 >= VaR95，且置信度越低损失幅度越小。"""
        fixtures = [
            FIXED_RETURNS,
            [
                0.03,
                -0.02,
                0.01,
                -0.04,
                0.02,
                -0.06,
                0.04,
                -0.01,
                0.03,
                -0.02,
                0.05,
                0.01,
                -0.03,
                0.02,
                0.01,
                -0.05,
                0.04,
                0.02,
                -0.01,
                0.03,
                0.01,
            ],
            [0.01] * 21,
        ]
        for returns in fixtures:
            result = compute_tail_risk(_bars_from_returns(returns))
            assert result["var99"] >= result["var95"]
            assert result["var95"] >= 0.0
            assert result["var99"] >= 0.0

    def test_var_zero_when_no_loss_days(self):
        """全部为正收益 → VaR 为 0（该分位无损失）。"""
        result = compute_tail_risk(_bars_from_returns([0.02] * 21))
        assert result["available"] is True
        assert result["var95"] == 0.0
        assert result["var99"] == 0.0


class TestMaxSingleDayDrop:
    """最大单日跌幅测试。"""

    def test_max_single_day_drop_value(self):
        """最大单日跌幅 = 5.0%，日期对应 bars[9]。"""
        bars = _bars_from_returns(FIXED_RETURNS)
        result = compute_tail_risk(bars)
        assert result["max_single_day_drop"] == pytest.approx(5.0, abs=0.01)
        assert result["max_single_day_drop_date"] == bars[9]["date"]

    def test_max_single_day_drop_takes_first_deepest(self):
        """出现两次相同最深跌幅 → 取第一个（索引较小）。"""
        returns = [
            0.01,
            -0.05,
            0.03,
            -0.05,
            0.02,
            -0.01,
            0.04,
            0.01,
            -0.03,
            0.02,
            0.05,
            0.01,
            -0.02,
            0.03,
            0.01,
            0.02,
            -0.01,
            0.04,
            0.01,
            0.03,
            0.02,
        ]  # 21 个
        bars = _bars_from_returns(returns)
        result = compute_tail_risk(bars)
        assert result["max_single_day_drop"] == pytest.approx(5.0, abs=0.01)
        assert result["max_single_day_drop_date"] == bars[2]["date"]


class TestConsecutiveDown:
    """最长连续下跌天数测试。"""

    def test_consecutive_down_days_fixed_fixture(self):
        """固定 fixture → 连续下跌 3 天，区间 bars[2]~bars[4]。"""
        bars = _bars_from_returns(FIXED_RETURNS)
        result = compute_tail_risk(bars)
        assert result["consecutive_down_days"] == 3
        assert result["consecutive_down_start"] == bars[2]["date"]
        assert result["consecutive_down_end"] == bars[4]["date"]

    def test_consecutive_down_later_longer_run_wins(self):
        """更长连续下跌区间后来出现 → 取更长者。"""
        returns = [
            0.01,
            -0.01,
            -0.02,
            0.03,
            0.01,
            -0.01,
            -0.02,
            -0.03,
            -0.01,
            0.02,
            0.04,
            0.01,
            -0.02,
            0.03,
            0.01,
            0.02,
            -0.01,
            0.04,
            0.01,
            0.03,
            0.02,
        ]  # 21 个；最长连续下跌 = 4（索引 5~8）
        bars = _bars_from_returns(returns)
        result = compute_tail_risk(bars)
        assert result["consecutive_down_days"] == 4
        assert result["consecutive_down_start"] == bars[6]["date"]
        assert result["consecutive_down_end"] == bars[9]["date"]

    def test_no_down_days_consecutive_zero(self):
        """全部正收益 → 连续下跌 0 天、区间 None。"""
        result = compute_tail_risk(_bars_from_returns([0.02] * 21))
        assert result["consecutive_down_days"] == 0
        assert result["consecutive_down_start"] is None
        assert result["consecutive_down_end"] is None


class TestRecoveryAfterDrop:
    """最大单日跌幅后恢复天数测试。"""

    def test_recovery_after_drop_recovered(self):
        """固定 fixture → 跌幅次日即回到前日水平，恢复 1 天。"""
        result = compute_tail_risk(_bars_from_returns(FIXED_RETURNS))
        assert result["recovery_days_after_drop"] == 1
        assert result["recovery_state"] == "recovered"

    def test_recovery_after_drop_unrecovered(self):
        """跌幅后数据期内未回到前日水平 → 恢复天数 None、状态 unrecovered。"""
        returns = [0.01] * 18 + [-0.05, 0.005]  # 20 个，跌幅在倒数第二，涨幅不足回补
        result = compute_tail_risk(_bars_from_returns(returns))
        assert result["recovery_days_after_drop"] is None
        assert result["recovery_state"] == "unrecovered"

    def test_no_loss_day_recovery_none(self):
        """无下跌日 → 恢复状态 none、恢复天数 None。"""
        result = compute_tail_risk(_bars_from_returns([0.02] * 21))
        assert result["recovery_state"] == "none"
        assert result["recovery_days_after_drop"] is None


class TestDataSufficiency:
    """样本充足性 / 数据降级测试。"""

    def test_sample_insufficient_unavailable(self):
        """日收益 < 下限 → available=False、各指标 None。"""
        returns = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.04, -0.01, 0.02, -0.02, 0.03, -0.01, 0.02, -0.03]  # 14 个
        result = compute_tail_risk(_bars_from_returns(returns))
        assert result["available"] is False
        assert result["sample_size"] == 14
        assert result["var95"] is None
        assert result["var99"] is None
        assert result["max_single_day_drop"] is None
        assert result["consecutive_down_days"] is None
        assert result["recovery_state"] is None
        assert result["warnings"]

    def test_none_bars_unavailable(self):
        """None 输入 → available=False、sample_size=0。"""
        result = compute_tail_risk(None)
        assert result["available"] is False
        assert result["sample_size"] == 0
        assert result["warnings"]

    def test_empty_bars_unavailable(self):
        """空列表 → available=False。"""
        result = compute_tail_risk([])
        assert result["available"] is False
        assert result["sample_size"] == 0

    def test_contract_field_completeness(self):
        """tail_risk_data 契约字段完整。"""
        result = compute_tail_risk(_bars_from_returns(FIXED_RETURNS))
        for key in (
            "available",
            "sample_size",
            "var95",
            "var99",
            "max_single_day_drop",
            "max_single_day_drop_date",
            "consecutive_down_days",
            "consecutive_down_start",
            "consecutive_down_end",
            "recovery_days_after_drop",
            "recovery_state",
            "warnings",
        ):
            assert key in result, f"契约应包含字段 {key}"
