"""口径修正因子计算模块测试。

测试策略：
  - cash_stripping() 覆盖空输入/全额现金/无现金/现金剥离计算/日收益率剥离
  - twr_calculation() 覆盖空/单期/多期/无效期间/年化计算
  - compute_alignment_factors() 整合入口验证摘要拼接
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

from src.python.analysis.alignment_correction import (
    cash_stripping,
    compute_alignment_factors,
    twr_calculation,
)


# ── cash_stripping 测试 ────────────────────────────────────────


class TestCashStripping:
    """现金剥离功能测试。"""

    def test_empty_holdings(self):
        """空持仓列表 → has_data=False + warning。"""
        result = cash_stripping([])
        assert result["has_data"] is False
        assert result["cash_allocation_pct"] == 0.0
        assert result["equity_allocation_pct"] == 0.0
        assert result["cash_holdings"] == []
        assert "持仓数据不足" in (result["warning"] or "")

    def test_total_mv_zero(self):
        """总市值为 0 → has_data=False。"""
        result = cash_stripping([{"name": "某某股票", "code": "600001", "market_value": 0}])
        assert result["has_data"] is False
        assert "总市值为零" in (result["warning"] or "")

    def test_no_cash_holdings(self):
        """全部为权益类品种 → cash_allocation_pct=0。"""
        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 100000},
            {"name": "腾讯控股", "code": "00700", "market_value": 50000},
        ]
        result = cash_stripping(holdings)
        assert result["has_data"] is True
        assert result["cash_allocation_pct"] == 0.0
        assert result["equity_allocation_pct"] == 1.0
        assert result["cash_holdings"] == []
        assert "未识别出现金管理品种" in (result["warning"] or "")

    def test_cash_keyword_match(self):
        """名称含"货币"关键词 → 识别为现金管理。"""
        holdings = [
            {"name": "余额宝货币", "code": "000001", "market_value": 30000},
            {"name": "某某股票", "code": "600001", "market_value": 70000},
        ]
        result = cash_stripping(holdings, total_mv=100000)
        assert result["has_data"] is True
        assert result["cash_allocation_pct"] == 0.3
        assert result["equity_allocation_pct"] == 0.7
        assert len(result["cash_holdings"]) == 1
        assert result["cash_holdings"][0]["code"] == "000001"

    def test_small_cash_ratio_warning(self):
        """现金占比 <5% → 剥离影响有限。"""
        holdings = [
            {"name": "银华日利", "code": "511880", "market_value": 2000},
            {"name": "某某股票", "code": "600001", "market_value": 98000},
        ]
        result = cash_stripping(holdings, total_mv=100000)
        assert result["cash_allocation_pct"] == 0.02
        assert "影响有限" in (result["warning"] or "")

    def test_stripped_return_with_daily_returns(self):
        """提供日收益率时计算剥离后收益率。"""
        holdings = [
            {"name": "余额宝货币", "code": "000001", "market_value": 20000},
            {"name": "某某股票", "code": "600001", "market_value": 80000},
        ]
        daily_returns = [0.001, -0.002, 0.003, 0.001, -0.001]
        result = cash_stripping(holdings, daily_returns, total_mv=100000)
        assert result["has_data"] is True
        # 组合累计 = (1+0.001)*(1-0.002)*(1+0.003)*(1+0.001)*(1-0.001)-1 ≈ 0.001997
        # 剥离后 = 0.001997 / 0.8 ≈ 0.002496
        assert result["stripped_return_pct"] is not None
        assert result["stripped_return_pct"] > 0.001

    def test_stripped_return_no_cash(self):
        """无现金品种时剥离后收益率等于组合收益率。"""
        holdings = [
            {"name": "某某股票", "code": "600001", "market_value": 100000},
        ]
        daily_returns = [0.01, 0.01]
        result = cash_stripping(holdings, daily_returns, total_mv=100000)
        assert result["has_data"] is True
        assert result["equity_allocation_pct"] == 1.0
        # 累计 (1+0.01)*(1+0.01) - 1 = 0.0201
        assert result["stripped_return_pct"] is not None
        assert abs(result["stripped_return_pct"] - 0.0201) < 1e-5

    def test_no_daily_returns(self):
        """无日收益率数据 → stripped_return_pct=None。"""
        holdings = [
            {"name": "余额宝货币", "code": "000001", "market_value": 10000},
            {"name": "某某股票", "code": "600001", "market_value": 90000},
        ]
        result = cash_stripping(holdings, total_mv=100000)
        assert result["stripped_return_pct"] is None
        assert "无日收益率数据" in (result["warning"] or "")

    def test_market_value_none_handling(self):
        """market_value 为 None 时视为 0，不崩溃。"""
        holdings = [
            {"name": "货币基金", "code": "000001", "market_value": None},
            {"name": "某某股票", "code": "600001", "market_value": 50000},
        ]
        result = cash_stripping(holdings, total_mv=50000)
        assert result["has_data"] is True


# ── twr_calculation 测试 ──────────────────────────────────────


class TestTwrCalculation:
    """时间加权收益率计算测试。"""

    def test_empty_snapshots(self):
        """空快照列表 → has_data=False。"""
        result = twr_calculation([])
        assert result["has_data"] is False
        assert result["twr"] is None
        assert result["n_periods"] == 0

    def test_single_snapshot(self):
        """仅单个快照 → twr=0。"""
        result = twr_calculation([{"value": 100000, "cash_flow": 0}])
        assert result["has_data"] is True
        assert result["twr"] == 0.0
        assert result["n_periods"] == 1
        assert "单个快照" in (result["warning"] or "")

    def test_two_periods_no_cash_flow(self):
        """两个期间，无现金流 → 简单增长。"""
        snapshots = [
            {"value": 100000, "cash_flow": 0},
            {"value": 105000, "cash_flow": 0},
        ]
        result = twr_calculation(snapshots)
        assert result["has_data"] is True
        assert result["n_periods"] == 1
        # (105000 - 0) / 100000 - 1 = 0.05
        assert abs(result["twr"] - 0.05) < 1e-6

    def test_multiple_periods(self):
        """多个期间，带现金流。"""
        snapshots = [
            {"value": 100000, "cash_flow": 0},
            {"value": 110000, "cash_flow": 5000},
            {"value": 108000, "cash_flow": 0},
        ]
        result = twr_calculation(snapshots)
        assert result["has_data"] is True
        assert result["n_periods"] == 2
        # 期间1: (110000-5000)/100000-1 = 0.05
        # 期间2: (108000-0)/110000-1 ≈ -0.01818
        # twr = (1+0.05)*(1-0.01818)-1 ≈ 0.0303
        assert result["twr"] is not None
        assert 0.02 < result["twr"] < 0.04

    def test_invalid_prev_value_zero(self):
        """期初市值为 0 → 跳过该期间。"""
        snapshots = [
            {"value": 0, "cash_flow": 0},
            {"value": 100000, "cash_flow": 0},
            {"value": 105000, "cash_flow": 0},
        ]
        result = twr_calculation(snapshots)
        assert result["has_data"] is True
        assert result["n_periods"] == 1  # 跳过第1个期间（prev=0）

    def test_all_invalid_periods(self):
        """所有期间均无效 → has_data=False。"""
        snapshots = [
            {"value": 0, "cash_flow": 0},
            {"value": 0, "cash_flow": 0},
        ]
        result = twr_calculation(snapshots)
        assert result["has_data"] is False
        assert result["twr"] is None
        assert "无有效期间" in (result["warning"] or "")

    def test_annualized_twr_enough_periods(self):
        """期间数 >= 252 → 计算年化 TWR。"""
        snapshots = [{"value": 100000, "cash_flow": 0}]
        # 构建 252 个期间，每日涨 0.01%
        for i in range(252):
            snapshots.append({"value": 100000 * (1 + 0.0001) ** (i + 1), "cash_flow": 0})
        result = twr_calculation(snapshots)
        assert result["has_data"] is True
        assert result["n_periods"] >= 252
        assert result["annualized_twr"] is not None

    def test_annualized_twr_too_few_periods(self):
        """期间数 < 252 → 年化 TWR 为 None。"""
        snapshots = [
            {"value": 100000, "cash_flow": 0},
            {"value": 105000, "cash_flow": 0},
        ]
        result = twr_calculation(snapshots)
        assert result["has_data"] is True
        assert result["n_periods"] == 1
        assert result["annualized_twr"] is None

    def test_few_periods_warning(self):
        """期间数 < 2 → warning。"""
        snapshots = [
            {"value": 100000, "cash_flow": 0},
            {"value": 105000, "cash_flow": 0},
        ]
        result = twr_calculation(snapshots)
        assert "不稳定" in (result["warning"] or "")


# ── compute_alignment_factors 集成测试 ────────────────────────


class TestComputeAlignmentFactors:
    """组合校准因子入口函数集成测试。"""

    def test_all_empty(self):
        """空持仓 + 无快照 → has_data=False。"""
        result = compute_alignment_factors([], 0)
        assert result["has_data"] is False
        assert result["has_any_data"] is False
        assert isinstance(result["summary_text"], str)

    def test_basic_alignment(self):
        """正常持仓 + 快照 → 三项修正均计算。"""
        holdings_details = [
            {"name": "某某股票", "code": "600001", "market_value": 80000},
            {"name": "余额宝货币", "code": "000001", "market_value": 20000},
        ]
        snapshots = [
            {"value": 100000, "cash_flow": 0},
            {"value": 105000, "cash_flow": 0},
        ]
        result = compute_alignment_factors(
            holdings_details,
            total_mv=100000,
            portfolio_daily_returns=[0.001, -0.0005, 0.002],
            snapshots=snapshots,
        )
        assert result["has_data"] is True
        assert result["has_any_data"] is True
        assert "费率估算" in result["summary_text"]
        assert "现金剥离" in result["summary_text"]
        assert "时间加权收益率" in result["summary_text"]

    def test_no_snapshots(self):
        """无快照 → TWR 部分返回未计算状态。"""
        holdings_details = [
            {"name": "某某股票", "code": "600001", "market_value": 100000},
        ]
        result = compute_alignment_factors(
            holdings_details,
            total_mv=100000,
        )
        assert result["has_data"] is True
        assert result["twr"]["has_data"] is False
        assert "未提供快照数据" in (result["twr"].get("warning") or "")
