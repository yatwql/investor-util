"""实验功能名解析边缘/异常场景测试。

必须放在 *_edge.py 文件中（pytest_collection_modifyitems 强制约束）。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_config, pytest.mark.edge]

from src.python.config.features import (
    EXPERIMENTAL_FEATURES,
    resolve_experiment_flags,
)


@pytest.mark.edge
class TestResolveExperimentFlagsEdge:
    """实验功能名解析边缘场景。"""

    @pytest.mark.edge
    def test_empty_input(self):
        """空列表解析为空集合，不产生未识别项。"""
        flags, unknown = resolve_experiment_flags([])
        assert flags == set()
        assert unknown == []

    @pytest.mark.edge
    def test_blank_tokens_skipped(self):
        """纯空白项被跳过（不计入未识别）。"""
        flags, unknown = resolve_experiment_flags(["", "   ", "\t"])
        assert flags == set()
        assert unknown == []

    @pytest.mark.edge
    def test_surrounding_whitespace_tolerated(self):
        """首尾空白被容忍。"""
        flags, unknown = resolve_experiment_flags(["  signal_pre_digest  "])
        assert flags == {"signal_pre_digest"}
        assert unknown == []

    @pytest.mark.edge
    def test_all_uppercase(self):
        """all 同样大小写不敏感。"""
        flags, unknown = resolve_experiment_flags(["ALL"])
        assert flags == set(EXPERIMENTAL_FEATURES)
        assert unknown == []

    @pytest.mark.edge
    def test_no_fuzzy_match(self):
        """不做模糊/前缀匹配——非精确名称一律视为未识别。"""
        flags, unknown = resolve_experiment_flags(["signal", "signal_pre_dig", "辩论"])
        assert flags == set()
        assert unknown == ["signal", "signal_pre_dig", "辩论"]

    @pytest.mark.edge
    def test_display_name_is_case_sensitive(self):
        """显示名按精确匹配（不做大小写折叠，避免与英文开关名互相误伤）。"""
        flags, unknown = resolve_experiment_flags(["信号预digest"])
        assert flags == set()
        assert unknown == ["信号预digest"]

    @pytest.mark.edge
    def test_duplicate_unknown_preserved(self):
        """重复的未识别项按原始输入逐条保留，便于报错时完整回显。"""
        flags, unknown = resolve_experiment_flags(["bad", "bad"])
        assert flags == set()
        assert unknown == ["bad", "bad"]
