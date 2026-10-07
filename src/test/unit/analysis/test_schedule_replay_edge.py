"""调仓纪律回放（schedule_replay）edge 场景测试。

覆盖设计 §5 降级契约与边界：
  - 阈值窗口内未触发 → 明示 note 而非空表（回放与买入持有一致）；
  - 窗口跨度不足 / 净值日不足 / 行情缺口越限 → available=False（章隐藏）；
  - 观测区间不相交时锚点 = 后起品种首日（前向 LOCF 同源约定）；
  - 空输入 / 无数据与零份额品种剔除；
  - NaN 净值剔除后 LOCF 续填；单品种组合调仓为零交易行；
  - 漂移恰好等于阈值（>= 边界）触发；费率表空 → 未知腿不冒充 0；
  - end_date 截窗；显式目标权重的忽略/缺失/重归一 note。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.python.analysis.schedule_replay import run_schedule_replay

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]

FAST = {"min_span_days": 0, "min_points": 1}


def _holdings() -> list[dict]:
    return [
        {"code": "A", "name": "甲基金", "shares": 100.0, "cost": 1.0},
        {"code": "B", "name": "乙基金", "shares": 100.0, "cost": 1.0},
    ]


def _navs_t() -> dict[str, dict[str, float]]:
    return {
        "A": {"2025-01-02": 10.0, "2025-02-03": 20.0, "2025-02-04": 10.0},
        "B": {"2025-01-02": 10.0, "2025-02-03": 10.0, "2025-02-04": 10.0},
    }


def _weekday_dates(start: date, end: date) -> list[str]:
    out: list[str] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


class TestDegradation:
    """降级契约：未触发明示 / 三类验收失败 / 锚点缺失。"""

    def test_threshold_never_fires_notes_not_empty_table(self):
        schedule = {
            "rule_type": "threshold",
            "threshold_pp": 20,
            "target_weights": {"A": 0.5, "B": 0.5},
        }
        result = run_schedule_replay(_holdings(), _navs_t(), schedule, **FAST)
        assert result["available"] is True
        assert result["trigger"]["count"] == 0
        assert result["periods"] == []
        assert any("窗口内未触发阈值" in n for n in result["notes"])
        assert result["series"]["replay"] == result["series"]["buyhold"]

    def test_span_below_twelve_months_unavailable(self):
        result = run_schedule_replay(_holdings(), _navs_t(), None)
        assert result["available"] is False
        assert "历史窗口不足 12 个月" in result["reason"]

    def test_points_below_minimum_unavailable(self):
        dates = [date(2025, 1, 6) + timedelta(days=7 * i) for i in range(55)]
        navs = {c: {d.isoformat(): 10.0 + i for i, d in enumerate(dates)} for c in ("A", "B")}
        result = run_schedule_replay(_holdings(), navs, None)
        assert result["available"] is False
        assert "净值日不足" in result["reason"]

    def test_gap_over_limit_unavailable(self):
        dates = _weekday_dates(date(2025, 1, 6), date(2026, 1, 15))
        navs = {
            "A": {d: 10.0 for d in dates},
            "B": {d: 10.0 for d in dates[:55]},  # 覆盖率 ~20% → 整体缺口 ~40%
        }
        result = run_schedule_replay(_holdings(), navs, None)
        assert result["available"] is False
        assert "行情缺口" in result["reason"]

    def test_disjoint_observations_anchor_at_later_start(self):
        # A 观测止于 1 月、B 始于 3 月：前向 LOCF 使 A 值延续到 3 月，
        # 锚点 = 后起品种首日（与 what-if「丢弃锚点前日期」同源约定）；
        # 时序不相交的稀疏性由缺口判定兑底（此处放行以专测锚点语义）
        navs = {
            "A": {"2025-01-02": 10.0, "2025-01-03": 10.0},
            "B": {"2025-03-03": 10.0, "2025-03-04": 10.0},
        }
        result = run_schedule_replay(_holdings(), navs, None, max_gap=0.9, **FAST)
        assert result["available"] is True
        assert result["window"]["start"] == "2025-03-03"

    @pytest.mark.parametrize("holdings,navs", [([], {}), ([{"code": "A", "shares": 1.0}], {})])
    def test_empty_inputs_unavailable(self, holdings, navs):
        result = run_schedule_replay(holdings, navs, None, **FAST)
        assert result["available"] is False
        assert result["reason"]


class TestDataEdge:
    """数据边界：NaN / 单品种 / 剔除 / 截窗 / 目标权重 note。"""

    def test_nan_nav_dropped_then_locf_carries(self):
        navs = {
            "A": {"2025-01-02": 10.0, "2025-02-03": float("nan"), "2025-02-04": 12.0},
            "B": {"2025-01-02": 10.0, "2025-02-03": 20.0, "2025-02-04": 20.0},
        }
        result = run_schedule_replay(_holdings(), navs, None, **FAST)
        assert result["available"] is True
        # NaN 日按 LOCF 沿用 01-02 的 10.0 → 与无 NaN 夹具同轨
        assert result["series"]["replay"] == [100.0, 150.0, 161.25]

    def test_single_code_zero_trade_rows(self):
        holdings = [{"code": "A", "name": "甲基金", "shares": 100.0, "cost": 1.0}]
        navs = {"A": {"2025-01-02": 10.0, "2025-02-03": 10.0, "2025-02-04": 12.0}}
        result = run_schedule_replay(holdings, navs, None, **FAST)
        assert result["available"] is True
        assert result["trigger"]["count"] == 1
        assert result["periods"][0]["trades"] == 0
        assert result["series"]["replay"] == result["series"]["buyhold"]

    def test_zero_share_and_no_data_codes_dropped_with_note(self):
        holdings = _holdings() + [
            {"code": "Z0", "name": "零份额", "shares": 0.0, "cost": 1.0},
            {"code": "Z1", "name": "无数据", "shares": 10.0, "cost": 1.0},
        ]
        result = run_schedule_replay(holdings, _navs_t(), None, **FAST)
        assert result["available"] is True
        note = next(n for n in result["notes"] if "已剔除" in n)
        assert "Z0" in note and "Z1" in note

    def test_end_date_bounds_window(self):
        result = run_schedule_replay(
            _holdings(),
            {
                "A": {"2025-01-02": 10.0, "2025-02-03": 10.0, "2025-02-04": 12.0},
                "B": {"2025-01-02": 10.0, "2025-02-03": 20.0, "2025-02-04": 20.0},
            },
            None,
            end_date="2025-02-03",
            **FAST,
        )
        assert result["available"] is True
        assert result["window"]["end"] == "2025-02-03"
        assert result["window"]["points"] == 2
        # 末日即目标 → 到点检查但零交易
        assert result["periods"][0]["trades"] == 0

    def test_explicit_target_ignore_missing_and_renormalize_notes(self):
        schedule = {
            "rule_type": "cadence",
            "target_weights": {"A": 0.3, "B": 0.3, "X": 0.4},
        }
        result = run_schedule_replay(_holdings(), _navs_t(), schedule, **FAST)
        assert result["available"] is True
        assert any("非持仓代码已忽略" in n and "X" in n for n in result["notes"])
        assert any("重归一" in n for n in result["notes"])


class TestCostEdge:
    """成本两态边界：空费率表 → 未知腿显式计数，不冒充 0。"""

    def test_empty_fee_index_unknown_legs_not_counted_as_zero_fee(self):
        result = run_schedule_replay(
            _holdings(),
            {
                "A": {"2025-01-02": 10.0, "2025-02-03": 10.0, "2025-02-04": 12.0},
                "B": {"2025-01-02": 10.0, "2025-02-03": 20.0, "2025-02-04": 20.0},
            },
            None,
            fee_index={},
            **FAST,
        )
        assert result["available"] is True
        assert result["cost_note"] == ""  # 费率表在场（即便空）≠ 未计成本
        assert result["periods"][0]["cost"] == 0.0
        assert result["periods"][0]["cost_known"] is False
        assert any("费率未知未计入" in n for n in result["notes"])


class TestThresholdBoundary:
    """漂移恰好等于阈值（>= 边界）必须触发。"""

    def test_exact_boundary_drift_fires(self):
        navs = {
            "A": {"2025-01-02": 11.0, "2025-02-03": 11.0},
            "B": {"2025-01-02": 9.0, "2025-02-03": 9.0},
        }
        schedule = {
            "rule_type": "threshold",
            "threshold_pp": 5.0,
            "target_weights": {"A": 0.5, "B": 0.5},
        }
        result = run_schedule_replay(_holdings(), navs, schedule, **FAST)
        assert result["available"] is True
        # 首日 wA = 1100/2000 = 0.55 → 漂移恰为 5pp → >= 边界触发
        assert result["trigger"]["fired"] == ["2025-01-02"]
        assert result["periods"][0]["trades"] == 2
