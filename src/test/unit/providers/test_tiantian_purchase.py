"""tiantian_purchase 申购状态总表 — 解析与抓取单元测试。

测试目标（设计文档 docs/plan/fund-purchase-limit-design.md §7 用例清单）：
  - 解析器：真实响应样本 fixture 的四类代表行（开放/限大额正常金额/限大额 0 元/
    暂停申购 + 下一开放日）→ PurchaseStatus 契约字段逐项断言
  - 载荷字段：purchase_schema 语义版本 + fetched_at 北京时区时间串 + 6 位代码键
  - 备链路：akshare 封装的字段映射与空表取不到
  - 直连抓取：经调用点 make_http_client 注入的传输桩走完整抓取路径（零出网）

运行：
  pytest src/test/unit/providers/test_tiantian_purchase.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.python.providers import tiantian_purchase as tp
from src.python.providers.tiantian_purchase import (
    PURCHASE_SCHEMA,
    PURCHASE_SCHEMA_FIELD,
    parse_purchase_table,
    stamp_purchase_payload,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]

_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "fund_purchase_table.txt"
_PAYLOAD_PREFIX = "var reData="


def _fixture_text() -> str:
    """读取真实响应样本（含 var reData= 前缀的完整响应体）。"""
    return _FIXTURE.read_text(encoding="utf-8")


# ── 传输桩（调用点注入，零出网） ──────────────────────────────


class _FakeResponse:
    """httpx.Response 的最小桩：文本 + raise_for_status 契约。"""

    def __init__(self, text: str, status_error: BaseException | None = None) -> None:
        self.text = text
        self.encoding = "utf-8"
        self._status_error = status_error

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error


class _FakeClient:
    """make_http_client 的最小桩：记录请求参数并返回预置响应。"""

    def __init__(self, response: _FakeResponse | None = None, request_error: BaseException | None = None):
        self._response = response
        self._request_error = request_error
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def get(self, url: str, params: dict | None = None, headers: dict | None = None) -> _FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        if self._request_error is not None:
            raise self._request_error
        assert self._response is not None
        return self._response


class _FakeDataFrame:
    """akshare fund_purchase_em() 返回的 DataFrame 最小鸭子桩。"""

    def __init__(self, records: list[dict[str, Any]], empty: bool = False) -> None:
        self._records = records
        self.empty = empty

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return self._records


class _FakeAkshare:
    def __init__(self, df: _FakeDataFrame) -> None:
        self._df = df

    def fund_purchase_em(self) -> _FakeDataFrame:
        return self._df


# ============================================================
#  解析器：四类代表行
# ============================================================


class TestParsePurchaseTable:
    """parse_purchase_table 真实样本解析 → 契约字段逐项断言。"""

    def test_payload_carries_schema_version_and_fetched_at(self):
        """载荷含 purchase_schema 版本字段与北京时区 fetched_at。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        assert payload[PURCHASE_SCHEMA_FIELD] == PURCHASE_SCHEMA
        fetched = datetime.fromisoformat(payload["fetched_at"])
        assert fetched.tzinfo is not None  # 陈旧阶梯按其与交易日历的距离判定

    def test_open_subscription_row(self):
        """代表行①：开放申购 + 超大日限（开放基金的无实质限制口径）。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        row = payload["rows"]["000001"]
        assert row["purchase_status"] == "开放申购"
        assert row["redemption_status"] == "开放赎回"
        assert row["next_open_date"] == ""
        assert row["daily_limit"] == pytest.approx(100_000_000_000.0)
        assert row["min_purchase"] == pytest.approx(10.0)

    def test_fee_rate_col12_parsed_to_fraction(self):
        """col12 手续费（"0.15%"）→ purchase_fee_rate 小数 0.0015（单档申购费率）。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        rows = payload["rows"]
        assert rows["000001"]["purchase_fee_rate"] == pytest.approx(0.0015)
        assert rows["000005"]["purchase_fee_rate"] == pytest.approx(0.0008)

    def test_fee_rate_zero_is_known_zero(self):
        """ "0.00%" → 0.0（已知 0 费率，与未知 None 严格区分——C 类无申购费）。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        assert payload["rows"]["000013"]["purchase_fee_rate"] == 0.0

    def test_limited_rows_with_daily_caps(self):
        """代表行②：限大额 + 正常日限金额（QDII 主场景，两只不同档位）。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        rows = payload["rows"]
        assert rows["000041"]["purchase_status"] == "限大额"
        assert rows["000041"]["daily_limit"] == pytest.approx(10_000.0)
        assert rows["000043"]["purchase_status"] == "限大额"
        assert rows["000043"]["daily_limit"] == pytest.approx(100.0)

    def test_limited_row_with_zero_cap_maps_to_none(self):
        """代表行③：限大额但日限 0 元 → 解析层单点转换为 None（限额未知，风险 R4）。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        row = payload["rows"]["000013"]
        assert row["purchase_status"] == "限大额"
        assert row["daily_limit"] is None

    def test_suspended_row_with_next_open_date(self):
        """代表行④：暂停申购 + 下一开放日原样保留。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        row = payload["rows"]["000005"]
        assert row["purchase_status"] == "暂停申购"
        assert row["redemption_status"] == "暂停赎回"
        assert row["next_open_date"] == "2026-12-08"

    def test_row_keys_are_six_digit_codes(self):
        """行键全部为 6 位数字代码（位置解析产物的结构约束）。"""
        payload = parse_purchase_table(_fixture_text())
        assert payload is not None
        assert payload["rows"], "样本应解析出非空行集"
        for code in payload["rows"]:
            assert len(code) == 6 and code.isdigit()

    def test_bare_object_body_without_prefix_parses(self):
        """剥掉 var reData= 前缀的裸对象体同样可解析（前缀剥离为等价变换）。"""
        body = _fixture_text().strip()
        assert body.startswith(_PAYLOAD_PREFIX)
        payload = parse_purchase_table(body[len(_PAYLOAD_PREFIX) :])
        assert payload is not None
        assert "000041" in payload["rows"]


