"""LLM 模块输出质量分级边缘/异常场景测试。

必须放在 *_edge.py 文件中（pytest_collection_modifyitems 强制约束）。
"""

from __future__ import annotations

import pytest

from unittest.mock import MagicMock

from src.python.report.llm_quality import (
    GRADE_A,
    GRADE_B,
    GRADE_C,
    GRADE_D,
    GRADE_F,
    TRIGGER_MISSING_SECTIONS,
    TRIGGER_PLACEHOLDER,
    _LENGTH_THRESHOLDS,
    _REQUIRED_MARKERS,
    apply_quality_banners,
    grade_module,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


def _feature_on(monkeypatch) -> None:
    from src.python.config import features as feat

    monkeypatch.setitem(feat.FEATURE_FLAGS, "module_quality_gate", True)


def _complete_body(module_key: str, pad: int) -> str:
    """构造章节齐备、可指定补白长度的正文。"""
    return "".join(_REQUIRED_MARKERS[module_key]) + "填" * pad


@pytest.mark.edge
class TestGradeModuleEdge:
    """分级边界与异常输入。"""

    @pytest.mark.edge
    def test_whitespace_and_tags_only_is_f(self):
        """标签与空白混合、无实际正文 → F。"""
        assert grade_module("global_macro", "\n<p>  </p>\n<br/>\n").grade == GRADE_F

    @pytest.mark.edge
    def test_exactly_at_min_threshold_is_not_too_short(self):
        """正文恰好等于下限 → 不判过短（边界取严格小于）。"""
        module_key = "health_check"
        min_chars, _comfort = _LENGTH_THRESHOLDS[module_key]
        markers = "".join(_REQUIRED_MARKERS[module_key])
        body = _complete_body(module_key, min_chars - len(markers))
        q = grade_module(module_key, "<p>" + body + "</p>")
        assert q.grade in (GRADE_B, GRADE_A), f"边界长度不应触发过短降级，实际 {q.grade}"

    @pytest.mark.edge
    def test_one_below_min_threshold_is_too_short(self):
        """正文比下限少一个字 → 判过短降级。"""
        module_key = "health_check"
        min_chars, _comfort = _LENGTH_THRESHOLDS[module_key]
        markers = "".join(_REQUIRED_MARKERS[module_key])
        body = _complete_body(module_key, min_chars - len(markers) - 1)
        assert grade_module(module_key, "<p>" + body + "</p>").grade == GRADE_D

    @pytest.mark.edge
    def test_exactly_at_comfort_threshold_is_a(self):
        """正文恰好等于参考篇幅 → A（不再判偏短）。"""
        module_key = "health_check"
        _min, comfort_chars = _LENGTH_THRESHOLDS[module_key]
        markers = "".join(_REQUIRED_MARKERS[module_key])
        body = _complete_body(module_key, comfort_chars - len(markers))
        q = grade_module(module_key, "<p>" + body + "</p>")
        assert q.grade == GRADE_A

    @pytest.mark.edge
    def test_placeholder_wins_over_missing_sections(self):
        """占位文本同时缺章节 → 取更严重的占位降级（不判 C）。"""
        from src.python.llm.fallback import get_placeholder_text

        q = grade_module("health_check", get_placeholder_text("health_check"))
        assert q.grade == GRADE_D
        assert q.trigger == TRIGGER_PLACEHOLDER

    @pytest.mark.edge
    def test_empty_string_placeholder_signature(self):
        """空串输入 is_placeholder 判定为假，但正文为空仍评 F。"""
        assert grade_module("health_check", "").grade == GRADE_F

    @pytest.mark.edge
    def test_unknown_module_uses_default_thresholds(self):
        """未在阈值表中登记的模块走默认阈值，不抛异常。"""
        q = grade_module("unregistered_module", "<p>" + "内容。" * 500 + "</p>")
        assert q.grade == GRADE_A
        assert q.module_key == "unregistered_module"

    @pytest.mark.edge
    def test_marker_present_only_in_banner_text_still_counts(self):
        """章节标记为子串匹配——正文任意位置出现即视为齐备（记录该口径）。"""
        module_key = "penetration_deep"
        _min, comfort_chars = _LENGTH_THRESHOLDS[module_key]
        markers = "".join(_REQUIRED_MARKERS[module_key])
        # 标记集中出现在开头一次即可，无需重复各章节
        body = _complete_body(module_key, comfort_chars - len(markers))
        assert grade_module(module_key, "<p>" + body + "</p>").grade == GRADE_A

    @pytest.mark.edge
    def test_missing_single_marker_is_c(self):
        """只缺一个必需章节 → C，原因仅列出该项。"""
        module_key = "penetration_deep"
        _min, comfort_chars = _LENGTH_THRESHOLDS[module_key]
        markers = list(_REQUIRED_MARKERS[module_key])
        dropped = markers.pop()
        body = "".join(markers) + "填" * (comfort_chars - len("".join(markers)))
        q = grade_module(module_key, "<p>" + body + "</p>")
        assert q.grade == GRADE_C
        assert q.trigger == TRIGGER_MISSING_SECTIONS
        assert dropped in q.reason

    @pytest.mark.edge
    def test_very_long_content_is_a(self):
        """超长正文不因长度被判异常（无上限判定）。"""
        assert grade_module("global_macro", "<p>" + "宏观。" * 20000 + "</p>").grade == GRADE_A


@pytest.mark.edge
class TestApplyQualityBannersEdge:
    """横幅注入的异常输入与开关组合。"""

    @pytest.mark.edge
    def test_empty_tuple(self, monkeypatch):
        """空元组在开关开启时原样返回。"""
        _feature_on(monkeypatch)
        assert apply_quality_banners(()) == ()

    @pytest.mark.edge
    def test_none_input(self, monkeypatch):
        """None 输入不抛异常，原样返回。"""
        _feature_on(monkeypatch)
        assert apply_quality_banners(None) is None

    @pytest.mark.edge
    def test_non_string_content_does_not_raise(self, monkeypatch):
        """非字符串内容（上游数据形状异常）按不可评级跳过，不炸报告主链路。"""
        _feature_on(monkeypatch)
        out = apply_quality_banners((None, None, {"unexpected": "dict"}, None))
        assert out[2] == {"unexpected": "dict"}

    @pytest.mark.edge
    def test_all_modules_advisory_warn_lists_each(self, monkeypatch):
        """多个低评级模块 → 汇总告警逐个列出。"""
        _feature_on(monkeypatch)
        reporter = MagicMock()
        # 150 字正文低于全部四个模块的下限 → 四个模块均为「过短」降级
        body = "<p>" + "说明。" * 50 + "</p>"
        apply_quality_banners((body, body, body, body), reporter)
        message = reporter.warn.call_args.args[0]
        assert "全球政经局势" in message
        assert "智囊团深度复盘" in message
        assert "持仓体检报告" in message
        assert "穿透深度分析" in message

    @pytest.mark.edge
    def test_repeated_apply_is_idempotent_on_healthy(self, monkeypatch):
        """健康内容重复调用结果稳定（幂等，不会累积横幅）。"""
        _feature_on(monkeypatch)
        module_key = "health_check"
        _min, comfort_chars = _LENGTH_THRESHOLDS[module_key]
        body = "<p>" + _complete_body(module_key, comfort_chars) + "</p>"
        once = apply_quality_banners((None, None, body, None))
        twice = apply_quality_banners(once)
        assert once == twice
