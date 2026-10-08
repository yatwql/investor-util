"""tiantian_fund_fee F10 交易费率页 — 解析、准入与抓取单元测试。

测试目标（whatif-cost-benchmark-design §11）：
  - 解析器：真实页面结构（9 表）中定位赎回阶梯表与申购档位表——优惠表优先于
    原生表、干扰表（申购状态/运作费用等）自动跳过、实体与空白归一
  - 准入：fee_schema 语义版本 + 赎回阶梯非空硬条件 + 行结构体检
  - 抓取：调用点 make_http_client 传输桩走完整路径（零出网）
  - 备链路：akshare fund_fee_em 封装（stub sys.modules，零出网）

运行：
  pytest src/test/unit/providers/test_tiantian_fund_fee.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

import pytest

from src.python.providers import tiantian_fund_fee as tf
from src.python.providers.tiantian_fund_fee import (
    FEE_SCHEMA,
    FEE_SCHEMA_FIELD,
    fee_payload_is_valid,
    parse_fee_page,
    stamp_fee_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


# ── 页面 fixture（镜像真实 F10 交易费率页的表结构与实体） ────────


def _page_html(
    *,
    with_native_purchase: bool = True,
    with_discount_purchase: bool = True,
    with_redemption: bool = True,
    with_nav_noise: bool = True,
) -> str:
    """构造最小真实结构页：干扰表 + （原生/优惠）申购表 + 赎回阶梯表。"""
    parts: list[str] = []
    if with_nav_noise:
        parts.append("<table><tr><td>管理费率</td><td>1.20%（每年）</td></tr></table>")
        parts.append("<table><tr><td>申购状态</td><td>开放申购</td></tr></table>")
    if with_native_purchase:
        parts.append(
            "<table><tr><th>适用金额</th><th> 费率 </th></tr>"
            "<tr><td>小于100万元</td><td>1.20%</td></tr>"
            "<tr><td>大于等于100万元</td><td>0.80%</td></tr></table>"
        )
    if with_discount_purchase:
        parts.append(
            "<table><tr><td>适用金额</td><td>原费率&nbsp;&nbsp;|&nbsp;&nbsp;天天基金优惠费率</td></tr>"
            "<tr><td>小于100万元</td><td> 1.50% &nbsp;&nbsp;|&nbsp;&nbsp;0.15%</td></tr>"
            "<tr><td>大于等于100万元</td><td> 0.90% &nbsp;&nbsp;|&nbsp;&nbsp;0.09%</td></tr></table>"
        )
    if with_redemption:
        parts.append(
            "<table><tr><td>适用期限</td><td>赎回费率</td></tr>"
            "<tr><td>小于7天</td><td>1.50%</td></tr>"
            "<tr><td>大于等于7天，小于30天</td><td>0.75%</td></tr>"
            "<tr><td>大于等于730天</td><td>0.00%</td></tr></table>"
        )
    return "<html><body>" + "".join(parts) + "</body></html>"


# ============================================================
#  解析器：表头定位与取行
# ============================================================


class TestParseFeePage:
    """parse_fee_page — 真实结构页 → 原始行契约逐项断言。"""

    def test_redemption_rows_parsed_exactly(self):
        """赎回阶梯表定位（适用期限+赎回费率）→ 行逐字断言。"""
        payload = parse_fee_page(_page_html())
        assert payload is not None
        assert payload["redemption_rows"] == [
            ["小于7天", "1.50%"],
            ["大于等于7天，小于30天", "0.75%"],
            ["大于等于730天", "0.00%"],
        ]

    def test_discount_purchase_table_preferred(self):
        """两张「适用金额」表并存 → 取带「优惠」的天天基金优惠表（非原生表）。"""
        payload = parse_fee_page(_page_html())
        assert payload is not None
        assert payload["purchase_rows"] == [
            ["小于100万元", "1.50% | 0.15%"],
            ["大于等于100万元", "0.90% | 0.09%"],
        ]
        assert "1.20%" not in payload["purchase_rows"][0][1]  # 原生表未被选中

    def test_native_purchase_table_used_when_no_discount(self):
        """无优惠表 → 退原生「适用金额+费率」表；干扰表（管理费率/申购状态）不参与。"""
        payload = parse_fee_page(_page_html(with_discount_purchase=False))
        assert payload is not None
        assert payload["purchase_rows"] == [
            ["小于100万元", "1.20%"],
            ["大于等于100万元", "0.80%"],
        ]

    def test_missing_purchase_table_keeps_empty(self):
        """无任何申购表（C 类/场内）→ purchase_rows 为空列表（如实为空，不编造）。"""
        payload = parse_fee_page(_page_html(with_native_purchase=False, with_discount_purchase=False))
        assert payload is not None
        assert payload["purchase_rows"] == []

    def test_missing_redemption_table_returns_none(self):
        """无赎回阶梯表（场内基金页）→ 整载荷判失败（不返回缺侧载荷冒充成功）。"""
        assert parse_fee_page(_page_html(with_redemption=False)) is None

    def test_invalid_inputs_return_none(self):
        """None/非字符串/空串/无表 HTML → None（不抛、不猜）。"""
        assert parse_fee_page(None) is None
        assert parse_fee_page(b"<html></html>") is None  # type: ignore[arg-type]
        assert parse_fee_page("") is None
        assert parse_fee_page("<html><body>没有表格</body></html>") is None


# ============================================================
#  准入校验：fee_payload_is_valid
# ============================================================


class TestPayloadAdmission:
    """写侧/读侧共用判据：语义版本 + 赎回非空 + 行结构。"""

    def test_valid_payload_passes(self):
        assert fee_payload_is_valid(stamp_fee_payload([["小于7天", "1.50%"]], [])) is True

    def test_schema_mismatch_rejected(self):
        """fee_schema 不等于当前版本（旧结构缓存）→ 拒绝按未命中丢弃。"""
        payload = stamp_fee_payload([["小于7天", "1.50%"]], [])
        assert fee_payload_is_valid({**payload, FEE_SCHEMA_FIELD: FEE_SCHEMA + 99}) is False
        assert fee_payload_is_valid({"redemption_rows": [["a", "1%"]], "purchase_rows": []}) is False

    def test_empty_redemption_rejected(self):
        """赎回阶梯缺失/为空 → 拒绝（核心侧缺失即整载荷失败）。"""
        assert fee_payload_is_valid(stamp_fee_payload([], [])) is False
        payload = stamp_fee_payload([["小于7天", "1.50%"]], [])
        assert fee_payload_is_valid({**payload, "redemption_rows": None}) is False

    def test_missing_fetched_at_rejected(self):
        payload = stamp_fee_payload([["小于7天", "1.50%"]], [])
        assert fee_payload_is_valid({**payload, "fetched_at": ""}) is False

    def test_bad_row_shape_rejected(self):
        """行不足 2 列 / 格非字符串 / 空格 → 拒绝（结构漂移不入缓存）。"""
        base = stamp_fee_payload([["小于7天", "1.50%"]], [])
        assert fee_payload_is_valid({**base, "redemption_rows": [["小于7天"]]}) is False
        assert fee_payload_is_valid({**base, "redemption_rows": [["小于7天", ""]]}) is False
        assert fee_payload_is_valid({**base, "redemption_rows": [["小于7天", 1.5]]}) is False
        assert fee_payload_is_valid({**base, "purchase_rows": [["小于100万元"]]}) is False

    def test_purchase_rows_missing_key_rejected(self):
        payload = stamp_fee_payload([["小于7天", "1.50%"]], [])
        assert fee_payload_is_valid({k: v for k, v in payload.items() if k != "purchase_rows"}) is False

    def test_non_dict_rejected(self):
        assert fee_payload_is_valid(None) is False
        assert fee_payload_is_valid(["rows"]) is False

    def test_stamp_carries_schema_and_tz_fetched_at(self):
        payload = stamp_fee_payload([["小于7天", "1.50%"]], [])
        assert payload[FEE_SCHEMA_FIELD] == FEE_SCHEMA
        fetched = datetime.fromisoformat(payload["fetched_at"])
        assert fetched.tzinfo is not None


# ============================================================
#  直连抓取：调用点传输桩
# ============================================================


class _FakeResponse:
    """httpx.Response 最小桩：文本 + raise_for_status 契约。"""

    def __init__(self, text: str, status_error: BaseException | None = None) -> None:
        self.text = text
        self.encoding = "utf-8"
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error


class _FakeClient:
    """make_http_client 最小桩：记录请求并返回预置响应。"""

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


class TestDirectFetch:
    """fetch_fund_fee_page — 经调用点 make_http_client 的抓取路径。"""

    def test_gets_fee_page_with_headers_and_parses(self, monkeypatch: pytest.MonkeyPatch):
        """请求 jjfl 页 + Referer/UA 头 + 解析出赎回与申购行。"""
        client = _FakeClient(response=_FakeResponse(_page_html()))
        monkeypatch.setattr(tf, "make_http_client", lambda **_kwargs: client)
        payload = tf.fetch_fund_fee_page("002943")
        assert payload is not None
        assert payload[FEE_SCHEMA_FIELD] == FEE_SCHEMA
        assert payload["redemption_rows"][0] == ["小于7天", "1.50%"]
        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["url"] == tf._FEE_URL.format(code="002943")
        assert call["headers"]["Referer"] == "https://fund.eastmoney.com/"

    def test_parse_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        """页面无赎回表 → 代码级空结果（None，不计熔断）。"""
        client = _FakeClient(response=_FakeResponse(_page_html(with_redemption=False)))
        monkeypatch.setattr(tf, "make_http_client", lambda **_kwargs: client)
        assert tf.fetch_fund_fee_page("561910") is None


# ============================================================
#  备链路：akshare fund_fee_em 封装
# ============================================================


class _FakeFeeDataFrame:
    """akshare fund_fee_em() 返回的 DataFrame 最小鸭子桩。"""

    def __init__(self, columns: list[str], records: list[dict[str, Any]], empty: bool = False) -> None:
        self.columns = columns
        self._records = records
        self.empty = empty

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return self._records


class _FakeFeeAkshare:
    def __init__(self, df: _FakeFeeDataFrame | None, raise_keyerror: bool = False) -> None:
        self._df = df
        self._raise_keyerror = raise_keyerror

    def fund_fee_em(self, symbol: str = "", indicator: str = "") -> _FakeFeeDataFrame:
        if self._raise_keyerror:
            raise KeyError(indicator)
        assert self._df is not None
        return self._df


class TestAkshareBackupParse:
    """fetch_fund_fee_page_via_akshare — 解析器冗余（stub sys.modules，零出网）。"""

    def test_maps_redemption_rows(self, monkeypatch: pytest.MonkeyPatch):
        """中文列名 → 赎回原始行；purchase_rows 恒为空（单档/配置承接申购）。"""
        df = _FakeFeeDataFrame(
            ["适用期限", "赎回费率"],
            [
                {"适用期限": "小于7天", "赎回费率": "1.50%"},
                {"适用期限": "大于等于730天", "赎回费率": "0.00%"},
            ],
        )
        monkeypatch.setitem(sys.modules, "akshare", _FakeFeeAkshare(df))
        payload = tf.fetch_fund_fee_page_via_akshare("002943")
        assert payload is not None
        assert payload["redemption_rows"] == [["小于7天", "1.50%"], ["大于等于730天", "0.00%"]]
        assert payload["purchase_rows"] == []
        assert fee_payload_is_valid(payload) is True

    def test_keyerror_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        """页面无赎回费率表（KeyError）→ 代码级取不到（None 走兜底）。"""
        monkeypatch.setitem(sys.modules, "akshare", _FakeFeeAkshare(None, raise_keyerror=True))
        assert tf.fetch_fund_fee_page_via_akshare("561910") is None

    def test_empty_or_narrow_frame_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        """空表 / 列不足 2 / 全空行 → None（不构造空载荷冒充成功）。"""
        monkeypatch.setitem(sys.modules, "akshare", _FakeFeeAkshare(_FakeFeeDataFrame([], [], empty=True)))
        assert tf.fetch_fund_fee_page_via_akshare("002943") is None
        monkeypatch.setitem(sys.modules, "akshare", _FakeFeeAkshare(_FakeFeeDataFrame(["适用期限"], [])))
        assert tf.fetch_fund_fee_page_via_akshare("002943") is None
        monkeypatch.setitem(
            sys.modules,
            "akshare",
            _FakeFeeAkshare(_FakeFeeDataFrame(["适用期限", "赎回费率"], [{"适用期限": "  ", "赎回费率": ""}])),
        )
        assert tf.fetch_fund_fee_page_via_akshare("002943") is None
