"""TUI 键盘输入函数单元测试。

测试目标：
  - get_key()      — Windows/Linux 分发逻辑
  - _get_key_windows() — Windows 分支（msvcrt）
  - _get_key_linux()    — Linux 分支（tty + termios + select）
  - 键名常量

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test.test_tui -v
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from src.python.tui import (
    KEY_CTRL_C,
    KEY_DOWN,
    KEY_ENTER,
    KEY_UNKNOWN,
    KEY_UP,
    get_key,
    _get_key_linux,
    _get_key_windows,
)


class TestConstants(unittest.TestCase):
    """键名常量测试。"""

    def test_key_up(self) -> None:
        self.assertEqual(KEY_UP, "KEY_UP")

    def test_key_down(self) -> None:
        self.assertEqual(KEY_DOWN, "KEY_DOWN")

    def test_key_enter(self) -> None:
        self.assertEqual(KEY_ENTER, "KEY_ENTER")

    def test_key_ctrl_c(self) -> None:
        self.assertEqual(KEY_CTRL_C, "KEY_CTRL_C")

    def test_key_unknown(self) -> None:
        self.assertEqual(KEY_UNKNOWN, "KEY_UNKNOWN")


class TestGetKeyDispatch(unittest.TestCase):
    """get_key() 分发逻辑测试。

    通过 mock _get_key_windows / _get_key_linux 验证 os.name 的分支选择，
    不依赖实际平台模块，可跨平台运行。
    """

    @patch("src.python.tui._get_key_windows")
    @patch("src.python.tui._get_key_linux")
    def test_windows_dispatch(
        self,
        mock_linux: MagicMock,
        mock_windows: MagicMock,
    ) -> None:
        """os.name == 'nt' 时走 Windows 分支。"""
        with patch("src.python.tui.os.name", "nt"):
            get_key()
        mock_windows.assert_called_once()
        mock_linux.assert_not_called()

    @patch("src.python.tui._get_key_windows")
    @patch("src.python.tui._get_key_linux")
    def test_linux_dispatch(
        self,
        mock_linux: MagicMock,
        mock_windows: MagicMock,
    ) -> None:
        """os.name != 'nt' 时走 Linux 分支。"""
        with patch("src.python.tui.os.name", "posix"):
            get_key()
        mock_linux.assert_called_once()
        mock_windows.assert_not_called()


@unittest.skipIf(os.name != "nt", "Windows only")
class TestGetKeyWindows(unittest.TestCase):
    """Windows 分支 _get_key_windows 测试。"""

    def setUp(self) -> None:
        # 确保 msvcrt 已在 sys.modules 中，patch 才能正确拦截
        import msvcrt  # noqa: F811

        self._patcher = patch("msvcrt.getch")
        self._mock_getch = self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    # -- 特殊键 -------------------------------------------------------

    def test_ctrl_c(self) -> None:
        """Ctrl+C 输入 → KEY_CTRL_C。"""
        self._mock_getch.return_value = b"\x03"
        self.assertEqual(_get_key_windows(), KEY_CTRL_C)

    def test_enter(self) -> None:
        """Enter 回车 → KEY_ENTER。"""
        self._mock_getch.return_value = b"\r"
        self.assertEqual(_get_key_windows(), KEY_ENTER)

    def test_arrow_up(self) -> None:
        """方向键上 (b'\\xe0' + b'H') → KEY_UP。"""
        self._mock_getch.side_effect = [b"\xe0", b"H"]
        self.assertEqual(_get_key_windows(), KEY_UP)

    def test_arrow_down(self) -> None:
        """方向键下 (b'\\xe0' + b'P') → KEY_DOWN。"""
        self._mock_getch.side_effect = [b"\xe0", b"P"]
        self.assertEqual(_get_key_windows(), KEY_DOWN)

    def test_arrow_unknown(self) -> None:
        """方向键前缀后跟未知键 → KEY_UNKNOWN。"""
        self._mock_getch.side_effect = [b"\xe0", b"Q"]
        self.assertEqual(_get_key_windows(), KEY_UNKNOWN)

    def test_func_key_prefix(self) -> None:
        """功能键前缀 b'\\x00' 后跟未知键 → KEY_UNKNOWN。"""
        self._mock_getch.side_effect = [b"\x00", b"Q"]
        self.assertEqual(_get_key_windows(), KEY_UNKNOWN)

    # -- 普通键 -------------------------------------------------------

    def test_upper_letter(self) -> None:
        """大写字母键 → 返回大写字母。"""
        self._mock_getch.return_value = b"X"
        self.assertEqual(_get_key_windows(), "X")

    def test_lowercase_letter(self) -> None:
        """小写字母键 → 转为大写。"""
        self._mock_getch.return_value = b"a"
        self.assertEqual(_get_key_windows(), "A")

    def test_digit(self) -> None:
        """数字键 → 返回数字字符串。"""
        self._mock_getch.return_value = b"7"
        self.assertEqual(_get_key_windows(), "7")

    # -- 异常路径 -----------------------------------------------------

    def test_unicode_decode_error(self) -> None:
        """UnicodeDecodeError → KEY_UNKNOWN。"""
        self._mock_getch.return_value = b"\x80"
        self.assertEqual(_get_key_windows(), KEY_UNKNOWN)

    def test_keyboard_interrupt(self) -> None:
        """KeyboardInterrupt 异常 → KEY_CTRL_C。"""
        self._mock_getch.side_effect = KeyboardInterrupt()
        self.assertEqual(_get_key_windows(), KEY_CTRL_C)


@unittest.skipIf(os.name != "posix", "Linux only")
class TestGetKeyLinux(unittest.TestCase):
    """Linux 分支 _get_key_linux 测试。"""

    def setUp(self) -> None:
        import termios
        import tty
        import select

        self._termios_error = termios.error
        self._stdin_patcher = patch("src.python.tui.sys.stdin")
        self._mock_stdin = self._stdin_patcher.start()
        self._mock_stdin.fileno.return_value = 99

        # 使用全局模块级 patch，因为 _get_key_linux 内部通过 import 获取模块
        self._tcgetattr_patcher = patch("termios.tcgetattr")
        self._mock_tcgetattr = self._tcgetattr_patcher.start()
        self._mock_tcgetattr.return_value = MagicMock()

        self._tcsetattr_patcher = patch("termios.tcsetattr")
        self._mock_tcsetattr = self._tcsetattr_patcher.start()

        self._setraw_patcher = patch("tty.setraw")
        self._mock_setraw = self._setraw_patcher.start()

        self._select_patcher = patch("select.select")
        self._mock_select = self._select_patcher.start()

    def tearDown(self) -> None:
        self._select_patcher.stop()
        self._setraw_patcher.stop()
        self._tcsetattr_patcher.stop()
        self._tcgetattr_patcher.stop()
        self._stdin_patcher.stop()

    # -- 特殊键 -------------------------------------------------------

    def test_ctrl_c(self) -> None:
        """Ctrl+C 输入 → KEY_CTRL_C。"""
        self._mock_stdin.read.return_value = "\x03"
        self.assertEqual(_get_key_linux(), KEY_CTRL_C)

    def test_enter_cr(self) -> None:
        """回车 \\r → KEY_ENTER。"""
        self._mock_stdin.read.return_value = "\r"
        self.assertEqual(_get_key_linux(), KEY_ENTER)

    def test_enter_lf(self) -> None:
        """换行 \\n → KEY_ENTER。"""
        self._mock_stdin.read.return_value = "\n"
        self.assertEqual(_get_key_linux(), KEY_ENTER)

    # -- ESC / 方向键 -------------------------------------------------

    def test_escape_up(self) -> None:
        """ESC [ A → KEY_UP。"""
        self._mock_stdin.read.side_effect = ["\x1b", "[A"]
        self._mock_select.return_value = ([self._mock_stdin], [], [])
        self.assertEqual(_get_key_linux(), KEY_UP)

    def test_escape_down(self) -> None:
        """ESC [ B → KEY_DOWN。"""
        self._mock_stdin.read.side_effect = ["\x1b", "[B"]
        self._mock_select.return_value = ([self._mock_stdin], [], [])
        self.assertEqual(_get_key_linux(), KEY_DOWN)

    def test_escape_unknown_seq(self) -> None:
        """ESC [ X → KEY_UNKNOWN。"""
        self._mock_stdin.read.side_effect = ["\x1b", "[X"]
        self._mock_select.return_value = ([self._mock_stdin], [], [])
        self.assertEqual(_get_key_linux(), KEY_UNKNOWN)

    def test_standalone_esc(self) -> None:
        """单独 ESC 键（select 超时）→ KEY_UNKNOWN。"""
        self._mock_stdin.read.return_value = "\x1b"
        self._mock_select.return_value = ([], [], [])
        self.assertEqual(_get_key_linux(), KEY_UNKNOWN)

    # -- 普通键 -------------------------------------------------------

    def test_normal_key(self) -> None:
        """普通字母键 → 转为大写。"""
        self._mock_stdin.read.return_value = "x"
        self.assertEqual(_get_key_linux(), "X")

    def test_empty_key(self) -> None:
        """空字符串 → KEY_UNKNOWN。"""
        self._mock_stdin.read.return_value = ""
        self.assertEqual(_get_key_linux(), KEY_UNKNOWN)

    # -- 异常路径 -----------------------------------------------------

    def test_setraw_error(self) -> None:
        """tty.setraw 抛出 termios.error → KEY_UNKNOWN，finally 仍调用 tcsetattr。"""
        self._mock_setraw.side_effect = self._termios_error("fake error")
        self.assertEqual(_get_key_linux(), KEY_UNKNOWN)
        self._mock_tcsetattr.assert_called_once()

    def test_keyboard_interrupt(self) -> None:
        """sys.stdin.read 抛出 KeyboardInterrupt → KEY_CTRL_C。"""
        self._mock_stdin.read.side_effect = KeyboardInterrupt()
        self.assertEqual(_get_key_linux(), KEY_CTRL_C)


if __name__ == "__main__":
    unittest.main()
