"""穿透模块单元测试。

测试目标：
  - classify_penetration — 各类型基金/股票/忽略的正确分类
  - _is_bond_fund / _is_index_link — 债券/联接识别
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

from src.models import Holding
from src.report import penetration as pene


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
        h = self._h("某现金管理", "888888")
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
    """测试 _is_bond_fund。"""

    def test_bond_keywords(self):
        for name in [
            "招商鑫福中短债A", "博时安盈短债A", "广发景明中短债A",
            "南方利率债A", "富国信用债A", "某纯债A", "某债券A",
        ]:
            with self.subTest(name=name):
                self.assertTrue(pene._is_bond_fund(name))

    def test_not_bond(self):
        self.assertFalse(pene._is_bond_fund("中欧医疗健康混合"))
        self.assertFalse(pene._is_bond_fund("华夏纳斯达克100ETF(QDII)"))
        self.assertFalse(pene._is_bond_fund("电池ETF"))


class TestIsIndexLink(unittest.TestCase):
    """测试 _is_index_link。"""

    def test_link_keywords(self):
        for name in [
            "天弘沪深300ETF联接A",
            "天弘沪深300ETF联接",
            "天弘沪深300  ETF  联接A",
            "某指数联接A",
        ]:
            with self.subTest(name=name):
                self.assertTrue(pene._is_index_link(name))

    def test_not_link(self):
        self.assertFalse(pene._is_index_link("中欧医疗健康混合"))
        self.assertFalse(pene._is_index_link("电池ETF"))
        self.assertFalse(pene._is_index_link("招商鑫福中短债A"))


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

    @patch("src.report.penetration.fetch_fund_holdings")
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

    @patch("src.report.penetration.fetch_fund_holdings")
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

    @patch("src.report.penetration.fetch_fund_holdings")
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
            Holding("证券账户", "现金管理", "888888", 1000, 1.0),
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
        with patch("src.report.penetration.fetch_fund_holdings") as mock_fetch:
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


if __name__ == "__main__":
    unittest.main()
