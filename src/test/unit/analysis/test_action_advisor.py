"""行动建议单一数据源单元测试（「行动建议」计算层）。

测试目标：
  - build_action_data 输出 `action_data` 契约（available/子块/摘要）
  - 再平衡信号：单品超限触发、全部合规为空、无持仓不可用
  - 交易纪律：收益率超止盈/止损线时信号流入 discipline_signals
  - 调仓建议/收益归因：后续轮次填充（当前为空骨架）
  - 摘要文本反映再平衡信号条数

运行：
  python -m pytest src/test/unit/analysis/test_action_advisor.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.action_advisor import build_action_data


pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


# ── 辅助构造 ──────────────────────────────────────────────


def _holding(
    name: str,
    code: str,
    market_value: float,
    profit: float = 0.0,
    shares: float = 0.0,
    price: float = 0.0,
) -> dict:
    """构造 holdings_details 单行（与 orchestrator 组装的字段一致）。"""
    return {
        "name": name,
        "code": code,
        "market_value": market_value,
        "cost": market_value - profit,
        "profit": profit,
        "profit_rate": (profit / max(market_value - profit, 1e-9)) * 100 if market_value else 0.0,
        "change_pct": 0.0,
        "nav_date": "2026-08-04",
        "source_api": "test",
        # shares/price 供调仓建议可行化层使用（缺省 0 时该品种不生成建议）
        "shares": shares,
        "price": price,
    }


def _concentrated_holdings() -> list[dict]:
    """构造超限持仓：一只占比 60%、一只占比 40%（各超 15% 警戒线）。"""
    return [
        _holding("品种甲", "600900", 6000.0),
        _holding("品种乙", "000001", 4000.0),
    ]


def _balanced_holdings() -> list[dict]:
    """构造合规持仓：十只各占 10%（不超 15% 警戒线）。"""
    return [_holding(f"品种{n}", f"60000{n}", 1000.0) for n in range(1, 11)]


class TestBuildActionData:
    """build_action_data 契约与行为测试。"""

    def test_contract_shape(self):
        """输出包含 available/rebalance_signals/discipline_signals/rebalance_advice/attribution/summary 六键。"""
        data = build_action_data(_concentrated_holdings(), 10000.0)
        assert set(data.keys()) == {
            "available",
            "rebalance_signals",
            "discipline_signals",
            "rebalance_advice",
            "attribution",
            "summary",
        }

    def test_unavailable_without_holdings(self):
        """空持仓 → available=False、各子块为空、摘要提示无数据。"""
        data = build_action_data([], 0.0)
        assert data["available"] is False
        assert data["rebalance_signals"] == []
        assert data["discipline_signals"] == []
        assert data["rebalance_advice"] == []
        assert data["attribution"] is None

    def test_rebalance_triggered_on_concentration(self):
        """单品占比超 15% 警戒线 → 再平衡信号正确列出超限品种。"""
        data = build_action_data(_concentrated_holdings(), 10000.0)
        assert data["available"] is True
        codes = {s["code"] for s in data["rebalance_signals"]}
        assert codes == {"600900", "000001"}
        for s in data["rebalance_signals"]:
            assert s["weight"] > 0.15

    def test_rebalance_empty_when_all_compliant(self):
        """全部品种占比合规 → 再平衡信号为空但 available=True。"""
        data = build_action_data(_balanced_holdings(), 10000.0)
        assert data["available"] is True
        assert data["rebalance_signals"] == []

    def test_discipline_signals_flow_through(self):
        """交易纪律信号经 build_action_data 流入 discipline_signals（收益率超线触发）。"""
        holdings = [
            _holding("品种甲", "600900", 1250.0, 250.0),  # +25% → 触发止盈
            _holding("品种乙", "000001", 850.0, -150.0),  # -15% → 触发止损
        ]
        data = build_action_data(holdings, 2100.0)
        assert data["available"] is True
        rules = {s["code"]: s["rule"] for s in data["discipline_signals"]}
        assert rules["600900"] == "止盈线 +20%"
        assert rules["000001"] == "止损线 -15%"

    def test_attribution_none_when_no_pnl(self):
        """全部品种无盈亏（Σ|profit|==0）→ 归因返回 None（渲染层写「待生成」占位）。"""
        data = build_action_data(_concentrated_holdings(), 10000.0)
        assert data["attribution"] is None

    def test_attribution_populated_with_profits(self):
        """有盈有亏 → 归因契约填充（盈利/亏损来源分列 + 净额合计摘要）。"""
        holdings = [
            _holding("品种甲", "600900", 1250.0, 250.0),
            _holding("品种乙", "000001", 850.0, -150.0),
        ]
        data = build_action_data(holdings, 2100.0)
        attr = data["attribution"]
        assert attr is not None
        assert attr["available"] is True
        assert {"盈利来源", "亏损来源", "summary"} <= set(attr.keys())
        assert {i["code"] for i in attr["盈利来源"]} == {"600900"}
        assert {i["code"] for i in attr["亏损来源"]} == {"000001"}
        assert "净" in attr["summary"]  # 净额合计摘要

    def test_rebalance_advice_flows_through_with_shares_price(self):
        """提供 shares/price 时，再平衡/纪律触发信号转成可执行调仓建议。"""
        holdings = [
            _holding("品种甲", "600900", 6000.0, profit=1500.0, shares=300, price=20.0),
            _holding("品种乙", "000001", 4000.0, profit=-1000.0, shares=400, price=10.0),
        ]
        data = build_action_data(holdings, 10000.0)
        assert data["available"] is True
        assert data["rebalance_advice"]
        for item in data["rebalance_advice"]:
            assert {"code", "name", "operation", "shares", "amount", "fee", "cash_after"} <= set(item)
            assert item["shares"] % 100 == 0  # 取整一手
            assert item["cash_after"] >= 0  # 现金非负
        # 乙跌超 -15% 触发止损 → 清仓建议优先
        assert data["rebalance_advice"][0]["operation"] == "止损"
        assert data["rebalance_advice"][0]["code"] == "000001"

    def test_summary_reflects_rebalance_count(self):
        """摘要文本反映再平衡信号条数（无信号/有信号两类）。"""
        empty = build_action_data(_balanced_holdings(), 10000.0)
        assert empty["summary"] == "当前无行动建议"

        triggered = build_action_data(_concentrated_holdings(), 10000.0)
        assert "再平衡建议 2 条" in triggered["summary"]

    def test_summary_includes_advice_count(self):
        """调仓建议非空时摘要追加「调仓建议 N 条」。"""
        holdings = [_holding("品种甲", "600900", 6000.0, profit=1500.0, shares=300, price=20.0)]
        data = build_action_data(holdings, 10000.0)
        assert "调仓建议 1 条" in data["summary"]

    def test_rebalance_signal_field_semantics(self):
        """再平衡信号每项含 code/name/weight/threshold/action（语义字段）。"""
        data = build_action_data(_concentrated_holdings(), 10000.0)
        s = data["rebalance_signals"][0]
        assert {"code", "name", "weight", "threshold", "action"} <= set(s.keys())

    def test_total_mv_guard(self):
        """总市值为 0 时按无有效数据处理（不除零）。"""
        data = build_action_data(_concentrated_holdings(), 0.0)
        assert data["available"] is True
        assert data["rebalance_signals"] == []

    def test_single_source_no_global_state(self):
        """重复调用返回独立对象（不共享模块级状态）。"""
        a = build_action_data(_concentrated_holdings(), 10000.0)
        b = build_action_data(_concentrated_holdings(), 10000.0)
        assert a is not b
        assert a["rebalance_signals"] is not b["rebalance_signals"]
