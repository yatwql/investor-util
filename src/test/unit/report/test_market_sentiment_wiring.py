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


class _StubPerf:
    """PerfCollector 替身（只吞掉计时与落盘）。"""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def start(self, *args, **kwargs) -> None:
        pass

    def stop(self, *args, **kwargs) -> None:
        pass

    def save(self, *args, **kwargs) -> None:
        pass


def _prep_stub(tmp_path) -> dict:
    """full 路径 prep 契约的最小替身（穿透标的非空，用于验证其被传入）。"""
    return {
        "output_dir": str(tmp_path),
        "news_top_count": 0,
        "details": [],
        "holdings_details": [],
        "total_mv": 0.0,
        "penetrated_assets": [{"name": "中际旭创", "codes": ["300308"]}],
        "a_indices": [],
        "us_indices": [],
        "risk_metrics": {},
    }


class TestFullPathInjection:
    """full 路径（HTML+Excel+LLM）须在写 HTML 之前取数并注入市场情绪契约。

    回归场景：`_generate_report_full` 曾只把契约给 Excel（靠 excel_generator 的就地
    兜底才取数），HTML 侧既无形参也不传参——于是同一次运行的 HTML 不渲染情绪区块、
    其「数据源可用性矩阵」缺「市场情绪」行、说明表记「未使用」，与 Excel 产物自相矛盾。
    """

    _SENTINEL = {"available": True, "rows": [], "entry_count": 0, "trade_date": "2026-09-18"}

    def _run_full(self, monkeypatch, tmp_path) -> dict:
        """跑一遍 full 编排（外部依赖全替身），返回传给 HTML 生成器的关键字实参。"""
        from unittest.mock import MagicMock

        import src.python.report._report_generation as rg

        seen: dict = {}
        for _flag in (
            "is_enable_action",
            "is_enable_cost_lots",
            "is_enable_data_quality",
            "is_enable_financial_indicator",
            "is_enable_financial_report_digest",
            "is_enable_fund_deep_analysis",
            "is_enable_history",
            "is_enable_llm",
            "is_enable_news",
            "is_enable_portfolio_evolution",
        ):
            monkeypatch.setattr(f"src.python.config.{_flag}", lambda *a, **k: False)
        for _name in (
            "_validate_prep_completeness",
            "_validate_pipeline_snapshot",
            "_spawn_health_checks",
            "_collect_health_checks",
            "record_deterministic_decisions",
            "record_prosperity_diagnosis",
            "record_llm_decisions_and_review_block",
            "record_deterministic_signals",
        ):
            monkeypatch.setattr(rg, _name, lambda *a, **k: None)
        monkeypatch.setattr(rg, "apply_module_quality_banners", lambda content, *a, **k: content)
        monkeypatch.setattr(rg, "_prepare_full_risk_metrics", lambda *a, **k: ({}, None))
        monkeypatch.setattr("src.python.report.orchestrator.prepare_report_data", lambda *a, **k: _prep_stub(tmp_path))
        monkeypatch.setattr("src.python.report._snapshot.capture_snapshot", lambda *a, **k: {})
        monkeypatch.setattr("src.python.analysis.action_advisor.build_action_data", lambda *a, **k: {})
        monkeypatch.setattr("src.python.fetcher.akshare.get_sector_fund_flow", lambda *a, **k: None)
        monkeypatch.setattr(
            "src.python.report._llm_news._fetch_llm_and_news",
            lambda *a, **k: ((None, None, None, None), [], {}, False, None),
        )
        monkeypatch.setattr("src.python.core.perf.PerfCollector", _StubPerf)
        monkeypatch.setattr(
            "src.python.report._report_aux_metrics.compute_market_sentiment_data",
            lambda *a, **k: self._SENTINEL,
        )
        monkeypatch.setattr(rg, "_generate_full_html_report", lambda *a, **k: seen.update(k) or True)
        monkeypatch.setattr(rg, "_generate_full_excel_report", lambda *a, **k: True)

        rg._generate_report_full(
            holdings=[SimpleNamespace(code="600900", name="长江电力")],
            config={},
            reporter=MagicMock(),
            output_dir=str(tmp_path),
        )
        return seen

    def test_orchestrator_injects_contract_before_html(self, monkeypatch, tmp_path):
        """编排层取数结果必须出现在传给 HTML 生成器的实参中。"""
        assert self._run_full(monkeypatch, tmp_path).get("market_sentiment_data") is self._SENTINEL

    def test_html_generator_forwards_contract(self, monkeypatch, tmp_path):
        """`_generate_full_html_report` 须把契约透传给 `write_html_report`。"""
        from unittest.mock import MagicMock

        import src.python.report._report_generation as rg
        from src.python.report.orchestrator import ReportResult

        seen: dict = {}
        monkeypatch.setattr("src.python.config.features.is_feature_enabled", lambda *a, **k: False)
        monkeypatch.setattr(rg, "_build_chart_datasets_for_report", lambda *a, **k: {})
        monkeypatch.setattr(
            "src.python.report.html_writer.write_html_report",
            lambda *a, **k: seen.update(k) or str(tmp_path / "report.html"),
        )

        ok = rg._generate_full_html_report(
            [],
            _prep_stub(tmp_path),
            str(tmp_path),
            [],
            (None, None, None, None),
            [],
            {},
            True,
            None,
            MagicMock(),
            False,
            False,
            False,
            False,
            None,
            ReportResult(),
            market_sentiment_data=self._SENTINEL,
        )

        assert ok is True
        assert seen.get("market_sentiment_data") is self._SENTINEL
