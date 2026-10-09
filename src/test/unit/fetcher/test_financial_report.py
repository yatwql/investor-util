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

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher, pytest.mark.usefixtures("offline_external_sources")]


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

    def test_merges_penetrated_targets_with_name_and_sources(self):
        """穿透标的带中文名与来源基金（展示层据此回填名称并标注穿透来源）。"""
        holdings = [SimpleNamespace(code="600519", name="贵州茅台")]
        targets = fr.collect_a_share_targets(
            holdings,
            [
                {"code": "300274", "name": "阳光电源", "sources": ["[ETF] 招商中证电池主题ETF(561910)"]},
                "AAPL",  # 非 A 股
            ],
        )
        assert [t["code"] for t in targets] == ["300274", "600519"]
        assert targets[0]["symbol"] == "300274.SZ"
        assert targets[0]["name"] == "阳光电源"
        assert targets[0]["kind"] == "penetrated"
        assert targets[0]["sources"] == ["[ETF] 招商中证电池主题ETF(561910)"]
        assert targets[1]["kind"] == "holding"
        assert targets[1]["sources"] == ["直接持有"]

    def test_bare_penetrated_code_keeps_name_empty(self):
        """裸代码（旧形态）仍可用：名称为空，展示层回退 symbol。"""
        targets = fr.collect_a_share_targets([], ["300750"])
        assert targets[0]["name"] == ""
        assert targets[0]["kind"] == "penetrated"

    def test_direct_holding_wins_over_penetrated(self):
        """同代码既是持仓又在穿透层时按持仓计（来源记「直接持有」）。"""
        holdings = [SimpleNamespace(code="600900", name="长江电力")]
        targets = fr.collect_a_share_targets(holdings, [{"code": "600900", "name": "长江电力", "sources": ["[ETF] X"]}])
        assert len(targets) == 1
        assert targets[0]["kind"] == "holding"

    def test_otc_fund_code_excluded_from_a_share_targets(self):
        """场外基金代码落在 00 重叠区时不取个股财报（002943 基金 ≠ 002943.SZ 股票）。

        现场：持仓「广发多因子灵活配置混合」(002943) 被判为深市 A 股，
        表格里出现该基金名 + 深市股票 002943.SZ 宇晶股份的半年报（张冠李戴）。
        """
        fund = SimpleNamespace(code="002943", name="广发多因子灵活配置混合")
        assert fr.collect_a_share_targets([fund]) == []
        stock = SimpleNamespace(code="002943", name="宇晶股份")
        assert [t["code"] for t in fr.collect_a_share_targets([stock])] == ["002943"]

    def test_empty(self):
        assert fr.collect_a_share_targets([]) == []

    def test_target_source_label(self):
        """来源标签：持仓「直接持有」；穿透拼接来源基金，超过 2 个以「…」略去。"""
        assert fr.target_source_label({"kind": "holding", "sources": ["直接持有"]}) == "直接持有"
        assert fr.target_source_label({"kind": "penetrated", "sources": []}) == "穿透"
        one = fr.target_source_label({"kind": "penetrated", "sources": ["[ETF] A"]})
        assert one == "穿透：[ETF] A"
        many = fr.target_source_label({"kind": "penetrated", "sources": ["A", "B", "C"]})
        assert many == "穿透：A；B…"


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
            lambda symbol, **k: [{"id": 7, "report_period": "2025-12-31", "doc_type": "annual"}],
        )
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["第三节管理层讨论与分析"])
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section, **_kw: {
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
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: None)
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": "x"})
        rec = fr.fetch_symbol_report("600519.SS")
        assert rec is not None and rec["doc_id"] == 9
        assert calls == []

    def test_document_miss_returns_none(self, monkeypatch):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: [{"id": 7}])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section, **_kw: None)
        assert fr.fetch_symbol_report("600519.SS") is None

    def test_multi_section_concatenation_order(self, monkeypatch):
        """多章节按声明顺序拼接（各节正文以空行分隔），元数据取首个非空记录。"""
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: [{"id": 7}])
        parts = {"管理层讨论与分析": "A段", "财务报告": "B段"}
        monkeypatch.setattr(
            fr, "_fetch_document", lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": parts.get(section, "")}
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
            fr, "_fetch_document", lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": parts.get(section, "")}
        )
        rec = fr.fetch_symbol_report("600519.SS", sections=("管理层讨论与分析", "财务报告"), max_chars=100)
        assert rec["content"] == "A段"

    def test_all_sections_missing_returns_none(self, monkeypatch):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: [{"id": 7}])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": "  "})
        assert fr.fetch_symbol_report("600519.SS", sections=("管理层讨论与分析", "财务报告")) is None


