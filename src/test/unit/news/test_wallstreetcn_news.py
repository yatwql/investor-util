"""华尔街见闻 news provider 单元测试。

测试目标：
  - _ts_to_str — 时间戳转换（北京时间）
  - _parse_news_item — 纯函数，JSON 条目解析（含 HTML 剥离、标题回退）
  - fetch_news — HTTP 请求、错误处理、空数据、limit 上限

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_wallstreetcn_news.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.providers.wallstreetcn_news import (

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
            "title": "新闻标题", "content_text": "正文内容",
            "display_time": "1782873000", "uri": "/live/12345",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["title"], "新闻标题")
        self.assertEqual(result["intro"], "正文内容")
        self.assertEqual(
            result["url"], "https://wallstreetcn.com/live/12345",
        )
        self.assertEqual(result["ctime"], "2026-07-01 10:30")
        self.assertEqual(result["media_name"], "华尔街见闻")

    def test_missing_title_falls_back_to_content(self):
        """缺少 title → 使用 content_text 前 40 字。"""
        content = "测试正文" * 20  # 80 chars
        item = {
            "content_text": content, "display_time": "0", "uri": "/live/1",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["title"], ("测试正文" * 10) + "…")

    def test_short_content_no_ellipsis(self):
        """content_text 不超过 40 字 → 不加 …。"""
        item = {
            "content_text": "短内容", "display_time": "0", "uri": "/live/1",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["title"], "短内容")

    def test_missing_title_and_content_returns_none(self):
        """缺少 title 和 content_text → None。"""
        self.assertIsNone(_parse_news_item({}))
        self.assertIsNone(_parse_news_item({"content_text": ""}))
        self.assertIsNone(_parse_news_item({"content_text": "  "}))

    def test_html_tags_stripped_from_intro(self):
        """intro 剥离 HTML 标签。"""
        item = {
            "title": "标题", "content_text": "<p>正文<b>强调</b></p>",
            "display_time": "0",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["intro"], "正文强调")

    def test_intro_truncated_at_300_chars(self):
        """intro 超过 300 字 → 截断加 …。"""
        long_text = "内容" * 200  # 400 chars
        item = {
            "title": "标题", "content_text": long_text, "display_time": "0",
        }
        result = _parse_news_item(item)
        self.assertLessEqual(len(result["intro"]), 301)  # 300 + "…"
        self.assertTrue(result["intro"].endswith("…"))

    def test_uri_relative_becomes_absolute(self):
        """相对路径 uri → 拼接完整 URL。"""
        item = {
            "title": "标题", "uri": "/live/abc", "display_time": "0",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["url"], "https://wallstreetcn.com/live/abc")

    def test_uri_absolute_kept_as_is(self):
        """绝对路径 uri → 保持原样。"""
        item = {
            "title": "标题", "uri": "https://example.com/page",
            "display_time": "0",
        }
        result = _parse_news_item(item)
        self.assertEqual(result["url"], "https://example.com/page")

    def test_missing_uri_returns_empty_url(self):
        """缺少 uri → url 为空。"""
        item = {"title": "标题", "display_time": "0"}
        result = _parse_news_item(item)
        self.assertEqual(result["url"], "")

    def test_empty_uri_returns_empty_url(self):
        """空 uri → url 为空。"""
        item = {"title": "标题", "uri": "", "display_time": "0"}
        result = _parse_news_item(item)
        self.assertEqual(result["url"], "")

    def test_invalid_display_time(self):
        """display_time 非数字 → ctime 为空。"""
        item = {"title": "标题", "display_time": "not-a-number"}
        result = _parse_news_item(item)
        self.assertEqual(result["ctime"], "")

    def test_missing_display_time(self):
        """缺少 display_time → ctime 为空。"""
        item = {"title": "标题"}
        result = _parse_news_item(item)
        self.assertEqual(result["ctime"], "")

    def test_media_name_is_hardcoded(self):
        """media_name 固定为"华尔街见闻"。"""
        result = _parse_news_item({"title": "标题", "display_time": "0"})
        self.assertEqual(result["media_name"], "华尔街见闻")


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

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_success(self, mock_factory):
        """正常返回 → 正确解析新闻列表。"""
        mock_resp = self._mock_response({
            "data": {"items": [
                {"title": "新闻1", "content_text": "内容1",
                 "display_time": "1782873000", "uri": "/live/1"},
                {"title": "新闻2", "content_text": "内容2",
                 "display_time": "1782873060", "uri": "/live/2"},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)

        result = fetch_news(num=10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "新闻1")
        self.assertEqual(result[0]["ctime"], "2026-07-01 10:30")

    # ── 空数据 ───────────────────────────────────────────

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_empty_items(self, mock_factory):
        """API 返回空 items → 空列表。"""
        mock_resp = self._mock_response({"data": {"items": []}})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(), [])

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_missing_data_field(self, mock_factory):
        """API 缺少 data 字段 → 空列表。"""
        mock_resp = self._mock_response({})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(), [])

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_data_has_no_items(self, mock_factory):
        """data 对象无 items → 空列表。"""
        mock_resp = self._mock_response({"data": {"other": "value"}})
        self._setup_mock(mock_factory, mock_resp)
        self.assertEqual(fetch_news(), [])

    # ── HTTP/网络异常 ─────────────────────────────────────

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_timeout_returns_empty(self, mock_factory):
        """超时 → 空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        self.assertEqual(fetch_news(), [])

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_request_error_returns_empty(self, mock_factory):
        """网络错误 → 空列表。"""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("err")
        self.assertEqual(fetch_news(), [])

    # ── JSON 解析异常 ────────────────────────────────────

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_json_parse_error_returns_empty(self, mock_factory):
        """JSON 解析异常 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("bad json")
        mock_client.get.return_value = mock_response
        self.assertEqual(fetch_news(), [])

    # ── limit 上限 ────────────────────────────────────────

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_limit_capped_at_100(self, mock_factory):
        """num 超过 100 → limit 限制为 100。"""
        mock_resp = self._mock_response({"data": {"items": []}})
        mock_client = self._setup_mock(mock_factory, mock_resp)

        fetch_news(num=200)

        call_kwargs = mock_client.get.call_args[1]
        self.assertEqual(call_kwargs["params"]["limit"], 100)

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_limit_under_100_passed_through(self, mock_factory):
        """num 不超过 100 → limit 原值传递。"""
        mock_resp = self._mock_response({"data": {"items": []}})
        mock_client = self._setup_mock(mock_factory, mock_resp)

        fetch_news(num=50)

        call_kwargs = mock_client.get.call_args[1]
        self.assertEqual(call_kwargs["params"]["limit"], 50)

    # ── 无效条目过滤 ─────────────────────────────────────

    @patch("src.python.providers.wallstreetcn_news.make_http_client")
    def test_invalid_items_skipped(self, mock_factory):
        """列表中含无效条目 → 跳过（无标题且无内容）。"""
        mock_resp = self._mock_response({
            "data": {"items": [
                {"title": "有效", "content_text": "内容",
                 "display_time": "0"},
                {},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)
        result = fetch_news(num=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "有效")
