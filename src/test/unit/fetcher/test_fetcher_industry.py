"""行业分类 API 模块单元测试。

测试目标：
  - _is_a_share_code — A 股代码识别
  - _industry_transform — 原始数据转换
  - fetch_industry_data — 单只证券行业查询（mock chain）
  - batch_fetch_industry_data — 批量查询（含非 A 股过滤）
  - eastmoney_industry_rest 模块：
    - _quote_prefix — A 股交易所前缀
    - _extract_quotedata — 行情页 JS 变量解析
    - fetch_industry_and_concepts — mock HTTP 后的业务逻辑

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_fetcher_industry.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]



class TestIsAShareCode(unittest.TestCase):
    """_is_a_share_code 纯函数测试。"""

    def _call(self, code: str) -> bool:
        from src.python.fetcher.industry import _is_a_share_code
        return _is_a_share_code(code)

    def test_normal_sh(self):
        """sh 前缀 A 股代码 → True。"""
        self.assertTrue(self._call("sh600000"))

    def test_normal_sz(self):
        """sz 前缀 A 股代码 → True。"""
        self.assertTrue(self._call("sz000001"))

    def test_normal_bj(self):
        """bj 前缀 A 股代码 → True。"""
        self.assertTrue(self._call("bj830001"))

    def test_raw_six_digit(self):
        """纯 6 位数字 → True。"""
        self.assertTrue(self._call("600900"))

    def test_us_stock(self):
        """美股字母代码 → False。"""
        self.assertFalse(self._call("AAPL"))

    def test_us_stock_numeric(self):
        """美股数字代码（无前缀非 6 位）→ False。"""
        self.assertFalse(self._call("BRK.B"))

    def test_hk_stock(self):
        """港股 5 位 → False。"""
        self.assertFalse(self._call("00700"))

    def test_empty(self):
        """空字符串 → False。"""
        self.assertFalse(self._call(""))

    def test_whitespace(self):
        """空格 → False。"""
        self.assertFalse(self._call("  "))

    def test_prefix_is_a_share(self):
        """带 sh/sz/bj 前缀的 6 位码 → True。"""
        for prefix in ("sh", "sz", "bj"):
            self.assertTrue(self._call(f"{prefix}600000"))

    def test_prefix_not_a_share(self):
        """带 sh/sz/bj 前缀但非 6 位 → False。"""
        self.assertFalse(self._call("sh60000"))  # 5 位


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

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_success(self, mock_fallback):
        """正常返回 → 返回行业数据。"""
        mock_fallback.return_value = {
            "code": "000001", "industry": "银行", "concepts": ["沪深300"],
        }
        from src.python.fetcher.industry import fetch_industry_data
        result = fetch_industry_data("000001")
        self.assertEqual(result["industry"], "银行")
        mock_fallback.assert_called_once()

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_failure_returns_none(self, mock_fallback):
        """获取失败 → None。"""
        mock_fallback.return_value = None
        from src.python.fetcher.industry import fetch_industry_data
        self.assertIsNone(fetch_industry_data("000001"))

    @patch("src.python.fetcher.industry.fetch_with_fallback")
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
        """批量 A 股成功 → 返回映射。"""
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

    @patch("src.python.fetcher.industry.fetch_industry_data", return_value=None)
    def test_us_stock_filtered_out(self, mock_fetch):
        """美股代码自动过滤，不调 API。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["600900", "AAPL", "00700", "PEP"])
        # AAPL/00700/PEP 被过滤，只调用了 600900（首次失败后重试一次）
        self.assertEqual(mock_fetch.call_count, 2)
        # 600900 两次均返回 None，全空
        self.assertEqual(result, {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_all_us_stocks_return_empty(self, mock_fetch):
        """全是美股 → 不调 API，直接返回空字典。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["AAPL", "GOOG", "TSLA"])
        mock_fetch.assert_not_called()
        self.assertEqual(result, {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_mixed_with_prefixed_codes(self, mock_fetch):
        """带 sh/sz 前缀和美股混合 → 前缀码通过，美股过滤。"""
        def side_effect(code, **kwargs):
            return {"code": code, "industry": "测试"}
        mock_fetch.side_effect = side_effect

        from src.python.fetcher.industry import batch_fetch_industry_data

        result = batch_fetch_industry_data(["sh600000", "sz000001", "AAPL"])
        self.assertEqual(len(result), 2)
        self.assertIn("sh600000", result)
        self.assertIn("sz000001", result)
        self.assertNotIn("AAPL", result)


class TestBatchFetchIndustryDataBroken(unittest.TestCase):
    """batch_fetch_industry_data 熔断预检测试。

    全链已熔断时跳过批量请求和重试，避免逐条冗余调用。
    """

    @patch("src.python.fetcher.industry.is_provider_chain_broken", return_value=True)
    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_entry_skipped_on_full_broken(self, mock_fetch, mock_broken):
        """全链熔断 → 入口预检返回空，不调用 fetch。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001", "600900"])
        self.assertEqual(result, {})
        mock_fetch.assert_not_called()

    @patch("src.python.fetcher.industry.is_provider_chain_broken")
    def test_entry_logs_warning(self, mock_broken):
        """全链熔断 → 日志含熔断提示。"""
        mock_broken.return_value = True
        with self.assertLogs("invest", level="WARNING") as log:
            from src.python.fetcher.industry import batch_fetch_industry_data
            batch_fetch_industry_data(["000001"])
            self.assertTrue(any("全链不可用（熔断）" in msg for msg in log.output))

    @patch("src.python.fetcher.industry.is_provider_chain_broken", return_value=True)
    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_empty_returned_on_full_broken(self, mock_fetch, mock_broken):
        """全链熔断 → 即使有代码也不调 API。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["sh600000", "sz000001"])
        self.assertEqual(result, {})
        mock_fetch.assert_not_called()

    @patch("src.python.fetcher.industry.is_provider_chain_broken", return_value=False)
    @patch("src.python.fetcher.industry.fetch_industry_data", return_value={"code": "000001", "industry": "银行"})
    def test_normal_when_not_broken(self, mock_fetch, mock_broken):
        """未熔断 → 正常调用不受影响。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001"])
        self.assertEqual(len(result), 1)
        mock_fetch.assert_called()


# ──────────────────────────────────────────────────────────────
# eastmoney_industry_rest 模块单元测试
# ──────────────────────────────────────────────────────────────

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
        from src.python.providers.eastmoney_industry_rest import _ext_memo_clear
        _ext_memo_clear()

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
