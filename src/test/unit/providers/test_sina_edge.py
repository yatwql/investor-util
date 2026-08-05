"""Sina 指数 K 线边缘场景测试。

必须放在 *_edge.py 文件中（边缘测试文件隔离）。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.providers.sina import fetch_index_kline

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers, pytest.mark.edge]


class TestFetchIndexKlineEdge(unittest.TestCase):
    """fetch_index_kline 边缘/异常场景。"""

    @patch("src.python.providers.sina.make_http_client")
    def test_request_error_returns_empty(self, mock_factory):
        """网络异常 → 空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("network error")

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.sina.make_http_client")
    def test_invalid_json_returns_empty(self, mock_factory):
        """非法 JSON 响应 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("invalid json")
        mock_client.get.return_value = mock_resp

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.sina.make_http_client")
    def test_malformed_not_a_list(self, mock_factory):
        """API 返回非列表结构 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"unexpected": "object"}
        mock_client.get.return_value = mock_resp

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.sina.make_http_client")
    def test_not_a_dict_entry_skipped(self, mock_factory):
        """列表中含非 dict 元素 → 自动跳过。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            "not a dict",
            {"day": "2026-07-02", "open": "4000.0", "close": "4010.0",
             "high": "4020.0", "low": "3990.0", "volume": "1000000"},
        ]
        mock_client.get.return_value = mock_resp

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(len(result), 1)

    @patch("src.python.providers.sina.make_http_client")
    def test_all_bars_filtered_due_to_zero_close(self, mock_factory):
        """所有 K 线 close 为 0 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"day": "2026-07-01", "open": "3990.0", "close": "0.0",
             "high": "4010.0", "low": "3980.0", "volume": "1000000"},
            {"day": "2026-07-02", "open": "4000.0", "close": "0.0",
             "high": "4020.0", "low": "3990.0", "volume": "1200000"},
        ]
        mock_client.get.return_value = mock_resp

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.sina.make_http_client")
    def test_days_clamped_to_2000(self, mock_factory):
        """请求 days=3650 时钳位到 2000（与 Tencent 对齐），避免超限响应。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_client.get.return_value = mock_resp

        fetch_index_kline("sh000300", 3650)
        call_kwargs = mock_client.get.call_args.kwargs
        datalen = call_kwargs["params"]["datalen"]
        self.assertEqual(datalen, 2000)
