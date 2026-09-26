"""财报域适配器与备源接管测试。

覆盖：
  - 两源适配器均已登记且契约自检通过（域/标识/标准字段集）
  - **命名空间隔离**：异源 doc_id 不互相服务（主源适配器遇 cninfo 提示即拒；
    巨潮适配器无 ``source_hint`` 即拒）
  - 巨潮适配器章节切片：关键词命中、跳过目录行、未命中返回 None（交链路降级）
  - 标准字段归一（源身份由适配器提供，不受上游自报影响）
  - **编排层接管**：主源索引空 → 巨潮索引；**主源可用时巨潮完全不被调用**（红线）
  - 主源可用时输出逐字不变（同一夹具下与不接入备源时的记录等价）
  - **链槽位覆盖**（回归）：财报域链上必须同时含主源与备源槽，备源候选经**真实链路**可被服务

运行：pytest src/test/unit/fetcher/test_report_backup_source.py -v
"""

from __future__ import annotations

import pytest

import src.python.fetcher.financial_report as fr
from src.python.fetcher.financial_report import DOC_PREFIX
from src.python.fetcher.chain import _DEFAULT_CHAINS, _get_chain, fetch_with_fallback
from src.python.fetcher.report_adapters import CninfoReportAdapter, DataSinkReportAdapter
from src.python.fetcher.report_locate import is_toc_line as _is_toc_line
from src.python.fetcher.source_adapter import (
    ADAPTER_REGISTRY,
    adapter_chain_slots,
    get_adapters,
)
from src.python.providers import cninfo, datasink
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_REPORT

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

#: 链名集合（取自链注册表，不写死清单）
_CHAIN_KEYS = frozenset(_DEFAULT_CHAINS)


def get_adapters_all_domains() -> list[str]:
    """全部已登记适配器的域名（不写死清单）。"""
    return list(ADAPTER_REGISTRY)


_TEXT = (
    "第一节 重要提示\n"
    "本行含 管理层讨论与分析 ...... 12\n"  # 目录行：须跳过
    "\n"
    "第三节 管理层讨论与分析\n"
    "报告期内公司经营稳健，营业收入同比增长。\n" + "详述内容。" * 40
)


class TestAdapterRegistration:
    """两源适配器登记与契约自检。"""

    def test_both_sources_registered(self):
        adapters = get_adapters(DOMAIN_FINANCIAL_REPORT)
        assert set(adapters) == {datasink.SOURCE_ID, cninfo.SOURCE_ID}

    def test_contract_self_test_passes(self):
        for adapter in get_adapters(DOMAIN_FINANCIAL_REPORT).values():
            assert adapter.self_test() == []

    def test_identity_fields_forced(self):
        """源身份由适配器提供：上游自报 source 不得覆盖链路标签。"""
        raw = {
            "doc_id": "1",
            "content": "x",
            "source": "伪造来源",
            "source_api": "fake",
        }
        out = CninfoReportAdapter().transform_data(raw, cninfo.DISPLAY_NAME)
        assert out["source"] == cninfo.DISPLAY_NAME
        assert out["source_api"] == cninfo.SOURCE_ID


class TestNamespaceIsolation:
    """异源 doc_id 不互相服务（防跨源请求与缓存串扰）。"""

    def test_primary_rejects_foreign_hint(self, monkeypatch):
        called: list = []
        monkeypatch.setattr(fr.datasink, "fetch_report_document", lambda *a, **k: called.append(a) or {"content": "x"})
        assert DataSinkReportAdapter().extract_data({"doc_id": "1001", "source_hint": cninfo.SOURCE_ID}) is None
        assert called == []

    def test_primary_serves_without_hint(self, monkeypatch):
        monkeypatch.setattr(
            fr.datasink, "fetch_report_document", lambda doc_id, section: {"content": f"{doc_id}/{section}"}
        )
        assert DataSinkReportAdapter().extract_data({"doc_id": 7, "section": "s"}) == {"content": "7/s"}

    def test_cninfo_rejects_missing_hint(self, monkeypatch):
        called: list = []
        monkeypatch.setattr(cninfo, "fetch_report_text", lambda *a, **k: called.append(a) or "text")
        assert CninfoReportAdapter().extract_data({"doc_id": "1001", "section": "s"}) is None
        assert called == []


