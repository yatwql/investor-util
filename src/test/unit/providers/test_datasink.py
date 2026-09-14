"""providers/datasink.py 单元测试。

覆盖：A 股符号映射、套餐感知的速率与配额派生、凭据缺失跳过、
HTTP 各状态码分支（401/429/非 200/非 JSON）、请求前限速与配额护栏、
列表/单篇/章节三个取数原语的响应解析。

运行：
  pytest src/test/unit/providers/test_datasink.py -v
"""

from __future__ import annotations

from datetime import date

import pytest

from src.python.providers import datasink as ds

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class _FakeResp:
    def __init__(self, status_code: int = 200, payload=None, json_error: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        return self._resp


def _prepare(monkeypatch, resp: _FakeResp) -> _FakeClient:
    client = _FakeClient(resp)
    monkeypatch.setattr(ds, "make_http_client", lambda **_kw: client)
    monkeypatch.setattr(ds, "credential_value", lambda _sid: "test-key")
    monkeypatch.setattr(ds, "missing_credential", lambda _sid: None)
    return client


# ── 符号映射 ────────────────────────────────────────────────


class TestFmpSymbol:
    def test_shanghai(self):
        assert ds.to_fmp_symbol("600519") == "600519.SS"
        assert ds.to_fmp_symbol("688981") == "688981.SS"

    def test_shenzhen(self):
        assert ds.to_fmp_symbol("000001") == "000001.SZ"
        assert ds.to_fmp_symbol("300750") == "300750.SZ"

    def test_beijing(self):
        assert ds.to_fmp_symbol("830799") == "830799.BJ"
        assert ds.to_fmp_symbol("920002") == "920002.BJ"

    def test_already_symbolic(self):
        assert ds.to_fmp_symbol("600519.SS") == "600519.SS"

    def test_non_a_share_returns_empty(self):
        assert ds.to_fmp_symbol("7203") == ""
        assert ds.to_fmp_symbol("AAPL") == ""
        assert ds.to_fmp_symbol("") == ""
        assert ds.to_fmp_symbol("12345") == ""


# ── 套餐感知的速率与配额 ────────────────────────────────────


class TestPlanLimits:
    def test_free_defaults(self):
        assert ds.resolve_requests_per_second({"plan": "free"}) == 3.0
        assert ds.resolve_daily_quota({"plan": "free"}) == 8191

    def test_yearly_defaults(self):
        assert ds.resolve_requests_per_second({"plan": "yearly"}) == 31.0
        assert ds.resolve_daily_quota({"plan": "yearly"}) == 131071

    def test_explicit_override_wins(self):
        assert ds.resolve_requests_per_second({"plan": "free", "requests_per_second": 1}) == 1.0
        assert ds.resolve_daily_quota({"plan": "free", "daily_quota": 100}) == 100

    def test_unknown_plan_falls_back_to_free(self):
        assert ds.resolve_requests_per_second({"plan": "enterprise"}) == 3.0


# ── 护栏：凭据 / 限速 / 配额 ────────────────────────────────


class TestGuards:
    def test_missing_credential_skips_without_http(self, monkeypatch):
        client = _FakeClient(_FakeResp(payload={"items": []}))
        monkeypatch.setattr(ds, "make_http_client", lambda **_kw: client)
        monkeypatch.setattr(ds, "missing_credential", lambda _sid: object())
        assert ds._request("/documents", {}) is None
        assert client.calls == []

    def test_limiter_acquired_before_request(self, monkeypatch):
        client = _prepare(monkeypatch, _FakeResp(payload={"items": []}))
        acquired: list[str] = []
        monkeypatch.setattr(ds, "_get_limiter", lambda: type("L", (), {"acquire": lambda _s, p: acquired.append(p)})())
        ds._request("/documents", {})
        assert acquired == ["datasink"]
        assert len(client.calls) == 1

    def test_quota_exhausted_skips_request(self, monkeypatch):
        client = _prepare(monkeypatch, _FakeResp(payload={"items": []}))
        monkeypatch.setattr(ds, "resolve_daily_quota", lambda: 1)
        monkeypatch.setattr(ds, "_read_quota", lambda: (date.today().isoformat(), 1))
        assert ds._request("/documents", {}) is None
        assert client.calls == []

    def test_quota_consumed_then_allows(self, monkeypatch, tmp_path):
        _prepare(monkeypatch, _FakeResp(payload={"items": []}))
        monkeypatch.setattr(ds, "_QUOTA_FILE", str(tmp_path / "quota.json"))
        monkeypatch.setattr(ds, "resolve_daily_quota", lambda: 2)
        assert ds._request("/documents", {}) is not None
        assert ds.quota_remaining() == 1


# ── HTTP 状态码分支 ─────────────────────────────────────────


class TestRequestStatus:
    def test_200_returns_dict(self, monkeypatch):
        client = _prepare(monkeypatch, _FakeResp(payload={"items": [{"id": 1}]}))
        data = ds._request("/documents", {"symbol": "600519.SS"})
        assert data == {"items": [{"id": 1}]}
        assert client.calls[0]["params"]["apikey"] == "test-key"
        assert client.calls[0]["params"]["symbol"] == "600519.SS"

    @pytest.mark.parametrize("status", [401, 403, 429, 500])
    def test_error_statuses_return_none(self, monkeypatch, status):
        _prepare(monkeypatch, _FakeResp(status_code=status, payload={}))
        assert ds._request("/documents", {}) is None

    def test_non_json_returns_none(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload=None, json_error=True))
        assert ds._request("/documents", {}) is None

    def test_network_error_returns_none(self, monkeypatch):
        def _boom(**_kw):
            raise OSError("unreachable")

        monkeypatch.setattr(ds, "make_http_client", _boom)
        monkeypatch.setattr(ds, "credential_value", lambda _sid: "test-key")
        monkeypatch.setattr(ds, "missing_credential", lambda _sid: None)
        assert ds._request("/documents", {}) is None

    def test_key_not_in_logs(self, monkeypatch, caplog):
        _prepare(monkeypatch, _FakeResp(status_code=401, payload={}))
        with caplog.at_level("WARNING"):
            ds._request("/documents", {})
        assert "test-key" not in caplog.text


# ── 取数原语 ────────────────────────────────────────────────


class TestFetchPrimitives:
    def test_documents_returns_items(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload={"items": [{"id": 7, "symbol": "600519.SS"}]}))
        assert ds.fetch_report_documents("600519.SS", doc_type="annual") == [{"id": 7, "symbol": "600519.SS"}]

    def test_documents_missing_items_returns_none(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload={"total": 0}))
        assert ds.fetch_report_documents("600519.SS") is None

    def test_document_passes_section(self, monkeypatch):
        client = _prepare(monkeypatch, _FakeResp(payload={"id": 7, "content": "# x"}))
        data = ds.fetch_report_document(7, section="管理层讨论与分析")
        assert data["id"] == 7
        assert client.calls[0]["params"]["section"] == "管理层讨论与分析"

    def test_sections_returns_titles(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload={"sections": ["第一节", "管理层讨论与分析"]}))
        assert ds.fetch_report_sections(7) == ["第一节", "管理层讨论与分析"]

    def test_sections_non_list_returns_none(self, monkeypatch):
        _prepare(monkeypatch, _FakeResp(payload={"sections": "oops"}))
        assert ds.fetch_report_sections(7) is None
