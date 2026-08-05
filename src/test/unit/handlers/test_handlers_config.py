"""测试 handlers_config 的 LLM 设置读写辅助函数。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestReadLlmSettings:
    """_read_llm_settings: JSON 注释支持 + 文件不存在处理。"""

    @patch("src.python.config._strip_json_comments")
    @patch("src.python.tui.handlers_config.open")
    @patch("src.python.tui.handlers_config.json.loads")
    def test_normal_read(self, mock_json_loads, mock_open, mock_strip):
        """正常读取带注释的 JSON。"""
        mock_strip.return_value = '{"enabled_llm": {"news_correlation": true}}'
        mock_json_loads.return_value = {"enabled_llm": {"news_correlation": True}}
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "raw content"
        mock_open.return_value = mock_file

        from src.python.tui.handlers_config import _read_llm_settings

        result = _read_llm_settings()
        assert result is not None
        settings, path = result
        assert settings["enabled_llm"]["news_correlation"] is True
        assert "llm_settings.json" in path

    @patch("src.python.tui.handlers_config.open", side_effect=FileNotFoundError)
    @patch("src.python.tui.handlers_config.press_any_key")
    def test_file_not_found(self, mock_press, mock_open):
        """文件不存在时返回 None。"""
        from src.python.tui.handlers_config import _read_llm_settings

        result = _read_llm_settings()
        assert result is None

    @patch("src.python.config._strip_json_comments")
    @patch("src.python.tui.handlers_config.open")
    @patch("src.python.tui.handlers_config.json.loads", side_effect=json.JSONDecodeError("x", "", 1))
    @patch("src.python.tui.handlers_config.press_any_key")
    def test_json_decode_error(self, mock_press, mock_json_loads, mock_open, mock_strip):
        """JSON 解析错误时返回 None。"""
        mock_strip.return_value = "bad json"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "bad json"
        mock_open.return_value = mock_file

        from src.python.tui.handlers_config import _read_llm_settings

        result = _read_llm_settings()
        assert result is None


class TestWriteLlmSettings:
    """_write_llm_settings: 写入 JSON + 刷新 LLM 配置缓存。"""

    @patch("src.python.tui.handlers_config.os.replace")
    @patch("src.python.tui.handlers_config.os.fdopen")
    @patch("src.python.tui.handlers_config.tempfile.mkstemp", return_value=(7, "/fake/path/llm_settings.json.tmp"))
    @patch("src.python.tui.handlers_config.os.makedirs")
    @patch("src.python.config.get_llm_config")
    @patch("src.python.tui.handlers_config.json.dump")
    @patch("src.python.tui.handlers_config.open")
    def test_write_settings(
        self, mock_open, mock_json_dump, mock_get_llm, mock_makedirs, mock_mkstemp, mock_fdopen, mock_replace
    ):
        """正确写入并刷新配置（fs 写路径全 mock，避免依赖 /fake 目录可写权限）。"""
        from src.python.tui.handlers_config import _write_llm_settings

        settings = {"enabled_llm": {"news_correlation": True}}
        path = "/fake/path/llm_settings.json"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = ""
        mock_open.return_value = mock_file

        _write_llm_settings(settings, path)
        mock_makedirs.assert_called_once()
        mock_mkstemp.assert_called_once()
        mock_replace.assert_called_once()
        mock_json_dump.assert_called_once()
        mock_get_llm.assert_called_once()
