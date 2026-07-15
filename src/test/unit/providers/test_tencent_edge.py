"""Tencent 指数 K 线边缘场景测试。

必须放在 *_edge.py 文件中（C12 约束）。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.providers.tencent import fetch_index_kline

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers, pytest.mark.edge]


class TestFetchIndexKlineEdge(unittest.TestCase):
    """fetch_index_kline 边缘/异常场景。"""

    @patch("src.python.providers.tencent.make_http_client")
    def test_request_error_returns_empty(self, mock_factory):
        """网络异常 → 空列表。"""
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("network error")

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.tencent.make_http_client")
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

    @patch("src.python.providers.tencent.make_http_client")
    def test_malformed_data_structure(self, mock_factory):
        """API 返回非标准结构 → 空列表（不抛异常）。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"unexpected": "format"}
        mock_client.get.return_value = mock_resp

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])

    @patch("src.python.providers.tencent.make_http_client")
    def test_kline_entry_too_short(self, mock_factory):
        """K 线条目字段不足 6 个 → 自动跳过该条目。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "sh000300": {
                    "qfqday": [
                        ["2026-07-01", "4000.0"],
                        ["2026-07-02", "4010.0", "4020.0", "3990.0", "4015.0", "1000000"],
                    ]
                }
            }
        }
        mock_client.get.return_value = mock_resp

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(len(result), 1)

    @patch("src.python.providers.tencent.make_http_client")
    def test_all_bars_filtered_due_to_zero_close(self, mock_factory):
        """所有 K 线 close 为 0 → 空列表。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "sh000300": {
                    "qfqday": [
                        ["2026-07-01", "3990.0", "0.0", "4010.0", "3980.0", "1000000"],
                        ["2026-07-02", "4000.0", "0.0", "4020.0", "3990.0", "1000000"],
                    ]
                }
            }
        }
        mock_client.get.return_value = mock_resp

        result = fetch_index_kline("sh000300", 30)
        self.assertEqual(result, [])