# ============================================================
#  载荷组装单点
# ============================================================


class TestStampPurchasePayload:
    """stamp_purchase_payload — 直连/备链路共用的载荷组装单点。"""

    def test_stamps_schema_and_rows(self):
        """rows 原样进入载荷并盖上语义版本与抓取时间。"""
        rows = {"000001": {"purchase_status": "开放申购"}}
        payload = stamp_purchase_payload(rows)
        assert payload["rows"] is rows
        assert payload[PURCHASE_SCHEMA_FIELD] == PURCHASE_SCHEMA
        assert datetime.fromisoformat(payload["fetched_at"]).tzinfo is not None


# ============================================================
#  备链路：akshare 封装映射
# ============================================================


class TestAkshareBackupParse:
    """fetch_fund_purchase_table_via_akshare — 字段映射（stub sys.modules，零出网）。"""

    def _stub_akshare(self, monkeypatch: pytest.MonkeyPatch, df: _FakeDataFrame) -> None:
        monkeypatch.setitem(sys.modules, "akshare", _FakeAkshare(df))

    def test_maps_record_fields(self, monkeypatch: pytest.MonkeyPatch):
        """中文列名 → 六键契约；日限 0 → None、下一开放日截到 10 位。"""
        df = _FakeDataFrame(
            [
                {
                    "基金代码": "000041",
                    "申购状态": "限大额",
                    "赎回状态": "开放赎回",
                    "下一开放日": "",
                    "日累计限定金额": 10000.0,
                    "购买起点": 10.0,
                },
                {
                    "基金代码": "000013",
                    "申购状态": "限大额",
                    "赎回状态": "开放赎回",
                    "下一开放日": None,
                    "日累计限定金额": 0,
                    "购买起点": "0",
                },
            ]
        )
        self._stub_akshare(monkeypatch, df)
        payload = tp.fetch_fund_purchase_table_via_akshare()
        assert payload is not None
        assert payload[PURCHASE_SCHEMA_FIELD] == PURCHASE_SCHEMA
        assert payload["rows"]["000041"]["daily_limit"] == pytest.approx(10_000.0)
        assert payload["rows"]["000041"]["min_purchase"] == pytest.approx(10.0)
        assert payload["rows"]["000013"]["daily_limit"] is None  # 0 → 限额未知
        assert payload["rows"]["000013"]["next_open_date"] == ""

    def test_maps_fee_rate_percent_number(self, monkeypatch: pytest.MonkeyPatch):
        """akshare「手续费」列（已剥 % 的百分数 0.15）→ 小数 0.0015；缺列/脏值 → None。"""
        df = _FakeDataFrame(
            [
                {"基金代码": "000001", "申购状态": "开放申购", "手续费": 0.15},
                {"基金代码": "000013", "申购状态": "开放申购", "手续费": 0.0},
                {"基金代码": "000041", "申购状态": "限大额"},  # 缺列 → 未知
                {"基金代码": "000043", "申购状态": "开放申购", "手续费": float("nan")},
            ]
        )
        self._stub_akshare(monkeypatch, df)
        payload = tp.fetch_fund_purchase_table_via_akshare()
        assert payload is not None
        assert payload["rows"]["000001"]["purchase_fee_rate"] == pytest.approx(0.0015)
        assert payload["rows"]["000013"]["purchase_fee_rate"] == 0.0
        assert payload["rows"]["000041"]["purchase_fee_rate"] is None
        assert payload["rows"]["000043"]["purchase_fee_rate"] is None

    def test_empty_frame_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        """空 DataFrame 视为取不到（返回 None 走下一槽位）。"""
        self._stub_akshare(monkeypatch, _FakeDataFrame([], empty=True))
        assert tp.fetch_fund_purchase_table_via_akshare() is None

    def test_skips_rows_without_code(self, monkeypatch: pytest.MonkeyPatch):
        """无代码行跳过；其余行照常映射（不因单行脏数据丢整表）。"""
        df = _FakeDataFrame(
            [
                {"基金代码": "", "申购状态": "限大额"},
                {"基金代码": "000043", "申购状态": "限大额", "日累计限定金额": 100.0},
            ]
        )
        self._stub_akshare(monkeypatch, df)
        payload = tp.fetch_fund_purchase_table_via_akshare()
        assert payload is not None
        assert "000043" in payload["rows"]
        assert all(code for code in payload["rows"])


# ============================================================
#  直连抓取：调用点传输桩
# ============================================================


class TestDirectFetch:
    """fetch_fund_purchase_table — 经调用点 make_http_client 的抓取路径。"""

    def test_gets_endpoint_with_headers_and_parses(self, monkeypatch: pytest.MonkeyPatch):
        """请求端点 + Referer/UA 头 + 剥前缀解析出载荷。"""
        client = _FakeClient(response=_FakeResponse(_fixture_text()))
        monkeypatch.setattr(tp, "make_http_client", lambda **_kwargs: client)
        payload = tp.fetch_fund_purchase_table()
        assert payload is not None
        assert payload[PURCHASE_SCHEMA_FIELD] == PURCHASE_SCHEMA
        assert "000005" in payload["rows"]
        assert len(client.calls) == 1
        call = client.calls[0]
        assert call["url"] == tp._ENDPOINT_URL
        assert call["params"] == tp._ENDPOINT_PARAMS
        assert call["headers"]["Referer"] == "https://fund.eastmoney.com/"
        assert call["headers"]["User-Agent"]
