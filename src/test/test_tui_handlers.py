"""TUI 命令处理器单元测试。

测试目标：
  - _check_network_available — 行情数据可用性检测
  - _print_error_with_hint — 不同类型异常的友好提示格式

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_tui_handlers -v
"""

from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock, patch

from src.python.tui_handlers import (
    _check_network_available,
    _print_error_with_hint,
)


class FakeDetail:
    """模拟 DetailRow（namedtuple 替代）。"""
    def __init__(self, price=None):
        self.price = price


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
        """其他错误 → 直接显示错误消息。"""
        out = self._capture(ValueError("invalid value"), "操作失败")
        self.assertIn("操作失败", out)
        self.assertIn("invalid value", out)

    def test_network_keywords(self) -> None:
        """不同网络错误关键词均触发网络提示。"""
        for kw in ("connect", "timeout", "dns", "reset", "eof", "read timed out"):
            out = self._capture(OSError(f"Connection {kw}"))
            self.assertIn("网络连接异常", out, f"Keyword '{kw}' not matched")


if __name__ == "__main__":
    unittest.main()
