"""providers/cninfo.py 单元测试（财报域备源）。

覆盖：orgId 解析与缓存、公告列表取数与文种归类（年报/半年报/季报、摘要剔除、
报告期推导）、列表缓存、PDF 正文下载解析与缓存、缺 pdfplumber 的优雅降级、
HTTP 异常/非 200/非 JSON/429 退避分支、限速器调用、**连接级瞬时失败重试一次**。

HTTP 一律 mock（``monkeypatch.setattr(cn, "make_http_client", ...)``，与
``test_datasink.py`` 同模式）；PDF 解析打桩在 ``_parse_pdf_text`` 接缝
（本机无需安装 pdfplumber）。

运行：pytest src/test/unit/providers/test_cninfo.py -v
"""

from __future__ import annotations

import httpx
import pytest

from src.python.providers import cninfo as cn

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class _FakeResp:
    def __init__(self, status_code: int = 200, payload=None, content: bytes = b"", json_error: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    """按 URL 后缀分派响应；记录调用供断言。"""

    def __init__(self, post_map: dict[str, _FakeResp] | None = None, get_resp: _FakeResp | None = None) -> None:
        self._post_map = post_map or {}
        self._get_resp = get_resp
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def post(self, url, data=None, headers=None):
        self.posts.append((url, dict(data or {})))
        for suffix, resp in self._post_map.items():
            if url.endswith(suffix):
                return resp
        return _FakeResp(status_code=404)

    def get(self, url, headers=None):
        self.gets.append(url)
        return self._get_resp or _FakeResp(status_code=404)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """缓存与限速器隔离：不落真实缓存目录、不真正阻塞。"""
    cn.reset_cninfo_limiter()
    store: dict = {}
    monkeypatch.setattr(cn, "cache_get", lambda key, ttl=None: store.get(key))
    monkeypatch.setattr(cn, "cache_set", lambda key, value: store.setdefault(key, value))
    monkeypatch.setattr(cn, "get_ttl", lambda module, key=None: 1.0)
    # 限速器换成零等待替身：真实 RateLimiter 会在同一用例内的多次请求间真 sleep
    monkeypatch.setattr(cn, "_get_limiter", lambda: _NoWaitLimiter())
    yield store
    cn.reset_cninfo_limiter()


class _NoWaitLimiter:
    """零等待限速器替身（记录调用；断言如需可改回真实实现）。"""

    def __init__(self) -> None:
        self.acquired: list[str] = []

    def acquire(self, name: str) -> None:
        self.acquired.append(name)


def _patch_client(monkeypatch, client) -> None:
    monkeypatch.setattr(cn, "make_http_client", lambda **_kw: client)


def _list_payload(items: list[dict]) -> _FakeResp:
    return _FakeResp(payload={"announcements": items})


def _ann(title: str, ann_id: str = "121", adjunct: str = "finalpage/2026-03-28/121.PDF") -> dict:
    return {
        "announcementTitle": title,
        "announcementId": ann_id,
        "adjunctUrl": adjunct,
        "announcementTime": 1774656000000,
    }


class TestResolveOrgId:
    """orgId 解析（列表查询的必需参数）。"""

    def test_resolves_and_caches(self, monkeypatch, _isolate):
        client = _FakeClient(
            post_map={
                "/topSearch/query": _FakeResp(payload={"keyBoardList": [{"code": "601398", "orgId": "gssh0601398"}]})
            }
        )
        _patch_client(monkeypatch, client)
        assert cn.resolve_org_id("601398") == "601398,gssh0601398"
        # 第二次命中缓存，不再发请求
        assert cn.resolve_org_id("601398") == "601398,gssh0601398"
        assert len(client.posts) == 1

    def test_missing_org_id_returns_none(self, monkeypatch, _isolate):
        _patch_client(monkeypatch, _FakeClient(post_map={"/topSearch/query": _FakeResp(payload={"keyBoardList": []})}))
        assert cn.resolve_org_id("601398") is None

    def test_empty_code(self, _isolate):
        assert cn.resolve_org_id("") is None


class TestFetchReportListings:
    """:func:`cninfo.fetch_report_listings` —— 公告列表归一为与主源同一形状。"""

    def _client(self, announcements: list[dict]) -> _FakeClient:
        return _FakeClient(
            post_map={
                "/topSearch/query": _FakeResp(payload={"keyBoardList": [{"code": "601398", "orgId": "gssh0601398"}]}),
                "/hisAnnouncement/query": _list_payload(announcements),
            }
        )

    def test_classifies_doc_types_and_periods(self, monkeypatch, _isolate):
        client = self._client(
            [
                _ann("中国工商银行2025年年度报告", "1001"),
                _ann("中国工商银行2026年半年度报告", "1002"),
                _ann("中国工商银行2026年第一季度报告", "1003"),
                _ann("中国工商银行2025年第三季度报告", "1004"),
            ]
        )
        _patch_client(monkeypatch, client)
        items = cn.fetch_report_listings("601398")
        by_id = {i["id"]: i for i in items}
        assert by_id["1001"]["doc_type"] == "annual" and by_id["1001"]["report_period"] == "2025-12-31"
        # 半年度必须先于年度判定（「半年度报告」含「年度报告」子串）
        assert by_id["1002"]["doc_type"] == "semiannual" and by_id["1002"]["report_period"] == "2026-06-30"
        assert by_id["1003"]["doc_type"] == "q1" and by_id["1003"]["report_period"] == "2026-03-31"
        assert by_id["1004"]["doc_type"] == "q3" and by_id["1004"]["report_period"] == "2025-09-30"

    def test_requests_only_financial_categories(self, monkeypatch, _isolate):
        """列表查询只查财报类目。

        回归背景：按全部类目（``category_szsh;``）查时第 1 页 30 条可能全是普通公告
        （实测工商银行），而列表只取第 1 页 → 候选为空 → 巨潮备源对该标的静默失效。
        """
        client = self._client([])
        _patch_client(monkeypatch, client)
        cn.fetch_report_listings("600900")

        listing_payloads = [payload for url, payload in client.posts if "hisAnnouncement" in url]
        assert listing_payloads
        assert all(p.get("category") == cn._FINANCIAL_CATEGORIES for p in listing_payloads)
        assert "category_ndbg_szsh;" in cn._FINANCIAL_CATEGORIES
        assert "category_bndbg_szsh;" in cn._FINANCIAL_CATEGORIES

    def test_skips_abstract_and_missing_fields(self, monkeypatch, _isolate):
        client = self._client(
            [
                _ann("中国工商银行2025年年度报告摘要", "2001"),
                _ann("中国工商银行2025年年度报告（英文版）", "2002"),
                _ann("关于召开2026年第一次临时股东大会的通知", "2003"),
                _ann("中国工商银行2025年年度报告", "2004", adjunct=""),
            ]
        )
        _patch_client(monkeypatch, client)
        assert cn.fetch_report_listings("601398") is None

    def test_result_shape_matches_primary_index(self, monkeypatch, _isolate):
        """条目形状与主源索引一致（编排层候选排序/回溯零改动复用）。"""
        _patch_client(monkeypatch, self._client([_ann("中国工商银行2025年年度报告", "3001")]))
        item = cn.fetch_report_listings("601398")[0]
        assert {
            "id",
            "doc_type",
            "report_period",
            "title",
            "announcement_time",
            "word_count",
            "adjunct_url",
            "source",
        } <= set(item)
        assert item["source"] == cn.SOURCE_ID

    def test_sorted_by_period_desc(self, monkeypatch, _isolate):
        _patch_client(
            monkeypatch,
            self._client([_ann("中国工商银行2025年年度报告", "4001"), _ann("中国工商银行2026年半年度报告", "4002")]),
        )
        items = cn.fetch_report_listings("601398")
        assert [i["id"] for i in items] == ["4002", "4001"]

    def test_listing_cached(self, monkeypatch, _isolate):
        client = self._client([_ann("中国工商银行2025年年度报告", "5001")])
        _patch_client(monkeypatch, client)
        cn.fetch_report_listings("601398")
        cn.fetch_report_listings("601398")
        assert len([u for u, _ in client.posts if u.endswith("/hisAnnouncement/query")]) == 1

    def test_http_failure_returns_none(self, monkeypatch, _isolate):
        _patch_client(
            monkeypatch,
            _FakeClient(
                post_map={
                    "/topSearch/query": _FakeResp(payload={"keyBoardList": [{"code": "601398", "orgId": "x"}]}),
                    "/hisAnnouncement/query": _FakeResp(status_code=500),
                }
            ),
        )
        assert cn.fetch_report_listings("601398") is None


class TestFetchReportText:
    """:func:`cninfo.fetch_report_text` —— PDF 下载 + 文本解析 + 缓存。"""

    def test_downloads_parses_and_caches(self, monkeypatch, _isolate):
        client = _FakeClient(get_resp=_FakeResp(content=b"%PDF-1.4 fake"))
        _patch_client(monkeypatch, client)
        parsed: list[bytes] = []
        monkeypatch.setattr(cn, "_parse_pdf_text", lambda b: parsed.append(b) or "全文正文内容")
        text = cn.fetch_report_text("1001", "finalpage/2026-03-28/1001.PDF")
        assert text == "全文正文内容" and len(parsed) == 1
        assert client.gets[0].startswith(cn._STATIC_BASE)
        # 第二次命中文本缓存，不再下载解析
        assert cn.fetch_report_text("1001", "finalpage/2026-03-28/1001.PDF") == "全文正文内容"
        assert len(parsed) == 1

    def test_absolute_url_used_as_is(self, monkeypatch, _isolate):
        client = _FakeClient(get_resp=_FakeResp(content=b"%PDF"))
        _patch_client(monkeypatch, client)
        monkeypatch.setattr(cn, "_parse_pdf_text", lambda b: "x")
        cn.fetch_report_text("1002", "http://static.cninfo.com.cn/a.PDF")
        assert client.gets[0] == "http://static.cninfo.com.cn/a.PDF"

    def test_missing_inputs(self, _isolate):
        assert cn.fetch_report_text("", "a.PDF") == ""
        assert cn.fetch_report_text("1003", "") == ""

    def test_download_failure_returns_empty(self, monkeypatch, _isolate):
        _patch_client(monkeypatch, _FakeClient(get_resp=_FakeResp(status_code=404)))
        assert cn.fetch_report_text("1004", "a.PDF") == ""

    def test_parse_failure_returns_empty(self, monkeypatch, _isolate):
        _patch_client(monkeypatch, _FakeClient(get_resp=_FakeResp(content=b"broken")))
        monkeypatch.setattr(cn, "_parse_pdf_text", lambda b: "")
        assert cn.fetch_report_text("1005", "a.PDF") == ""


class TestParsePdfText:
    """PDF 解析接缝：缺 pdfplumber 时优雅降级（不抛异常）。"""

    def test_missing_pdfplumber_returns_empty(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "pdfplumber":
                raise ImportError("no pdfplumber")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        assert cn._parse_pdf_text(b"%PDF-1.4") == ""

    def test_corrupt_pdf_returns_empty(self):
        """非 PDF 字节：解析失败返回空串（不抛异常）。"""
        assert cn._parse_pdf_text(b"not a pdf at all") == ""


class TestGuards:
    """限速与 HTTP 分支。"""

    def test_rate_limiter_acquired_per_request(self, monkeypatch, _isolate):
        acquired: list[str] = []
        limiter = type("L", (), {"acquire": lambda self, name: acquired.append(name)})()
        monkeypatch.setattr(cn, "_get_limiter", lambda: limiter)
        _patch_client(monkeypatch, _FakeClient(post_map={"/topSearch/query": _FakeResp(payload={"keyBoardList": []})}))
        cn.resolve_org_id("601398")
        assert acquired == [cn.SOURCE_ID]

    def test_non_json_response_returns_none(self, monkeypatch, _isolate):
        _patch_client(monkeypatch, _FakeClient(post_map={"/topSearch/query": _FakeResp(json_error=True)}))
        assert cn.resolve_org_id("601398") is None

    def test_429_retries_once_then_succeeds(self, monkeypatch, _isolate):
        class _SeqClient:
            def __init__(self):
                self.calls = 0

            def post(self, url, data=None, headers=None):
                self.calls += 1
                if self.calls == 1:
                    return _FakeResp(status_code=429)
                return _FakeResp(payload={"keyBoardList": [{"code": "601398", "orgId": "ok"}]})

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        client = _SeqClient()
        _patch_client(monkeypatch, client)
        monkeypatch.setattr(cn.time, "sleep", lambda _s: None)
        assert cn.resolve_org_id("601398") == "601398,ok"
        assert client.calls == 2

    def test_network_exception_returns_none(self, monkeypatch, _isolate):
        def _boom(**_kw):
            raise RuntimeError("network down")

        monkeypatch.setattr(cn, "make_http_client", _boom)
        assert cn.resolve_org_id("601398") is None


class _FlakyClient:
    """可编程假客户端：前 ``fail_times`` 次调用抛异常，之后返回给定响应。

    ``fail_times=None`` 表示始终抛异常（用于验证重试有界）。
    """

    def __init__(
        self,
        resp: _FakeResp | None = None,
        *,
        exc: Exception | None = None,
        fail_times: int | None = 1,
    ) -> None:
        self._resp = resp if resp is not None else _FakeResp(payload={"keyBoardList": []})
        self._exc = exc if exc is not None else httpx.ConnectTimeout("timed out")
        self._fail_times = fail_times
        self.calls = 0

    def _do(self) -> _FakeResp:
        self.calls += 1
        if self._fail_times is None or self.calls <= self._fail_times:
            raise self._exc
        return self._resp

    def post(self, url, data=None, headers=None) -> _FakeResp:
        return self._do()

    def get(self, url, headers=None) -> _FakeResp:
        return self._do()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestTransientConnectRetry:
    """连接级瞬时失败退避重试一次。

    回归背景（本机实测）：到 cninfo 的**首个连接**常被丢弃（http/https 均见 8s 超时，
    随后立即 200）。而 orgId 解析、公告列表、PDF 下载三条路径都**不经 Provider Chain**，
    拿不到链路的同源重试——不补重试时，冷启动抖动即让整只标的丢掉备源候选
    （orgId 解析失败 → 公告列表为空 → 备源不可用）。
    """

    def _patch_flaky(self, monkeypatch, client) -> list[float]:
        sleeps: list[float] = []
        monkeypatch.setattr(cn, "make_http_client", lambda **_kw: client)
        monkeypatch.setattr(cn.time, "sleep", sleeps.append)
        return sleeps

    def test_post_json_retries_once_then_succeeds(self, monkeypatch, _isolate):
        """首次连接失败 → 退避一次后成功返回 JSON。"""
        client = _FlakyClient(resp=_FakeResp(payload={"keyBoardList": [{"code": "600900", "orgId": "gssh0600900"}]}))
        sleeps = self._patch_flaky(monkeypatch, client)

        payload = cn._post_json("/new/information/topSearch/query", {"keyWord": "600900"})

        assert payload == {"keyBoardList": [{"code": "600900", "orgId": "gssh0600900"}]}
        assert client.calls == 2
        assert sleeps == [cn._CONNECT_RETRY_BACKOFF]

    def test_post_json_gives_up_after_one_retry(self, monkeypatch, _isolate):
        """始终失败 → 返回 None，且尝试次数有界（不无限重试）。"""
        client = _FlakyClient(fail_times=None)
        sleeps = self._patch_flaky(monkeypatch, client)

        assert cn._post_json("/x", {}) is None
        assert client.calls == cn._CONNECT_RETRY_ATTEMPTS
        assert sleeps == [cn._CONNECT_RETRY_BACKOFF * i for i in range(1, cn._CONNECT_RETRY_ATTEMPTS)]

    def test_get_bytes_retries_once_then_succeeds(self, monkeypatch, _isolate):
        """公告 PDF 下载同样退避重试一次。"""
        client = _FlakyClient(resp=_FakeResp(content=b"%PDF-1.4 fake"))
        sleeps = self._patch_flaky(monkeypatch, client)

        assert cn._get_bytes("http://static.cninfo.com.cn/a.PDF") == b"%PDF-1.4 fake"
        assert client.calls == 2
        assert sleeps == [cn._CONNECT_RETRY_BACKOFF]

    def test_non_transient_error_is_not_retried(self, monkeypatch, _isolate):
        """确定性失败（非传输级异常）只调一次，不浪费退避等待。"""
        client = _FlakyClient(exc=ValueError("bad params"), fail_times=None)
        sleeps = self._patch_flaky(monkeypatch, client)

        assert cn._post_json("/x", {}) is None
        assert client.calls == 1
        assert sleeps == []

    def test_retries_survive_two_consecutive_cold_start_failures(self, monkeypatch, _isolate):
        """连续两次冷启动失败后第 3 次成功（实测工况：首个连接常被丢弃）。"""
        client = _FlakyClient(
            resp=_FakeResp(payload=[{"code": "600900", "orgId": "gssh0600900"}]),
            fail_times=2,
        )
        sleeps = self._patch_flaky(monkeypatch, client)

        payload = cn._post_json("/new/information/topSearch/query", {"keyWord": "600900"})

        assert payload == [{"code": "600900", "orgId": "gssh0600900"}]
        assert client.calls == 3
        assert sleeps == [cn._CONNECT_RETRY_BACKOFF, cn._CONNECT_RETRY_BACKOFF * 2]


class TestTopSearchListShape:
    """topSearch 返回**数组**（实测），而 hisAnnouncement/query 返回 dict——两种都要放行。

    回归背景：``_post_json`` 早期只放行 dict（``isinstance(payload, dict)``），
    而 topSearch 实际返回 ``[{"code": "600900", "orgId": "gssh0600900", ...}]``
    → orgId 解析恒为 None → 公告列表为空 → 巨潮备源整条路径不可用。
    """

    def test_post_json_passes_list_payload_through(self, monkeypatch, _isolate):
        items = [{"code": "600900", "orgId": "gssh0600900", "zwjc": "长江电力"}]
        _patch_client(monkeypatch, _FakeClient(post_map={"/topSearch/query": _FakeResp(payload=items)}))
        assert cn._post_json("/new/information/topSearch/query", {"keyWord": "600900"}) == items

    def test_resolve_org_id_from_list_response(self, monkeypatch, _isolate):
        _patch_client(
            monkeypatch,
            _FakeClient(
                post_map={
                    "/topSearch/query": _FakeResp(
                        payload=[{"code": "600900", "orgId": "gssh0600900", "zwjc": "长江电力"}]
                    )
                }
            ),
        )
        assert cn.resolve_org_id("600900") == "600900,gssh0600900"

    def test_resolve_org_id_still_accepts_dict_wrapped_shape(self, monkeypatch, _isolate):
        """历史/其他部署可能包一层 dict（keyBoardList）——保持兼容。"""
        _patch_client(
            monkeypatch,
            _FakeClient(
                post_map={
                    "/topSearch/query": _FakeResp(
                        payload={"keyBoardList": [{"code": "600900", "orgId": "gssh0600900"}]}
                    )
                }
            ),
        )
        assert cn.resolve_org_id("600900") == "600900,gssh0600900"
