"""汇总模块单元测试。

测试目标：
  - _write_section — 章节标题合并+样式
  - _write_kv_row / _write_kv_row_colored — 指标行写入
  - _write_blanks — 空行写入
  - write_summary_sheet — 基本信息/持仓概况/盈亏汇总/市场指数各章节渲染
  - 条件分支：空分类、未更新、零成本、指数缺失
  - profit_font 着色逻辑

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_summary -v
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, call, patch

from src.report import summary as s


# ═══════════════════════════════════════════════════════════
#  辅助函数测试
# ═══════════════════════════════════════════════════════════


class TestWriteSection(unittest.TestCase):
    """测试 _write_section 章节标题渲染。"""

    def setUp(self):
        self.ws = MagicMock()
        self.cell = MagicMock()
        self.ws.cell.return_value = self.cell

    def test_write_section_merge_and_return(self):
        """章节标题写入：合并 8 列并返回下一行号。"""
        row = s._write_section(self.ws, 3, "【持仓概况】")
        self.assertEqual(row, 4)
        self.ws.merge_cells.assert_called_once_with(
            start_row=3, start_column=1, end_row=3, end_column=8,
        )

    def test_write_section_styles(self):
        """章节标题写入：深蓝粗体、居中对齐。"""
        s._write_section(self.ws, 5, "【盈亏汇总】")
        # cell.font 被赋值为 _SECTION_FONT
        self.assertIsNotNone(self.cell.font)
        # 居中
        self.assertEqual(self.cell.alignment.horizontal, "center")
        self.assertEqual(self.cell.alignment.vertical, "center")

    def test_write_section_label_value(self):
        """章节标题文本正确设置。"""
        s._write_section(self.ws, 7, "【市场指数】")
        self.ws.cell.assert_called_with(row=7, column=1, value="【市场指数】")


class TestWriteKvRow(unittest.TestCase):
    """测试 _write_kv_row / _write_kv_row_colored。"""

    def setUp(self):
        self.ws = MagicMock()

    @patch("src.report.summary.write_data_row")
    def test_write_kv_row(self, mock_data):
        """_write_kv_row：写入 key/value 并返回下一行号。"""
        row = s._write_kv_row(self.ws, 3, "持仓总数", 7)
        self.assertEqual(row, 4)
        mock_data.assert_called_once_with(self.ws, 3, ["持仓总数", 7])

    @patch("src.report.summary.write_data_row")
    def test_write_kv_row_colored(self, mock_data):
        """_write_kv_row_colored：写入 key/value 并应用字体到两列。"""
        from openpyxl.styles import Font
        red_font = Font(color="CC0000")

        row = s._write_kv_row_colored(self.ws, 5, "价格更新状态",
                                        "3/5 (尚有缺失)", red_font)
        self.assertEqual(row, 6)
        mock_data.assert_called_once_with(
            self.ws, 5, ["价格更新状态", "3/5 (尚有缺失)"])

        # 两列单元格都调用了 ws.cell
        calls = self.ws.cell.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], call(row=5, column=1))
        self.assertEqual(calls[1], call(row=5, column=2))

        # 字体被设到 cell 上
        self.assertIs(self.ws.cell.return_value.font, red_font)

    @patch("src.report.summary.write_data_row")
    def test_write_kv_row_colored_blue(self, mock_data):
        """_write_kv_row_colored：蓝色字体正常应用。"""
        from openpyxl.styles import Font
        blue_font = Font(color="2E75B6")

        s._write_kv_row_colored(self.ws, 8, "状态", "全部已更新", blue_font)

        self.assertIs(self.ws.cell.return_value.font, blue_font)


class TestWriteBlanks(unittest.TestCase):
    """测试 _write_blanks。"""

    def setUp(self):
        self.ws = MagicMock()

    def test_write_blanks_default(self):
        """默认写入 1 行空白。"""
        row = s._write_blanks(self.ws, 10)
        self.assertEqual(row, 11)

    def test_write_blanks_multiple(self):
        """写入 3 行空白。"""
        row = s._write_blanks(self.ws, 10, 3)
        self.assertEqual(row, 13)

    def test_write_blanks_zero(self):
        """写入 0 行空白（行号不变）。"""
        row = s._write_blanks(self.ws, 10, 0)
        self.assertEqual(row, 10)


# ═══════════════════════════════════════════════════════════
#  write_summary_sheet 主函数测试
# ═══════════════════════════════════════════════════════════


class TestWriteSummarySheet(unittest.TestCase):
    """测试 write_summary_sheet 各章节渲染和条件分支。

    全部 mock 外部依赖（excel_writer、get_last_trading_day、profit_font、datetime）。
    """

    # ── 辅助方法 ──────────────────────────────────────────

    def _call_summary_sheet(
        self, ws,
        total_mv, total_cost, total_profit, today_profit,
        categories=None, update_status=None,
        a_indices=None, us_indices=None,
    ):
        """调用 write_summary_sheet 并返回 mock 字典。

        使用 ExitStack 统一管理所有 patch 的生命周期。
        """
        with ExitStack() as stack:
            mock_title = stack.enter_context(
                patch("src.report.summary.write_title_row", return_value=3))
            mock_header = stack.enter_context(
                patch("src.report.summary.write_header_row", return_value=4))
            mock_data = stack.enter_context(
                patch("src.report.summary.write_data_row"))
            mock_freeze = stack.enter_context(
                patch("src.report.summary.freeze_header"))
            mock_auto = stack.enter_context(
                patch("src.report.summary.auto_width"))
            mock_day = stack.enter_context(
                patch("src.report.summary.get_last_trading_day",
                       return_value="2026-06-26"))
            mock_dt = stack.enter_context(
                patch("src.report.summary.datetime"))
            mock_pfont = stack.enter_context(
                patch("src.report.summary.profit_font"))

            # 固定 datetime.now() 输出
            mock_now = MagicMock()
            mock_now.strftime.side_effect = [
                "2026-06-27",           # today_str
                "2026-06-27 15:30:00",  # 统计时间
            ]
            mock_dt.now.return_value = mock_now

            s.write_summary_sheet(
                ws, total_mv, total_cost, total_profit, today_profit,
                categories=categories, update_status=update_status,
                a_indices=a_indices, us_indices=us_indices,
            )

            return {
                "ws": ws,
                "mock_title": mock_title,
                "mock_header": mock_header,
                "mock_data": mock_data,
                "mock_freeze": mock_freeze,
                "mock_auto": mock_auto,
                "mock_day": mock_day,
                "mock_dt": mock_dt,
                "mock_profit_font": mock_pfont,
            }

    def _data_pairs(self, mock_data):
        """从 write_data_row 的调用中提取 (key, value) 列表（保持顺序）。"""
        return [call_[0][2] for call_ in mock_data.call_args_list]

    def _find_section(self, pairs, header_key):
        """在 pairs 列表中搜索章节首行索引。"""
        for i, (key, _) in enumerate(pairs):
            if key == header_key:
                return i
        return -1

    def _assert_pairs_contain(self, pairs, key, value):
        """断言 pairs 中存在指定的 (key, value)。"""
        for k, v in pairs:
            if k == key and v == value:
                return
        self.fail(f"pair ({key!r}, {value!r}) not found in data pairs")

    def setUp(self):
        self.ws = MagicMock()
        self.ws.title = ""
        self.cell = MagicMock()
        self.ws.cell.return_value = self.cell

        # ── 标准测试数据 ──
        self.mv = 150000.0
        self.cost = 120000.0
        self.profit = 30000.0
        self.today = 5000.0
        # profit_rate = 30000/120000*100 = 25.00%
        # denominator = 120000+30000-5000 = 145000
        # today_rate = 5000/145000*100 ≈ 3.45%

        self.categories = {
            "场内股票": ["s1", "s2"],              # 2
            "场内ETF": ["e1", "e2", "e3"],          # 3
            "国内场外": ["f1"],                      # 1
            "QDII": ["q1"],                          # 1
        }  # 合计 7

        self.update_done = (5, 5, True)
        self.update_partial = (3, 5, False)
        self.update_empty = (0, 0, True)

        self.a_indices = {
            "sh000001": {"name": "上证指数", "price": 3200.50,
                          "yesterday_close": 3180.00, "change_pct": 0.64},
            "sz399001": {"name": "深证成指", "price": 10500.00,
                          "yesterday_close": 10450.00, "change_pct": 0.48},
            "sh000300": {"name": "沪深300", "price": 4200.00,
                          "yesterday_close": 4180.00, "change_pct": 0.48},
            "sh000688": {"name": "科创板50", "price": 950.00,
                          "yesterday_close": 940.00, "change_pct": 1.06},
            "sz399006": {"name": "创业板指", "price": 2100.00,
                          "yesterday_close": 2080.00, "change_pct": 0.96},
        }

        self.us_indices = {
            "gb_dji": {"name": "道琼斯", "price": 38000.00,
                        "yesterday_close": 37900.00, "change_pct": 0.26},
            "gb_ixic": {"name": "纳斯达克", "price": 16500.00,
                         "yesterday_close": 16400.00, "change_pct": 0.61},
            "gb_inx": {"name": "标普500", "price": 5100.00,
                        "yesterday_close": 5080.00, "change_pct": 0.39},
        }

    # ════════════════════════════════════════════════════════
    #  基本信息
    # ════════════════════════════════════════════════════════

    def test_basic_info_rows(self):
        """基本信息：统计时间 + 所属交易日写入。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        self.assertEqual(pairs[0], ["统计时间", "2026-06-27 15:30:00"])
        self.assertEqual(pairs[1], ["所属交易日", "2026-06-26"])

    def test_title_and_header(self):
        """标题行 + 表头行被调用。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
        )
        mocks["mock_title"].assert_called_once_with(self.ws, 1, "投资分析汇总", 8)
        mocks["mock_header"].assert_called_once_with(self.ws, 3, ["指标", "数值"])

    # ════════════════════════════════════════════════════════
    #  持仓概况
    # ════════════════════════════════════════════════════════

    def test_categories_written(self):
        """各类别 + 持仓总数正确渲染。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        self._assert_pairs_contain(pairs, "  场内股票", 2)
        self._assert_pairs_contain(pairs, "  场内ETF", 3)
        self._assert_pairs_contain(pairs, "  国内场外", 1)
        self._assert_pairs_contain(pairs, "  QDII", 1)
        self._assert_pairs_contain(pairs, "持仓总数", 7)

    def test_categories_none(self):
        """categories=None -> 持仓总数显示 --。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=None,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        self._assert_pairs_contain(pairs, "持仓总数", "--")

    def test_categories_empty_dict(self):
        """categories={} -> 空字典为 falsy，走 else 分支显示 --。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories={},
        )
        pairs = self._data_pairs(mocks["mock_data"])
        # Python 中 {} 为 falsy，不进入分类循环
        self._assert_pairs_contain(pairs, "持仓总数", "--")

    def test_categories_partial(self):
        """部分分类无数据：仅有场内股票和 QDII。"""
        partial = {"场内股票": ["s1"], "QDII": ["q1", "q2"]}
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=partial,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        self._assert_pairs_contain(pairs, "  场内股票", 1)
        self._assert_pairs_contain(pairs, "  场内ETF", 0)
        self._assert_pairs_contain(pairs, "  国内场外", 0)
        self._assert_pairs_contain(pairs, "  QDII", 2)
        self._assert_pairs_contain(pairs, "持仓总数", 3)

    # ════════════════════════════════════════════════════════
    #  价格更新状态
    # ════════════════════════════════════════════════════════

    def test_update_status_done(self):
        """全部更新（5/5 True）-> 蓝字 + '全部已更新'。"""
        self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            update_status=self.update_done,
        )
        self._assert_pairs_contain(
            self._data_pairs(self._call_summary_sheet(
                self.ws, self.mv, self.cost, self.profit, self.today,
                categories=self.categories,
                update_status=self.update_done,
            )["mock_data"]),
            "价格更新状态", "5/5  (全部已更新)",
        )

    def test_update_status_partial(self):
        """部分更新（3/5 False）-> 红字 + '尚有缺失'。"""
        self._assert_pairs_contain(
            self._data_pairs(self._call_summary_sheet(
                self.ws, self.mv, self.cost, self.profit, self.today,
                categories=self.categories,
                update_status=self.update_partial,
            )["mock_data"]),
            "价格更新状态", "3/5  (尚有缺失)",
        )

    def test_update_status_zero_total(self):
        """总数为 0 -> 显示 --。"""
        self._assert_pairs_contain(
            self._data_pairs(self._call_summary_sheet(
                self.ws, self.mv, self.cost, self.profit, self.today,
                categories=self.categories,
                update_status=self.update_empty,
            )["mock_data"]),
            "价格更新状态", "--",
        )

    def test_update_status_none(self):
        """update_status=None -> 显示 --。"""
        self._assert_pairs_contain(
            self._data_pairs(self._call_summary_sheet(
                self.ws, self.mv, self.cost, self.profit, self.today,
                categories=self.categories,
                update_status=None,
            )["mock_data"]),
            "价格更新状态", "--",
        )

    # ════════════════════════════════════════════════════════
    #  盈亏汇总
    # ════════════════════════════════════════════════════════

    def test_profit_summary_values(self):
        """盈亏汇总 6 行数据计算正确。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
        )
        pairs = self._data_pairs(mocks["mock_data"])

        self._assert_pairs_contain(pairs, "总市值 (元)", 150000.0)
        self._assert_pairs_contain(pairs, "总成本 (元)", 120000.0)
        self._assert_pairs_contain(pairs, "总盈亏 (元)", 30000.0)
        self._assert_pairs_contain(pairs, "总收益率", "+25.00%")
        self._assert_pairs_contain(pairs, "本日盈亏 (元)", 5000.0)
        self._assert_pairs_contain(pairs, "本日收益率", "+3.45%")

    def test_profit_font_called_for_profit_value(self):
        """总盈亏 >0 时 profit_font 被调用。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
        )
        mocks["mock_profit_font"].assert_any_call(30000.0)
        mocks["mock_profit_font"].assert_any_call(5000.0)

    def test_profit_font_negative(self):
        """总盈亏 <0 时 profit_font 被调用并传入负值。"""
        mocks = self._call_summary_sheet(
            self.ws, 80000.0, 100000.0, -20000.0, -3000.0,
            categories=self.categories,
        )
        mocks["mock_profit_font"].assert_any_call(-20000.0)
        mocks["mock_profit_font"].assert_any_call(-3000.0)

    def test_profit_font_rate_positive(self):
        """收益率正数时 profit_font 传入格式化后解析的浮点数（经 2 位小数舍入）。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
        )
        # 总收益率 25.00% -> profit_font(25.0)
        mocks["mock_profit_font"].assert_any_call(25.0)
        # 本日收益率原始值 ~3.4483%，经 :+.2f 格式化为 +3.45%，
        # 再解析回 3.45
        mocks["mock_profit_font"].assert_any_call(3.45)

    def test_profit_font_rate_negative(self):
        """收益率负值时 profit_font 传入经 2 位小数舍入后的值。"""
        mocks = self._call_summary_sheet(
            self.ws, 90000.0, 100000.0, -10000.0, -2000.0,
            categories=self.categories,
        )
        # profit_rate = -10.00% -> profit_font(-10.0)
        mocks["mock_profit_font"].assert_any_call(-10.0)
        # today_rate 原始值 ~-2.1739%，格式化为 -2.17%，再解析为 -2.17
        mocks["mock_profit_font"].assert_any_call(-2.17)

    def test_zero_cost_edge_case(self):
        """总成本为 0 时 profit_rate = 0.0，不除零。"""
        mocks = self._call_summary_sheet(
            self.ws, 10000.0, 0.0, 10000.0, 500.0,
            categories=self.categories,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        # total_cost=0 -> profit_rate=0.0
        self._assert_pairs_contain(pairs, "总收益率", "+0.00%")
        # denominator = 0 + 10000 - 500 = 9500
        # today_rate = 500/9500*100 ≈ 5.26%
        self._assert_pairs_contain(pairs, "本日收益率", "+5.26%")

    # ════════════════════════════════════════════════════════
    #  市场指数 — A 股
    # ════════════════════════════════════════════════════════

    def test_a_indices_today_values(self):
        """A 股指数本日行情写入（含涨跌幅符号）。

        因本日和上日使用相同的 key，通过位置索引区分。
        """
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=self.a_indices,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        start = self._find_section(pairs, "── A股指数（本日）──")
        self.assertGreaterEqual(start, 0)

        self.assertEqual(pairs[start + 1], ["  上证指数", "3200.50  (+0.64%)"])
        self.assertEqual(pairs[start + 2], ["  深证成指", "10500.00  (+0.48%)"])
        self.assertEqual(pairs[start + 3], ["  沪深300", "4200.00  (+0.48%)"])
        self.assertEqual(pairs[start + 4], ["  科创板50", "950.00  (+1.06%)"])
        self.assertEqual(pairs[start + 5], ["  创业板指", "2100.00  (+0.96%)"])

    def test_a_indices_yesterday_values(self):
        """A 股指数上日收盘写入。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=self.a_indices,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        start = self._find_section(pairs, "── A股指数（上日）──")
        self.assertGreaterEqual(start, 0)

        self.assertEqual(pairs[start + 1], ["  上证指数", "3180.00"])
        self.assertEqual(pairs[start + 2], ["  深证成指", "10450.00"])
        self.assertEqual(pairs[start + 3], ["  沪深300", "4180.00"])
        self.assertEqual(pairs[start + 4], ["  科创板50", "940.00"])
        self.assertEqual(pairs[start + 5], ["  创业板指", "2080.00"])

    def test_a_indices_negative_change(self):
        """A 股指数负涨跌幅正确显示符号。"""
        a_down = {
            "sh000001": {"name": "上证指数", "price": 3100.00,
                          "yesterday_close": 3200.00, "change_pct": -3.12},
            "sz399001": {"name": "深证成指", "price": 10000.00,
                          "yesterday_close": 10500.00, "change_pct": -4.76},
        }
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=a_down,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        start = self._find_section(pairs, "── A股指数（本日）──")
        self.assertGreaterEqual(start, 0)

        self.assertIn("(-3.12%)", pairs[start + 1][1])
        self.assertIn("(-4.76%)", pairs[start + 2][1])

    def test_a_indices_missing_code(self):
        """A 股缺失某个代码 -> 显示 --。"""
        partial = {
            "sh000001": {"name": "上证指数", "price": 3200.50,
                          "yesterday_close": 3180.00, "change_pct": 0.64},
            "sh000300": {"name": "沪深300", "price": 4200.00,
                          "yesterday_close": 4180.00, "change_pct": 0.48},
        }
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=partial,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        start = self._find_section(pairs, "── A股指数（本日）──")
        self.assertGreaterEqual(start, 0)

        self.assertEqual(pairs[start + 1], ["  上证指数", "3200.50  (+0.64%)"])
        self.assertEqual(pairs[start + 2], ["  深证成指", "--"])
        self.assertEqual(pairs[start + 3], ["  沪深300", "4200.00  (+0.48%)"])
        self.assertEqual(pairs[start + 4], ["  科创板50", "--"])
        self.assertEqual(pairs[start + 5], ["  创业板指", "--"])

    def test_a_indices_zero_price(self):
        """A 股价格 <=0 视为无效 -> 本日显示 --，上日仍有值。"""
        zero_price = {
            "sh000001": {"name": "上证指数", "price": 0,
                          "yesterday_close": 3200.00, "change_pct": 0},
        }
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=zero_price,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        # 本日：price=0 -> --
        start_today = self._find_section(pairs, "── A股指数（本日）──")
        self.assertGreaterEqual(start_today, 0)
        self.assertEqual(pairs[start_today + 1], ["  上证指数", "--"])

        # 上日：yesterday_close=3200 -> 正常显示
        start_yest = self._find_section(pairs, "── A股指数（上日）──")
        self.assertGreaterEqual(start_yest, 0)
        self.assertEqual(pairs[start_yest + 1], ["  上证指数", "3200.00"])

    def test_a_indices_none(self):
        """a_indices=None -> '暂无数据'。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=None,
            us_indices=None,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        self._assert_pairs_contain(pairs, "── A股指数 ──", "暂无数据")

    # ════════════════════════════════════════════════════════
    #  市场指数 — 美股
    # ════════════════════════════════════════════════════════

    def test_us_indices_today_values(self):
        """美股指数最新行情写入。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            us_indices=self.us_indices,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        start = self._find_section(pairs, "── 美股指数（最新）──")
        self.assertGreaterEqual(start, 0)

        self.assertEqual(pairs[start + 1], ["  道琼斯", "38000.00  (+0.26%)"])
        self.assertEqual(pairs[start + 2], ["  纳斯达克", "16500.00  (+0.61%)"])
        self.assertEqual(pairs[start + 3], ["  标普500", "5100.00  (+0.39%)"])

    def test_us_indices_yesterday_values(self):
        """美股指数上日收盘写入。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            us_indices=self.us_indices,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        start = self._find_section(pairs, "── 美股指数（上日）──")
        self.assertGreaterEqual(start, 0)

        self.assertEqual(pairs[start + 1], ["  道琼斯", "37900.00"])
        self.assertEqual(pairs[start + 2], ["  纳斯达克", "16400.00"])
        self.assertEqual(pairs[start + 3], ["  标普500", "5080.00"])

    def test_us_indices_missing_code(self):
        """美股缺失某个代码 -> 显示 --。"""
        partial = {
            "gb_dji": {"name": "道琼斯", "price": 38000.00,
                        "yesterday_close": 37900.00, "change_pct": 0.26},
        }
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            us_indices=partial,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        start = self._find_section(pairs, "── 美股指数（最新）──")
        self.assertGreaterEqual(start, 0)

        self.assertEqual(pairs[start + 1], ["  道琼斯", "38000.00  (+0.26%)"])
        self.assertEqual(pairs[start + 2], ["  纳斯达克", "--"])
        self.assertEqual(pairs[start + 3], ["  标普500", "--"])

    def test_us_indices_none(self):
        """us_indices=None -> '暂无数据'。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            us_indices=None,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        self._assert_pairs_contain(pairs, "── 美股指数 ──", "暂无数据")

    # ════════════════════════════════════════════════════════
    #  同时包含 A 股和美股
    # ════════════════════════════════════════════════════════

    def test_both_indices_together(self):
        """A 股 + 美股同时出现，各行均写入。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=self.a_indices,
            us_indices=self.us_indices,
        )
        pairs = self._data_pairs(mocks["mock_data"])
        key_set = {p[0] for p in pairs}

        # A 股章节
        self.assertIn("── A股指数（本日）──", key_set)
        self.assertIn("── A股指数（上日）──", key_set)
        self.assertIn("  上证指数", key_set)
        # 美股章节
        self.assertIn("── 美股指数（最新）──", key_set)
        self.assertIn("── 美股指数（上日）──", key_set)
        self.assertIn("  道琼斯", key_set)
        self.assertIn("  纳斯达克", key_set)
        self.assertIn("  标普500", key_set)

    # ════════════════════════════════════════════════════════
    #  全局行为
    # ════════════════════════════════════════════════════════

    def test_freeze_and_auto_width_called(self):
        """freeze_header 和 auto_width 在末尾被调用。"""
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
        )
        mocks["mock_freeze"].assert_called_once_with(self.ws, 2)
        mocks["mock_auto"].assert_called_once_with(self.ws)

    def test_worksheet_title_set(self):
        """工作页标签名设为 '汇总'。"""
        self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
        )
        self.assertEqual(self.ws.title, "汇总")

    def test_section_headers_written(self):
        """三个章节标题（持仓概况/盈亏汇总/市场指数）通过 section 写入。"""
        self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=self.categories,
            a_indices=self.a_indices,
            us_indices=self.us_indices,
        )
        # 提取 _write_section 中 ws.cell 的 value 参数
        cell_values = [
            c[1]["value"]
            for c in self.ws.cell.call_args_list
            if "value" in c[1]
        ]
        self.assertIn("【持仓概况】", cell_values)
        self.assertIn("【盈亏汇总】", cell_values)
        self.assertIn("【市场指数】", cell_values)

    def test_section_headers_without_data(self):
        """无分类/无指数时仍写入章节标题。"""
        self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=None,
            a_indices=None,
            us_indices=None,
        )
        cell_values = [
            c[1]["value"]
            for c in self.ws.cell.call_args_list
            if "value" in c[1]
        ]
        self.assertIn("【持仓概况】", cell_values)
        self.assertIn("【盈亏汇总】", cell_values)
        self.assertIn("【市场指数】", cell_values)

    def test_appendix_category_unknown_ignored(self):
        """categories 中有额外 key 被忽略（只处理 4 个已知分类）。"""
        extra = {
            "场内股票": ["s1"],
            "场内ETF": [],
            "国内场外": [],
            "QDII": [],
            "期货": ["f1"],  # 额外 key，应被忽略
        }
        mocks = self._call_summary_sheet(
            self.ws, self.mv, self.cost, self.profit, self.today,
            categories=extra,
        )
        pairs = self._data_pairs(mocks["mock_data"])

        self._assert_pairs_contain(pairs, "持仓总数", 1)
        # 额外 key 不会被渲染
        extra_keys = [p[0] for p in pairs if "期货" in p[0]]
        self.assertEqual(len(extra_keys), 0)


if __name__ == "__main__":
    unittest.main()
