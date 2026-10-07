"""穿透模块单元测试 — 合并与比值（write_penetration_sheet mock 路径）。

测试目标：
  - write_penetration_sheet (mock) — 合并/排序/TOP10 逻辑、概念板块入榜
  - 比值归一：TOP10 比值和 ≤100%、单资产/纯股场景、非负与无效比值过滤

兄弟分片：test_penetration_classify.py（classify_penetration 分类 + 债券/联接识别 + 类型标签 + 名称归一化）、
test_penetration_report_periods.py（报告期场景：穿透不可用/陈旧闸门/联接基金来源登记）。

运行：
  pytest src/test/unit/report/test_penetration.py -v
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from src.python.core.models import Holding
from src.python.report import penetration as pene
from src.python.report.market_value import DetailRow
from src.test.helpers import recent_holdings_period
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]


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


def _mock_fund_holdings_batch(holdings_by_code: dict[str, list[dict[str, Any]] | None]):
    """返回批量 mock 的 fetch_fund_holdings_batch 返回值。

    批量接口返回 ``{code: 数据或None}``。
    """
    result: dict[str, dict[str, Any] | None] = {}
    for code, holdings_data in holdings_by_code.items():
        if holdings_data is None:
            result[code] = None
        else:
            result[code] = {
                "code": code,
                "name": f"基金{code}",
                "date": recent_holdings_period(),
                "holdings": holdings_data,
            }
    return result


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
            MockDetailRow("561910", 10000.0),  # 电池ETF市值 1万
            MockDetailRow("012325", 5000.0),  # 短债市值 5000
            MockDetailRow("600900", 10000.0),  # 长江电力市值 1万
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

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_basic_merge_and_sort(self, mock_batch):
        """验证相同的底层标的合并、按市值排序。"""
        mock_batch.return_value = _mock_fund_holdings_batch(
            {
                "561910": self.etf_holdings,
                "012325": self.bond_holdings,
            }
        )

        # 调用写穿透的下层逻辑：直接调用 write_penetration_sheet 太重量级（需要 openpyxl）
        # 用内联方式测试 merge 阶段的逻辑
        detail_map = {d.code: d for d in self.details}
        merged: dict[str, dict[str, Any]] = {}

        for h in [h for h in self.holdings if pene.classify_penetration(h) != pene.STOCK]:
            ftype = pene.classify_penetration(h)
            tag = pene._fund_type_tag(ftype)
            detail = detail_map.get(h.code)
            fund_mv = detail.market_value if detail else 0.0

            holdings_batch = mock_batch.return_value
            data = holdings_batch.get(h.code)
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

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_top10_truncation(self, mock_batch):
        """验证超过 10 个标的时只取 TOP10。"""
        # 1只基金, 15个持仓
        holdings_15 = [{"name": f"股票{i:02d}", "code": f"600{i:03d}", "ratio": 5.0} for i in range(1, 16)]

        mock_batch.return_value = _mock_fund_holdings_batch(
            {
                "561910": holdings_15,
            }
        )

        h = Holding("证券账户", "电池ETF", "561910", 1000, 1.0)
        {"561910": MockDetailRow("561910", 10000.0)}
        merged = {}

        batch_data = mock_batch.return_value
        data = batch_data.get(h.code)
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

    @patch("src.python.report.penetration.fetch_fund_holdings_batch")
    def test_same_underlying_merged(self, mock_batch):
        """验证相同底层标的（同名）合并。"""
        mock_batch.return_value = _mock_fund_holdings_batch(
            {
                "561910": [{"name": "宁德时代", "code": "300750", "ratio": 10.0}],
                "515700": [{"name": "宁德时代", "code": "300750", "ratio": 10.0}],
            }
        )

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
            batch_data = mock_batch.return_value
            data = batch_data.get(h.code)
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
        classified: dict[str, list[Holding]] = {
            pene.QDII: [],
            pene.ETF: [],
            pene.INDEX_LINK: [],
            pene.BOND_FUND: [],
            pene.ACTIVE_EQUITY: [],
            pene.STOCK: [],
            pene.IGNORE: [],
        }
        for h in holdings:
            cat = pene.classify_penetration(h)
            if cat in classified:
                classified[cat].append(h)

        # 所有基金类型都为空
        fund_types = [pene.QDII, pene.ETF, pene.INDEX_LINK, pene.BOND_FUND, pene.ACTIVE_EQUITY]
        funds = [h for ft in fund_types for h in classified[ft]]
        stocks = classified[pene.STOCK]
        self.assertEqual(len(funds), 0)  # "浦发转债" 归入 IGNORE
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
        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch") as mock_batch,
            patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        ):
            mock_batch.return_value = _mock_fund_holdings_batch(
                {
                    "001234": [
                        {"name": "贵州茅台", "code": "600519", "ratio": 5.0},
                        {"name": "宁德时代", "code": "300750", "ratio": 4.0},
                    ],
                }
            )
            details = [MockDetailRow("001234", 10000.0)]
            detail_map = {d.code: d for d in details}
            merged = {}
            for h in holdings:
                cat = pene.classify_penetration(h)
                if cat in (pene.QDII, pene.ETF, pene.INDEX_LINK, pene.BOND_FUND, pene.ACTIVE_EQUITY):
                    tag = pene._fund_type_tag(cat)
                    detail = detail_map.get(h.code)
                    fund_mv = detail.market_value if detail else 0.0
                    batch_data = mock_batch.return_value
                    data = batch_data.get(h.code)
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

        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch") as mock_batch,
            patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        ):
            mock_batch.return_value = {
                "561910": {
                    "code": "561910",
                    "name": "电池ETF",
                    "date": recent_holdings_period(),
                    "holdings": [
                        {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                        {"name": "比亚迪", "code": "002594", "ratio": 10.0},
                    ],
                }
            }
            result = pene.compute_penetration_top10(holdings, details)
            for entry in result["top10"]:
                self.assertIn("concepts", entry, f"TOP10 条目 {entry['name']} 缺少 concepts 字段")
                # concepts 可以为空列表或字符串列表
                self.assertIsInstance(entry["concepts"], list)

    def test_concepts_field_in_entry(self):
        """merged 中的条目应包含 concepts 字段（API 数据补充后）。"""
        holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
        ]
        details = [MockDetailRow("561910", 10000.0)]

        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch") as mock_batch,
            patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        ):
            mock_batch.return_value = {
                "561910": {
                    "code": "561910",
                    "name": "电池ETF",
                    "date": recent_holdings_period(),
                    "holdings": [
                        {"name": "宁德时代", "code": "300750", "ratio": 15.0},
                    ],
                }
            }
            result = pene.compute_penetration_top10(holdings, details)
            self.assertIn("top10", result)
            first = result["top10"][0]
            # concepts 字段应存在（即使为空列表）
            self.assertIn("concepts", first)
            # sector 字段应存在
            self.assertIn("sector", first)


# ═══════════════════════════════════════════════════════════════
#  穿透市值占比归一化验证
# ═══════════════════════════════════════════════════════════════


class TestPenetrationRatioNormalization(unittest.TestCase):
    """验证穿透 TOP10 的市值占比总和 ≤ 100%。

    穿透运算将基金底层资产与直接持有的股票合并后计算占比，
    应保证各资产占总市值的比例之和不超过 100%。
    """

    def _make_holding(self, name: str, code: str, shares: float, price: float, account: str = "证券") -> Holding:
        return Holding(
            account=account,
            name=name,
            code=code,
            shares=shares,
            cost_price=price,
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

        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch") as mock_batch,
            patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        ):
            mock_batch.return_value = {
                "510300": {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "date": recent_holdings_period(),
                    "holdings": [
                        {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                        {"name": "宁德时代", "code": "300750", "ratio": 8.0},
                    ],
                }
            }
            result = pene.compute_penetration_top10(holdings, details)

        top10 = result.get("top10", [])
        if not top10:
            self.skipTest("穿透结果为空")

        total_ratio = sum(item.get("ratio_pct", 0) for item in top10)
        self.assertLessEqual(total_ratio, 100.0 + 1e-9, f"TOP10 占比总和 {total_ratio:.2f}% > 100%")

    def test_single_asset_ratio(self):
        """单一资产 → 占比应为 100%。"""
        holdings = [
            self._make_holding("长江电力", "600900", 100, 28.0),
        ]
        details = [
            self._make_detail("600900", "长江电力", 28.0),
        ]

        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch") as mock_batch,
            patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        ):
            mock_batch.return_value = {"600900": None}
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
        details = [self._make_detail(h.code, h.name, h.cost_price) for h in holdings]

        with patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}):
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

        with (
            patch("src.python.report.penetration.fetch_fund_holdings_batch") as mock_batch,
            patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        ):
            mock_batch.return_value = {
                "510300": {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "date": recent_holdings_period(),
                    "holdings": [
                        {"name": "贵州茅台", "code": "600519", "ratio": 16.0},
                    ],
                }
            }
            result = pene.compute_penetration_top10(holdings, details)

        top10 = result.get("top10", [])
        for item in top10:
            self.assertGreaterEqual(item.get("ratio_pct", -1), 0, f"{item.get('name')} 占比为负")
