"""确定性载体登记 — 单元测试。

覆盖：从 action_data 抽取卖出向决策（纪律信号 / 再平衡信号 / 组合级回撤跳过 /
纪律优先去重 / 带结算基线）；登记落账 pending 且带 baseline（入账必可结算）；
无持仓基线跳过不落账；开关关闭不登记。

运行：
  pytest src/test/unit/report/test_decision_record.py -v
"""

from __future__ import annotations

import pytest

from src.python.config.features import set_feature_enabled, reset_feature_flags
from src.python.core import decision_ledger as dl
from src.python.report import decision_record as rec

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

# 持仓明细：price 即登记日结算基线
_HOLDINGS: list[dict] = [
    {"name": "贵州茅台", "code": "600519", "price": 1680.0},
    {"name": "创业板ETF", "code": "159915", "price": 2.1},
    {"name": "浦发银行", "code": "sh600000", "price": 10.0},
]


@pytest.fixture(autouse=True)
def _enable_flag():
    """本组测试需要 decision_reflection 开启；结束后复位。"""
    set_feature_enabled("decision_reflection", True)
    yield
    reset_feature_flags()


def _signal(code, name, action, rule="", status_label=""):
    return {
        "code": code,
        "name": name,
        "action": action,
        "rule": rule,
        "status_label": status_label,
    }


class TestExtract:
    """action_data → 决策行抽取。"""

    def test_empty_action_data(self):
        assert rec.extract_deterministic_decisions(None) == []
        assert rec.extract_deterministic_decisions({}) == []
        assert rec.extract_deterministic_decisions({"available": False, "discipline_signals": []}) == []

    def test_discipline_signals_registered_short(self):
        ad = {
            "available": True,
            "discipline_signals": [
                _signal(
                    "600519", "贵州茅台", "部分止盈", rule="止盈线 +20%", status_label="触发（超线 2%，建议部分止盈）"
                ),
            ],
            "rebalance_signals": [],
        }
        rows = rec.extract_deterministic_decisions(ad)
        assert len(rows) == 1
        r = rows[0]
        assert r["code"] == "600519"
        assert r["direction"] == dl.DIRECTION_SHORT
        assert r["carrier"] == dl.CARRIER_DISCIPLINE
        assert r["magnitude"] == "mid"  # 部分止盈 → mid
        assert "超线 2%" in r["detail"]

    def test_rebalance_signal_registered_short(self):
        ad = {
            "available": True,
            "discipline_signals": [],
            "rebalance_signals": [
                {
                    "code": "159915",
                    "name": "创业板ETF",
                    "weight": 0.35,
                    "threshold": 0.2,
                    "action": "建议部分止盈至10-20%区间",
                },
            ],
        }
        rows = rec.extract_deterministic_decisions(ad)
        assert len(rows) == 1
        r = rows[0]
        assert r["code"] == "159915"
        assert r["carrier"] == dl.CARRIER_REBALANCE
        assert r["magnitude"] == "mid"
        assert "止盈" in r["detail"]

    def test_portfolio_drawdown_signal_skipped(self):
        # 组合级回撤：code 为空 → 跳过（无法按标的结算）
        ad = {
            "available": True,
            "discipline_signals": [_signal("", "组合", "减仓控回撤", rule="回撤线 -10%")],
            "rebalance_signals": [],
        }
        assert rec.extract_deterministic_decisions(ad) == []

    def test_discipline_precedence_over_rebalance(self):
        # 同 code 纪律 + 再平衡 → 纪律优先
        ad = {
            "available": True,
            "discipline_signals": [
                _signal("600000", "浦发银行", "止损/减仓", rule="止损线 -10%", status_label="触发，建议止损/减仓")
            ],
            "rebalance_signals": [
                {"code": "600000", "name": "浦发银行", "weight": 0.3, "threshold": 0.2, "action": "建议部分止盈"}
            ],
        }
        rows = rec.extract_deterministic_decisions(ad)
        assert len(rows) == 1
        assert rows[0]["carrier"] == dl.CARRIER_DISCIPLINE
        assert rows[0]["magnitude"] == "high"  # 止损 → high

    def test_different_codes_both_registered(self):
        ad = {
            "available": True,
            "discipline_signals": [_signal("600519", "贵州茅台", "部分止盈")],
            "rebalance_signals": [
                {"code": "159915", "name": "创业板ETF", "weight": 0.3, "threshold": 0.2, "action": "建议部分止盈"}
            ],
        }
        rows = rec.extract_deterministic_decisions(ad)
        assert len(rows) == 2
        codes = {r["code"] for r in rows}
        assert codes == {"600519", "159915"}


