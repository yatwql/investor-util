"""品种级数据状态标注单元测试 — 数据质量仪表盘品种覆盖诊断基础。

覆盖：
  - classify_code_format — 代码格式校验（A股/港股/场内/场外/异常格式/浮点假象）
  - names_match / normalize_name — 名称比对（精确/简称子串/空名）
  - annotate_position_status — 品种状态清单（有行情/净值缺失/可能退市/代码格式可疑/名称不匹配）
  - build_coverage_summary — 覆盖诊断契约摘要（abnormal_count / summary）
  - read_holdings 本地状态标注（data_status 随解析结果输出）

运行：
  python -m pytest src/test/unit/core/test_holding_status.py -v
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.python.core import holding_status as hs
from src.python.core.models import Holding
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


def _holding(name: str, code: str, account: str = "证券") -> Holding:
    return Holding(account=account, name=name, code=code, shares=100, cost_price=10.0)


def _detail(code: str, name: str, price: float = 10.0) -> SimpleNamespace:
    """构造最小行情明细（鸭子类型，仅含标注所需的属性）。"""
    return SimpleNamespace(code=code, name=name, price=price, price_type="场内收盘价(T)")


# ═════════════════════════════════════════════════════════════
#  classify_code_format
# ═════════════════════════════════════════════════════════════


class TestClassifyCodeFormat(unittest.TestCase):
    """代码格式校验。"""

    def test_a_share_ok(self):
        """6 位 A 股代码 → ok。"""
        self.assertEqual(hs.classify_code_format("600900"), hs.STATUS_OK)

    def test_exchange_fund_ok(self):
        """5 开头场内基金/ETF → ok。"""
        self.assertEqual(hs.classify_code_format("510300"), hs.STATUS_OK)

    def test_otc_fund_ok(self):
        """00 开头场外基金 → ok。"""
        self.assertEqual(hs.classify_code_format("005827"), hs.STATUS_OK)

    def test_hk_stock_ok(self):
        """5 位港股通代码 → ok。"""
        self.assertEqual(hs.classify_code_format("00700"), hs.STATUS_OK)

    def test_exchange_prefix_stripped(self):
        """带 sh/sz 前缀 → 去除前缀后仍合法。"""
        self.assertEqual(hs.classify_code_format("sh600900"), hs.STATUS_OK)
        self.assertEqual(hs.classify_code_format("sz000001"), hs.STATUS_OK)

    def test_uppercase_prefix_stripped(self):
        """大写 SH/SZ/BJ 前缀 → 小写归一后仍合法。"""
        self.assertEqual(hs.classify_code_format("SH600900"), hs.STATUS_OK)
        self.assertEqual(hs.classify_code_format("SZ000001"), hs.STATUS_OK)
        self.assertEqual(hs.classify_code_format("BJ430047"), hs.STATUS_OK)

    def test_float_artifact_normalized(self):
        """Excel 浮点假象（"600900.0"）→ 归一为合法。"""
        self.assertEqual(hs.classify_code_format("600900.0"), hs.STATUS_OK)

    def test_letters_bad(self):
        """含字母的代码 → bad_code_format。"""
        self.assertEqual(hs.classify_code_format("ABC600"), hs.STATUS_BAD_CODE_FORMAT)

    def test_too_short_bad(self):
        """长度不足（3 位）→ bad_code_format。"""
        self.assertEqual(hs.classify_code_format("123"), hs.STATUS_BAD_CODE_FORMAT)

    def test_seven_digit_bad(self):
        """7 位数字 → bad_code_format。"""
        self.assertEqual(hs.classify_code_format("6009000"), hs.STATUS_BAD_CODE_FORMAT)

    def test_empty_bad(self):
        """空代码 → bad_code_format。"""
        self.assertEqual(hs.classify_code_format(""), hs.STATUS_BAD_CODE_FORMAT)
        self.assertEqual(hs.classify_code_format(None), hs.STATUS_BAD_CODE_FORMAT)


# ═════════════════════════════════════════════════════════════
#  names_match / normalize_name
# ═════════════════════════════════════════════════════════════


class TestNamesMatch(unittest.TestCase):
    """持仓名称与数据源名称比对。"""

    def test_exact_match(self):
        """完全相同 → 匹配。"""
        self.assertTrue(hs.names_match("贵州茅台", "贵州茅台"))

    def test_whitespace_insensitive(self):
        """空白差异不影响匹配。"""
        self.assertTrue(hs.names_match(" 贵州 茅台 ", "贵州茅台"))

    def test_abbreviation_substring(self):
        """两字简称（茅台 ⊆ 贵州茅台）→ 匹配。"""
        self.assertTrue(hs.names_match("茅台", "贵州茅台"))

    def test_suffix_substring(self):
        """名称含后缀（易方达蓝筹精选 ⊆ 易方达蓝筹精选混合）→ 匹配。"""
        self.assertTrue(hs.names_match("易方达蓝筹精选", "易方达蓝筹精选混合"))

    def test_completely_different(self):
        """完全不同的名称 → 不匹配。"""
        self.assertFalse(hs.names_match("贵州白酒", "贵州茅台"))
        self.assertFalse(hs.names_match("长江电力", "贵州茅台"))

    def test_empty_name_tolerated(self):
        """任一侧名称为空 → 不判不匹配。"""
        self.assertTrue(hs.names_match("", "贵州茅台"))
        self.assertTrue(hs.names_match("贵州茅台", ""))

    def test_single_char_not_substring_match(self):
        """单字符简称 → 不判子串匹配（仅 ≥2 字符短名放宽）。"""
        self.assertFalse(hs.names_match("茅", "贵州茅台"))
        self.assertFalse(hs.names_match("贵", "贵州茅台"))

    def test_normalize_strips_case(self):
        """normalize_name 去空白并转小写。"""
        self.assertEqual(hs.normalize_name("  QDII-ETF  "), "qdii-etf")


# ═════════════════════════════════════════════════════════════
#  annotate_position_status
# ═════════════════════════════════════════════════════════════


class TestAnnotatePositionStatus(unittest.TestCase):
    """品种状态清单标注。"""

    def test_all_normal(self):
        """正常品种（有行情、名称匹配）→ 全部标注有行情。"""
        holdings = [
            _holding("长江电力", "600900"),
            _holding("贵州茅台", "600519"),
        ]
        details = [
            _detail("600900", "长江电力", 25.0),
            _detail("600519", "贵州茅台", 1700.0),
        ]
        items = hs.annotate_position_status(holdings, details)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i["status"] == hs.STATUS_OK for i in items))
        self.assertTrue(all(i["status_label"] == "有行情" for i in items))

    def test_bad_code_format(self):
        """代码格式可疑 → 标注 bad_code_format（不依赖行情数据）。"""
        holdings = [_holding("异常品种", "ABC600")]
        items = hs.annotate_position_status(holdings, None)
        self.assertEqual(items[0]["status"], hs.STATUS_BAD_CODE_FORMAT)
        self.assertEqual(items[0]["status_label"], "代码格式可疑")
        self.assertIn("代码格式", items[0]["reason"])

    def test_nav_missing_fund(self):
        """基金无净值 → 标注净值缺失。"""
        holdings = [_holding("易方达蓝筹精选", "005827", account="支付宝")]
        items = hs.annotate_position_status(holdings, [])
        self.assertEqual(items[0]["status"], hs.STATUS_NAV_MISSING)
        self.assertEqual(items[0]["status_label"], "净值缺失")

    def test_fund_zero_price_nav_missing(self):
        """基金行情 price=0 → 净值缺失。"""
        holdings = [_holding("易方达蓝筹精选", "005827", account="支付宝")]
        items = hs.annotate_position_status(holdings, [_detail("005827", "易方达蓝筹精选", 0.0)])
        self.assertEqual(items[0]["status"], hs.STATUS_NAV_MISSING)

    def test_delisted_stock_no_quote(self):
        """股票无行情 → 可能退市。"""
        holdings = [_holding("某退市股", "600999")]
        items = hs.annotate_position_status(holdings, [])
        self.assertEqual(items[0]["status"], hs.STATUS_POSSIBLY_DELISTED)
        self.assertEqual(items[0]["status_label"], "可能退市")

    def test_name_mismatch(self):
        """持仓名称与数据源名称不一致 → 名称不匹配。"""
        holdings = [_holding("贵州白酒", "600519")]
        items = hs.annotate_position_status(holdings, [_detail("600519", "贵州茅台", 1700.0)])
        self.assertEqual(items[0]["status"], hs.STATUS_NAME_MISMATCH)

    def test_name_abbreviation_not_flag(self):
        """简称（茅台 vs 贵州茅台）→ 不判名称不匹配。"""
        holdings = [_holding("茅台", "600519")]
        items = hs.annotate_position_status(holdings, [_detail("600519", "贵州茅台", 1700.0)])
        self.assertEqual(items[0]["status"], hs.STATUS_OK)

    def test_multi_account(self):
        """多账户多品种 → 逐品种独立标注。"""
        holdings = [
            _holding("长江电力", "600900", account="证券"),
            _holding("易方达蓝筹精选", "005827", account="支付宝"),
        ]
        details = [_detail("600900", "长江电力", 25.0)]
        items = hs.annotate_position_status(holdings, details)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["account"], "证券")
        self.assertEqual(items[0]["status"], hs.STATUS_OK)
        self.assertEqual(items[1]["account"], "支付宝")
        self.assertEqual(items[1]["status"], hs.STATUS_NAV_MISSING)

    def test_dict_detail_supported(self):
        """dict 形式行情明细 → 状态标注一致（_detail_value 兼容 dict/对象）。"""
        holdings = [_holding("长江电力", "600900")]
        details = [{"code": "600900", "name": "长江电力", "price": 25.0, "price_type": "场内收盘价(T)"}]
        items = hs.annotate_position_status(holdings, details)
        self.assertEqual(items[0]["status"], hs.STATUS_OK)

    def test_stock_no_quote_type_delisted(self):
        """股票 price_type 为「暂无行情」→ 可能退市（非基金）。"""
        holdings = [_holding("某退市股", "600999")]
        details = [SimpleNamespace(code="600999", name="某退市股", price=10.0, price_type="暂无行情")]
        items = hs.annotate_position_status(holdings, details)
        self.assertEqual(items[0]["status"], hs.STATUS_POSSIBLY_DELISTED)
        self.assertIn("退市", items[0]["reason"])

    def test_duplicate_code_keeps_first_detail(self):
        """同代码多条明细 → 取第一条（setdefault 语义），不被后续覆盖。"""
        holdings = [_holding("长江电力", "600900")]
        details = [
            _detail("600900", "长江电力", 25.0),
            _detail("600900", "名称不匹配的假数据", 25.0),
        ]
        items = hs.annotate_position_status(holdings, details)
        self.assertEqual(items[0]["status"], hs.STATUS_OK)  # 若取第二条会判名称不匹配

    def test_behavioral_mixed_five(self):
        """行为断言：5 品种（1 格式错码、1 净值缺失）→ 状态清单准确标注全部异常。"""
        holdings = [
            _holding("长江电力", "600900", account="证券"),
            _holding("贵州茅台", "600519", account="证券"),
            _holding("异常品种", "XYZ123", account="证券"),
            _holding("易方达蓝筹精选", "005827", account="支付宝"),
            _holding("某退市股", "600999", account="证券"),
        ]
        details = [
            _detail("600900", "长江电力", 25.0),
            _detail("600519", "贵州茅台", 1700.0),
        ]
        items = hs.annotate_position_status(holdings, details)
        status_by_code = {i["code"]: i["status"] for i in items}
        self.assertEqual(status_by_code["600900"], hs.STATUS_OK)
        self.assertEqual(status_by_code["600519"], hs.STATUS_OK)
        self.assertEqual(status_by_code["XYZ123"], hs.STATUS_BAD_CODE_FORMAT)
        self.assertEqual(status_by_code["005827"], hs.STATUS_NAV_MISSING)
        self.assertEqual(status_by_code["600999"], hs.STATUS_POSSIBLY_DELISTED)
        self.assertEqual(len(items), 5)


# ═════════════════════════════════════════════════════════════
#  build_coverage_summary
# ═════════════════════════════════════════════════════════════


class TestBuildCoverageSummary(unittest.TestCase):
    """覆盖诊断契约摘要。"""

    def test_summary_counts_abnormal(self):
        """异常品种计数与摘要文本正确。"""
        holdings = [
            _holding("长江电力", "600900"),
            _holding("异常品种", "XYZ123"),
            _holding("易方达蓝筹精选", "005827", account="支付宝"),
        ]
        details = [_detail("600900", "长江电力", 25.0)]
        summary = hs.build_coverage_summary(holdings, details)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["abnormal_count"], 2)
        self.assertIn("3", summary["summary"])
        self.assertIn("2", summary["summary"])

    def test_empty_holdings(self):
        """无持仓 → available=False，不报错。"""
        summary = hs.build_coverage_summary([], [])
        self.assertFalse(summary["available"])
        self.assertEqual(summary["items"], [])
        self.assertEqual(summary["abnormal_count"], 0)


# ═════════════════════════════════════════════════════════════
#  read_holdings 本地状态标注集成
# ═════════════════════════════════════════════════════════════


class TestReaderStatusAnnotation(unittest.TestCase):
    """reader 解析结果携带本地可判定的 data_status。"""

    def test_parse_workbook_sets_bad_code_status(self):
        """格式错码 → Holding.data_status = bad_code_format。"""
        from src.python.core import reader

        header = ["名称", "代码", "持仓份额", "每份成本"]
        data = [
            ["长江电力", "600900", 200, 50.0],
            ["异常品种", "XYZ123", 100, 10.0],
        ]

        class _Cell:
            def __init__(self, value):
                self.value = value

        class _Ws:
            max_row = 3

            def iter_rows(self, min_row=1, max_row=None, values_only=False):
                if min_row == 1 and not values_only:
                    return iter([[_Cell(v) for v in header]])
                return iter(data)

        class _Wb:
            sheetnames = ["证券账户"]

            def __getitem__(self, name):
                return _Ws()

        holdings = reader._parse_workbook(_Wb())
        self.assertEqual(len(holdings), 2)
        self.assertEqual(holdings[0].data_status, "")
        self.assertEqual(holdings[1].data_status, hs.STATUS_BAD_CODE_FORMAT)

    def test_normal_holding_status_empty(self):
        """正常品种 → data_status 为空（待行情标注），不改变解析结果。"""
        from src.python.core import reader

        header = ["名称", "代码", "持仓份额", "每份成本"]
        data = [["长江电力", 600900, 200, 50.0]]

        class _Cell:
            def __init__(self, value):
                self.value = value

        class _Ws:
            max_row = 2

            def iter_rows(self, min_row=1, max_row=None, values_only=False):
                if min_row == 1 and not values_only:
                    return iter([[_Cell(v) for v in header]])
                return iter(data)

        class _Wb:
            sheetnames = ["证券账户"]

            def __getitem__(self, name):
                return _Ws()

        holdings = reader._parse_workbook(_Wb())
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0].code, "600900")  # 代码仍为字符串，未因浮点/整型假象变化
        self.assertEqual(holdings[0].data_status, "")


if __name__ == "__main__":
    unittest.main()
