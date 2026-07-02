"""腾讯财经行情 provider 单元测试。

测试目标：
  - _add_prefix — 代码前缀添加
  - _parse_float — 安全浮点转换
  - _parse_response — 腾讯 API 文本解析
  - fetch_price — HTTP 请求、错误处理

注意：腾讯 API 返回的字段索引（1-based）依据 _FIELD_MAP：
  name=2, code=3, price=4, yesterday_close=5, price_date=31, high=34, low=35
需要至少 35 个 ~ 分隔字段。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_tencent.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]



def _make_tx_body(fields: list[str]) -> str:
    """用字段列表构造腾讯 API 返回体，不足 35 个字段用 "0" 补齐。"""
    padded = list(fields) + ["0"] * (35 - len(fields))
    return "~".join(padded)


class TestAddPrefix(unittest.TestCase):
    """_add_prefix 纯函数测试。"""

    def _call(self, code: str) -> str:
        from src.python.providers.tencent import _add_prefix
        return _add_prefix(code)

    def test_sh_5xxxxx(self):
        """5 开头 → sh 前缀。"""
        self.assertEqual(self._call("561910"), "sh561910")

    def test_sh_6xxxxx(self):
        """6 开头 → sh 前缀。"""
        self.assertEqual(self._call("600900"), "sh600900")

    def test_sz_0xxxxx(self):
        """0 开头 → sz 前缀。"""
        self.assertEqual(self._call("000001"), "sz000001")

    def test_sz_3xxxxx(self):
        """3 开头 → sz 前缀。"""
        self.assertEqual(self._call("300750"), "sz300750")

    def test_non_six_digit(self):
        """非 6 位代码 → 原样返回。"""
        self.assertEqual(self._call("HK00700"), "HK00700")

    def test_stripped(self):
        """去除首尾空格。"""
        self.assertEqual(self._call(" 600900 "), "sh600900")


class TestParseFloat(unittest.TestCase):
    """_parse_float 纯函数测试。"""

    def _call(self, s: str) -> float:
        from src.python.providers.tencent import _parse_float
        return _parse_float(s)

    def test_normal(self):
        self.assertEqual(self._call("1.234"), 1.234)

    def test_zero(self):
        self.assertEqual(self._call("0.000"), 0.0)

    def test_negative(self):
        self.assertEqual(self._call("-1.0"), 0.0)

    def test_empty(self):
        self.assertEqual(self._call(""), 0.0)

    def test_invalid(self):
        self.assertEqual(self._call("abc"), 0.0)


class TestParseResponse(unittest.TestCase):
    """_parse_response 纯函数测试。"""

    def _call(self, text: str):
        from src.python.providers.tencent import _parse_response
        return _parse_response(text)

    def _make_text(self, fields: list[str]) -> str:
        """构造带 quotes 的完整 API 返回文本。"""
        body = _make_tx_body(fields)
        return f'v_sh561910="{body}";'

    def test_normal(self):
        """正常数据 → 正确解析所有字段。"""
        # 至少 35 个字段（依据 _FIELD_MAP 最大索引 35）
        fields = [""] * 35
        fields[0] = "1"                # 序号(1)
        fields[1] = "科创材料ETF"       # name(2)
        fields[2] = "561910"           # code(3)
        fields[3] = "0.853"            # price(4)
        fields[4] = "0.901"            # yesterday_close(5)
        fields[5] = "0.850"            # open(6)
        fields[6] = "12345"            # volume(7)
        fields[7] = "67890"            # turnover(8)
        fields[30] = "20260701103000"  # price_date(31)
        fields[33] = "0.870"           # high(34)
        fields[34] = "0.840"           # low(35)

        result = self._call(self._make_text(fields))
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "科创材料ETF")
        self.assertEqual(result["code"], "561910")
        self.assertEqual(result["price"], 0.853)
        self.assertEqual(result["yesterday_close"], 0.901)
        self.assertEqual(result["open"], 0.850)
        self.assertEqual(result["volume"], 12345.0)
        self.assertEqual(result["turnover"], 67890.0)
        self.assertEqual(result["price_date"], "2026-07-01")

    def test_no_quotes(self):
        """无双引号 → None。"""
        self.assertIsNone(self._call("plain text"))

    def test_empty_body(self):
        """空引号内容 → None。"""
        self.assertIsNone(self._call('v_sh561910=""'))

    def test_too_few_fields(self):
        """字段不足 10 个 → None。"""
        self.assertIsNone(self._call('v_sh561910="a~b~c"'))

    def test_zero_price(self):
        """价格为 0.000 → 仍解析。"""
        fields = [""] * 35
        fields[0] = "1"
        fields[1] = "ETF"
        fields[2] = "561910"
        fields[3] = "0.000"
        fields[4] = "0.001"
        result = self._call(self._make_text(fields))
        self.assertIsNotNone(result)
        self.assertEqual(result["price"], 0.0)

    def test_date_parsing(self):
        """日期字段 YYYYMMDDHHMMSS → YYYY-MM-DD。"""
        fields = [""] * 35
        fields[0] = "1"
        fields[1] = "ETF"
        fields[2] = "561910"
        fields[3] = "0.853"
        fields[4] = "0.901"
        fields[30] = "20260701103000"
        result = self._call(self._make_text(fields))
        self.assertEqual(result["price_date"], "2026-07-01")


class TestFetchPrice(unittest.TestCase):
    """fetch_price HTTP 测试。"""

    @patch("src.python.providers.tencent.make_http_client")
    def test_success(self, mock_factory):
        """正常返回 → 正确解析。"""
        fields = [""] * 35
        fields[0] = "1"
        fields[1] = "长江电力"
        fields[2] = "600900"
        fields[3] = "26.65"
        fields[4] = "26.50"

        body = "~".join(fields)
        text = f'v_sh600900="{body}";'

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = text
        mock_client.get.return_value = mock_response

        from src.python.providers.tencent import fetch_price
        result = fetch_price("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "长江电力")
        self.assertEqual(result["price"], 26.65)
        self.assertEqual(result["yesterday_close"], 26.50)

    @patch("src.python.providers.tencent.make_http_client")
    def test_timeout_returns_none(self, mock_factory):
        """超时 → None。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        from src.python.providers.tencent import fetch_price
        self.assertIsNone(fetch_price("600900"))

    @patch("src.python.providers.tencent.make_http_client")
    def test_request_error_returns_none(self, mock_factory):
        """网络异常 → None。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("network error")

        from src.python.providers.tencent import fetch_price
        self.assertIsNone(fetch_price("600900"))

    @patch("src.python.providers.tencent.make_http_client")
    def test_parse_failure_returns_none(self, mock_factory):
        """解析失败 → None。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "invalid format"
        mock_client.get.return_value = mock_response

        from src.python.providers.tencent import fetch_price
        self.assertIsNone(fetch_price("600900"))
