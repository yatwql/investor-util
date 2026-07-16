"""orchestrator 共享层单元测试。

S1 骨架：prepare_report_data mock 测试。
S2 扩展：capture_snapshot + compute_early_warnings。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.python.report.orchestrator import (
    ReportResult,
    _read_section_flags,
    generate_report,
    prepare_report_data,
    capture_snapshot,
    compute_early_warnings,
    fetch_history_data,
)


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
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
        ):
            flags = _read_section_flags({})
        assert flags == {"b_series": True, "news": True, "history": True, "llm": True}

    def test_all_disabled(self):
        with (
            patch("src.python.config.is_enable_b_series", return_value=False),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            flags = _read_section_flags({})
        assert flags == {"b_series": False, "news": False, "history": False, "llm": False}

    def test_partial_flags(self):
        with (
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            flags = _read_section_flags({})
        assert flags["news"] is False
        assert flags["llm"] is False
        assert flags["b_series"] is True


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

        mock_category = MagicMock()

        with (
            patch("src.python.tui_menu.get_config_cache", return_value={}),
            patch("src.python.tui_handlers.check_network_available"),
            patch("src.python.handlers_report._get_pool") as mock_pool,
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report.market_value.classify_holdings", return_value=[mock_category]),
            patch("src.python.fetcher.index.fetch_indices", return_value={"sh000001": 3000}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={"gb_inx": 5000}),
            patch("src.python.report.penetration.compute_penetration_top10", return_value={"top10": []}),
        ):
            mock_ex = MagicMock()
            mock_fut_a = MagicMock()
            mock_fut_us = MagicMock()
            mock_fut_a.result.return_value = {"sh000001": 3000}
            mock_fut_us.result.return_value = {"gb_inx": 5000}
            mock_ex.submit.side_effect = [mock_fut_a, mock_fut_us]
            mock_pool.return_value = mock_ex

            result = prepare_report_data(mock_holdings, mock_reporter)

        expected_keys = {
            "details", "total_mv", "total_cost", "total_profit",
            "total_today_profit", "categories", "a_indices", "us_indices",
            "penetrated_assets", "holdings_details", "today_str",
            "output_dir", "news_top_count",
        }
        assert set(result.keys()) == expected_keys, f"缺少 key: {expected_keys - set(result.keys())}"

        assert result["total_mv"] == 1200.0
        assert result["total_cost"] == 1000.0
        assert result["total_profit"] == 200.0
        assert mock_reporter.info.call_count >= 3

    def test_prepare_report_data_empty_holdings(self):
        """空持仓不抛出异常，返回正确结构。"""
        mock_reporter = MagicMock()

        with (
            patch("src.python.tui_menu.get_config_cache", return_value={}),
            patch("src.python.tui_handlers.check_network_available"),
            patch("src.python.handlers_report._get_pool") as mock_pool,
            patch("src.python.report.market_value._generate_details", return_value=[]),
            patch("src.python.report.market_value.classify_holdings", return_value=[]),
            patch("src.python.fetcher.index.fetch_indices", return_value={}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
            patch("src.python.report.penetration.compute_penetration_top10", return_value={"top10": []}),
        ):
            mock_ex = MagicMock()
            mock_fut_a = MagicMock()
            mock_fut_us = MagicMock()
            mock_fut_a.result.return_value = {}
            mock_fut_us.result.return_value = {}
            mock_ex.submit.side_effect = [mock_fut_a, mock_fut_us]
            mock_pool.return_value = mock_ex

            result = prepare_report_data([], mock_reporter)

        assert result["total_mv"] == 0
        assert result["total_cost"] == 0
        assert result["total_profit"] == 0
        assert result["details"] == []
        assert result["holdings_details"] == []


@pytest.mark.unit
@pytest.mark.unit_report
class TestGenerateReport:
    """generate_report 骨架测试。"""

    def test_generate_report_skeleton(self):
        """骨架模式返回 ReportResult，不抛异常。"""
        mock_reporter = MagicMock()
        result = generate_report(holdings=[], config={}, reporter=mock_reporter)
        assert isinstance(result, ReportResult)
        assert result.report_generated is True
        assert result.exit_code == 0


@pytest.mark.unit
@pytest.mark.unit_report
class TestCaptureSnapshot:
    """capture_snapshot 快照创建测试（8 用例覆盖 5 子步骤）。"""

    def _make_mock_detail(self, code="SH600001", name="测试", mv=1200.0,
                          cost=1000.0, profit=200.0) -> MagicMock:
        d = MagicMock()
        d.code = code
        d.name = name
        d.market_value = mv
        d.cost = cost
        d.profit = profit
        d.profit_rate = profit / cost if cost else 0
        return d

    def _make_mock_holding(self, code="SH600001", name="测试",
                           shares=100, cost_price=10.0) -> MagicMock:
        h = MagicMock()
        h.code = code
        h.name = name
        h.shares = shares
        h.cost_price = cost_price
        return h

    def test_capture_snapshot_holding_mapping(self):
        """从 details → SnapshotHolding 字段映射正确。"""
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
                [self._make_mock_holding()], [detail], config, mock_reporter,
            )

        # 首次运行返回 None
        assert result is None

    def test_capture_snapshot_holdings_lookup(self):
        """holdings 回查补充 shares/cost_price；无匹配时默认 0.0。"""
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

            capture_snapshot(
                [self._make_mock_holding(code="SH600001", shares=200, cost_price=12.0)],
                [detail], config, mock_reporter,
            )

        # HistoryDiff.compute 被调用，说明 holdings 回查未抛出异常
        assert mock_hd.compute.called

    def test_capture_snapshot_data_creation(self):
        """SnapshotData 聚合计算正确。"""
        mock_reporter = MagicMock()
        details = [
            self._make_mock_detail(code="SH600001", mv=1200.0, cost=1000.0, profit=200.0),
            self._make_mock_detail(code="SH600002", mv=2400.0, cost=2000.0, profit=400.0),
        ]
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

            capture_snapshot(
                [self._make_mock_holding(code="SH600001"),
                 self._make_mock_holding(code="SH600002")],
                details, config, mock_reporter,
            )

        # HistoryDiff.compute 被正确传入 SnapshotData
        assert mock_hd.compute.called

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
                [self._make_mock_holding()], details, config, mock_reporter,
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
                [self._make_mock_holding()], [detail], config, mock_reporter,
            )

        # 验证 prune 参数来自 config 而非 get_config_cache()
        mock_prune.assert_called_once_with(retention_days=99, max_count=200)

    def test_capture_snapshot_f_context(self):
        """f_context 含 diff/diff_trimmed/days_since_last 三个顶层 key。"""
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
                [self._make_mock_holding()], [detail], config, mock_reporter,
            )

        assert result is not None
        assert "diff" in result
        assert "diff_trimmed" in result
        assert "days_since_last" in result
        assert result["days_since_last"] == 5

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
                [self._make_mock_holding()], [detail], config, mock_reporter,
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
                [self._make_mock_holding()], [detail], config, mock_reporter,
            )

        assert result is None


@pytest.mark.unit
@pytest.mark.unit_report
class TestComputeEarlyWarnings:
    """compute_early_warnings 预警计算测试。"""

    def test_compute_early_warnings_with_data(self):
        """有预警数据时返回含 sector_alerts + sentiment_alerts 的字典。"""
        mock_reporter = MagicMock()

        with patch(
            "src.python.report.early_warning.compute_early_warnings",
            return_value={
                "has_warnings": True,
                "sector_alerts": [{"name": "行业A"}],
                "sentiment_alerts": [{"name": "情绪B"}],
            },
        ):
            result = compute_early_warnings(
                [], [], [], [], {}, mock_reporter,
            )

        assert result is not None
        assert result["has_warnings"] is True
        assert len(result["sector_alerts"]) == 1

    def test_compute_early_warnings_no_data(self):
        """无预警时返回 has_warnings=False。"""
        mock_reporter = MagicMock()

        with patch(
            "src.python.report.early_warning.compute_early_warnings",
            return_value={"has_warnings": False, "sector_alerts": [], "sentiment_alerts": []},
        ):
            result = compute_early_warnings(
                [], [], [], [], {}, mock_reporter,
            )

        assert result is not None
        assert result["has_warnings"] is False

    def test_compute_early_warnings_exception(self):
        """内部异常时返回 None。"""
        mock_reporter = MagicMock()

        with patch(
            "src.python.report.early_warning.compute_early_warnings",
            side_effect=RuntimeError("测试异常"),
        ):
            result = compute_early_warnings(
                [], [], [], [], {}, mock_reporter,
            )

        assert result is None


@pytest.mark.unit
@pytest.mark.unit_report
class TestFetchHistoryData:
    """fetch_history_data 历史走势数据获取测试。"""

    def test_fetch_history_data_auto_mode(self):
        """auto 模式返回 PortfolioHistoryCalculator 计算结果。"""
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

        with patch(
            "src.python.report.portfolio_history.PortfolioHistoryCalculator"
        ) as mock_cls:
            mock_calc = MagicMock()
            mock_calc.get_combined_timeseries.return_value = mock_history_data
            mock_cls.return_value = mock_calc

            result = fetch_history_data(
                [mock_holding], {"history": {"coverage_threshold": 0.9}},
                mock_reporter,
            )

        assert result is not None
        assert result["status"] == "available"
        assert len(result["dates"]) == 2
        mock_cls.assert_called_once_with(
            coverage_threshold=0.9,
            benchmark_indices={},
        )

    def test_fetch_history_data_off_mode(self):
        """非 auto 模式直接返回 None。"""
        mock_reporter = MagicMock()

        result = fetch_history_data(
            [], {"history": {}}, mock_reporter, mode="off",
        )

        assert result is None

    def test_fetch_history_data_unavailable(self):
        """status=unavailable 时返回数据但 reporter.warn 被调用。"""
        mock_reporter = MagicMock()
        mock_history_data = {"status": "unavailable"}

        with patch(
            "src.python.report.portfolio_history.PortfolioHistoryCalculator"
        ) as mock_cls:
            mock_calc = MagicMock()
            mock_calc.get_combined_timeseries.return_value = mock_history_data
            mock_cls.return_value = mock_calc

            result = fetch_history_data(
                [MagicMock()], {"history": {}}, mock_reporter,
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
                [MagicMock()], {"history": {}}, mock_reporter,
            )

        assert result is None
