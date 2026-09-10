"""数据源记录-回放引擎 — 单元测试（语义名 datasource_cassette）。

覆盖：请求键归一（易变参数剥离/排序/方法大写）、交互与 cassette 的序列化往返、
录制写盘（原子写、无临时残留、权限）、读取报错（缺失/损坏/版本不符）、
回放命中与未命中（未命中必须显式失败且不联网）、传输层注入的安装与还原、
录制会话的收集/幂等写盘、``verify_cassettes`` 的 ok/fail/skipped 判定。

运行：
  pytest src/test/unit/core/test_cassette.py -v
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

from src.python.core import cassette as cs
from src.python.core.http_client import make_http_client

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


def _interaction(url: str, body: str = "hello", *, method: str = "GET", status: int = 200, **response_kwargs):
    """构造一条录制交互（测试夹具）。"""
    return cs.Interaction(
        method=method,
        url=url,
        status=status,
        headers=response_kwargs.pop("headers", {"content-type": "text/plain; charset=utf-8"}),
        body=body,
        encoding=response_kwargs.pop("encoding", "utf-8"),
    )


def _write_cassette(directory, name: str, interactions) -> cs.Cassette:
    cassette = cs.Cassette(name=name, source="test", recorded_at="2026-09-10T12:00:00+08:00")
    for interaction in interactions:
        cassette.record(interaction)
    cs.save_cassette(cassette, str(directory))
    return cassette


# ═══════════ 请求键归一 ═══════════


class TestNormalizeRequestKey:
    """请求键归一：易变参数剥离、参数排序、方法大写、fragment 丢弃。"""

    @pytest.mark.parametrize(
        "volatile",
        ["_=1726000000000", "callback=jQuery", "reqid=abc", "rt=0.1234", "req_trace=1726000000000"],
    )
    def test_volatile_query_params_are_stripped(self, volatile):
        """易变参数（防缓存/JSONP 回调/请求追踪）全部剥离，两次请求归一到同一键。"""
        plain = cs.normalize_request_key("GET", "https://api.example.com/data?id=1")
        noisy = cs.normalize_request_key("GET", f"https://api.example.com/data?id=1&{volatile}")
        assert plain == noisy

    def test_meaningful_query_params_are_kept_and_sorted(self):
        """有意义的查询参数保留并排序，参数顺序不同不影响匹配。"""
        a = cs.normalize_request_key("GET", "https://api.example.com/x?b=2&a=1")
        b = cs.normalize_request_key("GET", "https://api.example.com/x?a=1&b=2")
        assert a == b
        assert "a=1" in a and "b=2" in a

    def test_different_query_values_are_distinct(self):
        """参数值不同即不同键——归一不能宽到把两个请求混为一谈。"""
        one = cs.normalize_request_key("GET", "https://api.example.com/x?code=600519")
        two = cs.normalize_request_key("GET", "https://api.example.com/x?code=000001")
        assert one != two

    def test_method_is_upper_cased(self):
        """方法大小写不敏感。"""
        assert cs.normalize_request_key("get", "https://a.b/c") == cs.normalize_request_key("GET", "https://a.b/c")

    def test_fragment_is_dropped(self):
        """fragment 不参与匹配（不会随请求发往服务端）。"""
        with_frag = cs.normalize_request_key("GET", "https://a.b/c#section")
        without = cs.normalize_request_key("GET", "https://a.b/c")
        assert with_frag == without

    def test_no_query_has_no_trailing_question_mark(self):
        """无查询串时不留裸 ``?``。"""
        assert cs.normalize_request_key("GET", "https://qt.gtimg.cn/q=sh600519") == (
            "GET https://qt.gtimg.cn/q=sh600519"
        )


# ═══════════ 数据模型 ═══════════


class TestCassetteModel:
    """交互与 cassette 的增改查与序列化往返。"""

    def test_record_then_lookup_hits(self):
        """录制后按同一请求键可查到。"""
        cassette = cs.Cassette(name="c")
        cassette.record(_interaction("https://a.b/x"))
        assert cassette.lookup(cs.normalize_request_key("GET", "https://a.b/x")) is not None

    def test_lookup_miss_returns_none(self):
        """未录制的请求键返回 None（由传输层转成显式失败）。"""
        cassette = cs.Cassette(name="c")
        cassette.record(_interaction("https://a.b/x"))
        assert cassette.lookup(cs.normalize_request_key("GET", "https://a.b/y")) is None

    def test_duplicate_key_last_write_wins(self):
        """同键重复录制：后写覆盖先写，不堆积重复条目。"""
        cassette = cs.Cassette(name="c")
        cassette.record(_interaction("https://a.b/x", "first"))
        cassette.record(_interaction("https://a.b/x", "second"))
        assert len(cassette.interactions) == 1
        assert cassette.lookup(cs.normalize_request_key("GET", "https://a.b/x")).body == "second"

    def test_volatile_only_difference_collapses_to_one_entry(self):
        """仅易变参数不同的两次录制归为同一条（否则每次录制都会新增条目）。"""
        cassette = cs.Cassette(name="c")
        cassette.record(_interaction("https://a.b/x?rt=0.1"))
        cassette.record(_interaction("https://a.b/x?rt=0.9"))
        assert len(cassette.interactions) == 1

    def test_dict_round_trip_preserves_everything(self):
        """序列化往返后键集、方法、状态码、响应体、字符集逐项一致。"""
        original = cs.Cassette(name="c", source="tencent", recorded_at="2026-09-10T12:00:00+08:00")
        original.record(
            _interaction(
                "https://a.b/x?y=1", "贵州茅台", headers={"content-type": "text/html; charset=GBK"}, encoding="gbk"
            )
        )

        restored = cs.Cassette.from_dict(original.to_dict(), origin="<memory>")

        assert restored.to_dict() == original.to_dict()
        assert restored.source == "tencent"
        assert restored.interactions[0].encoding == "gbk"
        assert restored.interactions[0].body == "贵州茅台"

    def test_to_dict_carries_version(self):
        """写盘内容带版本号（读取侧据此拒绝不兼容格式）。"""
        assert cs.Cassette(name="c").to_dict()["version"] == 1


# ═══════════ 写盘与读取 ═══════════


class TestSaveLoad:
    """写盘原子性与读取报错可读性。"""

    def test_save_then_load_round_trip(self, tmp_path):
        """写盘后可原样读回。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x", "body")])
        loaded = cs.load_cassette("demo", str(tmp_path))
        assert loaded.name == "demo"
        assert loaded.interactions[0].body == "body"

    def test_save_leaves_no_temp_file(self, tmp_path):
        """原子写不残留临时文件（目录内只有目标 json）。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])
        assert sorted(os.listdir(tmp_path)) == ["demo.json"]

    def test_saved_file_is_group_readable(self, tmp_path):
        """落盘权限为 0644（入库夹具，非 mkstemp 默认的 0600）。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])
        assert os.stat(tmp_path / "demo.json").st_mode & 0o777 == 0o644

    def test_save_creates_missing_directory(self, tmp_path):
        """目标目录不存在时自动创建（首次录制场景）。"""
        target = tmp_path / "nested" / "cassettes"
        _write_cassette(target, "demo", [_interaction("https://a.b/x")])
        assert (target / "demo.json").is_file()

    def test_save_overwrites_existing(self, tmp_path):
        """重录覆盖旧文件，不残留旧交互。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x", "old")])
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/y", "new")])
        loaded = cs.load_cassette("demo", str(tmp_path))
        assert [i.body for i in loaded.interactions] == ["new"]

    def test_load_missing_raises_with_path(self, tmp_path):
        """文件缺失：报错信息带绝对路径，便于定位。"""
        with pytest.raises(cs.CassetteError) as excinfo:
            cs.load_cassette("nope", str(tmp_path))
        assert "cassette 不存在" in str(excinfo.value)
        assert str(tmp_path) in str(excinfo.value)

    def test_load_corrupt_json_raises_with_reason(self, tmp_path):
        """非法 JSON：报错信息带路径与解析原因。"""
        path = tmp_path / "broken.json"
        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(cs.CassetteError) as excinfo:
            cs.load_cassette("broken", str(tmp_path))
        assert "不是合法 JSON" in str(excinfo.value)

    def test_load_version_mismatch_reports_both_versions(self, tmp_path):
        """版本不符：报错信息同时给出文件版本与当前支持版本。"""
        (tmp_path / "v9.json").write_text(
            json.dumps({"version": 9, "name": "v9", "interactions": []}), encoding="utf-8"
        )
        with pytest.raises(cs.CassetteError) as excinfo:
            cs.load_cassette("v9", str(tmp_path))
        assert "版本不受支持" in str(excinfo.value)
        assert "9" in str(excinfo.value)

    def test_save_writes_readable_utf8_chinese(self, tmp_path):
        """中文不以 \\uXXXX 转义落盘（夹具需人可读可比对）。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x", "贵州茅台")])
        assert "贵州茅台" in (tmp_path / "demo.json").read_text(encoding="utf-8")