class TestCninfoSectionExtraction:
    """巨潮正文切片：关键词定位 + 目录行跳过 + 未命中降级。"""

    @staticmethod
    def _query(section: str, adjunct: str = "a.PDF") -> dict:
        return {
            "source_hint": cninfo.SOURCE_ID,
            "doc_id": "1001",
            "section": section,
            "meta": {
                "adjunct_url": adjunct,
                "title": "2025年年度报告",
                "report_period": "2025-12-31",
                "doc_type": "annual",
                "announcement_time": 1774656000000,
            },
        }

    def test_locates_section_skipping_toc(self, monkeypatch):
        monkeypatch.setattr(cninfo, "fetch_report_text", lambda *a, **k: _TEXT)
        raw = CninfoReportAdapter().extract_data(self._query("管理层讨论与分析"))
        assert raw is not None
        # 目录行被跳过：切片的起始处不是目录行（仅目录行含点线引导）
        assert not _is_toc_line(raw["content"], 0)
        # 命中的是正文那一次（正文行不含点线），而非目录行
        assert "...." not in raw["content"].split("\n", 1)[0]
        assert "报告期内公司经营稳健" in raw["content"]

    def test_missing_section_returns_none(self, monkeypatch):
        """关键词未命中 → None（链路继续下一偏好/候选，不产出空正文）。"""
        monkeypatch.setattr(cninfo, "fetch_report_text", lambda *a, **k: "无相关章节的正文")
        assert CninfoReportAdapter().extract_data(self._query("管理层讨论与分析")) is None

    def test_fulltext_query_capped(self, monkeypatch):
        monkeypatch.setattr(cninfo, "fetch_report_text", lambda *a, **k: "长" * (cninfo.FULLTEXT_CAP + 500))
        raw = CninfoReportAdapter().extract_data(self._query(""))
        assert raw is not None and len(raw["content"]) == cninfo.FULLTEXT_CAP

    def test_no_text_returns_none(self, monkeypatch):
        monkeypatch.setattr(cninfo, "fetch_report_text", lambda *a, **k: "")
        assert CninfoReportAdapter().extract_data(self._query("管理层讨论与分析")) is None

    def test_record_fields_from_meta(self, monkeypatch):
        monkeypatch.setattr(cninfo, "fetch_report_text", lambda *a, **k: _TEXT)
        raw = CninfoReportAdapter().extract_data(self._query("管理层讨论与分析"))
        assert raw["doc_type"] == "annual"
        assert raw["report_period"] == "2025-12-31"
        assert raw["title"] == "2025年年度报告"
        assert raw["adjunct_url"] == "a.PDF"


