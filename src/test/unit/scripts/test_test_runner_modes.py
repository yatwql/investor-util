"""测试：test-runner 模式注册表 —— preflight 去重契约 + dev-verify 双阶段合一。

回归背景：dev-verify 预检曾内置 check-doc-drift / check-test-redundancy 两个重量守护，
与 pre-commit 钩子的十守护在同一批次内对**同一待提交树**重复执行——其中
check-test-redundancy 全量 AST 解析约 3.5s/次，一轮任务最多跑 3 遍（冗余调用主因）。

去重设计：预检只保留 <100ms 的任务编号快检（fail-fast），重量守护由 pre-commit
钩子唯一执行、CI guards job 全量兜底；本文件锁死该契约，防止后续把重量守护加回预检。

双阶段合一：dev-verify 原「核心单元 Phase A + 基础场景 Phase B」两轮 pytest 收敛为
单轮并集 marker——用例集合必须与原两阶段并集布尔等价（零重叠零遗漏），否则
验收口径（收集数对拍）失效。
"""

from __future__ import annotations

import importlib.util
import itertools
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MODES_PATH = _REPO_ROOT / "scripts" / "_test_runner" / "modes.py"


def _load_modes():
    spec = importlib.util.spec_from_file_location("_test_runner_modes_under_test", _MODES_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit_scripts
class TestDevVerifyPreflightDedup:
    """dev-verify preflight 只允许轻量编号快检（与 pre-commit 钩子去重）。"""

    def test_preflight_is_numbering_only(self):
        """preflight 命令清单必须恰好是任务编号快检一项。"""
        modes = _load_modes()
        scripts = [cmd[1] for cmd in modes.MODES["dev-verify"].get("preflight", [])]
        assert scripts == ["scripts/check-task-numbering.py"]

    def test_heavy_guards_not_in_preflight(self):
        """重量守护不得回到预检（否则同树重复执行回归）。"""
        modes = _load_modes()
        joined = " ".join(" ".join(cmd) for cmd in modes.MODES["dev-verify"].get("preflight", []))
        assert "check-doc-drift" not in joined
        assert "check-test-redundancy" not in joined

    def test_preflight_entries_are_ci_guards(self):
        """预检条目必须指向 scripts/ 下的守护脚本并带 --ci（契约不破形）。"""
        modes = _load_modes()
        preflight = modes.MODES["dev-verify"].get("preflight", [])
        assert preflight, "preflight 不得为空（fail-fast 快检须保留）"
        for cmd in preflight:
            assert cmd[1].startswith("scripts/check-")
            assert "--ci" in cmd


@pytest.mark.unit_scripts
class TestDevVerifySinglePhaseMerge:
    """dev-verify 双阶段合一：单轮 marker ≡ 原两阶段并集（用例集合零变化）。"""

    #: 原 Phase A 核心单元域子标记（合一表达式的组成部分）
    _UNIT_DOMAIN = (
        "unit_core",
        "unit_providers",
        "unit_fetcher",
        "unit_analysis",
        "unit_scripts",
        "unit_web",
        "unit_report",
    )

    @staticmethod
    def _phase() -> dict:
        modes = _load_modes()
        phases = modes.MODES["dev-verify"]["phases"]
        assert len(phases) == 1, "dev-verify 必须单阶段（合一后回退两阶段会重复付收集与 worker 启动）"
        return phases[0]

    def test_marker_covers_both_domains(self):
        """单轮 marker 必须同时覆盖核心单元域与基础场景域，并保持 edge/data 排除。"""
        marker = self._phase()["marker"]
        assert "scenario_basic" in marker
        for name in self._UNIT_DOMAIN:
            assert name in marker
        assert "not (edge or data)" in marker

    def test_marker_boolean_equivalent_to_phase_union(self):
        """布尔等价对拍：marker ≡（任一单元域 ∧ ¬edge ∧ ¬data）∨ 基础场景——全组合枚举。"""
        marker = self._phase()["marker"]
        names = (*self._UNIT_DOMAIN, "edge", "data", "scenario_basic")
        for combo in itertools.product((False, True), repeat=len(names)):
            env = dict(zip(names, combo))
            expected = (any(env[n] for n in self._UNIT_DOMAIN) and not env["edge"] and not env["data"]) or env[
                "scenario_basic"
            ]
            assert eval(marker, {"__builtins__": {}}, env) == expected  # noqa: S307 — 受控注册表表达式，仅布尔标识符

    def test_timeout_budget_is_sum_of_legacy_phases(self):
        """超时预算 = 原两阶段 300s×2 之和（合并不缩总预算、不放宽单轮包络）。"""
        assert self._phase()["timeout_sec"] == 300 * 2
