"""测试：scripts/probe.py 统一入口 registry 分发与幻觉率 sampler 契约接入。

覆盖：
  - probe 入口：空参列出 target、未知 target 退出 2、分发到子模块 run()
  - probes/csi 与 probes/push2 子模块契约面（PROBE_TARGET / build_parser）
  - sampler 拆包后对 fact_checker 真实模块的契约（4 元组解包、corrections 键、
    组合核心数值委托 _utils 唯一实现）
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _ensure_scripts_on_path() -> None:
    """把 scripts/ 注入 sys.path（**幂等单点**；sampler 拆包后的扁平辅助包直接 import 需要）。"""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))


_ensure_scripts_on_path()  # 模块级唯一注入点：契约测试在测试体内直接 import _halluc_sampler
pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts]


def _load_script(rel_path: str, mod_name: str):
    """按路径加载脚本模块（scripts/ 目录下的扁平脚本没有包语境）。"""
    fpath = _REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def probe_entry():
    # 路径注入已在模块级单点完成（probe.py 加载时自身亦会插入同目录）——此处不再重复注入
    return _load_script("scripts/probe.py", "probe_entry")


# ═══ probe 入口 ═══


class TestProbeEntry:
    def test_no_args_lists_targets(self, probe_entry, capsys):
        assert probe_entry.main([]) == 0
        out = capsys.readouterr().out
        assert "csi" in out and "push2" in out

    def test_unknown_target_exit_two(self, probe_entry, capsys):
        assert probe_entry.main(["nope"]) == 2
        assert "未知 target" in capsys.readouterr().out

    def test_dispatches_to_submodule_run(self, probe_entry):
        """按 target 名分发到子模块 run()，透传其退出码（含非 0）。"""
        calls: list[Any] = []
        fake_args = object()

        class FakeModule:
            PROBE_TARGET = "fake"

            @staticmethod
            def build_parser():
                import argparse

                parser = argparse.ArgumentParser(prog="fake")
                parser.parse_args = staticmethod(lambda _argv: fake_args)
                return parser

            @staticmethod
            def run(args):
                calls.append(args)
                return 7

        with (
            patch.object(probe_entry, "get", return_value=FakeModule()),
            patch.object(probe_entry, "available_targets", return_value={"fake"}),
        ):
            rc = probe_entry.main(["fake", "x"])

        assert rc == 7 and calls == [fake_args]


class TestProbeTargetContracts:
    def test_registered_targets(self):
        from probes import available_targets

        assert {"csi", "push2"} <= available_targets()

    def test_csi_submodule_surface(self):
        from probes import get

        csi = get("csi")
        assert csi.PROBE_TARGET == "csi"
        help_text = csi.build_parser().format_help()
        assert "--days" in help_text and "--stale" in help_text

    def test_push2_submodule_surface(self):
        from probes import get

        push2 = get("push2")
        assert push2.PROBE_TARGET == "push2"
        assert "push2" in push2.build_parser().format_help()


# ═══ sampler 契约接入 ═══


class TestSamplerContract:
    def test_run_fact_check_unpacks_scoring_tuple_and_exposes_corrections(self):
        """数值检查器 v3 返回 4 元组——拆包后正确解包并透出 corrections 键。"""
        from _halluc_sampler import _run_fact_check

        holdings = [
            {
                "code": "110011",
                "name": "易方达中小盘混合",
                "mv": 10000.0,
                "cost": 9000.0,
                "profit": 1000.0,
                "profit_rate": 0.111,
            },
        ]
        result = _run_fact_check(
            "本组合总市值 10000 元，总成本 9000 元，持仓收益 1000 元，收益约为 11.1%。",
            holdings,
            module_label="expert_review",
            extra_valid_codes=set(),
            is_penetration_module=False,
        )
        assert isinstance(result["numerical_corrections"], list)
        assert 0.0 <= result["hallucination_rate"] <= 1.0
        assert set(result["issues"]) >= {"numerical", "symbol", "rank"}

    def test_portfolio_values_delegates_to_utils_implementation(self):
        """组合核心数值委托 fact_checker._utils 的唯一实现（拆包前坏 import 已修）。"""
        from _halluc_sampler import _compute_portfolio_values

        vals = _compute_portfolio_values(
            [{"code": "110011", "market_value": 10000.0, "cost": 9000.0, "profit": 1000.0}]
        )
        assert vals["total_mv"] == 10000.0
        assert vals["total_today_profit"] == 0.0


# ═══ 路径注入单点契约 ═══


class TestScriptsPathInjection:
    def test_scripts_dir_on_path(self):
        """sampler 契约测试依赖：scripts/ 已由模块级单点注入进 sys.path。"""
        assert str(_SCRIPTS_DIR) in sys.path

    def test_ensure_scripts_on_path_idempotent(self):
        """重复调用注入辅助函数不向 sys.path 追加重复条目（幂等保护回归）。"""
        before = sys.path.count(str(_SCRIPTS_DIR))
        _ensure_scripts_on_path()
        _ensure_scripts_on_path()
        assert sys.path.count(str(_SCRIPTS_DIR)) == before
