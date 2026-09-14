"""fetcher/financial_report.py 单元测试。

覆盖：A 股标的收集（过滤/去重/合并穿透）、元数据取用（文种顺序 + 缓存）、
单篇取用与字段装配、摘要截断、无覆盖返回 None。

运行：
  pytest src/test/unit/fetcher/test_financial_report.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.python.fetcher import financial_report as fr

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


class TestCollectTargets:
    def test_filters_non_a_share_and_dedups(self):
        holdings = [
            SimpleNamespace(code="600519", name="贵州茅台"),
            SimpleNamespace(code="000001", name="平安银行"),
            SimpleNamespace(code="016055", name="某联接基金"),  # 场外基金，非 A 股
            SimpleNamespace(code="600519", name="贵州茅台"),  # 重复
        ]
        targets = fr.collect_a_share_targets(holdings)
        assert [t["code"] for t in targets] == ["000001", "600519"]
        assert targets[1]["symbol"] == "600519.SS"

    def test_merges_penetrated_codes(self):
        holdings = [SimpleNamespace(code="600519", name="贵州茅台")]
        targets = fr.collect_a_share_targets(holdings, penetrated_codes=["300750", "AAPL"])
        assert [t["code"] for t in targets] == ["300750", "600519"]
        assert targets[0]["symbol"] == "300750.SZ"

    def test_empty(self):
        assert fr.collect_a_share_targets([]) == []


class TestFetchSymbolReport:
    def test_no_index_returns_none(self, monkeypatch):
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        assert fr.fetch_symbol_report("600519.SS") is None

    def test_assembles_record_and_truncates(self, monkeypatch):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(
            fr.datasink,
            "fetch_report_documents",
            lambda symbol, doc_type=None, **k: (
                [{"id": 7, "report_period": "2025-12-31", "doc_type": doc_type}] if doc_type == "annual" else None
            ),
        )
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section: {
                "doc_id": 7,
                "symbol": "600519.SS",
                "report_period": "2025-12-31",
                "doc_type": "annual",
                "title": "2025 年年度报告",
                "announcement_time": 1767225600000,
                "content": "甲" * 50,
                "word_count": 50,
                "source": "巨潮资讯网 (cninfo)",
                "adjunct_url": "http://x",
            },
        )
        rec = fr.fetch_symbol_report("600519.SS", max_chars=10)
        assert rec is not None
        assert rec["doc_id"] == 7
        assert rec["summary"] == "甲" * 10
        assert len(rec["content"]) == 50
        assert rec["source"] == "巨潮资讯网 (cninfo)"

    def test_index_hit_skips_provider(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: [{"id": 9}])
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: calls.append(1) or None)
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section: {"doc_id": doc_id, "content": "x"})
        rec = fr.fetch_symbol_report("600519.SS")
        assert rec is not None and rec["doc_id"] == 9
        assert calls == []

    def test_document_miss_returns_none(self, monkeypatch):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: [{"id": 7}])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section: None)
        assert fr.fetch_symbol_report("600519.SS") is None
