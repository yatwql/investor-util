"""财联社新闻 provider 单元测试。

测试目标：
  - _ts_to_str — 时间戳转换
  - _parse_news_item — 条目解析
  - fetch_news — HTTP 请求、错误处理、数据解析

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_cls_news.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_news]



class TestTsToStr(unittest.TestCase):
    """_ts_to_str 纯函数测试。"""

    def _call(self, ts: int) -> str:
        from src.python.providers.cls_news import _ts_to_str
        return _ts_to_str(ts)

    def test_normal_timestamp(self):
        """正常时间戳 → 格式化为 YYYY-MM-DD HH:MM。"""
        # 2026-07-01 10:30 UTC+8 = 2026-06-30 02:30 UTC
        # 但为了方便，用 2026-07-01 00:00 UTC+8 → 2026-06-30 16:00 UTC
        result = self._call(1769817600)  # 2026-07-01 00:00:00 UTC+8 (approx)
        self.assertIsInstance(result, str)
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

    def test_zero_timestamp(self):
        """时间戳 0 → 1970-01-01 08:00。"""
        result = self._call(0)
        self.assertEqual(result, "1970-01-01 08:00")

    def test_negative_timestamp(self):
        """负数 → 返回一个日期（各平台行为不同），但始终是字符串。"""
        import sys as _sys
        result = self._call(-1)
        self.assertIsInstance(result, str)
        # Windows 上 -1 不抛异常，返回 "1970-01-01 07:59"
        # Unix 上 OSError 被捕获返回 ""
        if _sys.platform == "win32":
            self.assertEqual(result, "1970-01-01 07:59")


class TestParseNewsItem(unittest.TestCase):
    """_parse_news_item 纯函数测试。"""

    def _call(self, item: dict):
        from src.python.providers.cls_news import _parse_news_item
        return _parse_news_item(item)

    def test_normal_item(self):
        """正常条目 → 正确解析所有字段。"""
        item = {
            "title": "快讯标题",
            "shareurl": "https://cls.cn/detail/123",
            "brief": "摘要内容",
            "ctime": 1769817600,
        }
        result = self._call(item)
        self.assertEqual(result["title"], "快讯标题")
        self.assertEqual(result["url"], "https://cls.cn/detail/123")
        self.assertEqual(result["intro"], "摘要内容")
        self.assertEqual(result["media_name"], "财联社")

    def test_empty_title_returns_none(self):
        """空标题 → None。"""
        self.assertIsNone(self._call({"title": ""}))

    def test_missing_title_returns_none(self):
        """缺少 title → None。"""
        self.assertIsNone(self._call({}))

    def test_empty_url_returns_none(self):
        """空 url（无 shareurl 且无 url）→ None。"""
        self.assertIsNone(self._call({"title": "标题"}))

    def test_fallback_url(self):
        """无 shareurl → 使用 url。"""
        result = self._call({"title": "标题", "url": "https://cls.cn/detail/456"})
        self.assertEqual(result["url"], "https://cls.cn/detail/456")

    def test_fallback_intro(self):
        """无 brief → 使用 intro。"""
        result = self._call({"title": "标题", "url": "http://url", "intro": "备选摘要"})
        self.assertEqual(result["intro"], "备选摘要")

    def test_missing_ctime(self):
        """无 ctime → ctime 为空字符串。"""
        result = self._call({"title": "标题", "url": "http://url"})
        self.assertEqual(result["ctime"], "")

    def test_string_ctime_handled(self):
        """字符串类型 ctime → 空字符串（int 转换失败）。"""
        result = self._call({
            "title": "标题", "url": "http://url", "ctime": "invalid",
        })
        self.assertEqual(result["ctime"], "")

    def test_whitespace_stripped(self):
        """字段值去除前后空格。"""
        result = self._call({
            "title": "  标题  ", "shareurl": "  http://url  ",
            "brief": "  摘要  ",
        })
        self.assertEqual(result["title"], "标题")
        self.assertEqual(result["url"], "http://url")
        self.assertEqual(result["intro"], "摘要")


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
        """配置 mock make_http_client。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.return_value = mock_response
        return mock_client

    # ── 正常路径 ──────────────────────────────────────────

    @patch("src.python.providers.cls_news.make_http_client")
    def test_success(self, mock_factory):
        """正常返回 → 正确解析新闻列表。"""
        mock_resp = self._mock_response({
            "data": {"roll_data": [
                {"title": "新闻1", "shareurl": "http://cls.cn/1",
                 "brief": "摘要1", "ctime": 1769817600},
                {"title": "新闻2", "shareurl": "http://cls.cn/2",
                 "brief": "摘要2", "ctime": 1769817600},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)

        from src.python.providers.cls_news import fetch_news
        result = fetch_news(num=10)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "新闻1")

    # ── 空数据 ───────────────────────────────────────────

    @patch("src.python.providers.cls_news.make_http_client")
    def test_empty_roll_data(self, mock_factory):
        """roll_data 为空列表 → 空列表。"""
        mock_resp = self._mock_response({"data": {"roll_data": []}})
        self._setup_mock(mock_factory, mock_resp)
        from src.python.providers.cls_news import fetch_news
        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.cls_news.make_http_client")
    def test_missing_data_field(self, mock_factory):
        """无 data 字段 → 空列表。"""
        mock_resp = self._mock_response({})
        self._setup_mock(mock_factory, mock_resp)
        from src.python.providers.cls_news import fetch_news
        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.cls_news.make_http_client")
    def test_data_not_dict(self, mock_factory):
        """data 字段非 dict → 空列表。"""
        mock_resp = self._mock_response({"data": "not dict"})
        self._setup_mock(mock_factory, mock_resp)
        from src.python.providers.cls_news import fetch_news
        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.cls_news.make_http_client")
    def test_errno_10012(self, mock_factory):
        """errno=10012 签名鉴权错误 → 空列表（不自毁）。"""
        mock_resp = self._mock_response({
            "data": "error", "errno": "10012",
        })
        self._setup_mock(mock_factory, mock_resp)
        from src.python.providers.cls_news import fetch_news
        self.assertEqual(fetch_news(num=10), [])

    # ── HTTP/网络异常 ───────────────────────────────────

    @patch("src.python.providers.cls_news.make_http_client")
    def test_timeout(self, mock_factory):
        """超时 → 空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        from src.python.providers.cls_news import fetch_news
        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.cls_news.make_http_client")
    def test_request_error(self, mock_factory):
        """网络异常 → 空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("network error")
        from src.python.providers.cls_news import fetch_news
        self.assertEqual(fetch_news(num=10), [])

    @patch("src.python.providers.cls_news.make_http_client")
    def test_json_decode_error(self, mock_factory):
        """JSON 解析失败 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("not json")
        mock_client.get.return_value = mock_response
        from src.python.providers.cls_news import fetch_news
        self.assertEqual(fetch_news(num=10), [])

    # ── 无效条目过滤 ────────────────────────────────────

    @patch("src.python.providers.cls_news.make_http_client")
    def test_invalid_items_skipped(self, mock_factory):
        """含无效条目 → 跳过空标题。"""
        mock_resp = self._mock_response({
            "data": {"roll_data": [
                {"title": "有效", "shareurl": "http://cls.cn/1"},
                {"title": "", "shareurl": "http://cls.cn/2"},
                {"title": "有效2", "shareurl": "http://cls.cn/3"},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)
        from src.python.providers.cls_news import fetch_news
        result = fetch_news(num=10)
        self.assertEqual(len(result), 2)

    @patch("src.python.providers.cls_news.make_http_client")
    def test_non_dict_item_skipped(self, mock_factory):
        """非 dict 条目 → 跳过。"""
        mock_resp = self._mock_response({
            "data": {"roll_data": [
                "string_item",
                {"title": "有效", "shareurl": "http://cls.cn/1"},
            ]},
        })
        self._setup_mock(mock_factory, mock_resp)
        from src.python.providers.cls_news import fetch_news

        result = fetch_news(num=10)
        self.assertEqual(len(result), 1)
