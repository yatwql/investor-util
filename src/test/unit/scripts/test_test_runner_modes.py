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

import itertools

import pytest
from src.test._script_loader import load_script


@pytest.mark.unit_scripts
class TestDevVerifyPreflightDedup:
    """dev-verify preflight 只允许轻量编号快检（与 pre-commit 钩子去重）。"""

    def test_preflight_is_numbering_only(self):
        """preflight 命令清单必须恰好是任务编号快检一项。"""
        modes = load_script("_test_runner/modes.py", module_name="_test_runner_modes_under_test")
        scripts = [cmd[1] for cmd in modes.MODES["dev-verify"].get("preflight", [])]
        assert scripts == ["scripts/check-task-numbering.py"]

    def test_heavy_guards_not_in_preflight(self):
        """重量守护不得回到预检（否则同树重复执行回归）。"""
        modes = load_script("_test_runner/modes.py", module_name="_test_runner_modes_under_test")
        joined = " ".join(" ".join(cmd) for cmd in modes.MODES["dev-verify"].get("preflight", []))
        assert "check-doc-drift" not in joined
        assert "check-test-redundancy" not in joined

    def test_preflight_entries_are_ci_guards(self):
        """预检条目必须指向 scripts/ 下的守护脚本并带 --ci（契约不破形）。"""
        modes = load_script("_test_runner/modes.py", module_name="_test_runner_modes_under_test")
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
        modes = load_script("_test_runner/modes.py", module_name="_test_runner_modes_under_test")
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


@pytest.mark.unit_scripts
class TestMarkerExprSingleSource:
    """marker 表达式单源：MODES 是唯一定义处，编译谓词与 `-m` 实跑同源求值。"""

    @staticmethod
    def _modes():
        return load_script("_test_runner/modes.py", module_name="_test_runner_modes_under_test")

    def test_every_mode_resolves_compilable_expression(self):
        """注册表里每个模式（含只有阶段 marker 的 dev-verify）都要能解析并编译。"""
        modes = self._modes()
        for name in modes.MODES:
            expr = modes.mode_marker_expr(name)
            assert isinstance(expr, str)
            assert callable(modes.compile_marker_expr(expr))

    def test_phase_marker_used_when_top_level_absent(self):
        modes = self._modes()
        assert "marker" not in modes.MODES["dev-verify"]
        assert modes.mode_marker_expr("dev-verify") == modes.MODES["dev-verify"]["phases"][0]["marker"]

    def test_top_level_marker_used_when_present(self):
        modes = self._modes()
        assert modes.mode_marker_expr("verify") == modes.MODES["verify"]["marker"]

    def test_expression_follows_registry_edit(self, monkeypatch):
        """改注册表里的表达式 → 解析结果跟着变（证明是读表而非抄写/缓存）。"""
        modes = self._modes()
        monkeypatch.setitem(modes.MODES, "unit", {**modes.MODES["unit"], "marker": "unit_report"})
        pred = modes.compile_marker_expr(modes.mode_marker_expr("unit"))
        assert pred({"unit_report"}) is True
        assert pred({"unit_core"}) is False

    def test_empty_expression_matches_everything(self):
        """空表达式 = 不过滤（与 test-runner 空 marker 不传 -m 同口径）。"""
        pred = self._modes().compile_marker_expr("")
        assert pred({"live"}) is True
        assert pred(set()) is True

    @pytest.mark.parametrize(
        ("expr", "markers", "expected"),
        [
            ("unit", {"unit"}, True),
            ("unit", {"edge"}, False),
            ("unit and not (edge or data)", {"unit"}, True),
            ("unit and not (edge or data)", {"unit", "edge"}, False),
            ("unit and not (edge or data)", {"unit", "data"}, False),
            ("scenario or integration", {"integration"}, True),
            ("scenario or integration", {"unit"}, False),
            ("not unit and not live", {"scenario"}, True),
            ("not unit and not live", {"live"}, False),
            ("not unit and not live", {"unit"}, False),
            ("scenario_extreme", {"scenario"}, False),
            ("scenario_extreme", {"scenario_extreme"}, True),
        ],
    )
    def test_boolean_semantics_match_dash_m(self, expr, markers, expected):
        """真值表断言（与 -m 布尔语义逐项对拍，独立于实现写死期望）。"""
        assert self._modes().compile_marker_expr(expr)(set(markers)) is expected

    def test_malformed_expression_fails_loudly(self):
        """语法错误在编译期暴露，不带病进入计数。"""
        with pytest.raises(SyntaxError):
            self._modes().compile_marker_expr("unit and")
