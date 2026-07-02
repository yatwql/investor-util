"""TUI 命令处理器单元测试。

测试目标：
  - _Timer 类上下文管理器
  - _print_timing_summary / _print_llm_session_usage 输出格式化
  - _check_network_available 行情数据可用性检测（含 print 输出）
  - _print_error_with_hint 不同类型异常的友好提示格式
  - _add_error / _clear_errors / _print_error_summary 错误累积
  - _call_sheet 安全调用包装
  - _execute_item 菜单执行调度与防重入
  - _select_holdings_file 文件选择逻辑

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test.test_tui_handlers -v
"""

from __future__ import annotations

import io
import time as _time_module
import unittest
from unittest.mock import MagicMock, patch

import src.python.tui_handlers as _th_module

from src.python.report.progress import _timing_records, _Timer

from src.python.tui_handlers import (

    _check_network_available,
    _execute_item,
    _print_error_with_hint,
    _print_llm_session_usage,
    _print_timing_summary,
    _select_holdings_file,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_ui]



class FakeDetail:
    """模拟 DetailRow（namedtuple 替代）。"""
    def __init__(self, price=None):
        self.price = price


# ═══════════════════════════════════════════════════════════════
# 原有测试（保持不变）
# ═══════════════════════════════════════════════════════════════

class TestCheckNetworkAvailable(unittest.TestCase):
    """_check_network_available 测试。"""

    def test_empty_list(self) -> None:
        """空列表 → False。"""
        self.assertFalse(_check_network_available([]))

    def test_all_none(self) -> None:
        """所有价格均为 None → False（网络不可用）。"""
        details = [FakeDetail(price=None), FakeDetail(price=None)]
        self.assertFalse(_check_network_available(details))

    def test_all_zero(self) -> None:
        """所有价格均为 0 → False（网络不可用）。"""
        details = [FakeDetail(price=0), FakeDetail(price=0)]
        self.assertFalse(_check_network_available(details))

    def test_mixed_available(self) -> None:
        """部分有价 → True。"""
        details = [FakeDetail(price=None), FakeDetail(price=10.5)]
        self.assertTrue(_check_network_available(details))

    def test_all_available(self) -> None:
        """全部有价 → True。"""
        details = [FakeDetail(price=10.0), FakeDetail(price=20.5)]
        self.assertTrue(_check_network_available(details))

    def test_single_none(self) -> None:
        """单条 None → False。"""
        self.assertFalse(_check_network_available([FakeDetail(price=None)]))

    def test_single_available(self) -> None:
        """单条有价 → True。"""
        self.assertTrue(_check_network_available([FakeDetail(price=15.0)]))


class TestPrintErrorWithHint(unittest.TestCase):
    """_print_error_with_hint 错误提示格式测试。"""

    def _capture(self, e: Exception, prefix: str = "") -> str:
        """捕获 print 输出。"""
        out = io.StringIO()
        with patch("sys.stdout", out):
            _print_error_with_hint(e, prefix)
        return out.getvalue()

    def test_network_error(self) -> None:
        """网络超时 → 网络连接异常提示。"""
        out = self._capture(TimeoutError("Connection timed out"), "获取失败")
        self.assertIn("网络连接异常", out)
        self.assertIn("获取失败", out)

    def test_connection_refused(self) -> None:
        """连接被拒 → 网络连接异常提示。"""
        out = self._capture(ConnectionError("Connection refused"))
        self.assertIn("网络连接异常", out)

    def test_dns_error(self) -> None:
        """DNS 解析失败 → 网络连接异常提示。"""
        out = self._capture(ConnectionError("Failed to resolve host"))
        self.assertIn("网络连接异常", out)

    def test_permission_error(self) -> None:
        """权限错误 → 文件写入权限提示。"""
        out = self._capture(PermissionError("Permission denied"))
        self.assertIn("写入权限", out)

    def test_file_not_found(self) -> None:
        """文件未找到 → 文件未找到提示。"""
        out = self._capture(FileNotFoundError("No such file"))
        self.assertIn("文件未找到", out)

    def test_generic_error(self) -> None:
        """其他错误 → 数据处理异常提示，不暴露原始堆栈。"""
        out = self._capture(ValueError("invalid value"), "操作失败")
        self.assertIn("操作失败", out)
        self.assertIn("数据处理异常", out)
        self.assertNotIn("invalid value", out)

    def test_network_keywords(self) -> None:
        """不同网络错误关键词均触发网络提示。"""
        for kw in ("connect", "timeout", "dns", "reset", "eof", "read timed out"):
            out = self._capture(OSError(f"Connection {kw}"))
            self.assertIn("网络连接异常", out, f"Keyword '{kw}' not matched")


