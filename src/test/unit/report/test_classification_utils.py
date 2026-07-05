"""classification_utils 模块单元测试。

测试目标：
  - is_stock_code   — A 股股票代码判定
  - is_etf          — ETF 识别（名称含 ETF / 代码 5/1 开头）
  - is_bond_fund    — 债券基金名称匹配
  - is_index_link   — 指数联接基金识别
  - is_offsite_fund — 场外基金账户判定
  - is_qdii         — QDII 识别（显式 + 隐式）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/report/test_classification_utils.py -v
"""

from __future__ import annotations

import unittest

from src.python.report.classification_utils import (
    INDEX_KEYWORDS,
    is_bond_fund,
    is_etf,
    is_index_link,
    is_offsite_fund,
    is_qdii,
    is_stock_code,
)
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ═══════════════════════════════════════════════════════════
#  is_stock_code
# ═══════════════════════════════════════════════════════════


class TestIsStockCode(unittest.TestCase):
    """测试 is_stock_code A 股股票代码判定。"""

    def test_shanghai_6(self):
        """6 开头 → True。"""
        self.assertTrue(is_stock_code("600000"))

    def test_shenzhen_0(self):
        """0 开头 → True。"""
        self.assertTrue(is_stock_code("000001"))

    def test_gem_3(self):
        """3 开头 → True。"""
        self.assertTrue(is_stock_code("300750"))

    def test_etf_code_5(self):
        """5 开头（ETF）→ False。"""
        self.assertFalse(is_stock_code("510050"))

    def test_fund_code_1(self):
        """1 开头 → False。"""
        self.assertFalse(is_stock_code("159915"))

    def test_empty(self):
        """空字符串 → False。"""
        self.assertFalse(is_stock_code(""))

    def test_non_numeric(self):
        """非数字代码 → False。"""
        self.assertFalse(is_stock_code("AAPL"))


# ═══════════════════════════════════════════════════════════
#  is_etf
# ═══════════════════════════════════════════════════════════


class TestIsEtf(unittest.TestCase):
    """测试 is_etf ETF 识别。"""

    def test_etf_in_name(self):
        """名称含 ETF → True。"""
        self.assertTrue(is_etf("电池ETF"))

    def test_etf_lowercase(self):
        """名称含小写 etf → True。"""
        self.assertTrue(is_etf("电池etf"))

    def test_etf_mixed_case(self):
        """名称含混合大小写 → True。"""
        self.assertTrue(is_etf("电池Etf"))

    def test_shanghai_etf_code(self):
        """代码 5 开头 → True。"""
        self.assertTrue(is_etf("沪深300ETF", "510300"))

    def test_shenzhen_etf_code(self):
        """代码 1 开头 → True。"""
        self.assertTrue(is_etf("创业板ETF", "159915"))

    def test_non_etf(self):
        """不含 ETF 且代码非 5/1 → False。"""
        self.assertFalse(is_etf("长江电力", "600900"))

    def test_non_etf_no_code(self):
        """仅名称不含 ETF，不传 code → False。"""
        self.assertFalse(is_etf("贵州茅台"))

    def test_empty_name(self):
        """空名称 → False。"""
        self.assertFalse(is_etf(""))

    def test_code_6_not_etf(self):
        """代码 6 开头但名称含 ETF → True。"""
        self.assertTrue(is_etf("某ETF", "600000"))


# ═══════════════════════════════════════════════════════════
#  is_bond_fund
# ═══════════════════════════════════════════════════════════


