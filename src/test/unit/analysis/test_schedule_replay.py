"""调仓纪律回放（schedule_replay）纯计算 + 回放规则契约（replay_schedule）测试。

覆盖：
  - 契约：默认解析 / 枚举与阈值边界 / 未知键 / 权重校验 / 版本不符 / 指纹；
  - 定期回放手算：2 期回放（跨月触发）+ 100 基点归一同源 + 逐期换手/成本行；
  - 阈值回放手算：显式目标权重下漂移触发（含边界 >= 判定）；
  - 成本两态：费率表缺席 → cost_note="未计成本"；费率全知 → 逐笔计入且成本行落账；
  - 长窗口指标：与买入持有同源对比（无触发时逐项相等、diff 结构关系）。

数值断言使用精确值或 pytest.approx（浮点）。
"""

from __future__ import annotations

import pytest

from src.python.analysis.schedule_replay import (
    COST_NOTE_ABSENT,
    run_schedule_replay,
)
from src.python.schemas.replay_schedule import (
    SCHEDULE_VERSION,
    parse_replay_schedule,
    schedule_fingerprint,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

#: 手算夹具为短窗口：绕过默认 12 个月跨度/净值日验收下限（默认值行为由 edge 文件守）
FAST = {"min_span_days": 0, "min_points": 1}


def _holdings() -> list[dict]:
    return [
        {"code": "A", "name": "甲基金", "shares": 100.0, "cost": 1.0},
        {"code": "B", "name": "乙基金", "shares": 100.0, "cost": 1.0},
    ]


def _navs_m() -> dict[str, dict[str, float]]:
    """夹具 M（定期回放手算）：A 持平后涨、B 第二天翻倍。"""
    return {
        "A": {"2025-01-02": 10.0, "2025-02-03": 10.0, "2025-02-04": 12.0},
        "B": {"2025-01-02": 10.0, "2025-02-03": 20.0, "2025-02-04": 20.0},
    }


def _navs_t() -> dict[str, dict[str, float]]:
    """夹具 T（阈值回放手算）：A 先翻倍再腰斩，B 恒定。"""
    return {
        "A": {"2025-01-02": 10.0, "2025-02-03": 20.0, "2025-02-04": 10.0},
        "B": {"2025-01-02": 10.0, "2025-02-03": 10.0, "2025-02-04": 10.0},
    }


def _long_series() -> dict[str, dict[str, float]]:
    """45 个工作日、带波动的长窗口（≥20 个日收益 → 指标非 None）。"""
    from datetime import date, timedelta

    dates: list[str] = []
    cur = date(2025, 3, 3)
    while len(dates) < 45:
        if cur.weekday() < 5:
            dates.append(cur.isoformat())
        cur += timedelta(days=1)
    a_map: dict[str, float] = {}
    for i, d in enumerate(dates):
        # 有界交替波动（±2%）+ 缓慢趋势：权重漂移远小于 20pp，波动足够算夏普
        base = 10.0 * (1.0 + 0.0005 * i)
        wiggle = 1.02 if i % 2 else 0.98
        a_map[d] = round(base * wiggle, 6)
    return {"A": a_map, "B": {d: 10.0 for d in dates}}


class TestParseReplaySchedule:
    """契约解析：默认值 / 校验 / 指纹。"""

    def test_defaults(self):
        s = parse_replay_schedule(None)
        assert s.rule_type == "cadence"
        assert s.cadence == "monthly"
        assert s.threshold_pp is None
        assert s.threshold is None
        assert s.target_weights is None
        assert s.version == SCHEDULE_VERSION

    def test_threshold_defaults_and_property(self):
        s = parse_replay_schedule({"rule_type": "threshold"})
        assert s.threshold_pp == 5.0
        assert s.threshold == pytest.approx(0.05)

    def test_quarterly_and_explicit_target(self):
        s = parse_replay_schedule(
            {"rule_type": "cadence", "cadence": "quarterly", "target_weights": {"A": 0.6, "B": 0.4}}
        )
        assert s.cadence == "quarterly"
        assert s.target_weights == {"A": 0.6, "B": 0.4}

    @pytest.mark.parametrize("bad", [{"rule_type": "weekly"}, {"cadence": "yearly"}, {"version": 99}])
    def test_enum_and_version_rejected(self, bad):
        with pytest.raises(ValueError, match="回放规则非法"):
            parse_replay_schedule(bad)

    @pytest.mark.parametrize("pp", [0, -1, 51, float("nan"), "5"])
    def test_threshold_pp_out_of_range_rejected(self, pp):
        with pytest.raises(ValueError, match="threshold_pp"):
            parse_replay_schedule({"rule_type": "threshold", "threshold_pp": pp})

    def test_threshold_pp_on_cadence_rejected(self):
        with pytest.raises(ValueError, match="仅适用"):
            parse_replay_schedule({"rule_type": "cadence", "threshold_pp": 5})

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="未知键"):
            parse_replay_schedule({"rule_typo": "cadence"})

    @pytest.mark.parametrize(
        "weights",
        [{"A": 0.6, "B": 0.7}, {"A": -0.1, "B": 1.1}, {}, {"": 1.0}, {"A": "x"}],
    )
    def test_target_weights_invalid_rejected(self, weights):
        with pytest.raises(ValueError, match="target_weights"):
            parse_replay_schedule({"target_weights": weights})

    def test_non_mapping_raw_rejected(self):
        with pytest.raises(ValueError, match="规则须为映射"):
            parse_replay_schedule(["cadence"])  # type: ignore[arg-type]

    def test_fingerprint_stable_and_sensitive(self):
        base = parse_replay_schedule(None)
        same = parse_replay_schedule({})
        other = parse_replay_schedule({"cadence": "quarterly"})
        assert schedule_fingerprint(base) == schedule_fingerprint(same)
        assert schedule_fingerprint(base) != schedule_fingerprint(other)