# ═══════════════════════════════════════════════════════════════
# 新增测试 — _Timer
# ═══════════════════════════════════════════════════════════════

class TestTimer(unittest.TestCase):
    """_Timer 上下文管理器测试。"""

    def setUp(self):
        _timing_records.clear()

    def tearDown(self):
        _timing_records.clear()

    def test_enter_sets_start(self):
        """__enter__ 记录开始时间。"""
        with patch.object(_time_module, 'time', return_value=12345.0):
            with _Timer("test") as t:
                self.assertEqual(t.start, 12345.0)

    def test_exit_records_elapsed(self):
        """__exit__ 正确记录耗时。"""
        with patch.object(_time_module, 'time', side_effect=[1000.0, 1005.5]):
            with _Timer("test"):
                pass
        self.assertEqual(len(_timing_records), 1)
        self.assertEqual(_timing_records[0][0], "test")
        self.assertAlmostEqual(_timing_records[0][1], 5.5)

    def test_multiple_timers(self):
        """多个计时器各自记录互不干扰。"""
        with patch.object(_time_module, 'time', side_effect=[100.0, 102.0, 102.0, 105.0]):
            with _Timer("fast"):
                pass
            with _Timer("slow"):
                pass
        self.assertEqual(len(_timing_records), 2)
        self.assertAlmostEqual(_timing_records[0][1], 2.0)
        self.assertAlmostEqual(_timing_records[1][1], 3.0)

    def test_nested_timers(self):
        """嵌套计时器正确工作。"""
        with patch.object(_time_module, 'time', side_effect=[0.0, 0.5, 1.0, 2.0]):
            with _Timer("outer"):
                with _Timer("inner"):
                    pass
        self.assertEqual(len(_timing_records), 2)
        self.assertEqual(_timing_records[0][0], "inner")
        self.assertAlmostEqual(_timing_records[0][1], 0.5)
        self.assertEqual(_timing_records[1][0], "outer")
        self.assertAlmostEqual(_timing_records[1][1], 2.0)

    def test_label_preserved(self):
        """标签正确储存在记录中。"""
        with _Timer("模块A"):
            pass
        self.assertEqual(_timing_records[0][0], "模块A")

    def test_elapsed_is_float(self):
        """耗时记录为浮点数。"""
        with patch.object(_time_module, 'time', side_effect=[0.0, 0.0]):
            with _Timer("test"):
                pass
        self.assertIsInstance(_timing_records[0][1], float)

    def test_many_timers_append_all(self):
        """大量计时器均被追加到列表中。"""
        n = 10
        times = list(range(n * 2))
        with patch.object(_time_module, 'time', side_effect=times):
            for i in range(n):
                with _Timer(f"t{i}"):
                    pass
        self.assertEqual(len(_timing_records), n)


# ═══════════════════════════════════════════════════════════════
# 新增测试 — _print_timing_summary
# ═══════════════════════════════════════════════════════════════

