"""行业分类 API 模块单元测试。

测试目标：
  - _industry_transform — 原始数据转换
  - fetch_industry_data — 单只证券行业查询（mock chain）
  - batch_fetch_industry_data — 批量查询

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_fetcher_industry.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestIndustryTransform(unittest.TestCase):
    """_industry_transform 纯函数测试。"""

    def _call(self, raw: dict | None, source: str = "eastmoney"):
        from src.python.fetcher.industry import _industry_transform
        return _industry_transform(raw, source)

    def test_normal(self):
        """正常数据 → 正确转换。"""
        raw = {
            "code": "000001",
            "industry": "银行",
            "industry_id": "BK0477",
            "concepts": ["沪深300", "MSCI"],
            "concept_ids": ["BK0500", "BK0600"],
        }
        result = self._call(raw)
        self.assertEqual(result["code"], "000001")
        self.assertEqual(result["industry"], "银行")
        self.assertEqual(len(result["concepts"]), 2)

    def test_none_input(self):
        """None 输入 → None。"""
        self.assertIsNone(self._call(None))

    def test_empty_dict(self):
        """空字典（falsy）→ None。"""
        self.assertIsNone(self._call({}))

    def test_missing_fields(self):
        """缺字段 → 不抛异常。"""
        result = self._call({"code": "000001"})
        self.assertEqual(result["code"], "000001")
        self.assertEqual(result["industry"], "")
        self.assertEqual(result["concepts"], [])


class TestFetchIndustryData(unittest.TestCase):
    """fetch_industry_data 测试。"""

    @patch("src.python.fetcher.industry._fetch_with_fallback")
    def test_success(self, mock_fallback):
        """正常返回 → 返回行业数据。"""
        mock_fallback.return_value = {
            "code": "000001", "industry": "银行", "concepts": ["沪深300"],
        }
        from src.python.fetcher.industry import fetch_industry_data
        result = fetch_industry_data("000001")
        self.assertEqual(result["industry"], "银行")
        mock_fallback.assert_called_once()

    @patch("src.python.fetcher.industry._fetch_with_fallback")
    def test_failure_returns_none(self, mock_fallback):
        """获取失败 → None。"""
        mock_fallback.return_value = None
        from src.python.fetcher.industry import fetch_industry_data
        self.assertIsNone(fetch_industry_data("000001"))

    @patch("src.python.fetcher.industry._fetch_with_fallback")
    def test_cache_key_includes_code(self, mock_fallback):
        """缓存键包含代码。"""
        mock_fallback.return_value = {}
        from src.python.fetcher.industry import fetch_industry_data
        fetch_industry_data("600900")
        args, kwargs = mock_fallback.call_args
        # 第三个位置参数是 cache_key
        self.assertIn("industry_600900", args)


class TestBatchFetchIndustryData(unittest.TestCase):
    """batch_fetch_industry_data 测试。"""

    def test_empty_input(self):
        """空列表 → 空字典。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        self.assertEqual(batch_fetch_industry_data([]), {})

    def test_all_empty_codes(self):
        """全空/无效代码 → 空字典。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        self.assertEqual(batch_fetch_industry_data(["", " ", None]), {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_batch_success(self, mock_fetch):
        """批量成功 → 返回映射。"""
        def side_effect(code, **kwargs):
            return {"code": code, "industry": "测试"}
        mock_fetch.side_effect = side_effect

        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001", "600900"])
        self.assertEqual(len(result), 2)
        self.assertIn("000001", result)

    @patch("src.python.fetcher.industry.fetch_industry_data", return_value=None)
    def test_batch_partial_failure(self, mock_fetch):
        """部分失败 → 只返回成功的。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001", "600900"])
        self.assertEqual(result, {})
