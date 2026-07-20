"""端到端性能测试 — 全量报告生成时间测量。

使用 mock 持仓和 mock API 调用，模拟 20 品种全量报告生成管线，
记录各阶段耗时分布以建立性能基线。

目标：basic 模式 <60s，失败条件 >120s。
测试中所有外部 API 和 LLM 调用均被 mock，实际耗时应远低于阈值。

@pytest.mark.scenario_perf
"""

from __future__ import annotations

import logging
import time
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.scenario_perf]

from src.python.models import Holding
from src.python.report.market_value import DetailRow

logger = logging.getLogger("invest")

# ── 20 品种测试持仓 ─────────────────────────────────────────


@pytest.fixture(scope="module")
def twenty_holdings() -> list[Holding]:
    """20 品种持仓：10 只股票 + 10 只基金。"""
    holdings: list[Holding] = []
    stocks = [
        ("平安银行", "000001", 2000, 12.0),
        ("万科A", "000002", 1500, 18.0),
        ("格力电器", "000651", 1000, 40.0),
        ("招商银行", "600036", 3000, 35.0),
        ("贵州茅台", "600519", 100, 1800.0),
        ("中国平安", "601318", 2000, 50.0),
        ("恒瑞医药", "600276", 1500, 35.0),
        ("伊利股份", "600887", 2500, 28.0),
        ("中信证券", "600030", 1800, 20.0),
        ("海康威视", "002415", 1200, 30.0),
    ]
    funds = [
        ("易方达蓝筹精选", "005827", 5000, 2.5),
        ("中欧医疗健康", "003095", 3000, 3.0),
        ("富国天惠", "161005", 4000, 2.0),
        ("兴全趋势", "163402", 3500, 1.8),
        ("景顺长城", "260108", 2000, 2.2),
        ("广发稳健", "270002", 6000, 1.5),
        ("华夏回报", "002001", 3000, 1.6),
        ("嘉实增长", "070002", 2500, 2.8),
        ("博时主题", "160505", 4000, 1.9),
        ("南方绩优", "202003", 3500, 2.1),
    ]
    for name, code, shares, cost in stocks + funds:
        holdings.append(Holding(name=name, code=code, shares=float(shares), cost_price=cost, account="测试账户"))
    return holdings


