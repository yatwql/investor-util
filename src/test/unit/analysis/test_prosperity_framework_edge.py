"""景气度框架诊断边缘场景测试（edge 标记，隔离在 *_edge.py）。

覆盖：
  - 空持仓 / 全零市值 / 负市值等退化输入不抛异常
  - 全防御板块、板块未知（"--"）等边界
  - 全部输入缺失 → 仅可计分维度参与、未验证清单完整
  - 极端集中度（单一持仓 100%）与快照不可用
运行：pytest src/test/unit/analysis/test_prosperity_framework_edge.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.prosperity_framework import build_prosperity_framework_data
from src.python.report.market_value import DetailRow

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


class _FakeDetail:
    """最小明细行替身（容忍异常字段值：None/负数/字符串）。"""

    def __init__(self, code, name, market_value):
        self.code = code
        self.name = name
        self.market_value = market_value


def test_empty_holdings_returns_unavailable():
    data = build_prosperity_framework_data([])
    assert data["available"] is False
    assert "无持仓数据" in data["reason"]


def test_none_holdings_returns_unavailable():
    assert build_prosperity_framework_data(None)["available"] is False


def test_all_zero_market_value_does_not_crash():
    details = [_FakeDetail("600519", "贵州茅台", 0.0), _FakeDetail("601398", "工商银行", 0.0)]
    data = build_prosperity_framework_data(details)
    assert data["available"] is True
    conc = next(d for d in data["dimensions"] if d["key"] == "concentration_cycle")
    # 无非零市值 → 集中度不可算，仅换手子项缺失 → 全缺 → unverified
    assert conc["status"] == "unverified"
    assert any("无可计算的前十大集中度" in u for u in conc["unverified"])


def test_invalid_market_value_types_tolerated():
    details = [_FakeDetail("600519", "贵州茅台", None), _FakeDetail("000001", "平安银行", "oops")]
    data = build_prosperity_framework_data(details)
    assert data["available"] is True
    assert isinstance(data["total_score"], int)


def test_all_defensive_scores_zero_boom():
    details = [_FakeDetail("600519", "贵州茅台", 100_000.0), _FakeDetail("601398", "工商银行", 100_000.0)]
    penetration = {
        "top10": [
            {"name": "贵州茅台", "sector": "消费", "concepts": ["白酒"], "ratio_pct": 50.0},
            {"name": "工商银行", "sector": "金融", "concepts": ["银行"], "ratio_pct": 50.0},
        ]
    }
    data = build_prosperity_framework_data(details, penetration_data=penetration)
    boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
    assert boom["score"] == 0
    assert any("未命中任何景气关键词" in e for e in boom["evidence"])


def test_unknown_sector_holdings_are_low_scores():
    details = [_FakeDetail("999999", "未知品种", 100_000.0)]
    data = build_prosperity_framework_data(details)
    boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
    assert boom["score"] == 0
    edge = next(d for d in data["dimensions"] if d["key"] == "global_edge")
    assert edge["score"] <= 5  # 仅境外占比可能给分；A 股未知代码不加分


def test_single_holding_extreme_concentration():
    details = [_FakeDetail("300308", "中际旭创", 1_000_000.0)]
    data = build_prosperity_framework_data(details)
    assert data["concentration_pct"] == 100.0
    conc = next(d for d in data["dimensions"] if d["key"] == "concentration_cycle")
    assert conc["score"] == 3  # 超过 1.4×目标 → 高集中度档


def test_all_inputs_missing_lists_every_unverified_dimension():
    details = [_FakeDetail("300308", "中际旭创", 100_000.0)]
    data = build_prosperity_framework_data(details)
    assert len(data["unverified"]) == 3  # ROE / 流动性 / 业绩
    assert data["scored_weight"] == 55
    by_key = {d["key"]: d for d in data["dimensions"]}
    assert by_key["roe_elasticity"]["status"] == "unverified"
    assert by_key["liquidity"]["status"] == "unverified"
    assert by_key["performance"]["status"] == "unverified"
    assert by_key["boom_cycle"]["status"] == "scored"
    assert by_key["global_edge"]["status"] == "scored"


def test_snapshots_without_holdings_key_are_ignored():
    data = build_prosperity_framework_data(
        [_FakeDetail("300308", "中际旭创", 100_000.0)],
        snapshots=[{"other": []}, {"other": []}],
    )
    assert data["turnover_proxy_pct"] is None


def test_history_with_zero_return_and_no_benchmark():
    details = [_FakeDetail("300308", "中际旭创", 100_000.0)]
    data = build_prosperity_framework_data(
        details,
        history_data={"status": "ok", "drawdown_available": True, "total_return_pct": 0.0, "max_drawdown_pct": 40.0},
    )
    dim = next(d for d in data["dimensions"] if d["key"] == "performance")
    assert dim["score"] == 3  # 收益非正 → 3 分；回撤 >25% 不加分
    assert any("未跑赢" not in e for e in dim["evidence"])


def test_negative_total_return_and_deep_drawdown():
    data = build_prosperity_framework_data(
        [_FakeDetail("300308", "中际旭创", 100_000.0)],
        history_data={"status": "ok", "drawdown_available": True, "total_return_pct": -12.0, "max_drawdown_pct": 33.0},
    )
    dim = next(d for d in data["dimensions"] if d["key"] == "performance")
    assert dim["score"] == 3
    assert any("最大回撤 33.00%" in e for e in dim["evidence"])


def test_penetration_top10_empty_list_falls_back_to_direct():
    data = build_prosperity_framework_data(
        [_FakeDetail("300308", "中际旭创", 100_000.0)], penetration_data={"top10": []}
    )
    boom = next(d for d in data["dimensions"] if d["key"] == "boom_cycle")
    assert any("直接持仓板块分布" in e for e in boom["evidence"])


def test_detail_row_objects_with_negative_market_value():
    rows = [DetailRow(account="A", name="中际旭创", code="300308", market_value=-1.0, cost=0.0)]
    data = build_prosperity_framework_data(rows)
    assert data["available"] is True
    assert data["total_score"] >= 0
