"""akshare 新闻 provider 单元测试。

测试目标：
  - _fetch_from_caixin — DataFrame 解析、去重、出界处理
  - _fetch_cctv_news — DataFrame 解析、去重、日期处理
  - fetch_news — 聚合去重、排序、截断

注意：akshare 是延迟导入（import akshare as ak 在函数内部），
因此用 sys.modules mock 而非模块属性 patch。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_akshare_news.py -v
"""

from __future__ import annotations

import builtins
import sys
import unittest
from unittest.mock import MagicMock, patch
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_news]



def _make_df(rows: list[dict]) -> MagicMock:
    """创建一个模拟的 pandas DataFrame，支持 iterrows()。"""
    import pandas as pd
    return pd.DataFrame(rows)


class TestFetchFromCaixin(unittest.TestCase):
    """_fetch_from_caixin 纯函数 + mock akshare 测试。"""

    def _make_akshare_mock(self) -> MagicMock:
        """创建一个 mock akshare 模块。"""
        ak = MagicMock()
        return ak

    # ── akshare 未安装 ──────────────────────────────────────

    def test_akshare_not_installed(self):
        """akshare 未安装 → 返回空列表。"""
        real_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "akshare":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)
        with patch.object(builtins, "__import__", mock_import):
            from src.python.providers.akshare_news import _fetch_from_caixin
            result = _fetch_from_caixin()
            self.assertEqual(result, [])

    # ── API 异常 ────────────────────────────────────────────

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_api_exception(self):
        """akshare API 抛出异常 → 返回空列表。"""
        import akshare
        akshare.stock_news_main_cx.side_effect = Exception("API error")
        from src.python.providers.akshare_news import _fetch_from_caixin
        self.assertEqual(_fetch_from_caixin(), [])

    # ── 空结果 ──────────────────────────────────────────────

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_empty_dataframe(self):
        """空的 DataFrame → 返回空列表。"""
        import akshare
        akshare.stock_news_main_cx.return_value = _make_df([])
        from src.python.providers.akshare_news import _fetch_from_caixin
        self.assertEqual(_fetch_from_caixin(), [])

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_none_dataframe(self):
        """返回 None → 返回空列表。"""
        import akshare
        akshare.stock_news_main_cx.return_value = None
        from src.python.providers.akshare_news import _fetch_from_caixin
        self.assertEqual(_fetch_from_caixin(), [])

    # ── 正常解析 ────────────────────────────────────────────

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_normal_parse(self):
        """正常数据 → 正确解析标题、摘要、URL。"""
        import akshare
        akshare.stock_news_main_cx.return_value = _make_df([
            {"tag": "政策", "summary": "央行发布重要政策调整通知全文", "url": "http://caixin.com/1"},
            {"tag": "", "summary": "股市收盘综述", "url": "http://caixin.com/2"},
        ])
        from src.python.providers.akshare_news import _fetch_from_caixin
        result = _fetch_from_caixin(num=10)
        self.assertEqual(len(result), 2)
        self.assertIn("央行", result[0]["title"])
        self.assertEqual(result[0]["media_name"], "财新网")
        self.assertEqual(result[1]["title"], "股市收盘综述")

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_dedup_by_url(self):
        """相同 URL → 去重。"""
        import akshare
        akshare.stock_news_main_cx.return_value = _make_df([
            {"tag": "A", "summary": "重复新闻", "url": "http://caixin.com/dup"},
            {"tag": "B", "summary": "重复新闻", "url": "http://caixin.com/dup"},
        ])
        from src.python.providers.akshare_news import _fetch_from_caixin
        result = _fetch_from_caixin(num=10)
        self.assertEqual(len(result), 1)

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_max_limit(self):
        """超过 num 条 → 截断。"""
        import akshare
        rows = [{"tag": "", "summary": f"新闻{i}", "url": f"http://caixin.com/{i}"}
                for i in range(10)]
        akshare.stock_news_main_cx.return_value = _make_df(rows)
        from src.python.providers.akshare_news import _fetch_from_caixin
        result = _fetch_from_caixin(num=3)
        self.assertEqual(len(result), 3)

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_no_summary_no_url_skipped(self):
        """无摘要且无URL → 跳过。"""
        import akshare
        akshare.stock_news_main_cx.return_value = _make_df([
            {"tag": "", "summary": "", "url": ""},
            {"tag": "", "summary": "有效新闻", "url": "http://caixin.com/1"},
        ])
        from src.python.providers.akshare_news import _fetch_from_caixin
        result = _fetch_from_caixin(num=10)
        self.assertEqual(len(result), 1)

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_long_summary_truncated(self):
        """超长摘要 → 截断到 300 字。"""
        import akshare
        long_summary = "字" * 500
        akshare.stock_news_main_cx.return_value = _make_df([
            {"tag": "", "summary": long_summary, "url": "http://caixin.com/1"},
        ])
        from src.python.providers.akshare_news import _fetch_from_caixin
        result = _fetch_from_caixin(num=10)
        self.assertLessEqual(len(result[0]["intro"]), 303)  # 300 + "…"