class TestTransportFailureDegradation:
    """传输级失败（连接级重试已耗尽而上抛）在编排层的降级行为。

    主源抛异常不得中断整只标的取数：索引失败 → 转巨潮备源；章节清单失败 → 回退偏好名直取。
    """

    def test_index_transport_failure_falls_back_to_cninfo(self, monkeypatch):
        import httpx

        def _boom(*_a, **_kw):
            raise httpx.ConnectTimeout("handshake operation timed out")

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", _boom)
        monkeypatch.setattr(
            fr.cninfo,
            "fetch_report_listings",
            lambda code, **_kw: [{"id": 11, "report_period": "2026-06-30", "source": "cninfo"}],
        )
        items = fr._fetch_index("600519.SS")
        assert items is not None
        assert [i["id"] for i in items] == [11]

    def test_sections_transport_failure_returns_none(self, monkeypatch, caplog):
        import httpx

        def _boom(*_a, **_kw):
            raise httpx.ConnectTimeout("handshake operation timed out")

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_sections", _boom)
        assert fr._fetch_sections(123) is None
        assert any("章节清单取数失败" in r.message for r in caplog.records)


class TestReportPeriodBacktrack:
    """最新报告缺目标章节时回溯上一份（银行股半年报缺「管理层讨论与分析」）。"""

    def _patch_index(self, monkeypatch, items):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: items)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)

    def test_backtrack_to_earlier_report(self, monkeypatch):
        """最新半年报无正文 → 回溯一季报 → 上年年报命中，报告期如实为年报。"""
        self._patch_index(
            monkeypatch,
            [
                {"id": 1, "report_period": "2026-06-30", "doc_type": "semiannual"},
                {"id": 2, "report_period": "2026-03-31", "doc_type": "q1"},
                {"id": 3, "report_period": "2025-12-31", "doc_type": "annual"},
            ],
        )
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["第三节 管理层讨论与分析"])
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section, **_kw: (
                {"doc_id": 3, "report_period": "2025-12-31", "doc_type": "annual", "content": "年报正文"}
                if doc_id == 3
                else None
            ),
        )
        rec = fr.fetch_symbol_report("601939.SS")
        assert rec is not None
        assert rec["report_period"] == "2025-12-31"
        assert rec["doc_type"] == "annual"
        assert rec["content"] == "年报正文"

    def test_degenerate_section_list_falls_back_to_direct_names(self, monkeypatch):
        """章节清单非空但残缺（只有无关章节）时回退偏好名直取，不白丢整篇。"""
        self._patch_index(monkeypatch, [{"id": 810006, "report_period": "2026-06-30"}])
        monkeypatch.setattr(
            fr, "_fetch_sections", lambda doc_id, source=None: ["一、有限售条件股份", "二、无限售条件股份"]
        )
        seen: list[str] = []

        def _doc(doc_id, section, **_kw):
            seen.append(section)
            return {"doc_id": doc_id, "content": "正文"} if section == "管理层讨论与分析" else None

        monkeypatch.setattr(fr, "_fetch_document", _doc)
        rec = fr.fetch_symbol_report("601939.SS")
        assert rec is not None
        assert seen[0] == "管理层讨论与分析"
        assert rec["content"] == "正文"

    def test_annual_preferred_over_newer_quarterly(self, monkeypatch):
        """年报/半年报优先于更新的季报（季报无「管理层讨论与分析」，先试它是白跑）。"""
        self._patch_index(
            monkeypatch,
            [
                {"id": 1, "report_period": "2026-03-31", "doc_type": "q1"},  # 最新
                {"id": 2, "report_period": "2025-12-31", "doc_type": "annual"},
            ],
        )
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["第三节 管理层讨论与分析"])
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section, **_kw: {"doc_id": doc_id, "report_period": str(doc_id), "content": f"doc{doc_id}"},
        )
        rec = fr.fetch_symbol_report("601939.SS")
        assert rec["doc_id"] == 2  # 年报先试（即便一季报更新）

    def test_notice_document_skipped(self, monkeypatch):
        """标题含「公告」的条目是信息披露公告，不是财报正文（索引里混排）。"""
        self._patch_index(
            monkeypatch,
            [
                {
                    "id": 1,
                    "report_period": "2026-03-31",
                    "doc_type": "q1",
                    "title": "关于变更2026年第一季度报告预约披露时间的公告",
                },
                {"id": 2, "report_period": "2025-12-31", "doc_type": "annual", "title": "某行2025年度报告"},
            ],
        )
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["第三节 管理层讨论与分析"])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": "正文"})
        rec = fr.fetch_symbol_report("601939.SS")
        assert rec["doc_id"] == 2

    def test_fulltext_fallback_locates_keyword(self, monkeypatch):
        """章节阶全失败 → 整篇下载后按偏好关键词定位片段（不取封面/目录）。"""
        self._patch_index(monkeypatch, [{"id": 9, "report_period": "2025-12-31", "doc_type": "annual"}])
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["附件"])
        full = "封面：某行2025年度报告\n公司简介……\n主要财务数据\n营业收入 100 亿元"
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": full} if section == "" else None,
        )
        rec = fr.fetch_symbol_report("601398.SS", max_chars=40)
        assert rec is not None
        assert rec["section_source"] == fr.SECTION_SOURCE_FULLTEXT
        assert rec["summary"].startswith("主要财务数据")
        assert "封面" not in rec["summary"]

    def test_fulltext_fallback_skips_toc_occurrence(self, monkeypatch):
        """关键词首次命中在目录行（点线引导）时跳到正文那一次，不把目录当摘要。"""
        self._patch_index(monkeypatch, [{"id": 9, "report_period": "2025-12-31", "doc_type": "annual"}])
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["附件"])
        full = (
            "目录\n董事会报告 ................................ 12\n第一章 公司简介\n"
            "董事会报告\n主要业务：提供银行及相关金融服务\n利润及股息分配……"
        )
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": full} if section == "" else None,
        )
        rec = fr.fetch_symbol_report("601398.SS", max_chars=30)
        assert rec["summary"].startswith("董事会报告\n主要业务")
        assert "........" not in rec["summary"]

    def test_fulltext_fallback_head_when_no_keyword(self, monkeypatch):
        """全文里没有任何偏好关键词 → 退化为正文开头片段（仍有内容，不判失败）。"""
        self._patch_index(monkeypatch, [{"id": 9, "report_period": "2025-12-31", "doc_type": "annual"}])
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["附件"])
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": "公司简介正文"} if section == "" else None,
        )
        rec = fr.fetch_symbol_report("601398.SS", max_chars=10)
        assert rec["summary"] == "公司简介正文"
        assert rec["section_source"] == fr.SECTION_SOURCE_FULLTEXT

    def test_sections_hit_marks_section_source(self, monkeypatch):
        """章节阶命中时标记取用方式为 sections（排查时区分两阶）。"""
        self._patch_index(monkeypatch, [{"id": 1, "report_period": "2025-12-31", "doc_type": "annual"}])
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["第三节 管理层讨论与分析"])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section, **_kw: {"doc_id": doc_id, "content": "正文"})
        rec = fr.fetch_symbol_report("600900.SS")
        assert rec["section_source"] == fr.SECTION_SOURCE_SECTIONS

    def test_failure_reasons(self, monkeypatch):
        """失败原因细分：索引无报告 / 目标章节缺失（附已试报告期）。"""
        self._patch_index(monkeypatch, [])
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: None)
        assert fr.fetch_symbol_report_detailed("601398.SS") == (None, fr.REASON_INDEX_EMPTY)

        self._patch_index(monkeypatch, [{"id": 1, "report_period": "2026-06-30"}])
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["一、股份变动情况"])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section, **_kw: None)
        rec, reason = fr.fetch_symbol_report_detailed("601398.SS")
        assert rec is None
        assert "2026-06-30" in reason
        assert reason.startswith("目标章节缺失")


