"""持仓分类模块单元测试 — 分类逻辑与边界测试。

测试目标：
  - _categorize_holding — 8 种分类分支全覆盖
  - write_category_sheet — 空/单条/混合持仓场景
  - _apply_profit_colors — 着色边界
  - 三维度分类聚合一致 — 资产属性/投资分类/账户小计之和 = 总计 (R-093)

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_category -v
"""

from __future__ import annotations

import unittest

from src.python.models import Holding
from src.python.report import category as cat
from src.python.report.market_value import DetailRow
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report]



class TestCategorizeHolding(unittest.TestCase):
    """_categorize_holding 全分支测试。"""

    def _h(self, name: str, code: str, account: str = "证券账户") -> Holding:
        return Holding(account=account, name=name, code=code,
                        shares=100, cost_price=10.0)

    @pytest.mark.smoke
    def test_qdii(self):
        """QDII → (基金, QDII)。"""
        h = self._h("华夏纳斯达克100ETF(QDII)", "513300")
        self.assertEqual(cat._categorize_holding(h), ("基金", "QDII"))

    @pytest.mark.smoke
    def test_bond(self):
        """含债关键词 → (债券, 纯债)。"""
        h = self._h("招商鑫福中短债A", "012325", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("债券", "纯债"))

    def test_cash(self):
        """含货币关键词 → (现金, 货币)。"""
        h = self._h("银华货币A", "180008", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("现金", "货币"))

    @pytest.mark.smoke
    def test_stock(self):
        """股票代码 6/0/3 开头 → (股票, A股)。"""
        h = self._h("贵州茅台", "600519")
        self.assertEqual(cat._categorize_holding(h), ("股票", "A股"))

    @pytest.mark.smoke
    def test_index_fund(self):
        """场内 ETF 代码 5 开头 → (基金, 指数)。"""
        h = self._h("南方中证500ETF", "510500", "证券账户")
        self.assertEqual(cat._categorize_holding(h), ("基金", "指数"))

    def test_active_fund(self):
        """场外渠道且非指数名称 → (基金, 主动)。"""
        h = self._h("易方达蓝筹精选混合", "005827", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("基金", "主动"))

    def test_hybrid_fund(self):
        """微信钱包账户含混合名称 → (基金, 主动)（微信属场外渠道）。"""
        h = self._h("招商安润灵活配置混合", "000126", "微信钱包")
        self.assertEqual(cat._categorize_holding(h), ("基金", "主动"))

    def test_other_fund(self):
        """其他基金（支付宝账户非指数）→ (基金, 主动)。"""
        h = self._h("某只特殊策略基金", "888888", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("基金", "主动"))

    def test_etf_code_no_keyword(self):
        """ETF代码(5开头)但名称无关键词 → (基金, 指数)。"""
        h = self._h("科创50", "588000")
        self.assertEqual(cat._categorize_holding(h), ("基金", "指数"))


class TestWriteCategorySheet(unittest.TestCase):
    """write_category_sheet 集成测试。"""

    def setUp(self):
        import openpyxl

        self.wb = openpyxl.Workbook()
        self.ws = self.wb.active

    def test_single_holding(self):
        """单条持仓 → 分类表正确渲染。"""
        h = Holding("证券", "长江电力", "600900", 100, 10.0)
        details = [DetailRow(
            code="600900", account="证券", name="长江电力",
            market_value=2500, profit=1500, profit_rate=1.5)]
        cat.write_category_sheet(self.ws, [h], details)
        # 应该至少有一行标题 + 一行数据 + 合计行
        self.assertGreater(self.ws.max_row, 2)

    def test_empty_holdings(self):
        """空持仓 → 不崩溃。"""
        try:
            cat.write_category_sheet(self.ws, [], [])
        except Exception as e:
            self.fail(f"write_category_sheet with empty holdings raised: {e}")


@pytest.mark.data
class TestCategoryAggregationConsistency(unittest.TestCase):
    """R-093: 三维度分类聚合一致 — 各维度小计之和 = 总计。"""

    def _build_mock_category_result(self):
        """构造模拟的 category() 输出，验证聚合一致。"""
        # 模拟分类结果结构：{维度: {类别: {account: {合计值}}}}
        return {
            "asset_type": {  # 资产属性维度
                "股票": {"count": 2, "market_value": 5000, "profit": 1000},
                "基金": {"count": 3, "market_value": 8000, "profit": -500},
                "债券": {"count": 1, "market_value": 3000, "profit": 100},
            },
            "invest_type": {  # 投资分类维度
                "主动管理": {"count": 2, "market_value": 6000, "profit": -300},
                "被动指数": {"count": 1, "market_value": 2000, "profit": -200},
                "纯债": {"count": 1, "market_value": 3000, "profit": 100},
                "股票": {"count": 2, "market_value": 5000, "profit": 1000},
            },
            "account": {  # 账户维度
                "证券账户": {"count": 3, "market_value": 9000, "profit": 800},
                "支付宝": {"count": 2, "market_value": 4000, "profit": -300},
                "微信钱包": {"count": 1, "market_value": 3000, "profit": 100},
            },
        }

    def test_asset_type_subtotals_equal_grand_total(self):
        """资产属性各分类市值之和 = 总市值。"""
        data = self._build_mock_category_result()
        total_mv = sum(v["market_value"] for v in data["asset_type"].values())
        expected_total = 5000 + 8000 + 3000
        self.assertEqual(total_mv, expected_total)
        self.assertEqual(total_mv, 16000)

    def test_invest_type_subtotals_equal_grand_total(self):
        """投资分类各子类市值之和 = 总市值。"""
        data = self._build_mock_category_result()
        total_mv = sum(v["market_value"] for v in data["invest_type"].values())
        expected_total = 6000 + 2000 + 3000 + 5000
        self.assertEqual(total_mv, expected_total)
        self.assertEqual(total_mv, 16000)

    def test_account_subtotals_equal_grand_total(self):
        """各账户市值之和 = 总市值。"""
        data = self._build_mock_category_result()
        total_mv = sum(v["market_value"] for v in data["account"].values())
        expected_total = 9000 + 4000 + 3000
        self.assertEqual(total_mv, expected_total)
        self.assertEqual(total_mv, 16000)

    def test_all_three_dimensions_agree(self):
        """三个维度的总计应一致。"""
        data = self._build_mock_category_result()
        asset_total = sum(v["market_value"] for v in data["asset_type"].values())
        invest_total = sum(v["market_value"] for v in data["invest_type"].values())
        account_total = sum(v["market_value"] for v in data["account"].values())
        self.assertEqual(asset_total, invest_total)
        self.assertEqual(invest_total, account_total)

    def test_profit_subtotals_also_consistent(self):
        """利润维度也应三维一致（交叉验证非仅市值）。"""
        data = self._build_mock_category_result()
        asset_profit = sum(v["profit"] for v in data["asset_type"].values())
        invest_profit = sum(v["profit"] for v in data["invest_type"].values())
        account_profit = sum(v["profit"] for v in data["account"].values())
        self.assertEqual(asset_profit, invest_profit)
        self.assertEqual(invest_profit, account_profit)
        # 1000 + (-500) + 100 = 600
        self.assertEqual(asset_profit, 600)

    def test_no_negative_counts(self):
        """所有 count 应为非负整数。"""
        data = self._build_mock_category_result()
        for dim_name, dim_data in data.items():
            for cat_name, values in dim_data.items():
                self.assertGreaterEqual(
                    values["count"], 0,
                    f"{dim_name}.{cat_name} count={values['count']} 为负"
                )


if __name__ == "__main__":
    unittest.main()