class TestCadenceReplay:
    """定期回放（夹具 M）：2 期跨月触发手算。"""

    def test_two_period_hand_computed(self):
        result = run_schedule_replay(_holdings(), _navs_m(), None, **FAST)
        assert result["available"] is True
        # 买入持有：2000 → 3000 → 3200（归一 100 基点）
        assert result["series"]["buyhold"] == [100.0, 150.0, 160.0]
        # 月度定期在 2025-02-03（跨月首日）回归末日目标权重 {A:.375, B:.625}：
        # 3000 × .375 / 10 = 112.5 份、3000 × .625 / 20 = 93.75 份 →
        # 02-04：112.5×12 + 93.75×20 = 3225（零费率 → 无成本损耗）→ 3225/2000 × 100
        assert result["series"]["replay"] == [100.0, 150.0, 161.25]
        assert result["window"]["points"] == 3

    def test_trigger_and_period_row(self):
        result = run_schedule_replay(_holdings(), _navs_m(), None, **FAST)
        assert result["trigger"]["rule_type"] == "cadence"
        assert result["trigger"]["cadence"] == "monthly"
        assert result["trigger"]["fired"] == ["2025-02-03"]
        assert result["trigger"]["count"] == 1
        (row,) = result["periods"]
        assert row["date"] == "2025-02-03"
        assert row["trades"] == 2
        assert row["turnover"] == pytest.approx(0.041667, abs=1e-6)
        assert row["cost"] == 0.0
        assert row["cost_known"] is False

    def test_cost_note_when_fee_absent(self):
        result = run_schedule_replay(_holdings(), _navs_m(), None, **FAST)
        assert result["cost_note"] == COST_NOTE_ABSENT
        assert any("期初批次建仓日" in n for n in result["notes"])

    def test_fee_known_cost_booked(self):
        fee_index = {
            "A": {"purchase": {"tiers": [{"min_amount": None, "max_amount": None, "rate": 0.01}]}},
            "B": {"redemption": {"tiers": [{"min_days": None, "max_days": None, "rate": 0.005}]}},
        }
        result = run_schedule_replay(
            _holdings(),
            _navs_m(),
            None,
            fee_index=fee_index,
            cost_counter=lambda start, end: 10,
            **FAST,
        )
        # 买入 12.5 份 × 10 = 125 元 × 1% = 1.25；卖出成本减量 6.25 元 × 0.5% = 0.03
        assert result["periods"][0]["cost"] == pytest.approx(1.28)
        assert result["periods"][0]["cost_known"] is True
        assert result["cost_note"] == ""
        # 价值轨迹含成本：2000 → 3000-1.28 → 3225-1.28
        assert result["series"]["replay"] == [100.0, 149.936, 161.186]
        assert any("交易成本 = 基金申赎费估算" in n for n in result["notes"])


class TestThresholdReplay:
    """阈值回放（夹具 T + 显式目标权重 {A:.5, B:.5}）。"""

    @staticmethod
    def _schedule(pp: float) -> dict:
        return {
            "rule_type": "threshold",
            "threshold_pp": pp,
            "target_weights": {"A": 0.5, "B": 0.5},
        }

    def test_drift_fires_and_rescues_value(self):
        result = run_schedule_replay(_holdings(), _navs_t(), self._schedule(5), **FAST)
        assert result["available"] is True
        # 触发：01-02 漂移 0（起点即目标）→ 02-03 漂移 16.7pp 触发 →
        # 调仓后 75A+150B，02-04 腰斩后漂移 16.7pp 再触发 → 112.5A+112.5B
        assert result["trigger"]["fired"] == ["2025-02-03", "2025-02-04"]
        assert result["trigger"]["count"] == 2
        # 买入持有 2000 → 3000 → 2000（首值锚 2000）= [100, 150, 100]；
        # 纪律回放 2000 → 3000 → 2250（75A+150B → 112.5A+112.5B）= [100, 150, 112.5]
        # （区间内回归目标缓冲了腰斩：回放高于持有 +12.5 基点）
        assert result["series"]["buyhold"] == [100.0, 150.0, 100.0]
        assert result["series"]["replay"] == [100.0, 150.0, 112.5]
        assert all(row["turnover"] == pytest.approx(0.166667, abs=1e-6) for row in result["periods"])
        assert all(row["trades"] == 2 for row in result["periods"])

    def test_long_window_metrics_consistency(self):
        result = run_schedule_replay(_holdings(), _long_series(), self._schedule(20), **FAST)
        assert result["available"] is True
        assert result["trigger"]["count"] == 0
        metrics = result["metrics"]
        # 指标原语同源：20pp 不触发 → 回放与买入持有逐项相等
        assert metrics["replay"] == metrics["buyhold"]
        assert metrics["replay"]["sharpe"] is not None
        assert metrics["replay"]["annualized"] is not None
        assert metrics["replay"]["max_drawdown"] is not None
        # diff 结构关系：逐项 = replay − buyhold（此处为零差）
        for key, value in metrics["diff"].items():
            assert value == pytest.approx(metrics["replay"][key] - metrics["buyhold"][key], abs=1e-12)