class TestDatasinkUsageMarking:
    """取数链路须打「本次取用」标记（数据源说明表「本次使用」列的数据来源）。"""

    def _keys(self):
        from src.python.report.data_status import get_tracker

        return [e["source_key"] for e in get_tracker().get_log()]

    def test_index_fetch_marks_used(self, monkeypatch):
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(
            fr,
            "datasink",
            type(
                "D",
                (),
                {
                    "fetch_report_documents": staticmethod(
                        lambda *a, **k: [{"id": 1, "doc_type": "annual", "report_period": "2025-12-31"}]
                    )
                },
            ),
        )
        assert fr._fetch_index("600900.SS", ("annual",)) == [
            {"id": 1, "doc_type": "annual", "report_period": "2025-12-31"}
        ]
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


class TestLatestPeriodAndSectionResolution:
    """取最新报告期（跨文种）与按实际章节名精确取正文。"""

    def _index(self, monkeypatch, items):
        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda symbol, **k: list(items))

    def test_latest_period_wins_over_annual(self, monkeypatch):
        """半年报（2026-06-30）比年报（2025-12-31）新 → 取半年报，不再「年报优先」。"""
        self._index(
            monkeypatch,
            [
                {"id": 59797, "doc_type": "annual", "report_period": "2025-12-31"},
                {"id": 818577, "doc_type": "semiannual", "report_period": "2026-06-30"},
                {"id": 59795, "doc_type": "q1", "report_period": "2026-03-31"},
            ],
        )
        picked = fr._fetch_index("600900.SS")
        assert [i["id"] for i in picked] == [818577, 59795, 59797]

    def test_doc_types_whitelist_filters(self, monkeypatch):
        """配置文种白名单非空时仅保留该类（可限定只取年报等）。"""
        self._index(
            monkeypatch,
            [
                {"id": 1, "doc_type": "annual", "report_period": "2025-12-31"},
                {"id": 2, "doc_type": "semiannual", "report_period": "2026-06-30"},
            ],
        )
        assert [i["id"] for i in fr._fetch_index("600900.SS", ("annual",))] == [1]

    def test_whitelist_without_match_returns_none(self, monkeypatch):
        self._index(monkeypatch, [{"id": 1, "doc_type": "annual", "report_period": "2025-12-31"}])
        assert fr._fetch_index("600900.SS", ("q3",)) is None

    def test_pick_sections_matches_actual_names(self):
        available = [
            "公司代码：600900公司简称：长江电力",
            "第三节管理层讨论与分析",
            "第八节财务报告",
            "五、主要会计数据和财务指标",
        ]
        assert fr._pick_sections(available, ("管理层讨论与分析", "主要会计数据")) == [
            "第三节管理层讨论与分析",
            "五、主要会计数据和财务指标",
        ]

    def test_pick_sections_dedups_and_keeps_preference_order(self):
        available = ["第三节管理层讨论与分析", "五、主要会计数据和财务指标"]
        picked = fr._pick_sections(available, ("主要会计数据", "管理层讨论与分析"))
        assert picked == ["五、主要会计数据和财务指标", "第三节管理层讨论与分析"]
        # 同一章节不被两个偏好重复取用
        assert fr._pick_sections(available, ("管理层讨论与分析", "管理层讨论与分析")) == ["第三节管理层讨论与分析"]

    def test_pick_sections_falls_back_to_preferences(self):
        assert fr._pick_sections(None, ("管理层讨论与分析",)) == ["管理层讨论与分析"]

    def test_uses_exact_section_name_from_list(self, monkeypatch):
        """按实际章节名（第三节管理层讨论与分析）请求正文，而非硬编码裸名。"""
        self._index(monkeypatch, [{"id": 7, "doc_type": "annual", "report_period": "2025-12-31"}])
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id, source=None: ["第三节管理层讨论与分析"])
        seen: list[str] = []

        def _doc(doc_id, section, **_kw):
            seen.append(section)
            return {"doc_id": doc_id, "content": "正文", "report_period": "2025-12-31", "doc_type": "annual"}

        monkeypatch.setattr(fr, "_fetch_document", _doc)
        assert fr.fetch_symbol_report("600900.SS") is not None
        assert seen == ["第三节管理层讨论与分析"]

    def test_missing_first_section_falls_through_to_next(self, monkeypatch):
        """首选项章节 404 → 继续试下一候选（不整只标的判失败）。"""
        self._index(monkeypatch, [{"id": 7, "doc_type": "annual", "report_period": "2025-12-31"}])
        monkeypatch.setattr(
            fr, "_fetch_sections", lambda doc_id, source=None: ["第三节管理层讨论与分析", "五、主要会计数据和财务指标"]
        )

        def _doc(doc_id, section, **_kw):
            if section == "第三节管理层讨论与分析":
                return None  # 模拟 404
            return {"doc_id": doc_id, "content": "财务数据", "report_period": "2025-12-31", "doc_type": "annual"}

        monkeypatch.setattr(fr, "_fetch_document", _doc)
        rec = fr.fetch_symbol_report("600900.SS")
        assert rec is not None and rec["content"] == "财务数据"

    def test_sections_list_is_cached(self, monkeypatch):
        """章节清单命中缓存不重复请求（清单本身是 1 次额外请求，必须缓存）。"""
        calls = {"n": 0}
        store: dict = {}

        def _sections(doc_id):
            calls["n"] += 1
            return ["第三节管理层讨论与分析"]

        monkeypatch.setattr(fr.datasink, "fetch_report_sections", _sections)
        monkeypatch.setattr(fr, "cache_get", lambda key, ttl=None: store.get(key))
        monkeypatch.setattr(fr, "cache_set", lambda key, value: store.__setitem__(key, value))
        assert fr._fetch_sections(7) == ["第三节管理层讨论与分析"]
        assert fr._fetch_sections(7) == ["第三节管理层讨论与分析"]
        assert calls["n"] == 1


