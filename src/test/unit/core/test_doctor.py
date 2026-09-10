"""系统自检单元测试。

覆盖三件事：
  1. 自检**永不抛异常**——环境/配置/目录任一项坏掉都要转成失败结果行，
     否则「配置坏了」时用户看到的是 traceback，而这正是最需要诊断输出的场景；
  2. 结果结构完整（group/label/ok/message/hint），分组顺序稳定；
  3. 渲染与统计与结果一致。
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.python.core import doctor
from src.python.core.doctor import (
    GROUP_CONFIG,
    GROUP_DIRS,
    GROUP_ENV,
    GROUP_FEATURES,
    GROUP_ORDER,
    format_doctor_report,
    run_doctor_checks,
    summarize_doctor_results,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


def _local_checks() -> list[dict]:
    """仅本地自检（不联网）——所有测试都走这条路径，避免真网络依赖。"""
    return run_doctor_checks(include_network=False)


@pytest.mark.unit
@pytest.mark.unit_core
class TestResultShape:
    """结果结构契约。"""

    def test_returns_non_empty_list(self):
        assert _local_checks()

    def test_every_item_has_required_keys(self):
        for item in _local_checks():
            assert set(item) >= {"group", "label", "ok", "message", "hint"}, item

    def test_ok_is_bool(self):
        for item in _local_checks():
            assert isinstance(item["ok"], bool), item

    def test_groups_follow_declared_order(self):
        """分组顺序稳定——两次自检结果可直接逐行对比。"""
        groups = [item["group"] for item in _local_checks()]
        order = {g: i for i, g in enumerate(GROUP_ORDER)}
        assert groups == sorted(groups, key=lambda g: order[g])

    def test_local_checks_cover_core_groups(self):
        groups = {item["group"] for item in _local_checks()}
        assert {GROUP_ENV, GROUP_CONFIG, GROUP_DIRS, GROUP_FEATURES} <= groups

    def test_network_group_absent_when_disabled(self):
        assert all(item["group"] != doctor.GROUP_NETWORK for item in _local_checks())


@pytest.mark.unit
@pytest.mark.unit_core
class TestNeverRaises:
    """自检必须永不抛异常——这是它存在的意义。"""

    def test_broken_config_yields_failure_item_not_exception(self):
        with patch("src.python.config.get_config", side_effect=RuntimeError("配置文件损坏")):
            results = _local_checks()

        config_items = [r for r in results if r["group"] == GROUP_CONFIG]
        assert config_items
        assert any(not r["ok"] for r in config_items)
        assert any("配置文件损坏" in r["message"] for r in config_items)

    def test_broken_features_registry_yields_failure_item(self):
        with patch("src.python.config.features.is_feature_enabled", side_effect=RuntimeError("坏了")):
            results = _local_checks()

        feature_items = [r for r in results if r["group"] == GROUP_FEATURES]
        assert feature_items
        assert any(not r["ok"] for r in feature_items)

    def test_network_check_failure_does_not_raise(self):
        with patch("src.python.core.check_sources.run_health_checks", side_effect=RuntimeError("DNS 挂了")):
            results = run_doctor_checks(include_network=True)

        network_items = [r for r in results if r["group"] == doctor.GROUP_NETWORK]
        assert network_items
        assert any(not r["ok"] for r in network_items)


@pytest.mark.unit
@pytest.mark.unit_core
class TestEnvironmentChecks:
    """环境项：解释器版本与虚拟环境。"""

    def test_python_version_ok_on_supported_interpreter(self):
        items = [r for r in _local_checks() if r["label"] == "Python 版本"]
        assert len(items) == 1
        assert items[0]["ok"] is True

    def test_old_python_reports_failure_with_hint(self):
        """低于下限 → 失败且给出可执行建议，而非只报版本号。"""
        with patch.object(doctor, "MIN_PYTHON", (99, 0)):
            item = doctor._check_python_version()

        assert item["ok"] is False
        assert item["hint"]

    def test_venv_detection_reflects_running_interpreter(self):
        item = doctor._check_venv()
        expected = __import__("sys").prefix != getattr(__import__("sys"), "base_prefix", __import__("sys").prefix)
        assert item["ok"] is expected

    def test_not_in_venv_reports_failure_with_hint(self):
        with patch.object(doctor.sys, "prefix", "/usr"), patch.object(doctor.sys, "base_prefix", "/usr"):
            item = doctor._check_venv()

        assert item["ok"] is False
        assert "python" in item["hint"].lower()


@pytest.mark.unit
@pytest.mark.unit_core
class TestDirectoryChecks:
    """目录项：可写性探测不得留下哨兵文件。"""

    def test_writable_directory_passes_and_leaves_no_residue(self, tmp_path):
        ok, message = doctor._check_writable(str(tmp_path))

        assert ok is True
        assert message == "可读写"
        assert os.listdir(tmp_path) == [], "探测哨兵文件必须清理干净"

    def test_missing_directory_fails(self, tmp_path):
        ok, message = doctor._check_writable(str(tmp_path / "nope"))

        assert ok is False
        assert "不存在" in message

    def test_readonly_directory_fails(self, tmp_path):
        if os.geteuid() == 0:
            pytest.skip("以 root 运行：权限位对 root 不生效，该场景无法构造")

        target = tmp_path / "ro"
        target.mkdir()
        target.chmod(0o500)
        try:
            ok, _message = doctor._check_writable(str(target))
        finally:
            target.chmod(0o700)

        assert ok is False, "只读目录必须被判为不可写"

    def test_holdings_dir_missing_is_reported(self):
        with patch("src.python.config.get_config", return_value={"holdings_dir": "/nonexistent/holdings"}):
            items = [r for r in doctor._check_directories() if r["label"] == "持仓目录"]

        assert items and not items[0]["ok"]

    def test_output_dir_unwritable_is_reported(self, tmp_path):
        target = tmp_path / "out"
        target.mkdir()
        with patch("src.python.config.get_config", return_value={"output_dir": str(target)}), patch.object(
            doctor, "_check_writable", return_value=(False, "不可写: 权限不足")
        ):
            items = [r for r in doctor._check_directories() if r["label"] == "输出目录"]

        assert items and not items[0]["ok"]


@pytest.mark.unit
@pytest.mark.unit_core
class TestFeatureGateReporting:
    """实验功能清单上屏（信息性，不改结论）。"""

    def test_no_experiment_enabled_is_ok(self):
        with patch("src.python.config.features.is_feature_enabled", return_value=False):
            items = doctor._check_experimental_features()

        assert items[0]["ok"] is True
        assert "未启用" in items[0]["message"]

    def test_enabled_experiments_listed_by_display_name(self):
        def _enabled(flag: str) -> bool:
            return flag == "doctor_check"

        with patch("src.python.config.features.is_feature_enabled", side_effect=_enabled):
            items = doctor._check_experimental_features()

        assert items[0]["ok"] is True
        assert "系统自检" in items[0]["message"]


@pytest.mark.unit
@pytest.mark.unit_core
class TestSummaryAndRender:
    """统计与渲染。"""

    def test_summary_counts(self):
        results = [
            {"group": "G", "label": "a", "ok": True, "message": "", "hint": ""},
            {"group": "G", "label": "b", "ok": False, "message": "", "hint": ""},
            {"group": "G", "label": "c", "ok": True, "message": "", "hint": ""},
        ]
        assert summarize_doctor_results(results) == (2, 1)

    def test_summary_on_empty(self):
        assert summarize_doctor_results([]) == (0, 0)

    def test_render_includes_every_label_and_footer(self):
        results = _local_checks()
        text = format_doctor_report(results)

        for item in results:
            assert item["label"] in text
        assert f"共 {len(results)} 项" in text

    def test_render_shows_hint_only_for_failures(self):
        results = [
            {"group": "G", "label": "好的", "ok": True, "message": "m", "hint": "不该显示"},
            {"group": "G", "label": "坏的", "ok": False, "message": "m", "hint": "照此修复"},
        ]
        text = format_doctor_report(results)

        assert "照此修复" in text
        assert "不该显示" not in text

    def test_render_marks_experimental_status(self):
        """自检是实验功能——输出必须自陈，不让用户误以为它是稳定结论。"""
        assert "doctor_check" in format_doctor_report([])

    def test_render_plain_when_color_disabled(self):
        text = format_doctor_report(_local_checks(), use_color=False)
        assert "\033[" not in text

    def test_render_colored_when_requested(self):
        text = format_doctor_report(
            [{"group": "G", "label": "x", "ok": True, "message": "m", "hint": ""}], use_color=True
        )
        assert "\033[" in text
