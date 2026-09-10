"""实验功能注册表与名称解析单元测试。

覆盖 ``features.EXPERIMENTAL_FEATURES`` 注册表驱动的名称解析
（``resolve_experiment_flags`` / ``describe_experiment_flags``），
该解析是 CLI ``--experiment`` 参数与 TUI 菜单 S / Web 配置面板同源的保证。
"""

from __future__ import annotations

import pytest

from src.python.config.features import (
    EXPERIMENT_ALL,
    EXPERIMENTAL_FEATURES,
    describe_experiment_flags,
    resolve_experiment_flags,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]

@pytest.mark.unit
class TestResolveExperimentFlags:
    """实验功能名解析测试。"""

    def test_resolve_by_flag_name(self):
        """按开关名解析。"""
        flags, unknown = resolve_experiment_flags(["signal_pre_digest"])
        assert flags == {"signal_pre_digest"}
        assert unknown == []

    def test_resolve_by_display_name(self):
        """按中文显示名解析（注册表驱动，无需维护第二份清单）。"""
        display_name = EXPERIMENTAL_FEATURES["signal_pre_digest"][0]
        flags, unknown = resolve_experiment_flags([display_name])
        assert flags == {"signal_pre_digest"}
        assert unknown == []

    def test_resolve_every_registry_entry(self):
        """注册表中每个实验功能的开关名与显示名均可解析。"""
        for flag, (display_name, _desc) in EXPERIMENTAL_FEATURES.items():
            by_flag, unknown_flag = resolve_experiment_flags([flag])
            by_name, unknown_name = resolve_experiment_flags([display_name])
            assert by_flag == {flag}, f"开关名解析失败: {flag}"
            assert by_name == {flag}, f"显示名解析失败: {display_name}"
            assert unknown_flag == [] and unknown_name == []

    def test_resolve_flag_name_case_insensitive(self):
        """开关名大小写不敏感。"""
        flags, unknown = resolve_experiment_flags(["SIGNAL_PRE_DIGEST"])
        assert flags == {"signal_pre_digest"}
        assert unknown == []

    def test_resolve_all(self):
        """all 解析为全部实验功能。"""
        flags, unknown = resolve_experiment_flags([EXPERIMENT_ALL])
        assert flags == set(EXPERIMENTAL_FEATURES)
        assert unknown == []

    def test_resolve_mixed_and_dedup(self):
        """多种写法混用并去重。"""
        display_name = EXPERIMENTAL_FEATURES["decision_reflection"][0]
        flags, unknown = resolve_experiment_flags(
            ["signal_pre_digest", "SIGNAL_PRE_DIGEST", display_name, "all"]
        )
        assert flags == set(EXPERIMENTAL_FEATURES)
        assert unknown == []

    def test_unknown_reported_but_hits_kept(self):
        """未识别项进入 unknown，已识别项仍正常解析。"""
        flags, unknown = resolve_experiment_flags(["signal_pre_digest", "no_such_feature"])
        assert flags == {"signal_pre_digest"}
        assert unknown == ["no_such_feature"]

    def test_describe_lists_all_entries(self):
        """清单描述串覆盖全部开关名与显示名。"""
        text = describe_experiment_flags()
        for flag, (display_name, _desc) in EXPERIMENTAL_FEATURES.items():
            assert flag in text
            assert display_name in text
