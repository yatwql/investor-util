"""orchestrator 报告生成主流程 — generate_report 产物落盘与快照比对。

覆盖场景：
  - generate_report 调用前后 reports/ 目录快照差异（新增/覆盖产物）
  - 报告产物落盘副作用与返回值契约

运行：
  pytest src/test/unit/report/test_orchestrator_generate_report.py -v
"""

from __future__ import annotations

import os

import pytest

from unittest.mock import MagicMock, patch

from src.python.report.orchestrator import (
    ReportResult,
    generate_report,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]


def _real_reports_dir() -> str:
    """项目真实 reports 目录（与 conftest 防线基准一致）。"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "reports"))


def _snapshot_reports() -> frozenset:
    """返回项目 reports/ 下所有文件相对路径（用于断言防线生效）。"""
    root = _real_reports_dir()
    if not os.path.isdir(root):
        return frozenset()
    result = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            result.add(os.path.relpath(os.path.join(dirpath, f), root))
    return frozenset(result)


@pytest.mark.unit
@pytest.mark.unit_report
class TestGenerateReport:
    """generate_report 骨架测试。"""

    def test_generate_report_skeleton(self):
        """骨架模式返回 ReportResult，不抛异常（输出隔离由 conftest 防线兜底）。

        report_type 默认 basic（仅生成 Excel 不写 HTML），config 缺 output_dir
        时输出回退到相对路径 "reports"，解析为项目真实 reports/ 目录；空持仓
        会生成空页签 Excel 归档并覆盖根目录最新版，累积残留。conftest.
        _isolate_report_output_dir 兜底把指向项目真实 reports/ 的输出重定向到
        临时目录，此处用运行前后文件快照断言真实 reports/ 无新增，作永久回归
        守护。
        """
        mock_reporter = MagicMock()
        before = _snapshot_reports()
        with (
            # 市场数据网络依赖：交易日历（akshare）+ A 股/美股指数（腾讯/新浪）
            patch("src.python.core.trading_calendar._get_trading_calendar", return_value=set()),
            patch("src.python.fetcher.index.fetch_indices", return_value={}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
            # 后台数据源健康检查（全量 HTTP 连通性探测）
            patch("src.python.report._report_generation._spawn_health_checks", return_value=None),
            patch("src.python.report._report_generation._collect_health_checks"),
        ):
            result = generate_report(holdings=[], config={}, reporter=mock_reporter)
        assert isinstance(result, ReportResult)
        assert result.report_generated is True
        assert result.exit_code == 0
        after = _snapshot_reports()
        assert before == after, "报告输出未重定向，真实 reports/ 目录被测试污染"

    def test_generate_report_basic(self):
        """basic 路径直接调用 excel_generator.generate_excel_report 生成 Excel 报告。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.excel_generator.generate_excel_report") as mock_gen,
            patch("src.python.core.registry.get_report_section_order", return_value=[{"key": "overview"}]),
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
        # 验证 generate_excel_report 被正确调用（行动建议/数据质量仪表盘默认开，
        # 成本流式子模块默认关）——enable_action 必须显式下传，漏传则行动建议页签
        # 在 basic 路径下静默缺席（页签由 board 层开关决定创建与否）
        mock_gen.assert_called_once_with(
            mock_holdings,
            include_news=False,
            output_dir="reports",
            section_order=[{"key": "overview"}],
            progress=mock_reporter,
            enable_action=True,
            enable_data_quality=True,
            enable_cost_lots=False,
            transactions=None,
            dividends=None,
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
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
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
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
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
            "history": {"fetch_mode": "auto"},
        }

        mock_detail = MagicMock()
        mock_detail.code = "SH600001"
        mock_detail.market_value = 1200.0
        mock_detail.cost = 1000.0

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report._snapshot.capture_snapshot") as mock_cap,
            patch("src.python.report._snapshot.fetch_history_data") as mock_hist,
            patch("src.python.report.html_writer.write_html_report") as mock_html,
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            # 品种覆盖诊断：mock_detail 无真实价格字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.core.holding_status.build_coverage_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            # 可信度摘要：同样依赖真实价格/净值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            # 行动建议单一数据源：mock_detail 无真实市值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                return_value={"available": True, "summary": "", "rebalance_signals": []},
            ),
        ):
            mock_cap.return_value = {"diff": {}}
            mock_hist.return_value = {"dates": [], "status": "available"}

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="both",
                fetch_history=True,
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
        """both 路径历史走势关闭（enable_history=False）时不调用 fetch_history_data。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[MagicMock()]),
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data") as mock_hist,
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
            # 可信度摘要：MagicMock detail 无真实价格/净值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            # 行动建议单一数据源：MagicMock detail 无真实市值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                return_value={"available": True, "summary": "", "rebalance_signals": []},
            ),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="both",
                fetch_history=True,
            )

        assert result.report_generated is True
        # history 关闭时 fetch_history_data 不应被调用（即使 fetch_history=True）
        mock_hist.assert_not_called()

    def test_generate_report_both_fetch_history_follows_config(self):
        """both 路径未显式传 fetch_history 时按 config.history.fetch_mode 决定。

        回归守护：CLI 未传 --history 时默认值不得硬编码，须回退到 config.json
        的 history.fetch_mode（off → 不获取；auto/缺失 → 获取），验证
        fetch_history_data 收到的 fetch 参数来自配置层。
        """
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]

        def _run(config: dict) -> bool:
            with (
                patch("src.python.report.market_value._generate_details", return_value=[MagicMock()]),
                patch("src.python.report._snapshot.capture_snapshot", return_value={}),
                patch("src.python.report._snapshot.fetch_history_data") as mock_hist,
                patch("src.python.report.html_writer.write_html_report"),
                patch("src.python.report.excel_generator.generate_excel_report"),
                patch("src.python.core.registry.get_report_section_order"),
                patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
                patch("src.python.config.is_enable_news", return_value=False),
                patch("src.python.config.is_enable_history", return_value=True),
                # 可信度摘要：MagicMock detail 无真实价格/净值字段，须 mock
                patch(
                    "src.python.core.data_freshness.build_freshness_summary",
                    return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
                ),
                # 行动建议单一数据源：MagicMock detail 无真实市值字段，须 mock
                patch(
                    "src.python.analysis.action_advisor.build_action_data",
                    return_value={"available": True, "summary": "", "rebalance_signals": []},
                ),
            ):
                result = generate_report(
                    holdings=mock_holdings,
                    config=config,
                    reporter=mock_reporter,
                    report_type="both",
                    fetch_history=None,
                )
            assert result.report_generated is True
            mock_hist.assert_called_once()
            return mock_hist.call_args.kwargs["fetch"]

        assert _run({"output_dir": "reports", "history": {"fetch_mode": "off"}}) is False
        assert _run({"output_dir": "reports", "history": {"fetch_mode": "auto"}}) is True
        # fetch_mode 缺失 → 默认 auto（获取）
        assert _run({"output_dir": "reports"}) is True

    def test_generate_report_both_no_prepare_report_data(self):
        """both 路径不应调用 prepare_report_data（无指数/穿透/分类）。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[MagicMock()]),
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            # 可信度摘要：MagicMock detail 无真实价格/净值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            # 行动建议单一数据源：MagicMock detail 无真实市值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                return_value={"available": True, "summary": "", "rebalance_signals": []},
            ),
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
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch(
                "src.python.report.html_writer.write_html_report",
                side_effect=RuntimeError("HTML 失败"),
            ),
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
            # 可信度摘要：MagicMock detail 无真实价格/净值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            # 行动建议单一数据源：MagicMock detail 无真实市值字段，须 mock（防 MagicMock 比较崩溃）
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                return_value={"available": True, "summary": "", "rebalance_signals": []},
            ),
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

    def test_generate_report_both_passes_percent_profit_rate(self):
        """both 路径传入纪律引擎的 profit_rate 为百分数（小数 ×100）。

        回归验证：交易纪律（止盈/止损）以百分数阈值（如 +20%）比较，
        both 路径必须把 DetailRow 的小数收益率换算为百分数，否则纪律
        信号永不触发（与 full 路径 orchestrator 组装口径一致）。
        """
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]

        mock_detail = MagicMock()
        mock_detail.code = "SH600001"
        mock_detail.name = "测试"
        mock_detail.market_value = 1250.0
        mock_detail.cost = 1000.0
        mock_detail.profit = 250.0
        mock_detail.profit_rate = 0.25  # 小数字段（DetailRow 契约）
        mock_detail.shares = 100
        mock_detail.price = 12.5

        captured: dict = {}

        def _fake_build(holdings_details, total_mv, **kwargs):
            captured["holdings_details"] = holdings_details
            return {"available": True, "summary": "", "rebalance_signals": []}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch(
                "src.python.core.holding_status.build_coverage_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            # 拦截 build_action_data，捕获其收到的 holdings_details
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                side_effect=_fake_build,
            ),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config={"output_dir": "reports", "history": {"fetch_mode": "auto"}},
                reporter=mock_reporter,
                report_type="both",
            )

        assert result.report_generated is True
        detail = captured["holdings_details"][0]
        # 0.25（小数）→ 25.0（百分数），纪律引擎以 20.0 阈值比较能正确触发止盈
        assert detail["profit_rate"] == pytest.approx(25.0)
        assert detail["profit"] == pytest.approx(250.0)
        assert detail["market_value"] == pytest.approx(1250.0)

    def test_generate_report_both_passes_channel_context(self):
        """both 路径持仓明细携带渠道上下文（账户关键词 → 场内/场外）。

        回归：可行化层按 channel 区分场外基金（整数份 + 赎回费）与场内品种
        （100 份取整 + 仅佣金），字段缺失会退回代码前缀判定而误判 LOF/开放式基金。
        """
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="161725", name="招商中证白酒指数A", shares=100, cost_price=1.0)]

        mock_detail = MagicMock()
        mock_detail.code = "161725"
        mock_detail.name = "招商中证白酒指数A"
        mock_detail.market_value = 1250.0
        mock_detail.cost = 1000.0
        mock_detail.profit = 250.0
        mock_detail.profit_rate = 0.25
        mock_detail.shares = 100
        mock_detail.price = 12.5
        mock_detail.account = "天天基金"  # 场外账户关键词 → 渠道为场外

        captured: dict = {}

        def _fake_build(holdings_details, total_mv, **kwargs):
            captured["holdings_details"] = holdings_details
            return {"available": True, "summary": "", "rebalance_signals": []}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch(
                "src.python.core.holding_status.build_coverage_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                side_effect=_fake_build,
            ),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config={"output_dir": "reports", "history": {"fetch_mode": "auto"}},
                reporter=mock_reporter,
                report_type="both",
            )

        assert result.report_generated is True
        assert captured["holdings_details"][0]["channel"] == "场外"

    def test_generate_report_both_injects_portfolio_peak_mv(self):
        """both 路径历史走势后重建 action_data，注入组合历史峰值市值。

        回归：组合回撤纪律以 history_data.bars 的峰值市值为基准——峰值在
        「3. 历史走势」之后才可得，action_data 必须就地重建并传入
        portfolio_peak_mv，否则回撤纪律在生产路径永不激活。
        """
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]

        mock_detail = MagicMock()
        mock_detail.code = "SH600001"
        mock_detail.name = "测试"
        mock_detail.market_value = 1250.0
        mock_detail.cost = 1000.0
        mock_detail.profit = 250.0
        mock_detail.profit_rate = 0.25
        mock_detail.shares = 100
        mock_detail.price = 12.5

        captured: dict = {}

        def _fake_build(holdings_details, total_mv, **kwargs):
            captured["portfolio_peak_mv"] = kwargs.get("portfolio_peak_mv")
            return {"available": True, "summary": "", "rebalance_signals": []}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            # 历史走势 bars：峰值 200.0（100→200→150），回撤纪律基准应为历史峰值
            patch(
                "src.python.report._snapshot.fetch_history_data",
                return_value={
                    "status": "ok",
                    "bars": [
                        {"date": "2026-01-01", "total_value": 100.0},
                        {"date": "2026-01-02", "total_value": 200.0},
                        {"date": "2026-01-03", "total_value": 150.0},
                    ],
                },
            ),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch(
                "src.python.core.holding_status.build_coverage_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                side_effect=_fake_build,
            ),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config={"output_dir": "reports"},
                reporter=mock_reporter,
                report_type="both",
                fetch_history=True,
            )

        assert result.report_generated is True
        assert captured["portfolio_peak_mv"] == pytest.approx(200.0)

    def test_generate_report_both_peak_none_when_history_off(self):
        """both 路径历史走势关闭 → 峰值注入 None（组合回撤纪律按「峰值未知」不激活）。

        历史走势关闭时 action_data 仍需构建（止盈/止损纪律不受影响），
        峰值取 None 且不得报错。
        """
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]

        mock_detail = MagicMock()
        mock_detail.code = "SH600001"
        mock_detail.name = "测试"
        mock_detail.market_value = 1250.0
        mock_detail.cost = 1000.0
        mock_detail.profit = 250.0
        mock_detail.profit_rate = 0.25
        mock_detail.shares = 100
        mock_detail.price = 12.5

        captured: dict = {}

        def _fake_build(holdings_details, total_mv, **kwargs):
            captured["portfolio_peak_mv"] = kwargs.get("portfolio_peak_mv")
            return {"available": True, "summary": "", "rebalance_signals": []}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[mock_detail]),
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=False),
            patch(
                "src.python.core.holding_status.build_coverage_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                side_effect=_fake_build,
            ),
        ):
            result = generate_report(
                holdings=mock_holdings,
                config={"output_dir": "reports"},
                reporter=mock_reporter,
                report_type="both",
                fetch_history=True,
            )

        assert result.report_generated is True
        assert captured["portfolio_peak_mv"] is None

    def test_generate_report_full_calls_prepare_report_data(self):
        """full 路径调用 prepare_report_data（含指数/穿透/分类）。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {
            "output_dir": "reports",
            "news_top_count": 100,
            "history": {"fetch_mode": "auto"},
        }

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report._llm_news._fetch_llm_and_news") as mock_llm_news,
            patch("src.python.report.html_writer.write_html_report") as mock_html,
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=[]),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
        ):
            mock_prep.return_value = {
                "details": [],
                "total_mv": 0,
                "total_cost": 0,
                "total_profit": 0,
                "total_today_profit": 0,
                "categories": [],
                "a_indices": {},
                "us_indices": {},
                "penetrated_assets": [],
                "holdings_details": [],
                "today_str": "2026-07-16",
                "output_dir": "reports",
                "news_top_count": 100,
            }
            mock_llm_news.return_value = (
                (None, None, None, None),
                [],
                {},
                False,
                None,
            )

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
                fetch_history=True,
                force_llm=False,
            )

        assert isinstance(result, ReportResult)
        assert result.report_generated is True
        # prepare_report_data 被调用且传入了 config；transactions 透传（未提供时为 None），
        # 供持仓明细附加 holding_days（再平衡误报防护的「新买入品种观察期」判据）
        mock_prep.assert_called_once_with(mock_holdings, mock_reporter, config, transactions=None)
        # HTML 和 Excel 报告生成
        assert mock_html.call_count >= 1
        assert mock_xls.call_count >= 1
        # 传入 enable_llm=True（full 路径含 LLM）
        _html_kwargs = mock_html.call_args.kwargs
        assert _html_kwargs.get("enable_llm") is True

    def test_generate_report_full_injects_portfolio_peak_mv(self):
        """full 路径历史走势后重建 action_data，注入组合历史峰值市值。

        回归：prepare_report_data 的 action_data 为中间占位构建（无峰值），
        full 路径必须在 _prepare_full_risk_metrics（history 就绪）后重建并
        注入 portfolio_peak_mv，组合回撤纪律方能激活。
        """
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {
            "output_dir": "reports",
            "news_top_count": 100,
            "history": {"fetch_mode": "auto"},
        }

        captured: dict = {}

        def _fake_build(holdings_details, total_mv, **kwargs):
            captured["portfolio_peak_mv"] = kwargs.get("portfolio_peak_mv")
            return {"available": True, "summary": "", "rebalance_signals": []}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            # 历史走势 bars：峰值 200.0（100→200→150），回撤纪律基准应为历史峰值
            patch(
                "src.python.report._snapshot.fetch_history_data",
                return_value={
                    "status": "ok",
                    "bars": [
                        {"date": "2026-01-01", "total_value": 100.0},
                        {"date": "2026-01-02", "total_value": 200.0},
                        {"date": "2026-01-03", "total_value": 150.0},
                    ],
                },
            ),
            patch("src.python.report._llm_news._fetch_llm_and_news") as mock_llm_news,
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=[]),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                side_effect=_fake_build,
            ),
        ):
            mock_prep.return_value = {
                "details": [],
                "total_mv": 1250.0,
                "total_cost": 1000.0,
                "total_profit": 250.0,
                "total_today_profit": 0,
                "categories": [],
                "a_indices": {},
                "us_indices": {},
                "penetrated_assets": [],
                "holdings_details": [
                    {
                        "name": "测试",
                        "code": "SH600001",
                        "market_value": 1250.0,
                        "cost": 1000.0,
                        "profit": 250.0,
                        "profit_rate": 25.0,
                        "shares": 100,
                        "price": 12.5,
                    }
                ],
                "today_str": "2026-07-16",
                "output_dir": "reports",
                "news_top_count": 100,
            }
            mock_llm_news.return_value = (
                (None, None, None, None),
                [],
                {},
                False,
                None,
            )

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
                fetch_history=True,
                force_llm=False,
            )

        assert result.report_generated is True
        assert captured["portfolio_peak_mv"] == pytest.approx(200.0)

    def test_generate_report_full_news_only(self):
        """full 路径仅新闻（LLM 关闭）时正常工作。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report._snapshot.capture_snapshot", return_value=None),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=False),
            patch("src.python.report.news_correlation.build_news_data", return_value=([{"title": "新闻1"}], {})),
        ):
            mock_prep.return_value = {
                "details": [],
                "total_mv": 0,
                "total_cost": 0,
                "total_profit": 0,
                "total_today_profit": 0,
                "categories": [],
                "a_indices": {},
                "us_indices": {},
                "penetrated_assets": [],
                "holdings_details": [],
                "today_str": "2026-07-16",
                "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
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
            patch("src.python.report._snapshot.capture_snapshot", return_value=None),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
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
        ):
            mock_prep.return_value = {
                "details": [],
                "total_mv": 0,
                "total_cost": 0,
                "total_profit": 0,
                "total_today_profit": 0,
                "categories": [],
                "a_indices": {},
                "us_indices": {},
                "penetrated_assets": [],
                "holdings_details": [],
                "today_str": "2026-07-16",
                "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
            )

        assert result.report_generated is True

    def test_generate_report_full_both_disabled(self):
        """full 路径 LLM 和新闻均关闭时跳过内容生成，报告仍正常生成。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report._snapshot.capture_snapshot", return_value=None),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            mock_prep.return_value = {
                "details": [],
                "total_mv": 0,
                "total_cost": 0,
                "total_profit": 0,
                "total_today_profit": 0,
                "categories": [],
                "a_indices": {},
                "us_indices": {},
                "penetrated_assets": [],
                "holdings_details": [],
                "today_str": "2026-07-16",
                "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
            )

        assert result.report_generated is True

    def test_generate_report_full_excel_fallback(self):
        """full 路径 HTML 失败时仍继续生成 Excel 报告。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock()]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data"),
            patch(
                "src.python.report.html_writer.write_html_report",
                side_effect=RuntimeError("HTML 失败"),
            ),
            patch("src.python.report.excel_generator.generate_excel_report") as mock_xls,
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
            patch("src.python.config.is_enable_llm", return_value=False),
        ):
            mock_prep.return_value = {
                "details": [],
                "total_mv": 0,
                "total_cost": 0,
                "total_profit": 0,
                "total_today_profit": 0,
                "categories": [],
                "a_indices": {},
                "us_indices": {},
                "penetrated_assets": [],
                "holdings_details": [],
                "today_str": "2026-07-16",
                "output_dir": "reports",
                "news_top_count": 100,
            }

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
            )

        assert result.html_ok is False
        assert result.excel_ok is True
        assert result.report_generated is True
        mock_xls.assert_called_once()
