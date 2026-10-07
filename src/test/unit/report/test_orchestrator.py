"""orchestrator 共享层单元测试。

prepare_report_data mock 测试 + capture_snapshot。

兄弟分片：test_orchestrator_generate_report.py（generate_report 产物落盘与快照比对）。
"""

from __future__ import annotations


import pytest

from unittest.mock import MagicMock, patch

from src.python.report._llm_news import _fetch_llm_and_news, _report_llm_module_results
from src.python.report._snapshot import capture_snapshot, fetch_history_data
from src.python.report.orchestrator import (
    ReportResult,
    _read_section_flags,
    prepare_report_data,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]


class TestReportResult:
    """ReportResult 数据结构测试。"""

    def test_exit_code_success(self):
        result = ReportResult(report_generated=True)
        assert result.exit_code == 0

    def test_exit_code_partial(self):
        result = ReportResult(report_generated=True, errors=["部分失败"])
        assert result.exit_code == 1

    def test_exit_code_severe(self):
        result = ReportResult()
        assert result.exit_code == 2

    def test_exit_code_severe_via_errors(self):
        """report_generated=False 即使有 errors 也返回 2（严重错误优先）。"""
        result = ReportResult(errors=["错误"])
        assert result.exit_code == 2


class TestReadSectionFlags:
    """_read_section_flags 配置解析测试。"""

    def test_all_enabled(self):
        with (
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_portfolio_evolution", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
        ):
            flags = _read_section_flags({})
        assert flags == {"fund_deep_analysis": True, "news": True, "history": True, "evolution": True, "llm": True}

    def test_all_disabled(self):
        with (
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=False),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
            patch("src.python.config.is_enable_portfolio_evolution", return_value=False),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            flags = _read_section_flags({})
        assert flags == {"fund_deep_analysis": False, "news": False, "history": False, "evolution": False, "llm": False}

    def test_partial_flags(self):
        with (
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_portfolio_evolution", return_value=False),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            flags = _read_section_flags({})
        assert flags["news"] is False
        assert flags["llm"] is False
        assert flags["fund_deep_analysis"] is True
        assert flags["evolution"] is False


@pytest.mark.unit
@pytest.mark.unit_report
class TestPrepareReportData:
    """prepare_report_data 数据准备功能测试。"""

    def test_prepare_report_data_structure(self):
        """验证返回的 dict 包含全部预期 key，且结构正确。"""
        mock_reporter = MagicMock()
        mock_holdings = [
            MagicMock(code="SH600001", name="测试股票", shares=100, cost_price=10.0),
        ]

        mock_detail = MagicMock()
        mock_detail.code = "SH600001"
        mock_detail.name = "测试股票"
        mock_detail.market_value = 1200.0
        mock_detail.cost = 1000.0
        mock_detail.profit = 200.0
        mock_detail.profit_rate = 0.2
        mock_detail.today_profit = 10.0
        mock_detail.price = 12.0
        mock_detail.yesterday_close = 11.0
        mock_detail.nav_date = "2026-07-16"
        mock_detail.source_api = "mock"
        mock_detail.account = "证券账户"  # 非场外账户关键词 → 渠道为场内

        mock_category = MagicMock()

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report.market_value.classify_holdings", return_value=[mock_category]),
            patch("src.python.fetcher.index.fetch_indices", return_value={"sh000001": 3000}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={"gb_inx": 5000}),
            patch("src.python.report.penetration.compute_penetration_top10", return_value={"top10": []}),
            # 因子暴露编排含真实网络拉取（持仓历史/因子指数 K 线），测试必须 mock（防 API 依赖/不稳定）
            patch(
                "src.python.report.orchestrator.compute_factor_exposure_data",
                return_value={"available": False, "status": "insufficient"},
            ),
            # 持仓关系矩阵·相关性编排同样含真实网络拉取（持仓历史 K 线），必须 mock
            patch(
                "src.python.report.orchestrator.compute_correlation_data",
                return_value={"available": False, "status": "insufficient"},
            ),
        ):
            result = prepare_report_data(mock_holdings, mock_reporter, config={})

        expected_keys = {
            "details",
            "total_mv",
            "total_cost",
            "total_profit",
            "total_today_profit",
            "categories",
            "a_indices",
            "us_indices",
            "penetrated_assets",
            "holdings_details",
            "today_str",
            "output_dir",
            "news_top_count",
            "risk_metrics",
            "style_factor_data",
            # 因子目录契约（实验开关 factor_catalog 关闭时为 None）
            "factor_catalog_data",
            "position_relationship_data",
            # 品种覆盖诊断：品种级数据状态标注契约
            "position_status",
            # 可信度摘要：新鲜度分类 + 单日跳变检测契约
            "data_freshness",
            # 行动建议单一数据源：「行动建议」章行动板块 + 「智囊团深度复盘」章行动摘要共享（数据契约）
            "action_data",
            # 估值分位契约（功能开关 valuation_percentile 关闭时为 None）
            "valuation_data",
            # 市场温度契约（功能开关 market_temperature 关闭时为 None）
            "market_temperature_data",
            # 持仓个股财报摘要契约（功能开关 financial_report_digest 关闭时为 None）
            "financial_report_digest_data",
            # 财务指标契约（功能开关 financial_indicator 关闭时为 None）
            "financial_indicator_data",
            # 申购限购状态契约（功能开关 fund_purchase_limit 关闭时为 None）
            "purchase_status_data",
        }
        assert set(result.keys()) == expected_keys, f"缺少 key: {expected_keys - set(result.keys())}"

        assert result["total_mv"] == 1200.0
        assert result["total_cost"] == 1000.0
        assert result["total_profit"] == 200.0
        assert mock_reporter.info.call_count >= 3

    def test_prepare_report_data_channel_from_account(self):
        """holdings_details 契约携带渠道上下文：账户关键词决定场内/场外。

        回归：调仓建议可行化层按渠道计算份额取整与费用，场外账户（如天天基金）
        持有的 16/11 开头基金不得按场内 100 份取整 + 仅佣金处理。
        """
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="161725", name="招商中证白酒指数A", shares=1000, cost_price=1.0)]

        mock_detail = MagicMock()
        mock_detail.code = "161725"
        mock_detail.name = "招商中证白酒指数A"
        mock_detail.market_value = 1200.0
        mock_detail.cost = 1000.0
        mock_detail.profit = 200.0
        mock_detail.profit_rate = 0.2
        mock_detail.today_profit = 0.0
        mock_detail.price = 1.2
        mock_detail.yesterday_close = 1.1
        mock_detail.nav_date = "2026-08-04"
        mock_detail.source_api = "mock"
        mock_detail.account = "天天基金"  # 场外账户关键词 → 渠道为场外

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report.market_value.classify_holdings", return_value=[]),
            patch("src.python.fetcher.index.fetch_indices", return_value={}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
            patch("src.python.report.penetration.compute_penetration_top10", return_value={"top10": []}),
            patch(
                "src.python.report.orchestrator.compute_factor_exposure_data",
                return_value={"available": False, "status": "insufficient"},
            ),
            patch(
                "src.python.report.orchestrator.compute_correlation_data",
                return_value={"available": False, "status": "insufficient"},
            ),
        ):
            result = prepare_report_data(mock_holdings, mock_reporter, config={})

        assert result["holdings_details"][0]["channel"] == "场外"

    def test_prepare_report_data_empty_holdings(self):
        """空持仓不抛出异常，返回正确结构。"""
        mock_reporter = MagicMock()

        with (
            patch("src.python.report.market_value._generate_details", return_value=[]),
            patch("src.python.report.market_value.classify_holdings", return_value=[]),
            patch("src.python.fetcher.index.fetch_indices", return_value={}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
            patch("src.python.report.penetration.compute_penetration_top10", return_value={"top10": []}),
        ):
            result = prepare_report_data([], mock_reporter, config={})

        assert result["total_mv"] == 0
        assert result["total_cost"] == 0
        assert result["total_profit"] == 0
        assert result["details"] == []
        assert result["holdings_details"] == []


@pytest.mark.unit
@pytest.mark.unit_report
class TestReportLlmModuleResults:
    """_report_llm_module_results 统一 LLM 结果报告测试。"""

    @pytest.fixture(autouse=True)
    def _clean_llm_failure_state(self):
        """清除 LLM_MODULE_FAILURE 全局状态，避免跨测试污染。"""
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        _saved = dict(LLM_MODULE_FAILURE)
        LLM_MODULE_FAILURE.clear()
        yield
        LLM_MODULE_FAILURE.update(_saved)

    def test_all_ok(self):
        """所有 4 个模块均成功。"""
        reporter = MagicMock()
        _report_llm_module_results(
            ("<p>A</p>", "<p>B</p>", "<p>C</p>", "<p>D</p>"),
            (False, False, False, False),
            reporter,
        )
        # "LLM 内容生成完成" 被调用
        ok_calls = [c for c in reporter.ok.call_args_list if "内容生成完成" in str(c)]
        assert len(ok_calls) == 1

    def test_with_cached(self):
        """全部缓存命中时 tag="缓存"。"""
        reporter = MagicMock()
        _report_llm_module_results(
            ("<p>A</p>", "<p>B</p>", "<p>C</p>", "<p>D</p>"),
            (True, True, True, True),
            reporter,
        )
        ok_calls = [c for c in reporter.ok.call_args_list if "缓存" in str(c)]
        assert len(ok_calls) == 1

    def test_all_none(self):
        """全部为 None 时不抛异常。"""
        reporter = MagicMock()
        _report_llm_module_results(
            (None, None, None, None),
            (False, False, False, False),
            reporter,
        )
        reporter.warn.assert_called()


@pytest.mark.unit
@pytest.mark.unit_report
class TestFetchLlmAndNews:
    """_fetch_llm_and_news 4 分支测试。"""

    def _make_prep_data(self, **overrides) -> dict:
        data = {
            "news_top_count": 100,
            "penetrated_assets": [],
            "a_indices": {},
            "us_indices": {},
            "total_mv": 0,
            "total_cost": 0,
            "total_profit": 0,
            "total_today_profit": 0,
            "categories": [],
            "holdings_details": [],
        }
        data.update(overrides)
        return data

    def test_both_enabled(self):
        """分支①：LLM+新闻均开启。"""
        reporter = MagicMock()
        holdings = [MagicMock(code="SH600001", shares=100)]
        prep = self._make_prep_data()

        with (
            patch(
                "src.python.llm.generate_all_llm",
                return_value=(
                    "<p>宏观</p>",
                    None,
                    None,
                    None,
                    False,
                    False,
                    False,
                    False,
                ),
            ),
            patch(
                "src.python.report.news_correlation.build_news_data",
                return_value=(
                    [{"title": "新闻1"}],
                    {},
                ),
            ),
        ):
            result = _fetch_llm_and_news(
                holdings,
                prep,
                sector_flow=[],
                force_llm=False,
                pipeline_data=None,
                enable_news=True,
                enable_llm=True,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok, _debate_info = result
        assert llm_content[0] == "<p>宏观</p>"
        assert len(news_data) == 1
        assert news_ok is True

    def test_llm_only(self):
        """分支③：仅 LLM。"""
        reporter = MagicMock()
        holdings = [MagicMock(code="SH600001", shares=100)]
        prep = self._make_prep_data()

        with (
            patch(
                "src.python.llm.generate_all_llm",
                return_value=(
                    "<p>宏观</p>",
                    None,
                    None,
                    None,
                    False,
                    False,
                    False,
                    False,
                ),
            ),
            patch("src.python.report.news_correlation.build_news_data"),
        ):
            result = _fetch_llm_and_news(
                holdings,
                prep,
                sector_flow=[],
                force_llm=False,
                pipeline_data=None,
                enable_news=False,
                enable_llm=True,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok, _debate_info = result
        assert llm_content[0] == "<p>宏观</p>"
        assert news_data == []
        assert news_ok is False

    def test_news_only(self):
        """分支②：仅新闻。"""
        reporter = MagicMock()
        holdings = [MagicMock(code="SH600001", shares=100)]
        prep = self._make_prep_data()

        with (
            patch("src.python.llm.generate_all_llm"),
            patch(
                "src.python.report.news_correlation.build_news_data",
                return_value=(
                    [{"title": "新闻1"}],
                    {},
                ),
            ),
        ):
            result = _fetch_llm_and_news(
                holdings,
                prep,
                sector_flow=[],
                force_llm=False,
                pipeline_data=None,
                enable_news=True,
                enable_llm=False,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok, _debate_info = result
        assert llm_content == (None, None, None, None)
        assert len(news_data) == 1
        assert news_ok is True

    def test_both_disabled(self):
        """分支④：均关闭。"""
        reporter = MagicMock()

        result = _fetch_llm_and_news(
            [],
            {},
            sector_flow=None,
            force_llm=False,
            pipeline_data=None,
            enable_news=False,
            enable_llm=False,
            reporter=reporter,
        )

        llm_content, news_data, news_llm_meta, news_ok, _debate_info = result
        assert llm_content == (None, None, None, None)
        assert news_data == []
        assert news_ok is False
        reporter.info.assert_called_once()

    def test_llm_failure_fallback(self):
        """LLM 失败时新闻仍正常返回。"""
        reporter = MagicMock()
        holdings = [MagicMock(code="SH600001", shares=100)]
        prep = self._make_prep_data()

        with (
            patch("src.python.llm.generate_all_llm", side_effect=RuntimeError("LLM 异常")),
            patch(
                "src.python.report.news_correlation.build_news_data",
                return_value=(
                    [{"title": "新闻1"}],
                    {},
                ),
            ),
        ):
            result = _fetch_llm_and_news(
                holdings,
                prep,
                sector_flow=[],
                force_llm=False,
                pipeline_data=None,
                enable_news=True,
                enable_llm=True,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok, _debate_info = result
        assert llm_content == (None, None, None, None)
        assert len(news_data) == 1  # 新闻仍返回
        assert news_ok is True


@pytest.mark.unit
@pytest.mark.unit_report
@pytest.mark.unit
class TestSubmitLlmFutureDegradationEvents:
    """_submit_llm_future 数据降级事件透传回归测试。

    回归场景：数据源降级事件此前未随参数送入 generate_all_llm，持仓体检
    提示词中的【数据质量降级】详情段在生产路径恒为空，LLM 只能凭基础
    降级块泛泛而谈。此处锁定「事件快照确实被读取并透传」。
    """

    def _prep(self) -> dict:
        return {
            "a_indices": {},
            "us_indices": {},
            "total_mv": 0.0,
            "total_cost": 0.0,
            "total_profit": 0.0,
            "total_today_profit": 0.0,
            "categories": [],
            "penetrated_assets": [],
            "holdings_details": [],
        }

    def _capture_submit_kwargs(self, fail_source_key: str | None) -> tuple[dict, list[dict]]:
        """执行一次提交，返回 (submit 关键字参数, 提交时刻的降级事件日志)。"""
        from src.python.report._llm_news import _submit_llm_future
        from src.python.report.data_status import get_tracker

        tracker = get_tracker()
        tracker.clear_log()
        if fail_source_key:
            tracker.record(fail_source_key, "T2", success=False, failure_type="unreachable")
        expected_events = tracker.get_log()

        pool = MagicMock()
        pool.submit.return_value = MagicMock(name="future")
        with patch("src.python.llm.generate_all_llm", MagicMock()):
            _submit_llm_future(pool, [MagicMock()], self._prep(), [], False, None, True)
        return pool.submit.call_args.kwargs, expected_events

    def test_degradation_events_forwarded(self):
        """有降级事件时，事件列表随参数透传给 generate_all_llm。"""
        kwargs, expected = self._capture_submit_kwargs("industry")
        assert "degradation_events" in kwargs, "降级事件未透传，体检提示词的数据质量详情段将为空"
        assert kwargs["degradation_events"] == expected
        assert [e["source_key"] for e in kwargs["degradation_events"]] == ["industry"]

    def test_empty_degradation_events_still_forwarded(self):
        """无降级事件时透传空列表（而非 None），保持与数据源侧语义一致。"""
        kwargs, expected = self._capture_submit_kwargs(None)
        assert kwargs["degradation_events"] == []
        assert expected == []

    def test_disabled_llm_skips_submit(self):
        """未启用 LLM 时不提交任务，也不读取降级事件。"""
        from src.python.report._llm_news import _submit_llm_future

        pool = MagicMock()
        assert _submit_llm_future(pool, [MagicMock()], self._prep(), [], False, None, False) is None
        pool.submit.assert_not_called()


@pytest.mark.unit
class TestCaptureSnapshot:
    """capture_snapshot 快照创建测试（8 用例覆盖 5 子步骤）。"""

    def _make_mock_detail(self, code="SH600001", name="测试", mv=1200.0, cost=1000.0, profit=200.0) -> MagicMock:
        d = MagicMock()
        d.code = code
        d.name = name
        d.market_value = mv
        d.cost = cost
        d.profit = profit
        d.profit_rate = profit / cost if cost else 0
        return d

    def _make_mock_holding(self, code="SH600001", name="测试", shares=100, cost_price=10.0) -> MagicMock:
        h = MagicMock()
        h.code = code
        h.name = name
        h.shares = shares
        h.cost_price = cost_price
        return h

    def test_capture_snapshot_holding_mapping(self):
        """从 details → SnapshotHolding 字段映射正确（份额/成本由持仓对象回填）。

        断言落在传给 save() 的快照对象上，而不是仅看返回值——
        首次运行返回值本就是 None，看不出字段映射是否正确。
        """
        mock_reporter = MagicMock()
        detail = self._make_mock_detail()
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}

        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None),
            patch("src.python.report.history_snapshot.save") as mock_save,
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd,
            patch("src.python.report.history_snapshot.prune"),
        ):
            mock_diff = MagicMock()
            mock_diff.is_first_check = True
            mock_hd.compute.return_value = mock_diff

            capture_snapshot(
                [self._make_mock_holding(code="SH600001", name="测试", shares=200, cost_price=12.0)],
                [detail],
                config,
                mock_reporter,
            )

        snapshot = mock_save.call_args.args[0]
        holding = snapshot.accounts[0].holdings[0]
        # 行情侧字段（来自 detail）
        assert holding.code == "SH600001"
        assert holding.market_value == 1200.0
        assert holding.total_pnl == 200.0
        assert holding.cost_total == 1000.0
        # 持仓侧字段（按 code 从 holdings 回填：detail 本身无份额/成本）
        assert holding.name == "测试"
        assert holding.shares == 200
        assert holding.cost_price == 12.0
        # 汇总字段与账户名
        assert snapshot.accounts[0].account_name == "全部"
        assert snapshot.total_value == 1200.0
        assert snapshot.total_cost == 1000.0
        assert snapshot.total_pnl == 200.0

    def test_capture_snapshot_holdings_lookup(self):
        """holdings 回查补充 shares/cost_price；无匹配时默认 0.0。"""
        mock_reporter = MagicMock()
        detail = self._make_mock_detail()
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}

        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None),
            patch("src.python.report.history_snapshot.save") as mock_save,
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd,
            patch("src.python.report.history_snapshot.prune"),
        ):
            mock_diff = MagicMock()
            mock_diff.is_first_check = True
            mock_hd.compute.return_value = mock_diff

            # 持仓列表不含 detail 的代码 → 走「无匹配」分支，份额/成本应回落默认值
            # （匹配分支的回填由 test_capture_snapshot_holding_mapping 覆盖）
            capture_snapshot(
                [self._make_mock_holding(code="SZ000001", shares=200, cost_price=12.0)],
                [detail],
                config,
                mock_reporter,
            )

        # 断言落在 save() 收到的快照对象上（只看 compute.called 无法证明默认值生效）
        holding = mock_save.call_args.args[0].accounts[0].holdings[0]
        assert holding.code == "SH600001"
        assert holding.shares == 0.0
        assert holding.cost_price == 0.0

    def test_capture_snapshot_data_creation(self):
        """SnapshotData 聚合计算正确（多明细求和 + 账户内持仓清单）。"""
        mock_reporter = MagicMock()
        details = [
            self._make_mock_detail(code="SH600001", mv=1200.0, cost=1000.0, profit=200.0),
            self._make_mock_detail(code="SH600002", mv=2400.0, cost=2000.0, profit=400.0),
        ]
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}

        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None),
            patch("src.python.report.history_snapshot.save") as mock_save,
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd,
            patch("src.python.report.history_snapshot.prune"),
        ):
            mock_diff = MagicMock()
            mock_diff.is_first_check = True
            mock_hd.compute.return_value = mock_diff

            capture_snapshot(
                [self._make_mock_holding(code="SH600001"), self._make_mock_holding(code="SH600002")],
                details,
                config,
                mock_reporter,
            )

        snapshot = mock_save.call_args.args[0]
        assert snapshot.accounts[0].account_name == "全部"
        assert [h.code for h in snapshot.accounts[0].holdings] == ["SH600001", "SH600002"]
        assert snapshot.total_value == 3600.0  # 1200 + 2400
        assert snapshot.total_cost == 3000.0  # 1000 + 2000
        assert snapshot.total_pnl == 600.0  # 200 + 400

    def test_capture_snapshot_diff_compute(self):
        """HistoryDiff.compute 被调用，diff 结果含四个子列表。"""
        mock_reporter = MagicMock()
        detail = self._make_mock_detail()
        details = [detail]
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}

        # 构造有 diff 数据的 mock
        mock_diff = MagicMock()
        mock_diff.is_first_check = False
        mock_diff.total_value_diff = 100.0
        mock_diff.total_value_diff_pct = 0.05
        mock_diff.total_pnl_diff = 50.0
        mock_diff.days_since_last_report = 1
        mock_diff.trimmed = False

        added_item = MagicMock()
        added_item.name = "新增股"
        added_item.code = "SH600003"
        added_item.action = "added"
        added_item.shares_diff = 100
        added_item.value_diff = 500.0
        mock_diff.added = [added_item]
        mock_diff.removed = []
        mock_diff.increased = []
        mock_diff.decreased = []

        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=MagicMock()),
            patch("src.python.report.history_snapshot.save"),
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd_cls,
            patch("src.python.report.history_snapshot.prune"),
        ):
            mock_hd_cls.compute.return_value = mock_diff

            result = capture_snapshot(
                [self._make_mock_holding()],
                details,
                config,
                mock_reporter,
            )

        assert result is not None
        assert "diff" in result
        assert result["diff"]["is_first_check"] is False
        assert result["diff"]["total_value_diff"] == 100.0
        assert len(result["diff"]["added"]) == 1

    def test_capture_snapshot_prune_params(self):
        """prune 接收的 retention_days/max_count 来自 config 参数。"""
        mock_reporter = MagicMock()
        detail = self._make_mock_detail()
        config = {"history": {"snapshot_retention_days": 99, "snapshot_max_count": 200}}

        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None),
            patch("src.python.report.history_snapshot.save"),
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd,
            patch("src.python.report.history_snapshot.prune") as mock_prune,
        ):
            mock_diff = MagicMock()
            mock_diff.is_first_check = True
            mock_hd.compute.return_value = mock_diff

            capture_snapshot(
                [self._make_mock_holding()],
                [detail],
                config,
                mock_reporter,
            )

        # 验证 prune 参数来自 config 而非 get_config_cache()；默认 namespace=None（共享主目录）
        mock_prune.assert_called_once_with(retention_days=99, max_count=200, namespace=None)

    def test_capture_snapshot_pipeline_data(self):
        """pipeline_data 含 diff/diff_trimmed/days_since_last 三个顶层 key。"""
        mock_reporter = MagicMock()
        detail = self._make_mock_detail()
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}

        mock_diff = MagicMock()
        mock_diff.is_first_check = False
        mock_diff.total_value_diff = 0.0
        mock_diff.total_value_diff_pct = 0.0
        mock_diff.total_pnl_diff = 0.0
        mock_diff.days_since_last_report = 5
        mock_diff.trimmed = False
        mock_diff.added = []
        mock_diff.removed = []
        mock_diff.increased = []
        mock_diff.decreased = []

        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=MagicMock()),
            patch("src.python.report.history_snapshot.save"),
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd_cls,
            patch("src.python.report.history_snapshot.prune"),
        ):
            mock_hd_cls.compute.return_value = mock_diff

            result = capture_snapshot(
                [self._make_mock_holding()],
                [detail],
                config,
                mock_reporter,
            )

        assert result is not None
        assert "diff" in result
        assert result["diff"]["days_since_last_report"] == 5

    def test_capture_snapshot_first_run(self):
        """首次运行（无旧快照）时返回 None。"""
        mock_reporter = MagicMock()
        detail = self._make_mock_detail()
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}

        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None),
            patch("src.python.report.history_snapshot.save"),
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd,
            patch("src.python.report.history_snapshot.prune"),
        ):
            mock_diff = MagicMock()
            mock_diff.is_first_check = True
            mock_hd.compute.return_value = mock_diff

            result = capture_snapshot(
                [self._make_mock_holding()],
                [detail],
                config,
                mock_reporter,
            )

        assert result is None

    def test_capture_snapshot_exception_safe(self):
        """异常时捕获到 logger，返回 None 不阻塞。"""
        mock_reporter = MagicMock()
        detail = self._make_mock_detail()
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}

        with (
            patch("src.python.report.history_snapshot.load_latest", side_effect=ValueError("测试异常")),
            patch("src.python.report.history_snapshot.save"),
            patch("src.python.fetcher.history_diff.HistoryDiff"),
            patch("src.python.report.history_snapshot.prune"),
        ):
            result = capture_snapshot(
                [self._make_mock_holding()],
                [detail],
                config,
                mock_reporter,
            )

        assert result is None


