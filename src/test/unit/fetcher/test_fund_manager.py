"""fetcher/fund_manager.py 单元测试。

测试目标：
  - parse_manager_from_html：从 mock HTML 中正确提取经理信息
  - fetch_fund_manager：缓存+HTTP 请求+回退逻辑
  - _parse_manager_from_archive_page：档案页回退解析

场景覆盖：
  1. infoOfFund 表格解析（标准桌面版页面）
  2. 页面文本回退搜索（无 infoOfFund 表格的简化页面）
  3. 两位经理（"/"分隔）
  4. 解析失败返回 None
  5. HTTP 超时
  6. 档案页回退
  7. 缓存命中/未命中

运行：
  pytest src/test/ -m "unit_fetcher" -k "fund_manager" -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.fetcher.fund_manager import (
    _parse_manager_from_archive_page,
    fetch_fund_manager,
    parse_manager_from_html,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

# ── HTML Fixtures ────────────────────────────────────────────────

_HTML_INFOOFUND = """<!DOCTYPE html>
<html><head></head><body>
<div class="infoOfFund">
    <table>
        <tr><td>基金代码</td><td>110011</td></tr>
        <tr><td>基金经理</td><td><a href="/manager/123.html">张坤</a><br>任职起始日：2012-09-28</td></tr>
        <tr><td>历任基金经理</td><td><a href="/manager/456.html">张三</a>（2010-01-01）<br><a href="/manager/789.html">李四</a>（2008-06-15）</td></tr>
    </table>
</div>
</body></html>
"""

_HTML_TWO_MANAGERS = """<!DOCTYPE html>
<html><head></head><body>
<div class="infoOfFund">
    <table>
        <tr><td>基金经理</td><td><a href="/manager/1.html">王浩</a>&nbsp;<a href="/manager/2.html">陈晨</a><br>任职起始日：2024-03-15</td></tr>
    </table>
</div>
</body></html>
"""

_HTML_NO_TABLE = """<!DOCTYPE html>
<html><head></head><body>
<div class="fundDetail">
    <p>基金经理：刘彦春</p>
    <p>其他信息...</p>
</div>
</body></html>
"""

_HTML_NO_MANAGER = """<!DOCTYPE html>
<html><head></head><body>
<div class="infoOfFund">
    <table>
        <tr><td>基金代码</td><td>999999</td></tr>
        <tr><td>基金类型</td><td>货币型</td></tr>
    </table>
</div>
</body></html>
"""

_HTML_MOBILE_STYLE = """<!DOCTYPE html>
<html><head></head><body>
<div class="fundDetail">
    <span>基金经理</span>
    <span><a href="/manager/5.html">葛兰</a></span>
    <span>任职起始日：2018-07-15</span>
</div>
</body></html>
"""

_HTML_ARCHIVE_PAGE = """<!DOCTYPE html>
<html><head></head><body>
<table class="table">
    <tr><td><a href="#">张坤</a></td><td>2012-09-28</td></tr>
    <tr><td><a href="#">张三</a></td><td>2010-01-01 ~ 2012-09-27</td></tr>
    <tr><td><a href="#">李四</a></td><td>2008-06-15 ~ 2010-01-01</td></tr>
