"""TUI 报告生成命令处理器单元测试。

测试可独立辅助函数。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/handlers/test_handlers_report.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


@pytest.mark.unit_core
class TestPromptForceLlm(unittest.TestCase):
    """_prompt_force_llm 用户确认。"""

    def test_yes_returns_true(self):
        """输入 y → True，并调用 reporter.ok。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        with patch("builtins.input", return_value="y"):
            result = _prompt_force_llm(reporter)
        self.assertTrue(result)
        reporter.ok.assert_called_once()

    def test_no_returns_false(self):
        """输入 n → False。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        with patch("builtins.input", return_value="n"):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)
        reporter.ok.assert_not_called()

    def test_empty_input_returns_false(self):
        """空回车 → False。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        with patch("builtins.input", return_value=""):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)

    def test_eof_error_returns_false(self):
        """EOFError → False，不崩溃。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        with patch("builtins.input", side_effect=EOFError):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)

    def test_keyboard_interrupt_returns_false(self):
        """KeyboardInterrupt → False，不崩溃。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)

    def test_uppercase_y(self):
        """大写 Y 也视为 yes。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        with patch("builtins.input", return_value="Y"):
            result = _prompt_force_llm(reporter)
        self.assertTrue(result)

    def test_whitespace_y(self):
        """y 带前后空格仍视为 yes。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        with patch("builtins.input", return_value="  y  "):
            result = _prompt_force_llm(reporter)
        self.assertTrue(result)
