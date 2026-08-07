"""Web 配置编辑模块测试（web/config_edit.py + GET/POST /api/config/edit 路由）。

覆盖设计矩阵 T1~T10：白名单完备 / 隐藏 LLM 键拒绝 / 面板全量读取 / 标量写 /
嵌套 dict 写（子模块 + 对比指数池增删重置）/ llm_settings 写 / features 写 /
校验与守卫（未知键/类型/枚举/同源 403/写失败 500）/ 写前 .bak 备份。

隔离（conftest _isolate_sensitive_paths）：config.json / llm_settings.json /
features.json 均已重定向到临时目录，本测试不触碰真实 data/config/。
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.web.app import create_app
from src.python.web.config_edit import config_edit_whitelist
from src.python.web.runs import RunManager

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """构造 Flask test_client（fake executor 管线，配置路径已由 conftest 隔离）。"""
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()

    rm = RunManager(executor=lambda state, params: 0)
    app = create_app(rm)
    app.config["TESTING"] = True
    return app.test_client()


# ═══════════════════════════════════════════════════════════════
# T1 白名单完备：7 组全集 + 无多余键
# ═══════════════════════════════════════════════════════════════

_EXPECTED_WHITELIST = {
    # 1 自由文本路径（菜单 C/F/O）
    "holdings_dir",
    "holdings_filename",
    "output_dir",
    # 2 报告章节开关（菜单 P 1~5）
    "enable_fund_deep_analysis",
    "enable_news",
    "enable_history",
    "enable_portfolio_evolution",
    "enable_action",
    # 3 报告增强子模块开关（菜单 P 6）
    "report_submodules.data_quality",
    "report_submodules.industry_beta",
    "report_submodules.candidate_compare",
    "report_submodules.cost_lots",
    "report_submodules.valuation_percentile",
    "report_submodules.market_temperature",
    # 4 持仓匿名化枚举（菜单 A）
    "anonymization.mode",
    # 5 对比指数池（菜单 I）
    "comparison_indices",
    # 6 LLM 分析章节开关（菜单 S 1~5）
    "enabled_llm.global_macro",
    "enabled_llm.expert_review",
    "enabled_llm.health_check",
    "enabled_llm.penetration_deep",
    "enabled_llm.news_correlation",
    # 7 辩论实验功能开关（菜单 S 6~8）
    "llm_debate_procon",
    "llm_debate_conditional",
    "llm_debate_qa_concentration",
}


class TestWhitelist:
    """T1/T2：白名单完备性与隐藏键语义。"""

    def test_whitelist_covers_all_tui_editable_keys(self):
        """白名单 = 7 组 TUI 可编辑项全集，无多余键。"""
        assert set(config_edit_whitelist) == _EXPECTED_WHITELIST

    @pytest.mark.parametrize(
        "key",
        [
            "enabled_llm.debate_pro",
            "enabled_llm.debate_con",
            "enabled_llm.debate_synthesis",
        ],
    )
    def test_hidden_llm_keys_rejected(self, app_client, key):
        """隐藏辩论三模块不在白名单 → 400 BAD_PARAM（镜像 TUI 隐藏语义）。"""
        resp = app_client.post("/api/config/edit", json={"key": key, "value": True})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"


# ═══════════════════════════════════════════════════════════════
# T3 面板读取：GET /api/config/edit 返回 7 组全量可编辑面
# ═══════════════════════════════════════════════════════════════


class TestGetSurface:
    """T3：面板全量读取。"""

    def test_surface_returns_all_groups(self, app_client):
        """GET 返回 paths/sections/submodules/anonymization/comparison_indices/llm。"""
        resp = app_client.get("/api/config/edit")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        data = body["data"]
        assert set(data) == {
            "paths",
            "sections",
            "submodules",
            "anonymization",
            "comparison_indices",
            "comparison_indices_defaults",
            "llm",
        }
        assert set(data["paths"]) == {"holdings_dir", "holdings_filename", "output_dir"}
        assert set(data["sections"]) == {
            "enable_fund_deep_analysis",
            "enable_news",
            "enable_history",
            "enable_portfolio_evolution",
            "enable_action",
        }
        assert set(data["submodules"]) == {
            "data_quality",
            "industry_beta",
            "candidate_compare",
            "cost_lots",
            "valuation_percentile",
            "market_temperature",
        }

    def test_surface_values_from_defaults(self, app_client):
        """无配置文件时值来自默认配置：章节全开、子模块 data_quality 开其余关、匿名化 off。"""
        resp = app_client.get("/api/config/edit")
        data = resp.get_json()["data"]
        # 报告章节默认全开
        assert all(data["sections"].values())
        # 子模块默认 data_quality 开，其余关
        assert data["submodules"]["data_quality"] is True
        assert data["submodules"]["industry_beta"] is False
        assert data["submodules"]["cost_lots"] is False
        # 匿名化默认 off，枚举选项齐全
        assert data["anonymization"]["mode"] == "off"
        assert data["anonymization"]["options"] == ["off", "code_display", "full_anonymous", "summary"]
        # 对比指数池 = 默认池
        assert data["comparison_indices"] == data["comparison_indices_defaults"]
        # LLM 开关默认开，隐藏模块列出辩论三模块，辩论实验默认关
        assert set(data["llm"]["enabled_llm"]) == {
            "global_macro",
            "expert_review",
            "health_check",
            "penetration_deep",
            "news_correlation",
        }
        assert data["llm"]["hidden_modules"] == ["debate_pro", "debate_con", "debate_synthesis"]
        assert all(v is False for v in data["llm"]["debate"].values())


# ═══════════════════════════════════════════════════════════════
# T4/T5 标量写 + 嵌套 dict 写
# ═══════════════════════════════════════════════════════════════


class TestApplyScalarWrite:
    """T4：标量/枚举编辑走对应写入原语，写后读回正确。"""

    def test_holdings_dir_write(self, app_client):
        """holdings_dir 写：set_config 单键 patch，写后 get_config 读回。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "holdings_dir", "value": "/tmp/config-edit-holdings"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["key"] == "holdings_dir"
        assert data["value"] == "/tmp/config-edit-holdings"

        from src.python.config import get_config

        assert get_config()["holdings_dir"] == "/tmp/config-edit-holdings"

    def test_enable_news_write(self, app_client):
        """enable_news 写：bool 值持久化到 config.json。"""
        resp = app_client.post("/api/config/edit", json={"key": "enable_news", "value": False})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["value"] is False

        from src.python.config import get_config

        assert get_config()["enable_news"] is False

    def test_anonymization_mode_write(self, app_client):
        """anonymization.mode 写：set_anonymization_mode（写顶层键），读回生效。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "anonymization.mode", "value": "code_display"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["value"] == "code_display"

        from src.python.config.anonymizer import get_anonymization_mode

        assert get_anonymization_mode() == "code_display"


class TestApplyNestedDictWrite:
    """T5：嵌套 dict 读合并后整块写，其余子键/指数保留。"""

    def test_submodule_cost_lots_keeps_others(self, app_client):
        """report_submodules.cost_lots 写：其余子键保持默认值。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "report_submodules.cost_lots", "value": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["value"] is True

        from src.python.config import get_config

        sub = get_config()["report_submodules"]
        assert sub["cost_lots"] is True
        assert sub["data_quality"] is True  # 默认开，未被覆盖
        assert sub["industry_beta"] is False

    def test_comparison_indices_add_keeps_defaults(self, app_client):
        """指数池 add：新指数入池，默认池指数保留。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "comparison_indices", "action": "add", "code": "sh000016", "name": "上证50"},
        )
        assert resp.status_code == 200
        indices = resp.get_json()["data"]["value"]
        assert indices["sh000016"] == "上证50"
        assert indices["sh000300"] == "沪深300"

        from src.python.config import get_config

        assert get_config()["comparison_indices"]["sh000016"] == "上证50"

    def test_comparison_indices_remove(self, app_client):
        """指数池 remove：目标指数移除，其余保留。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "comparison_indices", "action": "remove", "code": "sh000300"},
        )
        assert resp.status_code == 200
        indices = resp.get_json()["data"]["value"]
        assert "sh000300" not in indices
        assert "sh000905" in indices

    def test_comparison_indices_reset_to_defaults(self, app_client):
        """指数池 reset：先增后重置，恢复为默认池。"""
        app_client.post(
            "/api/config/edit",
            json={"key": "comparison_indices", "action": "add", "code": "sh000016", "name": "上证50"},
        )
        resp = app_client.post("/api/config/edit", json={"key": "comparison_indices", "action": "reset"})
        assert resp.status_code == 200
        indices = resp.get_json()["data"]["value"]
        assert indices == dict(_config_defaults._DEFAULT_CONFIG["comparison_indices"])
        assert "sh000016" not in indices


