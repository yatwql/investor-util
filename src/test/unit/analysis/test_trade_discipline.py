"""交易纪律规则引擎单元测试（止盈/止损/回撤触发检测）。

覆盖：
  - 止盈触发：收益率 ≥ 止盈线 → 触发 + 距触发幅度 + 建议动作
  - 止损触发：收益率 ≤ 止损线 → 触发 + 距触发幅度 + 建议动作
  - 距触发幅度：超线百分数计算正确
  - 回撤纪律：组合当前市值相对历史峰值回撤 ≥ 回撤线 → 触发
  - 参数边界：恰在线上（distance=0）/ 合规区间内不触发
  - 静默期：静默期内重复信号被抑制、静默期过后恢复
  - 多品种混合触发
  - 数据守卫：空持仓 / 总市值为 0 / 缺 profit_rate 品种

运行：
  python -m pytest src/test/unit/analysis/test_trade_discipline.py -v
"""

from __future__ import annotations

import json
import os

import pytest

from src.python.analysis.trade_discipline import compute_discipline_signals


pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


# ── 辅助构造 ──────────────────────────────────────────────


def _holding(
    name: str,
    code: str,
    profit_rate: float | None,
    market_value: float = 1000.0,
) -> dict:
    """构造 holdings_details 单行（profit_rate 为百分数，如 -16 表示 -16%）。"""
    return {
        "name": name,
        "code": code,
        "market_value": market_value,
        "cost": 1000.0,
        "profit": market_value - 1000.0,
        "profit_rate": profit_rate,
        "change_pct": 0.0,
        "nav_date": "2026-08-04",
        "source_api": "test",
    }


def _holdings(*rates) -> list[dict]:
    """按收益率序列构造持仓（代码 SH60000X 递增）。"""
    return [_holding(f"品种{n}", f"SH60000{n}", r, 1000.0) for n, r in enumerate(rates, 1)]


# ── 止盈 / 止损 ──────────────────────────────────────────


class TestTakeProfit:
    """止盈纪律：收益率 ≥ 止盈线（默认 +20%）触发。"""

    def test_take_profit_triggered(self):
        """收益率 +25% ≥ +20% → 触发，超线 +5%，建议部分止盈。"""
        signals = compute_discipline_signals(_holdings(25.0), 1000.0)
        assert len(signals) == 1
        s = signals[0]
        assert s["code"] == "SH600001"
        assert s["rule"] == "止盈线 +20%"
        assert s["triggered"] is True
        assert s["distance_pct"] == pytest.approx(5.0)
        assert "触发" in s["status_label"]
        assert "部分止盈" in s["status_label"]
        assert s["action"] == "部分止盈"

    def test_take_profit_boundary_at_line(self):
        """收益率恰为 +20% → 触发（线上，距触发幅度 0）。"""
        signals = compute_discipline_signals(_holdings(20.0), 1000.0)
        assert len(signals) == 1
        assert signals[0]["distance_pct"] == pytest.approx(0.0)

    def test_no_signal_within_compliant_range(self):
        """收益率 +5%（止盈线与止损线之间）→ 不触发。"""
        signals = compute_discipline_signals(_holdings(5.0), 1000.0)
        assert signals == []


class TestStopLoss:
    """止损纪律：收益率 ≤ 止损线（默认 -15%）触发。"""

    def test_stop_loss_triggered(self):
        """收益率 -18% ≤ -15% → 触发，超线 +3%，建议止损/减仓。"""
        signals = compute_discipline_signals(_holdings(-18.0), 1000.0)
        assert len(signals) == 1
        s = signals[0]
        assert s["rule"] == "止损线 -15%"
        assert s["triggered"] is True
        assert s["distance_pct"] == pytest.approx(3.0)
        assert "触发" in s["status_label"]
        assert "止损" in s["status_label"]
        assert s["action"] == "止损/减仓"

    def test_minus_15_behavior_scenario(self):
        """-15% 止损场景：正确输出「触发 + 距触发幅度 + 建议动作」。"""
        signals = compute_discipline_signals(_holdings(-16.0), 1000.0)
        assert len(signals) == 1
        s = signals[0]
        assert s["triggered"] is True
        assert s["distance_pct"] == pytest.approx(1.0)  # 超线 1%
        assert "触发" in s["status_label"] and "1.0" in s["status_label"]
        assert "止损/减仓" in s["status_label"]
        assert s["value"] == "-16.0%"


class TestDistanceAndShape:
    """距触发幅度与信号结构。"""

    def test_distance_semantics(self):
        """止盈/止损距触发幅度 = 超线百分数（正数）。

        关闭静默期：本测试聚焦距触发幅度计算，避免同一代码两次触发被静默期抑制。
        """
        no_silence = {"silence_days": 0}
        tp = compute_discipline_signals(_holdings(23.5), 1000.0, discipline_config=no_silence)[0]
        assert tp["distance_pct"] == pytest.approx(3.5)
        sl = compute_discipline_signals(_holdings(-17.5), 1000.0, discipline_config=no_silence)[0]
        assert sl["distance_pct"] == pytest.approx(2.5)

    def test_signal_shape_fields(self):
        """每项含 code/name/rule/value/status_label/triggered/distance_pct/action。"""
        s = compute_discipline_signals(_holdings(30.0), 1000.0)[0]
        assert {
            "code",
            "name",
            "rule",
            "value",
            "status_label",
            "triggered",
            "distance_pct",
            "action",
        } <= set(s.keys())
        assert s["value"] == "+30.0%"

    def test_custom_threshold(self):
        """自定义止盈线 +10% → 收益率 +12% 触发（默认 +20% 下不触发）。"""
        cfg = {"take_profit_pct": 10.0, "stop_loss_pct": -8.0}
        signals = compute_discipline_signals(_holdings(12.0), 1000.0, discipline_config=cfg)
        assert len(signals) == 1
        assert signals[0]["rule"] == "止盈线 +10%"


