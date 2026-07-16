"""TUI 报告生成命令处理器单元测试。

测试 _prompt_force_llm、_compute_early_warnings 等可独立辅助函数。

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


@pytest.mark.unit_core
class TestComputeEarlyWarnings(unittest.TestCase):
    """_compute_early_warnings 智能预警计算。"""

    def setUp(self):
        self.reporter = MagicMock()
        self.holdings: list = []
        self.assets = [{"name": "腾讯控股", "codes": ["00700"]}]
        self.sector_flow = [{"name": "电力"}]
        self.news_data = [{"title": "test"}]
        self.news_meta: dict = {}

    def _call(self):
        from src.python.report.orchestrator import compute_early_warnings
        return compute_early_warnings(
            self.holdings, self.assets, self.sector_flow,
            self.news_data, self.news_meta, self.reporter,
        )

    @patch("src.python.report.early_warning.compute_early_warnings")
    def test_has_warnings(self, mock_compute):
        """有预警时 reporter.ok 被调用。"""
        mock_compute.return_value = {
            "has_warnings": True,
            "sector_alerts": [{"industry": "电力"}],
            "sentiment_alerts": [{"code": "600900"}],
        }
        result = self._call()
        self.assertIsNotNone(result)
        self.assertTrue(result["has_warnings"])
        self.reporter.ok.assert_called_once()

    @patch("src.python.report.early_warning.compute_early_warnings")
    def test_no_warnings(self, mock_compute):
        """无预警时 reporter.ok 不被调用。"""
        mock_compute.return_value = {
            "has_warnings": False,
            "sector_alerts": [],
            "sentiment_alerts": [],
        }
        result = self._call()
        self.assertIsNotNone(result)
        self.assertFalse(result["has_warnings"])
        self.reporter.ok.assert_not_called()

    @patch("src.python.report.early_warning.compute_early_warnings",
           side_effect=ValueError("test error"))
    def test_exception_returns_none(self, mock_compute):
        """异常时返回 None 且不传播。"""
        result = self._call()
        self.assertIsNone(result)
