"""excel_market_data 成本流水组装层单元测试。

测试目标：
  - _build_flow_data — 成本流水子模块开关门控 + 无流水 available=False 占位契约
  - resolve_market_data — fund_flow_data 注入 data 字典（汇总/市值/分类页签渲染数据源）

开关 `report_submodules.cost_lots` 对应 _build_flow_data 的 enable_cost_lots：
False → None（汇总/市值/分类页签保持既有输出）；True → 计算 fund_flow_data 契约。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.report.excel_market_data import _build_flow_data, resolve_market_data
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestBuildFlowData(unittest.TestCase):
    """_build_flow_data 开关门控与占位契约。"""

    def test_none_when_switch_disabled(self):
        """开关关闭（enable_cost_lots=False）→ 返回 None，不调用成本流水计算。"""
        with patch("src.python.analysis.cost_flow.build_fund_flow_data") as mock_bffd:
            result = _build_flow_data(False, [MagicMock()], [], [], [])
        self.assertIsNone(result)
        mock_bffd.assert_not_called()

    def test_available_false_placeholder_when_no_flows(self):
        """开关开启但无流水 → 返回 available=False 占位契约（渲染层写「未录入流水」）。"""
        with patch(
            "src.python.analysis.cost_flow.build_fund_flow_data", return_value={"available": False}
        ) as mock_bffd:
            result = _build_flow_data(True, None, None, [], [])
        self.assertEqual(result, {"available": False})
        mock_bffd.assert_called_once_with([], [], [], {}, end_date=None)

    def test_passes_current_prices_when_flows_present(self):
        """开关开启且有流水 → 以行情明细构建代码→市价映射传入成本流水计算。"""
        holdings = [MagicMock()]
        detail = MagicMock()
        detail.code = "600519"
        detail.price = 1500.0
        with patch(
            "src.python.analysis.cost_flow.build_fund_flow_data", return_value={"available": True}
        ) as mock_bffd:
            result = _build_flow_data(True, [MagicMock()], [MagicMock()], holdings, [detail])
        self.assertEqual(result, {"available": True})
        args, _ = mock_bffd.call_args
        # 位置参数：transactions, dividends, holdings, current_prices
        self.assertEqual(args[3], {"600519": 1500.0})


class TestResolveMarketDataFlow(unittest.TestCase):
    """resolve_market_data 将 fund_flow_data 注入 data 字典（Excel 渲染数据源）。"""

    def test_fund_flow_data_injected_when_enabled(self):
        """开关开启且外部传入明细时，data 含 fund_flow_data（透传 _build_flow_data 结果）。"""
        modules = {
            "write_market_value_sheet": MagicMock(),
            "classify_holdings": MagicMock(return_value={}),
        }
        detail = MagicMock()
        detail.code = "600519"
        detail.price = 1500.0
        with patch(
            "src.python.report.excel_market_data._build_flow_data",
            return_value={"available": True, "xirr": {"rate": 0.1}},
        ) as mock_bfd:
            data = resolve_market_data(
                holdings=[MagicMock()],
                details=[detail],
                modules=modules,
                ws2=MagicMock(),
                prog=MagicMock(),
                enable_cost_lots=True,
                transactions=[MagicMock()],
                dividends=[],
            )
        self.assertTrue(data["fund_flow_data"]["available"])
        self.assertEqual(data["fund_flow_data"]["xirr"]["rate"], 0.1)
        mock_bfd.assert_called_once()

    def test_fund_flow_data_none_when_disabled(self):
        """开关关闭（enable_cost_lots=False）→ data 中 fund_flow_data 为 None（保持既有输出）。"""
        modules = {
            "write_market_value_sheet": MagicMock(),
            "classify_holdings": MagicMock(return_value={}),
        }
        detail = MagicMock()
        detail.code = "600519"
        detail.price = 1500.0
        data = resolve_market_data(
            holdings=[MagicMock()],
            details=[detail],
            modules=modules,
            ws2=MagicMock(),
            prog=MagicMock(),
            enable_cost_lots=False,
        )
        # 开关关闭 → 真实 _build_flow_data 直接返回 None，不触发任何成本流水计算
        self.assertIsNone(data["fund_flow_data"])
