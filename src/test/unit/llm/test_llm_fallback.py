"""LLM 降级/回退策略模块测试。

测试策略：
  - get_placeholder_text() 覆盖有效键/无效键/时间戳覆盖
  - is_all_llm_failed() 覆盖全部失败/部分成功/全部成功/空元组
  - build_fallback_llm_content() 覆盖全部失败/部分失败/force 模式
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]

from src.python.llm.fallback import (
    build_fallback_llm_content,
    get_placeholder_text,
    is_all_llm_failed,
)


# ── get_placeholder_text 测试 ──────────────────────────────────


class TestGetPlaceholderText:
    """占位文本获取测试。"""

    def test_known_module_key(self):
        """已知模块键 → 返回含模块名称的 HTML。"""
        text = get_placeholder_text("global_macro")
        assert "全球政经局势" in text
        assert "⚠️" in text

    def test_expert_review_key(self):
        """expert_review 模块。"""
        text = get_placeholder_text("expert_review")
        assert "智囊团深度复盘" in text

    def test_health_check_key(self):
        """health_check 模块。"""
        text = get_placeholder_text("health_check")
        assert "持仓体检报告" in text

    def test_penetration_deep_key(self):
        """penetration_deep 模块。"""
        text = get_placeholder_text("penetration_deep")
        assert "穿透深度分析" in text

    def test_unknown_key(self):
        """未知模块键 → 通用占位文本。"""
        text = get_placeholder_text("unknown_module")
        assert "暂不可用" in text

    def test_custom_timestamp(self):
        """传入自定义时间戳。"""
        text = get_placeholder_text("global_macro", timestamp="2026-07-30 10:00")
        assert "2026-07-30 10:00" in text


# ── is_all_llm_failed 测试 ────────────────────────────────────


class TestIsAllLlmFailed:
    """LLM 全部失败检测测试。"""

    def test_all_none(self):
        """全部为 None → True。"""
        assert is_all_llm_failed((None, None, None, None)) is True

    def test_partial_success(self):
        """部分成功 → False。"""
        assert is_all_llm_failed(("<h3>内容</h3>", None, None, None)) is False

    def test_all_have_content(self):
        """全部有内容 → False。"""
        t = "<h3>内容</h3>"
        assert is_all_llm_failed((t, t, t, t)) is False

    def test_empty_tuple(self):
        """空元组 → True。"""
        assert is_all_llm_failed(()) is True

    def test_short_tuple(self):
        """少于 4 项 → True。"""
        assert is_all_llm_failed((None, None)) is True

    def test_all_empty_strings(self):
        """空字符串 → 视为有内容（TypeError 安全，非 None）。"""
        t = ""
        assert is_all_llm_failed((t, t, t, t)) is False


# ── build_fallback_llm_content 测试 ─────────────────────────


class TestBuildFallbackLlmContent:
    """LLM 降级内容构建测试。"""

    def test_all_failed(self):
        """全部失败 → 全部使用占位文本。"""
        result = build_fallback_llm_content((None, None, None, None))
        assert len(result) == 4
        for text in result:
            assert "⚠️" in text

    def test_partial_failure(self):
        """部分失败 → 仅替换失败项。"""
        content = ("<h3>全球政经</h3>", None, "<h3>持仓体检</h3>", None)
        result = build_fallback_llm_content(content)
        assert result[0] == "<h3>全球政经</h3>"
        assert "⚠️" in result[1]
        assert result[2] == "<h3>持仓体检</h3>"
        assert "⚠️" in result[3]

    def test_all_success(self):
        """全部成功 → 原样返回。"""
        content = ("<p>A</p>", "<p>B</p>", "<p>C</p>", "<p>D</p>")
        result = build_fallback_llm_content(content)
        assert result == content

    def test_force_mode(self):
        """force=True → 强制全部占位。"""
        content = ("<p>A</p>", "<p>B</p>", "<p>C</p>", "<p>D</p>")
        result = build_fallback_llm_content(content, force=True)
        assert len(result) == 4
        for text in result:
            assert "⚠️" in text

    def test_mixture_with_force(self):
        """混合状态 + force → 全部占位。"""
        result = build_fallback_llm_content(("<p>OK</p>", None, None, "<p>OK</p>"), force=True)
        for text in result:
            assert "⚠️" in text