# ═══════════ 回放传输 ═══════════


class TestReplayTransport:
    """回放：命中返回录制内容，未命中显式失败。"""

    def test_hit_replays_status_headers_and_body(self, tmp_path):
        """命中时状态码/响应体/字符集逐一还原（提供方拿到与真实一致的对象）。"""
        _write_cassette(
            tmp_path,
            "demo",
            [
                _interaction(
                    "https://a.b/x",
                    "贵州茅台",
                    status=201,
                    headers={"content-type": "text/html; charset=GBK"},
                    encoding="gbk",
                )
            ],
        )
        with cs.cassette_replay(["demo"], directory=str(tmp_path)):
            with make_http_client() as client:
                response = client.get("https://a.b/x")
        assert response.status_code == 201
        assert response.text == "贵州茅台"
        assert response.encoding.lower() == "gbk"

    def test_replay_drops_transport_encoding_headers(self, tmp_path):
        """录制存的已是解压正文，回放须丢弃 content-encoding（否则二次解压报错）。"""
        _write_cassette(
            tmp_path,
            "demo",
            [
                _interaction(
                    "https://a.b/x",
                    "plain text",
                    headers={
                        "content-type": "text/plain; charset=utf-8",
                        "content-encoding": "gzip",
                        "content-length": "38",
                        "transfer-encoding": "chunked",
                    },
                )
            ],
        )
        with cs.cassette_replay(["demo"], directory=str(tmp_path)):
            with make_http_client() as client:
                response = client.get("https://a.b/x")
        assert response.text == "plain text"

    def test_replay_matches_despite_volatile_params(self, tmp_path):
        """请求带易变参数时仍能命中录制（归一在传输层生效）。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x?id=1&rt=0.1", "matched")])
        with cs.cassette_replay(["demo"], directory=str(tmp_path)):
            with make_http_client() as client:
                response = client.get("https://a.b/x?id=1&rt=0.9")
        assert response.text == "matched"

    def test_miss_raises_with_key_and_recorded_keys(self, tmp_path):
        """未命中：抛 CassetteMissError，消息含缺失键与已录制键清单。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/recorded", "x")])
        with cs.cassette_replay(["demo"], directory=str(tmp_path)):
            with make_http_client() as client:
                with pytest.raises(cs.CassetteMissError) as excinfo:
                    client.get("https://a.b/missing")
        message = str(excinfo.value)
        assert "https://a.b/missing" in message
        assert "https://a.b/recorded" in message

    def test_miss_is_not_an_httpx_error(self):
        """未命中刻意不属于 httpx 错误族：provider 的 httpx 降级分支不会吞掉它。"""
        assert not issubclass(cs.CassetteMissError, httpx.HTTPError)
        assert issubclass(cs.CassetteMissError, cs.CassetteError)

    def test_miss_lists_marker_when_nothing_recorded(self, tmp_path):
        """空 cassette 未命中时，消息说明「未录制任何交互」而非给出空清单。"""
        _write_cassette(tmp_path, "empty", [])
        with cs.cassette_replay(["empty"], directory=str(tmp_path)):
            with make_http_client() as client:
                with pytest.raises(cs.CassetteMissError) as excinfo:
                    client.get("https://a.b/x")
        assert "未录制任何交互" in str(excinfo.value)

    def test_replay_fails_before_touching_network(self, tmp_path):
        """未命中时**不**回落真实网络——测试环境的 socket 阻断是兜底防线。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/recorded")])
        with cs.cassette_replay(["demo"], directory=str(tmp_path)):
            with make_http_client() as client:
                # 若实现回落网络，这里会被 conftest 的 _block_external_network 拦成 RuntimeError
                with pytest.raises(cs.CassetteMissError):
                    client.get("https://a.b/missing")

    def test_replay_installs_and_restores_factory(self, tmp_path):
        """回放块退出后传输工厂还原，后续客户端回到默认传输。"""
        from src.python.core import http_client

        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])
        assert http_client._TRANSPORT_FACTORY is None
        with cs.cassette_replay(["demo"], directory=str(tmp_path)):
            assert http_client._TRANSPORT_FACTORY is not None
        assert http_client._TRANSPORT_FACTORY is None

    def test_replay_missing_cassette_raises_before_installing(self, tmp_path):
        """cassette 文件缺失时立即报错，不留下已安装的工厂。"""
        from src.python.core import http_client

        with pytest.raises(cs.CassetteError):
            with cs.cassette_replay(["nope"], directory=str(tmp_path)):
                pass
        assert http_client._TRANSPORT_FACTORY is None

    def test_factory_returns_fresh_transport_per_client(self, tmp_path):
        """工厂每次产出新传输实例：前一个客户端关闭后，后续请求仍可用。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x", "first")])
        with cs.cassette_replay(["demo"], directory=str(tmp_path)):
            with make_http_client() as first:
                assert first.get("https://a.b/x").text == "first"
            with make_http_client() as second:
                assert second.get("https://a.b/x").text == "first"