class TestPrintTimingSummary(unittest.TestCase):
    """_print_timing_summary 输出格式化测试。"""

    def setUp(self):
        _timing_records.clear()

    def tearDown(self):
        _timing_records.clear()

    def _capture(self) -> str:
        out = io.StringIO()
        with patch("sys.stdout", out):
            _print_timing_summary()
        return out.getvalue()

    def test_no_records_silent(self):
        """无计时记录时静默无输出。"""
        out = self._capture()
        self.assertEqual(out, "")

    def test_single_record(self):
        """单条记录正确输出。"""
        _timing_records.append(("模块A", 1.5))
        out = self._capture()
        self.assertIn("模块A", out)
        self.assertIn("1.5s", out)
        self.assertIn("100.0%", out)

    def test_clears_after_print(self):
        """输出后清空记录列表。"""
        _timing_records.append(("test", 0.5))
        self._capture()
        self.assertEqual(len(_timing_records), 0)

    def test_sorted_by_desc(self):
        """按耗时降序排列。"""
        _timing_records.append(("fast", 0.5))
        _timing_records.append(("slow", 3.0))
        _timing_records.append(("medium", 1.0))
        out = self._capture()
        slow_idx = out.find("slow")
        medium_idx = out.find("medium")
        fast_idx = out.find("fast")
        self.assertLess(slow_idx, medium_idx)
        self.assertLess(medium_idx, fast_idx)

    def test_zero_total_handling(self):
        """总耗时为 0 时不会除零错误。"""
        _timing_records.append(("zero", 0.0))
        try:
            self._capture()
        except ZeroDivisionError:
            self.fail("总耗时为 0 时不应抛出 ZeroDivisionError")

    def test_multiple_records_percentages(self):
        """多条记录的百分比计算正确。"""
        _timing_records.append(("A", 1.0))
        _timing_records.append(("B", 3.0))
        out = self._capture()
        self.assertIn("25.0%", out)
        self.assertIn("75.0%", out)

    def test_header_and_footer_lines(self):
        """输出包含正确的表头和表尾。"""
        _timing_records.append(("X", 1.0))
        out = self._capture()
        self.assertIn("模块耗时排行", out)
        self.assertIn("┌", out)
        self.assertIn("└", out)


# ═══════════════════════════════════════════════════════════════
# 新增测试 — _print_llm_session_usage
# ═══════════════════════════════════════════════════════════════

class TestPrintLlmSessionUsage(unittest.TestCase):
    """_print_llm_session_usage 输出测试。"""

    def _capture(self, usage: dict | None = None) -> str:
        out = io.StringIO()
        with patch("sys.stdout", out):
            _print_llm_session_usage(usage)
        return out.getvalue()

    def test_empty_dict_silent(self):
        """空 usage 字典不输出。"""
        out = self._capture({})
        self.assertEqual(out, "")

    def test_zero_calls_silent(self):
        """调用次数为零时不输出。"""
        out = self._capture({"call_count": 0})
        self.assertEqual(out, "")

    def test_with_calls(self):
        """有调用记录时输出格式正确。"""
        usage = {"call_count": 5, "input_tokens": 1000, "output_tokens": 500, "total_cost": 0.15, "currency": "CNY"}
        out = self._capture(usage)
        self.assertIn("5", out)
        self.assertIn("1,500", out)
        self.assertIn("¥0.1500", out)

    def test_usd_currency(self):
        """USD 货币符号正确。"""
        usage = {"call_count": 1, "input_tokens": 100, "output_tokens": 100, "total_cost": 0.05, "currency": "USD"}
        out = self._capture(usage)
        self.assertIn("$0.0500", out)

    def test_eur_currency(self):
        """EUR 货币符号正确。"""
        usage = {"call_count": 1, "input_tokens": 100, "output_tokens": 100, "total_cost": 0.05, "currency": "EUR"}
        out = self._capture(usage)
        self.assertIn("€0.0500", out)

    def test_gbp_currency(self):
        """GBP 货币符号正确。"""
        usage = {"call_count": 1, "input_tokens": 100, "output_tokens": 100, "total_cost": 0.05, "currency": "GBP"}
        out = self._capture(usage)
        self.assertIn("£0.0500", out)

    def test_none_usage_calls_get_session_usage(self):
        """usage=None 时导入 get_session_usage 并使用其返回值。"""
        mock_usage = {"call_count": 2, "input_tokens": 50, "output_tokens": 50, "total_cost": 0.01, "currency": "CNY"}
        with patch("src.python.llm.get_session_usage", return_value=mock_usage):
            out = self._capture(None)
            self.assertIn("2", out)

    def test_none_usage_empty_result_silent(self):
        """usage=None 且 get_session_usage 返回空用量时静默。"""
        with patch("src.python.llm.get_session_usage", return_value={"call_count": 0}):
            out = self._capture(None)
            self.assertEqual(out, "")

    def test_zero_tokens_formatted(self):
        """tokens 为 0 时格式化为 0。"""
        usage = {"call_count": 1, "input_tokens": 0, "output_tokens": 0, "total_cost": 0.0, "currency": "CNY"}
        out = self._capture(usage)
        self.assertIn("1", out)
        self.assertIn("0", out)


# ═══════════════════════════════════════════════════════════════
# 新增测试 — _check_network_available print 输出
# ═══════════════════════════════════════════════════════════════

