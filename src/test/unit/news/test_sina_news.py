"""新浪新闻 provider 单元测试。

测试目标：
  - _ts_to_str — 时间戳转换（北京时间）
  - _parse_news_item — 纯函数，JSON 条目解析
  - fetch_news — HTTP 请求、错误处理、空数据

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_sina_news.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.providers.sina_news import (

    _ts_to_str,
    _parse_news_item,
    fetch_news,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_news]



class TestTsToStr(unittest.TestCase):
    """_ts_to_str 时间戳转换测试。"""

    def test_normal_timestamp(self):
        """正常时间戳 → 格式化为北京时间。"""
        # 1782873000 = 2026-07-01 02:30:00 UTC = 2026-07-01 10:30 CST
        result = _ts_to_str(1782873000)
        self.assertEqual(result, "2026-07-01 10:30")

    def test_epoch(self):
        """Unix 纪元 → 1970-01-01 08:00。"""
        result = _ts_to_str(0)
        self.assertEqual(result, "1970-01-01 08:00")


class TestParseNewsItem(unittest.TestCase):
    """_parse_news_item 纯函数测试。"""

    def test_normal_item(self):
        """正常条目 → 正确解析所有字段。"""
        item = {
            "title": "新闻标题", "url": "http://example.com/news/1",
            "intro": "简介内容", "ctime": "1782873000", "media_name": "新浪财经",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["title"], "新闻标题")
        self.assertEqual(result["intro"], "简介内容")
        self.assertEqual(result["url"], "http://example.com/news/1")
        self.assertEqual(result["ctime"], "2026-07-01 10:30")
        self.assertEqual(result["media_name"], "新浪财经")

    def test_empty_title_returns_none(self):
        """空标题 → None。"""
        self.assertIsNone(_parse_news_item({"title": "", "url": "http://u"}))
        self.assertIsNone(_parse_news_item({"url": "http://u"}))

    def test_empty_url_returns_none(self):
        """空 url → None。"""
        self.assertIsNone(_parse_news_item({"title": "标题", "url": ""}))
        self.assertIsNone(_parse_news_item({"title": "标题"}))

    def test_missing_intro(self):
        """缺少 intro → 空字符串。"""
        result = _parse_news_item({"title": "标题", "url": "http://u"})
        self.assertEqual(result["intro"], "")

    def test_missing_ctime(self):
        """缺少 ctime → 空字符串。"""
        result = _parse_news_item({"title": "标题", "url": "http://u"})
        self.assertEqual(result["ctime"], "")

    def test_invalid_ctime(self):
        """ctime 非数字 → 空字符串。"""
        item = {"title": "标题", "url": "http://u", "ctime": "not-a-number"}
        result = _parse_news_item(item)
        self.assertEqual(result["ctime"], "")

    def test_missing_media_name(self):
        """缺少 media_name → 空字符串。"""
        result = _parse_news_item({"title": "标题", "url": "http://u"})
        self.assertEqual(result["media_name"], "")

    def test_whitespace_stripped(self):
        """字段值去除前后空格。"""
        item = {"title": "  标题  ", "url": "  http://u  ",
                "intro": "  简介  ", "media_name": "  新浪  "}
        result = _parse_news_item(item)
        self.assertEqual(result["title"], "标题")
        self.assertEqual(result["intro"], "简介")
        self.assertEqual(result["url"], "http://u")
        self.assertEqual(result["media_name"], "新浪")

    def test_ctime_int_conversion(self):
        """ctime 为整数字符串 → 正确转换。"""
        item = {"title": "标题", "url": "http://u", "ctime": "1782873000"}
        result = _parse_news_item(item)
        self.assertEqual(result["ctime"], "2026-07-01 10:30")


class TestFetchNews(unittest.TestCase):
    """fetch_news HTTP 集成测试。"""

    def _mock_response(self, json_data: dict | None = None):
        """创建模拟 httpx.Response（200 OK）。"""
        import httpx
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = json_data or {}
        resp.raise_for_status.return_value = None
        return resp

    def _setup_mock(self, mock_factory: MagicMock,
                    mock_response: MagicMock) -> MagicMock:
        """配置 mock make_http_client。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.return_value = mock_response
        return mock_client

    # ── 正常路径 ──────────────────────────────────────────

    @patch("src.python.providers.sina_news.make_http_client")
    def test_success_with_data(self, mock_factory):
        """正常返回 → 正确解析新闻列表。"""
        mock_resp = self._mock_response({
            "result": {"data": [
                {"title": "新闻1", "url": "http://u1",
                 "ctime": "1782873000", "media_name": "新浪财经"},
                {"title": "新闻2", "url": "http://u2",
                 "ctime": "1782873060", "media_name": "新浪财经"},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)

        result = fetch_news(lid="2516", num=30)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "新闻1")
        self.assertEqual(result[0]["ctime"], "2026-07-01 10:30")

    # ── 空数据 ───────────────────────────────────────────

    @patch("src.python.providers.sina_news.make_http_client")
    def test_empty_data_list(self, mock_factory):
        """API 返回空 data 列表 → 空列表。"""
        mock_resp = self._mock_response({"result": {"data": []}})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(), [])

    @patch("src.python.providers.sina_news.make_http_client")
    def test_missing_result_field(self, mock_factory):
        """API 缺少 result 字段 → 空列表。"""
        mock_resp = self._mock_response({})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(), [])

    @patch("src.python.providers.sina_news.make_http_client")
    def test_result_without_data(self, mock_factory):
        """result 对象无 data 字段 → 空列表。"""
        mock_resp = self._mock_response({"result": {}})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(), [])

    @patch("src.python.providers.sina_news.make_http_client")
    def test_data_is_not_list(self, mock_factory):
        """data 字段非列表 → 空列表。"""
        mock_resp = self._mock_response({"result": {"data": "string"}})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(), [])

    # ── HTTP/网络异常 ─────────────────────────────────────

    @patch("src.python.providers.sina_news.make_http_client")
    def test_timeout_returns_empty(self, mock_factory):
        """超时异常 → 空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        self.assertEqual(fetch_news(), [])

    @patch("src.python.providers.sina_news.make_http_client")
    def test_request_error_returns_empty(self, mock_factory):
        """网络异常 → 空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("err")
        self.assertEqual(fetch_news(), [])

    # ── JSON 解析异常 ────────────────────────────────────

    @patch("src.python.providers.sina_news.make_http_client")
    def test_json_parse_error_returns_empty(self, mock_factory):
        """非 JSON 响应 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("not json")
        mock_client.get.return_value = mock_response
        self.assertEqual(fetch_news(), [])

    # ── 无效条目过滤 ─────────────────────────────────────

    @patch("src.python.providers.sina_news.make_http_client")
    def test_invalid_items_skipped(self, mock_factory):
        """列表中含无效条目 → 跳过空标题和空 URL。"""
        mock_resp = self._mock_response({
            "result": {"data": [
                {"title": "有效", "url": "http://u1"},
                {"title": "", "url": "http://u2"},
                {"title": "无URL", "url": ""},
                {},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)
        result = fetch_news()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "有效")

    # ── 参数传递 ─────────────────────────────────────────

    @patch("src.python.providers.sina_news.make_http_client")
    def test_params_passed_correctly(self, mock_factory):
        """请求参数正确传递。"""
        mock_resp = self._mock_response({"result": {"data": []}})
        mock_client = self._setup_mock(mock_factory, mock_resp)

        fetch_news(lid="2509", num=20, page=2)

        call_kwargs = mock_client.get.call_args[1]
        self.assertEqual(call_kwargs["params"]["lid"], "2509")
        self.assertEqual(call_kwargs["params"]["num"], 20)
        self.assertEqual(call_kwargs["params"]["page"], 2)