class TestIsBondFund(unittest.TestCase):
    """测试 is_bond_fund 债券基金名称匹配。"""

    def test_bond_keywords(self):
        """含债券关键词 → True。"""
        cases = [
            "招商鑫福中短债A",
            "博时安盈短债A",
            "广发景明中短债A",
            "南方利率债A",
            "富国信用债A",
            "某纯债A",
            "某债券A",
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertTrue(is_bond_fund(name))

    def test_not_bond(self):
        """不含债券关键词 → False。"""
        self.assertFalse(is_bond_fund("中欧医疗健康混合"))
        self.assertFalse(is_bond_fund("华夏纳斯达克100ETF(QDII)"))
        self.assertFalse(is_bond_fund("电池ETF"))

    def test_empty(self):
        """空字符串 → False。"""
        self.assertFalse(is_bond_fund(""))


# ═══════════════════════════════════════════════════════════
#  is_index_link
# ═══════════════════════════════════════════════════════════


class TestIsIndexLink(unittest.TestCase):
    """测试 is_index_link 指数联接基金识别。"""

    def test_link_keywords(self):
        """含联接/链接关键词 → True。"""
        cases = [
            "天弘沪深300ETF联接A",
            "天弘沪深300ETF联接",
            "天弘沪深300  ETF  联接A",
            "某指数联接A",
        ]
        for name in cases:
            with self.subTest(name=name):
                self.assertTrue(is_index_link(name))

    def test_not_link(self):
        """不含联接关键词 → False。"""
        self.assertFalse(is_index_link("中欧医疗健康混合"))
        self.assertFalse(is_index_link("电池ETF"))
        self.assertFalse(is_index_link("招商鑫福中短债A"))
        self.assertFalse(is_index_link(""))

    def test_link_with_etf_link(self):
        """ETF链接 → True。"""
        self.assertTrue(is_index_link("天弘沪深300ETF链接A"))


# ═══════════════════════════════════════════════════════════
#  is_offsite_fund
# ═══════════════════════════════════════════════════════════


class TestIsOffsiteFund(unittest.TestCase):
    """测试 is_offsite_fund 场外基金账户判定。"""

    def test_fund_account(self):
        """含"基金" → True。"""
        self.assertTrue(is_offsite_fund("基金账户"))

    def test_alipay(self):
        """含"支付宝" → True。"""
        self.assertTrue(is_offsite_fund("支付宝"))

    def test_wechat(self):
        """含"微信" → True。"""
        self.assertTrue(is_offsite_fund("微信理财通"))

    def test_bank(self):
        """含"银行" → True。"""
        self.assertTrue(is_offsite_fund("招商银行"))

    def test_securities(self):
        """证券账户 → False。"""
        self.assertFalse(is_offsite_fund("证券账户"))

    def test_empty(self):
        """空字符串 → False。"""
        self.assertFalse(is_offsite_fund(""))


# ═══════════════════════════════════════════════════════════
#  is_qdii
# ═══════════════════════════════════════════════════════════


class TestIsQdii(unittest.TestCase):
    """测试 is_qdii QDII 识别（显式+隐式）。"""

    # ── 显式 QDII ──

    def test_qdii_in_name(self):
        """名称含 QDII → True。"""
        self.assertTrue(is_qdii("华夏纳斯达克100ETF(QDII)"))

    def test_qdii_lowercase(self):
        """名称含小写 qdii → True。"""
        self.assertTrue(is_qdii("华夏纳斯达克100ETF(qdii)"))

    def test_qdii_mixed_case(self):
        """名称含混合大小写 → True。"""
        self.assertTrue(is_qdii("测试(QdIi)"))

    def test_no_market_value_keyword(self):
        """含 QD 但非 QDII → False。"""
        self.assertFalse(is_qdii("QD股票基金"))

    # ── 隐式 QDII ──

    def test_implicit_nasdaq(self):
        """名称含"纳斯达克"（无 QDII 字样）→ True。"""
        self.assertTrue(is_qdii("华安纳斯达克100ETF联接基金A"))

    def test_implicit_sp(self):
        """名称含"标普" → True。"""
        self.assertTrue(is_qdii("标普500ETF"))

    def test_implicit_nasdaq_index(self):
        """名称含"纳指" → True。"""
        self.assertTrue(is_qdii("纳指ETF"))

    def test_implicit_dowjones(self):
        """名称含"道琼斯" → True。"""
        self.assertTrue(is_qdii("道琼斯ETF"))

    def test_implicit_nikkei(self):
        """名称含"日经" → True。"""
        self.assertTrue(is_qdii("日经ETF"))

    # ── 非 QDII ──

    def test_non_qdii_domestic(self):
        """纯国内基金 → False。"""
        self.assertFalse(is_qdii("中欧医疗健康混合"))
        self.assertFalse(is_qdii("电池ETF"))

    def test_empty_string(self):
        """空字符串 → False。"""
        self.assertFalse(is_qdii(""))

    def test_none(self):
        """None → False。"""
        self.assertFalse(is_qdii(None))


# ═══════════════════════════════════════════════════════════
#  INDEX_KEYWORDS 常量
# ═══════════════════════════════════════════════════════════


class TestIndexKeywords(unittest.TestCase):
    """测试 INDEX_KEYWORDS 常量。"""

    def test_contains_expected(self):
        """常量包含常见指数关键词。"""
        self.assertIn("指数", INDEX_KEYWORDS)
        self.assertIn("ETF联接", INDEX_KEYWORDS)
        self.assertIn("中证", INDEX_KEYWORDS)
        self.assertIn("沪深300", INDEX_KEYWORDS)

    def test_is_tuple(self):
        """常量类型为 tuple。"""
        self.assertIsInstance(INDEX_KEYWORDS, tuple)
