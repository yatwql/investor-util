"""穿透模块单元测试 — 分类与名称判定（penetration.py 分片）。

测试目标：
  - classify_penetration — 各类型基金/股票/忽略的正确分类
  - is_bond_related_by_name / is_index_link_by_name — 债券/联接识别（委派 code_utils）
  - _fund_type_tag — 类型→标签映射
  - normalize_name — 名称归一化

运行：
  pytest src/test/unit/report/test_penetration_classify.py -v
"""

from __future__ import annotations
import unittest
from src.python.core.models import Holding
from src.python.report import penetration as pene
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]


# ═══════════════════════════════════════════════════════════
#  分类测试
# ═══════════════════════════════════════════════════════════


class TestClassifyPenetration(unittest.TestCase):
    """测试 classify_penetration 对所有分支类型的正确分类。"""

    def _h(self, name: str, code: str = "", account: str = "证券账户") -> Holding:
        return Holding(
            account=account,
            name=name,
            code=code,
            shares=1.0,
            cost_price=1.0,
        )

    # ── 正向分支 ──────────────────────────────────────────

    def test_qdii_fund(self):
        """QDII 基金 → QDII。"""
        h = self._h("华夏纳斯达克100ETF(QDII)", "513300")
        self.assertEqual(pene.classify_penetration(h), pene.QDII)

    def test_qdii_lowercase(self):
        """QDII 名称大小写不敏感。"""
        h = self._h("易方达标普500指数(QDII)", "161125")
        self.assertEqual(pene.classify_penetration(h), pene.QDII)

    def test_bond_fund_chunzhai(self):
        """纯债基金 → BOND_FUND。"""
        h = self._h("招商鑫福中短债A", "012325", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.BOND_FUND)

    def test_bond_fund_duanzhai(self):
        """短债基金 → BOND_FUND。"""
        h = self._h("博时安盈短债A", "006929", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.BOND_FUND)

    def test_bond_fund_zhongduanzhai(self):
        """中短债基金 → BOND_FUND。"""
        h = self._h("广发景明中短债A", "006591", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.BOND_FUND)

    def test_bond_fund_lilvzhai(self):
        """利率债基金 → BOND_FUND。"""
        h = self._h("南方利率债A", "012345", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.BOND_FUND)

    def test_bond_fund_xinyongzhai(self):
        """信用债基金 → BOND_FUND。"""
        h = self._h("富国信用债A", "010123", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.BOND_FUND)

    def test_index_link_etf(self):
        """ETF联接基金 → INDEX_LINK。"""
        h = self._h("天弘沪深300ETF联接A", "000961", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.INDEX_LINK)

    def test_index_link_no_etf_prefix(self):
        """联接（无 ETF 前缀）→ INDEX_LINK。"""
        h = self._h("某指数联接A", "001234", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.INDEX_LINK)

    def test_index_link_with_spaces(self):
        """带空格的 ETF 联接 → INDEX_LINK。"""
        name = "天弘沪深300 ETF 联接 A"
        h = self._h(name, "000961", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.INDEX_LINK)

    def test_etf_in_name(self):
        """ETF 名称 → ETF。"""
        h = self._h("电池ETF", "561910")
        self.assertEqual(pene.classify_penetration(h), pene.ETF)

    def test_etf_code_5_prefix(self):
        """代码 5 开头 → ETF。"""
        h = self._h("黄金ETF", "518880")
        self.assertEqual(pene.classify_penetration(h), pene.ETF)

    def test_active_equity_alipay(self):
        """支付宝账户中的基金 → ACTIVE_EQUITY。"""
        h = self._h("中欧医疗健康混合", "003095", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)

    def test_active_equity_wechat(self):
        """微信账户中的基金 → ACTIVE_EQUITY。"""
        h = self._h("易方达蓝筹精选", "005827", "微信")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)

    def test_active_equity_bank(self):
        """银行账户中的基金 → ACTIVE_EQUITY。"""
        h = self._h("某稳健增长", "001234", "银行")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)

    def test_active_equity_fund_account(self):
        """基金账户 → ACTIVE_EQUITY。"""
        h = self._h("广发稳健增长", "270002", "基金账户")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)

    def test_stock_sh_6(self):
        """6 开头上海股票 → STOCK。"""
        h = self._h("长江电力", "600900")
        self.assertEqual(pene.classify_penetration(h), pene.STOCK)

    def test_stock_sz_0(self):
        """0 开头深圳股票 → STOCK。"""
        h = self._h("平安银行", "000001")
        self.assertEqual(pene.classify_penetration(h), pene.STOCK)

    def test_stock_cyb_3(self):
        """3 开头创业板股票 → STOCK。"""
        h = self._h("宁德时代", "300750")
        self.assertEqual(pene.classify_penetration(h), pene.STOCK)

    # ── 边缘/优先级测试 ───────────────────────────────────

    def test_code_0_in_fund_account(self):
        """代码 0 开头但场外账户 → ACTIVE_EQUITY（账户优先级高于代码）。"""
        h = self._h("同一代码", "000001", "支付宝")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)

    def test_code_6_in_fund_account(self):
        """代码 6 开头但场外账户 → ACTIVE_EQUITY。"""
        h = self._h("某基金", "600900", "微信")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)

    def test_ignore_convertible_bond(self):
        """可转债（名称含"转债"）→ IGNORE（名称优先级高于代码前缀）。"""
        h = self._h("浦发转债", "110059")
        self.assertEqual(pene.classify_penetration(h), pene.IGNORE)

    def test_ignore_unknown_asset(self):
        """未知类型 → IGNORE。"""
        h = self._h("某现金管理", "400000")
        self.assertEqual(pene.classify_penetration(h), pene.IGNORE)

    # ── 债券优先级高于联接/ETF ────────────────────────────

    def test_bond_fund_etf_in_name_but_bond(self):
        """名称含"债券"且含"ETF" → BOND_FUND（债券优先级高于 ETF）。"""
        # 按代码逻辑，债券检查在 ETF 之前，所以应返回 BOND_FUND
        h = self._h("某债券ETF", "511880")
        self.assertEqual(pene.classify_penetration(h), pene.BOND_FUND)

    # ── 00 代码 OTC 基金（非场外账户→不应误判为STOCK）────

    def test_otc_fund_00_code_in_securities_account(self):
        """00 代码混合基金在证券账户 → ACTIVE_EQUITY（非 STOCK）。"""
        h = self._h("广发多因子混合", "002943", "证券账户")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)

    def test_otc_fund_00_code_money_market(self):
        """00 代码货币基金在证券账户 → ACTIVE_EQUITY（非 STOCK）。"""
        h = self._h("易方达增利货币A", "009123", "证券账户")
        self.assertEqual(pene.classify_penetration(h), pene.ACTIVE_EQUITY)