# ═══════════════════════════════════════════════════════════════
# T6/T7 llm_settings 写 + features 写
# ═══════════════════════════════════════════════════════════════


class TestApplyLlmSettingsWrite:
    """T6：enabled_llm 写 llm_settings.json（注释保留 + 原子写）。"""

    def test_enabled_llm_write_preserves_comments(self, app_client):
        """enabled_llm.news_correlation 写：文件注释保留，字段更新。"""
        from src.python.config._llm_settings import get_llm_settings_path

        path = get_llm_settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('{\n  // 模型配置\n  "model": "claude",\n  "enabled_llm": {"news_correlation": false}\n}\n')

        resp = app_client.post(
            "/api/config/edit",
            json={"key": "enabled_llm.news_correlation", "value": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["value"] is True

        raw = open(path, encoding="utf-8").read()
        assert "// 模型配置" in raw  # 注释保留
        assert '"model": "claude"' in raw  # 其余键保留
        assert '"news_correlation": true' in raw  # 字段更新


class TestApplyFeaturesWrite:
    """T7：辩论实验开关写 features.json（save_feature_overrides + 运行时生效）。"""

    def test_debate_flag_write_takes_effect(self, app_client):
        """llm_debate_conditional 写：features.json 含覆写，运行时开关生效。"""
        from src.python.config.features import _FEATURES_FILE, is_feature_enabled

        assert is_feature_enabled("llm_debate_conditional") is False  # 默认关

        resp = app_client.post(
            "/api/config/edit",
            json={"key": "llm_debate_conditional", "value": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["value"] is True
        assert is_feature_enabled("llm_debate_conditional") is True

        raw = open(_FEATURES_FILE, encoding="utf-8").read()
        assert '"llm_debate_conditional": true' in raw


# ═══════════════════════════════════════════════════════════════
# T9 校验与守卫
# ═══════════════════════════════════════════════════════════════


class TestValidationAndGuard:
    """T9：未知键/类型/枚举/comparison 非法 → 400；同源失败 → 403；写失败 → 500。"""

    def test_unknown_key_400(self, app_client):
        """未知点分键 → 400 BAD_PARAM（不落盘）。"""
        resp = app_client.post("/api/config/edit", json={"key": "no_such_key", "value": "x"})
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    @pytest.mark.parametrize(
        "payload",
        [
            {"key": "enable_news", "value": 1},  # 伪 bool int
            {"key": "enable_news", "value": "true"},  # 伪 bool str
            {"key": "enable_news"},  # 缺 value
            {"key": "holdings_dir", "value": ""},  # 空串
            {"key": "holdings_dir", "value": "   "},  # 纯空白
            {"key": "holdings_filename", "value": "sub/持仓.xlsx"},  # 含路径分隔符
            {"key": "anonymization.mode", "value": "bogus"},  # 非法枚举
        ],
    )
    def test_invalid_value_400(self, app_client, payload):
        """类型/格式/枚举校验失败 → 400 BAD_PARAM。"""
        resp = app_client.post("/api/config/edit", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    @pytest.mark.parametrize(
        "payload",
        [
            {"key": "comparison_indices", "action": "add", "code": "ab", "name": "x"},  # code <3
            {"key": "comparison_indices", "action": "add", "code": "../sh000300", "name": "x"},  # 非法字符
            {"key": "comparison_indices", "action": "add", "code": "sh000300", "name": ""},  # 空名称
            {"key": "comparison_indices", "action": "add", "code": "sh000300", "name": "   "},  # 空白名称
            {"key": "comparison_indices", "action": "remove", "code": "not_exists"},  # 不在池
            {"key": "comparison_indices", "action": "bogus"},  # 非法 action
        ],
    )
    def test_comparison_invalid_400(self, app_client, payload):
        """对比指数池 action/code/name 校验失败 → 400 BAD_PARAM。"""
        resp = app_client.post("/api/config/edit", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_add_duplicate_code_400(self, app_client):
        """重复 add 已在池中的 code → 400。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "comparison_indices", "action": "add", "code": "sh000300", "name": "沪深300"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_cross_origin_403(self, app_client):
        """非同一来源（伪造 Origin）→ 403 BAD_PARAM。"""
        resp = app_client.post(
            "/api/config/edit",
            json={"key": "enable_news", "value": True},
            headers={"Origin": "http://evil.example.com"},
        )
        assert resp.status_code == 403
        assert resp.get_json()["error_code"] == "BAD_PARAM"

    def test_write_failure_500(self, app_client):
        """写入原语抛异常 → 500 CONFIG_WRITE_FAILED（详情记日志）。"""
        with patch("src.python.config.set_config", side_effect=OSError("disk full")):
            resp = app_client.post("/api/config/edit", json={"key": "enable_news", "value": True})
        assert resp.status_code == 500
        assert resp.get_json()["error_code"] == "CONFIG_WRITE_FAILED"

    def test_non_dict_payload_400(self, app_client):
        """请求体非 JSON object → 400 BAD_PARAM。"""
        resp = app_client.post(
            "/api/config/edit",
            data=json.dumps(["enable_news", True]),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error_code"] == "BAD_PARAM"


# ═══════════════════════════════════════════════════════════════
# T10 写前 .bak 备份（单槽轮转）
# ═══════════════════════════════════════════════════════════════


class TestConfigBackup:
    """T10：写共享配置前单槽 .bak 备份。"""

    def test_backup_created_on_first_write(self, app_client):
        """已有 config.json 时写前生成 .bak，内容=写前旧值；新值落盘。"""
        from src.python.config._config_defaults import get_config_path

        path = get_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"enable_news": True}, f, ensure_ascii=False)
        invalidate_config_cache()

        resp = app_client.post("/api/config/edit", json={"key": "enable_news", "value": False})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["backup"] == path + ".bak"

        bak = json.loads(open(path + ".bak", encoding="utf-8").read())
        assert bak["enable_news"] is True  # 备份写前旧值
        current = json.loads(open(path, encoding="utf-8").read())
        assert current["enable_news"] is False

    def test_backup_none_when_file_missing(self, app_client):
        """首次写入（无原文件）→ backup=None。"""
        resp = app_client.post("/api/config/edit", json={"key": "enable_news", "value": False})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["backup"] is None