class TestCheckNetworkAvailablePrint(unittest.TestCase):
    """_check_network_available 的 print 输出测试。"""

    def _capture_call(self, details: list) -> tuple[bool, str]:
        out = io.StringIO()
        with patch("sys.stdout", out):
            result = _check_network_available(details)
        return result, out.getvalue()

    def test_empty_list_no_print(self):
        """空列表不输出。"""
        result, out = self._capture_call([])
        self.assertFalse(result)
        self.assertEqual(out, "")

    def test_all_none_prints_warning(self):
        """全部为 None 时打印网络异常提示。"""
        result, out = self._capture_call([FakeDetail(price=None)])
        self.assertFalse(result)
        self.assertIn("网络连接异常", out)

    def test_all_zero_prints_warning(self):
        """全部为 0 时打印网络异常提示。"""
        result, out = self._capture_call([FakeDetail(price=0)])
        self.assertFalse(result)
        self.assertIn("网络连接异常", out)

    def test_mixed_no_print(self):
        """部分有价时不输出。"""
        result, out = self._capture_call([FakeDetail(price=None), FakeDetail(price=10.0)])
        self.assertTrue(result)
        self.assertEqual(out, "")

    def test_all_available_no_print(self):
        """全部有价时不输出。"""
        result, out = self._capture_call([FakeDetail(price=10.0), FakeDetail(price=20.5)])
        self.assertTrue(result)
        self.assertEqual(out, "")

    def test_warning_message_contains_guide(self):
        """网络异常消息包含指引文字。"""
        _, out = self._capture_call([FakeDetail(price=None)])
        self.assertIn("请检查网络连接", out)


# ═══════════════════════════════════════════════════════════════
# 新增测试 — _print_error_with_hint 额外用例
# ═══════════════════════════════════════════════════════════════

class TestPrintErrorWithHintExtended(unittest.TestCase):
    """_print_error_with_hint 额外关键词及边界测试。"""

    def _capture(self, e: Exception, prefix: str = "") -> str:
        out = io.StringIO()
        with patch("sys.stdout", out):
            _print_error_with_hint(e, prefix)
        return out.getvalue()

    def test_network_keyword_match(self):
        """'network' 关键词触发网络提示。"""
        out = self._capture(OSError("network is unreachable"))
        self.assertIn("网络连接异常", out)

    def test_connection_keyword_match(self):
        """'connection' 关键词触发网络提示。"""
        out = self._capture(OSError("connection broken"))
        self.assertIn("网络连接异常", out)

    def test_resolve_keyword_match(self):
        """'resolve' 关键词触发网络提示。"""
        out = self._capture(OSError("unable to resolve"))
        self.assertIn("网络连接异常", out)

    def test_case_insensitive_keyword(self):
        """关键词匹配不区分大小写。"""
        out = self._capture(OSError("CONNECTION LOST"))
        self.assertIn("网络连接异常", out)

    def test_prefix_appears_in_output(self):
        """前缀字符串出现在输出中，不暴露原始异常。"""
        out = self._capture(ValueError("test msg"), "自定义前缀")
        self.assertIn("自定义前缀", out)
        self.assertNotIn("test msg", out)
        self.assertIn("数据处理异常", out)

    def test_empty_message_handling(self):
        """空消息的异常不崩溃。"""
        out = self._capture(ValueError(""), "操作失败")
        self.assertNotIn("网络连接异常", out)
        self.assertIn("操作失败", out)


# ═══════════════════════════════════════════════════════════════
# 新增测试 — _execute_item
# ═══════════════════════════════════════════════════════════════

