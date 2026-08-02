"""组合演进页签 Excel 呈现测试。

覆盖：
  - available=True → 汇总 + 总市值趋势表 + HHI 趋势表 + TOP 持仓占比变迁表 + 说明
  - 标题顺序：总市值 → HHI → TOP 变迁 → 说明
  - 多账户 → 账户配置流表
  - 单期无有效权重 → HHI 记 "-"
  - available=False（快照不足）→ 占位文本
  - evolution_data=None → 整页占位
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _evolution_data(**extra) -> dict:
    """构造 C19 契约 evolution_data mock（3 观察日，双账户，TOP3）。"""
    d = {
        "available": True,
        "snapshot_count": 5,
        "min_snapshots": 3,
        "periods": ["07-01", "07-02", "07-03"],
        "total_value": [100000.0, 110000.0, 120000.0],
        "total_cost": [90000.0, 90000.0, 90000.0],
        "total_pnl": [10000.0, 20000.0, 30000.0],
        "holding_counts": [2, 2, 3],
        "account_flows": {"账户A": [60.0, 50.0, 70.0], "账户B": [40.0, 50.0, 30.0]},
        "hhi": [0.52, 0.58, 0.38],
        "top_holdings": [
            {"code": "a", "name": "资产A", "weights": [60.0, 70.0, 50.0], "present_count": 3},
            {"code": "b", "name": "资产B", "weights": [40.0, 30.0, 30.0], "present_count": 3},
            {"code": "c", "name": "资产C", "weights": [0.0, 0.0, 20.0], "present_count": 1},
        ],
        "reason": "",
    }
    d.update(extra)
    return d


class TestExcelEvolutionSheet(unittest.TestCase):
    """组合演进页签 Excel 呈现测试。"""

    def _write(self, evolution_data) -> "object":
        from openpyxl import Workbook

        from src.python.report.evolution_sheet import write_evolution_sheet

        wb = Workbook()
        ws = wb.active
        write_evolution_sheet(ws, evolution_data)
        return ws

    def _all_text(self, ws) -> list[list[str]]:
        return [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()]

    def _flat(self, ws) -> list[str]:
        return [v for row in self._all_text(ws) for v in row]

    def test_full_rendering_when_available(self):
        """available=True → 汇总 + 总市值趋势 + HHI 趋势 + TOP 变迁 + 说明齐全。"""
        ws = self._write(_evolution_data())
        titles = [r[0] for r in self._all_text(ws)]
        self.assertTrue(any("组合演进" in t for t in titles), f"应含组合演进标题，实际: {titles}")
        self.assertTrue(any("总市值趋势" in t for t in titles))
        self.assertTrue(any("HHI" in t for t in titles))
        self.assertTrue(any("持仓占比变迁" in t for t in titles))
        self.assertTrue(any("账户配置流" in t for t in titles))
        self.assertTrue(any("说明" in t for t in titles))
        # 标题顺序：总市值 → HHI → TOP → 说明
        mv_idx = next(i for i, t in enumerate(titles) if "总市值趋势" in t)
        hhi_idx = next(i for i, t in enumerate(titles) if "HHI" in t)
        top_idx = next(i for i, t in enumerate(titles) if "持仓占比变迁" in t)
        notes_idx = next(i for i, t in enumerate(titles) if "说明" in t)
        self.assertLess(mv_idx, hhi_idx)
        self.assertLess(hhi_idx, top_idx)
        self.assertLess(top_idx, notes_idx)
        # 数据完整
        flat = self._flat(ws)
        self.assertTrue(any("5 份快照" in v for v in flat), "汇总应含快照数")
        self.assertIn("07-01", flat)
        self.assertTrue(any("100000" in v for v in flat), "应含首期总市值")
        self.assertIn("0.5200", flat)  # HHI 首期
        self.assertTrue(any("资产A (a)" in v for v in flat), "TOP 持仓应含品种")
        self.assertTrue(any("1 / 3" in v for v in flat), "出现期数应正确")
        # 说明区
        self.assertTrue(any("权重口径" in v for v in flat))

    def test_account_flows_when_multi_account(self):
        """多账户 → 账户配置流表含各账户占比。"""
        ws = self._write(_evolution_data())
        flat = self._flat(ws)
        self.assertIn("账户A", flat)
        self.assertIn("账户B", flat)
        self.assertIn("60.00", flat)  # 账户A 首期占比

    def test_single_account_no_flow_table(self):
        """单账户 → 不渲染账户配置流表。"""
        data = _evolution_data()
        data["account_flows"] = {"全部": [100.0, 100.0, 100.0]}
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertFalse(any("账户配置流" in v for v in flat))

    def test_hhi_dash_when_no_valid_weight(self):
        """某期无有效权重 → HHI 记 "-"。"""
        data = _evolution_data()
        data["hhi"] = [0.52, None, 0.38]
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertIn("0.5200", flat)
        self.assertIn("-", flat)

    def test_unavailable_placeholder(self):
        """available=False（快照不足）→ 占位文本。"""
        data = _evolution_data(
            available=False,
            snapshot_count=2,
            periods=[],
            total_value=[],
            total_cost=[],
            total_pnl=[],
            holding_counts=[],
            hhi=[],
            top_holdings=[],
            reason="组合演进快照不足",
        )
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertTrue(any("组合演进数据暂不可用" in v for v in flat), "available=False 应写占位")

    def test_none_placeholder(self):
        """evolution_data=None → 整页占位。"""
        ws = self._write(None)
        flat = self._flat(ws)
        self.assertTrue(any("组合演进数据暂不可用" in v for v in flat), "None 应写整页占位")
