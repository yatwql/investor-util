"""管线冒烟 — 申购限购状态契约（purchase_status_data）注入两条报告路径。

对应设计文档 docs/plan/fund-purchase-limit-design.md 验收第 4 条：
`available=false` 时渲染层静默隐列，且报告生成成功（生成器收到契约、不抛异常）。

  - full 路径：prep 契约 → pipeline_data → HTML kwarg / Excel pipeline_data
  - both 路径：编排层就地构建（离线桩下全链失败 → available=False 降级契约）

输出目录重定向临时目录，最小持仓 fixture，渲染器全部 mock（不出网、不落真实报告）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic, pytest.mark.usefixtures("offline_external_sources")]

_SAMPLE_HOLDINGS = [
    Holding(account="证券", name="长江电力", code="600900", shares=100, cost_price=10.0),
]


def _degraded_contract() -> dict:
    """离线桩下全链失败的降级契约（available=False → 静默隐列）。"""
    return {
        "available": False,
        "reason": "申购状态全链路取数失败且无可用缓存",
        "rows": {},
        "fetched_at": None,
        "source": None,
    }


class TestFullPathInjection:
    """full 路径：prepare_report_data 的契约经 pipeline_data 注入 HTML 与 Excel。"""

    def test_full_report_injects_purchase_status_contract(self, tmp_path):
        from src.python.report.orchestrator import generate_report

        contract = _degraded_contract()
        mock_reporter = MagicMock()
        config = {"output_dir": str(tmp_path / "reports")}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data", return_value=None),
            patch("src.python.report.html_writer.write_html_report") as mock_html,
            patch("src.python.report.excel_generator.generate_excel_report") as mock_excel,
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=False),
            patch("src.python.report.news_correlation.build_news_data", return_value=([], {})),
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
                "today_str": "2026-10-01",
                "output_dir": str(tmp_path / "reports"),
                "news_top_count": 100,
                "risk_metrics": {},
                "purchase_status_data": contract,
            }

            result = generate_report(
                holdings=_SAMPLE_HOLDINGS,
                config=config,
                reporter=mock_reporter,
                report_type="full",
            )

        # available=False 契约下报告生成成功（渲染层据此隐列，不抛异常）
        assert result.report_generated is True
        # HTML 收到契约 kwarg（列可见性判据的唯一输入）
        assert mock_html.call_args.kwargs["purchase_status_data"] == contract
        # Excel 经 pipeline_data 收到契约
        assert mock_excel.call_args.kwargs["pipeline_data"]["purchase_status_data"] == contract


class TestBothPathDegrade:
    """both 路径：编排层就地构建契约（离线桩全链失败 → available=False）。"""

    def test_both_report_builds_degraded_contract(self, tmp_path):
        from src.python.report.orchestrator import generate_report

        mock_reporter = MagicMock()
        config = {"output_dir": str(tmp_path / "reports")}

        with (
            patch("src.python.report._report_generation._compute_details", return_value=[]),
            patch("src.python.report._snapshot.capture_snapshot", return_value={}),
            patch("src.python.report._snapshot.fetch_history_data", return_value=None),
            patch("src.python.report.html_writer.write_html_report") as mock_html,
            patch("src.python.report.excel_generator.generate_excel_report") as mock_excel,
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.config.is_enable_news", return_value=False),
            patch("src.python.config.is_enable_history", return_value=False),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=False),
            patch("src.python.config.is_enable_financial_indicator", return_value=False),
            patch("src.python.config.is_enable_financial_report_digest", return_value=False),
            patch("src.python.config.is_enable_portfolio_evolution", return_value=False),
        ):
            result = generate_report(
                holdings=_SAMPLE_HOLDINGS,
                config=config,
                reporter=mock_reporter,
                report_type="both",
                fetch_history=False,
            )

        # 双端均收到契约；离线桩下全链失败 → available=False（静默隐列）
        html_contract = mock_html.call_args.kwargs["purchase_status_data"]
        excel_contract = mock_excel.call_args.kwargs["purchase_status_data"]
        assert html_contract is not None
        assert html_contract["available"] is False
        assert excel_contract == html_contract
        assert result.report_generated is True