class TestExecuteItem(unittest.TestCase):
    """_execute_item 菜单执行调度与防重入测试。"""

    def setUp(self):
        _th_module._busy = False

    def tearDown(self):
        _th_module._busy = False

    @patch("src.python.tui_handlers.MENU_ITEMS")
    def test_exit_item_calls_exit_app(self, mock_menu):
        """退出项调用 _exit_app。"""
        callback = MagicMock()
        mock_menu.__getitem__.return_value = ("X", "Exit", callback, True)
        with patch("src.python.tui_menu._exit_app", side_effect=SystemExit(0)):
            with self.assertRaises(SystemExit):
                _execute_item(0)
        callback.assert_not_called()

    @patch("src.python.tui_handlers.MENU_ITEMS")
    def test_normal_item_calls_callback(self, mock_menu):
        """普通项调用回调函数。"""
        callback = MagicMock()
        mock_menu.__getitem__.return_value = ("T", "Test", callback, False)
        _execute_item(0)
        callback.assert_called_once()

    @patch("src.python.tui_handlers.MENU_ITEMS")
    def test_busy_lock_prevents_reentry(self, mock_menu):
        """_busy 锁防止重入。"""
        callback = MagicMock()
        mock_menu.__getitem__.return_value = ("T", "Test", callback, False)
        _th_module._busy = True
        _execute_item(0)
        callback.assert_not_called()

    @patch("src.python.tui_handlers.MENU_ITEMS")
    def test_busy_reset_after_execution(self, mock_menu):
        """执行后 _busy 恢复为 False。"""
        callback = MagicMock()
        mock_menu.__getitem__.return_value = ("T", "Test", callback, False)
        _execute_item(0)
        self.assertFalse(_th_module._busy)

    @patch("src.python.tui_handlers.MENU_ITEMS")
    def test_keyboard_interrupt_handled(self, mock_menu):
        """KeyboardInterrupt 被捕获并调用 _press_any_key。"""
        callback = MagicMock(side_effect=KeyboardInterrupt)
        mock_menu.__getitem__.return_value = ("T", "Test", callback, False)
        with patch("src.python.tui_handlers._press_any_key") as mock_pak:
            _execute_item(0)
            mock_pak.assert_called_once()
        self.assertFalse(_th_module._busy)

    @patch("src.python.tui_handlers.MENU_ITEMS")
    def test_none_callback_does_not_set_busy(self, mock_menu):
        """callback 为 None 时不设置 _busy。"""
        mock_menu.__getitem__.return_value = ("T", "Test", None, False)
        _execute_item(0)
        self.assertFalse(_th_module._busy)

    def test_invalid_index_raises_error(self):
        """无效索引引发 IndexError。"""
        with self.assertRaises(IndexError):
            _execute_item(999)


# ═══════════════════════════════════════════════════════════════
# 新增测试 — _select_holdings_file
# ═══════════════════════════════════════════════════════════════