class TestOrchestrationTakeover:
    """编排层接管语义：主源空 → 巨潮；主源可用 → 巨潮零调用（红线）。"""

    def _isolate_cache(self, monkeypatch):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)

    def test_primary_index_empty_triggers_cninfo(self, monkeypatch):
        self._isolate_cache(monkeypatch)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: None)
        cn_calls: list = []
        monkeypatch.setattr(
            fr.cninfo,
            "fetch_report_listings",
            lambda code: (
                cn_calls.append(code)
                or [
                    {
                        "id": "1001",
                        "doc_type": "annual",
                        "report_period": "2025-12-31",
                        "title": "t",
                        "source": "cninfo",
                    }
                ]
            ),
        )
        items = fr._fetch_index("601398.SS")
        assert cn_calls == ["601398"]
        assert items and items[0]["id"] == "1001"

    def test_primary_available_means_cninfo_untouched(self, monkeypatch):
        """主源有索引时备源完全不被调用（主源输出不变的强约束）。"""
        self._isolate_cache(monkeypatch)
        monkeypatch.setattr(
            fr.datasink,
            "fetch_report_documents",
            lambda *a, **k: [{"id": 7, "doc_type": "annual", "report_period": "2025-12-31", "title": "t"}],
        )
        cn_calls: list = []
        monkeypatch.setattr(fr.cninfo, "fetch_report_listings", lambda code: cn_calls.append(code) or [])
        items = fr._fetch_index("601398.SS")
        assert cn_calls == []
        assert items and items[0]["id"] == 7

    def test_cninfo_candidate_threads_source_into_document_fetch(self, monkeypatch, tmp_path):
        """巨潮候选的读取带 source_hint 与 meta，且走独立缓存键段（防跨源碰撞）。"""
        self._isolate_cache(monkeypatch)
        seen: list = []

        def _fake_chain(data_type, provider_map, cache_key, ttl, fn_kwargs=None, transform=None):
            seen.append((cache_key, fn_kwargs))
            return {
                "doc_id": 1001,
                "content": "正文",
                "report_period": "2025-12-31",
                "doc_type": "annual",
                "title": "t",
            }

        monkeypatch.setattr("src.python.fetcher.chain.fetch_with_fallback", _fake_chain)
        meta = {"id": "1001", "source": "cninfo", "adjunct_url": "a.PDF", "title": "t"}
        record = fr._fetch_document("1001", "管理层讨论与分析", source="cninfo", meta=meta)
        assert record and record["content"] == "正文"
        cache_key, kwargs = seen[0]
        assert cache_key.startswith(f"{fr.DOC_PREFIX}{cninfo.SOURCE_ID}_")
        assert kwargs["source_hint"] == cninfo.SOURCE_ID
        assert kwargs["meta"]["adjunct_url"] == "a.PDF"

    def test_primary_document_failure_triggers_cninfo_body_takeover(self, monkeypatch):
        """主源**索引正常但正文不可得** → 巨潮备源按同一符号取正文（回归：正文无备源）。

        回归背景：备源原本只在「索引为空」时接管；主源索引正常而正文取数失败
        （断连/配额耗尽/章节残缺）时无任何退路。
        """
        self._isolate_cache(monkeypatch)
        monkeypatch.setattr(
            fr.datasink,
            "fetch_report_documents",
            lambda *a, **k: [{"id": 7, "doc_type": "annual", "report_period": "2025-12-31", "title": "主源"}],
        )
        cn_calls: list = []
        monkeypatch.setattr(
            fr.cninfo,
            "fetch_report_listings",
            lambda code: (
                cn_calls.append(code)
                or [
                    {
                        "id": "1001",
                        "doc_type": "annual",
                        "report_period": "2025-12-31",
                        "title": "巨潮",
                        "source": cninfo.SOURCE_ID,
                    }
                ]
            ),
        )

        # 主源文档取数全失败（源侧章节残缺）；巨潮候选命中正文
        def _fake_chain(data_type, provider_map, cache_key, ttl, fn_kwargs=None, transform=None):
            if fn_kwargs and fn_kwargs.get("source_hint") == cninfo.SOURCE_ID:
                return {
                    "doc_id": "1001",
                    "content": "第三节 管理层讨论与分析\n报告期内经营稳健。",
                    "report_period": "2025-12-31",
                    "doc_type": "annual",
                }
            return None

        monkeypatch.setattr("src.python.fetcher.chain.fetch_with_fallback", _fake_chain)
        monkeypatch.setattr(fr, "_fetch_sections", lambda *a, **k: None)

        record, reason = fr.fetch_symbol_report_detailed("601398.SS")
        assert cn_calls == ["601398"], "主源正文失败后应调用巨潮备源"
        assert record is not None and reason == ""
        assert record["doc_id"] == "1001", "应由巨潮备源交付"
        assert "管理层讨论与分析" in record["content"]

    def test_primary_document_ok_means_cninfo_untouched(self, monkeypatch):
        """主源正文可得时巨潮零调用（主源可用 → 各源零影响的强约束）。"""
        self._isolate_cache(monkeypatch)
        monkeypatch.setattr(
            fr.datasink,
            "fetch_report_documents",
            lambda *a, **k: [{"id": 7, "doc_type": "annual", "report_period": "2025-12-31", "title": "主源"}],
        )
        cn_calls: list = []
        monkeypatch.setattr(fr.cninfo, "fetch_report_listings", lambda code: cn_calls.append(code) or [])

        def _fake_chain(data_type, provider_map, cache_key, ttl, fn_kwargs=None, transform=None):
            return {
                "doc_id": 7,
                "content": "第三节 管理层讨论与分析\n报告期内经营稳健。",
                "report_period": "2025-12-31",
                "doc_type": "annual",
            }

        monkeypatch.setattr("src.python.fetcher.chain.fetch_with_fallback", _fake_chain)
        monkeypatch.setattr(fr, "_fetch_sections", lambda *a, **k: None)
        monkeypatch.setattr(fr, "_fetch_document", lambda *a, **k: _fake_chain(None, None, None, None))

        record, reason = fr.fetch_symbol_report_detailed("601398.SS")
        assert record is not None and reason == ""
        assert cn_calls == [], "主源正文可用时不得调用备源"

    def test_both_sources_failing_reports_periods(self, monkeypatch):
        """主备正文均不可得 → 原因文案含已试报告期，不静默失败。"""
        self._isolate_cache(monkeypatch)
        monkeypatch.setattr(
            fr.datasink,
            "fetch_report_documents",
            lambda *a, **k: [{"id": 7, "doc_type": "annual", "report_period": "2025-12-31", "title": "主源"}],
        )
        monkeypatch.setattr(
            fr.cninfo,
            "fetch_report_listings",
            lambda code: [
                {
                    "id": "1001",
                    "doc_type": "annual",
                    "report_period": "2024-12-31",
                    "title": "巨潮",
                    "source": cninfo.SOURCE_ID,
                }
            ],
        )
        monkeypatch.setattr("src.python.fetcher.chain.fetch_with_fallback", lambda *a, **k: None)
        record, reason = fr.fetch_symbol_report_detailed("601398.SS")
        assert record is None
        assert "2025-12-31" in reason and "2024-12-31" in reason

    def test_primary_document_cache_key_unchanged(self, monkeypatch):
        """主源候选仍用原缓存键（不因接入备源而使既有缓存失效）。"""
        self._isolate_cache(monkeypatch)
        seen: list = []
        monkeypatch.setattr(
            "src.python.fetcher.chain.fetch_with_fallback",
            lambda data_type, provider_map, cache_key, ttl, fn_kwargs=None, transform=None: seen.append(cache_key),
        )
        fr._fetch_document(7, "管理层讨论与分析", source=None, meta=None)
        assert seen[0] == f"{fr.DOC_PREFIX}7_管理层讨论与分析"

    def test_fulltext_ladder_uses_source(self, monkeypatch):
        """全文兜底阶同样透传来源（巨潮候选不落主源命名空间）。"""
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id: None)
        seen: list = []

        def _fake_fetch(doc_id, section, source=None, meta=None):
            seen.append((section, source))
            return {"content": "董事会报告 正文段落"}

        monkeypatch.setattr(fr, "_fetch_document", _fake_fetch)
        record, contents = fr._collect_doc_sections(1001, ["董事会报告"], source="cninfo", meta={"id": "1001"})
        assert contents and seen[0][1] == "cninfo"


