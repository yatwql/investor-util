"""市场情绪章内区块的接线测试（开关门禁 / 契约注入 / 双端渲染载体）。

覆盖：编排函数受开关门禁、异常兜底为 None、Excel 区块写入（含零命中说明）、
HTML partial 含区块标记（双端同源）。

运行：
  pytest src/test/unit/report/test_market_sentiment_wiring.py -v
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from src.python.report import _report_aux_metrics as aux

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


_CONTRACT = {
    "available": True,
    "reason": "",
    "trade_date": "2026-09-16",
    "summary": {"board_caps": {"二连板": 4}, "lhb_stock_count": 63, "ladder_date": "2026-09-16"},
    "rows": [
        {
            "code": "600900",
            "name": "长江电力",
            "holding_kind": "直接持有",
            "event_type": "龙虎榜",
            "event_date": "2026-09-16",
            "net_value_yi": 9.14,
            "hot_money_net_value_yi": -0.25,
            "org_net_value_yi": 2.06,
            "hot_rank": 1,
            "range_days": 3,
            "limit_reason": "电网投资+中报增长",
            "concepts": "电力、核电",
            "board_label": "",
            "board_num": None,
            "seal_nextday": None,
        }
    ],
    "failures": [],
    "entry_count": 1,
}


def _enable(on: bool):
    from src.python.config.features import set_feature_enabled

    set_feature_enabled("market_sentiment", on)


class TestOrchestrationGate:
    def test_switch_off_returns_none(self, monkeypatch):
        _enable(False)
        assert aux.compute_market_sentiment_data([SimpleNamespace(code="600900", name="长江电力")], None, {}) is None

    def test_switch_on_delegates_to_builder(self, monkeypatch):
        _enable(True)
        calls = {}

        def _build(holdings, penetrated, config):
            calls["penetrated"] = penetrated
            return _CONTRACT

        monkeypatch.setattr("src.python.report.market_sentiment.build_market_sentiment_data", _build)
        out = aux.compute_market_sentiment_data(
            [SimpleNamespace(code="600900", name="长江电力")],
            {"penetrated_assets": [{"name": "中际旭创", "codes": ["300308"]}]},
            {},
        )
        assert out is _CONTRACT
        assert calls["penetrated"] == [{"name": "中际旭创", "codes": ["300308"]}]

    def test_builder_exception_returns_none(self, monkeypatch):
        """增强模块异常不得中断主报告（兜底为 None，其余章节照常）。"""
        _enable(True)
        monkeypatch.setattr(
            "src.python.report.market_sentiment.build_market_sentiment_data",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        assert aux.compute_market_sentiment_data([], None, {}) is None


class TestExcelBlock:
    def _write(self, data):
        from src.python.report.action_sheet import _write_market_sentiment_block

        ws = Workbook().active
        _write_market_sentiment_block(ws, 1, data, 5)
        return "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)

    def test_hit_rows_rendered(self):
        text = self._write(_CONTRACT)
        assert "市场情绪与持仓热点" in text
        assert "长江电力" in text and "600900" in text
        assert "净买额 9.14 亿" in text and "游资 -0.25 亿" in text
        assert "龙虎榜上榜 63 只" in text
        assert "非投资建议" in text

    def test_zero_hits_shows_reason_and_overview(self):
        text = self._write(
            {**_CONTRACT, "rows": [], "entry_count": 0, "reason": "当日无持仓/穿透标的命中龙虎榜或连板梯队"}
        )
        assert "当日无持仓/穿透标的命中" in text
        assert "龙虎榜上榜 63 只" in text  # 概览仍在

    def test_unavailable_writes_reason(self):
        text = self._write({"available": False, "reason": "未配置同花顺 API key", "failures": []})
        assert "未配置同花顺 API key" in text


class TestHtmlParity:
    def test_partial_contains_block(self):
        """HTML partial 与 Excel 同源：区块标记与关键字段都在模板里。"""
        text = Path("src/static/tmpl/partials/action_section.html").read_text(encoding="utf-8")
        assert "市场情绪与持仓热点" in text
        assert "market_sentiment_data" in text
        assert "不做概念联想" in text  # 口径说明双端一致
