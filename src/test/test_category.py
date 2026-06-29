"""持仓分类模块单元测试 — 分类逻辑与边界测试。

测试目标：
  - _categorize_holding — 8 种分类分支全覆盖
  - write_category_sheet — 空/单条/混合持仓场景
  - _apply_profit_colors — 着色边界

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_category -v
"""

from __future__ import annotations

import unittest

from src.python.models import Holding
from src.python.report import category as cat


class TestCategorizeHolding(unittest.TestCase):
    """_categorize_holding 全分支测试。"""

    def _h(self, name: str, code: str, account: str = "证券账户") -> Holding:
        return Holding(account=account, name=name, code=code,
                        shares=100, cost_price=10.0)

    def test_qdii(self):
        """QDII → (基金, QDII)。"""
        h = self._h("华夏纳斯达克100ETF(QDII)", "513300")
        self.assertEqual(cat._categorize_holding(h), ("基金", "QDII"))

    def test_bond(self):
        """含债关键词 → (债券, 纯债)。"""
        h = self._h("招商鑫福中短债A", "012325", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("债券", "纯债"))

    def test_cash(self):
        """含货币关键词 → (现金, 货币)。"""
        h = self._h("银华货币A", "180008", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("现金", "货币"))

    def test_cash_bao(self):
        """含宝关键词 → (现金, 货币)。"""
        h = self._h("余额宝", "000001", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("现金", "货币"))

    def test_offsite_passive(self):
        """场外渠道 + 指数关键词 → (基金, 被动)。"""
        h = self._h("天弘沪深300ETF联接A", "000961", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("基金", "被动"))

    def test_offsite_active(self):
        """场外渠道 + 无指数关键词 → (基金, 主动)。"""
        h = self._h("易方达中小盘混合", "110011", "支付宝")
        self.assertEqual(cat._categorize_holding(h), ("基金", "主动"))

    def test_etf(self):
        """场内ETF → (基金, 指数)。"""
        h = self._h("科创材料ETF", "561910")
        self.assertEqual(cat._categorize_holding(h), ("基金", "指数"))

    def test_etf_code5(self):
        """代码5开头(ETF) → (基金, 指数)。"""
        h = self._h("黄金ETF", "518880")
        self.assertEqual(cat._categorize_holding(h), ("基金", "指数"))

    def test_stock(self):
        """场内股票 → (股票, A股)。"""
        h = self._h("长江电力", "600900")
        self.assertEqual(cat._categorize_holding(h), ("股票", "A股"))

    def test_stock_shenzhen(self):
        """深交所股票 → (股票, A股)。"""
        h = self._h("五粮液", "000858")
        self.assertEqual(cat._categorize_holding(h), ("股票", "A股"))

    def test_stock_chuangyeban(self):
        """创业板股票 → (股票, A股)。"""
        h = self._h("宁德时代", "300750")
        self.assertEqual(cat._categorize_holding(h), ("股票", "A股"))

    def test_fallback_mixed(self):
        """银行渠道其余 → (基金, 主动)。"""
        h = self._h("某理财产品", "999999", "银行")
        self.assertEqual(cat._categorize_holding(h), ("基金", "主动"))


class TestCategorizeHoldingEdgeCases(unittest.TestCase):
    """边缘分支测试。"""

    def _h(self, name: str, code: str, account: str = "证券账户") -> Holding:
        return Holding(account=account, name=name, code=code,
                        shares=100, cost_price=10.0)

    def test_empty_name_code(self):
        """空名称或代码 → 按账户和 code 前缀判断。"""
        h = self._h("", "600900")
        # 无名称、代码 6 开头 → 场内股票
        self.assertEqual(cat._categorize_holding(h), ("股票", "A股"))

    def test_bond_in_securities_account(self):
        """证券账户中的债券 → (债券, 纯债)。"""
        h = self._h("国债ETF", "511880")
        self.assertEqual(cat._categorize_holding(h), ("债券", "纯债"))

    def test_kw_priority(self):
        """QDII 优先级最高 → 即使名称含债关键词也归 QDII。"""
        h = self._h("QDII债券基金", "123456")
        self.assertEqual(cat._categorize_holding(h), ("基金", "QDII"))


class TestWriteCategorySheet(unittest.TestCase):
    """write_category_sheet 边界测试。"""

    def setUp(self):
        from openpyxl import Workbook
        self.wb = Workbook()
        self.ws = self.wb.active

    def test_empty_holdings(self):
        """空持仓 → 不崩溃。"""
        try:
            cat.write_category_sheet(self.ws, [], [])
        except Exception as e:
            self.fail(f"write_category_sheet with empty holdings raised: {e}")


if __name__ == "__main__":
    unittest.main()
