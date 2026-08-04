"""尾部风险统计（tail_risk_data数据契约）全接线测试 — 注入 + Excel + HTML。

覆盖：
  - _prepare_full_risk_metrics 将 tail_risk_data 注入 pipeline_data（充足 / 不足）
  - Excel：write_portfolio_history_drawdown_sheet 尾部指标行（可用 / 占位）
  - HTML：组合历史走势与回撤章尾部风险卡（可用 / 样本不足 / 未恢复 / 图下说明）
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

from src.test.unit.report.test_html_report_structure import (
    _REPORT_SECTION_DEFAULT,
    _build_minimal_render_data,
    _render_template,
)


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


# 21 个日收益固定 fixture（同模块测试）：VaR95=4.0%、VaR99=5.0%、最大单日跌幅=5.0%
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


def _mock_history(bars: list[dict]) -> dict:
    """构造带 bars 的 history_data mock（daily_returns 置空，跳过量化指标重计算）。"""
    return {
        "status": "ok",
        "bars": bars,
        "daily_returns_portfolio": [],
        "annualized_volatility": 0.12,
        "max_drawdown_pct": -5.0,
        "total_return_pct": 10.0,
        "data_start": "2026-01-01",
        "data_end": "2026-02-01",
        "warnings": [],
    }


class TestPipelineInjection:
    """tail_risk_data 注入 pipeline_data。"""

    def _prepare(self, history_data: dict):
        from src.python.report._report_generation import _prepare_full_risk_metrics

        prep: dict = {}
        pipeline_data: dict = {}
        reporter = MagicMock()
        perf = MagicMock()
        holdings = [MagicMock(code="SH600001")]
        with (
            patch(
                "src.python.report._snapshot.fetch_history_data",
                return_value=history_data,
            ),
            patch(
                "src.python.analysis.crisis_annotation.build_crisis_annotation",
                return_value={"available": False, "intervals": []},
            ),
        ):
            history, metrics = _prepare_full_risk_metrics(
                holdings,
                config={},
                reporter=reporter,
                perf=perf,
                fetch_history=False,
                enable_history=True,
                prep=prep,
                pipeline_data=pipeline_data,
            )
        return history, metrics, pipeline_data

    def test_inject_tail_risk_data_available(self):
        """样本充足 → pipeline_data.tail_risk_data available=True 且指标正确。"""
        history, _metrics, pipeline_data = self._prepare(_mock_history(_bars_from_returns(FIXED_RETURNS)))
        assert history is not None
        tr = pipeline_data["tail_risk_data"]
        assert tr["available"] is True
        assert tr["var95"] == pytest.approx(4.0, abs=0.01)
        assert tr["var99"] == pytest.approx(5.0, abs=0.01)
        assert tr["max_single_day_drop"] == pytest.approx(5.0, abs=0.01)
        assert tr["consecutive_down_days"] == 3

    def test_inject_tail_risk_data_insufficient(self):
        """样本不足 → pipeline_data.tail_risk_data available=False。"""
        _history, _metrics, pipeline_data = self._prepare(
            _mock_history(_bars_from_returns([0.01, -0.01, 0.02, -0.02]))  # 4 个收益
        )
        tr = pipeline_data["tail_risk_data"]
        assert tr["available"] is False
        assert tr["var95"] is None
        assert tr["sample_size"] == 4

    def test_inject_skipped_when_pipeline_none(self):
        """pipeline_data=None → 不注入、不抛异常。"""
        from src.python.report._report_generation import _prepare_full_risk_metrics

        with (
            patch(
                "src.python.report._snapshot.fetch_history_data",
                return_value=_mock_history(_bars_from_returns(FIXED_RETURNS)),
            ),
        ):
            history, metrics = _prepare_full_risk_metrics(
                [MagicMock(code="SH600001")],
                config={},
                reporter=MagicMock(),
                perf=MagicMock(),
                fetch_history=False,
                enable_history=True,
                prep={},
                pipeline_data=None,
            )
        assert history is not None


class TestExcelTailRiskRows:
    """Excel 组合历史走势与回撤章尾部指标行呈现。"""

    def _write(self, history_data, tail_risk=None):
        from openpyxl import Workbook

        from src.python.report.portfolio_history_drawdown_sheet import (
            write_portfolio_history_drawdown_sheet,
        )

        wb = Workbook()
        ws = wb.active
        write_portfolio_history_drawdown_sheet(ws, history_data, None, tail_risk)
        return ws

    def _flat(self, ws) -> list[str]:
        return [str(c.value) if c.value is not None else "" for row in ws.iter_rows() for c in row]

    def test_tail_risk_rows_written_when_available(self):
        """available=True → 写入 VaR/最大单日跌幅/连续下跌/恢复天数行。"""
        tail_risk = {
            "available": True,
            "sample_size": 21,
            "var95": 4.0,
            "var99": 5.0,
            "max_single_day_drop": 5.0,
            "max_single_day_drop_date": "2026-01-10",
            "consecutive_down_days": 3,
            "consecutive_down_start": "2026-01-03",
            "consecutive_down_end": "2026-01-05",
            "recovery_days_after_drop": 1,
            "recovery_state": "recovered",
        }
        ws = self._write(_mock_history(_bars_from_returns(FIXED_RETURNS)), tail_risk)
        flat = self._flat(ws)
        for key in ("VaR(95)", "VaR(99)", "最大单日跌幅(%)", "最长连续下跌(天)", "最大单日跌幅后恢复(天)"):
            assert key in flat, f"缺少尾部指标行 {key}"
        # 值（百分比按 FMT_PERCENT 存小数）
        assert "0.04" in flat  # VaR95
        assert "0.05" in flat  # VaR99 / 最大单日跌幅
        assert "3" in flat  # 连续下跌天数
        assert "1" in flat  # 恢复天数

    def test_tail_risk_unrecovered_placeholder(self):
        """available=True 但未恢复 → 恢复单元格写「未恢复」。"""
        tail_risk = {
            "available": True,
            "sample_size": 21,
            "var95": 4.0,
            "var99": 5.0,
            "max_single_day_drop": 5.0,
            "max_single_day_drop_date": "2026-01-10",
            "consecutive_down_days": 1,
            "consecutive_down_start": None,
            "consecutive_down_end": None,
            "recovery_days_after_drop": None,
            "recovery_state": "unrecovered",
        }
        ws = self._write(_mock_history(_bars_from_returns(FIXED_RETURNS)), tail_risk)
        assert "未恢复" in self._flat(ws)

    def test_tail_risk_unavailable_placeholder(self):
        """tail_risk 缺失/不可用 → 写「样本不足」占位行。"""
        ws = self._write(_mock_history(_bars_from_returns(FIXED_RETURNS)))
        flat = self._flat(ws)
        assert any("样本不足" in v for v in flat), "tail_risk=None 应写入占位行"


class TestHtmlTailRiskCards:
    """HTML 组合历史走势与回撤章尾部风险卡呈现。"""

    def _render_section(self, tail_risk: dict | None) -> "object":
        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: (sec["key"] == "portfolio_history_drawdown") for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["history_data"] = {
            "status": "ok",
            "bars": [{"date": "2026-01-01", "total_value": 100.0, "drawdown_pct": 0.0}],
            "total_return_pct": 10.0,
            "total_return": 1000.0,
            "data_start": "2026-01-01",
            "data_end": "2026-02-01",
            "max_drawdown_pct": -0.05,
            "max_drawdown": -500.0,
            "annualized_volatility": 0.18,
            "drawdown_available": False,
            "drawdown_events": [],
            "min_depth_pct": 5,
        }
        data["tail_risk_data"] = tail_risk
        soup = _render_template(data)
        return soup.find(id="sec-portfolio_history_drawdown")

    def test_cards_rendered_when_available(self):
        """available=True → 渲染 VaR/最大单日跌幅/连续下跌/恢复卡。"""
        tail_risk = {
            "available": True,
            "sample_size": 21,
            "var95": 4.0,
            "var99": 5.0,
            "max_single_day_drop": 5.0,
            "max_single_day_drop_date": "2026-01-10",
            "consecutive_down_days": 3,
            "consecutive_down_start": "2026-01-03",
            "consecutive_down_end": "2026-01-05",
            "recovery_days_after_drop": 1,
            "recovery_state": "recovered",
        }
        section = self._render_section(tail_risk)
        text = section.get_text()
        assert "VaR(95)" in text
        assert "VaR(99)" in text
        assert "+4.00%" in text
        assert "+5.00%" in text
        assert "最大单日跌幅" in text
        assert "最长连续下跌" in text
        assert "3 天" in text
        assert "最大跌幅后恢复" in text
        assert "1 天" in text

    def test_unrecovered_state_rendered(self):
        """recovery_state=unrecovered → 卡显示「未恢复」。"""
        tail_risk = {
            "available": True,
            "sample_size": 21,
            "var95": 4.0,
            "var99": 5.0,
            "max_single_day_drop": 5.0,
            "max_single_day_drop_date": "2026-01-10",
            "consecutive_down_days": 1,
            "consecutive_down_start": None,
            "consecutive_down_end": None,
            "recovery_days_after_drop": None,
            "recovery_state": "unrecovered",
        }
        section = self._render_section(tail_risk)
        assert "未恢复" in section.get_text()

    def test_placeholder_when_unavailable(self):
        """tail_risk 缺失 → 显示「样本不足」占位卡。"""
        section = self._render_section(None)
        text = section.get_text()
        assert "尾部风险统计" in text
        assert "样本不足" in text

    def test_caption_note_present(self):
        """尾部风险卡下方附说明（历史模拟法 VaR）。"""
        tail_risk = {
            "available": True,
            "sample_size": 21,
            "var95": 4.0,
            "var99": 5.0,
            "max_single_day_drop": 5.0,
            "max_single_day_drop_date": None,
            "consecutive_down_days": 1,
            "consecutive_down_start": None,
            "consecutive_down_end": None,
            "recovery_days_after_drop": None,
            "recovery_state": "unrecovered",
        }
        section = self._render_section(tail_risk)
        assert "历史模拟法 VaR" in section.get_text()
