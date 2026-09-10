"""数据源记录-回放引擎 — 边界与异常场景（语义名 datasource_cassette）。

覆盖：畸形 URL 归一、空/缺失/错类型的 cassette 结构、未知版本号的各形态、
文件内重复键、空交互集的回放行为、非 ASCII 与重复查询参数的归一稳定性。

运行：
  pytest src/test/unit/core/test_cassette_edge.py -v
"""

from __future__ import annotations

import json

import pytest

from src.python.core import cassette as cs

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


def _payload(**overrides):
    """最小合法 cassette 结构，供逐个字段破坏。"""
    data = {
        "version": 1,
        "name": "demo",
        "source": "test",
        "recorded_at": "2026-09-10T12:00:00+08:00",
        "interactions": [
            {
                "request": {"method": "GET", "url": "https://a.b/x"},
                "response": {"status": 200, "headers": {}, "body": "x", "encoding": "utf-8"},
            }
        ],
    }
    data.update(overrides)
    return data


# ═══════════ 请求键归一 ═══════════


class TestNormalizeEdge:
    """畸形与非常规 URL 的归一。"""

    def test_relative_url_without_scheme(self):
        """无 scheme/host 的相对 URL：归一不抛异常且保留路径。"""
        key = cs.normalize_request_key("GET", "/v1/data?b=2&a=1")
        assert key == "GET /v1/data?a=1&b=2"

    def test_empty_query_marker_is_equivalent_to_no_query(self):
        """尾随裸 ``?``（空查询串）与无查询串归一相同。"""
        assert cs.normalize_request_key("GET", "https://a.b/c?") == cs.normalize_request_key("GET", "https://a.b/c")

    def test_blank_query_value_is_preserved(self):
        """空值参数保留（``?debug=`` 与「无 debug」不是同一请求）。"""
        with_blank = cs.normalize_request_key("GET", "https://a.b/c?debug=")
        without = cs.normalize_request_key("GET", "https://a.b/c")
        assert with_blank != without

    def test_duplicate_query_params_are_both_kept(self):
        """重复同名参数全部保留（多值参数不能只留一个）。"""
        key = cs.normalize_request_key("GET", "https://a.b/c?tag=a&tag=b")
        assert key.count("tag=") == 2

    def test_normalization_is_idempotent_for_non_ascii(self):
        """非 ASCII 参数归一一次与两次结果一致（匹配两侧走同一归一）。"""
        once = cs.normalize_request_key("GET", "https://a.b/c?q=贵州茅台")
        twice = cs.normalize_request_key("GET", once.split(" ", 1)[1])
        assert once == twice

    def test_volatile_param_inside_path_is_not_stripped(self):
        """易变参数**名**只按查询参数剥离，出现在路径里照旧保留。"""
        key = cs.normalize_request_key("GET", "https://a.b/callback=keep")
        assert "callback=keep" in key


# ═══════════ 结构校验 ═══════════