</table>
</body></html>
"""


# ── parse_manager_from_html 测试 ──────────────────────────────


class TestParseManagerFromHtml(unittest.TestCase):
    """parse_manager_from_html：纯解析函数测试"""

    def test_parse_from_infooffund(self):
        """从 infoOfFund 表格中正确提取经理信息。"""
        result = parse_manager_from_html(_HTML_INFOOFUND)
        self.assertIsNotNone(result)
        self.assertEqual(result["manager_name"], "张坤")
        self.assertEqual(result["start_date"], "2012-09-28")
        self.assertGreater(result["tenure_days"], 0)
        self.assertGreater(len(result["history"]), 0)

    def test_two_managers_separated_by_slash(self):
        """两位基金经理用"/"连接。"""
        result = parse_manager_from_html(_HTML_TWO_MANAGERS)
        self.assertIsNotNone(result)
        self.assertIn("王浩", result["manager_name"])
        self.assertIn("陈晨", result["manager_name"])
        self.assertIn("/", result["manager_name"])
        self.assertEqual(result["start_date"], "2024-03-15")

    def test_parse_no_table_fallback(self):
        """无 infoOfFund 表格时通过全文回退匹配经理。"""
        result = parse_manager_from_html(_HTML_NO_TABLE)
        self.assertIsNotNone(result)
        self.assertEqual(result["manager_name"], "刘彦春")

    def test_no_manager_returns_none(self):
        """页面中无经理信息时返回 None。"""
        result = parse_manager_from_html(_HTML_NO_MANAGER)
        self.assertIsNone(result)

    def test_mobile_style_page(self):
        """移动端简化页面（span 模式）也能正确解析。"""
        result = parse_manager_from_html(_HTML_MOBILE_STYLE)
        self.assertIsNotNone(result)
        self.assertEqual(result["manager_name"], "葛兰")

    def test_empty_html_returns_none(self):
        """空 HTML 返回 None。"""
        self.assertIsNone(parse_manager_from_html(""))
        self.assertIsNone(parse_manager_from_html(None))  # type: ignore[arg-type]

    def test_invalid_html_returns_none(self):
        """无意义 HTML 返回 None。"""
        self.assertIsNone(parse_manager_from_html("<html><body>no data</body></html>"))


# ── fetch_fund_manager 测试 ──────────────────────────────────


class TestFetchFundManager(unittest.TestCase):
    """fetch_fund_manager：缓存+HTTP+回退测试"""

    def setUp(self):
        self.code = "110011"
        self.cache_key = f"fund_manager_{self.code}"

    @patch("src.python.fetcher.fund_manager.cache_get")
    @patch("src.python.fetcher.fund_manager._request_fund_html")
    def test_cache_hit(self, mock_request: MagicMock, mock_cache: MagicMock):
        """缓存命中时直接返回缓存数据，不发起 HTTP。"""
        cached_data = {
            "manager_name": "张坤",
            "start_date": "2012-09-28",
            "tenure_days": 5000,
            "history": [],
        }
        mock_cache.return_value = cached_data

        result = fetch_fund_manager(self.code)

        self.assertEqual(result, cached_data)
        mock_request.assert_not_called()

    @patch("src.python.fetcher.fund_manager.cache_get")
    @patch("src.python.fetcher.fund_manager._request_fund_html")
    @patch("src.python.fetcher.fund_manager.cache_set")
    def test_cache_miss_html_success(
        self, mock_set: MagicMock, mock_request: MagicMock, mock_cache: MagicMock,
    ):
        """缓存未命中，HTTP 成功，解析并缓存。"""
        mock_cache.return_value = None
        mock_request.return_value = _HTML_INFOOFUND

        result = fetch_fund_manager(self.code)

        self.assertIsNotNone(result)
        self.assertEqual(result["manager_name"], "张坤")
        mock_set.assert_called_once()

    @patch("src.python.fetcher.fund_manager.cache_get")
    @patch("src.python.fetcher.fund_manager._request_fund_html")
    @patch("src.python.fetcher.fund_manager._parse_manager_from_archive_page")
    @patch("src.python.fetcher.fund_manager.cache_set")
    def test_html_failed_archive_fallback(
        self, mock_set: MagicMock, mock_archive: MagicMock,
        mock_request: MagicMock, mock_cache: MagicMock,
    ):
        """主页请求失败时回退到档案页。"""
        mock_cache.return_value = None
        mock_request.return_value = None
        mock_archive.return_value = {
            "manager_name": "张坤",
            "start_date": "2012-09-28",
            "tenure_days": 5000,
            "history": [],
        }

        result = fetch_fund_manager(self.code)

        self.assertIsNotNone(result)
        self.assertEqual(result["manager_name"], "张坤")
        mock_archive.assert_called_once_with(self.code)
        mock_set.assert_called_once()

    @patch("src.python.fetcher.fund_manager.cache_get")
    @patch("src.python.fetcher.fund_manager._request_fund_html")
    @patch("src.python.fetcher.fund_manager._parse_manager_from_archive_page")
    def test_all_failed_returns_none(
        self, mock_archive: MagicMock, mock_request: MagicMock, mock_cache: MagicMock,
    ):
        """主页和档案页均失败时返回 None。"""
        mock_cache.return_value = None
        mock_request.return_value = None  # 主页请求失败
        mock_archive.return_value = None  # 档案页也失败

        result = fetch_fund_manager(self.code)

        self.assertIsNone(result)

    @patch("src.python.fetcher.fund_manager.cache_get")
    @patch("src.python.fetcher.fund_manager._request_fund_html")
    @patch("src.python.fetcher.fund_manager._parse_manager_from_archive_page")
    @patch("src.python.fetcher.fund_manager.cache_set")
    def test_archive_fallback(
        self, mock_set: MagicMock, mock_archive: MagicMock,
        mock_request: MagicMock, mock_cache: MagicMock,
    ):
        """主页 HTML 无经理信息时回退到档案页。"""
        mock_cache.return_value = None
        mock_request.return_value = _HTML_NO_MANAGER  # 主页无经理信息
        mock_archive.return_value = {
            "manager_name": "张坤",
            "start_date": "2012-09-28",
            "tenure_days": 5000,
            "history": [],
        }

        result = fetch_fund_manager(self.code)

        self.assertIsNotNone(result)
        self.assertEqual(result["manager_name"], "张坤")
        mock_archive.assert_called_once_with(self.code)


# ── _parse_manager_from_archive_page 测试 ──────────────────


class TestParseManagerFromArchivePage(unittest.TestCase):
    """_parse_manager_from_archive_page：档案页解析测试"""

    @patch("src.python.fetcher.fund_manager.make_http_client")
    def test_parse_archive_success(self, mock_client: MagicMock):
        """从档案页正确解析当前经理和历任经理。"""
        mock_resp = MagicMock()
        mock_resp.text = _HTML_ARCHIVE_PAGE
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_ctx
        mock_ctx.get.return_value = mock_resp
        mock_client.return_value = mock_ctx

        result = _parse_manager_from_archive_page("110011")

        self.assertIsNotNone(result)
        self.assertEqual(result["manager_name"], "张坤")
        self.assertEqual(result["start_date"], "2012-09-28")
        self.assertGreater(result["tenure_days"], 0)
        self.assertEqual(len(result["history"]), 2)

    @patch("src.python.fetcher.fund_manager.make_http_client")
    def test_archive_http_failure(self, mock_client: MagicMock):
        """档案页 HTTP 请求失败时返回 None。"""
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_ctx
        import httpx
        mock_ctx.get.side_effect = httpx.TimeoutException("timeout", request=MagicMock())
        mock_client.return_value = mock_ctx

        result = _parse_manager_from_archive_page("110011")
        self.assertIsNone(result)