class TestIndexSourceStatus:
    """索引来源归属与「两源皆失败」的降级登记（report_datasink_index 状态）。"""

    def _keys(self):
        from src.python.report.data_status import get_tracker

        return [e["source_key"] for e in get_tracker().get_log()]

    def _last_event(self, key):
        from src.python.report.data_status import get_tracker

        events = [e for e in get_tracker().get_log() if e["source_key"] == key]
        return events[-1] if events else None

    def test_cninfo_backup_labels_cninfo_source(self, monkeypatch):
        """主源空 → 巨潮备源接管时，「本次使用」如实记为巨潮。"""
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fr, "datasink", type("D", (), {"fetch_report_documents": staticmethod(lambda *a, **k: [])}))
        monkeypatch.setattr(
            fr,
            "cninfo",
            type(
                "C",
                (),
                {
                    "fetch_report_listings": staticmethod(
                        lambda code: [
                            {
                                "id": 9,
                                "doc_type": "annual",
                                "report_period": "2025-12-31",
                                "source": "cninfo",
                            }
                        ]
                    )
                },
            ),
        )
        picked = fr._fetch_index("600900.SS", ("annual",))
        assert picked and picked[0]["source"] == "cninfo"
        assert "report_cninfo_index" in self._keys()
        assert "report_datasink_index" not in self._keys()

    def test_index_cache_hit_labels_source_from_cache(self, monkeypatch):
        """缓存命中（条目来自巨潮）→ 仍如实记为巨潮，不误记主源。"""
        from src.python.fetcher import financial_report as fr

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: [{"id": 3, "source": "cninfo"}])
        fr._fetch_index("600900.SS", ("annual",))
        assert "report_cninfo_index" in self._keys()
        assert "report_datasink_index" not in self._keys()

    def test_both_sources_fail_records_degradation(self, monkeypatch):
        """主源异常且备源无命中 → 登记 report_datasink_index 失败且健康矩阵可见（可观测）。"""
        from src.python.fetcher import financial_report as fr
        from src.python.report.data_source_matrix import build_data_source_matrix

        def _boom(*a, **k):
            raise RuntimeError("connection reset")

        monkeypatch.setattr(fr, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fr, "datasink", type("D", (), {"fetch_report_documents": staticmethod(_boom)}))
        monkeypatch.setattr(fr, "cninfo", type("C", (), {"fetch_report_listings": staticmethod(lambda code: None)}))
        assert fr._fetch_index("600900.SS", ("annual",)) is None
        # ① 降级事件本身：source_key 正确、success=False（不再静默）
        event = self._last_event("report_datasink_index")
        assert event is not None and event["success"] is False
        # ② 事件在「财报全文」类别的健康矩阵行中可见（无论计为 failed 还是 degraded）
        row = next(r for r in build_data_source_matrix() if r["key"] == "financial_report")
        assert row["failed"] + row["degraded"] >= 1


