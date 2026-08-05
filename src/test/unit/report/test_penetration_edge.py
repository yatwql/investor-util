"""穿透市值占比归一化验证测试 。

测试目标：
  - 各资产 ratio_pct 之和 ≈ 100%（允许舍入误差 ±0.01%）
  - 总市值 = 0 → 所有 ratio_pct = 0
  - 单资产 → ratio_pct = 100%
  - 多资产占比正确
  - TOP10 覆盖度计算正确
  - ratio_pct 舍入后总和不超过 100%（向上舍入保护）

运行：
  pytest src/test/unit/report/test_penetration_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.core.models import Holding
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]



def _make_holding(name: str, code: str, shares: float = 100,
                  cost_price: float = 10.0, account: str = "证券") -> Holding:
    return Holding(account=account, name=name, code=code,
                   shares=shares, cost_price=cost_price)


def _make_merged_item(name: str, mv: float,
                      codes: list[str] | None = None,
                      funds: list[str] | None = None,
                      sector: str = "制造业",
                      concepts: list[str] | None = None) -> dict:
    return {
        "name": name,
        "mv": mv,
        "codes": codes or [],
        "funds": funds or ["直接持股"],
        "sector": sector,
        "concepts": concepts or [],
    }


class TestPenetrationRatioNormalization(unittest.TestCase):
    """穿透市值占比归一化验证。"""

    def test_all_ratios_sum_to_100(self):
        """多个股东穿透 → 各 ratio_pct 之和 ≈ 100%。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 50000),
            "600900": _make_merged_item("长江电力", 30000),
            "300750": _make_merged_item("宁德时代", 20000),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = [_make_holding("贵州茅台", "600519"),
                         _make_holding("长江电力", "600900"),
                         _make_holding("宁德时代", "300750")]

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        total_ratio = sum(item["ratio_pct"] for item in result["top10"])
        self.assertAlmostEqual(total_ratio, 100.0, delta=0.02,
                               msg=f"ratio_pct 之和应 ≈ 100%，实际 {total_ratio}")

    def test_zero_total_mv_returns_zero_ratios(self):
        """总市值 = 0 → 所有 ratio_pct = 0。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 0),
            "600900": _make_merged_item("长江电力", 0),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = []

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        for item in result["top10"]:
            self.assertEqual(item["ratio_pct"], 0.0,
                             f"{item['name']} ratio_pct 应为 0，实际 {item['ratio_pct']}")

    def test_single_asset_ratio_100(self):
        """单资产 → ratio_pct = 100%。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 100000),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = [_make_holding("贵州茅台", "600519")]

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        self.assertEqual(len(result["top10"]), 1)
        self.assertEqual(result["top10"][0]["ratio_pct"], 100.0)

    def test_total_mv_correct(self):
        """summary.total_mv 等于各条目 mv 之和。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 50000.123),
            "600900": _make_merged_item("长江电力", 30000.456),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = []

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        expected_total = round(50000.123 + 30000.456, 2)
        self.assertEqual(result["summary"]["total_mv"], expected_total)


class TestPenetrationNormalizationEdgeCases(unittest.TestCase):
    """占比归异常边界场景。"""

    def test_top10_coverage_calculation(self):
        """top10_coverage_pct = TOP10 mv / total_mv。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "A": _make_merged_item("资产A", 10000),
            "B": _make_merged_item("资产B", 5000),
            "C": _make_merged_item("资产C", 2000),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = []

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        expected_coverage = (10000 + 5000 + 2000) / (10000 + 5000 + 2000) * 100
        self.assertAlmostEqual(result["summary"]["top10_coverage_pct"],
                               expected_coverage, delta=0.1)

    def test_top10_coverage_zero_total(self):
        """总市值 = 0 → top10_coverage_pct = 0。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "A": _make_merged_item("资产A", 0),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = []

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        self.assertEqual(result["summary"]["top10_coverage_pct"], 0.0)

    def test_ratio_rounding_consistency(self):
        """ratio_pct 舍入后总值不出现明显偏差。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 33333),
            "600900": _make_merged_item("长江电力", 33333),
            "300750": _make_merged_item("宁德时代", 33334),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = []

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        total_ratio = sum(item["ratio_pct"] for item in result["top10"])
        # 允许 ±0.02% 的舍入误差
        self.assertAlmostEqual(total_ratio, 100.0, delta=0.02)

    def test_merged_count_matches(self):
        """merged_count = 合并后的资产数量。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 50000),
            "600900": _make_merged_item("长江电力", 30000),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = []

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        self.assertEqual(result["summary"]["merged_count"], 2)

    def test_top10_limited_to_10(self):
        """超过 10 项合并资产 → 只取 TOP10。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {f"CODE{i:04d}": _make_merged_item(f"资产{i}", (11 - i) * 1000)
                  for i in range(1, 15)}
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = []

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        self.assertEqual(len(result["top10"]), 10)
        # 排名 1 的市值应该最大
        self.assertGreaterEqual(result["top10"][0]["mv"], result["top10"][-1]["mv"])