# ═══════════════════════════════════════════════════════════
#  辅助函数测试
# ═══════════════════════════════════════════════════════════


class TestIsBondFund(unittest.TestCase):
    """测试 is_bond_related_by_name。"""

    def test_bond_keywords(self):
        from src.python.core.code_utils import is_bond_related_by_name

        for name in [
            "招商鑫福中短债A",
            "博时安盈短债A",
            "广发景明中短债A",
            "南方利率债A",
            "富国信用债A",
            "某纯债A",
            "某债券A",
        ]:
            with self.subTest(name=name):
                self.assertTrue(is_bond_related_by_name(name))

    def test_not_bond(self):
        from src.python.core.code_utils import is_bond_related_by_name

        self.assertFalse(is_bond_related_by_name("中欧医疗健康混合"))
        self.assertFalse(is_bond_related_by_name("华夏纳斯达克100ETF(QDII)"))
        self.assertFalse(is_bond_related_by_name("电池ETF"))


class TestIsIndexLink(unittest.TestCase):
    """测试 is_index_link_by_name。"""

    def test_link_keywords(self):
        from src.python.core.code_utils import is_index_link_by_name

        for name in [
            "天弘沪深300ETF联接A",
            "天弘沪深300ETF联接",
            "天弘沪深300  ETF  联接A",
            "某指数联接A",
        ]:
            with self.subTest(name=name):
                self.assertTrue(is_index_link_by_name(name))

    def test_not_link(self):
        from src.python.core.code_utils import is_index_link_by_name

        self.assertFalse(is_index_link_by_name("中欧医疗健康混合"))
        self.assertFalse(is_index_link_by_name("电池ETF"))
        self.assertFalse(is_index_link_by_name("招商鑫福中短债A"))


class TestFundTypeTag(unittest.TestCase):
    """测试 _fund_type_tag。"""

    def test_known_types(self):
        cases = {
            pene.QDII: "QDII",
            pene.ETF: "ETF",
            pene.INDEX_LINK: "联接",
            pene.BOND_FUND: "债券",
            pene.ACTIVE_EQUITY: "权益",
        }
        for ftype, expected in cases.items():
            with self.subTest(ftype=ftype):
                self.assertEqual(pene._fund_type_tag(ftype), expected)

    def test_unknown_type(self):
        self.assertEqual(pene._fund_type_tag("unknown"), "基金")


class TestNormalizeName(unittest.TestCase):
    """测试 normalize_name。"""

    def test_strip_whitespace(self):
        self.assertEqual(pene.normalize_name("  贵州茅台  "), "贵州茅台")

    def test_fullwidth_space(self):
        self.assertEqual(pene.normalize_name("贵州　茅台"), "贵州 茅台")

    def test_nbsp(self):
        self.assertEqual(pene.normalize_name("贵州\xa0茅台"), "贵州 茅台")

    def test_clean_name_unchanged(self):
        self.assertEqual(pene.normalize_name("贵州茅台"), "贵州茅台")
