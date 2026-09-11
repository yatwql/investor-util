"""功能开关名解析边缘/异常场景测试。

必须放在 *_edge.py 文件中（pytest_collection_modifyitems 强制约束）。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.config.features import (
    FEATURE_FLAGS,
    GROUP_EXPERIMENTAL,
    parse_switch_override,
    resolve_experiment_flags,
    save_feature_overrides,
    switches_in_group,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_config, pytest.mark.edge]


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
        assert flags == {flag for flag, _d in switches_in_group(GROUP_EXPERIMENTAL)}
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


@pytest.mark.edge
class TestParseSwitchOverrideEdge:
    """``--feature NAME=VALUE`` 取值解析的畸形输入。"""

    @pytest.mark.edge
    def test_empty_value_raises(self):
        """``doctor_check=`` → 取值空串视为笔误，报错而非按 false 处理。"""
        with pytest.raises(ValueError):
            parse_switch_override("doctor_check=")

    @pytest.mark.edge
    def test_equals_only_raises(self):
        """孤立 ``=`` → 缺开关名，报错。"""
        with pytest.raises(ValueError) as err:
            parse_switch_override("=on")
        assert "NAME=VALUE" in str(err.value)

    @pytest.mark.edge
    def test_empty_string_raises(self):
        """空串 → 报错（不静默当作未指定）。"""
        with pytest.raises(ValueError):
            parse_switch_override("")

    @pytest.mark.edge
    def test_value_with_extra_equals_keeps_full_value(self):
        """取值含多余 ``=`` → 整段参与词表比对，识别不了即报错，不静默截断。"""
        with pytest.raises(ValueError):
            parse_switch_override("doctor_check=off=extra")

    @pytest.mark.edge
    def test_name_case_sensitive(self):
        """开关名不做大小写折叠（取值才折叠）——防止两个开关名折叠后互相误伤。"""
        with pytest.raises(ValueError):
            parse_switch_override("DOCTOR_CHECK=off")


@pytest.mark.edge
class TestSaveFeatureOverridesEdge:
    """开关覆写落盘失败边缘场景（落盘委托 core/atomic_write）。"""

    @pytest.mark.edge
    def test_write_failure_does_not_raise_and_syncs_runtime(self):
        """落盘失败 → 不抛出，且运行时开关仍按本次覆写同步。

        落盘属尽力持久化（原语只记日志返回 False）：写不进盘不能中断调用链，
        更不能让"本次运行已生效"的内存态回退成旧值。
        """
        with (
            patch("src.python.config.features.write_json_atomic", return_value=False),
            patch.dict(FEATURE_FLAGS, {"signal_pre_digest": True}, clear=False),
        ):
            save_feature_overrides({"signal_pre_digest": False}, merge=False)  # 不抛
            assert FEATURE_FLAGS["signal_pre_digest"] is False
