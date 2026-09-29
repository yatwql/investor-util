"""东方财富指数 K 线 provider 边缘/异常场景测试。

必须放在 *_edge.py 文件中（边缘测试文件隔离）：覆盖无法映射的代码、
push2his 响应结构异常、解析失败与重试耗尽等降级路径。

运行：
  pytest src/test/unit/providers/test_eastmoney_index_edge.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.python.core.retry import STRATEGY_FIXED, RetryPolicy
from src.python.providers import eastmoney
from src.python.providers.eastmoney import fetch_index_kline

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers, pytest.mark.edge]


class TestFetchIndexKlineEdge:
    """fetch_index_kline 异常/边界场景。"""

    def test_non_index_code_returns_empty(self):
        """非指数代码（个股）→ 空列表，不发请求。"""
        with patch("src.python.providers.eastmoney._fetch_index_kline_json") as mock_json:
            assert fetch_index_kline("600900", 30) == []
            mock_json.assert_not_called()

    def test_json_none_returns_empty(self):
        """上游 JSON 拉取失败（重试耗尽）→ 空列表，不抛异常。"""
        with patch("src.python.providers.eastmoney._fetch_index_kline_json", return_value=None):
            assert fetch_index_kline("sh000300", 30) == []

    def test_malformed_klines_are_skipped(self):
        """行字段不足 / close<=0 / 非法行 → 跳过，只保留有效行。"""
        payload = {
            "data": {
                "klines": [
                    "bad",
                    "2026-07-01,1,2",
                    "2026-07-02,1,0,3,4,5,0,0",
                    "2026-07-03,1,2,3,4,5,0,0",
                ]
            }
        }
        with patch("src.python.providers.eastmoney._fetch_index_kline_json", return_value=payload):
            bars = fetch_index_kline("sh000300", 30)
        assert [b["date"] for b in bars] == ["2026-07-03"]

    def test_non_list_klines_returns_empty(self):
        """klines 结构异常（非列表）→ 空列表，不抛异常。"""
        with patch(
            "src.python.providers.eastmoney._fetch_index_kline_json",
            return_value={"data": {"klines": {"unexpected": True}}},
        ):
            assert fetch_index_kline("sh000300", 30) == []

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_transient_exhausted_returns_none(self, mock_factory):
        """传输级失败（RequestError）重试耗尽 → None，且确实尝试了 3 次。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("refused")

        with patch.object(
            eastmoney, "_INDEX_RETRY_POLICY", RetryPolicy(attempts=3, strategy=STRATEGY_FIXED, base_backoff=0.0)
        ):
            assert eastmoney._fetch_index_kline_json("1.000300", 30) is None
        assert mock_client.get.call_count == 3

    @patch("src.python.providers.eastmoney.make_http_client")
    def test_http_500_not_retried(self, mock_factory):
        """HTTP 5xx（HTTPStatusError）非瞬时 → 不重试，直接降级。"""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_factory.return_value = mock_client
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
        mock_client.get.return_value = resp

        with patch.object(
            eastmoney, "_INDEX_RETRY_POLICY", RetryPolicy(attempts=3, strategy=STRATEGY_FIXED, base_backoff=0.0)
        ):
            assert eastmoney._fetch_index_kline_json("1.000300", 30) is None
        assert mock_client.get.call_count == 1
