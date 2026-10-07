"""tiantian_fund_fee F10 交易费率页 边缘/降级用例（@pytest.mark.edge 独立文件）。

覆盖：传输异常向上抛（熔断计数由 chain 统一）、表序颠倒/多表重复/全空行、
代码空白归一、行类型容忍——一律不抛解析器内部异常、不构造缺侧载荷。
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.python.providers import tiantian_fund_fee as tf
from src.python.providers.tiantian_fund_fee import fee_payload_is_valid, parse_fee_page

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers, pytest.mark.edge]


class _FakeResponse:
    def __init__(self, text: str, status_error: BaseException | None = None) -> None:
        self.text = text
        self.encoding = "utf-8"
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error


class _FakeClient:
    def __init__(self, response: _FakeResponse | None = None, request_error: BaseException | None = None):
        self._response = response
        self._request_error = request_error
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def get(self, url: str, headers: dict | None = None) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers})
        if self._request_error is not None:
            raise self._request_error
        assert self._response is not None
        return self._response


def _redemption_table(*rows: tuple[str, str]) -> str:
    head = "<table><tr><td>适用期限</td><td>赎回费率</td></tr>"
    body = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
    return head + body + "</table>"


class TestTransportPropagation:
    """传输级异常向上抛出——由 fetch_with_fallback 计熔断/重试（不吞成代码级 None）。"""

    def test_request_error_propagates(self, monkeypatch: pytest.MonkeyPatch):
        client = _FakeClient(request_error=httpx.ConnectError("boom"))
        monkeypatch.setattr(tf, "make_http_client", lambda **_kwargs: client)
        with pytest.raises(httpx.ConnectError):
            tf.fetch_fund_fee_page("002943")

    def test_http_status_error_propagates(self, monkeypatch: pytest.MonkeyPatch):
        client = _FakeClient(
            response=_FakeResponse(
                "", status_error=httpx.HTTPStatusError("503", request=MagicMock(), response=MagicMock())
            )
        )
        monkeypatch.setattr(tf, "make_http_client", lambda **_kwargs: client)
        with pytest.raises(httpx.HTTPStatusError):
            tf.fetch_fund_fee_page("002943")


class TestTableOrderingEdges:
    """表序/重复表/空行——解析器不依赖页面表的固定顺序。"""

    def test_discount_table_before_native_still_wins(self):
        """优惠表在原生表之前出现 → 仍取优惠表（顺序无关）。"""
        html = (
            "<table><tr><td>适用金额</td><td>原费率 | 天天基金优惠费率</td></tr>"
            "<tr><td>小于100万元</td><td>1.50% | 0.15%</td></tr></table>"
            "<table><tr><th>适用金额</th><th>费率</th></tr><tr><td>小于100万元</td><td>1.20%</td></tr></table>"
            + _redemption_table(("小于7天", "1.50%"))
        )
        payload = parse_fee_page(html)
        assert payload is not None
        assert payload["purchase_rows"][0][1] == "1.50% | 0.15%"

    def test_duplicate_redemption_tables_first_wins(self):
        """重复赎回表取首个（不拼接、不覆盖为后者）。"""
        html = _redemption_table(("小于7天", "1.50%")) + _redemption_table(("小于7天", "9.99%"))
        payload = parse_fee_page(html)
        assert payload is not None
        assert payload["redemption_rows"] == [["小于7天", "1.50%"]]

    def test_rows_with_empty_cells_filtered(self):
        """赎回表中空费率/空标签行被过滤；全过滤 → 无阶梯 → None。"""
        html = (
            "<table><tr><td>适用期限</td><td>赎回费率</td></tr>"
            "<tr><td>小于7天</td><td></td></tr>"
            "<tr><td></td><td>1.50%</td></tr></table>"
        )
        assert parse_fee_page(html) is None

    def test_entities_in_labels_unescaped(self):
        """标签中的 HTML 实体解码后进入原始行（&amp; 等不残留）。"""
        html = _redemption_table(("大于等于7天，小于30天", "0.75%")).replace("大于等于7天", "大于等于7天&amp;附录")
        payload = parse_fee_page(html)
        assert payload is not None
        assert payload["redemption_rows"][0][0] == "大于等于7天&附录，小于30天"


class TestFetchCodeNormalization:
    def test_code_is_stripped_for_url(self, monkeypatch: pytest.MonkeyPatch):
        """带空白的代码归一后再拼 URL（前后空格不产生 404 请求）。"""
        html = _redemption_table(("小于7天", "1.50%"))
        client = _FakeClient(response=_FakeResponse(html))
        monkeypatch.setattr(tf, "make_http_client", lambda **_kwargs: client)
        payload = tf.fetch_fund_fee_page("  002943 ")
        assert payload is not None
        assert client.calls[0]["url"].endswith("jjfl_002943.html")


class TestAkshareTupleRows:
    def test_tuple_rows_accepted_by_admission(self, monkeypatch: pytest.MonkeyPatch):
        """备链路行即使以元组呈现，准入按序列两格判定（不误杀）。"""

        class _DF:
            columns = ["适用期限", "赎回费率"]
            empty = False

            def to_dict(self, orient: str) -> list[dict[str, Any]]:
                return [{"适用期限": "小于7天", "赎回费率": "1.50%"}]

        class _Ak:
            def fund_fee_em(self, symbol: str = "", indicator: str = "") -> _DF:
                return _DF()

        monkeypatch.setitem(sys.modules, "akshare", _Ak())
        payload = tf.fetch_fund_fee_page_via_akshare("002943")
        assert payload is not None
        assert fee_payload_is_valid(payload) is True