class TestFetchCctvNews(unittest.TestCase):
    """_fetch_cctv_news 纯函数 + mock akshare 测试。"""

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_normal_parse(self):
        """正常数据 → 正确解析标题、内容。"""
        import akshare
        akshare.news_cctv.return_value = _make_df([
            {"title": "央视头条", "content": "今日重要新闻内容"},
        ])
        from src.python.providers.akshare_news import _fetch_cctv_news
        result = _fetch_cctv_news("20260701")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "央视头条")
        self.assertEqual(result[0]["media_name"], "央视新闻")
        self.assertEqual(result[0]["url"], "")

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_empty_title_skipped(self):
        """空标题 → 跳过。"""
        import akshare
        akshare.news_cctv.return_value = _make_df([
            {"title": "", "content": "无标题内容"},
        ])
        from src.python.providers.akshare_news import _fetch_cctv_news
        result = _fetch_cctv_news("20260701")
        self.assertEqual(result, [])

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_api_exception(self):
        """ake 异常 → 返回空列表。"""
        import akshare
        akshare.news_cctv.side_effect = Exception("API error")
        from src.python.providers.akshare_news import _fetch_cctv_news
        self.assertEqual(_fetch_cctv_news("20260701"), [])

    @patch.dict("sys.modules", {"akshare": MagicMock()})
    def test_none_dataframe(self):
        """返回 None → 返回空列表。"""
        import akshare
        akshare.news_cctv.return_value = None
        from src.python.providers.akshare_news import _fetch_cctv_news
        self.assertEqual(_fetch_cctv_news("20260701"), [])


class TestFetchNews(unittest.TestCase):
    """fetch_news 聚合集成测试。"""

    @patch("src.python.providers.akshare_news._fetch_cctv_news")
    @patch("src.python.providers.akshare_news._fetch_from_caixin")
    def test_merge_two_sources(self, mock_caixin, mock_cctv):
        """两个源合并 → 正确去重并排序。"""
        mock_caixin.return_value = [
            {"title": "财新新闻", "url": "http://caixin.com/1",
             "ctime": "2026-07-01 10:00", "media_name": "财新网"},
        ]
        mock_cctv.return_value = [
            {"title": "央视新闻", "url": "", "ctime": "2026-07-01 11:00",
             "media_name": "央视新闻"},
        ]
        from src.python.providers.akshare_news import fetch_news
        result = fetch_news(num=10)
        self.assertEqual(len(result), 2)
        # 按 ctime 降序，央视在前
        self.assertEqual(result[0]["media_name"], "央视新闻")

    @patch("src.python.providers.akshare_news._fetch_cctv_news")
    @patch("src.python.providers.akshare_news._fetch_from_caixin")
    def test_truncate_to_num(self, mock_caixin, mock_cctv):
        """超过 num 条 → 截断。"""
        mock_caixin.return_value = [
            {"title": f"新闻{i}", "url": f"http://caixin.com/{i}",
             "ctime": f"2026-07-01 {i:02d}:00", "media_name": "财新网"}
            for i in range(5)
        ]
        mock_cctv.return_value = []
        from src.python.providers.akshare_news import fetch_news

        result = fetch_news(num=3)
        self.assertEqual(len(result), 3)
