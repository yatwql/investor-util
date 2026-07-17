"""测试 handlers_cache / handlers_config / handlers_report 辅助函数。

覆盖范围：
- handlers_cache: _print_cache_refresh_report, _refresh_one_fund_cache,
                  _refresh_profit_forecast_cache, _refresh_sector_flow_cache
- handlers_config: _read_llm_settings, _write_llm_settings
- handlers_report: _prompt_force_llm
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from io import StringIO
from unittest.mock import MagicMock, patch, ANY
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_ui]




# ═══════════════════════════════════════════════════════════════
#  handlers_config 测试
# ═══════════════════════════════════════════════════════════════


class TestReadLlmSettings:
    """_read_llm_settings: JSON 注释支持 + 文件不存在处理。"""

    @patch("src.python.config._strip_json_comments")
    @patch("src.python.handlers_config.open")
    @patch("src.python.handlers_config.json.loads")
    def test_normal_read(self, mock_json_loads, mock_open, mock_strip):
        """正常读取带注释的 JSON。"""
        mock_strip.return_value = '{"enabled_llm": {"news_correlation": true}}'
        mock_json_loads.return_value = {"enabled_llm": {"news_correlation": True}}
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "raw content"
        mock_open.return_value = mock_file

        from src.python.handlers_config import _read_llm_settings

        result = _read_llm_settings()
        assert result is not None
        settings, path = result
        assert settings["enabled_llm"]["news_correlation"] is True
        assert "llm_settings.json" in path

    @patch("src.python.handlers_config.open", side_effect=FileNotFoundError)
    @patch("src.python.handlers_config.press_any_key")
    def test_file_not_found(self, mock_press, mock_open):
        """文件不存在时返回 None。"""
        from src.python.handlers_config import _read_llm_settings
        result = _read_llm_settings()
        assert result is None

    @patch("src.python.config._strip_json_comments")
    @patch("src.python.handlers_config.open")
    @patch("src.python.handlers_config.json.loads", side_effect=json.JSONDecodeError("x", "", 1))
    @patch("src.python.handlers_config.press_any_key")
    def test_json_decode_error(self, mock_press, mock_json_loads, mock_open, mock_strip):
        """JSON 解析错误时返回 None。"""
        mock_strip.return_value = "bad json"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "bad json"
        mock_open.return_value = mock_file

        from src.python.handlers_config import _read_llm_settings
        result = _read_llm_settings()
        assert result is None


class TestWriteLlmSettings:
    """_write_llm_settings: 写入 JSON + 刷新 LLM 配置缓存。"""

    @patch("src.python.config.get_llm_config")
    @patch("src.python.handlers_config.json.dump")
    @patch("src.python.handlers_config.open")
    def test_write_settings(self, mock_open, mock_json_dump, mock_get_llm):
        """正确写入并刷新配置。"""
        from src.python.handlers_config import _write_llm_settings

        settings = {"enabled_llm": {"news_correlation": True}}
        path = "/fake/path/llm_settings.json"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = ""
        mock_open.return_value = mock_file

        _write_llm_settings(settings, path)
        mock_json_dump.assert_called_once()
        mock_get_llm.assert_called_once()


# ═══════════════════════════════════════════════════════════════
#  handlers_cache 测试
# ═══════════════════════════════════════════════════════════════


class TestPrintCacheRefreshReport:
    """_print_cache_refresh_report 输出格式（CacheUpdateResult 版）。"""

    def _make_result(self, **kwargs):
        from src.python.cache.operations import CacheUpdateResult
        return CacheUpdateResult(**kwargs)

    def _call(self, result):
        from src.python.handlers_cache import _print_cache_refresh_report
        captured = StringIO()
        with patch.object(sys, "stdout", captured):
            _print_cache_refresh_report(result)
        return captured.getvalue()

    def test_all_success(self):
        """全部成功时输出 [OK] 标签。"""
        result = self._make_result(
            total_funds=5, perf_ok=5, hold_ok=5, bm_ok=5,
            pf_ok=100, sf_ok=30,
        )
        output = self._call(result)
        assert "全部成功" in output or "[OK]" in output
        assert "100 只股票" in output
        assert "30 个行业" in output

    def test_partial_failure(self):
        """部分失败时输出 [!] 标签。"""
        result = self._make_result(
            total_funds=5, perf_ok=3, hold_ok=4, bm_ok=5,
            pf_ok=0, sf_ok=0,
        )
        output = self._call(result)
        assert "失败" in output or "[!]" in output

    def test_empty_funds(self):
        """没有基金时跳过基金输出。"""
        result = self._make_result(
            total_funds=0, perf_ok=0, hold_ok=0, bm_ok=0,
            pf_ok=50, sf_ok=10,
        )
        output = self._call(result)
        assert "50 只股票" in output
        assert "10 个行业" in output


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


class TestRefreshProfitForecast:
    """_refresh_profit_forecast_cache: 盈利预测缓存刷新（operations 版）。"""

    @patch("src.python.providers.akshare_extras._memo_clear")
    @patch("src.python.providers.akshare_extras.get_profit_forecast")
    def test_success(self, mock_get, mock_clear):
        """成功返回覆盖股票数。"""
        mock_get.return_value = {"600519": {}, "000001": {}}
        from src.python.cache.operations import _refresh_profit_forecast_cache

        count = _refresh_profit_forecast_cache()
        assert count == ("profit_forecast", 2)

    @patch("src.python.providers.akshare_extras._memo_clear")
    @patch("src.python.providers.akshare_extras.get_profit_forecast", return_value=None)
    def test_failure(self, mock_get, mock_clear):
        """失败返回 ('profit_forecast', 0)。"""
        from src.python.cache.operations import _refresh_profit_forecast_cache

        count = _refresh_profit_forecast_cache()
        assert count == ("profit_forecast", 0)


class TestRefreshSectorFlow:
    """_refresh_sector_flow_cache: 行业资金流向缓存刷新（operations 版）。"""

    @patch("src.python.providers.akshare_extras.get_sector_fund_flow")
    def test_success(self, mock_get):
        """成功返回行业数。"""
        mock_get.return_value = {"银行": {}, "地产": {}}
        from src.python.cache.operations import _refresh_sector_flow_cache

        count = _refresh_sector_flow_cache()
        assert count == ("sector_flow", 2)

    @patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=None)
    def test_failure(self, mock_get):
        """失败返回 ('sector_flow', 0)。"""
        from src.python.cache.operations import _refresh_sector_flow_cache

        count = _refresh_sector_flow_cache()
        assert count == ("sector_flow", 0)


# ═══════════════════════════════════════════════════════════════
#  handlers_report 测试
# ═══════════════════════════════════════════════════════════════




class TestPromptForceLlm:
    """_prompt_force_llm: 用户选择是否强制刷新 LLM。"""

    @patch("src.python.handlers_report.input", return_value="y")
    def test_force_yes(self, mock_input):
        """输入 y 返回 True。"""
        from src.python.handlers_report import _prompt_force_llm
        reporter = MagicMock()
        result = _prompt_force_llm(reporter)
        assert result is True
        reporter.ok.assert_called_once()

    @patch("src.python.handlers_report.input", return_value="n")
    def test_force_no(self, mock_input):
        """输入 n 返回 False。"""
        from src.python.handlers_report import _prompt_force_llm
        result = _prompt_force_llm(MagicMock())
        assert result is False

    @patch("src.python.handlers_report.input", side_effect=EOFError)
    def test_eof(self, mock_input):
        """EOFError 时返回 False。"""
        from src.python.handlers_report import _prompt_force_llm

        result = _prompt_force_llm(MagicMock())
        assert result is False
