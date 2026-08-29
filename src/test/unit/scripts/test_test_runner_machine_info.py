"""测试：test-runner.py 机器信息采集与耗时表格渲染

覆盖：
  - 机器信息采集：字段完整性、并行级别映射、Linux 采集读取在 /proc 缺失时回退 None 不崩溃
  - bench 别名展开：14 个对照表模式、去重保序、不含 live、非 bench 原样透传
  - 耗时表格渲染：表头与行格式、按对照表顺序排序、verify,regression 组合行、
    约值取整与下限、跳过超时与不在对照表内的模式
  - 机器信息行渲染：字段齐全时正常、缺失时以"未知"占位

测试通过 import 方式直接复用 _collect_machine_info / _resolve_modes /
_render_duration_table 等函数，不运行真实 CLI、不触发任何测试执行。
"""

from __future__ import annotations

import builtins
import importlib.util
import os
import platform
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def runner_script():
    return _load_script("test-runner.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


class TestMachineInfo:
    """机器信息采集：字段完整性、并行级别、Linux 回退。"""

    def test_machine_info_shape(self, runner_script):
        info = runner_script._collect_machine_info("medium")
        required_keys = {
            "os", "os_release", "arch", "hostname", "cpu_model",
            "cpu_physical_cores", "cpu_threads", "mem_gib", "disk_type",
            "fs_type", "python_version", "parallel_level", "parallel_workers",
            "date",
        }
        assert required_keys <= set(info)
        assert info["os"] == platform.system()
        assert info["cpu_threads"] == os.cpu_count()
        assert info["date"]

    def test_machine_info_parallel_workers(self, runner_script):
        info = runner_script._collect_machine_info("high")
        assert info["parallel_level"] == "high"
        assert info["parallel_workers"] == runner_script._calc_parallel_workers("high")

    @pytest.mark.skipif(sys.platform != "linux", reason="依赖 Linux 读取路径")
    def test_linux_readers_fallback_when_proc_missing(self, runner_script, monkeypatch):
        original_open = builtins.open

        def fake_open(path, *args, **kwargs):
            if isinstance(path, str) and any(
                marker in path for marker in ("cpuinfo", "meminfo", "mounts")
            ):
                raise OSError("simulated missing")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", fake_open)
        assert runner_script._read_cpu_model_linux() is None
        assert runner_script._count_physical_cores_linux() is None
        assert runner_script._mem_gib_linux() is None
        fs, disk = runner_script._linux_disk_info()
        assert fs is None and disk is None

    @pytest.mark.skipif(sys.platform != "linux", reason="依赖 Linux 读取路径")
    def test_collect_machine_info_no_crash_when_proc_missing(self, runner_script, monkeypatch):
        monkeypatch.setattr(runner_script, "_read_cpu_model_linux", lambda: None)
        monkeypatch.setattr(runner_script, "_count_physical_cores_linux", lambda: None)
        monkeypatch.setattr(runner_script, "_mem_gib_linux", lambda: None)
        monkeypatch.setattr(runner_script, "_linux_disk_info", lambda: (None, None))
        info = runner_script._collect_machine_info("medium")
        assert info["cpu_model"] is None
        assert info["cpu_threads"] == os.cpu_count()
        assert info["os"] == platform.system()


class TestResolveModes:
    """bench 别名展开：聚合序列、去重保序、排除 live、非 bench 透传。"""

    def test_resolve_bench_expands_all_table_modes(self, runner_script):
        resolved = runner_script._resolve_modes(["bench"])
        assert resolved == list(runner_script._BENCH_MODES)
        assert len(resolved) == 14
        assert set(resolved) == set(runner_script._MODE_TABLE_ORDER)

    def test_resolve_bench_excludes_live(self, runner_script):
        assert "live" not in runner_script._resolve_modes(["bench"])

    def test_resolve_bench_dedup_keeps_first_order(self, runner_script):
        expected = list(runner_script._BENCH_MODES)
        assert runner_script._resolve_modes(["unit", "bench"]) == expected
        assert runner_script._resolve_modes(["bench", "unit"]) == expected
        scenario_first = runner_script._resolve_modes(["scenario", "bench"])
        assert len(scenario_first) == 14
        assert scenario_first[0] == "scenario"

    def test_resolve_non_bench_passthrough(self, runner_script):
        assert runner_script._resolve_modes(["unit", "edge"]) == ["unit", "edge"]
        assert runner_script._resolve_modes([]) == []


class TestDurationTable:
    """耗时表格渲染：顺序、组合行、约值取整、超时与未知模式跳过。"""

    @staticmethod
    def _res(mode, passed=1, duration=1.0, **overrides):
        base = {"mode": mode, "passed": passed, "failed": 0, "skipped": 0,
                "errors": 0, "duration": duration, "exit_code": 0, "timed_out": False}
        base.update(overrides)
        return base

    def test_render_duration_table_headers_and_rows(self, runner_script):
        text = runner_script._render_duration_table([self._res("unit", 4672, 15.2)])
        assert "| `--mode` | 覆盖项数 | 耗时 |" in text
        assert "| `unit` | 4672 | ~15s |" in text

    def test_render_duration_table_sorted_by_table_order(self, runner_script):
        text = runner_script._render_duration_table(
            [self._res("regression", 241, 17.4), self._res("unit", 4672, 15.2),
             self._res("scenario_extreme", 9, 2.1)]
        )
        idx_unit = text.index("`unit`")
        idx_reg = text.index("`regression`")
        idx_ext = text.index("`scenario_extreme`")
        assert idx_unit < idx_reg < idx_ext

    def test_render_duration_table_combined_row(self, runner_script):
        text = runner_script._render_duration_table(
            [self._res("regression", 241, 17.4), self._res("verify", 3016, 10.2)]
        )
        combined = "| `verify,regression` | 3257 | ~28s（verify+regression 之和） |"
        assert combined in text
        idx_reg = text.index("`regression`")
        idx_comb = text.index("`verify,regression`")
        assert idx_comb > idx_reg

    def test_render_duration_table_rounding_and_min_clamp(self, runner_script):
        assert runner_script._approx_sec(15.3) == 15
        assert runner_script._approx_sec(15.6) == 16
        assert runner_script._approx_sec(0.4) == 1

    def test_render_duration_table_skips_timeout_and_unknown(self, runner_script):
        text = runner_script._render_duration_table(
            [self._res("unit", 4672, 15.2), self._res("edge", 1, 300.0, timed_out=True),
             self._res("live", 14, 5.0)]
        )
        assert "`edge`" not in text
        assert "`live`" not in text
        assert "`unit`" in text


class TestEnvTable:
    """环境属性表与机器信息行渲染。"""

    def test_render_env_table_has_all_rows(self, runner_script):
        info = {
            "os": "Linux", "os_release": "6.1", "arch": "x86_64",
            "hostname": "host-a", "cpu_model": "cpu-x", "cpu_physical_cores": 12,
            "cpu_threads": 16, "mem_gib": 46.8, "disk_type": "NVMe SSD",
            "fs_type": "btrfs", "python_version": "3.13", "parallel_level": "medium",
            "parallel_workers": "8", "date": "2026-08-05",
        }
        text = runner_script._render_env_table(info)
        for label in ("操作系统", "系统版本", "架构", "主机名", "CPU 型号", "物理核数",
                      "逻辑线程", "内存", "磁盘类型", "文件系统", "Python 版本",
                      "并行级别", "worker 数", "采集日期"):
            assert f"| {label} |" in text
        assert "46.8 GiB" in text

    def test_render_env_table_unknown_fallback(self, runner_script):
        info = {k: None for k in (
            "os", "os_release", "arch", "hostname", "cpu_model", "cpu_physical_cores",
            "cpu_threads", "mem_gib", "disk_type", "fs_type", "python_version",
            "parallel_level", "parallel_workers", "date",
        )}
        text = runner_script._render_env_table(info)
        assert "未知" in text

    def test_format_machine_info_renders_fields(self, runner_script):
        info = {
            "os": "Linux", "arch": "x86_64", "os_release": "6.1", "hostname": "host-a",
            "cpu_model": "cpu-x", "cpu_physical_cores": 12, "cpu_threads": 16,
            "mem_gib": 46.8, "disk_type": "NVMe SSD", "fs_type": "btrfs",
            "python_version": "3.13", "parallel_level": "medium",
            "parallel_workers": "8", "date": "2026-08-05",
        }
        line = runner_script._format_machine_info(info)
        assert "Linux x86_64" in line
        assert "cpu-x" in line
        assert "12 核 16 线程" in line
        assert "46.8 GiB" in line
        assert "worker=8" in line
        assert "2026-08-05" in line

    def test_format_machine_info_unknown_fallback(self, runner_script):
        info = {k: None for k in (
            "os", "os_release", "arch", "hostname", "cpu_model", "cpu_physical_cores",
            "cpu_threads", "mem_gib", "disk_type", "fs_type", "python_version",
            "parallel_level", "parallel_workers", "date",
        )}
        line = runner_script._format_machine_info(info)
        assert "未知" in line
