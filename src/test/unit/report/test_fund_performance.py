"""基金业绩分析模块单元测试。

测试目标：
  - _is_fund — 基金识别逻辑（股票排除、基金账户覆盖）
  - _fund_display_type — 穿透分类 -> 中文显示标签（mock classify_penetration）
  - _format_return — 收益率格式化（含边界）
  - _format_rank — 排名格式化
  - _RATING_COMMENT — 评级映射完整性
  - write_fund_performance_sheet — mock API + writer 主流程
      (正常 / 空基金 / 全部获取失败 / 部分失败 / 评级标色 / 评级分布)

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_fund_performance -v
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, call, patch

from src.python.models import Holding
from src.python.report import fund_performance as fp
from src.python.report import penetration as pene
from src.python.report.styles import BLUE_FONT, GREEN_FONT, RED_FONT
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report]




# ============================================================
#  Helper
# ============================================================

class _MockDetailRow:
    """替代 DetailRow，避免 import openpyxl 重量级依赖。"""
    def __init__(self, code: str, profit: float = 0.0,
                 profit_rate: float = 0.0, market_value: float = 0.0):
        self.code = code
        self.profit = profit
        self.profit_rate = profit_rate
        self.market_value = market_value
        self.account = ""
        self.name = ""
        self.shares = 0.0


# ============================================================
#  _is_fund
# ============================================================

class TestIsFund(unittest.TestCase):
    """测试 _is_fund 基金识别逻辑。"""

    def _h(self, name: str, code: str = "",
           account: str = "证券账户") -> Holding:
        return Holding(account=account, name=name, code=code,
                       shares=1.0, cost_price=1.0)

    # -- 股票排除 --

    def test_stock_sh_6_excluded(self):
        """6 开头上海股票 + 证券账户 -> False"""
        h = self._h("长江电力", "600900")
        self.assertFalse(fp._is_fund(h))

    def test_stock_sz_0_excluded(self):
        """0 开头深圳股票 + 证券账户 -> False"""
        h = self._h("平安银行", "000001")
        self.assertFalse(fp._is_fund(h))

    def test_stock_cyb_3_excluded(self):
        """3 开头创业板股票 + 证券账户 -> False"""
        h = self._h("宁德时代", "300750")
        self.assertFalse(fp._is_fund(h))

    # -- ETF 绕过股票排除 --

    def test_etf_name_bypasses_stock_check(self):
        """名称含 ETF + 6 开头代码 -> True（ETF 绕过股票排除）"""
        for name in ["半导体ETF", "电池ETF", "消费ETF"]:
            with self.subTest(name=name):
                h = self._h(name, "512480")
                self.assertTrue(fp._is_fund(h))

    # -- 场外基金账户覆盖 --

    def test_fund_in_alipay(self):
        """6 开头代码 + 支付宝 -> True"""
        h = self._h("某混合基金", "600001", "支付宝")
        self.assertTrue(fp._is_fund(h))

    def test_fund_in_wechat(self):
        """0 开头代码 + 微信 -> True"""
        h = self._h("某货币基金", "000001", "微信")
        self.assertTrue(fp._is_fund(h))

    def test_fund_in_bank(self):
        """3 开头代码 + 银行 -> True"""
        h = self._h("某稳健增长", "300001", "银行")
        self.assertTrue(fp._is_fund(h))

    def test_fund_in_fund_account(self):
        """6 开头代码 + 基金账户 -> True"""
        h = self._h("某指数基金", "600001", "基金账户")
        self.assertTrue(fp._is_fund(h))

    # -- 非股票前缀代码始终为基金 --

    def test_non_stock_prefix_codes(self):
        """1 / 5 / 8 开头代码（非股票前缀）-> True"""
        cases = [("某债券", "110011"), ("某ETF", "510050"),
                 ("某产品", "888888")]
        for name, code in cases:
            with self.subTest(code=code):
                h = self._h(name, code)
                self.assertTrue(fp._is_fund(h))

    # -- QDII / 空代码 --

    def test_qdii_is_fund(self):
        """QDII 基金 -> True"""
        h = self._h("华夏纳斯达克100ETF(QDII)", "513300")
        self.assertTrue(fp._is_fund(h))

    def test_empty_code_is_fund(self):
        """空代码 -> True（不触发前缀检查）"""
        h = self._h("某基金", "")
        self.assertTrue(fp._is_fund(h))


# ============================================================
#  _fund_display_type
# ============================================================

class TestFundDisplayType(unittest.TestCase):
    """测试 _fund_display_type 穿透分类到中文标签的映射（mock classify_penetration）。"""

    def _h(self) -> Holding:
        return Holding("账户", "名称", "000000", 1.0, 1.0)

    @patch("src.python.report.fund_performance.classify_penetration")
    def test_qdii_label(self, mock_cls):
        """QDII -> 场外QDII基金"""
        mock_cls.return_value = pene.QDII
        self.assertEqual(fp._fund_display_type(self._h()), "场外QDII基金")

    @patch("src.python.report.fund_performance.classify_penetration")
    def test_etf_label(self, mock_cls):
        """ETF -> 场内ETF"""
        mock_cls.return_value = pene.ETF
        self.assertEqual(fp._fund_display_type(self._h()), "场内ETF")

    @patch("src.python.report.fund_performance.classify_penetration")
    def test_index_link_label(self, mock_cls):
        """INDEX_LINK -> 场外指数基金"""
        mock_cls.return_value = pene.INDEX_LINK
        self.assertEqual(fp._fund_display_type(self._h()), "场外指数基金")

    @patch("src.python.report.fund_performance.classify_penetration")
    def test_bond_fund_label(self, mock_cls):
        """BOND_FUND -> 场外债券基金"""
        mock_cls.return_value = pene.BOND_FUND
        self.assertEqual(fp._fund_display_type(self._h()), "场外债券基金")

    @patch("src.python.report.fund_performance.classify_penetration")
    def test_active_equity_label(self, mock_cls):
        """ACTIVE_EQUITY -> 场外主动型基金"""
        mock_cls.return_value = pene.ACTIVE_EQUITY
        self.assertEqual(fp._fund_display_type(self._h()), "场外主动型基金")

    @patch("src.python.report.fund_performance.classify_penetration")
    def test_unknown_type_fallback(self, mock_cls):
        """未知穿透类型 -> '--'"""
        mock_cls.return_value = "SOME_UNKNOWN_TYPE"
        self.assertEqual(fp._fund_display_type(self._h()), "--")


# ============================================================
#  _format_return
# ============================================================

class TestFormatReturn(unittest.TestCase):
    """测试 _format_return 收益率格式化。"""

    def test_none(self):
        """None -> '--'"""
        self.assertEqual(fp._format_return(None), "--")

    def test_dash_string(self):
        """'--' -> '--'"""
        self.assertEqual(fp._format_return("--"), "--")

    def test_positive_float(self):
        """正浮点数 -> '+X.XX%'"""
        self.assertEqual(fp._format_return(1.5), "+1.50%")

    def test_negative_float(self):
        """负浮点数 -> '-X.XX%'"""
        self.assertEqual(fp._format_return(-3.25), "-3.25%")

    def test_zero(self):
        """零 -> '+0.00%'"""
        self.assertEqual(fp._format_return(0), "+0.00%")

    def test_positive_string_number(self):
        """正数字符串 -> '+X.XX%'"""
        self.assertEqual(fp._format_return("2.5"), "+2.50%")

    def test_negative_string_number(self):
        """负数字符串 -> '-X.XX%'"""
        self.assertEqual(fp._format_return("-1.8"), "-1.80%")

    def test_rounding(self):
        """四舍五入：99.999 -> '+100.00%'"""
        self.assertEqual(fp._format_return(99.999), "+100.00%")

    def test_small_positive(self):
        """很小的正数 -> '+0.01%'"""
        self.assertEqual(fp._format_return(0.006), "+0.01%")

    def test_empty_string(self):
        """空字符串 -> '--'"""
        self.assertEqual(fp._format_return(""), "--")

    def test_invalid_string(self):
        """非数字字符串 -> '--'"""
        self.assertEqual(fp._format_return("abc"), "--")


# ============================================================
#  _format_rank
# ============================================================

class TestFormatRank(unittest.TestCase):
    """测试 _format_rank 排名格式化。"""

    def test_normal(self):
        """正常排名 -> 'rank/total'"""
        self.assertEqual(fp._format_rank({"rank": 1, "total": 100}),
                         "1/100")

    def test_rank_is_dash(self):
        """rank='--' -> '--'"""
        self.assertEqual(fp._format_rank({"rank": "--", "total": 100}),
                         "--")

    def test_total_is_dash(self):
        """total='--' -> '--'"""
        self.assertEqual(fp._format_rank({"rank": 1, "total": "--"}),
                         "--")

    def test_both_dash(self):
        """两者均为 '--' -> '--'"""
        self.assertEqual(fp._format_rank({"rank": "--", "total": "--"}),
                         "--")

    def test_empty_dict(self):
        """空字典 -> '--'（get 默认值）"""
        self.assertEqual(fp._format_rank({}), "--")

    def test_rank_zero(self):
        """rank=0 -> '0/total'"""
        self.assertEqual(fp._format_rank({"rank": 0, "total": 500}),
                         "0/500")

    def test_string_values(self):
        """字符串数字值 -> 'rank/total'"""
        self.assertEqual(fp._format_rank({"rank": "5", "total": "100"}),
                         "5/100")

    def test_large_numbers(self):
        """大数字 -> '1234/99999'"""
        self.assertEqual(fp._format_rank({"rank": 1234, "total": 99999}),
                         "1234/99999")


# ============================================================
#  _RATING_COMMENT
# ============================================================

class TestRatingComment(unittest.TestCase):
    """测试 _RATING_COMMENT 评级映射完整性。"""

    def test_all_expected_keys_present(self):
        """四个预期评级键均存在且有非空描述"""
        expected = ["优秀", "良好", "稳定", "偏差"]
        for k in expected:
            with self.subTest(key=k):
                self.assertIn(k, fp._RATING_COMMENT)
                self.assertTrue(fp._RATING_COMMENT[k])

    def test_description_prefix_matches_key(self):
        """每个评级的描述以键名开头"""
        for k, v in fp._RATING_COMMENT.items():
            with self.subTest(key=k):
                self.assertTrue(v.startswith(k),
                                f"'{v}' 不以 '{k}' 开头")


# ============================================================
#  write_fund_performance_sheet
# ============================================================

class TestWriteFundPerformanceSheet(unittest.TestCase):
    """测试 write_fund_performance_sheet 主流程（mock API + writer）。"""

    _PATCH_TARGETS = [
        "src.python.report.fund_performance.write_title_row",
        "src.python.report.fund_performance.write_header_row",
        "src.python.report.fund_performance.write_data_row",
        "src.python.report.fund_performance.freeze_header",
        "src.python.report.fund_performance.auto_width",
        "src.python.report.fund_performance.fetch_fund_rankings",
        "src.python.report.fund_performance.fetch_fund_benchmark",
        "src.python.report.fund_performance.classify_penetration",
    ]

    def setUp(self):
        self.ws = MagicMock()
        # ws.cell 必须通过 side_effect 返回独立 mock，否则 Python 3.13+ 中
        # _Call 不可 hash，所有 ws.cell() 返回同一对象，font 会相互覆盖
        _cell_cache: dict[tuple[int, int], MagicMock] = {}
        def _cell_side_effect(*, row: int, column: int) -> MagicMock:
            key = (row, column)
            if key not in _cell_cache:
                _cell_cache[key] = MagicMock()
            return _cell_cache[key]
        self.ws.cell.side_effect = _cell_side_effect

        self._patchers: dict[str, Any] = {}
        self.mocks: dict[str, Any] = {}
        for target in self._PATCH_TARGETS:
            p = patch(target)
            self._patchers[target] = p
            name = target.rsplit(".", 1)[-1]
            self.mocks[name] = p.start()

        self.mocks["write_title_row"].return_value = 2
        self.mocks["write_header_row"].return_value = 3

        # -- classify_penetration 侧效 --
        def _cls_side_effect(h: Holding) -> str:
            if h.code == "561910" or "ETF" in h.name.upper():
                return pene.ETF
            if h.code == "012325":
                return pene.BOND_FUND
            return pene.ACTIVE_EQUITY
        self.mocks["classify_penetration"].side_effect = _cls_side_effect

        # -- fetch_fund_rankings 侧效 --
        def _rankings_side_effect(code: str) -> dict | None:
            data = {
                "561910": {
                    "rankings": {
                        "近3月": {"return": 1.5},
                        "近6月": {"return": 3.2},
                        "近1年": {"return": 8.5},
                        "同类排名": {"rank": 50, "total": 500},
                    },
                    "rating": "优秀",
                },
                "012325": {
                    "rankings": {
                        "近3月": {"return": 0.8},
                        "近6月": {"return": 1.5},
                        "近1年": {"return": 3.0},
                        "同类排名": {"rank": 100, "total": 800},
                    },
                    "rating": "稳定",
                },
            }
            return data.get(code)  # None 表示获取失败
        self.mocks["fetch_fund_rankings"].side_effect = _rankings_side_effect

        # -- fetch_fund_benchmark 侧效 --
        def _benchmark_side_effect(code: str) -> str:
            return {"561910": "沪深300指数",
                    "012325": "中债综合指数"}.get(code, "--")
        self.mocks["fetch_fund_benchmark"].side_effect = _benchmark_side_effect

        # -- 公共测试数据 --
        self.holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000, 1.0),
            Holding("支付宝", "招商鑫福中短债A", "012325", 500, 1.0),
            Holding("证券账户", "长江电力", "600900", 200, 50.0),
        ]
        self.details = [
            _MockDetailRow("561910", profit=1000.0, profit_rate=0.05,
                           market_value=10000.0),
            _MockDetailRow("012325", profit=200.0, profit_rate=0.03,
                           market_value=5000.0),
            _MockDetailRow("600900", profit=500.0, profit_rate=0.10,
                           market_value=10000.0),
        ]

    def tearDown(self):
        for p in self._patchers.values():
            p.stop()

    # -- normal flow -------------------------------------------------

    def test_normal_flow(self):
        """正常流程：两只基金获取到业绩数据，正确写入行、标色、统计。"""
        fp.write_fund_performance_sheet(self.ws, self.holdings, self.details)

        # write_data_row 调用顺序：fund1 + fund2 + 统计行 + 评级分布 + 业绩评价标准说明
        calls = self.mocks["write_data_row"].call_args_list
        self.assertEqual(len(calls), 5)

        # --- Fund 1 (561910, 市值 10000 -> 排首位) ---
        vals0 = calls[0][0][2]
        self.assertEqual(vals0[0], "电池ETF")
        self.assertEqual(vals0[1], "561910")
        self.assertEqual(vals0[2], "场内ETF")
        self.assertEqual(vals0[3], "+1.50%")
        self.assertEqual(vals0[4], "+3.20%")
        self.assertEqual(vals0[5], "+8.50%")
        self.assertEqual(vals0[6], "+1,000.00")
        self.assertEqual(vals0[7], "+5.00%")
        self.assertEqual(vals0[8], "沪深300指数")
        self.assertEqual(vals0[9], "优秀 持续跑赢基准，超额收益显著（基准：沪深300指数）")
        self.assertEqual(vals0[10], "50/500")

        # --- Fund 2 (012325, 市值 5000 -> 排第二) ---
        vals1 = calls[1][0][2]
        self.assertEqual(vals1[0], "招商鑫福中短债A")
        self.assertEqual(vals1[1], "012325")
        self.assertEqual(vals1[2], "场外债券基金")
        self.assertEqual(vals1[3], "+0.80%")
        self.assertEqual(vals1[4], "+1.50%")
        self.assertEqual(vals1[5], "+3.00%")
        self.assertEqual(vals1[6], "+200.00")
        self.assertEqual(vals1[7], "+3.00%")
        self.assertEqual(vals1[8], "中债综合指数")
        self.assertEqual(vals1[9], "稳定 收益率稳健，波动控制良好（基准：中债综合指数）")
        self.assertEqual(vals1[10], "100/800")

        # --- 统计行 ---
        vals2 = calls[2][0][2]
        self.assertEqual(vals2[0],
                         "共 2 只基金，2 只获取到业绩数据")

        # --- 评级分布 ---
        vals3 = calls[3][0][2]
        self.assertIn("优秀: 1只", vals3[0])
        self.assertIn("稳定: 1只", vals3[0])

        # -- 单元格标色 --
        cell_3 = self.ws.cell(row=3, column=10)
        self.assertIs(cell_3.font, RED_FONT)   # 优秀 -> 红
        cell_4 = self.ws.cell(row=4, column=10)
        self.assertIs(cell_4.font, BLUE_FONT)  # 稳定 -> 蓝

        # -- 冻结 + 自动列宽 --
        self.mocks["freeze_header"].assert_called_once_with(self.ws, 2)
        self.mocks["auto_width"].assert_called_once_with(
            self.ws, min_width=10, max_width=30)

    # -- no funds ----------------------------------------------------

    def test_no_funds(self):
        """全部非基金持仓 -> 写入占位提示并提前返回。"""
        stocks = [
            Holding("证券账户", "长江电力", "600900", 200, 50.0),
            Holding("证券账户", "平安银行", "000001", 100, 10.0),
        ]
        fp.write_fund_performance_sheet(self.ws, stocks, [])

        self.mocks["write_title_row"].assert_called_once_with(
            self.ws, 1, "基金业绩分析", 12)
        self.mocks["write_header_row"].assert_called_once()

        # write_data_row 仅调用一次（占位行）
        self.mocks["write_data_row"].assert_called_once()
        args = self.mocks["write_data_row"].call_args[0]
        self.assertIn("未检测到基金持仓", args[2][0])

        # freeze + auto_width 仍被调用
        self.mocks["freeze_header"].assert_called_once_with(self.ws, 2)
        self.mocks["auto_width"].assert_called_once_with(self.ws)

        # fetch 不应被调用
        self.mocks["fetch_fund_rankings"].assert_not_called()
        self.mocks["fetch_fund_benchmark"].assert_not_called()

    # -- all fail ----------------------------------------------------

    def test_all_funds_fail(self):
        """所有基金 API 获取失败 -> 全部写占位行 + 统计正确。"""
        self.mocks["fetch_fund_rankings"].side_effect = lambda code: None

        fp.write_fund_performance_sheet(self.ws, self.holdings, self.details)

        calls = self.mocks["write_data_row"].call_args_list
        # 2 占位行 + 1 统计行 + 1 业绩评价标准说明行（perf_results 为空 -> 无评级分布）
        self.assertEqual(len(calls), 4)

        # 两只基金都是占位行
        for i in range(2):
            vals = calls[i][0][2]
            self.assertEqual(vals[3], "--")
            self.assertEqual(vals[4], "--")
            self.assertEqual(vals[5], "--")
            self.assertEqual(vals[6], "--")
            self.assertEqual(vals[7], "--")
            self.assertEqual(vals[8], "--")
            self.assertEqual(vals[9], "--")
            self.assertEqual(vals[10], "--")

        # 统计行
        summary_vals = calls[2][0][2]
        self.assertEqual(summary_vals[0],
                         "共 2 只基金，0 只获取到业绩数据")

        # benchmark 不应被调用（continue 跳过）
        self.mocks["fetch_fund_benchmark"].assert_not_called()

        # ws.cell 不应被调用（无成功基金）
        self.assertEqual(self.ws.cell.call_count, 0)

    # -- partial fail ------------------------------------------------

    def test_partial_fail(self):
        """部分基金获取失败 -> 成功行 + 占位行 + 统计 + 评级分布。"""
        # 只有 561910 成功
        self.mocks["fetch_fund_rankings"].side_effect = lambda code: (
            None if code == "012325" else {
                "561910": {
                    "rankings": {
                        "近3月": {"return": 1.5},
                        "近6月": {"return": 3.2},
                        "近1年": {"return": 8.5},
                        "同类排名": {"rank": 50, "total": 500},
                    },
                    "rating": "优秀",
                },
            }.get(code)
        )

        # 额外细节：002325 的 detail 实际上不会被用到（占位行）
        fp.write_fund_performance_sheet(self.ws, self.holdings, self.details)

        calls = self.mocks["write_data_row"].call_args_list
        # 1 成功 + 1 占位 + 1 统计 + 1 评级分布 + 1 业绩评价标准说明
        self.assertEqual(len(calls), 5)

        # 成功行
        vals0 = calls[0][0][2]
        self.assertEqual(vals0[1], "561910")
        self.assertEqual(vals0[9], "优秀 持续跑赢基准，超额收益显著（基准：沪深300指数）")
        self.assertEqual(vals0[10], "50/500")

        # 占位行
        vals1 = calls[1][0][2]
        self.assertEqual(vals1[1], "012325")
        self.assertEqual(vals1[3], "--")
        self.assertEqual(vals1[9], "--")

        # 统计
        self.assertIn("1 只获取到业绩数据", calls[2][0][2][0])

        # 评级分布（只有优秀）
        self.assertIn("优秀: 1只", calls[3][0][2][0])

        # 仅成功的那只标色
        cell_3 = self.ws.cell(row=3, column=10)
        self.assertIs(cell_3.font, RED_FONT)

    # -- empty details -----------------------------------------------

    def test_empty_details(self):
        """details 为空 -> 盈亏字段按 0 处理，不报错。"""
        fp.write_fund_performance_sheet(self.ws, self.holdings, [])

        calls = self.mocks["write_data_row"].call_args_list
        self.assertEqual(len(calls), 5)  # 2 基金 + 统计 + 评级分布 + 业绩评价标准说明

        # 利润字段为 0
        vals0 = calls[0][0][2]
        self.assertEqual(vals0[6], "+0.00")
        self.assertEqual(vals0[7], "+0.00%")

        vals1 = calls[1][0][2]
        self.assertEqual(vals1[6], "+0.00")
        self.assertEqual(vals1[7], "+0.00%")

    # -- all ratings (color test) ------------------------------------

    def test_rating_colors(self):
        """各种评级对应正确的单元格字体颜色。"""
        def _rankings_all_ratings(code: str) -> dict | None:
            data = {
                "561910": {
                    "rankings": {"近3月": {"return": 1.0},
                                 "近6月": {"return": 2.0},
                                 "近1年": {"return": 3.0},
                                 "同类排名": {"rank": 1, "total": 100}},
                    "rating": "优秀",
                },
                "012325": {
                    "rankings": {"近3月": {"return": 0.5},
                                 "近6月": {"return": 1.0},
                                 "近1年": {"return": 1.5},
                                 "同类排名": {"rank": 50, "total": 100}},
                    "rating": "稳定",
                },
            }
            return data.get(code)

        self.mocks["fetch_fund_rankings"].side_effect = _rankings_all_ratings

        # 添加第三只基金仅用于测试 "偏差" 评级
        holdings = self.holdings + [
            Holding("微信", "易方达蓝筹精选", "005827", 300, 2.0),
        ]
        details = self.details + [
            _MockDetailRow("005827", profit=-100.0, profit_rate=-0.02,
                           market_value=3000.0),
        ]

        def _cls_side_effect_3(h: Holding) -> str:
            if h.code == "561910" or "ETF" in h.name.upper():
                return pene.ETF
            if h.code == "012325":
                return pene.BOND_FUND
            return pene.ACTIVE_EQUITY
        self.mocks["classify_penetration"].side_effect = _cls_side_effect_3

        def _rankings_3(code: str) -> dict | None:
            data = {
                "561910": {
                    "rankings": {"近3月": {"return": 1.0},
                                 "近6月": {"return": 2.0},
                                 "近1年": {"return": 3.0},
                                 "同类排名": {"rank": 1, "total": 100}},
                    "rating": "优秀",
                },
                "012325": {
                    "rankings": {"近3月": {"return": 0.5},
                                 "近6月": {"return": 1.0},
                                 "近1年": {"return": 1.5},
                                 "同类排名": {"rank": 50, "total": 100}},
                    "rating": "稳定",
                },
                "005827": {
                    "rankings": {"近3月": {"return": -2.0},
                                 "近6月": {"return": -5.0},
                                 "近1年": {"return": -8.0},
                                 "同类排名": {"rank": 90, "total": 100}},
                    "rating": "偏差",
                },
            }
            return data.get(code)
        self.mocks["fetch_fund_rankings"].side_effect = _rankings_3

        fp.write_fund_performance_sheet(self.ws, holdings, details)

        # 排序：561910(10000) > 012325(5000) > 005827(3000)
        # row 3: 561910 -> 优秀 -> RED_FONT
        # row 4: 012325 -> 稳定 -> BLUE_FONT
        # row 5: 005827 -> 偏差 -> GREEN_FONT
        self.assertIs(self.ws.cell(row=3, column=10).font, RED_FONT)
        self.assertIs(self.ws.cell(row=4, column=10).font, BLUE_FONT)
        self.assertIs(self.ws.cell(row=5, column=10).font, GREEN_FONT)

    # -- rating distribution with diverse ratings --------------------

    def test_rating_distribution(self):
        """多基金不同评级 -> 评级分布汇总行正确。"""
        # 3 只基金，评级分别为 优秀 x2, 偏差 x1
        def _rankings_dist(code: str) -> dict | None:
            data = {
                "561910": {
                    "rankings": {"近3月": {"return": 1.0},
                                 "近6月": {"return": 2.0},
                                 "近1年": {"return": 3.0},
                                 "同类排名": {"rank": 1, "total": 100}},
                    "rating": "优秀",
                },
                "012325": {
                    "rankings": {"近3月": {"return": 0.5},
                                 "近6月": {"return": 1.0},
                                 "近1年": {"return": 1.5},
                                 "同类排名": {"rank": 50, "total": 100}},
                    "rating": "优秀",
                },
                "005827": {
                    "rankings": {"近3月": {"return": -2.0},
                                 "近6月": {"return": -5.0},
                                 "近1年": {"return": -8.0},
                                 "同类排名": {"rank": 90, "total": 100}},
                    "rating": "偏差",
                },
            }
            return data.get(code)
        self.mocks["fetch_fund_rankings"].side_effect = _rankings_dist

        holdings = self.holdings + [
            Holding("微信", "易方达蓝筹精选", "005827", 300, 2.0),
        ]
        details = self.details + [
            _MockDetailRow("005827", profit=-100.0, profit_rate=-0.02,
                           market_value=3000.0),
        ]

        def _cls_dist(h: Holding) -> str:
            if h.code == "561910" or "ETF" in h.name.upper():
                return pene.ETF
            if h.code == "012325":
                return pene.BOND_FUND
            return pene.ACTIVE_EQUITY
        self.mocks["classify_penetration"].side_effect = _cls_dist

        fp.write_fund_performance_sheet(self.ws, holdings, details)

        calls = self.mocks["write_data_row"].call_args_list
        # 3 基金 + 1 统计 + 1 评级分布 + 1 业绩评价标准说明 = 6
        self.assertEqual(len(calls), 6)

        rating_row = calls[4][0][2][0]
        self.assertIn("评级分布:", rating_row)
        self.assertIn("优秀: 2只", rating_row)
        self.assertIn("偏差: 1只", rating_row)

        # 评级按 _RATING_COMMENT 顺序：优秀 -> 良好 -> 稳定 -> 偏差
        # 应出现 优秀 在 偏差 之前
        self.assertLess(rating_row.index("优秀"), rating_row.index("偏差"))

    # -- perf_evaluation JSON null safety --------------------------------

    def test_perf_eval_null_categories(self):
        """perf_evaluation.categories 为 JSON null → 不崩溃，正确兜底。"""
        def _rankings_null_cat(code: str) -> dict | None:
            return {
                "561910": {
                    "rankings": {"近3月": {"return": 1.5},
                                 "近6月": {"return": 3.2},
                                 "近1年": {"return": 8.5},
                                 "同类排名": {"rank": 50, "total": 500}},
                    "rating": "优秀",
                    "perf_evaluation": {"categories": None, "data": None},
                },
                "012325": {
                    "rankings": {"近3月": {"return": 0.8},
                                 "近6月": {"return": 1.5},
                                 "近1年": {"return": 3.0},
                                 "同类排名": {"rank": 100, "total": 800}},
                    "rating": "稳定",
                    "perf_evaluation": {"categories": None, "data": None},
                },
            }.get(code)
        self.mocks["fetch_fund_rankings"].side_effect = _rankings_null_cat

        fp.write_fund_performance_sheet(self.ws, self.holdings, self.details)

        calls = self.mocks["write_data_row"].call_args_list
        # 2 基金 + 统计 + 评级分布 + 业绩评价标准说明 = 5
        self.assertEqual(len(calls), 5)

        # 正常写入，评级未降级（无超额收益数据）
        vals0 = calls[0][0][2]
        self.assertEqual(vals0[9], "优秀 持续跑赢基准，超额收益显著（基准：沪深300指数）")

        vals1 = calls[1][0][2]
        self.assertEqual(vals1[9], "稳定 收益率稳健，波动控制良好（基准：中债综合指数）")

    def test_perf_eval_null_data(self):
        """perf_evaluation.data 为 JSON null，categories 正常 → 不崩溃。"""
        def _rankings_null_data(code: str) -> dict | None:
            return {
                "561910": {
                    "rankings": {"近3月": {"return": 1.5},
                                 "近6月": {"return": 3.2},
                                 "近1年": {"return": 8.5},
                                 "同类排名": {"rank": 50, "total": 500}},
                    "rating": "优秀",
                    "perf_evaluation": {"categories": ["超额收益", "选股能力"], "data": None},
                },
            }.get(code)
        self.mocks["fetch_fund_rankings"].side_effect = _rankings_null_data

        fp.write_fund_performance_sheet(self.ws, [self.holdings[0]], [self.details[0]])

        calls = self.mocks["write_data_row"].call_args_list
        # 1 基金 + 统计 + 评级分布 + 业绩评价标准说明 = 4
        self.assertEqual(len(calls), 4)

        # categories 正常但 data 为 None，len(scores) 应兜底为 0
        vals0 = calls[0][0][2]
        self.assertIn("基准：沪深300指数", vals0[9])



# ============================================================
#  R-098: 基金排名数据合理性
# ============================================================

@pytest.mark.data
class TestFormatReturnBoundary(unittest.TestCase):
    """_format_return 边界值和合理性验证。"""

    def _call(self, val):
        return fp._format_return(val)

    def test_normal_positive(self):
        """正收益率 → +X.XX% 格式。"""
        self.assertEqual(self._call(5.5), "+5.50%")

    def test_normal_negative(self):
        """负收益率 → -X.XX% 格式。"""
        self.assertEqual(self._call(-3.2), "-3.20%")

    def test_zero(self):
        """零收益率 → +0.00%。"""
        self.assertEqual(self._call(0), "+0.00%")

    def test_extreme_large(self):
        """极大值(+9999%) → 不崩溃。"""
        result = self._call(9999.99)
        self.assertTrue(result.endswith("%"))

    def test_extreme_small(self):
        """极小值(-99.99%) → 不崩溃。"""
        result = self._call(-99.99)
        self.assertTrue(result.endswith("%"))
        self.assertTrue(result.startswith("-"))

    def test_none(self):
        """None → '--'。"""
        self.assertEqual(self._call(None), "--")

    def test_invalid_string(self):
        """无效字符串 → '--'。"""
        self.assertEqual(self._call("N/A"), "--")


@pytest.mark.data
class TestFormatRankSanity(unittest.TestCase):
    """_format_rank 合理性验证。"""

    def _call(self, entry):
        return fp._format_rank(entry)

    def test_normal_rank(self):
        """正常排名 → '排名/总数'。"""
        self.assertEqual(self._call({"rank": 50, "total": 2000}), "50/2000")

    def test_top_rank(self):
        """第1名。"""
        self.assertEqual(self._call({"rank": 1, "total": 500}), "1/500")

    def test_last_rank(self):
        """最后一名。"""
        self.assertEqual(self._call({"rank": 500, "total": 500}), "500/500")

    def test_rank_not_exceed_total(self):
        """排名不超过总数。"""
        entry = {"rank": 500, "total": 500}
        rank, total = entry["rank"], entry["total"]
        self.assertLessEqual(rank, total)

    def test_rank_positive(self):
        """排名为正数。"""
        entry = {"rank": 1, "total": 500}
        self.assertGreaterEqual(entry["rank"], 1)

    def test_missing_rank(self):
        """缺失排名 → '--'。"""
        self.assertEqual(self._call({}), "--")

    def test_missing_total(self):
        """缺失总数 → '--'。"""
        self.assertEqual(self._call({"rank": 1}), "--")

    def test_none_rank(self):
        """rank=None → '--'。"""
        self.assertEqual(self._call({"rank": None, "total": 500}), "--")


@pytest.mark.data
class TestRankDataReasonableRange(unittest.TestCase):
    """R-098: 排名和收益率在合理范围内（通过 write_fund_performance_sheet 集成测试）。"""

    def setUp(self):
        self.ws = MagicMock()
        _cell_cache: dict = {}
        def _cell_side_effect(*, row: int, column: int) -> MagicMock:
            key = (row, column)
            if key not in _cell_cache:
                _cell_cache[key] = MagicMock()
            return _cell_cache[key]
        self.ws.cell.side_effect = _cell_side_effect

    @patch("src.python.report.fund_performance.fetch_fund_rankings")
    @patch("src.python.report.fund_performance.fetch_fund_benchmark",
           return_value="沪深300指数")
    @patch("src.python.report.fund_performance.classify_penetration",
           return_value=pene.ACTIVE_EQUITY)
    def test_yield_rate_in_reasonable_range(self, mock_pene, mock_bm, mock_rank):
        """收益率极端值应通过 _format_return 格式化为正确字符串。"""
        mock_rank.return_value = {
            "rankings": {
                "近3月": {"return": 9999.99},      # 极端大
                "近6月": {"return": -99.99},        # 极端小负
                "近1年": {"return": 50.0},           # 正常
                "同类排名": {"rank": 100, "total": 500},
            },
            "rating": "优秀",
        }
        holdings = [Holding("支付宝", "易方达蓝筹混合", "005827", 100, 2.0)]
        details = [_MockDetailRow("005827", profit=1000.0, profit_rate=0.05,
                                  market_value=10000.0)]
        with patch("src.python.report.fund_performance.write_data_row") as mock_wdr:
            with patch("src.python.report.fund_performance.write_title_row",
                       return_value=2):
                with patch("src.python.report.fund_performance.write_header_row",
                           return_value=3):
                    with patch("src.python.report.fund_performance.freeze_header"):
                        with patch("src.python.report.fund_performance.auto_width"):
                            fp.write_fund_performance_sheet(
                                self.ws, holdings, details)

            calls = mock_wdr.call_args_list
            fund_row = calls[0][0][2]
            # 格式化结果应为 +符号 + 保留两位小数 + % 后缀
            self.assertEqual(fund_row[3], "+9999.99%")
            self.assertEqual(fund_row[4], "-99.99%")
            self.assertEqual(fund_row[5], "+50.00%")

    @patch("src.python.report.fund_performance.fetch_fund_rankings")
    @patch("src.python.report.fund_performance.fetch_fund_benchmark",
           return_value="沪深300指数")
    @patch("src.python.report.fund_performance.classify_penetration",
           return_value=pene.ACTIVE_EQUITY)
    def test_rank_not_exceed_total_all(self, mock_pene, mock_bm, mock_rank):
        """排名数据中 rank ≤ total → _format_rank 输出正确格式。"""
        mock_rank.return_value = {
            "rankings": {
                "近3月": {"return": 5.0},
                "近6月": {"return": 3.0},
                "近1年": {"return": 1.0},
                "同类排名": {"rank": 500, "total": 500},  # 边界值
            },
            "rating": "优秀",
        }
        holdings = [Holding("支付宝", "易方达蓝筹混合", "005827", 100, 2.0)]
        details = [_MockDetailRow("005827", profit=1000.0, profit_rate=0.05,
                                  market_value=10000.0)]
        with patch("src.python.report.fund_performance.write_data_row") as mock_wdr:
            with patch("src.python.report.fund_performance.write_title_row",
                       return_value=2):
                with patch("src.python.report.fund_performance.write_header_row",
                           return_value=3):
                    with patch("src.python.report.fund_performance.freeze_header"):
                        with patch("src.python.report.fund_performance.auto_width"):
                            fp.write_fund_performance_sheet(
                                self.ws, holdings, details)

            calls = mock_wdr.call_args_list
            fund_row = calls[0][0][2]
            # 同类排名在第11列（索引10）
            rank_str = fund_row[10]
            self.assertEqual(rank_str, "500/500")


# ============================================================
#  Entry
# ============================================================

if __name__ == "__main__":
    unittest.main()
