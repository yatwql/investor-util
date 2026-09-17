"""LLM 设置共享写入原语 write_llm_settings 单元测试 — 注释保留 / 原子写 / 缓存刷新。

TUI 与 Web 配置编辑共用的 llm_settings.json 写入原语（自 tui/handlers_config 抽取）。
"""

from __future__ import annotations

import json

import pytest

from src.python.config._llm_settings import write_llm_settings

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


class TestWriteLlmSettingsShared:
    """write_llm_settings：字段级替换保留注释 + 原子写 + 刷新 LLM 配置缓存。"""

    def test_scalar_change_preserves_comments(self, tmp_path):
        """标量字段替换：保留文件内注释与未变更字段。"""
        path = tmp_path / "llm_settings.json"
        path.write_text(
            '// 全局说明\n{\n  "model": "claude",\n  // 最大输出 tokens\n  "max_tokens": 8000\n}\n',
            encoding="utf-8",
        )

        write_llm_settings({"max_tokens": 9000}, str(path))

        raw = path.read_text(encoding="utf-8")
        assert "// 全局说明" in raw
        assert "// 最大输出 tokens" in raw
        assert '"model": "claude"' in raw
        assert '"max_tokens": 9000' in raw

    def test_dict_change_keeps_other_keys(self, tmp_path):
        """dict 字段替换：整块重生成，其余顶层键保留。"""
        path = tmp_path / "llm_settings.json"
        path.write_text(
            '{\n  "model": "claude",\n  "enabled_llm": {"global_macro": false, "news_correlation": false}\n}\n',
            encoding="utf-8",
        )

        write_llm_settings(
            {"enabled_llm": {"global_macro": True, "news_correlation": False}},
            str(path),
        )

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["model"] == "claude"
        assert data["enabled_llm"] == {"global_macro": True, "news_correlation": False}

    def test_create_when_missing(self, tmp_path):
        """文件不存在：创建目录并写入完整 settings。"""
        path = tmp_path / "nested" / "llm_settings.json"

        write_llm_settings({"enabled_llm": {"news_correlation": True}}, str(path))

        assert json.loads(path.read_text(encoding="utf-8")) == {"enabled_llm": {"news_correlation": True}}

    def test_refreshes_llm_cache(self, tmp_path, monkeypatch):
        """写入完成后刷新 LLM 配置缓存（get_llm_config 被调用）。"""
        path = tmp_path / "llm_settings.json"
        path.write_text('{"model": "claude"}\n', encoding="utf-8")

        import src.python.config._llm_settings as llm_mod

        calls = []
        monkeypatch.setattr(llm_mod, "get_llm_config", lambda: calls.append(1) or None)

        write_llm_settings({"model": "claude"}, str(path))

        assert calls == [1]


class TestTokenCapHeadroom:
    """模块 token 上限基线：思考型模型须给正文留余量（防「思考耗尽 max_tokens」）。

    背景：`max_tokens_{module}` 是 thinking + 正文**共享预算**。实测智囊团复盘
    在预算偏紧时思考占满预算、响应无正文（日志「LLM 输出思考部分耗尽 max_tokens
    预算，未生成最终文本」），程序只能关闭 thinking 重试一次（多一次调用）。
    2026-09-16 按 +50% 整体上调各模块 max_tokens / thinking_budget，本用例锁定基线，
    防止误改回旧值导致思考耗尽复发。
    """

    EXPECTED = {
        "max_tokens_global_macro": 3072,
        "thinking_budget_global_macro": 6000,
        "max_tokens_expert_review": 36000,
        "thinking_budget_expert_review": 24000,
        "max_tokens_health_check": 24000,
        "thinking_budget_health_check": 18000,
        "max_tokens_penetration_deep": 12288,
        "thinking_budget_penetration_deep": 12000,
        "max_tokens_news_correlation": 3000,
        "thinking_budget_news_correlation": 6000,
    }

    def test_module_token_caps_match_baseline(self):
        """各模块 max_tokens / thinking_budget 默认值须为 +50% 后的基线值。"""
        from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS

        actual = {k: _DEFAULT_LLM_SETTINGS[k] for k in self.EXPECTED}
        assert actual == self.EXPECTED

    def test_thinking_enabled_modules_keep_body_headroom(self):
        """开启 thinking 的模块：max_tokens 必须大于 thinking_budget（否则无正文余量）。"""
        from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS

        d = _DEFAULT_LLM_SETTINGS
        for module in ("expert_review", "health_check"):
            assert d[f"thinking_enabled_{module}"] is True, f"{module} 应默认开启 thinking"
            assert d[f"max_tokens_{module}"] > d[f"thinking_budget_{module}"], (
                f"{module}: max_tokens({d[f'max_tokens_{module}']}) 须大于 "
                f"thinking_budget({d[f'thinking_budget_{module}']})，否则思考会占满预算"
            )

    def test_debate_stage_caps_sized_for_thinking(self):
        """辩论每阶段上限与总预算：18432/72000（三段 3×18432=55296 < 72000，守卫不早trigger）。"""
        from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS

        debate = _DEFAULT_LLM_SETTINGS["debate"]
        assert debate["procon"]["per_call_max_tokens"] == 18432
        assert debate["max_total_tokens_per_report"] == 72000
        assert 3 * debate["procon"]["per_call_max_tokens"] < debate["max_total_tokens_per_report"]
