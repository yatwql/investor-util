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
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id: ["第三节管理层讨论与分析"])
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
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id: None)
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
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id: ["第三节 管理层讨论与分析"])
        monkeypatch.setattr(
            fr,
            "_fetch_document",
            lambda doc_id, section: (
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
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id: ["一、有限售条件股份", "二、无限售条件股份"])
        seen: list[str] = []

        def _doc(doc_id, section):
            seen.append(section)
            return {"doc_id": doc_id, "content": "正文"} if section == "管理层讨论与分析" else None

        monkeypatch.setattr(fr, "_fetch_document", _doc)
        rec = fr.fetch_symbol_report("601939.SS")
        assert rec is not None
        assert seen[0] == "管理层讨论与分析"
        assert rec["content"] == "正文"

    def test_failure_reasons(self, monkeypatch):
        """失败原因细分：索引无报告 / 目标章节缺失（附已试报告期）。"""
        self._patch_index(monkeypatch, [])
        monkeypatch.setattr(fr.datasink, "fetch_report_documents", lambda *a, **k: None)
        assert fr.fetch_symbol_report_detailed("601398.SS") == (None, fr.REASON_INDEX_EMPTY)

        self._patch_index(monkeypatch, [{"id": 1, "report_period": "2026-06-30"}])
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id: ["一、股份变动情况"])
        monkeypatch.setattr(fr, "_fetch_document", lambda doc_id, section: None)
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
        monkeypatch.setattr(fr, "_fetch_sections", lambda doc_id: ["第三节管理层讨论与分析"])
        seen: list[str] = []

        def _doc(doc_id, section):
            seen.append(section)
            return {"doc_id": doc_id, "content": "正文", "report_period": "2025-12-31", "doc_type": "annual"}

        monkeypatch.setattr(fr, "_fetch_document", _doc)
        assert fr.fetch_symbol_report("600900.SS") is not None
        assert seen == ["第三节管理层讨论与分析"]

    def test_missing_first_section_falls_through_to_next(self, monkeypatch):
        """首选项章节 404 → 继续试下一候选（不整只标的判失败）。"""
        self._index(monkeypatch, [{"id": 7, "doc_type": "annual", "report_period": "2025-12-31"}])
        monkeypatch.setattr(
            fr, "_fetch_sections", lambda doc_id: ["第三节管理层讨论与分析", "五、主要会计数据和财务指标"]
        )

        def _doc(doc_id, section):
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
