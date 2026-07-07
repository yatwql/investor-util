"""TUI 错误友好提示测试 — 异常堆栈不暴露给用户。

测试目标：
  - _print_error_with_hint 对不同异常类型输出对应的中文友好提示
  - 所有友好提示不包含原始异常类型名
  - 菜单调度 _execute_item 捕获异常并用友好提示替代

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/ui/test_tui_edge.py -v
"""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_ui, pytest.mark.edge]


@pytest.mark.edge
class TestPrintErrorWithHint(unittest.TestCase):
    """_print_error_with_hint 友好提示输出测试。"""

    def setUp(self):
        self.capture = io.StringIO()

    def _call(self, e: Exception, prefix: str = "操作失败"):
        from src.python.tui_handlers import _print_error_with_hint
        with patch("sys.stdout", self.capture):
            _print_error_with_hint(e, prefix)
        return self.capture.getvalue()

    def assert_friendly(self, text: str, *keywords: str):
        """友好提示包含所有关键词。"""
        for kw in keywords:
            self.assertIn(kw, text, f"友好提示应包含「{kw}」, 得到: {text}")

    def assert_no_raw_type(self, text: str, e: Exception):
        """友好提示不暴露原始异常类型名。"""
        raw = type(e).__name__
        self.assertNotIn(raw, text,
                         f"友好提示不应包含原始异常类型名「{raw}」: {text}")

    # ── 网络异常 ──

    def test_network_connect(self):
        """ConnectionError → 网络连接异常提示。"""
        out = self._call(ConnectionError("connect failed"))
        self.assert_friendly(out, "网络连接异常")
        self.assert_no_raw_type(out, ConnectionError())

    def test_network_timeout(self):
        """Timeout 信息 → 网络连接异常提示。"""
        out = self._call(TimeoutError("request timeout"))
        self.assert_friendly(out, "网络连接异常")
        self.assert_no_raw_type(out, TimeoutError())

    def test_network_keyword_connect(self):
        """异常信息含 connect → 网络连接异常。"""
        out = self._call(ValueError("cannot connect to host"))
        self.assert_friendly(out, "网络连接异常")
        self.assert_no_raw_type(out, ValueError(""))

    def test_network_keyword_timeout(self):
        """异常信息含 timeout → 网络连接异常。"""
        out = self._call(OSError("read timed out"))
        self.assert_friendly(out, "网络连接异常")
        self.assert_no_raw_type(out, OSError())

    # ── 权限/文件异常 ──

    def test_permission_error(self):
        """PermissionError → 权限不足提示。"""
        out = self._call(PermissionError("access denied"))
        self.assert_friendly(out, "权限不足")
        self.assert_no_raw_type(out, PermissionError())

    def test_file_not_found(self):
        """FileNotFoundError → 文件未找到提示。"""
        out = self._call(FileNotFoundError("no such file"))
        self.assert_friendly(out, "文件未找到")
        self.assert_no_raw_type(out, FileNotFoundError())

    # ── 配置/数据异常 ──

    def test_json_decode_error(self):
        """JSONDecodeError → 配置文件格式错误提示。"""
        out = self._call(json.JSONDecodeError("bad", "", 1))
        self.assert_friendly(out, "配置文件格式错误")
        self.assert_no_raw_type(out, json.JSONDecodeError("x", "", 1))

    def test_value_error(self):
        """ValueError → 数据处理异常提示。"""
        out = self._call(ValueError("invalid value"))
        self.assert_friendly(out, "数据处理异常", "logs/app.log")
        self.assert_no_raw_type(out, ValueError(""))

    def test_key_error(self):
        """KeyError → 数据处理异常提示。"""
        out = self._call(KeyError("missing_key"))
        self.assert_friendly(out, "数据处理异常", "logs/app.log")
        self.assert_no_raw_type(out, KeyError())

    def test_type_error(self):
        """TypeError → 数据处理异常提示。"""
        out = self._call(TypeError("unsupported type"))
        self.assert_friendly(out, "数据处理异常", "logs/app.log")
        self.assert_no_raw_type(out, TypeError())

    # ── 导入/通用异常 ──

    def test_import_error(self):
        """ImportError → 模块加载失败提示。"""
        out = self._call(ImportError("no module named x"))
        self.assert_friendly(out, "模块加载失败", "pip install")
        self.assert_no_raw_type(out, ImportError())

    def test_generic_exception(self):
        """通用 Exception → 操作异常提示。"""
        out = self._call(RuntimeError("something broke"))
        self.assert_friendly(out, "操作异常", "logs/app.log")
        self.assert_no_raw_type(out, RuntimeError(""))


@pytest.mark.edge
class TestExecuteItemErrorFriendly(unittest.TestCase):
    """菜单调度 _execute_item 异常捕获友好提示测试。"""

    def setUp(self):
        self.capture = io.StringIO()

    def _execute(self, callback):
        from src.python.tui_handlers import _execute_item
        # 修补 MENU_ITEMS 构造一个临时条目
        with patch("src.python.tui_handlers.MENU_ITEMS", [
            (0, "test", callback, False),
        ]):
            with patch("sys.stdout", self.capture):
                with patch("src.python.tui_handlers._press_any_key"):
                    _execute_item(0)
        return self.capture.getvalue()

    def test_callback_raises_generic(self):
        """回调抛出通用异常 → 友好提示不含原始异常名。"""
        def _bad():
            raise RuntimeError("内部错误123")
        out = self._execute(_bad)
        self.assertIn("操作执行异常", out)
        self.assertNotIn("RuntimeError", out)

    def test_callback_raises_value_error(self):
        """回调抛出 ValueError → 友好提示含数据处理异常。"""
        def _bad():
            raise ValueError("bad data")
        out = self._execute(_bad)
        self.assertIn("操作执行异常", out)
        self.assertIn("logs/app.log", out)

    def test_callback_raises_network_error(self):
        """回调抛出网络相关异常 → 友好提示含网络连接异常。"""
        def _bad():
            raise ConnectionError("timeout")
        out = self._execute(_bad)
        self.assertIn("操作执行异常", out)
        self.assertIn("网络连接异常", out)

    def test_callback_raises_permission_error(self):
        """回调抛出 PermissionError → 友好提示含权限不足。"""
        def _bad():
            raise PermissionError("no write")
        out = self._execute(_bad)
        self.assertIn("操作执行异常", out)
        self.assertIn("权限不足", out)

    def test_callback_keyboard_interrupt(self):
        """Ctrl+C → 不调用 _print_error_with_hint，直接显示取消。"""
        def _cancel():
            raise KeyboardInterrupt()
        with patch("src.python.tui_handlers._print_error_with_hint") as mock_err:
            out = self._execute(_cancel)
        self.assertIn("操作已取消", out)
        mock_err.assert_not_called()

    def test_busy_skip(self):
        """_busy=True 时跳过执行。"""
        from src.python.tui_handlers import _execute_item
        callback = MagicMock()
        with patch("src.python.tui_handlers.MENU_ITEMS", [
            (0, "test", callback, False),
        ]):
            with patch("src.python.tui_handlers._busy", True):
                _execute_item(0)
        callback.assert_not_called()
