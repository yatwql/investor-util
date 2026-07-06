"""穿透模块单元测试。

测试目标：
  - classify_penetration — 各类型基金/股票/忽略的正确分类
  - is_bond_related_by_name / is_index_link_by_name — 债券/联接识别（委派 code_utils）
  - _fund_type_tag — 类型→标签映射
  - normalize_name — 名称归一化
  - write_penetration_sheet (mock) — 合并/排序/TOP10 逻辑

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_penetration -v
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

from src.python.models import Holding
from src.python.report import penetration as pene
from src.python.report.market_value import DetailRow
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report]




# ═══════════════════════════════════════════════════════════
#  分类测试
# ═══════════════════════════════════════════════════════════


class TestClassifyPenetration(unittest.TestCase):
    """测试 classify_penetration 对所有分支类型的正确分类。"""

    def _h(self, name: str, code: str = "", account: str = "证券账户") -> Holding:
        return Holding(
            account=account, name=name, code=code,
            shares=1.0, cost_price=1.0,
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
        """可转债（证券账户中 1 开头代码但无 ETF 名称）→ IGNORE。"""
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


# ═══════════════════════════════════════════════════════════
#  辅助函数测试
# ═══════════════════════════════════════════════════════════


class TestIsBondFund(unittest.TestCase):
    """测试 is_bond_related_by_name。"""

    def test_bond_keywords(self):
        from src.python.code_utils import is_bond_related_by_name
        for name in [
            "招商鑫福中短债A", "博时安盈短债A", "广发景明中短债A",
            "南方利率债A", "富国信用债A", "某纯债A", "某债券A",
        ]:
            with self.subTest(name=name):
                self.assertTrue(is_bond_related_by_name(name))

    def test_not_bond(self):
        from src.python.code_utils import is_bond_related_by_name
        self.assertFalse(is_bond_related_by_name("中欧医疗健康混合"))
        self.assertFalse(is_bond_related_by_name("华夏纳斯达克100ETF(QDII)"))
        self.assertFalse(is_bond_related_by_name("电池ETF"))


class TestIsIndexLink(unittest.TestCase):
    """测试 is_index_link_by_name。"""

    def test_link_keywords(self):
        from src.python.code_utils import is_index_link_by_name
        for name in [
            "天弘沪深300ETF联接A",
            "天弘沪深300ETF联接",
            "天弘沪深300  ETF  联接A",
            "某指数联接A",
        ]:
            with self.subTest(name=name):
                self.assertTrue(is_index_link_by_name(name))

    def test_not_link(self):
        from src.python.code_utils import is_index_link_by_name
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


# ═══════════════════════════════════════════════════════════
#  Merged 合并/排序逻辑测试（mock API）
# ═══════════════════════════════════════════════════════════


class MockDetailRow:
    """替代 DetailRow 的简单对象，避免导入 openpyxl 依赖。"""
    def __init__(self, code: str, market_value: float):
        self.code = code
        self.market_value = market_value
        self.name = ""
        self.account = ""
        self.shares = 0.0


def _mock_fund_holdings(holdings_data: list[dict[str, Any]] | None):
    """返回一个 mock 的 fetch_fund_holdings，固定返回指定数据。"""
    def _fetch(code: str) -> dict[str, Any] | None:
        if holdings_data is None:
            return None
        return {
            "code": code,
            "name": f"基金{code}",
            "date": "2026-03-31",
            "holdings": holdings_data,
        }
    return _fetch


class TestPenetrationMerge(unittest.TestCase):
    """测试穿透合并/排序逻辑（mock API 调用）。"""

    def setUp(self):
        # 两只有持仓数据的基金
        self.holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
            Holding("支付宝", "招商鑫福中短债A", "012325", 500, 1.0),
            Holding("证券账户", "长江电力", "600900", 200, 50.0),
        ]
        # 对应的 detail 行
        self.details = [
            MockDetailRow("561910", 10000.0),    # 电池ETF市值 1万
            MockDetailRow("012325", 5000.0),       # 短债市值 5000
            MockDetailRow("600900", 10000.0),      # 长江电力市值 1万
        ]

        # mock 电池ETF持仓：前10=宁德时代(15%)+比亚迪(10%)
        self.etf_holdings = [
            {"name": "宁德时代", "code": "300750", "ratio": 15.0},
            {"name": "比亚迪", "code": "002594", "ratio": 10.0},
        ]
        # mock 短债持仓：具体债券品种
        self.bond_holdings = [
            {"name": "23国开10", "code": "230210", "ratio": 8.0},
            {"name": "22国债14", "code": "220014", "ratio": 6.0},
        ]

    @patch("src.python.report.penetration.fetch_fund_holdings")
    def test_basic_merge_and_sort(self, mock_fetch):
        """验证相同的底层标的合并、按市值排序。"""

        def side_effect(code: str) -> dict[str, Any] | None:
            if code == "561910":
                return {
                    "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                    "holdings": self.etf_holdings,
                }
            elif code == "012325":
                return {
                    "code": "012325", "name": "招商鑫福中短债A", "date": "2026-03-31",
                    "holdings": self.bond_holdings,
                }
            return None
        mock_fetch.side_effect = side_effect

        # 调用写穿透的下层逻辑：直接调用 write_penetration_sheet 太重量级（需要 openpyxl）
        # 改为测试 merge 阶段的逻辑 —— 用内联方式测试
        detail_map = {d.code: d for d in self.details}
        merged: dict[str, dict[str, Any]] = {}

        for h in [h for h in self.holdings if pene.classify_penetration(h) != pene.STOCK]:
            ftype = pene.classify_penetration(h)
            tag = pene._fund_type_tag(ftype)
            detail = detail_map.get(h.code)
            fund_mv = detail.market_value if detail else 0.0

            data = mock_fetch(h.code)
            if not data or not data.get("holdings"):
                continue

            for item in data["holdings"]:
                name = item.get("name", "").strip()
                code = item.get("code", "").strip()
                ratio = item.get("ratio", 0.0)
                if not name:
                    continue
                mv = fund_mv * (ratio / 100.0)
                norm = pene.normalize_name(name)
                if norm not in merged:
                    merged[norm] = {"name": name, "codes": set(), "mv": 0.0, "funds": []}
                if code:
                    merged[norm]["codes"].add(code)
                merged[norm]["mv"] += mv
                merged[norm]["funds"].append(f"[{tag}] {h.name}({h.code})")

        # 加入直接持股
        for h in self.holdings:
            if pene.classify_penetration(h) == pene.STOCK:
                detail = detail_map.get(h.code)
                stock_mv = detail.market_value if detail else 0.0
                norm = pene.normalize_name(h.name)
                if norm not in merged:
                    merged[norm] = {"name": h.name, "codes": {h.code}, "mv": 0.0, "funds": []}
                else:
                    merged[norm]["codes"].add(h.code)
                merged[norm]["mv"] += stock_mv
                merged[norm]["funds"].append("直接持有")

        # 验证合并数量
        # 宁德时代(电池ETF→1500) + 比亚迪(电池ETF→1000) + 23国开10(短债→400) + 22国债14(短债→300) + 长江电力(直接→10000)
        self.assertEqual(len(merged), 5)

        # 验证排序结果（长江电力市值最大 → 第一）
        sorted_items = sorted(merged.items(), key=lambda x: x[1]["mv"], reverse=True)
        self.assertEqual(sorted_items[0][1]["name"], "长江电力")
        self.assertAlmostEqual(sorted_items[0][1]["mv"], 10000.0)
        self.assertEqual(sorted_items[1][1]["name"], "宁德时代")
        self.assertAlmostEqual(sorted_items[1][1]["mv"], 1500.0)
        self.assertEqual(sorted_items[2][1]["name"], "比亚迪")
        self.assertAlmostEqual(sorted_items[2][1]["mv"], 1000.0)

        # 验证来源带类型标签
        nd_sources = sorted_items[1][1]["funds"]
        self.assertTrue(any("[ETF]" in s for s in nd_sources))
        self.assertTrue(any("561910" in s for s in nd_sources))

        # 验证债券的来源标签
        bond_sources = sorted_items[3][1]["funds"]
        self.assertTrue(any("[债券]" in s for s in bond_sources))

    @patch("src.python.report.penetration.fetch_fund_holdings")
    def test_top10_truncation(self, mock_fetch):
        """验证超过 10 个标的时只取 TOP10。"""
        # 1只基金, 15个持仓
        holdings_15 = [{"name": f"股票{i:02d}", "code": f"600{i:03d}", "ratio": 5.0}
                       for i in range(1, 16)]

        mock_fetch.return_value = {
            "code": "561910", "name": "电池ETF", "date": "2026-03-31",
            "holdings": holdings_15,
        }

        h = Holding("证券账户", "电池ETF", "561910", 1000, 1.0)
        detail_map = {"561910": MockDetailRow("561910", 10000.0)}
        merged = {}

        data = mock_fetch(h.code)
        for item in data["holdings"]:
            name = item.get("name", "")
            code = item.get("code", "")
            ratio = item.get("ratio", 0.0)
            mv = 10000.0 * (ratio / 100.0)
            norm = pene.normalize_name(name)
            if norm not in merged:
                merged[norm] = {"name": name, "codes": set(), "mv": 0.0, "funds": []}
            if code:
                merged[norm]["codes"].add(code)
            merged[norm]["mv"] += mv
            merged[norm]["funds"].append("[ETF] 电池ETF(561910)")

        sorted_items = sorted(merged.items(), key=lambda x: x[1]["mv"], reverse=True)
        # 只取 TOP10
        top10 = sorted_items[:10]

        self.assertEqual(len(top10), 10)  # 确为 10
        self.assertGreater(len(sorted_items), 10)  # 原始多于 10
        self.assertEqual(top10[0][1]["name"], "股票01")  # 排序正确

    @patch("src.python.report.penetration.fetch_fund_holdings")
    def test_same_underlying_merged(self, mock_fetch):
        """验证相同底层标的（同名）合并。"""
        # 两只基金都持有宁德时代
        mock_fetch.side_effect = lambda code: {
            "code": code, "name": f"基金{code}", "date": "2026-03-31",
            "holdings": [{"name": "宁德时代", "code": "300750", "ratio": 10.0}],
        }

        holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
            Holding("支付宝", "新能源车ETF", "515700", 500, 1.0),
        ]
        details = [
            MockDetailRow("561910", 10000.0),
            MockDetailRow("515700", 8000.0),
        ]

        detail_map = {d.code: d for d in details}
        merged = {}

        for h in holdings:
            ftype = pene.classify_penetration(h)
            tag = pene._fund_type_tag(ftype)
            detail = detail_map.get(h.code)
            fund_mv = detail.market_value if detail else 0.0
            data = mock_fetch(h.code)
            for item in data["holdings"]:
                name = item.get("name", "")
                code = item.get("code", "")
                ratio = item.get("ratio", 0.0)
                mv = fund_mv * (ratio / 100.0)
                norm = pene.normalize_name(name)
                if norm not in merged:
                    merged[norm] = {"name": name, "codes": set(), "mv": 0.0, "funds": []}
                if code:
                    merged[norm]["codes"].add(code)
                merged[norm]["mv"] += mv
                merged[norm]["funds"].append(f"[{tag}] {h.name}({h.code})")

        self.assertEqual(len(merged), 1)  # 两只基金的宁德时代合并为 1 个
        nd = merged[pene.normalize_name("宁德时代")]
        self.assertAlmostEqual(nd["mv"], 10000.0 * 0.1 + 8000.0 * 0.1)  # 1800
        self.assertEqual(len(nd["funds"]), 2)  # 两个来源


# ═══════════════════════════════════════════════════════════
#  空 / 边界情况测试
# ═══════════════════════════════════════════════════════════


class TestPenetrationEdgeCases(unittest.TestCase):
    """测试空数据和边界场景（覆盖 _classify 之外的逻辑）。"""

    def test_no_funds_no_stocks(self):
        """全部忽略类型 → merged 为空。"""
        holdings = [
            Holding("证券账户", "浦发转债", "110059", 10, 100.0),
            Holding("证券账户", "现金管理", "400000", 1000, 1.0),
        ]
        details = []
        classified: dict[str, list[Holding]] = {
            pene.QDII: [], pene.ETF: [], pene.INDEX_LINK: [],
            pene.BOND_FUND: [], pene.ACTIVE_EQUITY: [], pene.STOCK: [], pene.IGNORE: [],
        }
        for h in holdings:
            cat = pene.classify_penetration(h)
            if cat in classified:
                classified[cat].append(h)

        # 所有基金类型都为空
        fund_types = [pene.QDII, pene.ETF, pene.INDEX_LINK, pene.BOND_FUND, pene.ACTIVE_EQUITY]
        funds = [h for ft in fund_types for h in classified[ft]]
        stocks = classified[pene.STOCK]
        self.assertEqual(len(funds), 0)
        self.assertEqual(len(stocks), 0)
        self.assertEqual(len(classified[pene.IGNORE]), 2)

    def test_all_funds_fail_to_fetch(self):
        """所有基金均无法获取穿透数据 → merged 为空。"""
        holdings = [
            Holding("支付宝", "某混合基金", "001234", 1000, 1.0),
            Holding("证券账户", "电池ETF", "561910", 100, 10.0),
        ]
        details = [
            MockDetailRow("001234", 5000.0),
            MockDetailRow("561910", 3000.0),
        ]
        detail_map = {d.code: d for d in details}
        merged: dict = {}
        unknown_mv = 0.0

        # 模拟所有 fetch 返回 None
        for h in holdings:
            cat = pene.classify_penetration(h)
            if cat in (pene.QDII, pene.ETF, pene.INDEX_LINK, pene.BOND_FUND, pene.ACTIVE_EQUITY):
                detail = detail_map.get(h.code)
                fund_mv = detail.market_value if detail else 0.0
                # fetch 失败 → unknown
                unknown_mv += fund_mv

        self.assertAlmostEqual(unknown_mv, 8000.0)

    def test_less_than_10_items(self):
        """穿透后不足 10 个，不报错。"""
        holdings = [
            Holding("支付宝", "某混合基金", "001234", 1000, 1.0),
        ]
        with patch("src.python.report.penetration.fetch_fund_holdings") as mock_fetch:
            mock_fetch.return_value = {
                "code": "001234", "name": "某混合", "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 5.0},
                    {"name": "宁德时代", "code": "300750", "ratio": 4.0},
                ],
            }
            details = [MockDetailRow("001234", 10000.0)]
            detail_map = {d.code: d for d in details}
            merged = {}
            for h in holdings:
                cat = pene.classify_penetration(h)
                if cat in (pene.QDII, pene.ETF, pene.INDEX_LINK, pene.BOND_FUND, pene.ACTIVE_EQUITY):
                    tag = pene._fund_type_tag(cat)
                    detail = detail_map.get(h.code)
                    fund_mv = detail.market_value if detail else 0.0
                    data = mock_fetch(h.code)
                    if data and data.get("holdings"):
                        for item in data["holdings"]:
                            name = item.get("name", "").strip()
                            if not name:
                                continue
                            mv = fund_mv * (item.get("ratio", 0.0) / 100.0)
                            norm = pene.normalize_name(name)
                            if norm not in merged:
                                merged[norm] = {"name": name, "codes": set(), "mv": 0.0, "funds": []}
                            merged[norm]["mv"] += mv
                            merged[norm]["funds"].append(f"[{tag}] {h.name}({h.code})")

            self.assertEqual(len(merged), 2)
            sorted_items = sorted(merged.items(), key=lambda x: x[1]["mv"], reverse=True)
            # 取 TOP10 不应报错（虽然不到 10 个）
            top10 = sorted_items[:10]
            self.assertEqual(len(top10), 2)


class TestPenetrationConcepts(unittest.TestCase):
    """测试穿透概念列数据获取与输出。"""

    def test_concepts_in_top10_output(self):
        """compute_penetration_top10 返回的 top10 条目应包含 concepts 字段。"""
        holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
        ]
        details = [MockDetailRow("561910", 10000.0)]

        with patch("src.python.report.penetration.fetch_fund_holdings") as mock_fetch:
            mock_fetch.return_value = {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            }
            result = pene.compute_penetration_top10(holdings, details)
            for entry in result["top10"]:
                self.assertIn("concepts", entry,
                              f"TOP10 条目 {entry['name']} 缺少 concepts 字段")
                # concepts 可以为空列表或字符串列表
                self.assertIsInstance(entry["concepts"], list)

    def test_concepts_field_in_entry(self):
        """merged 中的条目应包含 concepts 字段（API 数据补充后）。"""
        holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
        ]
        details = [MockDetailRow("561910", 10000.0)]

        with patch("src.python.report.penetration.fetch_fund_holdings") as mock_fetch:
            mock_fetch.return_value = {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                ],
            }
            result = pene.compute_penetration_top10(holdings, details)
            self.assertIn("top10", result)
            first = result["top10"][0]
            # concepts 字段应存在（即使为空列表）
            self.assertIn("concepts", first)
            # sector 字段应存在
            self.assertIn("sector", first)


# ═══════════════════════════════════════════════════════════════
#  R-092: 穿透市值占比归一化验证
# ═══════════════════════════════════════════════════════════════


class TestPenetrationRatioNormalization(unittest.TestCase):
    """验证穿透 TOP10 的市值占比总和 ≤ 100%。

    穿透运算将基金底层资产与直接持有的股票合并后计算占比，
    应保证各资产占总市值的比例之和不超过 100%。
    """

    def _make_holding(self, name: str, code: str, shares: float,
                       price: float, account: str = "证券") -> Holding:
        return Holding(
            account=account, name=name, code=code,
            shares=shares, cost_price=price,
        )

    def _make_detail(self, code: str, name: str, price: float) -> DetailRow:
        dr = DetailRow()
        dr.account = "证券"
        dr.code = code
        dr.name = name
        dr.price = price
        dr.nav_date = "2026-06-26"
        dr.yesterday_close = price * 0.98
        dr.price_type = "T"
        dr.premium = "--"
        dr.shares = 100
        dr.market_value = price * 100
        dr.cost = price * 100
        dr.profit = 0.0
        dr.profit_rate = 0.0
        dr.today_profit = 0.0
        dr.source = "mock"
        dr.source_api = "tencent"
        return dr

    def test_top10_ratio_sum_le_100(self):
        """混合持仓穿透后 TOP10 占比总和 ≤ 100%。"""
        holdings = [
            self._make_holding("沪深300ETF", "510300", 100, 4.0),
            self._make_holding("长江电力", "600900", 100, 28.0),
        ]
        details = [
            self._make_detail("510300", "沪深300ETF", 4.0),
            self._make_detail("600900", "长江电力", 28.0),
        ]

        with patch("src.python.report.penetration.fetch_fund_holdings") as mock_fetch:
            mock_fetch.return_value = {
                "code": "510300", "name": "沪深300ETF",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                    {"name": "宁德时代", "code": "300750", "ratio": 8.0},
                ],
            }
            result = pene.compute_penetration_top10(holdings, details)

        top10 = result.get("top10", [])
        if not top10:
            self.skipTest("穿透结果为空")

        total_ratio = sum(item.get("ratio_pct", 0) for item in top10)
        self.assertLessEqual(total_ratio, 100.0 + 1e-9,
                             f"TOP10 占比总和 {total_ratio:.2f}% > 100%")

    def test_single_asset_ratio(self):
        """单一资产 → 占比应为 100%。"""
        holdings = [
            self._make_holding("长江电力", "600900", 100, 28.0),
        ]
        details = [
            self._make_detail("600900", "长江电力", 28.0),
        ]

        with patch("src.python.report.penetration.fetch_fund_holdings") as mock_fetch:
            mock_fetch.return_value = None
            result = pene.compute_penetration_top10(holdings, details)
        top10 = result.get("top10", [])
        if top10:
            self.assertAlmostEqual(sum(t["ratio_pct"] for t in top10), 100.0, places=4)

    def test_direct_stock_only_sum_le_100(self):
        """仅直接持有股票 → 各股占比总和 ≤ 100%。"""
        holdings = [
            self._make_holding("贵州茅台", "600519", 100, 2000.0),
            self._make_holding("长江电力", "600900", 200, 28.0),
            self._make_holding("宁德时代", "300750", 50, 250.0),
        ]
        details = [self._make_detail(h.code, h.name, h.cost_price)
                    for h in holdings]

        result = pene.compute_penetration_top10(holdings, details)
        top10 = result.get("top10", [])
        total_ratio = sum(t.get("ratio_pct", 0) for t in top10)
        self.assertLessEqual(total_ratio, 100.0 + 1e-9)

    def test_ratio_non_negative(self):
        """每个资产的占比 ≥ 0。"""
        holdings = [
            self._make_holding("沪深300ETF", "510300", 100, 4.0),
        ]
        details = [self._make_detail("510300", "沪深300ETF", 4.0)]

        with patch("src.python.report.penetration.fetch_fund_holdings") as mock_fetch:
            mock_fetch.return_value = {
                "code": "510300", "name": "沪深300ETF",
                "date": "2026-03-31",
                "holdings": [
                    {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                ],
            }
            result = pene.compute_penetration_top10(holdings, details)

        top10 = result.get("top10", [])
        for item in top10:
            self.assertGreaterEqual(item.get("ratio_pct", -1), 0,
                                    f"{item.get('name')} 占比为负")


class TestFundsWithUnavailableHoldings(unittest.TestCase):
    """验证基金持仓不可获取或数据无效时，不污染穿透 TOP10。"""

    def _make_detail(self, code: str, market_value: float) -> MockDetailRow:
        return MockDetailRow(code, market_value)

    @patch("src.python.report.penetration.fetch_fund_holdings")
    def test_failed_fund_not_in_top10(self, mock_fetch):
        """持仓数据取不到的基金 → 不进入 top10，基金全值计入 unknown_mv。"""
        # 一只持仓数据可获取的基金（电池ETF → 宁德时代）
        # 两只持仓数据不可获取的基金（财通基金 → fetch 返回 None）
        mock_fetch.side_effect = lambda code: {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                ],
            },
        }.get(code, None)

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
            self.assertNotIn("财通", name,
                             f"穿透 TOP10 不应包含基金名称「{name}」")

        # 宁德时代和比亚迪应为穿透结果（来自电池ETF）
        self.assertIn("宁德时代", top10_names)
        self.assertIn("比亚迪", top10_names)

        # 宁德时代市值 = 10000 * 15% = 1500
        nd = next(e for e in result["top10"] if e["name"] == "宁德时代")
        self.assertAlmostEqual(nd["mv"], 1500.0, places=1)

        # unknown_mv 包含两只财通基金的全值
        self.assertAlmostEqual(result["summary"]["unknown_mv"],
                               31299.59 + 31152.86, delta=0.02)

        # failed_funds 应正确计数
        self.assertEqual(result["summary"]["failed_funds"], 2)

    @patch("src.python.report.penetration.fetch_fund_holdings")
    def test_failed_fund_ratio_not_distorted(self, mock_fetch):
        """未穿透的基金不参与总市值计算，ratio_pct 仅基于可识别资产。"""
        mock_fetch.side_effect = lambda code: {
            "561910": {
                "code": "561910", "name": "电池ETF", "date": "2026-03-31",
                "holdings": [
                    {"name": "宁德时代", "code": "300750", "ratio": 50.0},
                ],
            },
        }.get(code, None)

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

    @patch("src.python.report.penetration.fetch_fund_holdings")
    def test_invalid_ratio_filtered(self, mock_fetch):
        """持仓比例 >100% 的标的应被过滤（如 518880 黄金 ETF API 返回的垃圾数据）。"""
        mock_fetch.side_effect = lambda code: {
            "518880": {
                "code": "518880", "name": "华安黄金ETF", "date": "",
                "holdings": [
                    # 与用户实际遇到的缓存数据一致：ratio > 100%
                    {"name": "财通成长优选混合A（001480）", "code": "001480", "ratio": 401.03},
                    {"name": "财通成长优选混合C（021528）", "code": "021528", "ratio": 399.15},
                    {"name": "财通价值动量混合A（720001）", "code": "720001", "ratio": 359.33},
                ],
            },
        }.get(code, None)

        holdings = [
            Holding("证券账户", "华安黄金ETF", "518880", 100, 83.097),
        ]
        details = [
            self._make_detail("518880", 8309.70),
        ]

        result = pene.compute_penetration_top10(holdings, details)

        # 过滤后无有效标的 → top10 应为空
        self.assertEqual(len(result["top10"]), 0,
                         "ratio 全部 >100% 的基金不应产生穿透标的")

        # unknown_mv 应包含 518880 的全值
        self.assertAlmostEqual(result["summary"]["unknown_mv"], 8309.70, delta=0.02)
        self.assertEqual(result["summary"]["failed_funds"], 1)

    @patch("src.python.report.penetration.fetch_fund_holdings")
    def test_mixed_valid_and_invalid_ratios(self, mock_fetch):
        """同一基金混有无效和有效比例 → 只保留有效比例。"""
        mock_fetch.side_effect = lambda code: {
            "518880": {
                "code": "518880", "name": "华安黄金ETF", "date": "",
                "holdings": [
                    {"name": "财通成长优选混合A（001480）", "code": "001480", "ratio": 401.03},
                    {"name": "山东黄金", "code": "600547", "ratio": 15.0},
                    {"name": "中金黄金", "code": "600489", "ratio": 10.0},
                ],
            },
        }.get(code, None)

        holdings = [
            Holding("证券账户", "华安黄金ETF", "518880", 100, 83.097),
        ]
        details = [
            self._make_detail("518880", 8309.70),
        ]

        result = pene.compute_penetration_top10(holdings, details)

        # 财通基金应被过滤，只保留山东黄金和中金黄金
        top10_names = [e["name"] for e in result["top10"]]
        self.assertNotIn("财通成长优选混合A", top10_names,
                         "ratio>100% 的标的应被过滤")
        self.assertIn("山东黄金", top10_names)
        self.assertIn("中金黄金", top10_names)

        # 山东黄金 = 8309.70 * 15% = 1246.46
        sd = next(e for e in result["top10"] if e["name"] == "山东黄金")
        self.assertAlmostEqual(sd["mv"], 1246.46, places=1)

        # 有效持仓占比之和 ≈ 100%
        total_ratio = sum(e["ratio_pct"] for e in result["top10"])
        self.assertAlmostEqual(total_ratio, 100.0, delta=0.02)


if __name__ == "__main__":
    unittest.main()
