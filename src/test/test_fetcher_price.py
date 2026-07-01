"""价格获取 chain 模块单元测试。

测试目标：
  - _name_matches — 名称匹配逻辑
  - _price_cache_key — 缓存键生成
  - _price_transform_tencent — 腾讯数据转换
  - _price_transform_eastmoney — 东方财富数据转换
  - fetch_market_data — 完整链路（mock chain）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_fetcher_price.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestNameMatches(unittest.TestCase):
    """_name_matches 纯函数测试。"""

    def _call(self, a: str, b: str) -> bool:
        from src.python.fetcher.price import _name_matches
        return _name_matches(a, b)

    def test_exact_match(self):
        """完全匹配 → True。"""
        self.assertTrue(self._call("长江电力", "长江电力"))

    def test_empty_a(self):
        """a 为空 → False。"""
        self.assertFalse(self._call("", "长江电力"))

    def test_empty_b(self):
        """b 为空 → False。"""
        self.assertFalse(self._call("长江电力", ""))

    def test_substring_match(self):
        """子串匹配（>3 字）→ True。"""
        self.assertTrue(self._call("长江电力", "长江电力股份"))

    def test_substring_reverse(self):
        """另一方向子串匹配 → True。"""
        self.assertTrue(self._call("长江电力股份", "长江电力"))

    def test_cjk_overlap(self):
        """CJK 字符重叠 >= 70% → True。"""
        self.assertTrue(self._call("长江电力", "长江电"))

    def test_low_overlap(self):
        """CJK 重叠 < 70% → False。"""
        self.assertFalse(self._call("长江电力", "贵州茅台"))

    def test_no_cjk_chars(self):
        """无非汉字的名称 → False。"""
        self.assertFalse(self._call("ABC", "XYZ"))


class TestPriceCacheKey(unittest.TestCase):
    """_price_cache_key 纯函数测试。"""

    def _call(self, code: str) -> str:
        from src.python.fetcher.price import _price_cache_key
        return _price_cache_key(code)

    def test_format(self):
        """格式为 price_{code}。"""
        self.assertEqual(self._call("600900"), "price_600900")

    def test_different_code(self):
        """不同代码 → 不同键。"""
        self.assertNotEqual(self._call("600900"), self._call("000001"))


class TestPriceTransformTencent(unittest.TestCase):
    """_price_transform_tencent 纯函数测试。"""

    def _call(self, raw: dict, source: str = "腾讯财经"):
        from src.python.fetcher.price import _price_transform_tencent
        return _price_transform_tencent(raw, source)

    def test_normal(self):
        """正常数据 → 统一格式。"""
        raw = {
            "name": "长江电力", "code": "600900",
            "price": 26.65, "yesterday_close": 26.50,
            "price_date": "2026-07-01",
        }
        result = self._call(raw)
        self.assertEqual(result["name"], "长江电力")
        self.assertEqual(result["price"], 26.65)
        self.assertEqual(result["source_api"], "tencent")
        self.assertEqual(result["source"], "腾讯财经")

    def test_empty_fields(self):
        """缺字段 → 不抛异常。"""
        result = self._call({"code": "600900"})
        self.assertEqual(result["price"], 0.0)
        self.assertEqual(result["name"], "")


class TestPriceTransformEastmoney(unittest.TestCase):
    """_price_transform_eastmoney 纯函数测试。"""

    def _call(self, raw: dict, source: str = "东方财富"):
        from src.python.fetcher.price import _price_transform_eastmoney
        return _price_transform_eastmoney(raw, source)

    def test_normal(self):
        """正常数据 → 统一格式。"""
        raw = {
            "name": "测试基金", "code": "011506",
            "nav": 1.2345, "yesterday_nav": 1.2000,
            "nav_date": "2026-07-01",
        }
        result = self._call(raw)
        self.assertEqual(result["name"], "测试基金")
        self.assertEqual(result["price"], 1.2345)
        self.assertEqual(result["yesterday_close"], 1.2000)
        self.assertEqual(result["source_api"], "eastmoney")

    def test_zero_nav_returns_none(self):
        """nav <= 0 → None。"""
        self.assertIsNone(self._call({"code": "011506", "nav": 0.0}))

    def test_negative_nav_returns_none(self):
        """nav 负数 → None。"""
        self.assertIsNone(self._call({"code": "011506", "nav": -1.0}))

    def test_missing_nav(self):
        """无 nav 字段 → None（默认 0.0）。"""
        self.assertIsNone(self._call({"code": "011506"}))


class TestFetchMarketData(unittest.TestCase):
    """fetch_market_data 测试（mock chain）。"""

    @patch("src.python.fetcher.price._fetch_with_fallback")
    def test_success(self, mock_fallback):
        """正常返回。"""
        mock_fallback.return_value = {
            "name": "长江电力", "code": "600900",
            "price": 26.65, "source": "腾讯财经",
        }
        from src.python.fetcher.price import fetch_market_data
        result = fetch_market_data("600900", "长江电力")
        self.assertEqual(result["price"], 26.65)

    @patch("src.python.fetcher.price._fetch_with_fallback")
    def test_all_fail_returns_none(self, mock_fallback):
        """全部失败 → None。"""
        mock_fallback.return_value = None
        from src.python.fetcher.price import fetch_market_data
        self.assertIsNone(fetch_market_data("600900"))

    @patch("src.python.fetcher.price._fetch_with_fallback")
    def test_expected_name_passed(self, mock_fallback):
        """expected_name 正确传递到 validate。"""
        mock_fallback.return_value = None
        from src.python.fetcher.price import fetch_market_data
        fetch_market_data("600900", "长江电力")
        # _fetch_with_fallback 被调用，validate 从 fn_kwargs 读取
        args, kwargs = mock_fallback.call_args
        self.assertIn("validate", kwargs)
