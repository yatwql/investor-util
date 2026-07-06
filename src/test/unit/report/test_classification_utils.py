"""classification_utils → code_utils 合并后的遗留测试。

测试原 classification_utils 的独有函数，现已迁入 code_utils：
  - is_etf_by_name_or_code — ETF 识别（名称含 ETF / 代码 5/1 开头）
  - is_bond_fund_by_name   — 债券基金名称匹配（宽松）
  - is_offsite_fund        — 场外基金账户判定
  - is_qdii_extended       — QDII 识别（显式 + 隐式）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/report/test_classification_utils.py -v
"""

from __future__ import annotations

import unittest

from src.python.code_utils import (
    FUND_ACCOUNT_KEYWORDS,
    is_bond_fund_by_name,
    is_etf_by_name_or_code,
    is_offsite_fund,
    is_qdii_extended,
)
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ═══════════════════════════════════════════════════════════
#  is_etf_by_name_or_code
# ═══════════════════════════════════════════════════════════


class TestIsEtf(unittest.TestCase):
    """测试 is_etf_by_name_or_code ETF 识别。"""

    def test_etf_in_name(self):
        """名称含 ETF → True。"""
        self.assertTrue(is_etf_by_name_or_code("电池ETF"))

    def test_etf_lowercase(self):
        """名称含小写 etf → True。"""
        self.assertTrue(is_etf_by_name_or_code("电池etf"))

    def test_etf_mixed_case(self):
        """名称含混合大小写 → True。"""
        self.assertTrue(is_etf_by_name_or_code("电池Etf"))

    def test_shanghai_etf_code(self):
        """代码 5 开头 → True。"""
        self.assertTrue(is_etf_by_name_or_code("沪深300ETF", "510300"))

    def test_shenzhen_etf_code(self):
        """代码 1 开头 → True。"""
        self.assertTrue(is_etf_by_name_or_code("创业板ETF", "159915"))

    def test_non_etf(self):
        """不含 ETF 且代码非 5/1 → False。"""
        self.assertFalse(is_etf_by_name_or_code("长江电力", "600900"))

    def test_non_etf_no_code(self):
        """仅名称不含 ETF，不传 code → False。"""
        self.assertFalse(is_etf_by_name_or_code("贵州茅台"))

    def test_empty_name(self):
        """空名称 → False。"""
        self.assertFalse(is_etf_by_name_or_code(""))

    def test_code_6_not_etf(self):
        """代码 6 开头但名称含 ETF → True。"""
        self.assertTrue(is_etf_by_name_or_code("某ETF", "600000"))


# ═══════════════════════════════════════════════════════════
#  is_bond_fund_by_name
# ═══════════════════════════════════════════════════════════


class TestIsBondFund(unittest.TestCase):
    """测试 is_bond_fund_by_name 债券基金名称匹配（宽松）。"""

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
                self.assertTrue(is_bond_fund_by_name(name))

    def test_not_bond(self):
        """不含债券关键词 → False。"""
        self.assertFalse(is_bond_fund_by_name("中欧医疗健康混合"))
        self.assertFalse(is_bond_fund_by_name("华夏纳斯达克100ETF(QDII)"))
        self.assertFalse(is_bond_fund_by_name("电池ETF"))

    def test_empty(self):
        """空字符串 → False。"""
        self.assertFalse(is_bond_fund_by_name(""))


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
#  is_qdii_extended
# ═══════════════════════════════════════════════════════════


class TestIsQdiiExtended(unittest.TestCase):
    """测试 is_qdii_extended QDII 识别（显式+隐式）。"""

    # ── 显式 QDII ──

    def test_qdii_in_name(self):
        """名称含 QDII → True。"""
        self.assertTrue(is_qdii_extended("华夏纳斯达克100ETF(QDII)"))

    def test_qdii_lowercase(self):
        """名称含小写 qdii → True。"""
        self.assertTrue(is_qdii_extended("华夏纳斯达克100ETF(qdii)"))

    def test_qdii_mixed_case(self):
        """名称含混合大小写 → True。"""
        self.assertTrue(is_qdii_extended("测试(QdIi)"))

    def test_no_market_value_keyword(self):
        """含 QD 但非 QDII → False。"""
        self.assertFalse(is_qdii_extended("QD股票基金"))

    # ── 隐式 QDII ──

    def test_implicit_nasdaq(self):
        """名称含"纳斯达克"（无 QDII 字样）→ True。"""
        self.assertTrue(is_qdii_extended("华安纳斯达克100ETF联接基金A"))

    def test_implicit_sp(self):
        """名称含"标普" → True。"""
        self.assertTrue(is_qdii_extended("标普500ETF"))

    def test_implicit_nasdaq_index(self):
        """名称含"纳指" → True。"""
        self.assertTrue(is_qdii_extended("纳指ETF"))

    def test_implicit_dowjones(self):
        """名称含"道琼斯" → True。"""
        self.assertTrue(is_qdii_extended("道琼斯ETF"))

    def test_implicit_nikkei(self):
        """名称含"日经" → True。"""
        self.assertTrue(is_qdii_extended("日经ETF"))

    # ── 非 QDII ──

    def test_non_qdii_domestic(self):
        """纯国内基金 → False。"""
        self.assertFalse(is_qdii_extended("中欧医疗健康混合"))
        self.assertFalse(is_qdii_extended("电池ETF"))

    def test_empty_string(self):
        """空字符串 → False。"""
        self.assertFalse(is_qdii_extended(""))

    def test_none(self):
        """None → False。"""
        self.assertFalse(is_qdii_extended(None))


# ═══════════════════════════════════════════════════════════
#  FUND_ACCOUNT_KEYWORDS 常量
# ═══════════════════════════════════════════════════════════


class TestFundAccountKeywords(unittest.TestCase):
    """测试 FUND_ACCOUNT_KEYWORDS 常量。"""

    def test_contains_expected(self):
        """常量包含常见场外基金渠道关键词。"""
        self.assertIn("基金", FUND_ACCOUNT_KEYWORDS)
        self.assertIn("支付宝", FUND_ACCOUNT_KEYWORDS)
        self.assertIn("微信", FUND_ACCOUNT_KEYWORDS)
        self.assertIn("银行", FUND_ACCOUNT_KEYWORDS)

    def test_is_tuple(self):
        """常量类型为 tuple。"""
        self.assertIsInstance(FUND_ACCOUNT_KEYWORDS, tuple)
