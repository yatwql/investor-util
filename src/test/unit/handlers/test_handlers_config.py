"""测试 handlers_config 和 operations 辅助函数。"""

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

    @patch("src.python.config.get_llm_config")
    @patch("src.python.tui.handlers_config.json.dump")
    @patch("src.python.tui.handlers_config.open")
    def test_write_settings(self, mock_open, mock_json_dump, mock_get_llm):
        """正确写入并刷新配置。"""
        from src.python.tui.handlers_config import _write_llm_settings

        settings = {"enabled_llm": {"news_correlation": True}}
        path = "/fake/path/llm_settings.json"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = ""
        mock_open.return_value = mock_file

        _write_llm_settings(settings, path)
        mock_json_dump.assert_called_once()
        mock_get_llm.assert_called_once()


class TestRefreshOneFundCache:
    """_refresh_one_fund_cache 单基金缓存刷新（operations 版）。"""

    def _make_fund(self, code="000001", name="测试基金"):
        f = MagicMock()
        f.code = code
        f.name = name
        return f

    @patch("src.python.fetcher.fund.fetch_fund_benchmark")
    @patch("src.python.fetcher.fund.fetch_fund_holdings")
    @patch("src.python.fetcher.fund.fetch_fund_rankings")
    def test_all_ok(self, mock_perf, mock_hold, mock_bm):
        """全部数据获取成功。"""
        from src.python.cache.operations import _refresh_one_fund_cache

        mock_perf.return_value = {"rank": 1}
        mock_hold.return_value = {"holdings": [{"name": "茅台", "code": "600519"}]}
        mock_bm.return_value = "沪深300"

        result = _refresh_one_fund_cache(self._make_fund())
        assert result[0] == "fund"
        assert result[1] == "000001"
        assert result[3] is True  # perf_ok
        assert result[4] is True  # hold_ok
        assert result[6] is True  # bm_ok

    @patch("src.python.fetcher.fund.fetch_fund_benchmark", return_value="--")
    @patch("src.python.fetcher.fund.fetch_fund_holdings", return_value=None)
    @patch("src.python.fetcher.fund.fetch_fund_rankings", return_value=None)
    def test_all_fail(self, mock_perf, mock_hold, mock_bm):
        """全部数据获取失败。"""
        from src.python.cache.operations import _refresh_one_fund_cache

        result = _refresh_one_fund_cache(self._make_fund())
        assert result[3] is False  # perf_ok
        assert result[4] is False  # hold_ok
        assert result[6] is False  # bm_ok

    @patch("src.python.fetcher.fund.fetch_fund_benchmark", return_value="--")
    @patch("src.python.fetcher.fund.fetch_fund_holdings", return_value=None)
    @patch("src.python.fetcher.fund.fetch_fund_rankings", side_effect=Exception("API err"))
    def test_rankings_raises(self, mock_perf, mock_hold, mock_bm):
        """排名 API 抛出异常时向上传播（函数未捕获该异常）。"""
        from src.python.cache.operations import _refresh_one_fund_cache

        with pytest.raises(Exception, match="API err"):
            _refresh_one_fund_cache(self._make_fund())