class TestRegister:
    """登记落账（须带结算基线；无基线跳过——入账必可结算）。"""

    def test_register_appends_pending_with_baseline(self, tmp_path):
        ad = {
            "available": True,
            "discipline_signals": [_signal("600519", "贵州茅台", "部分止盈", rule="止盈线 +20%")],
            "rebalance_signals": [],
        }
        out = rec.register_action_decisions(
            ad, holdings_details=_HOLDINGS, report_date="2026-09-01", path=str(tmp_path / "ledger.jsonl")
        )
        assert out["registered"] == 1
        assert len(out["ids"]) == 1
        stats = dl.fold_ledger(path=str(tmp_path / "ledger.jsonl"))
        assert stats["pending_count"] == 1
        d = stats["decisions"][0]
        assert d["status"] == "pending"
        assert d["carrier"] == dl.CARRIER_DISCIPLINE
        assert d["baseline_close"] == 1680.0  # 入账必可结算：基线落库

    def test_register_prefix_code_baseline(self, tmp_path):
        # sh600000 场内持仓别名 → 信号裸 600000 code 命中并取到基线
        ad = {
            "available": True,
            "discipline_signals": [_signal("600000", "浦发银行", "止损/减仓")],
            "rebalance_signals": [],
        }
        out = rec.register_action_decisions(ad, holdings_details=_HOLDINGS, path=str(tmp_path / "ledger.jsonl"))
        assert out["registered"] == 1
        stats = dl.fold_ledger(path=str(tmp_path / "ledger.jsonl"))
        assert stats["decisions"][0]["baseline_close"] == 10.0

    def test_no_baseline_skipped(self, tmp_path):
        # 无 holdings_details → 信号行无基线 → 跳过不落账（不留永久 pending）
        ad = {
            "available": True,
            "discipline_signals": [_signal("600519", "贵州茅台", "部分止盈")],
            "rebalance_signals": [],
        }
        out = rec.register_action_decisions(ad, path=str(tmp_path / "ledger.jsonl"))
        assert out == {"registered": 0, "ids": []}
        assert dl.fold_ledger(path=str(tmp_path / "ledger.jsonl"))["pending_count"] == 0

    def test_register_skips_same_day_duplicate(self, tmp_path):
        # 同日重跑（LLM 缓存命中/用户重生成）→ 同(报告日, code, carrier) pending
        # 已存在 → 第二次不重复登记（append-only 账本避免重复 pending 污染统计）
        lp = str(tmp_path / "ledger.jsonl")
        ad = {
            "available": True,
            "discipline_signals": [_signal("600519", "贵州茅台", "部分止盈", rule="止盈线 +20%")],
            "rebalance_signals": [],
        }
        first = rec.register_action_decisions(ad, holdings_details=_HOLDINGS, report_date="2026-09-01", path=lp)
        assert first["registered"] == 1
        second = rec.register_action_decisions(ad, holdings_details=_HOLDINGS, report_date="2026-09-01", path=lp)
        assert second == {"registered": 0, "ids": []}
        assert dl.fold_ledger(path=lp)["pending_count"] == 1

    def test_register_allows_next_day_new_decision(self, tmp_path):
        # 跨日新报告日视为新一轮判断（不误伤）；同 code 不同报告日各登记一条
        lp = str(tmp_path / "ledger.jsonl")
        ad = {
            "available": True,
            "discipline_signals": [_signal("600519", "贵州茅台", "部分止盈", rule="止盈线 +20%")],
            "rebalance_signals": [],
        }
        rec.register_action_decisions(ad, holdings_details=_HOLDINGS, report_date="2026-09-01", path=lp)
        rec.register_action_decisions(ad, holdings_details=_HOLDINGS, report_date="2026-09-02", path=lp)
        assert dl.fold_ledger(path=lp)["pending_count"] == 2

    def test_flag_off_no_register(self, tmp_path):
        reset_feature_flags()  # decision_reflection 默认 False
        ad = {
            "available": True,
            "discipline_signals": [_signal("600519", "贵州茅台", "部分止盈")],
            "rebalance_signals": [],
        }
        out = rec.register_action_decisions(ad, holdings_details=_HOLDINGS, path=str(tmp_path / "ledger.jsonl"))
        assert out == {"registered": 0, "ids": []}
        # 未落账
        assert dl.fold_ledger(path=str(tmp_path / "ledger.jsonl"))["settled_count"] == 0
