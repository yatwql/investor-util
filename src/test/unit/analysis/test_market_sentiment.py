"""市场情绪纯装配单元测试（龙虎榜 / 连板梯队 × 持仓与穿透标的）。

覆盖：跟踪标的映射（直接持有优先）、龙虎榜命中与净买额排序/亿元换算/概念截断、
连板梯队最新交易日与板位标签/封板标记、无命中与无数据两种降级契约、汇总字段。

运行：
  pytest src/test/unit/analysis/test_market_sentiment.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.python.analysis.market_sentiment import build_market_sentiment, tracked_targets

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _holding(code: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(code=code, name=name)


_LHB = {
    "trade_date": "2026-09-16",
    "stock_count": 63,
    "stock_items": [
        {
            "ticker": "600900",
            "name": "长江电力",
            "net_value": 914_138_161.16,
            "hot_money_net_value": -25_126_051.63,
            "org_net_value": 205_899_784.14,
            "hot_rank": 1,
            "range_days": 3,
            "limit_reason": "光纤光缆+网络安全+中报增长",
            "concept_list": [{"name": "5G"}, {"name": "光纤概念"}, {"name": "固态电池"}, {"name": "第四个"}],
        },
        {"ticker": "000001", "name": "平安银行", "net_value": 5_000_000_000.0},  # 非跟踪标的 → 不出现
    ],
}

_LADDER = {
    "window": {
        "length": 30,
        "date_list": ["2026-09-16", "2026-09-15"],
        "board_caps": {"two_board": 4, "seven_over": 1},
    },
    "item": [
        {
            "date": "2026-09-16",
            "boards": {
                "two_board": [{"ticker": "300308", "name": "中际旭创", "board_num": 2, "seal_nextday": True}],
                "seven_over": [{"ticker": "999999", "name": "无关股", "board_num": 7, "seal_nextday": False}],
            },
        },
        {"date": "2026-09-15", "boards": {"two_board": [{"ticker": "600900", "name": "长江电力", "board_num": 2}]}},
    ],
}


class TestTrackedTargets:
    def test_direct_holding_wins_over_penetrated(self):
        targets = tracked_targets(
            [_holding("600900", "长江电力")],
            [{"name": "长江电力", "codes": ["600900"]}, {"name": "中际旭创", "codes": ["300308"]}],
        )
        assert targets["600900"]["holding_kind"] == "直接持有"
        assert targets["300308"] == {"name": "中际旭创", "holding_kind": "穿透"}

    def test_empty_inputs(self):
        assert tracked_targets([], None) == {}


class TestDragonTigerRows:
    def _rows(self):
        targets = tracked_targets([_holding("600900", "长江电力")], [{"name": "中际旭创", "codes": ["300308"]}])
        return build_market_sentiment(_LHB, _LADDER, targets)

    def test_only_tracked_codes_kept(self):
        codes = {r["code"] for r in self._rows()["rows"]}
        assert codes == {"600900", "300308"}  # 平安银行被过滤

    def test_amounts_in_yi_and_concepts_truncated(self):
        row = next(r for r in self._rows()["rows"] if r["event_type"] == "龙虎榜")
        assert row["net_value_yi"] == pytest.approx(9.14)
        assert row["hot_money_net_value_yi"] == pytest.approx(-0.25)
        assert row["org_net_value_yi"] == pytest.approx(2.06)
        assert row["concepts"] == "5G、光纤概念、固态电池"  # 只留前三个
        assert row["event_date"] == "2026-09-16"

    def test_ladder_uses_latest_day_only(self):
        """连板梯队只取最新交易日（历史日期里的命中不算当日事件）。"""
        rows = [r for r in self._rows()["rows"] if r["event_type"] == "连板梯队"]
        assert len(rows) == 1
        assert rows[0]["code"] == "300308"
        assert rows[0]["board_label"] == "二连板"
        assert rows[0]["seal_nextday"] is True
        assert rows[0]["event_date"] == "2026-09-16"

    def test_summary_fields(self):
        summary = self._rows()["summary"]
        assert summary["lhb_stock_count"] == 63
        assert summary["ladder_date"] == "2026-09-16"
        assert summary["board_caps"]["二连板"] == 4 and summary["board_caps"]["七连板及以上"] == 1


class TestDegradedContracts:
    def test_no_source_available(self):
        out = build_market_sentiment(None, None, {"600900": {"name": "长江电力", "holding_kind": "直接持有"}})
        assert out["available"] is False
        assert out["reason"] == "情绪面数据不可用"
        assert {f["source"] for f in out["failures"]} == {"龙虎榜", "连板梯队"}

    def test_sources_ok_but_no_hits_still_available(self):
        """零命中也要出契约（带市场概览与说明）——价值型组合常年不涨停，恒空会让人分不清空与坏。"""
        out = build_market_sentiment(_LHB, _LADDER, {"111111": {"name": "无", "holding_kind": "穿透"}})
        assert out["available"] is True
        assert out["rows"] == [] and out["entry_count"] == 0
        assert "无持仓/穿透标的命中" in out["reason"]
        assert out["summary"]["lhb_stock_count"] == 63  # 概览仍在
        assert out["failures"] == []  # 源本身可用 → 不记失败

    def test_dirty_values_do_not_raise(self):
        out = build_market_sentiment(
            {
                "trade_date": "2026-09-16",
                "stock_items": [{"ticker": "600900", "net_value": "bad", "concept_list": "x"}],
            },
            None,
            {"600900": {"name": "长江电力", "holding_kind": "直接持有"}},
        )
        assert out["available"] is True
        assert out["rows"][0]["net_value_yi"] is None
        assert out["rows"][0]["concepts"] == ""
