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
            "// 全局说明\n"
            "{\n"
            '  "model": "claude",\n'
            "  // 最大输出 tokens\n"
            '  "max_tokens": 8000\n'
            "}\n",
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
            "{\n"
            '  "model": "claude",\n'
            '  "enabled_llm": {"global_macro": false, "news_correlation": false}\n'
            "}\n",
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

        assert json.loads(path.read_text(encoding="utf-8")) == {
            "enabled_llm": {"news_correlation": True}
        }

    def test_refreshes_llm_cache(self, tmp_path, monkeypatch):
        """写入完成后刷新 LLM 配置缓存（get_llm_config 被调用）。"""
        path = tmp_path / "llm_settings.json"
        path.write_text('{"model": "claude"}\n', encoding="utf-8")

        import src.python.config._llm_settings as llm_mod

        calls = []
        monkeypatch.setattr(llm_mod, "get_llm_config", lambda: calls.append(1) or None)

        write_llm_settings({"model": "claude"}, str(path))

        assert calls == [1]