# ═══════════ 录制会话 ═══════════


class TestRecordingSession:
    """录制会话：收集、幂等写盘、无内容不落盘。"""

    def _observe(self, session, url, body):
        response = httpx.Response(
            200, headers={"content-type": "text/plain; charset=utf-8"}, content=body.encode("utf-8")
        )
        response.read()
        session.observe(httpx.Request("GET", url), response)

    def test_flush_writes_recorded_interactions(self, tmp_path):
        """录到的交互写盘并可回放。"""
        session = cs.RecordingSession("demo", source="tencent", directory=str(tmp_path))
        self._observe(session, "https://a.b/x", "payload")

        assert session.flush() is True

        loaded = cs.load_cassette("demo", str(tmp_path))
        assert loaded.source == "tencent"
        assert loaded.recorded_at
        assert [i.body for i in loaded.interactions] == ["payload"]

    def test_flush_is_idempotent(self, tmp_path):
        """重复 flush 不再写盘（无新增内容）。"""
        session = cs.RecordingSession("demo", directory=str(tmp_path))
        self._observe(session, "https://a.b/x", "payload")
        assert session.flush() is True
        assert session.flush() is False

    def test_flush_without_traffic_writes_nothing(self, tmp_path):
        """一次请求都没发时不产生空 cassette 文件。"""
        session = cs.RecordingSession("demo", directory=str(tmp_path))
        assert session.flush() is False
        assert not os.path.exists(cs.cassette_path("demo", str(tmp_path)))

    def test_repeated_url_is_recorded_once(self, tmp_path):
        """同一 URL 请求两次只留一条（后写覆盖先写）。"""
        session = cs.RecordingSession("demo", directory=str(tmp_path))
        self._observe(session, "https://a.b/x", "first")
        self._observe(session, "https://a.b/x", "second")
        session.flush()
        loaded = cs.load_cassette("demo", str(tmp_path))
        assert [i.body for i in loaded.interactions] == ["second"]

    def test_record_context_installs_recording_transport(self, tmp_path):
        """cassette_record 块内 make_http_client 拿到录制传输（不装则回落真实网络）。"""
        from src.python.core.cassette import _RecordTransport

        with cs.cassette_record("demo", source="tencent", directory=str(tmp_path)):
            with make_http_client() as client:
                assert isinstance(client._transport, _RecordTransport)


