"""因子暴露分析管线场景测试。

覆盖：
  1. compute_factor_exposure_data 返回完整数据契约（available=True，全部 13 键）
  2. 全部因子指数拉取失败 → available=False + status="source_failed"（§1.4.5 ②），不抛异常
  3. 持仓历史为空 → available=False + status="insufficient"（§1.4.5 ①）
  4. _generate_report_full 将 prep.style_factor_data 注入 pipeline_data（HTML/Excel 消费）

约束：
  - 所有外部 API 均为 mock（持仓历史 K 线 / 因子指数 K 线）
  - 不触发真实网络/LLM 调用
  - output_dir 指向临时目录，避免报告产物残留
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.python.core.models import Holding
from src.python.report.orchestrator import compute_factor_exposure_data

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]

_SAMPLE_HOLDINGS = [
    Holding(account="证券", name="长江电力", code="600900", shares=100, cost_price=10.0),
    Holding(account="证券", name="贵州茅台", code="600519", shares=50, cost_price=200.0),
]

_CONTRACT_KEYS = {
    "available",
    "status",
    "betas",
    "t_stats",
    "significant",
    "style_allocation",
    "baseline_betas",
    "factor_correlations",
    "correlation_note",
    "alpha",
    "window",
    "sample_count",
    "stale_factors",
}


def _klines(n: int = 90, start: str = "2026-03-01", base: float = 100.0, step: float = 0.3) -> list[dict]:
    """生成 n 根单调递增的日 K 线（date/close 升序）。"""
    d = date.fromisoformat(start)
    out: list[dict] = []
    for i in range(n):
        out.append({"date": d.isoformat(), "close": round(base + i * step, 3)})
        d += timedelta(days=1)
    return out


def _mock_reporter() -> MagicMock:
    return MagicMock()


class TestComputeFactorExposureData:
    """编排层 compute_factor_exposure_data 场景验证。"""

    def test_c19_contract_available(self):
        """持仓历史 + 因子/基准 K 线齐备 → 返回全部数据契约键且 available=True。"""
        hold_bars = _klines(n=90, base=100.0)
        factor_bars = _klines(n=90, base=100.0, step=0.4)

        def _fake_fallback(chain_name, code, days=30, **kw):
            if chain_name == "history_stock":
                return [dict(b) for b in hold_bars]
            return []

        def _fake_index(code, days=365):
            return [dict(b) for b in factor_bars]

        with (
            patch("src.python.fetcher.chain.fetch_with_incremental_fallback", side_effect=_fake_fallback),
            patch("src.python.fetcher.index.fetch_index_history", side_effect=_fake_index),
        ):
            result = compute_factor_exposure_data(
                _SAMPLE_HOLDINGS, {"enable_fund_deep_analysis": True}, _mock_reporter()
            )

        assert isinstance(result, dict)
        assert set(result.keys()) == _CONTRACT_KEYS, f"数据契约键集不匹配: {_CONTRACT_KEYS - set(result.keys())}"
        assert result["available"] is True
        assert result["status"] == "ok"
        assert set(result["betas"].keys()) == {"value", "growth", "quality"}
        assert result["sample_count"] >= 36
        assert isinstance(result["baseline_betas"], dict)
        assert isinstance(result["style_allocation"], dict)

    def test_all_factors_failed_returns_source_failed(self):
        """全部因子指数 K 线拉取失败 → available=False + status="source_failed"，不抛异常。"""
        hold_bars = _klines(n=90, base=100.0)

        def _fake_fallback(chain_name, code, days=30, **kw):
            if chain_name == "history_stock":
                return [dict(b) for b in hold_bars]
            return []

        with (
            patch("src.python.fetcher.chain.fetch_with_incremental_fallback", side_effect=_fake_fallback),
            patch("src.python.fetcher.index.fetch_index_history", return_value=[]),
        ):
            result = compute_factor_exposure_data(
                _SAMPLE_HOLDINGS, {"enable_fund_deep_analysis": True}, _mock_reporter()
            )

        assert isinstance(result, dict)
        assert result["available"] is False
        assert result["status"] == "source_failed"

    def test_empty_portfolio_returns_insufficient(self):
        """持仓历史为空 → available=False + status="insufficient"（数据不足，§1.4.5 ①）。"""
        with (
            patch("src.python.fetcher.chain.fetch_with_incremental_fallback", return_value=[]),
            patch("src.python.fetcher.index.fetch_index_history", return_value=[]),
        ):
            result = compute_factor_exposure_data(
                _SAMPLE_HOLDINGS, {"enable_fund_deep_analysis": True}, _mock_reporter()
            )

        assert isinstance(result, dict)
        assert result["available"] is False
        assert result["status"] == "insufficient"
        assert result["betas"] == {}

    def test_fund_deep_analysis_disabled_returns_none(self):
        """基金深度分析关闭 → 返回 None（章节隐藏，不发起任何数据拉取）。"""
        with (
            patch("src.python.fetcher.chain.fetch_with_incremental_fallback") as mock_chain,
            patch("src.python.fetcher.index.fetch_index_history") as mock_index,
        ):
            result = compute_factor_exposure_data(
                _SAMPLE_HOLDINGS, {"enable_fund_deep_analysis": False}, _mock_reporter()
            )

        assert result is None
        mock_chain.assert_not_called()
        mock_index.assert_not_called()


class TestPipelineInjection:
    """_generate_report_full 将 prep.style_factor_data 注入 pipeline_data（数据契约 写入阶段）。"""

    def test_full_report_injects_style_factor_data_into_pipeline(self, tmp_path):
        """full 路径 capture_snapshot 后，pipeline_data["style_factor_data"] 从 prep 注入，HTML/Excel 消费。"""
        from src.python.report.orchestrator import generate_report

        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="600900", name="长江电力", shares=100, cost_price=10.0)]
        config = {"output_dir": str(tmp_path / "reports")}

        fe_data = {
            "available": True,
            "status": "ok",
            "betas": {"value": 0.8, "growth": -0.2, "quality": 0.4},
            "t_stats": {"value": 5.2, "growth": -1.1, "quality": 2.3},
            "significant": {"value": True, "growth": False, "quality": True},
            "style_allocation": {"value": 0.57, "growth": 0.14, "quality": 0.29},
            "baseline_betas": {"value": 0.9, "growth": 0.1, "quality": 0.3},
            "factor_correlations": {},
            "correlation_note": "",
            "alpha": 0.0001,
            "window": 60,
            "sample_count": 60,
            "stale_factors": [],
        }

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
                "today_str": "2026-08-01",
                "output_dir": str(tmp_path / "reports"),
                "news_top_count": 100,
                "risk_metrics": {},
                "style_factor_data": fe_data,
            }

            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
            )

        assert result.report_generated is True
        # Excel 收到含 style_factor_data 的 pipeline_data
        excel_kw = mock_excel.call_args.kwargs
        assert excel_kw["pipeline_data"]["style_factor_data"]["available"] is True
        # HTML 收到 style_factor_data kwarg
        html_kw = mock_html.call_args.kwargs
        assert html_kw["style_factor_data"]["betas"]["value"] == 0.8
