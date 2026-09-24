"""新浪财经行情 provider 单元测试。

测试目标：
  - _parse_us_index — 美股指数文本解析
  - fetch_us_indices — HTTP 请求、错误处理

运行：
  pytest src/test/unit/providers/test_sina.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class TestFetchFundNav(unittest.TestCase):
    """场外基金净值（`f_` 前缀）获取与解析 —— 跨厂商备源（回归：单源无备）。"""

    _LINE = 'var hq_str_f_011506="建信高端装备股票A,1.8384,1.8384,1.8828,2026-09-24,2.25622";'

    def _mock_client(self, text: str):
        resp = MagicMock()
        resp.text = text
        resp.encoding = "utf-8"
        client = MagicMock()
        client.get.return_value = resp
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        return client

    def test_parses_nav_fields(self):
        """正常响应 → 与 eastmoney.fetch_nav 同形状的原始字典。"""
        from src.python.providers import sina

        with patch.object(sina, "make_http_client", return_value=self._mock_client(self._LINE)):
            out = sina.fetch_fund_nav("011506")
        assert out is not None
        assert out["name"] == "建信高端装备股票A"
        assert out["code"] == "011506"
        assert out["nav"] == 1.8384
        assert out["acc_nav"] == 1.8384
        assert out["yesterday_nav"] == 1.8828
        assert out["nav_date"] == "2026-09-24"
        assert out["source"] == "新浪财经（场外净值）"

    def test_request_uses_fund_prefix_and_referer(self):
        """URL 使用 f_ 前缀 + Referer（防端点被误指向股票行情接口而静默失效）。"""
        from src.python.providers import sina

        client = self._mock_client(self._LINE)
        with patch.object(sina, "make_http_client", return_value=client):
            sina.fetch_fund_nav("011506")
        url = client.get.call_args.args[0]
        assert url.endswith("list=f_011506"), url
        assert "Referer" in (client.get.call_args.kwargs.get("headers") or {})

    def test_invalid_or_empty_response_returns_none(self):
        """响应缺失 / 字段不足 / 净值 <= 0 → None（交由链路下一槽）。"""
        from src.python.providers import sina

        for text in (
            "",
            'var hq_str_f_011506="";',
            'var hq_str_f_011506="名称,1.2";',
            'var hq_str_f_011506="名称,0,0,0,2026-09-24,0";',
            'var hq_str_sh000001="1,2,3";',
        ):
            assert sina._parse_fund_nav_response(text, "011506") is None, text

    def test_network_error_returns_none(self):
        """网络异常不抛异常，返回 None。"""
        import httpx

        from src.python.providers import sina

        with patch.object(sina, "make_http_client", side_effect=httpx.ConnectError("boom")):
            assert sina.fetch_fund_nav("011506") is None


class TestParseUsIndex(unittest.TestCase):
    """_parse_us_index 纯函数测试。"""

    def _call(self, text: str):
        from src.python.providers.sina import _parse_us_index

        return _parse_us_index(text)

    def test_normal_line(self):
        """正常数据 → 正确解析所有字段。"""
        line = 'var hq_str_gb_dji="道琼斯指数,34500.00,0.50,2026-07-01 04:30:00,+150.00,0.00,34600.00,34400.00";'
        result = self._call(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "道琼斯指数")
        self.assertEqual(result["price"], 34500.0)
        self.assertEqual(result["change"], 150.0)
        # change_pct = change / (price - change) * 100 = 150 / 34350 * 100 ≈ 0.44
        self.assertAlmostEqual(result["change_pct"], 0.44, places=2)
        self.assertEqual(result["price_date"], "2026-07-01")

    def test_no_quotes(self):
        """无双引号 → None。"""
        self.assertIsNone(self._call("plain text"))

    def test_empty_body(self):
        """空引号内容 → None。"""
        self.assertIsNone(self._call('var hq_str_gb_dji=""'))

    def test_too_few_fields(self):
        """字段不足 5 个 → None。"""
        self.assertIsNone(self._call('var hq_str_gb_dji="a,b,c"'))

    def test_zero_price(self):
        """价格为 0 → 仍返回。"""
        line = 'var hq_str_gb_dji="指数,0,0,,,";'
        result = self._call(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["price"], 0.0)

    def test_empty_parts(self):
        """含空字段 → 安全解析。"""
        line = 'var hq_str_gb_dji="指数,,,2026-07-01,,0,,";'
        result = self._call(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["price"], 0.0)

    def test_yclose_calculation(self):
        """昨收盘 = price - change。"""
        line = 'var hq_str_gb_dji="指数,100,1.0,2026-07-01,+2,0,,,";'
        result = self._call(line)
        self.assertEqual(result["yesterday_close"], 98.0)
        self.assertEqual(result["change_pct"], 2.04)  # 2/98*100 ≈ 2.04


class TestFetchUsIndices(unittest.TestCase):
    """fetch_us_indices HTTP 测试。"""

    def _make_response_text(self, results: dict[str, str]) -> str:
        """构造 Sina 返回的每行一条的格式。"""
        lines = []
        for code, body in results.items():
            lines.append(f'var hq_str_{code}="{body}";')
        return "\n".join(lines)

    @patch("src.python.providers.sina.make_http_client")
    def test_parses_three_us_indices(self, mock_factory):
        """正常返回 → 正确解析美股三大指数。"""
        text = self._make_response_text(
            {
                "gb_dji": "道琼斯,34500,0.5,2026-07-01,+150,0,34600,34400",
                "gb_ixic": "纳斯达克,14000,0.3,2026-07-01,+42,0,14100,13900",
                "gb_inx": "标普500,4500,0.4,2026-07-01,+18,0,4510,4490",
            }
        )
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = text
        mock_client.get.return_value = mock_response

        from src.python.providers.sina import fetch_us_indices

        result = fetch_us_indices()
        self.assertEqual(len(result), 3)
        self.assertIn("gb_dji", result)
        self.assertEqual(result["gb_dji"]["name"], "道琼斯")

    @patch("src.python.providers.sina.make_http_client")
    def test_missing_code_skipped(self, mock_factory):
        """返回中包含未注册代码 → 跳过。"""
        text = self._make_response_text(
            {
                "gb_unknown": "未知,100,0,2026-07-01,0,0,101,99",
                "gb_dji": "道琼斯,34500,0.5,2026-07-01,+150,0,34600,34400",
            }
        )
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = text
        mock_client.get.return_value = mock_response

        from src.python.providers.sina import fetch_us_indices

        result = fetch_us_indices()
        self.assertEqual(len(result), 1)

    @patch("src.python.providers.sina.make_http_client")
    def test_timeout_returns_empty(self, mock_factory):
        """超时 → 空字典。"""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        from src.python.providers.sina import fetch_us_indices

        self.assertEqual(fetch_us_indices(), {})

    @patch("src.python.providers.sina.make_http_client")
    def test_request_error_returns_empty(self, mock_factory):
        """网络异常 → 空字典。"""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("network error")

        from src.python.providers.sina import fetch_us_indices

        self.assertEqual(fetch_us_indices(), {})


class TestFetchIndexKline(unittest.TestCase):
    """fetch_index_kline 指数历史 K 线获取测试。"""

    def _make_kline_json(self, entries: list[list]) -> list[dict]:
        """构造 Sina K 线 JSON 响应。"""
        return [
            {
                "day": e[0],
                "open": str(e[1]),
                "close": str(e[2]),
                "high": str(e[3]),
                "low": str(e[4]),
                "volume": str(e[5]),
            }
            for e in entries
        ]

    @patch("src.python.providers.sina.make_http_client")
    def test_normal_a_share_index(self, mock_factory):
        """sh000300 正常返回 → 正确解析。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_kline_json(
            [
                ["2026-07-01", 3990.0, 4000.0, 4010.0, 3980.0, 1000000],
                ["2026-07-02", 4000.0, 4010.0, 4020.0, 3990.0, 1200000],
            ]
        )
        mock_client.get.return_value = mock_resp

        from src.python.providers.sina import fetch_index_kline

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(len(result), 2)
        expected_keys = {"date", "open", "close", "high", "low", "volume"}
        for bar in result:
            self.assertEqual(set(bar.keys()), expected_keys)
            self.assertIsNotNone(bar["close"])

    @patch("src.python.providers.sina.make_http_client")
    def test_us_index(self, mock_factory):
        """gb_inx 正常返回 → 正确解析。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_kline_json(
            [
                ["2026-07-01", 5490.0, 5500.0, 5510.0, 5480.0, 500000],
            ]
        )
        mock_client.get.return_value = mock_resp

        from src.python.providers.sina import fetch_index_kline

        result = fetch_index_kline("gb_inx", 30)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["close"], 5500.0)

    @patch("src.python.providers.sina.make_http_client")
    def test_empty_response(self, mock_factory):
        """远程返回空列表 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_client.get.return_value = mock_resp

        from src.python.providers.sina import fetch_index_kline

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.sina.make_http_client")
    def test_timeout_returns_empty(self, mock_factory):
        """超时 → 空列表。"""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        from src.python.providers.sina import fetch_index_kline

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    def test_non_index_code_returns_empty(self):
        """非指数代码 → 空列表。"""
        from src.python.providers.sina import fetch_index_kline

        result = fetch_index_kline("600900", 30)
        self.assertEqual(result, [])

    def test_empty_code_returns_empty(self):
        """空代码 → 空列表。"""
        from src.python.providers.sina import fetch_index_kline

        result = fetch_index_kline("", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.sina.make_http_client")
    def test_is_index_code_called_for_c1(self, mock_factory):
        """函数通过 code_utils.is_index_code 校验传入代码（代码类型判定）。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_kline_json(
            [
                ["2026-07-01", 3990.0, 4000.0, 4010.0, 3980.0, 1000000],
            ]
        )
        mock_client.get.return_value = mock_resp

        from src.python.core.code_utils import is_index_code as _orig_is_index

        with patch("src.python.providers.sina.is_index_code", wraps=_orig_is_index) as spy:
            from src.python.providers.sina import fetch_index_kline

            fetch_index_kline("sh000300", 30)
            spy.assert_called_with("sh000300")