class TestSourceNormalization:
    """候选来源归一与命名空间隔离（source_hint 根因回归：主源索引自由文本 source 直传
    source_hint 令两适配器双双静默拒服务，主源整条失效）。"""

    def test_datasink_free_text_normalizes_to_primary(self):
        """DataSinking 索引条目自带「巨潮资讯网 (cninfo)」自由文本 → 归一为主源 datasink。"""
        from src.python.fetcher import financial_report as fr

        assert fr._candidate_source({"source": "巨潮资讯网 (cninfo)"}) == "datasink"

    def test_exact_cninfo_literal_stays_backup(self):
        """cninfo provider 写入的精确字面量 → 备源 cninfo（备源接管语义不变）。"""
        from src.python.fetcher import financial_report as fr

        assert fr._candidate_source({"source": "cninfo"}) == "cninfo"

    def test_missing_or_other_text_defaults_to_primary(self):
        """无 source/其他自由文本 → 主源（宁可主源尝试，不得双槽同拒）。"""
        from src.python.fetcher import financial_report as fr

        assert fr._candidate_source({}) == "datasink"
        assert fr._candidate_source({"source": "DataSinking, Inc."}) == "datasink"

    def test_index_source_attribution_exact_match_only(self):
        """取用标记归属只认精确 cninfo：主源自由文本条目不得错记到备源名下。"""
        from src.python.fetcher import financial_report as fr

        assert fr._index_source_of([{"id": 1, "source": "巨潮资讯网 (cninfo)"}]) == fr._SRC_INDEX_DATASINK
        assert fr._index_source_of([{"id": 2, "source": "cninfo"}]) == fr._SRC_INDEX_CNINFO
        assert fr._index_source_of([{"id": 3}]) == fr._SRC_INDEX_DATASINK

    def test_sections_fetch_skipped_for_backup_source(self, monkeypatch):
        """章节清单仅主源提供：备源候选不打 datasink /sections（每轮 404 与历史挂起的次生根因）。"""
        from src.python.fetcher import financial_report as fr

        calls: list = []
        monkeypatch.setattr(fr.datasink, "fetch_report_sections", lambda d: calls.append(d) or ["节一"])

        assert fr._fetch_sections(999001001, source="cninfo") is None
        assert calls == [], "备源候选不得触发主源章节清单请求"

        assert fr._fetch_sections(999001002, source="datasink") == ["节一"]
        assert calls == [999001002]

    def test_fulltext_ladder_passes_source_and_meta(self, monkeypatch):
        """全文阶 _fetch_document 必须带 source/meta（漏传曾致单次生成 1 次跨源 404）。"""
        from src.python.fetcher import financial_report as fr

        seen: dict = {}

        def _fake_fetch(doc_id, section, source=None, meta=None):
            seen.update({"doc_id": doc_id, "source": source, "meta": meta})
            return {"doc_id": doc_id, "content": "全文内容"}

        monkeypatch.setattr(fr, "_fetch_document", _fake_fetch)
        monkeypatch.setattr(fr, "_locate_from_fulltext", lambda *a, **k: ("关键词片段", "关键词"))
        monkeypatch.setattr(fr, "_collect_doc_sections", lambda *a, **k: (None, []))

        meta = {"id": 555001, "source": "cninfo", "report_period": "2026-06-30"}
        result = fr._attempt_candidates([meta], "600000.SS", ["管理层讨论"], 1000, [])

        assert result is not None, "全文阶应命中"
        assert seen["source"] == "cninfo", "全文阶必须携带归一后的 source"
        assert seen["meta"]["id"] == 555001, "全文阶必须透传候选 meta"
