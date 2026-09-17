"""providers/akshare_financial.py 单元测试。

覆盖：宽表（指标 × 报告期）→ 标准字段记录的归一化；百分数换算为小数比例；
同名指标多分组时首个非空为准；缺失指标取 None；文种映射；非 A 股/未安装/
调用失败/空表降级；多期历史顺序与截断。

不发起真实网络：以 duck-typed 假宽表替换 akshare 返回对象。

运行：
  pytest src/test/unit/providers/test_akshare_financial.py -v
"""

from __future__ import annotations

import pytest

from src.python.providers import akshare_financial as af

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]

_COLS = ["选项", "指标", "20260630", "20251231", "20241231"]


class _Row(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class _FakeFrame:
    """最小 duck-typed 宽表：provider 只用 columns / empty / iterrows。"""

    def __init__(self, rows, columns=None, empty=False):
        self.columns = columns if columns is not None else _COLS
        self._rows = rows
        self.empty = empty

    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield i, row


def _row(option: str, name: str, **periods):
    r = _Row({"选项": option, "指标": name})
    r.update(periods)
    return r


def _patch(monkeypatch, frame):
    monkeypatch.setattr(af, "_import_akshare", lambda: _FakeAk(frame))


class _FakeAk:
    def __init__(self, frame):
        self._frame = frame

    def stock_financial_abstract(self, symbol: str):  # noqa: ARG002
        return self._frame


def _full_frame():
    return _FakeFrame(
        [
            _row("常用指标", "营业总收入", **{"20260630": 92278072083.21, "20251231": 1.0e11}),
            _row("常用指标", "归母净利润", **{"20260630": 44516880421.86, "20251231": 8.0e10}),
            _row("常用指标", "经营现金流量净额", **{"20260630": 70690750119.06}),
            _row("常用指标", "基本每股收益", **{"20260630": 35.57}),
            _row("常用指标", "每股净资产", **{"20260630": 200.989754}),
            _row("常用指标", "净资产收益率(ROE)", **{"20260630": 16.75}),
            _row("常用指标", "毛利率", **{"20260630": 89.555212}),
            _row("常用指标", "资产负债率", **{"20260630": 15.193112}),
            _row("成长能力", "营业总收入增长率", **{"20260630": 1.300099}),
            _row("成长能力", "归属母公司净利润增长率", **{"20260630": -1.951594}),
        ]
    )


class TestLatestRecord:
    def test_fields_and_units(self, monkeypatch):
        """最新报告期记录：金额原样、百分数换算为小数、文种与报告期正确。"""
        _patch(monkeypatch, _full_frame())
        rec = af.fetch_financial_indicators("600519")

        assert rec is not None
        assert rec["code"] == "600519"
        assert rec["symbol"] == "600519.SS"
        assert rec["report_period"] == "2026-06-30"
        assert rec["doc_type"] == "semiannual"
        assert rec["source_api"] == af.SOURCE_ID
        # 金额：元，原样
        assert rec["revenue"] == pytest.approx(92278072083.21)
        assert rec["operating_cash_flow"] == pytest.approx(70690750119.06)
        # 比率：上游百分数 → 小数比例
        assert rec["roe"] == pytest.approx(0.1675)
        assert rec["gross_margin"] == pytest.approx(0.895552)
        assert rec["debt_ratio"] == pytest.approx(0.151931)
        assert rec["revenue_yoy"] == pytest.approx(0.013001)
        assert rec["net_profit_yoy"] == pytest.approx(-0.019516)
        # 每股金额：元，原样
        assert rec["eps"] == pytest.approx(35.57)
        assert rec["bvps"] == pytest.approx(200.989754)

    def test_history_descending_and_limit(self, monkeypatch):
        """多期按报告期降序，limit 生效。"""
        _patch(monkeypatch, _full_frame())
        hist = af.fetch_financial_indicator_history("600519", limit=3)
        assert [r["report_period"] for r in hist] == ["2026-06-30", "2025-12-31"]

    def test_duplicate_indicator_first_non_empty_wins(self, monkeypatch):
        """同名指标出现在多个分组时，按表格顺序首个非空为准。"""
        frame = _FakeFrame(
            [
                _row("常用指标", "净资产收益率(ROE)", **{"20260630": 10.0}),
                _row("盈利能力", "净资产收益率(ROE)", **{"20260630": 99.0}),
            ]
        )
        _patch(monkeypatch, frame)
        rec = af.fetch_financial_indicators("600519")
        assert rec is not None
        assert rec["roe"] == pytest.approx(0.10)

    def test_earlier_period_value_fills_later_duplicate(self, monkeypatch):
        """前一分组的某期缺失、后一分组有值时，由后一分组补齐（逐期首个非空）。"""
        frame = _FakeFrame(
            [
                _row("常用指标", "毛利率", **{"20260630": 80.0}),
                _row("盈利能力", "毛利率", **{"20260630": 99.0, "20251231": 70.0}),
            ]
        )
        _patch(monkeypatch, frame)
        hist = af.fetch_financial_indicator_history("600519")
        assert hist[0]["gross_margin"] == pytest.approx(0.80)
        assert hist[1]["gross_margin"] == pytest.approx(0.70)


class TestDocType:
    @pytest.mark.parametrize(
        ("period", "expected"),
        [("20260331", "q1"), ("20260630", "semiannual"), ("20260930", "q3"), ("20261231", "annual")],
    )
    def test_doc_type_mapping(self, monkeypatch, period, expected):
        frame = _FakeFrame([_row("常用指标", "营业总收入", **{period: 100.0})], columns=["选项", "指标", period])
        _patch(monkeypatch, frame)
        rec = af.fetch_financial_indicators("600519")
        assert rec is not None
        assert rec["doc_type"] == expected
        assert rec["report_period"] == f"{period[:4]}-{period[4:6]}-{period[6:]}"


class TestDegradation:
    def test_missing_metrics_are_none(self, monkeypatch):
        """仅一项指标可用时，其余标准字段取 None（键恒出现），记录仍保留。"""
        frame = _FakeFrame([_row("常用指标", "营业总收入", **{"20260630": 100.0})])
        _patch(monkeypatch, frame)
        rec = af.fetch_financial_indicators("600519")
        assert rec is not None
        assert rec["revenue"] == pytest.approx(100.0)
        assert rec["roe"] is None
        assert rec["eps"] is None
        assert rec["net_profit"] is None

    def test_no_mapped_metric_yields_empty(self, monkeypatch):
        """宽表无任何可映射指标 → 空列表 / None。"""
        frame = _FakeFrame([_row("常用指标", "流动比率", **{"20260630": 1.2})])
        _patch(monkeypatch, frame)
        assert af.fetch_financial_indicator_history("600519") == []
        assert af.fetch_financial_indicators("600519") is None

    def test_non_a_share_filtered(self, monkeypatch):
        _patch(monkeypatch, _full_frame())
        assert af.fetch_financial_indicator_history("00700") == []
        assert af.fetch_financial_indicators("161725") is None

    def test_akshare_not_installed(self, monkeypatch):
        monkeypatch.setattr(af, "_import_akshare", lambda: None)
        assert af.fetch_financial_indicators("600519") is None

    def test_call_failure_returns_empty(self, monkeypatch):
        monkeypatch.setattr(af, "_import_akshare", lambda: _FakeAk(_full_frame()))
        monkeypatch.setattr(af, "run_with_timeout", lambda *_a, **_k: None)
        assert af.fetch_financial_indicators("600519") is None

    def test_empty_frame(self, monkeypatch):
        _patch(monkeypatch, _FakeFrame([], empty=True))
        assert af.fetch_financial_indicators("600519") is None

    def test_no_period_columns(self, monkeypatch):
        frame = _FakeFrame([_row("常用指标", "营业总收入")], columns=["选项", "指标"])
        _patch(monkeypatch, frame)
        assert af.fetch_financial_indicator_history("600519") == []