# ── 回撤纪律 ─────────────────────────────────────────────


class TestDrawdownDiscipline:
    """组合回撤纪律：相对历史峰值回撤 ≥ 回撤线（默认 -10%）触发。"""

    def test_drawdown_triggered(self):
        """峰值 10000、当前 8800 → 回撤 12% ≥ 10% → 触发。"""
        signals = compute_discipline_signals(
            _holdings(0.0),
            8800.0,
            portfolio_peak_mv=10000.0,
        )
        assert len(signals) == 1
        s = signals[0]
        assert s["name"] == "组合"
        assert s["rule"] == "回撤线 -10%"
        assert s["triggered"] is True
        assert s["distance_pct"] == pytest.approx(2.0)
        assert "回撤" in s["status_label"]

    def test_drawdown_skipped_without_peak(self):
        """无峰值数据 → 不输出回撤信号（数据可用时激活）。"""
        signals = compute_discipline_signals(_holdings(0.0), 8800.0, portfolio_peak_mv=None)
        assert signals == []

    def test_drawdown_skipped_at_peak(self):
        """当前市值不低于峰值 → 无回撤。"""
        signals = compute_discipline_signals(
            _holdings(0.0),
            10000.0,
            portfolio_peak_mv=10000.0,
        )
        assert signals == []

    def test_drawdown_below_threshold(self):
        """回撤 5% < 10% → 不触发。"""
        signals = compute_discipline_signals(
            _holdings(0.0),
            9500.0,
            portfolio_peak_mv=10000.0,
        )
        assert signals == []

    def test_drawdown_rule_text_negative_when_positive_config(self):
        """回撤线配置为正值（10）时，规则文本统一按负值展示（回撤线 -10%）。"""
        cfg = {"drawdown_pct": 10.0}
        signals = compute_discipline_signals(
            _holdings(0.0),
            8800.0,
            portfolio_peak_mv=10000.0,
            discipline_config=cfg,
        )
        assert len(signals) == 1
        assert signals[0]["rule"] == "回撤线 -10%"


# ── 静默期 ───────────────────────────────────────────────


class TestSilencePeriod:
    """静默期：同一品种触发后 N 天内不重复告警（复用再平衡静默机制）。"""

    def test_silence_suppresses_repeat_trigger(self, tmp_path):
        """首次触发写入状态；静默期内再次计算 → 信号被抑制。"""
        silence_file = str(tmp_path / "discipline_silence.json")
        cfg = {"silence_days": 30}
        first = compute_discipline_signals(
            _holdings(25.0),
            1000.0,
            discipline_config=cfg,
            silence_file=silence_file,
        )
        assert len(first) == 1
        assert os.path.exists(silence_file)

        second = compute_discipline_signals(
            _holdings(25.0),
            1000.0,
            discipline_config=cfg,
            silence_file=silence_file,
        )
        assert second == []

    def test_silence_expired_retriggers(self, tmp_path):
        """静默期已过（历史触发日期早于窗口）→ 清理并恢复触发。"""
        silence_file = str(tmp_path / "discipline_silence.json")
        with open(silence_file, "w", encoding="utf-8") as f:
            json.dump({"SH600001": "2000-01-01"}, f)  # 远早于静默窗口
        cfg = {"silence_days": 30}
        signals = compute_discipline_signals(
            _holdings(25.0),
            1000.0,
            discipline_config=cfg,
            silence_file=silence_file,
        )
        assert len(signals) == 1  # 静默期已过，重新触发
        assert signals[0]["triggered"] is True

    def test_silence_disabled_when_zero(self, tmp_path):
        """silence_days=0 → 不抑制重复信号。"""
        silence_file = str(tmp_path / "discipline_silence.json")
        cfg = {"silence_days": 0}
        for _ in range(2):
            signals = compute_discipline_signals(
                _holdings(25.0),
                1000.0,
                discipline_config=cfg,
                silence_file=silence_file,
            )
            assert len(signals) == 1


# ── 多品种与守卫 ─────────────────────────────────────────


class TestMultiAndGuards:
    """多品种混合触发与数据守卫。"""

    def test_multiple_positions_mixed(self):
        """多品种：一只触发止盈、一只触发止损、一只合规。"""
        signals = compute_discipline_signals(_holdings(25.0, -18.0, 5.0), 3000.0)
        assert len(signals) == 2
        rules = {s["code"]: s["rule"] for s in signals}
        assert rules["SH600001"] == "止盈线 +20%"
        assert rules["SH600002"] == "止损线 -15%"

    def test_empty_holdings(self):
        """空持仓 → 无信号。"""
        assert compute_discipline_signals([], 1000.0) == []
        assert compute_discipline_signals(None, 1000.0) == []

    def test_total_mv_zero_guard(self):
        """总市值为 0 → 无信号（不除零）。"""
        assert compute_discipline_signals(_holdings(25.0), 0.0) == []

    def test_missing_profit_rate_skipped(self):
        """缺 profit_rate 的品种跳过（不触发也不报错）。"""
        signals = compute_discipline_signals(_holdings(None), 1000.0)
        assert signals == []