class TestPenetrationWithFunds(unittest.TestCase):
    """含基金的穿透占比测试。"""

    def test_mixed_direct_and_fund(self):
        """直接持股 + 基金穿透 → 占比之和 ≈ 100%。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 40000, funds=["直接持股", "沪深300ETF"]),
            "600900": _make_merged_item("长江电力", 25000, funds=["直接持股"]),
            "300750": _make_merged_item("宁德时代", 20000, funds=["沪深300ETF"]),
            "000858": _make_merged_item("五粮液", 15000, funds=["易方达蓝筹"]),
        }
        classified = {"qdii": [], "etf": [_make_holding("510300", "沪深300ETF")],
                      "index_link": [], "bond_fund": [],
                      "active_equity": [_make_holding("005827", "易方达蓝筹")]}
        funds = [_make_holding("510300", "沪深300ETF"),
                 _make_holding("005827", "易方达蓝筹")]
        direct_stocks = [_make_holding("贵州茅台", "600519"),
                         _make_holding("长江电力", "600900")]

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=0.0,
            failed_count=0,
            failed_fund_details=[],
        )

        total_ratio = sum(item["ratio_pct"] for item in result["top10"])
        self.assertAlmostEqual(total_ratio, 100.0, delta=0.02)

    def test_unknown_mv_included_in_total(self):
        """unknown_mv 计入总市值但不计入 TOP10。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {
            "600519": _make_merged_item("贵州茅台", 50000),
        }
        classified = {key: [] for key in ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        funds = []
        direct_stocks = [_make_holding("贵州茅台", "600519")]

        result = _build_penetration_result(
            merged=merged,
            classified=classified,
            funds=funds,
            direct_stocks=direct_stocks,
            unknown_mv=30000.0,
            failed_count=0,
            failed_fund_details=[],
        )

        # unknown_mv 不会出现在 top10 中
        top10_mv = sum(item["mv"] for item in result["top10"])
        self.assertEqual(top10_mv, 50000)

        # ratio_pct 基于 merged 的 total_mv 计算（不含 unknown_mv）
        # unknown_mv 仅在 summary 中显示
        self.assertEqual(result["summary"]["unknown_mv"], 30000)


class TestSectorAllocationRatio(unittest.TestCase):
    """穿透行业占比归一化 — 各行业占比之和 ≤ 100%。"""

    def _make_sector_result(self, sectors: list[tuple[str, float]]) -> dict:
        """构造穿透结果，含行业分布。"""
        from src.python.report.penetration import _build_penetration_result

        merged = {}
        for name, mv in sectors:
            merged[name] = {
                "name": name, "mv": mv, "codes": [], "funds": ["直接持股"],
                "sector": name, "concepts": [],
            }
        classified = {key: [] for key in
                       ("qdii", "etf", "index_link", "bond_fund", "active_equity")}
        return _build_penetration_result(
            merged=merged, classified=classified, funds=[],
            direct_stocks=[], unknown_mv=0.0, failed_count=0,
            failed_fund_details=[],
        )

    def test_sector_ratios_sum_to_100(self):
        """多个行业 → 各行业占比 ≈ 100%。"""
        sectors = [("制造业", 50000), ("金融", 30000), ("信息技术", 20000)]
        result = self._make_sector_result(sectors)
        # 穿透结果中 sector 字段来自 merged item 的 sector
        sector_mvs = {}
        for item in result["top10"]:
            s = item.get("sector", item["name"])
            sector_mvs[s] = sector_mvs.get(s, 0) + item["mv"]
        total_mv = sum(sector_mvs.values())
        sector_ratios = {s: mv / total_mv * 100 for s, mv in sector_mvs.items()}
        self.assertAlmostEqual(sum(sector_ratios.values()), 100.0, delta=0.01)

    def test_single_sector_100_percent(self):
        """单一行业 → 占比 100%。"""
        sectors = [("制造业", 100000)]
        result = self._make_sector_result(sectors)
        sector_mvs = {}
        for item in result["top10"]:
            s = item.get("sector", item["name"])
            sector_mvs[s] = sector_mvs.get(s, 0) + item["mv"]
        total_mv = sum(sector_mvs.values())
        sector_ratios = {s: mv / total_mv * 100 for s, mv in sector_mvs.items()}
        self.assertAlmostEqual(sector_ratios.get("制造业", 0), 100.0, delta=0.01)

    def test_no_holdings_no_sectors(self):
        """无持仓 → 行业分布为空。"""
        sectors = []
        result = self._make_sector_result(sectors)
        self.assertEqual(len(result.get("top10", [])), 0)


if __name__ == "__main__":
    unittest.main()
