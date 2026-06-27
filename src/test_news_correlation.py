"""财经新闻关联模块单元测试 — 异常场景与边界测试。

测试目标：
  - build_news_data — 空持仓/API 失败降级（mock API）
  - write_news_sheet — 空数据/正常数据渲染

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_news_correlation -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.models import Holding
from src.report import news_correlation as nc


class TestBuildNewsData(unittest.TestCase):
    """build_news_data 异常场景测试（mock 网络层）。"""

    @patch("src.providers.news_aggregator.aggregate_news")
    def test_empty_holdings_returns_empty_list(self, mock_aggregate):
        """空持仓 → aggregate_news 不会被调或返回空列表。"""
        mock_aggregate.return_value = []
        result = nc.build_news_data([])
        self.assertEqual(result, [])

    @patch("src.providers.news_aggregator.aggregate_news")
    def test_api_failure_returns_empty(self, mock_aggregate):
        """API 失败 → 返回空列表。"""
        mock_aggregate.return_value = []
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                     shares=100, cost_price=10.0)
        ]
        result = nc.build_news_data(holdings)
        self.assertEqual(result, [])

    @patch("src.providers.news_aggregator.aggregate_news")
    def test_api_returns_data(self, mock_aggregate):
        """API 返回数据 → 正确传递。"""
        mock_aggregate.return_value = [
            {"title": "新闻标题", "intro": "简介", "url": "http://example.com",
             "ctime": "2026-06-27", "media_name": "新浪财经", "matched_keywords": ["长江电力"]},
        ]
        holdings = [
            Holding(account="证券", name="长江电力", code="600900",
                     shares=100, cost_price=10.0)
        ]
        result = nc.build_news_data(holdings)
        self.assertEqual(len(result), 1)
        self.assertIn("matched_keywords", result[0])


class TestWriteNewsSheet(unittest.TestCase):
    """write_news_sheet 边界测试。"""

    def setUp(self):
        from openpyxl import Workbook
        self.wb = Workbook()
        self.ws = self.wb.active

    def test_empty_data(self):
        """空数据 → 写入"暂无关联新闻"占位。"""
        nc.write_news_sheet(self.ws, [])
        any_text = False
        for row in self.ws.iter_rows():
            for cell in row:
                if cell.value and "暂无" in str(cell.value):
                    any_text = True
        self.assertTrue(any_text)

    def test_with_data(self):
        """有数据 → 正确写入标题、序号、关键词。"""
        data = [
            {"title": "新闻A", "intro": "简介A", "url": "http://a.com",
             "ctime": "2026-06-27", "media_name": "新浪", "matched_keywords": ["茅台"]},
            {"title": "新闻B", "intro": "简介B", "url": "http://b.com",
             "ctime": "2026-06-26", "media_name": "新浪", "matched_keywords": ["五粮液", "白酒"]},
        ]
        nc.write_news_sheet(self.ws, data)
        headers = [self.ws.cell(row=2, column=c).value for c in range(1, 7)]
        self.assertIn("序号", headers)
        self.assertEqual(self.ws.cell(row=3, column=1).value, 1)

    def test_partial_missing_fields(self):
        """数据缺少可选字段 → 不崩溃。"""
        data = [
            {"title": "仅标题", "matched_keywords": ["茅台"]},
        ]
        try:
            nc.write_news_sheet(self.ws, data)
        except Exception as e:
            self.fail(f"write_news_sheet with partial data raised: {e}")


if __name__ == "__main__":
    unittest.main()