# ═══════════ 目录索引与解析校验 ═══════════


class TestListAndVerify:
    """cassette 目录索引与「当前解析器能否解析」判定。"""

    def test_list_returns_empty_for_missing_directory(self, tmp_path):
        """目录不存在时返回空列表（不抛异常）。"""
        assert cs.list_cassettes(str(tmp_path / "nope")) == []

    def test_list_reports_metadata(self, tmp_path):
        """索引含来源、录制时间、交互数、大小与路径。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])
        entries = cs.list_cassettes(str(tmp_path))
        assert len(entries) == 1
        entry = entries[0]
        assert entry["name"] == "demo"
        assert entry["source"] == "test"
        assert entry["interactions"] == 1
        assert entry["size_bytes"] > 0
        assert entry["path"].endswith("demo.json")

    def test_list_surfaces_corrupt_file_instead_of_crashing(self, tmp_path):
        """损坏文件以 error 字段如实呈现，其余条目照常列出，不整体失败。"""
        _write_cassette(tmp_path, "good", [_interaction("https://a.b/x")])
        (tmp_path / "bad.json").write_text("{ broken", encoding="utf-8")

        entries = {entry["name"]: entry for entry in cs.list_cassettes(str(tmp_path))}

        assert entries["good"]["interactions"] == 1
        assert "不是合法 JSON" in entries["bad"]["error"]

    def test_verify_ok_when_parser_returns_result(self, tmp_path):
        """解析器返回非空结果 → ok。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])
        verdicts = cs.verify_cassettes({"demo": lambda: [{"ok": True}]}, directory=str(tmp_path))
        assert verdicts[0]["status"] == "ok"

    def test_verify_fail_when_parser_raises(self, tmp_path):
        """解析器抛异常 → fail，详情带异常类型（诊断入口不向上抛）。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])

        def _boom():
            raise ValueError("上游格式变了")

        verdicts = cs.verify_cassettes({"demo": _boom}, directory=str(tmp_path))
        assert verdicts[0]["status"] == "fail"
        assert "ValueError" in verdicts[0]["detail"]

    def test_verify_fail_when_parser_returns_empty(self, tmp_path):
        """解析器返回空结果 → fail（「解析器吃不下」正是要抓的回归）。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])
        for empty in (None, [], {}, ""):
            verdicts = cs.verify_cassettes({"demo": lambda value=empty: value}, directory=str(tmp_path))
            assert verdicts[0]["status"] == "fail", f"空结果 {empty!r} 应判失败"

    def test_verify_skips_unregistered_cassette(self, tmp_path):
        """未登记解析器 → skipped（不伪造通过，也不判失败）。"""
        _write_cassette(tmp_path, "demo", [_interaction("https://a.b/x")])
        verdicts = cs.verify_cassettes({}, directory=str(tmp_path))
        assert verdicts[0]["status"] == "skipped"

    def test_verify_reports_corrupt_cassette_as_fail(self, tmp_path):
        """损坏 cassette 在解析校验中判 fail 并带原因。"""
        (tmp_path / "bad.json").write_text("{ broken", encoding="utf-8")
        verdicts = cs.verify_cassettes({"bad": lambda: [1]}, directory=str(tmp_path))
        assert verdicts[0]["status"] == "fail"
        assert "不是合法 JSON" in verdicts[0]["detail"]

    def test_verify_names_filter_limits_scope(self, tmp_path):
        """names 过滤只校验指定 cassette——避免录制用例被别的 cassette 连带失败。"""
        _write_cassette(tmp_path, "a", [_interaction("https://a.b/a")])
        _write_cassette(tmp_path, "b", [_interaction("https://a.b/b")])
        verdicts = cs.verify_cassettes({"a": lambda: [1]}, directory=str(tmp_path), names=["a"])
        assert [v["name"] for v in verdicts] == ["a"]

    def test_verify_covers_all_cassettes_without_filter(self, tmp_path):
        """不过滤时覆盖目录内全部 cassette（CLI 维护命令语义）。"""
        _write_cassette(tmp_path, "a", [_interaction("https://a.b/a")])
        _write_cassette(tmp_path, "b", [_interaction("https://a.b/b")])
        verdicts = cs.verify_cassettes({"a": lambda: [1]}, directory=str(tmp_path))
        assert sorted(v["name"] for v in verdicts) == ["a", "b"]
