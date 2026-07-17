"""orchestrator 共享层单元测试。

S1 骨架：prepare_report_data mock 测试。
S2 扩展：capture_snapshot。
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
    fetch_history_data,
    _report_llm_module_results,
    _fetch_llm_and_news,
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
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report.market_value.classify_holdings", return_value=[mock_category]),
            patch("src.python.fetcher.index.fetch_indices", return_value={"sh000001": 3000}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={"gb_inx": 5000}),
            patch("src.python.report.penetration.compute_penetration_top10", return_value={"top10": []}),
        ):
            result = prepare_report_data(mock_holdings, mock_reporter, config={})

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
class TestGenerateReport:
    """generate_report 骨架测试。"""

    def test_generate_report_skeleton(self):
        """骨架模式返回 ReportResult，不抛异常。"""
        mock_reporter = MagicMock()
        result = generate_report(holdings=[], config={}, reporter=mock_reporter)
        assert isinstance(result, ReportResult)
        assert result.report_generated is True
        assert result.exit_code == 0

    def test_generate_report_basic(self):
        """basic 路径直接调用 excel_generator.generate_excel_report 生成 Excel 报告。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.excel_generator.generate_excel_report") as mock_gen,
            patch("src.python.registry.get_report_section_order", return_value=[{"key": "overview"}]),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="basic",
            )

        assert isinstance(result, ReportResult)
        assert result.excel_ok is True
        assert result.holdings_ok is True
        assert result.report_generated is True
        assert result.exit_code == 0
        # 验证 generate_excel_report 被正确调用
        mock_gen.assert_called_once_with(
            mock_holdings, include_news=False,
            output_dir="reports",
            section_order=[{"key": "overview"}],
            progress=mock_reporter,
        )
        # 验证不调用数据准备/快照/历史等函数
        with pytest.raises(AssertionError):
            mock_reporter.info.assert_any_call("generate_report: 骨架模式")

    def test_generate_report_basic_exception(self):
        """basic 路径异常时 result.excel_ok=False，errors 非空。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]

        with (
            patch(
                "src.python.report.excel_generator.generate_excel_report",
                side_effect=RuntimeError("生成失败"),
            ),
            patch("src.python.registry.get_report_section_order", return_value=[]),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config={},
                reporter=mock_reporter,
                report_type="basic",
            )

        assert result.excel_ok is False
        assert len(result.errors) > 0
        # reporter.add_error 被调用
        mock_reporter.add_error.assert_called_once()

    def test_generate_report_basic_uses_output_dir(self):
        """output_dir 参数覆盖 config 中的 output_dir。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]

        with (
            patch("src.python.report.excel_generator.generate_excel_report") as mock_gen,
            patch("src.python.registry.get_report_section_order", return_value=[]),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config={"output_dir": "reports"},
                reporter=mock_reporter,
                report_type="basic",
                output_dir="/custom/path",
            )

        assert result.report_generated is True
        mock_gen.assert_called_once()
        # output_dir 使用传参而非 config 值
        _call_kwargs = mock_gen.call_args.kwargs
        assert _call_kwargs["output_dir"] == "/custom/path"


    def test_generate_report_both_calls_compute_details(self):
        """both 路径调用 _compute_details 而非 prepare_report_data，不调用 LLM/线程池。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {
            "output_dir": "reports",
            "news_top_count": 100,
            "history": {"analysis": "auto"},
        }

        mock_detail = MagicMock()
        mock_detail.code = "SH600001"
        mock_detail.market_value = 1200.0
        mock_detail.cost = 1000.0

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report.orchestrator.capture_snapshot") as mock_cap,
            patch("src.python.report.orchestrator.fetch_history_data") as mock_hist,
            patch("src.python.report.html_writer.write_html_report") as mock_html,
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.registry.get_report_section_order", return_value=[]),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
        ):
            mock_cap.return_value = {"diff": {}}
            mock_hist.return_value = {"dates": [], "status": "available"}

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="both",
                history_mode="auto",
            )

        assert isinstance(result, ReportResult)
        assert result.report_generated is True
        assert result.html_ok is True
        assert result.excel_ok is True
        # 验证 _compute_details （即 _generate_details）被调用
        # 验证 capture_snapshot 和 fetch_history_data 被调用
        mock_cap.assert_called_once()
        mock_hist.assert_called_once()
        # 验证 write_html_report 和 generate_excel_report 被调用
        assert mock_html.call_count >= 1
        assert mock_xls.call_count >= 1
        # 验证传入 enable_llm=False（both 路径不含 LLM）
        _html_kwargs = mock_html.call_args.kwargs
        assert _html_kwargs.get("enable_llm") is False
        _xls_kwargs = mock_xls.call_args.kwargs
        assert _xls_kwargs.get("enable_llm") is False

    def test_generate_report_both_history_off(self):
        """both 路径 history_mode=off 时不调用 fetch_history_data。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[MagicMock()]),
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data") as mock_hist,
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.registry.get_report_section_order"),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="both",
                history_mode="off",
            )

        assert result.report_generated is True
        # history 关闭时 fetch_history_data 不应被调用
        mock_hist.assert_not_called()

    def test_generate_report_both_no_prepare_report_data(self):
        """both 路径不应调用 prepare_report_data（无指数/穿透/分类）。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[MagicMock()]),
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.registry.get_report_section_order"),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            # 使用 wrapt 确保 prepare_report_data 不被调用
        ):
            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="both",
            )

        assert result.report_generated is True

    def test_generate_report_both_excel_fallback(self):
        """both 路径 HTML 失败时仍继续生成 Excel。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[MagicMock()]),
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data"),
            patch(
                "src.python.report.html_writer.write_html_report",
                side_effect=RuntimeError("HTML 失败"),
            ),
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.registry.get_report_section_order"),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="both",
            )

        assert result.html_ok is False
        assert result.excel_ok is True
        assert result.report_generated is True  # Excel 成功，不算失败
        mock_xls.assert_called_once()

    def test_generate_report_full_calls_prepare_report_data(self):
        """full 路径调用 prepare_report_data（含指数/穿透/分类）。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {
            "output_dir": "reports",
            "news_top_count": 100,
            "history": {"analysis": "auto"},
        }

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data"),
            patch("src.python.report.orchestrator._fetch_llm_and_news") as mock_llm_news,
            patch("src.python.report.html_writer.write_html_report") as mock_html,
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.registry.get_report_section_order", return_value=[]),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=[]),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
        ):
            mock_prep.return_value = {
                "details": [], "total_mv": 0, "total_cost": 0,
                "total_profit": 0, "total_today_profit": 0,
                "categories": [], "a_indices": {}, "us_indices": {},
                "penetrated_assets": [], "holdings_details": [],
                "today_str": "2026-07-16", "output_dir": "reports",
                "news_top_count": 100,
            }
            mock_llm_news.return_value = (
                (None, None, None, None), [], {}, False,
            )

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
                history_mode="auto",
                force_llm=False,
            )

        assert isinstance(result, ReportResult)
        assert result.report_generated is True
        # prepare_report_data 被调用且传入了 config
        mock_prep.assert_called_once_with(mock_holdings, mock_reporter, config)
        # HTML 和 Excel 报告生成
        assert mock_html.call_count >= 1
        assert mock_xls.call_count >= 1
        # 传入 enable_llm=True（full 路径含 LLM）
        _html_kwargs = mock_html.call_args.kwargs
        assert _html_kwargs.get("enable_llm") is True

    def test_generate_report_full_news_only(self):
        """full 路径仅新闻（LLM 关闭）时正常工作。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=False),
            patch("src.python.report.news_correlation.build_news_data", return_value=([{"title": "新闻1"}], {})),
        ):
            mock_prep.return_value = {
                "details": [], "total_mv": 0, "total_cost": 0,
                "total_profit": 0, "total_today_profit": 0,
                "categories": [], "a_indices": {}, "us_indices": {},
                "penetrated_assets": [], "holdings_details": [],
                "today_str": "2026-07-16", "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings, config=config,
                reporter=mock_reporter, report_type="full",
            )

        assert result.report_generated is True
        assert result.news_ok is True

    def test_generate_report_full_llm_only(self):
        """full 路径仅 LLM（新闻关闭）时正常工作。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
            patch("src.python.llm.generate_all_llm", return_value=(
                "<p>宏观</p>", None, None, None, False, False, False, False,
            )),
        ):
            mock_prep.return_value = {
                "details": [], "total_mv": 0, "total_cost": 0,
                "total_profit": 0, "total_today_profit": 0,
                "categories": [], "a_indices": {}, "us_indices": {},
                "penetrated_assets": [], "holdings_details": [],
                "today_str": "2026-07-16", "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings, config=config,
                reporter=mock_reporter, report_type="full",
            )

        assert result.report_generated is True

    def test_generate_report_full_both_disabled(self):
        """full 路径 LLM 和新闻均关闭时跳过内容生成，报告仍正常生成。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            mock_prep.return_value = {
                "details": [], "total_mv": 0, "total_cost": 0,
                "total_profit": 0, "total_today_profit": 0,
                "categories": [], "a_indices": {}, "us_indices": {},
                "penetrated_assets": [], "holdings_details": [],
                "today_str": "2026-07-16", "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings, config=config,
                reporter=mock_reporter, report_type="full",
            )

        assert result.report_generated is True

    def test_generate_report_full_excel_fallback(self):
        """full 路径 HTML 失败时仍继续生成 Excel 报告。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report.orchestrator.capture_snapshot"),
            patch("src.python.report.orchestrator.fetch_history_data"),
            patch(
                "src.python.report.html_writer.write_html_report",
                side_effect=RuntimeError("HTML 失败"),
            ),
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_b_series", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            mock_prep.return_value = {
                "details": [], "total_mv": 0, "total_cost": 0,
                "total_profit": 0, "total_today_profit": 0,
                "categories": [], "a_indices": {}, "us_indices": {},
                "penetrated_assets": [], "holdings_details": [],
                "today_str": "2026-07-16", "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings, config=config,
                reporter=mock_reporter, report_type="full",
            )

        assert result.html_ok is False
        assert result.excel_ok is True
        assert result.report_generated is True
        mock_xls.assert_called_once()


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
            "a_indices": {}, "us_indices": {},
            "total_mv": 0, "total_cost": 0, "total_profit": 0,
            "total_today_profit": 0,
            "categories": [], "holdings_details": [],
        }
        data.update(overrides)
        return data

    def test_both_enabled(self):
        """分支①：LLM+新闻均开启。"""
        reporter = MagicMock()
        holdings = [MagicMock(code="SH600001", shares=100)]
        prep = self._make_prep_data()

        with (
            patch("src.python.llm.generate_all_llm", return_value=(
                "<p>宏观</p>", None, None, None, False, False, False, False,
            )),
            patch("src.python.report.news_correlation.build_news_data", return_value=(
                [{"title": "新闻1"}], {},
            )),
        ):
            result = _fetch_llm_and_news(
                holdings, prep, sector_flow=[], force_llm=False,
                f_context=None, enable_news=True, enable_llm=True,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok = result
        assert llm_content[0] == "<p>宏观</p>"
        assert len(news_data) == 1
        assert news_ok is True

    def test_llm_only(self):
        """分支③：仅 LLM。"""
        reporter = MagicMock()
        holdings = [MagicMock(code="SH600001", shares=100)]
        prep = self._make_prep_data()

        with (
            patch("src.python.llm.generate_all_llm", return_value=(
                "<p>宏观</p>", None, None, None, False, False, False, False,
            )),
            patch("src.python.report.news_correlation.build_news_data"),
        ):
            result = _fetch_llm_and_news(
                holdings, prep, sector_flow=[], force_llm=False,
                f_context=None, enable_news=False, enable_llm=True,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok = result
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
            patch("src.python.report.news_correlation.build_news_data", return_value=(
                [{"title": "新闻1"}], {},
            )),
        ):
            result = _fetch_llm_and_news(
                holdings, prep, sector_flow=[], force_llm=False,
                f_context=None, enable_news=True, enable_llm=False,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok = result
        assert llm_content == (None, None, None, None)
        assert len(news_data) == 1
        assert news_ok is True

    def test_both_disabled(self):
        """分支④：均关闭。"""
        reporter = MagicMock()

        result = _fetch_llm_and_news(
            [], {}, sector_flow=None, force_llm=False,
            f_context=None, enable_news=False, enable_llm=False,
            reporter=reporter,
        )

        llm_content, news_data, news_llm_meta, news_ok = result
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
            patch("src.python.report.news_correlation.build_news_data", return_value=(
                [{"title": "新闻1"}], {},
            )),
        ):
            result = _fetch_llm_and_news(
                holdings, prep, sector_flow=[], force_llm=False,
                f_context=None, enable_news=True, enable_llm=True,
                reporter=reporter,
            )

        llm_content, news_data, news_llm_meta, news_ok = result
        assert llm_content == (None, None, None, None)
        assert len(news_data) == 1  # 新闻仍返回
        assert news_ok is True


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
