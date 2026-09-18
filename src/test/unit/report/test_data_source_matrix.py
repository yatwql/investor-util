"""build_data_source_matrix 单元测试。

测试目标：
  - degraded 事件 → degraded_list 正确填充
  - failed 事件 → sample_failures 正确填充
  - 混合 degraded + failed → 状态为 "degraded"，两种列表均填充
  - 无 degraded → degraded_list 为空
  - 无事件 → 返回空列表
  - 全失败 → status="failed"

运行：
  python -m pytest src/test/unit/report/test_data_source_matrix.py -v
"""

from __future__ import annotations

from typing import Any

import pytest

from src.python.report.data_status import (
    get_tracker,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestBuildDataSourceMatrixDegradedList:
    """build_data_source_matrix — degraded_list 字段（新增）。"""

    # ── 辅助 ─────────────────────────────────

    def _add_event(
        self,
        source_key: str,
        tier: str = "T2",
        success: bool = False,
        degraded: bool = False,
        failure_type: str = "unreachable",
    ) -> None:
        """向 DegradationTracker 注入一条 record 事件。"""
        t = get_tracker()
        t._events.append(
            t._make_event(
                source_key=source_key,
                tier=tier,
                success=success,
                failure_type=failure_type,
                degraded=degraded,
                count=1,
                effective_threshold=1,
                timestamp=1000.0,
            )
        )
        # 同步更新计数器（避免 _record_unsafe 影响，直接操作 _events）
        # 注：_make_event 是私有的——我们直接构造 DegradationEvent 对象

    def _add_raw_event(self, **kwargs) -> None:
        """向 DegradationTracker 注入一条 DegradationEvent。"""
        from src.python.report.data_status import DegradationEvent

        t = get_tracker()
        ev = DegradationEvent(**kwargs)
        t._events.append(ev)

    def _build(self) -> list[dict[str, Any]]:
        from src.python.report.data_source_matrix import build_data_source_matrix

        return build_data_source_matrix()

    # ── 测试用例 ─────────────────────────────

    def test_degraded_only_one_category(self):
        """单类别单条 degraded → degraded_list 含 1 项，sample_failures 空。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=True,
            count=3,
            effective_threshold=2,
            timestamp=1000.0,
        )
        matrix = self._build()
        assert len(matrix) >= 1
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["degraded"] == 1
        assert len(price_row["degraded_list"]) == 1
        assert "price_600900" in price_row["degraded_list"][0]
        assert price_row["failed"] == 0
        assert len(price_row["sample_failures"]) == 0
        assert price_row["status"] == "degraded"

    def test_failed_only(self):
        """单类别单条 failed（非 degraded）→ sample_failures 含 1 项，degraded_list 空。"""
        self._add_raw_event(
            source_key="price_000001",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=False,
            count=1,
            effective_threshold=2,
            timestamp=1000.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["failed"] == 1
        assert len(price_row["sample_failures"]) == 1
        assert price_row["degraded"] == 0
        assert len(price_row["degraded_list"]) == 0

    def test_mixed_degraded_and_failed(self):
        """同一类别有 1 ok + 1 degraded + 1 failed → 两种列表均填充，status='degraded'。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2",
            success=True,
            failure_type="unreachable",
            degraded=False,
            count=0,
            effective_threshold=0,
            timestamp=999.0,
        )
        self._add_raw_event(
            source_key="price_600519",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=True,
            count=3,
            effective_threshold=2,
            timestamp=1000.0,
        )
        self._add_raw_event(
            source_key="price_000001",
            tier="T2",
            success=False,
            failure_type="empty",
            degraded=False,
            count=1,
            effective_threshold=2,
            timestamp=1001.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["ok"] == 1
        assert price_row["degraded"] == 1
        assert price_row["failed"] == 1
        assert len(price_row["degraded_list"]) == 1
        assert len(price_row["sample_failures"]) == 1
        assert price_row["status"] == "degraded"

    def test_all_ok_no_degraded_list(self):
        """全部成功 → degraded_list 和 sample_failures 均为空。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2",
            success=True,
            failure_type="unreachable",
            degraded=False,
            count=0,
            effective_threshold=0,
            timestamp=1000.0,
        )
        self._add_raw_event(
            source_key="price_000001",
            tier="T2",
            success=True,
            failure_type="unreachable",
            degraded=False,
            count=0,
            effective_threshold=0,
            timestamp=1001.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["status"] == "ok"
        assert len(price_row["degraded_list"]) == 0
        assert len(price_row["sample_failures"]) == 0

    def test_multiple_degraded_same_category(self):
        """同一类别多条 degraded → degraded_list 含多项。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=True,
            count=3,
            effective_threshold=2,
            timestamp=1000.0,
        )
        self._add_raw_event(
            source_key="price_600519",
            tier="T2",
            success=False,
            failure_type="timeout",
            degraded=True,
            count=4,
            effective_threshold=2,
            timestamp=1001.0,
        )
        self._add_raw_event(
            source_key="price_000001",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=True,
            count=3,
            effective_threshold=2,
            timestamp=1002.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["degraded"] == 3
        assert len(price_row["degraded_list"]) == 3
        # 每项都应包含 source_key 前缀
        for dg in price_row["degraded_list"]:
            assert "price_" in dg

    def test_all_failed_degraded_list_empty(self):
        """全部失败（非 degraded）→ status='failed', degraded_list 空。"""
        for code in ("price_a", "price_b", "price_c"):
            self._add_raw_event(
                source_key=code,
                tier="T4",
                success=False,
                failure_type="unreachable",
                degraded=False,
                count=1,
                effective_threshold=1,
                timestamp=1000.0,
            )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["status"] == "failed"
        assert price_row["failed"] == 3
        assert price_row["degraded"] == 0
        assert len(price_row["degraded_list"]) == 0
        assert len(price_row["sample_failures"]) == 3

    def test_no_events_returns_empty(self):
        """无任何事件 → 空列表。"""
        from src.python.report.data_status import reset_tracker

        reset_tracker()
        matrix = self._build()
        assert matrix == []

    def test_degraded_list_includes_failure_type(self):
        """degraded_list 每项格式包含 failure_type 描述。"""
        self._add_raw_event(
            source_key="fund_rank_001",
            tier="T2",
            success=False,
            failure_type="empty",
            degraded=True,
            count=3,
            effective_threshold=2,
            timestamp=1000.0,
        )
        matrix = self._build()
        rank_row = next(r for r in matrix if r["key"] == "fund_rank")
        assert len(rank_row["degraded_list"]) == 1
        assert "empty" in rank_row["degraded_list"][0]
        assert "fund_rank_001" in rank_row["degraded_list"][0]


class TestBuildDataSourceCatalog:
    """build_data_source_catalog — 数据源说明表（用途/计费/凭据/本次使用）。"""

    def _catalog(self):
        from src.python.report.data_source_matrix import build_data_source_catalog

        return build_data_source_catalog()

    def _by_id(self, rows, sid):
        return next(r for r in rows if r["id"] == sid)

    def test_returns_all_catalog_categories(self):
        """说明表覆盖全部登记类别（含财报全文）。"""
        rows = self._catalog()
        ids = {r["id"] for r in rows}
        assert {
            "price",
            "fund_rank",
            "fund_hold",
            "industry",
            "index",
            "profit_forecast",
            "dividend",
            "fund_flow",
            "financial_report",
        } <= ids

    def test_used_flag_reflects_observed_events(self):
        """本次观测到事件的类别标记为已使用；未观测到的为未使用。"""
        from src.python.report.data_status import DegradationEvent, get_tracker

        get_tracker()._events.append(
            DegradationEvent(
                source_key="report_datasink_600519.SS",
                tier="T2",
                success=True,
                failure_type="",
                degraded=False,
                count=0,
                effective_threshold=0,
                timestamp=1000.0,
            )
        )
        rows = self._catalog()
        assert self._by_id(rows, "financial_report")["used"] is True
        assert self._by_id(rows, "price")["used"] is False

    def test_datasink_billing_follows_plan(self, monkeypatch):
        """财报全文计费随 datasink.plan 变化（free / yearly）。"""
        rows = self._catalog()
        assert "免费档" in self._by_id(rows, "financial_report")["billing"]
        monkeypatch.setattr("src.python.report.data_source_matrix._datasink_plan", lambda: "yearly")
        rows = self._catalog()
        assert "付费档" in self._by_id(rows, "financial_report")["billing"]

    def test_datasink_auth_shows_credential_state(self, monkeypatch):
        """财报全文凭据列附加就绪状态（未配置 key）。"""
        from src.python.core.datasource_credential import CredentialSpec, register_credential_spec

        monkeypatch.delenv("DATASINK_API_KEY", raising=False)
        register_credential_spec(CredentialSpec("datasink", "DataSinking 财报", "DATASINK_API_KEY"))
        rows = self._catalog()
        assert self._by_id(rows, "financial_report")["auth"] == "需 key（未配置）"

    def test_free_sources_marked_no_key(self):
        """免费源凭据列为「无需」；有兜底槽的类别标「无需（主源）」（key 要求写在 provider 文案）。"""
        rows = self._catalog()
        for sid in (
            "price",
            "fund_rank",
            "fund_hold",
            "industry",
            "index",
            "profit_forecast",
            "dividend",
            "fund_flow",
            "history",
        ):
            assert self._by_id(rows, sid)["auth"].startswith("无需")
        for sid in ("fund_rank", "industry", "index", "profit_forecast", "dividend", "fund_flow"):
            assert self._by_id(rows, sid)["auth"] == "无需"


class TestDataSourceCatalog:
    """数据源说明表：类别清单、取用判定与开关提示。"""

    def _rows(self):
        from src.python.report.data_source_matrix import build_data_source_catalog

        return {r["id"]: r for r in build_data_source_catalog()}

    def test_financial_indicator_category_present(self):
        row = self._rows()["financial_indicator"]
        assert row["category"] == "财务指标"
        assert "akshare" in row["provider"]
        assert "DataSinking" in row["provider"]
        assert "财务指标" in row["category"] and "功能开关" in row["note"]

    def test_financial_report_row_hints_required_switches(self):
        """财报全文行须写明「需开启哪些开关才会取用」（否则读者会误以为未被调用）。"""
        row = self._rows()["financial_report"]
        assert "financial_report_digest" in row["note"]
        assert "financial_indicator" in row["note"]

    def test_used_by_category_prefix(self):
        from src.python.report.data_status import mark_data_used

        rows = self._rows()
        assert rows["financial_report"]["used"] is False
        assert rows["financial_indicator"]["used"] is False
        mark_data_used("report_datasink_doc")
        mark_data_used("fin_indicator_akshare_financial")
        rows = self._rows()
        assert rows["financial_report"]["used"] is True
        assert rows["financial_indicator"]["used"] is True
        # 不相干类别不受影响
        assert rows["price"]["used"] is False

    def test_used_false_when_nothing_fetched(self):
        rows = self._rows()
        assert all(r["used"] is False for r in rows.values())


class TestProviderAttribution:
    """矩阵「命中源」列 —— provider 级归属（本次这类数据由哪个源服务）。

    回归背景：报告曾只能答「这类数据健康吗」——tracker 的类别键里只有代码、没有
    provider，同花顺作为兜底槽接管时报告一字未提，令使用者误以为提供的 key 未被使用。
    """

    def _build(self):
        from src.python.report.data_source_matrix import build_data_source_matrix

        return build_data_source_matrix()

    def _category_event(self, source_key: str, success: bool = True) -> None:
        from src.python.report.data_status import DegradationEvent, get_tracker

        get_tracker()._events.append(
            DegradationEvent(
                source_key=source_key,
                tier="T2",
                success=success,
                failure_type="",
                degraded=False,
                count=0,
                effective_threshold=0,
                timestamp=1000.0,
            )
        )

    def test_hithink_fallback_attributed_to_category_row(self):
        """同花顺接管行情时，命中源列必须点名同花顺（而非只显示类别健康度）。"""
        from src.python.report.data_status import mark_provider_used

        self._category_event("price_price_stock_600900")
        mark_provider_used("price_stock", "hithink", "同花顺金融数据")
        row = next(r for r in self._build() if r["key"] == "price")
        assert "同花顺金融数据 ×1" in row["providers_text"]
        assert row["providers"]["hithink"]["count"] == 1

    def test_sentiment_row_from_provider_hits_alone(self):
        """市场情绪只有 provider 级归属（无类别事件）时仍须成行且点名同花顺。"""
        from src.python.report.data_status import mark_provider_used

        mark_provider_used("sentiment", "hithink", "同花顺金融数据")
        mark_provider_used("sentiment", "hithink", "同花顺金融数据")
        row = next(r for r in self._build() if r["key"] == "sentiment")
        assert row["name"] == "市场情绪"
        assert row["status"] == "ok"
        assert "同花顺金融数据 ×2" in row["providers_text"]
        assert "取数 2 次" in row["detail"]

    def test_provider_hits_aggregate_across_data_types(self):
        """同一类别的多个链路数据类型汇入同一行（行情含场内/场外两条链）。"""
        from src.python.report.data_status import mark_provider_used

        mark_provider_used("price_stock", "tencent", "腾讯财经")
        mark_provider_used("price_fund_otc", "eastmoney", "东方财富")
        row = next(r for r in self._build() if r["key"] == "price")
        # 命中次数相同时按展示名排序（输出稳定，便于比对）
        assert row["providers_text"] == "东方财富 ×1、腾讯财经 ×1"

    def test_dash_when_no_provider_hits(self):
        """命中缓存（无 provider 参与网络取数）时命中源列留空占位，而非硬凑一个源。"""
        self._category_event("fund_hold_017730")
        row = next(r for r in self._build() if r["key"] == "fund_hold")
        assert row["providers_text"] == "—"

    def test_history_data_types_mapped_to_history_category(self):
        """历史日 K 无类别级事件，其行由 provider 归属单独成立。"""
        from src.python.report.data_status import mark_provider_used

        mark_provider_used("history_stock", "tencent", "腾讯财经")
        row = next(r for r in self._build() if r["key"] == "history")
        assert row["name"] == "历史走势"
        assert "腾讯财经 ×1" in row["providers_text"]

    def test_index_history_mapped_to_index_category(self):
        """指数历史日 K 归入「指数数据」（与 index_history_ 类别前缀同口径）。"""
        from src.python.report.data_status import mark_provider_used

        mark_provider_used("history_index", "tencent", "腾讯财经")
        row = next(r for r in self._build() if r["key"] == "index")
        assert "腾讯财经 ×1" in row["providers_text"]

    def test_every_chain_data_type_is_mapped(self):
        """不变式：链路每个 data_type 必须有归属类别，否则命中源静默丢失。

        有意不进矩阵者须显式登记在 ``UNMAPPED_CHAIN_DATA_TYPES``（未归属是决策、不是遗漏）。
        """
        from src.python.fetcher.chain import _DEFAULT_CHAINS
        from src.python.report.data_source_matrix import UNMAPPED_CHAIN_DATA_TYPES, _SOURCE_CATEGORIES

        declared = {dt for cat in _SOURCE_CATEGORIES for dt in cat.get("data_types", [cat["key"]])}
        assert set(_DEFAULT_CHAINS) <= declared | set(UNMAPPED_CHAIN_DATA_TYPES)


class TestCatalogFallbackAndSentimentRows:
    """说明表须如实标注同花顺兜底槽位与市场情绪类别（用户误判 key 未生效的根因）。"""

    def _rows(self):
        from src.python.report.data_source_matrix import build_data_source_catalog

        return {r["id"]: r for r in build_data_source_catalog()}

    def test_fallback_rows_name_hithink_and_key(self):
        """以同花顺为兜底槽的类别，provider 文案须点名同花顺并标「需 key」。"""
        rows = self._rows()
        for sid in ("price", "fund_hold", "financial_indicator", "history"):
            assert "同花顺" in rows[sid]["provider"]
            assert "需 key" in rows[sid]["provider"]

    def test_financial_report_row_notes_no_fallback(self):
        """财报全文无兜底源（同花顺不含公告原文）——写明以防读者误以为漏配。"""
        assert "无兜底源" in self._rows()["financial_report"]["note"]

    def test_sentiment_row_registered(self):
        """市场情绪为同花顺唯一源：须有独立行、计费免费、注明所需开关。"""
        row = self._rows()["sentiment"]
        assert row["category"] == "市场情绪"
        assert "同花顺" in row["provider"]
        assert row["billing"].startswith("免费")
        assert "market_sentiment" in row["note"]

    def test_sentiment_auth_shows_credential_state(self, monkeypatch):
        """凭据列附同花顺 key 就绪态。"""
        from src.python.core.datasource_credential import CredentialSpec, register_credential_spec

        monkeypatch.delenv("HITHINK_FINANCE_API_KEY", raising=False)
        register_credential_spec(CredentialSpec("hithink", "同花顺金融数据", "HITHINK_FINANCE_API_KEY"))
        assert self._rows()["sentiment"]["auth"] == "需 key（未配置）"

    def test_sentiment_used_tracks_category_mark(self):
        from src.python.report.data_status import mark_data_used

        assert self._rows()["sentiment"]["used"] is False
        mark_data_used("sentiment")
        assert self._rows()["sentiment"]["used"] is True

    def test_history_used_follows_provider_hits(self):
        """历史走势只登记缓存键：其「本次使用」以 provider 归属为正面证据。"""
        from src.python.report.data_status import mark_provider_used

        assert self._rows()["history"]["used"] is False
        mark_provider_used("history_stock", "tencent", "腾讯财经")
        assert self._rows()["history"]["used"] is True
