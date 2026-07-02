"""东方财富新闻 provider 单元测试。

测试目标：
  - _parse_news_item — 纯函数，JSON 条目解析
  - fetch_news — HTTP 请求、错误处理、空数据

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_eastmoney_news.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.providers.eastmoney_news import (

    _parse_news_item,
    fetch_news,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_news]


class TestParseNewsItem(unittest.TestCase):
    """_parse_news_item 纯函数测试。"""

    def test_normal_item(self):
        """正常条目 → 正确解析所有字段。"""
        item = {
            "title": "快讯标题",
            "code": "20260701123456",
            "summary": "摘要内容",
            "showTime": "2026-07-01 10:30",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["title"], "快讯标题")
        self.assertEqual(result["intro"], "摘要内容")
        self.assertEqual(
            result["url"],
            "https://finance.eastmoney.com/a/20260701123456.html",
        )
        self.assertEqual(result["ctime"], "2026-07-01 10:30")
        self.assertEqual(result["media_name"], "东方财富")

    def test_empty_title_returns_none(self):
        """空标题 → None。"""
        self.assertIsNone(_parse_news_item({"title": ""}))
        self.assertIsNone(_parse_news_item({"title": "  "}))

    def test_missing_title_returns_none(self):
        """缺少 title → None。"""
        self.assertIsNone(_parse_news_item({}))

    def test_empty_code_returns_empty_url(self):
        """空 code → url 为空字符串。"""
        result = _parse_news_item({"title": "标题", "code": ""})
        self.assertEqual(result["url"], "")

    def test_missing_code_returns_empty_url(self):
        """缺少 code → url 为空字符串。"""
        result = _parse_news_item({"title": "标题"})
        self.assertEqual(result["url"], "")

    def test_missing_summary(self):
        """缺少 summary → intro 为空字符串。"""
        result = _parse_news_item({"title": "标题", "code": "123"})
        self.assertEqual(result["intro"], "")

    def test_missing_show_time(self):
        """缺少 showTime → ctime 为空字符串。"""
        result = _parse_news_item({"title": "标题", "code": "123"})
        self.assertEqual(result["ctime"], "")

    def test_whitespace_stripped(self):
        """字段值去除前后空格。"""
        result = _parse_news_item({
            "title": "  标题  ", "code": "  123  ",
            "summary": "  摘要  ", "showTime": "  2026-07-01  ",
        })
        self.assertEqual(result["title"], "标题")
        self.assertEqual(result["intro"], "摘要")
        self.assertEqual(result["ctime"], "2026-07-01")

    def test_media_name_is_hardcoded(self):
        """media_name 固定为"东方财富"。"""
        result = _parse_news_item({"title": "标题", "code": "123"})
        self.assertEqual(result["media_name"], "东方财富")


class TestFetchNews(unittest.TestCase):
    """fetch_news HTTP 集成测试。"""

    def _mock_response(self, json_data: dict | None = None,
                       status_code: int = 200):
        """创建模拟 httpx.Response。"""
        import httpx
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        if status_code >= 400:
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"{status_code} error", request=MagicMock(), response=resp,
            )
        else:
            resp.raise_for_status.return_value = None
        return resp

    def _setup_mock(self, mock_factory: MagicMock,
                    mock_response: MagicMock) -> MagicMock:
        """配置 mock make_http_client 返回 mock client。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.return_value = mock_response
        return mock_client

    # ── 正常路径 ──────────────────────────────────────────

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_success(self, mock_factory):
        """正常返回 → 正确解析新闻列表。"""
        mock_resp = self._mock_response({
            "data": {"fastNewsList": [
                {"title": "新闻1", "code": "c001",
                 "summary": "摘要1", "showTime": "2026-07-01 10:00"},
                {"title": "新闻2", "code": "c002",
                 "summary": "摘要2", "showTime": "2026-07-01 10:01"},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)

        result = fetch_news(num=10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "新闻1")
        self.assertEqual(result[1]["title"], "新闻2")

    # ── 空数据 ───────────────────────────────────────────

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_empty_fast_news_list(self, mock_factory):
        """API 返回空 fastNewsList → 空列表。"""
        mock_resp = self._mock_response({"data": {"fastNewsList": []}})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_missing_data_field(self, mock_factory):
        """API 返回无 data 字段 → 空列表。"""
        mock_resp = self._mock_response({})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_empty_data_object(self, mock_factory):
        """API 返回 data 为 None → 空列表。"""
        mock_resp = self._mock_response({"data": None})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(num=10), [])

    # ── HTTP/网络异常 ─────────────────────────────────────

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_timeout_returns_empty_list(self, mock_factory):
        """超时异常 → 返回空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_request_error_returns_empty_list(self, mock_factory):
        """网络请求异常 → 返回空列表。"""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("network error")

        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_http_status_error_returns_empty_list(self, mock_factory):
        """HTTP 状态码异常 → 返回空列表。"""
        mock_resp = self._mock_response({}, status_code=500)
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(num=10), [])

    # ── JSON 解析异常 ────────────────────────────────────

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_json_parse_error_returns_empty_list(self, mock_factory):
        """非 JSON 响应 → 返回空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("not json")
        mock_client.get.return_value = mock_response

        self.assertEqual(fetch_news(num=10), [])

    # ── 无效条目过滤 ─────────────────────────────────────

    @patch("src.python.providers.eastmoney_news.make_http_client")
    def test_invalid_items_skipped(self, mock_factory):
        """列表中含无效条目 → 跳过空标题。"""
        mock_resp = self._mock_response({
            "data": {"fastNewsList": [
                {"title": "有效", "code": "c001"},
                {"title": "", "code": "c002"},
                {"title": "   ", "code": "c003"},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)

        result = fetch_news(num=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "有效")