@pytest.mark.unit
@pytest.mark.unit_report
class TestFetchHistoryData:
    """fetch_history_data 历史走势数据获取测试。"""

    def test_fetch_history_data_fetch_true(self):
        """fetch=True 返回 PortfolioHistoryCalculator 计算结果。"""
        mock_reporter = MagicMock()
        mock_holding = MagicMock()
        mock_holding.code = "SH600001"
        mock_holding.name = "测试"
        mock_holding.shares = 100

        mock_history_data = {
            "dates": ["2026-01-01", "2026-07-16"],
            "values": [1000.0, 1200.0],
            "status": "available",
        }

        with patch("src.python.report.portfolio_history.PortfolioHistoryCalculator") as mock_cls:
            mock_calc = MagicMock()
            mock_calc.get_combined_timeseries.return_value = mock_history_data
            mock_cls.return_value = mock_calc

            result = fetch_history_data(
                [mock_holding],
                {"history": {"coverage_threshold": 0.9}},
                mock_reporter,
                fetch=True,
            )

        assert result is not None
        assert result["status"] == "available"
        assert len(result["dates"]) == 2
        mock_cls.assert_called_once_with(
            coverage_threshold=0.9,
            benchmark_indices={},
        )

    def test_fetch_history_data_fetch_false(self):
        """fetch=False 返回 None 并醒目提示 history 已关闭（回归守护）。

        防回退：history 关闭时必须通过 reporter.warn + logger 明确警示，
        不得静默跳过——否则下游只剩误导性的"尾部风险：无历史 bars"占位警告。
        """
        mock_reporter = MagicMock()

        result = fetch_history_data(
            [],
            {"history": {}},
            mock_reporter,
            fetch=False,
        )

        assert result is None
        mock_reporter.warn.assert_called_once()
        # 警示文案须点明 history 关闭与后果，避免与"无历史 bars"混淆
        warn_msg = mock_reporter.warn.call_args.args[0]
        assert "history off" in warn_msg
        assert "数据不可用" in warn_msg

    def test_fetch_history_data_unavailable(self):
        """status=unavailable 时返回数据但 reporter.warn 被调用。"""
        mock_reporter = MagicMock()
        mock_history_data = {"status": "unavailable"}

        with patch("src.python.report.portfolio_history.PortfolioHistoryCalculator") as mock_cls:
            mock_calc = MagicMock()
            mock_calc.get_combined_timeseries.return_value = mock_history_data
            mock_cls.return_value = mock_calc

            result = fetch_history_data(
                [MagicMock()],
                {"history": {}},
                mock_reporter,
            )

        assert result is not None
        assert result["status"] == "unavailable"
        mock_reporter.warn.assert_called_once()

    def test_fetch_history_data_exception(self):
        """内部异常时返回 None 不阻塞。"""
        mock_reporter = MagicMock()

        with patch(
            "src.python.report.portfolio_history.PortfolioHistoryCalculator",
            side_effect=RuntimeError("测试异常"),
        ):
            result = fetch_history_data(
                [MagicMock()],
                {"history": {}},
                mock_reporter,
            )

        assert result is None

    def test_fetch_history_data_uses_lookback_days(self):
        """history.lookback_days 配置透传给 get_combined_timeseries 的 days 参数。

        回归防护：回撤分析需 ≥60 交易日（MIN_SPAN），若取数窗口未随配置放大，
        主报告回撤分析将一直判定数据不足。此处断言配置 → days 透传。
        """
        mock_reporter = MagicMock()
        mock_holding = MagicMock()
        mock_holding.code = "SH600001"
        mock_holding.name = "测试"
        mock_holding.shares = 100

        with patch("src.python.report.portfolio_history.PortfolioHistoryCalculator") as mock_cls:
            mock_calc = MagicMock()
            mock_calc.get_combined_timeseries.return_value = {"status": "ok", "bars": []}
            mock_cls.return_value = mock_calc

            fetch_history_data(
                [mock_holding],
                {"history": {"lookback_days": 120}},
                mock_reporter,
                fetch=True,
            )

        mock_calc.get_combined_timeseries.assert_called_once_with(
            [("SH600001", "测试", 100)],
            days=120,
        )

    def test_fetch_history_data_lookback_days_default_90(self):
        """未配置 lookback_days 时取数窗口默认 90。"""
        mock_reporter = MagicMock()
        mock_holding = MagicMock()
        mock_holding.code = "SH600001"
        mock_holding.name = "测试"
        mock_holding.shares = 100

        with patch("src.python.report.portfolio_history.PortfolioHistoryCalculator") as mock_cls:
            mock_calc = MagicMock()
            mock_calc.get_combined_timeseries.return_value = {"status": "ok", "bars": []}
            mock_cls.return_value = mock_calc

            fetch_history_data(
                [mock_holding],
                {"history": {}},
                mock_reporter,
                fetch=True,
            )

        mock_calc.get_combined_timeseries.assert_called_once_with(
            [("SH600001", "测试", 100)],
            days=90,
        )


class TestArtifactsForReportType:
    """artifacts_for_report_type — 报告类型 → 产物 kind 单源（Web 产物清单消费）。"""

    def test_basic_yields_excel_only(self):
        from src.python.report.orchestrator import artifacts_for_report_type

        assert artifacts_for_report_type("basic") == ("xlsx",)

    def test_both_and_full_include_html(self):
        from src.python.report.orchestrator import artifacts_for_report_type

        for report_type in ("both", "full"):
            assert artifacts_for_report_type(report_type) == ("html", "xlsx")

    def test_unknown_type_defaults_to_excel(self):
        from src.python.report.orchestrator import artifacts_for_report_type

        assert artifacts_for_report_type("nonsense") == ("xlsx",)
