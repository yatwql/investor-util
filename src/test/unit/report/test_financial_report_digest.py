"""report/financial_report_digest.py 单元测试。

覆盖：凭据缺失/无 A 股标的/全部无覆盖的降级契约、成功行的文种中文标签与
披露日换算、摘要长度、失败清单不吞。

运行：
  pytest src/test/unit/report/test_financial_report_digest.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.python.report import financial_report_digest as frd

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _holding(code="600519", name="贵州茅台"):
    return SimpleNamespace(code=code, name=name)


class TestDegradedContracts:
    def test_missing_credential(self, monkeypatch):
        monkeypatch.setattr(frd.datasink, "missing_credential", lambda _sid: object())
        result = frd.build_financial_report_digest([_holding()])
        assert result["available"] is False
        assert "API key" in result["reason"]

    def test_no_a_share_holdings(self, monkeypatch):
        monkeypatch.setattr(frd.datasink, "missing_credential", lambda _sid: None)
        result = frd.build_financial_report_digest([_holding(code="016055", name="某联接基金")])
        assert result["available"] is False
        assert "无 A 股" in result["reason"]

    def test_all_uncovered(self, monkeypatch):
        monkeypatch.setattr(frd.datasink, "missing_credential", lambda _sid: None)
        monkeypatch.setattr(frd, "fetch_symbol_report", lambda *a, **k: None)
        result = frd.build_financial_report_digest([_holding()])
        assert result["available"] is False
        assert result["failures"][0]["code"] == "600519"


class TestAssembly:
    def test_rows_with_labels_and_date(self, monkeypatch):
        monkeypatch.setattr(frd.datasink, "missing_credential", lambda _sid: None)
        monkeypatch.setattr(
            frd,
            "fetch_symbol_report",
            lambda symbol, doc_types, section, max_chars: {
                "symbol": "600519.SS",
                "report_period": "2025-12-31",
                "doc_type": "annual",
                "title": "2025 年年度报告",
                "announcement_time": 1767225600000,
                "summary": "摘要正文",
                "source": "巨潮资讯网 (cninfo)",
                "adjunct_url": "http://x",
            },
        )
        result = frd.build_financial_report_digest([_holding()], config={"datasink": {"max_chars": 4}})
        assert result["available"] is True
        row = result["rows"][0]
        assert row["doc_type"] == "年报"
        assert row["announcement_date"] == "2026-01-01"
        assert row["source"] == "巨潮资讯网 (cninfo)"

    def test_partial_failures_kept(self, monkeypatch):
        monkeypatch.setattr(frd.datasink, "missing_credential", lambda _sid: None)

        def _fetch(symbol, doc_types, section, max_chars):
            return (
                None
                if symbol == "000001.SZ"
                else {"symbol": symbol, "report_period": "2025-12-31", "doc_type": "annual"}
            )

        monkeypatch.setattr(frd, "fetch_symbol_report", _fetch)
        holdings = [_holding("600519", "贵州茅台"), _holding("000001", "平安银行")]
        result = frd.build_financial_report_digest(holdings)
        assert result["entry_count"] == 1
        assert [f["code"] for f in result["failures"]] == ["000001"]


class TestHelpers:
    def test_announcement_date_boundaries(self):
        assert frd._announcement_date(0) == ""
        assert frd._announcement_date(None) == ""
        assert frd._announcement_date("bad") == ""

    def test_doc_type_label_fallback(self):
        assert frd._doc_type_label("semiannual") == "半年报"
        assert frd._doc_type_label("unknown") == "unknown"