@pytest.fixture(scope="module")
def mock_all_apis():
    """Mock 所有外部 API 调用，避免真实网络请求。"""
    patches = [
        patch("src.python.fetcher.price.fetch_market_data", return_value={}),
        patch("src.python.fetcher.akshare.get_profit_forecast", return_value={}),
        patch("src.python.fetcher.akshare.get_dividend_data", return_value={}),
        patch("src.python.fetcher.index.fetch_indices", return_value={}),
        patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
        patch("src.python.fetcher.fund.fetch_fund_holdings", return_value=None),
        patch("src.python.fetcher.fund.fetch_fund_holdings_cached", return_value=None),
        patch("src.python.fetcher.fund.fetch_fund_rankings", return_value=[]),
        patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


# ── 性能测试 ─────────────────────────────────────────────────


class TestE2EPerformance:
    """端到端报告生成性能测试（所有外部调用已 mock）。"""

    @pytest.mark.scenario_perf
    def test_basic_metrics_time(self, twenty_holdings, mock_all_apis):
        """仅指标计算阶段耗时测量。"""
        from src.python.analysis.metrics import compute_all_metrics

        portfolio_returns = [0.001] * 252
        benchmark_returns = [0.0005] * 252
        start = time.perf_counter()
        result = compute_all_metrics(
            portfolio_returns,
            portfolio_weights=[0.1] * 20,
            benchmark_daily_returns=benchmark_returns,
        )
        elapsed = time.perf_counter() - start

        logger.info("指标计算耗时: %.3fs", elapsed)
        assert result is not None
        assert "beta_analysis" in result
        assert elapsed < 10.0, f"指标计算耗时 {elapsed:.2f}s > 10s 阈值"

    @pytest.mark.scenario_perf
    def test_penetration_time(self, twenty_holdings, mock_all_apis):
        """穿透 TOP10 计算耗时测量。"""
        from src.python.report.penetration import compute_penetration_top10

        details = [
            DetailRow(
                name=h.name, code=h.code, market_value=h.shares * h.cost_price,
                cost=h.shares * h.cost_price, profit=0.0, account=h.account,
            )
            for h in twenty_holdings
        ]
        start = time.perf_counter()
        result = compute_penetration_top10(twenty_holdings, details)
        elapsed = time.perf_counter() - start

        logger.info("穿透计算耗时: %.3fs", elapsed)
        assert result is not None
        assert elapsed < 10.0, f"穿透计算耗时 {elapsed:.2f}s > 10s 阈值"

    @pytest.mark.scenario_perf
    def test_scenario_analysis_time(self, twenty_holdings, mock_all_apis):
        """情景分析计算耗时测量。"""
        from src.python.analysis.scenario import scenario_analysis

        start = time.perf_counter()
        result = scenario_analysis(
            portfolio_value=1000000.0,
            beta=0.85,
            beta_ci_lower=0.7,
            beta_ci_upper=1.0,
            portfolio_volatility=0.20,
        )
        elapsed = time.perf_counter() - start

        logger.info("情景分析耗时: %.3fs", elapsed)
        assert result is not None
        assert len(result["scenarios"]) == 6
        assert elapsed < 2.0, f"情景分析耗时 {elapsed:.2f}s > 2s 阈值"

    @pytest.mark.scenario_perf
    def test_excel_report_time(self, twenty_holdings, mock_all_apis, tmp_path):
        """Excel 报告写入耗时测量。"""
        import os

        from openpyxl import Workbook

        from src.python.report.excel_writer import (
            create_workbook,
            save_workbook,
            write_data_row,
            write_header_row,
            write_title_row,
        )

        wb = create_workbook()
        ws = wb.active
        ws.title = "性能测试"
        headers = ["名称", "代码", "市值", "成本", "盈亏"]
        write_title_row(ws, 1, "测试报告", len(headers))
        write_header_row(ws, 2, headers)
        for i, h in enumerate(twenty_holdings):
            mkt_val = h.shares * h.cost_price
            write_data_row(ws, i + 3, [h.name, h.code, mkt_val, h.cost_price, 0.0])

        start = time.perf_counter()
        result_path = save_workbook(wb, str(tmp_path))
        elapsed = time.perf_counter() - start

        logger.info("Excel 报告写入耗时: %.3fs", elapsed)
        assert result_path is not None
        assert os.path.exists(result_path)
        assert elapsed < 30.0, f"Excel 写入耗时 {elapsed:.2f}s > 30s 阈值"

    @pytest.mark.scenario_perf
    def test_full_pipeline_time(self, twenty_holdings, mock_all_apis, tmp_path):
        """全量管线模拟（指标+穿透+情景）耗时总计。"""
        from src.python.analysis.metrics import compute_all_metrics
        from src.python.analysis.scenario import (
            scenario_analysis,
            sharpe_ci_propagation,
        )
        from src.python.report.penetration import compute_penetration_top10

        portfolio_returns = [0.001] * 252
        benchmark_returns = [0.0005] * 252
        details = [
            DetailRow(
                name=h.name, code=h.code, market_value=h.shares * h.cost_price,
                cost=h.shares * h.cost_price, profit=0.0, account=h.account,
            )
            for h in twenty_holdings
        ]

        start = time.perf_counter()

        metrics = compute_all_metrics(
            portfolio_returns,
            portfolio_weights=[0.1] * 20,
            benchmark_daily_returns=benchmark_returns,
        )
        penetration = compute_penetration_top10(twenty_holdings, details)
        scenario = scenario_analysis(
            portfolio_value=1000000.0,
            beta=metrics.get("portfolio_beta"),
            portfolio_volatility=0.20,
        )
        sharpe_ci = sharpe_ci_propagation(
            sharpe_ratio=metrics.get("sharpe_ratio"),
            annual_volatility=0.20,
            years_of_data=1.0,
        )

        elapsed = time.perf_counter() - start
        logger.info("全量管线耗时: %.3fs", elapsed)
        assert elapsed < 60.0, f"全量管线耗时 {elapsed:.2f}s > 60s 阈值（失败条件 120s）"
        assert metrics is not None
        assert penetration is not None
        assert scenario is not None
        assert sharpe_ci is not None