class TestStructureEdge:
    """畸形 cassette 结构的报错可读性。"""

    @pytest.mark.parametrize("version", [0, 2, 99, "1", None, 1.0, True])
    def test_unsupported_version_rejected(self, version):
        """版本号须严格为整数 1：字符串/浮点/布尔/缺失一律拒绝。

        浮点与布尔是刻意覆盖的——JSON 里写成 ``1.0`` / ``true`` 时 Python 的
        ``==`` 会判其「等于 1」，只做等值比较会把畸形文件放行。
        """
        with pytest.raises(cs.CassetteError, match="版本不受支持"):
            cs.Cassette.from_dict(_payload(version=version), origin="<memory>")

    @pytest.mark.parametrize("top", [[], "x", 3, None])
    def test_non_object_top_level_rejected(self, top):
        """顶层不是对象 → 拒绝。"""
        with pytest.raises(cs.CassetteError, match="顶层不是对象"):
            cs.Cassette.from_dict(top, origin="<memory>")

    @pytest.mark.parametrize("name", ["", None, 7])
    def test_missing_or_invalid_name_rejected(self, name):
        """name 缺失/空/非字符串 → 拒绝。"""
        with pytest.raises(cs.CassetteError, match="缺少 name"):
            cs.Cassette.from_dict(_payload(name=name), origin="<memory>")

    @pytest.mark.parametrize("interactions", [None, "x", {}, 3])
    def test_interactions_must_be_list(self, interactions):
        """interactions 不是列表 → 拒绝。"""
        with pytest.raises(cs.CassetteError, match="缺少 interactions 列表"):
            cs.Cassette.from_dict(_payload(interactions=interactions), origin="<memory>")

    @pytest.mark.parametrize("item", [[], "x", 3, None])
    def test_interaction_item_must_be_object(self, item):
        """交互项不是对象 → 拒绝。"""
        with pytest.raises(cs.CassetteError, match="交互项不是对象"):
            cs.Cassette.from_dict(_payload(interactions=[item]), origin="<memory>")

    @pytest.mark.parametrize("drop", ["request", "response"])
    def test_interaction_requires_both_sides(self, drop):
        """交互项缺 request 或 response → 拒绝。"""
        item = _payload()["interactions"][0]
        item.pop(drop)
        with pytest.raises(cs.CassetteError, match="缺少 request/response"):
            cs.Cassette.from_dict(_payload(interactions=[item]), origin="<memory>")

    @pytest.mark.parametrize(
        "request_overrides",
        [{"method": None}, {"method": "GET", "url": None}, {"url": "https://a.b/x"}],
    )
    def test_interaction_requires_method_and_url(self, request_overrides):
        """交互项缺 method/url 或类型不对 → 拒绝。"""
        item = _payload()["interactions"][0]
        item["request"] = request_overrides
        with pytest.raises(cs.CassetteError, match="缺少 method/url/status"):
            cs.Cassette.from_dict(_payload(interactions=[item]), origin="<memory>")

    @pytest.mark.parametrize("status", [None, "200", 200.0])
    def test_status_must_be_int(self, status):
        """状态码非整数 → 拒绝（``"200"`` 这类上游序列化残留不能蒙混过关）。"""
        item = _payload()["interactions"][0]
        item["response"]["status"] = status
        with pytest.raises(cs.CassetteError, match="缺少 method/url/status"):
            cs.Cassette.from_dict(_payload(interactions=[item]), origin="<memory>")

    def test_optional_response_fields_fall_back(self):
        """headers/body/encoding 类型不对时取安全缺省，不因可选字段拒绝整份文件。"""
        item = _payload()["interactions"][0]
        item["response"] = {"status": 200, "headers": "oops", "body": 3, "encoding": None}
        cassette = cs.Cassette.from_dict(_payload(interactions=[item]), origin="<memory>")
        interaction = cassette.interactions[0]
        assert interaction.headers == {}
        assert interaction.body == ""
        assert interaction.encoding == "utf-8"

    def test_optional_top_level_fields_fall_back(self):
        """source/recorded_at 缺失或类型不对 → 空串，不影响可读性。"""
        cassette = cs.Cassette.from_dict(_payload(source=None, recorded_at=3), origin="<memory>")
        assert cassette.source == ""
        assert cassette.recorded_at == ""

    def test_non_object_interaction_reported_with_origin(self, tmp_path):
        """从文件读取时，报错信息带文件路径（定位损坏夹具）。"""
        (tmp_path / "bad.json").write_text(json.dumps(_payload(interactions=["x"])), encoding="utf-8")
        with pytest.raises(cs.CassetteError) as excinfo:
            cs.load_cassette("bad", str(tmp_path))
        assert str(tmp_path) in str(excinfo.value)

    def test_empty_interactions_is_valid(self, tmp_path):
        """空交互集是合法文件（只是回放必然未命中）。"""
        (tmp_path / "empty.json").write_text(json.dumps(_payload(interactions=[])), encoding="utf-8")
        cassette = cs.load_cassette("empty", str(tmp_path))
        assert cassette.interactions == []
        assert cassette.lookup("GET https://a.b/x") is None

    def test_duplicate_keys_in_file_resolve_to_last(self, tmp_path):
        """文件内同键两条（手工编辑/合并残留）→ 取最后一条，不抛异常。"""
        items = _payload()["interactions"]
        items.append(
            {
                "request": {"method": "GET", "url": "https://a.b/x"},
                "response": {"status": 200, "headers": {}, "body": "second", "encoding": "utf-8"},
            }
        )
        (tmp_path / "dup.json").write_text(json.dumps(_payload(interactions=items)), encoding="utf-8")
        cassette = cs.load_cassette("dup", str(tmp_path))
        assert cassette.lookup(cs.normalize_request_key("GET", "https://a.b/x")).body == "second"


# ═══════════ 回放/录制边界 ═══════════


class TestTransportEdge:
    """传输层在异常输入下的行为。"""

    def test_empty_cassette_miss_message_lists_no_keys(self, tmp_path):
        """空 cassette 回放未命中：消息给出「未录制任何交互」而非空清单。"""
        (tmp_path / "empty.json").write_text(json.dumps(_payload(interactions=[])), encoding="utf-8")
        with cs.cassette_replay(["empty"], directory=str(tmp_path)):
            from src.python.core.http_client import make_http_client

            with make_http_client() as client:
                with pytest.raises(cs.CassetteMissError) as excinfo:
                    client.get("https://a.b/x")
        assert excinfo.value.recorded_keys == ()

    def test_multi_cassette_replay_falls_through_to_second(self, tmp_path):
        """声明多份 cassette 时按顺序查找，第一份没有则由第二份命中。"""
        (tmp_path / "one.json").write_text(json.dumps(_payload(name="one")), encoding="utf-8")
        other = _payload(name="two")
        other["interactions"][0]["request"]["url"] = "https://a.b/other"
        (tmp_path / "two.json").write_text(json.dumps(other), encoding="utf-8")

        from src.python.core.http_client import make_http_client

        with cs.cassette_replay(["one", "two"], directory=str(tmp_path)):
            with make_http_client() as client:
                assert client.get("https://a.b/other").text == "x"

    def test_miss_error_lists_cassette_qualified_keys(self, tmp_path):
        """未命中消息中的已录制键带 cassette 名前缀（跨多份时可定位到具体文件）。"""
        (tmp_path / "one.json").write_text(json.dumps(_payload(name="one")), encoding="utf-8")
        with cs.cassette_replay(["one"], directory=str(tmp_path)):
            from src.python.core.http_client import make_http_client

            with make_http_client() as client:
                with pytest.raises(cs.CassetteMissError) as excinfo:
                    client.get("https://a.b/missing")
        assert "one: GET https://a.b/x" in str(excinfo.value)

    def test_list_ignores_non_json_files(self, tmp_path):
        """目录内非 .json 文件（如写盘中途的 .tmp）不计入索引。"""
        (tmp_path / "demo.json").write_text(json.dumps(_payload()), encoding="utf-8")
        (tmp_path / ".cassette-abc.tmp").write_text("partial", encoding="utf-8")
        (tmp_path / "README.md").write_text("说明", encoding="utf-8")
        assert [entry["name"] for entry in cs.list_cassettes(str(tmp_path))] == ["demo"]
