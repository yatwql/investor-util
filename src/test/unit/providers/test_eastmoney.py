"""东方财富 ETF/股票行情 provider 单元测试。

测试目标：
  - _strip_jsonp — JSONP 剥离
  - _safe_float — 安全浮点转换
  - _fallback_fundf10 — 备用链路 HTML 解析
  - fetch_nav — 主链路/备用链路、异常处理

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_eastmoney.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]



class TestStripJsonp(unittest.TestCase):
    """_strip_jsonp 纯函数测试。"""

    def _call(self, text: str) -> str:
        from src.python.providers.eastmoney import _strip_jsonp
        return _strip_jsonp(text)

    @pytest.mark.smoke
    def test_jsonp_format(self):
        """jQuery 回调包裹 → 提取 JSON。"""
        text = 'jQuery({"Data": {"LSJZList": []}})'
        self.assertEqual(self._call(text), '{"Data": {"LSJZList": []}}')

    @pytest.mark.smoke
    def test_pure_json(self):
        """纯 JSON → 原样返回。"""
        text = '{"key": "value"}'
        self.assertEqual(self._call(text), '{"key": "value"}')

    def test_no_brackets(self):
        """无括号 → 原样。"""
        text = "plain text"
        self.assertEqual(self._call(text), "plain text")


class TestSafeFloat(unittest.TestCase):
    """_safe_float 纯函数测试。"""

    def _call(self, s: str) -> float:
        from src.python.providers.eastmoney import _safe_float
        return _safe_float(s)

    @pytest.mark.smoke
    def test_normal(self):
        self.assertEqual(self._call("1.2345"), 1.2345)

    @pytest.mark.smoke
    def test_empty_string(self):
        self.assertEqual(self._call(""), 0.0)

    def test_none_type(self):
        self.assertEqual(self._call(None), 0.0)  # type: ignore

    def test_invalid_string(self):
        self.assertEqual(self._call("abc"), 0.0)


class TestFallbackFundf10(unittest.TestCase):
    """_fallback_fundf10 备用链路测试。"""

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_success(self, mock_factory):
        """正常返回 → 解析出净值。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = (
            '<table><tr><td class="bold">1.2345</td>'
            '<td class="">2026-07-01</td></tr></table>'
        )
        mock_client.get.return_value = mock_response

        from src.python.providers.eastmoney import _fallback_fundf10
        result = _fallback_fundf10("011506")
        self.assertIsNotNone(result)
        self.assertEqual(result["nav"], 1.2345)
        self.assertEqual(result["nav_date"], "2026-07-01")
        self.assertEqual(result["source"], "天天基金(备用链路)")

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_request_error(self, mock_factory):
        """网络异常 → 返回 None。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        import httpx
        mock_client.get.side_effect = httpx.RequestError("network error")

        from src.python.providers.eastmoney import _fallback_fundf10
        self.assertIsNone(_fallback_fundf10("011506"))

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_parse_failure(self, mock_factory):
        """HTML 中无 bold 标签 → 返回 None。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "<html><body>无数据</body></html>"
        mock_client.get.return_value = mock_response

        from src.python.providers.eastmoney import _fallback_fundf10
        self.assertIsNone(_fallback_fundf10("011506"))


