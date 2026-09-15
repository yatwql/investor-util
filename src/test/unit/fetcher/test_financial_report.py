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

    def test_multi_section_concatenation_order(self, monkeypatch):
        """多章节按声明顺序拼接（各节正文以空行分隔），元数据取首个非空记录。"""
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: [{"id": 7}])
        parts = {"管理层讨论与分析": "A段", "财务报告": "B段"}
        monkeypatch.setattr(
            fr, "_fetch_document", lambda doc_id, section: {"doc_id": doc_id, "content": parts.get(section, "")}
        )
        rec = fr.fetch_symbol_report("600519.SS", sections=("管理层讨论与分析", "财务报告"), max_chars=100)
        assert rec is not None
        assert rec["content"] == "A段\n\nB段"
        rev = fr.fetch_symbol_report("600519.SS", sections=("财务报告", "管理层讨论与分析"), max_chars=100)
        assert rev["content"] == "B段\n\nA段"

    def test_multi_section_skips_missing(self, monkeypatch):
        """某章节未命中（None 或空正文）时跳过，其余照常拼接。"""
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: [{"id": 7}])
        parts = {"管理层讨论与分析": "A段", "财务报告": ""}
        monkeypatch.setattr(
            fr, "_fetch_document", lambda doc_id, section: {"doc_id": doc_id, "content": parts.get(section, "")}
        )
        rec = fr.fetch_symbol_report("600519.SS", sections=("管理层讨论与分析", "财务报告"), max_chars=100)
        assert rec["content"] == "A段"

    def test_all_sections_missing_returns_none(self, monkeypatch):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: [{"id": 7}])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section: {"doc_id": doc_id, "content": "  "})
        assert fr.fetch_symbol_report("600519.SS", sections=("管理层讨论与分析", "财务报告")) is None


class TestDatasinkUsageMarking:
    """取数链路须打「本次取用」标记（数据源说明表「本次使用」列的数据来源）。"""

    def _keys(self):
        from src.python.report.data_status import get_tracker

        return [e["source_key"] for e in get_tracker().get_log()]

    def test_index_fetch_marks_used(self, monkeypatch):
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(
            fr, "datasink", type("D", (), {"fetch_report_documents": staticmethod(lambda *a, **k: [{"id": 1}])})
        )
        assert fr._fetch_index("600900.SS", ("annual",)) == [{"id": 1}]
        assert "report_datasink_index" in self._keys()

    def test_index_cache_hit_marks_used(self, monkeypatch):
        """命中缓存也算「本次取用」（读者关心的是这次报告有没有用到该源）。"""
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: [{"id": 2}])
        assert fr._fetch_index("600900.SS", ("annual",)) == [{"id": 2}]
        assert "report_datasink_index" in self._keys()

    def test_index_miss_marks_nothing(self, monkeypatch):
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(
            fr, "datasink", type("D", (), {"fetch_report_documents": staticmethod(lambda *a, **k: None)})
        )
        assert fr._fetch_index("600900.SS", ("annual",)) is None
        assert self._keys() == []

    def test_document_fetch_marks_used(self, monkeypatch):
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "adapter_chain_slots", lambda domain: ({}, {}))
        monkeypatch.setattr(
            "src.python.fetcher.chain.fetch_with_fallback",
            lambda *a, **k: {"doc_id": 1, "content": "x"},
        )
        assert fr._fetch_document(1, "管理层讨论与分析") is not None
        assert "report_datasink_doc" in self._keys()

    def test_document_miss_marks_nothing(self, monkeypatch):
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "adapter_chain_slots", lambda domain: ({}, {}))
        monkeypatch.setattr("src.python.fetcher.chain.fetch_with_fallback", lambda *a, **k: None)
        assert fr._fetch_document(1, "管理层讨论与分析") is None
        assert self._keys() == []
