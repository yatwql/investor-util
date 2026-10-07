"""穿透模块单元测试 — 报告期场景（penetration.py 分片）。

测试目标：
  - 取数不可用基金的剔除与未穿透计数、无效比值过滤
  - 持仓报告期陈旧闸门：陈旧基金剔除出 TOP10、报告期明细上屏与汇总横幅
  - 联接基金穿透：来源登记进报告期明细（非联接条目不带来源键）

运行：
  pytest src/test/unit/report/test_penetration_report_periods.py -v
"""

from __future__ import annotations
import unittest
from typing import Any
from unittest.mock import patch
from src.python.core.models import Holding
from src.python.report import penetration as pene
from src.test.helpers import recent_holdings_period
import pytest

from .test_penetration import MockDetailRow

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]


class TestFundsWithUnavailableHoldings(unittest.TestCase):
    """验证基金持仓不可获取或数据无效时，不污染穿透 TOP10。"""

    def _make_detail(self, code: str, market_value: float) -> MockDetailRow:
        return MockDetailRow(code, market_value)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_failed_fund_not_in_top10(self, mock_batch, mock_ind):
        """持仓数据取不到的基金 → 不进入 top10，基金全值计入 unknown_mv。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910",
                "name": "电池ETF",
                "date": recent_holdings_period(),
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            },
        }

        holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
            Holding("支付宝", "财通成长优选混合A", "001480", 1000, 1.0),
            Holding("支付宝", "财通成长优选混合C", "021528", 500, 1.0),
        ]
        details = [
            self._make_detail("561910", 10000.0),
            self._make_detail("001480", 31299.59),
            self._make_detail("021528", 31152.86),
        ]

        result = pene.compute_penetration_top10(holdings, details)

        # 财通基金不应该出现在 top10 的名称中
        top10_names = [e["name"] for e in result["top10"]]
        for name in top10_names:
            self.assertNotIn("财通", name, f"穿透 TOP10 不应包含基金名称「{name}」")

        # 宁德时代和比亚迪应为穿透结果（来自电池ETF）
        self.assertIn("宁德时代", top10_names)
        self.assertIn("比亚迪", top10_names)

        # 宁德时代市值 = 10000 * 15% = 1500
        nd = next(e for e in result["top10"] if e["name"] == "宁德时代")
        self.assertAlmostEqual(nd["mv"], 1500.0, places=1)

        # unknown_mv 包含两只财通基金的全值
        self.assertAlmostEqual(result["summary"]["unknown_mv"], 31299.59 + 31152.86, delta=0.02)

        # failed_funds 应正确计数
        self.assertEqual(result["summary"]["failed_funds"], 2)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_failed_fund_ratio_not_distorted(self, mock_batch, mock_ind):
        """未穿透的基金不参与总市值计算，ratio_pct 仅基于可识别资产。"""
        mock_batch.return_value = {
            "561910": {
                "code": "561910",
                "name": "电池ETF",
                "date": recent_holdings_period(),
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 50.0},
                ],
            },
        }

        holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
            Holding("支付宝", "财通成长优选混合A", "001480", 1000, 1.0),
        ]
        details = [
            self._make_detail("561910", 20000.0),
            self._make_detail("001480", 100000.0),
        ]

        result = pene.compute_penetration_top10(holdings, details)

        # 电池ETF 穿透宁德时代 = 20000 * 50% = 10000
        # 财通不进 merged，总市值 = 10000
        nd = next(e for e in result["top10"] if e["name"] == "宁德时代")
        self.assertAlmostEqual(nd["mv"], 10000.0, places=1)
        # 占比应 ≈ 100%
        self.assertAlmostEqual(nd["ratio_pct"], 100.0, places=1)

        # unknown_mv 正确
        self.assertAlmostEqual(result["summary"]["unknown_mv"], 100000.0, delta=0.02)
        self.assertEqual(result["summary"]["failed_funds"], 1)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_invalid_ratio_filtered(self, mock_batch, mock_ind):
        """持仓比例 >100% 的标的应被过滤（如 518880 黄金 ETF API 返回的垃圾数据）。"""
        mock_batch.return_value = {
            "518880": {
                "code": "518880",
                "name": "华安黄金ETF",
                "date": "",
                "holdings": [
                    # ratio > 100% 的垃圾数据
                    {"name": "财通成长优选混合A（001480）", "code": "001480", "ratio": 401.03},
                    {"name": "财通成长优选混合C（021528）", "code": "021528", "ratio": 399.15},
                    {"name": "财通价值动量混合A（720001）", "code": "720001", "ratio": 359.33},
                ],
            },
        }

        holdings = [
            Holding("证券账户", "华安黄金ETF", "518880", 100, 83.097),
        ]
        details = [
            self._make_detail("518880", 8309.70),
        ]

        result = pene.compute_penetration_top10(holdings, details)

        # 过滤后无有效标的 → top10 应为空
        self.assertEqual(len(result["top10"]), 0, "ratio 全部 >100% 的基金不应产生穿透标的")

        # unknown_mv 应包含 518880 的全值
        self.assertAlmostEqual(result["summary"]["unknown_mv"], 8309.70, delta=0.02)
        self.assertEqual(result["summary"]["failed_funds"], 1)

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_mixed_valid_and_invalid_ratios(self, mock_batch, mock_ind):
        """同一基金混有无效和有效比例 → 只保留有效比例。"""
        mock_batch.return_value = {
            "518880": {
                "code": "518880",
                "name": "华安黄金ETF",
                "date": "",
                "holdings": [
                    {"name": "财通成长优选混合A（001480）", "code": "001480", "ratio": 401.03},
                    {"name": "山东黄金", "code": "600547", "ratio": 15.0},
                    {"name": "中金黄金", "code": "600489", "ratio": 10.0},
                ],
            },
        }

        holdings = [
            Holding("证券账户", "华安黄金ETF", "518880", 100, 83.097),
        ]
        details = [
            self._make_detail("518880", 8309.70),
        ]

        result = pene.compute_penetration_top10(holdings, details)

        # 财通基金应被过滤，只保留山东黄金和中金黄金
        top10_names = [e["name"] for e in result["top10"]]
        self.assertNotIn("财通成长优选混合A", top10_names, "ratio>100% 的标的应被过滤")
        self.assertIn("山东黄金", top10_names)
        self.assertIn("中金黄金", top10_names)

        # 山东黄金 = 8309.70 * 15% = 1246.46
        sd = next(e for e in result["top10"] if e["name"] == "山东黄金")
        self.assertAlmostEqual(sd["mv"], 1246.46, places=1)

        # 有效持仓占比之和 ≈ 100%
        total_ratio = sum(e["ratio_pct"] for e in result["top10"])
        self.assertAlmostEqual(total_ratio, 100.0, delta=0.02)


class TestStaleHoldingsReportPeriod(unittest.TestCase):
    """持仓报告期陈旧的基金不得按当期市值并入穿透 TOP10。

    实测场景：天天基金在不指定年份的默认请求下会返回该基金最近一次披露的
    报告，部分基金仅有早期报告（实测 2022-12-08）。该快照若按当期市值加权
    并入 TOP10，得到的是数年前的配置权重，且报告中没有字段能让人看出这一点。
    """

    def _make_detail(self, code: str, market_value: float) -> MockDetailRow:
        return MockDetailRow(code, market_value)

    @staticmethod
    def _holdings_data(code: str, name: str, period: str | None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": code,
            "name": name,
            "holdings": [{"name": "苹果", "code": "AAPL", "ratio": 20.0}],
        }
        if period is not None:
            data["date"] = period
        return data

    @patch("src.python.report.penetration.fetch_fund_manager", return_value=None)
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_stale_report_excluded_from_merge(self, mock_batch, mock_manager):
        """报告期 2022-12-08（约四年前）的基金 → 不并入 merged，市值计入 unknown_mv。"""
        from src.python.report.penetration import _merge_fund_layer

        name = "华安纳斯达克100ETF联接(QDII)A"
        mock_batch.return_value = {"040046": self._holdings_data("040046", name, "2022-12-08")}

        funds = [Holding("支付宝", name, "040046", 100, 10.0)]
        merge = _merge_fund_layer(funds, {"040046": 1000.0})

        self.assertNotIn("苹果", merge.merged, "陈旧持仓不得进入穿透结果")
        self.assertEqual(merge.stale_count, 1)
        self.assertEqual(merge.stale_details[0]["code"], "040046")
        self.assertEqual(merge.stale_details[0]["period"], "2022-12-08")
        self.assertEqual(merge.period_details, [], "被剔除的基金不应出现在报告期明细中")
        self.assertAlmostEqual(merge.unknown_mv, 1000.0)

    @patch("src.python.report.penetration.fetch_fund_manager", return_value=None)
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_fresh_report_kept_and_period_recorded(self, mock_batch, mock_manager):
        """报告期在阈值内 → 正常并入，并登记报告期供报告标注。"""
        from src.python.report.penetration import _merge_fund_layer

        name = "易方达蓝筹"
        mock_batch.return_value = {"005827": self._holdings_data("005827", name, recent_holdings_period())}

        funds = [Holding("支付宝", name, "005827", 100, 10.0)]
        merge = _merge_fund_layer(funds, {"005827": 1000.0})

        self.assertIn("苹果", merge.merged)
        self.assertAlmostEqual(merge.merged["苹果"]["mv"], 200.0)
        self.assertEqual(merge.stale_count, 0)
        self.assertEqual(len(merge.period_details), 1)
        self.assertEqual(merge.period_details[0]["period"], recent_holdings_period())
        self.assertAlmostEqual(merge.unknown_mv, 0.0)

    @patch("src.python.report.penetration.fetch_fund_manager", return_value=None)
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_missing_report_period_is_not_gated(self, mock_batch, mock_manager):
        """接口未给报告期 → 不判陈旧（属数据缺失，由既有的获取失败路径处理）。"""
        from src.python.report.penetration import _merge_fund_layer

        mock_batch.return_value = {"005827": self._holdings_data("005827", "易方达蓝筹", None)}

        funds = [Holding("支付宝", "易方达蓝筹", "005827", 100, 10.0)]
        merge = _merge_fund_layer(funds, {"005827": 1000.0})

        self.assertIn("苹果", merge.merged)
        self.assertEqual(merge.stale_count, 0)
        self.assertEqual(merge.period_details[0]["period"], "未知")

    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={})
    @patch("src.python.report.penetration.fetch_fund_manager", return_value=None)
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_summary_surfaces_stale_funds_and_periods(self, mock_batch, mock_manager, mock_ind):
        """穿透结果 summary 携带陈旧剔除明细与各基金报告期（供 Excel/HTML 上屏）。"""
        stale_name = "华安纳斯达克100ETF联接(QDII)A"
        fresh_name = "易方达蓝筹"
        mock_batch.return_value = {
            "040046": self._holdings_data("040046", stale_name, "2022-12-08"),
            "005827": self._holdings_data("005827", fresh_name, recent_holdings_period()),
        }

        holdings = [
            Holding("支付宝", stale_name, "040046", 100, 10.0),
            Holding("支付宝", fresh_name, "005827", 100, 10.0),
        ]
        details = [
            self._make_detail("040046", 1000.0),
            self._make_detail("005827", 2000.0),
        ]

        result = pene.compute_penetration_top10(holdings, details)
        summary = result["summary"]

        self.assertEqual(summary["stale_funds"], 1)
        self.assertEqual(summary["stale_fund_details"][0]["code"], "040046")
        self.assertEqual(summary["stale_fund_details"][0]["period"], "2022-12-08")
        self.assertEqual([p["code"] for p in summary["report_periods"]], ["005827"])
        # 陈旧基金全值计入 unknown_mv，不参与 TOP10 权重
        self.assertAlmostEqual(summary["unknown_mv"], 1000.0)
        self.assertEqual(summary["failed_funds"], 0, "报告期陈旧属独立计数，不混入获取失败")


class TestFeederPenetrationReportPeriod(unittest.TestCase):
    """联接基金的持仓穿透自目标 ETF，报告期明细须登记该来源。

    实测场景：联接基金的季报股票表按构造为空（其资产即目标 ETF），不穿透时
    只能落到陈年分区、被时效闸门剔除。穿透后底层暴露是**目标 ETF 的成分股**，
    若报告只写本基金名，读者会把它们误认为该联接基金的直接持仓。
    """

    @staticmethod
    def _holdings_data(code: str, name: str, feeder: dict[str, str] | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": code,
            "name": name,
            "date": recent_holdings_period(),
            "holdings": [{"name": "苹果", "code": "AAPL", "ratio": 20.0}],
        }
        if feeder is not None:
            data["feeder_penetration"] = feeder
        return data

    @patch("src.python.report.penetration.fetch_fund_manager", return_value=None)
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_feeder_source_recorded_in_period_details(self, mock_batch, mock_manager):
        """穿透结果登记本基金名 + 目标 ETF 来源，市值仍按本基金持仓归集。"""
        from src.python.report.penetration import _merge_fund_layer

        name = "博时纳斯达克100ETF发起式联接(QDII)A人民币"
        mock_batch.return_value = {
            "016055": self._holdings_data("016055", name, {"target_code": "513390", "target_name": "纳指100ETF博时"})
        }

        funds = [Holding("支付宝", name, "016055", 100, 10.0)]
        merge = _merge_fund_layer(funds, {"016055": 1000.0})

        self.assertIn("苹果", merge.merged)
        self.assertEqual(merge.stale_count, 0)
        entry = merge.period_details[0]
        self.assertEqual(entry["code"], "016055")
        self.assertEqual(entry["name"], name)
        self.assertEqual(entry["feeder_target_code"], "513390")
        self.assertEqual(entry["feeder_target_name"], "纳指100ETF博时")

    @patch("src.python.report.penetration.fetch_fund_manager", return_value=None)
    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_non_feeder_entry_has_no_source_keys(self, mock_batch, mock_manager):
        """非联接基金不带来源键（无来源即无标注，不产出空字段）。"""
        from src.python.report.penetration import _merge_fund_layer

        mock_batch.return_value = {"005827": self._holdings_data("005827", "易方达蓝筹")}

        funds = [Holding("支付宝", "易方达蓝筹", "005827", 100, 10.0)]
        merge = _merge_fund_layer(funds, {"005827": 1000.0})

        entry = merge.period_details[0]
        self.assertNotIn("feeder_target_code", entry)
        self.assertNotIn("feeder_target_name", entry)


if __name__ == "__main__":
    unittest.main()
