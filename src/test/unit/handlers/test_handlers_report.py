"""TUI 报告生成命令处理器单元测试。

测试可独立辅助函数。

运行：
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
        from src.python.tui.handlers_report import _prompt_force_llm

        reporter = MagicMock()
        with patch("builtins.input", return_value="y"):
            result = _prompt_force_llm(reporter)
        self.assertTrue(result)
        reporter.ok.assert_called_once()

    def test_no_returns_false(self):
        """输入 n → False。"""
        from src.python.tui.handlers_report import _prompt_force_llm

        reporter = MagicMock()
        with patch("builtins.input", return_value="n"):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)
        reporter.ok.assert_not_called()

    def test_empty_input_returns_false(self):
        """空回车 → False。"""
        from src.python.tui.handlers_report import _prompt_force_llm

        reporter = MagicMock()
        with patch("builtins.input", return_value=""):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)

    def test_eof_error_returns_false(self):
        """EOFError → False，不崩溃。"""
        from src.python.tui.handlers_report import _prompt_force_llm

        reporter = MagicMock()
        with patch("builtins.input", side_effect=EOFError):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)

    def test_keyboard_interrupt_returns_false(self):
        """KeyboardInterrupt → False，不崩溃。"""
        from src.python.tui.handlers_report import _prompt_force_llm

        reporter = MagicMock()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _prompt_force_llm(reporter)
        self.assertFalse(result)

    def test_uppercase_y(self):
        """大写 Y 也视为 yes。"""
        from src.python.tui.handlers_report import _prompt_force_llm

        reporter = MagicMock()
        with patch("builtins.input", return_value="Y"):
            result = _prompt_force_llm(reporter)
        self.assertTrue(result)

    def test_whitespace_y(self):
        """y 带前后空格仍视为 yes。"""
        from src.python.tui.handlers_report import _prompt_force_llm

        reporter = MagicMock()
        with patch("builtins.input", return_value="  y  "):
            result = _prompt_force_llm(reporter)
        self.assertTrue(result)


@pytest.mark.unit_core
class TestPromptHistory(unittest.TestCase):
    """_prompt_history 历史走势获取决定（读 history.fetch_mode 三态）。"""

    def _config(self, mode: str) -> dict:
        return {"history": {"fetch_mode": mode}}

    def test_auto_returns_true(self):
        """fetch_mode=auto → True（自动获取，不询问）。"""
        from src.python.tui.handlers_report import _prompt_history

        reporter = MagicMock()
        with (
            patch("src.python.tui.handlers_report.get_config_cache", return_value=self._config("auto")),
            patch("src.python.config.is_enable_history", return_value=True),
        ):
            result = _prompt_history(reporter)
        self.assertTrue(result)

    def test_off_returns_false(self):
        """fetch_mode=off → False（不获取，不询问）。"""
        from src.python.tui.handlers_report import _prompt_history

        reporter = MagicMock()
        with (
            patch("src.python.tui.handlers_report.get_config_cache", return_value=self._config("off")),
            patch("src.python.config.is_enable_history", return_value=True),
        ):
            result = _prompt_history(reporter)
        self.assertFalse(result)

    def test_enable_history_false_returns_false(self):
        """enable_history 关闭 → False（总闸优先）。"""
        from src.python.tui.handlers_report import _prompt_history

        reporter = MagicMock()
        with (
            patch("src.python.tui.handlers_report.get_config_cache", return_value=self._config("auto")),
            patch("src.python.config.is_enable_history", return_value=False),
        ):
            result = _prompt_history(reporter)
        self.assertFalse(result)

    def test_prompt_yes_returns_true(self):
        """fetch_mode=prompt 且用户答 y → True。"""
        from src.python.tui.handlers_report import _prompt_history

        reporter = MagicMock()
        with (
            patch("src.python.tui.handlers_report.get_config_cache", return_value=self._config("prompt")),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("builtins.input", return_value="y"),
        ):
            result = _prompt_history(reporter)
        self.assertTrue(result)

    def test_prompt_no_returns_false(self):
        """fetch_mode=prompt 且用户答 n → False。"""
        from src.python.tui.handlers_report import _prompt_history

        reporter = MagicMock()
        with (
            patch("src.python.tui.handlers_report.get_config_cache", return_value=self._config("prompt")),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("builtins.input", return_value="n"),
        ):
            result = _prompt_history(reporter)
        self.assertFalse(result)

    def test_prompt_eof_returns_false(self):
        """fetch_mode=prompt 且 EOFError → False，不崩溃。"""
        from src.python.tui.handlers_report import _prompt_history

        reporter = MagicMock()
        with (
            patch("src.python.tui.handlers_report.get_config_cache", return_value=self._config("prompt")),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("builtins.input", side_effect=EOFError),
        ):
            result = _prompt_history(reporter)
        self.assertFalse(result)

    def test_missing_fetch_mode_defaults_auto(self):
        """fetch_mode 缺失时默认 auto → True。"""
        from src.python.tui.handlers_report import _prompt_history

        reporter = MagicMock()
        with (
            patch("src.python.tui.handlers_report.get_config_cache", return_value={}),
            patch("src.python.config.is_enable_history", return_value=True),
        ):
            result = _prompt_history(reporter)
        self.assertTrue(result)
