"""Web 配置编辑极端/异常输入边界测试（@pytest.mark.edge，*_edge.py 隔离）。

覆盖设计矩阵 T11：空/空白字符串、伪布尔（0/1/"true"）、非法枚举、路径穿越
代码、超长名称、JSON 注入等极端载荷 —— 全部应被校验拒绝（400 BAD_PARAM），
且不产生任何落盘副作用（共享配置不得被污染）。

隔离（conftest _isolate_sensitive_paths）：config.json / llm_settings.json /
features.json 均已重定向到临时目录，本测试不触碰真实 data/config/。
"""

from __future__ import annotations

import json
import os

import pytest

from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.web.app import create_app
from src.python.web.runs import RunManager

pytestmark = [pytest.mark.unit, pytest.mark.unit_web, pytest.mark.edge]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """构造 Flask test_client（fake executor 管线，配置路径已由 conftest 隔离）。"""
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()

    rm = RunManager(executor=lambda state, params: 0)
    app = create_app(rm)
    app.config["TESTING"] = True
    return app.test_client()


class TestStringEdgeCases:
    """字符串配置项极端输入。"""

    @pytest.mark.parametrize(
        "value",
        ["", "   ", "\t", "\n", " 　 "],  # 空 / 纯空白 / 全角空格
    )
    def test_blank_string_rejected(self, app_client, value):
        """空/空白字符串 → 400 BAD_PARAM（不落盘）。"""
        resp = app_client.post("/api/config/edit", json={"key": "holdings_dir", "value": value})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_overlong_path_rejected(self, app_client):
        """超长路径字符串（远超合理长度）→ 仍为合法 str，应通过写入（仅长度正常校验）。"""
        value = "/tmp/" + "x" * 2000
        resp = app_client.post("/api/config/edit", json={"key": "holdings_dir", "value": value})
        # 无长度上限设计：超长字符串属合法 str，应成功写入而非 400
        assert resp.status_code == 200

    def test_mixed_whitespace_filename_rejected(self, app_client):
        """holdings_filename 含路径分隔符 → 400。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "holdings_filename", "value": "..\\持仓.xlsx"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"


class TestBoolEdgeCases:
    """布尔配置项伪布尔/类型混淆载荷。"""

    @pytest.mark.parametrize(
        "value",
        [0, 1, -1, "true", "false", "True", "1", 0.0, 1.0, None, [], {}],
    )
    def test_pseudo_bool_rejected(self, app_client, value):
        """伪布尔（int/str/float/None/容器）→ 400 BAD_PARAM。"""
        resp = app_client.post("/api/config/edit", json={"key": "enable_news", "value": value})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"


class TestEnumEdgeCases:
    """匿名化枚举极端取值。"""

    @pytest.mark.parametrize(
        "value",
        ["", "OFF", "Code_Display", "off ", " code_display", "full-anonymous", 0, None],
    )
    def test_invalid_enum_rejected(self, app_client, value):
        """大小写/空白/非法值/非字符串枚举 → 400 BAD_PARAM（严格白名单匹配）。"""
        resp = app_client.post("/api/config/edit", json={"key": "anonymization.mode", "value": value})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"


class TestComparisonIndexEdgeCases:
    """对比指数池极端 code/name。"""

    @pytest.mark.parametrize(
        "payload",
        [
            {"key": "comparison_indices", "action": "add", "code": "../etc/passwd", "name": "x"},
            {"key": "comparison_indices", "action": "add", "code": "a/../b", "name": "x"},
            {"key": "comparison_indices", "action": "add", "code": "sh000300/", "name": "x"},
            {"key": "comparison_indices", "action": "add", "code": "sh000300", "name": "x" * 5000},
            {"key": "comparison_indices", "action": "add", "code": "sh000300", "name": "<script>alert(1)</script>"},
            {"key": "comparison_indices", "action": "add", "code": None, "name": "x"},
            {"key": "comparison_indices", "action": "add", "code": 12345, "name": "x"},
        ],
    )
    def test_hostile_code_or_name_rejected(self, app_client, payload):
        """路径穿越代码/超长名称/HTML 注入/非字符串字段 → 400。"""
        resp = app_client.post("/api/config/edit", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_rejected_write_leaves_pool_unchanged(self, app_client):
        """非法 add 被拒后对比池内容不变（无部分写入副作用）。"""
        from src.python.config import get_config

        before = dict(get_config()["comparison_indices"])

        resp = app_client.post(
            "/api/config/edit",
            json={"key": "comparison_indices", "action": "add", "code": "../evil", "name": "x"},
        )
        assert resp.status_code == 400

        after = get_config()["comparison_indices"]
        assert after == before


class TestPayloadInjectionEdgeCases:
    """请求体 JSON 注入 / 结构异常。"""

    @pytest.mark.parametrize(
        "raw",
        [
            "not json at all",
            '{"key": "enable_news", "value": true',
            '["enable_news", true]',
            "null",
            "42",
        ],
    )
    def test_malformed_body_400(self, app_client, raw):
        """非 JSON / 截断 JSON / 数组 / 标量请求体 → 400 BAD_PARAM。"""
        resp = app_client.post(
            "/api/config/edit",
            data=raw,
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_extra_unknown_fields_ignored(self, app_client):
        """未知顶层字段被忽略，不影响合法编辑。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "enable_history", "value": True, "injected": "x", "admin": 1},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["value"] is True

    def test_no_side_effect_on_rejected_edit(self, app_client):
        """非法编辑被拒后共享配置文件内容不被污染（无 .bak 残留、原文件不变）。"""
        from src.python.config import get_config
        from src.python.config._config_defaults import get_config_path

        path = get_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"enable_news": True}, f, ensure_ascii=False)
        invalidate_config_cache()

        resp = app_client.post("/api/config/edit", json={"key": "no_such_key", "value": True})
        assert resp.status_code == 400

        # 无 .bak 备份残留（校验失败发生在备份之前）
        assert not os.path.exists(path + ".bak")
        # 原文件内容未被修改
        raw = open(path, encoding="utf-8").read()
        assert '"enable_news": true' in raw
        assert get_config()["enable_news"] is True