class TestSelectHoldingsFile(unittest.TestCase):
    """_select_holdings_file 文件选择逻辑测试。"""

    @patch("src.python.tui_handlers._refresh_config")
    @patch("src.python.tui_handlers.get_config_cache")
    @patch("os.path.exists")
    def test_specific_path_exists(
        self,
        mock_exists: MagicMock,
        mock_config_cache: MagicMock,
        mock_refresh: MagicMock,
    ):
        """配置中的具体路径存在时直接返回该路径。"""
        mock_config_cache.return_value = {
            "holdings_dir": "dummy_dir",
            "holdings_filename": "myfile.xlsx",
        }
        mock_exists.return_value = True
        result = _select_holdings_file()
        self.assertIsNotNone(result)
        self.assertIn("myfile.xlsx", result)

    @patch("src.python.tui_handlers._refresh_config")
    @patch("src.python.tui_handlers.get_config_cache")
    @patch("os.path.exists")
    @patch("src.python.tui_handlers.list_xlsx_files")
    def test_no_files_found(
        self,
        mock_list: MagicMock,
        mock_exists: MagicMock,
        mock_config_cache: MagicMock,
        mock_refresh: MagicMock,
    ):
        """目录下无 xlsx 文件时返回 None。"""
        mock_config_cache.return_value = {
            "holdings_dir": "dummy_dir",
            "holdings_filename": "",
        }
        mock_exists.return_value = False
        mock_list.return_value = []
        out = io.StringIO()
        with patch("sys.stdout", out):
            result = _select_holdings_file()
        self.assertIsNone(result)
        self.assertIn("未找到", out.getvalue())

    @patch("src.python.tui_handlers._refresh_config")
    @patch("src.python.tui_handlers.get_config_cache")
    @patch("os.path.exists")
    @patch("src.python.tui_handlers.list_xlsx_files")
    def test_single_file_auto_select(
        self,
        mock_list: MagicMock,
        mock_exists: MagicMock,
        mock_config_cache: MagicMock,
        mock_refresh: MagicMock,
    ):
        """仅一个文件时自动选择。"""
        mock_config_cache.return_value = {
            "holdings_dir": "dummy_dir",
            "holdings_filename": "",
        }
        mock_exists.return_value = False
        mock_list.return_value = ["dummy_dir/holdings.xlsx"]
        out = io.StringIO()
        with patch("sys.stdout", out):
            result = _select_holdings_file()
        self.assertEqual(result, "dummy_dir/holdings.xlsx")
        self.assertIn("唯一找到", out.getvalue())

    @patch("src.python.tui_handlers._refresh_config")
    @patch("src.python.tui_handlers.get_config_cache")
    @patch("os.path.exists")
    @patch("src.python.tui_handlers.list_xlsx_files")
    @patch("src.python.tui_handlers.get_xlsx_info")
    @patch("os.path.getsize")
    @patch("os.path.getmtime")
    @patch("builtins.input")
    def test_multiple_files_user_select(
        self,
        mock_input: MagicMock,
        mock_mtime: MagicMock,
        mock_size: MagicMock,
        mock_info: MagicMock,
        mock_list: MagicMock,
        mock_exists: MagicMock,
        mock_config_cache: MagicMock,
        mock_refresh: MagicMock,
    ):
        """多个文件时用户可输入编号选择。"""
        mock_config_cache.return_value = {
            "holdings_dir": "dummy_dir",
            "holdings_filename": "",
        }
        mock_exists.return_value = False
        mock_list.return_value = ["dummy_dir/a.xlsx", "dummy_dir/b.xlsx"]
        mock_info.return_value = {"accounts": 3}
        mock_input.return_value = "2"
        mock_size.return_value = 2048
        mock_mtime.return_value = 1000000.0
        result = _select_holdings_file()
        self.assertEqual(result, "dummy_dir/b.xlsx")

    @patch("src.python.tui_handlers._refresh_config")
    @patch("src.python.tui_handlers.get_config_cache")
    @patch("os.path.exists")
    @patch("src.python.tui_handlers.list_xlsx_files")
    @patch("src.python.tui_handlers.get_xlsx_info")
    @patch("os.path.getsize")
    @patch("os.path.getmtime")
    @patch("builtins.input")
    def test_multiple_files_invalid_input(
        self,
        mock_input: MagicMock,
        mock_mtime: MagicMock,
        mock_size: MagicMock,
        mock_info: MagicMock,
        mock_list: MagicMock,
        mock_exists: MagicMock,
        mock_config_cache: MagicMock,
        mock_refresh: MagicMock,
    ):
        """无效编号输入返回 None。"""
        mock_config_cache.return_value = {
            "holdings_dir": "dummy_dir",
            "holdings_filename": "",
        }
        mock_exists.return_value = False
        mock_list.return_value = ["dummy_dir/a.xlsx", "dummy_dir/b.xlsx"]
        mock_info.return_value = {"accounts": 3}
        mock_input.return_value = "abc"
        mock_size.return_value = 2048
        mock_mtime.return_value = 1000000.0
        result = _select_holdings_file()
        self.assertIsNone(result)

    @patch("src.python.tui_handlers._refresh_config")
    @patch("src.python.tui_handlers.get_config_cache")
    @patch("os.path.exists")
    @patch("src.python.tui_handlers.list_xlsx_files")
    @patch("src.python.tui_handlers.get_xlsx_info")
    @patch("os.path.getsize")
    @patch("os.path.getmtime")
    @patch("builtins.input")
    def test_eof_error_handled(
        self,
        mock_input: MagicMock,
        mock_mtime: MagicMock,
        mock_size: MagicMock,
        mock_info: MagicMock,
        mock_list: MagicMock,
        mock_exists: MagicMock,
        mock_config_cache: MagicMock,
        mock_refresh: MagicMock,
    ):
        """input 引发 EOFError 时返回 None。"""
        mock_config_cache.return_value = {
            "holdings_dir": "dummy_dir",
            "holdings_filename": "",
        }
        mock_exists.return_value = False
        mock_list.return_value = ["dummy_dir/a.xlsx", "dummy_dir/b.xlsx"]
        mock_info.return_value = {"accounts": 3}
        mock_input.side_effect = EOFError()
        mock_size.return_value = 2048
        mock_mtime.return_value = 1000000.0
        result = _select_holdings_file()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