class TestChainSlotCoverage:
    """回归：财报域链的槽位必须覆盖全部已登记适配器源。

    缺陷背景：plan-50 加入巨潮备源**适配器**后，``_DEFAULT_CHAINS["financial_report"]``
    仍是单槽 ``["datasink"]``。而 ``fetch_with_fallback`` 的**遍历列表**取自
    ``_get_chain(data_type)``（provider 映射则来自适配器注册表）——链上缺 cninfo 槽时，
    带 ``source_hint=cninfo`` 的备源候选在主源槽上被适配器按命名空间拒服务（零请求、
    零日志）后无处可去 → 必落“全链路失败”，备源正文实际永远取不到。
    日志表现：反复的“尝试 DataSinking 财报 → datasink 返回空 → 全链路失败”三连，
    且整个日志里**没有任何 ``[datasink]`` 请求日志**（根本没发出过请求）。
    """

    def test_all_report_adapter_sources_are_chain_slots(self):
        """财报域：适配器注册的每个源都必须在链上（含备源 cninfo）。"""
        assert set(get_adapters(DOMAIN_FINANCIAL_REPORT)) <= set(_get_chain("financial_report"))

    def test_single_chain_domains_cover_their_adapters(self):
        """通用不变式：凡“域名即链名”的域，其适配器源必须被本链槽位覆盖。

        ``quote`` 例外——它的适配器服务 ``price_stock`` / ``price_fund_otc`` / ``price``
        三条链（域名与链名不同），故不适用本不变式；其覆盖由行情域测试单独保证。
        """
        loaded = {domain for domain in get_adapters_all_domains() if domain in _CHAIN_KEYS}
        assert loaded, "适配器域与链名的交集不应为空"
        for domain in sorted(loaded):
            missing = set(get_adapters(domain)) - set(_get_chain(domain))
            assert not missing, f"{domain} 链上缺槽：{sorted(missing)}"

    def test_backup_candidate_served_through_real_chain(self, monkeypatch):
        """备源候选经**真实链路**（不 mock fetch_with_fallback）能被服务。"""
        monkeypatch.setattr(cninfo, "fetch_report_text", lambda *_a, **_k: _TEXT)
        monkeypatch.setattr("src.python.fetcher.chain.cache_get", lambda *_a, **_k: None)
        monkeypatch.setattr("src.python.fetcher.chain.cache_set", lambda *_a, **_k: None)
        provider_map, transform_map = adapter_chain_slots(DOMAIN_FINANCIAL_REPORT)

        record = fetch_with_fallback(
            "financial_report",
            provider_map,
            f"{DOC_PREFIX}cninfo_1001_管理层讨论与分析",
            3600,
            fn_kwargs={
                "doc_id": "1001",
                "section": "管理层讨论与分析",
                "source_hint": cninfo.SOURCE_ID,
                "meta": {"symbol": "600900.SS", "stock_name": "长江电力", "title": "2025年年度报告"},
            },
            transform=transform_map,
        )

        assert record is not None, "备源候选应经链路被 cninfo 适配器服务"
        assert record["source_api"] == cninfo.SOURCE_ID
        assert "报告期内公司经营稳健" in record["content"]

    def test_foreign_hint_still_rejected_by_primary_slot(self, monkeypatch):
        """主源槽仍在备源候选上按命名空间拒服务（不发起无效请求）。"""
        called: list = []
        monkeypatch.setattr(
            datasink,
            "fetch_report_document",
            lambda *a, **k: called.append(a) or {"content": "不应被调用"},
        )
        assert DataSinkReportAdapter().extract_data({"doc_id": "1001", "source_hint": cninfo.SOURCE_ID}) is None
        assert called == []