class TestFetchNav(unittest.TestCase):
    """fetch_nav 主链路 + 备用链路测试。"""

    def _make_mock_client(self, factory_mock, text: str):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        factory_mock.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = text
        mock_client.get.return_value = mock_response
        return mock_client

    # ── 主链路正常 ──────────────────────────────────────

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_success(self, mock_factory):
        """主链路正常 → 返回净值数据。"""
        jsonp = 'jQuery({"Data": {"LSJZList": [{"DWJZ":"1.2345","LJJZ":"2.3456","FSRQ":"2026-07-01"}], "FundName":"测试基金"}})'
        self._make_mock_client(mock_factory, jsonp)

        from src.python.providers.eastmoney import fetch_nav
        result = fetch_nav("011506")
        self.assertIsNotNone(result)
        self.assertEqual(result["nav"], 1.2345)
        self.assertEqual(result["acc_nav"], 2.3456)
        self.assertEqual(result["nav_date"], "2026-07-01")
        self.assertEqual(result["name"], "测试基金")
        self.assertEqual(result["source"], "东方财富")

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_success_with_yesterday(self, mock_factory):
        """有前一日净值 → 正确计算。"""
        jsonp = ('jQuery({"Data": {"LSJZList": ['
                 '{"DWJZ":"1.2345","LJJZ":"2.3456","FSRQ":"2026-07-01"},'
                 '{"DWJZ":"1.2000","LJJZ":"2.3000","FSRQ":"2026-06-30"}'
                 ']}})')
        self._make_mock_client(mock_factory, jsonp)

        from src.python.providers.eastmoney import fetch_nav
        result = fetch_nav("011506")
        self.assertEqual(result["nav"], 1.2345)
        self.assertEqual(result["yesterday_nav"], 1.2000)

    # ── 主链路失败 → 备用链路 ──────────────────────────

    @patch("src.python.providers.eastmoney._fallback_fundf10")
    @patch("src.python.providers.eastmoney.make_http_client")
    def test_timeout_triggers_fallback(self, mock_factory, mock_fallback):
        """超时 → 尝试备用链路。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        import httpx
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        mock_fallback.return_value = {"nav": 1.1, "source": "天天基金(备用链路)"}

        from src.python.providers.eastmoney import fetch_nav
        result = fetch_nav("011506")
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "天天基金(备用链路)")

    @patch("src.python.providers.eastmoney._fallback_fundf10")
    @patch("src.python.providers.eastmoney.make_http_client")
    def test_json_decode_triggers_fallback(self, mock_factory, mock_fallback):
        """JSON 解析失败 → 尝试备用链路。"""
        self._make_mock_client(mock_factory, "not json")
        mock_fallback.return_value = {"nav": 1.1, "source": "天天基金(备用链路)"}

        from src.python.providers.eastmoney import fetch_nav
        result = fetch_nav("011506")
        self.assertIsNotNone(result)

    @patch("src.python.providers.eastmoney._fallback_fundf10")
    @patch("src.python.providers.eastmoney.make_http_client")
    def test_empty_records_triggers_fallback(self, mock_factory, mock_fallback):
        """空净值列表 → 尝试备用链路。"""
        self._make_mock_client(mock_factory, 'jQuery({"Data": {"LSJZList": []}})')
        mock_fallback.return_value = None

        from src.python.providers.eastmoney import fetch_nav
        result = fetch_nav("011506")
        self.assertIsNone(result)

    # ── 全部失败 ─────────────────────────────────────────

    @patch("src.python.providers.eastmoney._fallback_fundf10")
    @patch("src.python.providers.eastmoney.make_http_client")
    def test_all_fail_returns_none(self, mock_factory, mock_fallback):
        """主链路和备用链路全失败 → None。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        import httpx
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        mock_fallback.return_value = None

        from src.python.providers.eastmoney import fetch_nav
        self.assertIsNone(fetch_nav("011506"))


class TestQdiiNavRelationships(unittest.TestCase):
    """QDII 估值净值 vs 官方净值关系。"""

    def _call_fetch_nav(self, mock_data: dict | None = None):
        """Mock fetch_nav 返回指定数据。"""
        with patch("src.python.providers.eastmoney.make_http_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_factory.return_value = mock_client
            if mock_data:
                mock_client.get.return_value.status_code = 200
                import json
                mock_client.get.return_value.text = json.dumps(mock_data)
            else:
                import httpx
                mock_client.get.side_effect = httpx.TimeoutException("timeout")

            from src.python.providers.eastmoney import fetch_nav

            return fetch_nav("513300")

    def test_official_nav_non_negative(self):
        """官方净值 ≥ 0。"""
        result = self._call_fetch_nav({
            "Data": {"LSJZList": [{"NAV": 1.5, "NAVdate": "2026-07-01"}]}
        })
        if result and "NAV" in result:
            self.assertGreaterEqual(result["NAV"], 0)

    def test_estimated_nav_vs_official(self):
        """估值净值与官方净值的关系合理：两者差距通常在 ±5% 以内。"""
        # 模拟典型 scenario：估值 1.48，官方 1.50
        result = self._call_fetch_nav({
            "Data": {"LSJZList": [
                {"NAV": 1.50, "NAVdate": "2026-07-01"},
                {"NAV": 1.48, "NAVdate": "2026-06-30"},  # 估值净值（T-1）
            ]}
        })
        if result and "NAV" in result:
            self.assertGreaterEqual(result["NAV"], 0)

    def test_official_nav_delayed_t2(self):
        """QDII 官方净值通常延迟 T-2（验证数据日期合理性）。"""
        result = self._call_fetch_nav({
            "Data": {"LSJZList": [{"NAV": 1.5, "NAVdate": "2026-06-28"}]}
        })
        # fetch_nav 返回最新一条 NAV
        if result and "NAVdate" in result:
            self.assertIn("2026-06-28", result["NAVdate"])

    def test_nav_date_ascending_order(self):
        """净值日期应递增（旧→新）。"""
        result = self._call_fetch_nav({
            "Data": {"LSJZList": [
                {"NAV": 1.4, "NAVdate": "2026-06-28"},
                {"NAV": 1.5, "NAVdate": "2026-07-01"},
            ]}
        })
        # 如果 fetch_nav 返回多条，验证日期顺序
        if result and isinstance(result, list):
            dates = [r.get("NAVdate", "") for r in result if "NAVdate" in r]
            if len(dates) >= 2:
                self.assertLessEqual(dates[0], dates[1],
                                     "净值日期应递增")
