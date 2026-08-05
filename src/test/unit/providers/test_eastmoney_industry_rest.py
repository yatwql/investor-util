"""eastmoney_industry_rest 模块单元测试。

覆盖 REST 接口的行业分类数据解析：
  - _quote_prefix 交易所前缀判定
  - _extract_quotedata HTML 内嵌数据解析
  - fetch_industry_and_concepts 行业+概念获取（HTTP 异常降级）

运行：
  pytest src/test/unit/providers/test_eastmoney_industry_rest.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class TestRestQuotePrefix(unittest.TestCase):
    """_quote_prefix 纯函数测试。"""

    def _call(self, code: str) -> str:
        from src.python.providers.eastmoney_industry_rest import _quote_prefix
        return _quote_prefix(code)

    def test_sh_60(self):
        """60xxxx → sh。"""
        self.assertEqual(self._call("600000"), "sh")

    def test_sh_68(self):
        """68xxxx → sh。"""
        self.assertEqual(self._call("688001"), "sh")

    def test_sz_00(self):
        """00xxxx → sz。"""
        self.assertEqual(self._call("000001"), "sz")

    def test_sz_30(self):
        """30xxxx → sz。"""
        self.assertEqual(self._call("300001"), "sz")

    def test_bj_8(self):
        """8xxxxx → bj。"""
        self.assertEqual(self._call("830001"), "bj")


class TestRestExtractQuotedata(unittest.TestCase):
    """_extract_quotedata 纯函数测试。"""

    def _call(self, html: str) -> dict | None:
        from src.python.providers.eastmoney_industry_rest import _extract_quotedata
        return _extract_quotedata(html)

    def test_normal(self):
        """正常 HTML 含 quotedata → 正确解析。"""
        html = (
            '<html><body><script>'
            'var quotedata = {"name":"test","code":"600000",'
            '"bk_name":"白酒Ⅱ","bk_id":"BK1277"};'
            '</script></body></html>'
        )
        result = self._call(html)
        self.assertEqual(result["bk_name"], "白酒Ⅱ")
        self.assertEqual(result["bk_id"], "BK1277")

    def test_no_quotedata(self):
        """不含 quotedata → None。"""
        html = "<html><body>no data here</body></html>"
        self.assertIsNone(self._call(html))

    def test_empty_html(self):
        """空 HTML → None。"""
        self.assertIsNone(self._call(""))

    def test_sz_stock(self):
        """深圳股票 quotedata → 正确解析。"""
        html = (
            '<script>var quotedata = {"name":"平安银行","code":"000001",'
            '"bk_name":"银行","bk_id":"BK0477","type111":2};</script>'
        )
        result = self._call(html)
        self.assertEqual(result["bk_name"], "银行")
        self.assertEqual(result["bk_id"], "BK0477")


class TestRestFetchIndustryAndConcepts(unittest.TestCase):
    """eastmoney_industry_rest.fetch_industry_and_concepts 测试。"""

    def setUp(self):
        from src.python.core.provider_registry import get_registry
        get_registry().session_cache_clear("industry_rest")

    @patch("src.python.providers.eastmoney_industry_rest.make_http_client")
    def test_success(self, mock_client_factory):
        """正常返回 → 返回行业数据，概念列表为空。"""
        from src.python.providers.eastmoney_industry_rest import fetch_industry_and_concepts

        # mock HTTP 响应
        mock_client = mock_client_factory.return_value.__enter__.return_value
        mock_resp = mock_client.get.return_value
        mock_resp.text = (
            '<script>var quotedata = {"name":"贵州茅台","code":"600519",'
            '"bk_name":"白酒Ⅱ","bk_id":"BK1277"};</script>'
        )

        result = fetch_industry_and_concepts("600519")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "600519")
        self.assertEqual(result["industry"], "白酒Ⅱ")
        self.assertEqual(result["industry_id"], "BK1277")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry_rest.make_http_client")
    def test_no_quotedata(self, mock_client_factory):
        """页面无 quotedata → None。"""
        from src.python.providers.eastmoney_industry_rest import fetch_industry_and_concepts

        mock_client = mock_client_factory.return_value.__enter__.return_value
        mock_resp = mock_client.get.return_value
        mock_resp.text = "<html><body>no data</body></html>"

        result = fetch_industry_and_concepts("600519")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney_industry_rest.make_http_client")
    def test_http_error_returns_none(self, mock_client_factory):
        """HTTP 请求异常 → None。"""
        from src.python.providers.eastmoney_industry_rest import fetch_industry_and_concepts

        mock_client = mock_client_factory.return_value.__enter__.return_value
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        result = fetch_industry_and_concepts("000001")
        self.assertIsNone(result)
