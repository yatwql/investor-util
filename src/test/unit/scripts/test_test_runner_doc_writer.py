"""测试：test_runner.py 环境耗时对照文档自动更新（--update-docs 写入器）

覆盖：
  - 环境属性表：同名列原地更新/新机器列追加/OS 与系统版本分行/未知行标签保留原值
  - 耗时对照表：同名列更新/新列追加未测留空/组合行 verify,regression/部分结果保留未测行
  - 模式对应测试量表：实测执行计数+耗时回填/未实测与超时保留原值/marker 缺失抛 ValueError
  - 标记定位：start/end marker 缺失抛 ValueError、round-trip 幂等、标记区外文本逐字节不变
  - IO 封装：仅内容变化才写盘、缺标记文件不落盘
  - parse_args：--update-docs 隐含 --machine-info

通过 import 方式直接复用 _update_test_coverage_doc / _update_machine_table /
_duration_mode_cells / _env_value 等函数，不运行真实 CLI、不触发任何测试执行。
"""

from __future__ import annotations

import importlib.util
import os
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
    return _load_script("test_runner.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


# ── 样本数据 ────────────────────────────────────────────────

_MACHINE_INFO = {
    "os": "Linux",
    "os_release": "6.18.25-x64v3-xanmod1",
    "arch": "x86_64",
    "hostname": "dragonball",
    "cpu_model": "13th Gen Intel(R) Core(TM) i5-13500H",
    "cpu_physical_cores": 12,
    "cpu_threads": 16,
    "mem_gib": 46.8,
    "disk_type": "NVMe SSD",
    "fs_type": "btrfs",
    "python_version": "3.13.5",
    "parallel_level": "medium",
    "parallel_workers": "8",
    "date": "2026-08-05",
}

_ENV_LABELS = [
    "操作系统",
    "系统版本",
    "架构",
    "主机名",
    "CPU 型号",
    "物理核数",
    "逻辑线程",
    "内存",
    "磁盘类型",
    "文件系统",
    "Python 版本",
    "并行级别",
    "worker 数",
    "采集日期",
]

_DURATION_MODES = [
    "unit",
    "standard",
    "scenario",
    "regression",
    "verify,regression",
    "dev-verify",
    "verify",
    "integration",
    "edge",
    "data",
    "all",
    "smoke",
    "report",
    "all_no_unit",
    "scenario_extreme",
]


def _env_table(col2: str = "旧值", header: str = "dragonball（2026-08-04 实测）", col3: str = "未知") -> list[str]:
    """构造环境属性表（14 数据行；col2 为当前机器列，col3 为历史参考列）。"""
    lines = [f"| 环境属性 | {header} | 旧慢笔记本（早期标注） |"]
    lines.append("|:---------|:---------------------------|:----------------------|")
    lines.extend(f"| {label} | {col2} | {col3} |" for label in _ENV_LABELS)
    return lines


def _duration_table(
    col2: str | dict[str, str] = "旧值", header: str = "dragonball（2026-08-04 实测）", col3: str = "~30s"
) -> list[str]:
    """构造各模式耗时对照表（col2 可传 per-mode dict 便于断言部分保留）。

    末行「数据更新时间」为各设备耗时实测日期（col2 dict 用 `数据更新时间` 键）。
    """
    lines = [f"| `--mode` | {header} | 旧慢笔记本（早期标注，约值） |"]
    lines.append("|:---------|:---------------------------:|:---------------------------:|")
    for mode in _DURATION_MODES:
        c2 = col2.get(mode, "旧值") if isinstance(col2, dict) else col2
        lines.append(f"| `{mode}` | {c2} | {col3} |")
    c2_time = col2.get("数据更新时间", "旧值") if isinstance(col2, dict) else col2
    lines.append(f"| 数据更新时间 | {c2_time} | {col3} |")
    return lines


# 「模式对应测试量」表模式行（对齐文档，无 verify,regression 组合行）
_MODE_COUNT_MODES = [
    "unit",
    "standard",
    "scenario",
    "regression",
    "dev-verify",
    "verify",
    "integration",
    "edge",
    "data",
    "all",
    "smoke",
    "report",
    "all_no_unit",
    "scenario_extreme",
]


def _mode_count_table(col2: str = "旧值", col3: str = "~30s") -> list[str]:
    """构造「模式对应测试量」表（col2 覆盖项数、col3 典型耗时）。"""
    lines = ["| `--mode` 值 | 覆盖项数 | 典型耗时 |"]
    lines.append("|:------------|:--------:|:--------:|")
    lines.extend(f"| `{mode}` | {col2} | {col3} |" for mode in _MODE_COUNT_MODES)
    return lines


def _sample_doc(env_lines: list[str], dur_lines: list[str], with_markers: bool = True) -> str:
    """构造含三对标记 + 前后文案的完整文档样本（模式对应测试量 + 环境耗时对照两表）。"""
    head = [
        "# 测试覆盖统计",
        "",
        "## 说明",
        "> 注：典型耗时按当前开发机实测。",
        "",
        "## 模式对应测试量",
        "",
    ]
    count_block = (
        ["<!-- mode-count-table:start -->"] + _mode_count_table() + ["<!-- mode-count-table:end -->"]
        if with_markers
        else _mode_count_table()
    )
    mid1 = [
        "",
        "### 环境耗时对照",
        "",
        "> 跨机器采集：在新机器上运行 bench 采集。",
        "",
        "#### 采集环境属性",
        "",
    ]
    env_block = ["<!-- env-table:start -->"] + env_lines + ["<!-- env-table:end -->"] if with_markers else env_lines
    mid2 = [
        "",
        "#### 各模式耗时对照",
        "",
    ]
    dur_block = (
        ["<!-- duration-table:start -->"] + dur_lines + ["<!-- duration-table:end -->"] if with_markers else dur_lines
    )
    tail = [
        "",
        "> 两环境差距因模式而异。",
        "",
        "## 尾部内容",
        "end",
    ]
    return "\n".join(head + count_block + mid1 + env_block + mid2 + dur_block + tail)


def _res(mode: str, duration: float = 1.0, **overrides) -> dict:
    base = {
        "mode": mode,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "duration": duration,
        "exit_code": 0,
        "timed_out": False,
    }
    base.update(overrides)
    return base


# ── 环境属性表 ──────────────────────────────────────────────


class TestEnvTableUpdate:
    """环境属性表：同名列更新、新列追加、分行、未知行保留。"""

    def test_env_update_existing_machine_column_refreshes_values_and_date(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        info = dict(_MACHINE_INFO, date="2026-08-06")
        updated = runner_script._update_test_coverage_doc(doc, info, [])
        assert "| 环境属性 | dragonball（2026-08-06 实测） | 旧慢笔记本（早期标注） |" in updated
        assert "| 操作系统 | Linux | 未知 |" in updated
        assert "| 采集日期 | 2026-08-06 | 未知 |" in updated
        # 历史参考列不被触碰
        assert "| 内存 | 46.8 GiB | 未知 |" in updated
        # 不重复追加同名列（dragonball 表头仅一处）
        header = [ln for ln in updated.splitlines() if ln.startswith("| 环境属性 |")][0]
        assert header.count("dragonball") == 1

    def test_env_split_os_and_system_version_rows(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])
        assert "| 操作系统 | Linux | 未知 |" in updated
        assert "| 系统版本 | 6.18.25-x64v3-xanmod1 | 未知 |" in updated
        env_lines = runner_script._extract_table_region(updated, runner_script._DOC_ENV_TABLE_MARKERS)
        assert len(env_lines) == 16  # 表头 + 分隔行 + 14 数据行
        # stdout 渲染表同样 14 行（跳过表头）
        rendered = runner_script._render_env_table(_MACHINE_INFO)
        data_lines = [ln for ln in rendered.splitlines() if ln.startswith("| ")][1:]
        assert len(data_lines) == 14
        assert "| 操作系统 | Linux |" in rendered
        assert "| 系统版本 | 6.18.25-x64v3-xanmod1 |" in rendered

    def test_env_append_new_machine_column(self, runner_script):
        # 无主机名的旧表头 → 追加 dragonball 新列
        doc = _sample_doc(
            _env_table(col2="旧值", header="当前开发机（2026-08-04 实测）"),
            _duration_table(col2="旧值", header="当前开发机（2026-08-04 实测）"),
        )
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])
        assert (
            "| 环境属性 | 当前开发机（2026-08-04 实测） | 旧慢笔记本（早期标注） | dragonball（2026-08-05 实测） |"
            in updated
        )
        assert "| 操作系统 | 旧值 | 未知 | Linux |" in updated
        # 新增列分隔标记：环境表左对齐
        assert "|:---------|:---------------------------|:----------------------|:---|" in updated

    def test_env_unknown_row_label_preserves_existing_cell(self, runner_script):
        env_lines = _env_table(col2="旧值")
        env_lines.append("| 显卡型号 | 旧值 | 未知 |")
        doc = _sample_doc(env_lines, _duration_table(col2="旧值"))
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])
        # 未知属性 → 该行当前机器列保留原值不更新
        assert "| 显卡型号 | 旧值 | 未知 |" in updated
        # 已知行照常更新
        assert "| 内存 | 46.8 GiB | 未知 |" in updated

    def test_env_value_formats_and_unknown_fallback(self, runner_script):
        assert runner_script._env_value("操作系统", _MACHINE_INFO) == "Linux"
        assert runner_script._env_value("系统版本", _MACHINE_INFO) == "6.18.25-x64v3-xanmod1"
        assert runner_script._env_value("内存", _MACHINE_INFO) == "46.8 GiB"
        assert runner_script._env_value("物理核数", {"cpu_physical_cores": None}) == "未知"
        assert runner_script._env_value("内存", {"mem_gib": None}) == "未知"
        assert runner_script._env_value("采集日期", _MACHINE_INFO) == "2026-08-05"
        assert runner_script._env_value("显卡型号", _MACHINE_INFO) is None


# ── 各模式耗时对照表 ────────────────────────────────────────


class TestDurationTableUpdate:
    """耗时对照表：同名列更新、新列追加、组合行、部分结果保留。"""

    def test_duration_update_existing_machine_column(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        results = [_res("unit", 15.2), _res("all", 21.4), _res("verify", 10.2), _res("regression", 17.4)]
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, results)
        assert "| `unit` | ~15s | ~30s |" in updated
        assert "| `all` | ~21s | ~30s |" in updated
        assert "| `verify,regression` | ~28s（verify+regression 顺序之和） | ~30s |" in updated
        # 未实测模式保留原值
        assert "| `standard` | 旧值 | ~30s |" in updated
        # 数据更新时间行：同机列更新为采集日期，历史列保留
        assert "| 数据更新时间 | 2026-08-05 | ~30s |" in updated

    def test_duration_append_new_machine_column_blank_unmeasured(self, runner_script):
        doc = _sample_doc(
            _env_table(col2="旧值", header="当前开发机（2026-08-04 实测）"),
            _duration_table(col2="旧值", header="当前开发机（2026-08-04 实测）"),
        )
        results = [_res("unit", 15.2)]
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, results)
        assert "| `unit` | 旧值 | ~30s | ~15s |" in updated
        # 未测模式留空格子
        assert "| `standard` | 旧值 | ~30s | |" in updated
        # 新增列分隔标记：耗时表居中
        assert "|:---------|:---------------------------:|:---------------------------:|:---:|" in updated
        # 数据更新时间行：新列同样填入采集日期
        assert "| 数据更新时间 | 旧值 | ~30s | 2026-08-05 |" in updated

    def test_duration_update_time_row_matches_machine_date(self, runner_script):
        # 数据更新时间行随采集日期联动（换日期再跑 → 同机列日期刷新）
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        info = dict(_MACHINE_INFO, date="2026-08-06")
        updated = runner_script._update_test_coverage_doc(doc, info, [_res("unit", 15.2)])
        assert "| 数据更新时间 | 2026-08-06 | ~30s |" in updated

    def test_duration_combined_row_and_format(self, runner_script):
        assert runner_script._approx_sec(0.4) == 1
        assert runner_script._approx_sec(15.6) == 16
        assert runner_script._format_approx_duration(0.4) == "~1s"
        assert runner_script._format_approx_duration(21.4) == "~21s"
        assert runner_script._format_approx_duration(59.4) == "~59s"
        assert runner_script._format_approx_duration(600.0) == "~10min"

    def test_duration_partial_results_leave_unmeasured_untouched(self, runner_script):
        old = {m: f"旧{m}" for m in _DURATION_MODES}
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2=old))
        results = [_res("unit", 15.2), _res("regression", 17.4), _res("verify", 10.2)]
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, results)
        assert "| `unit` | ~15s | ~30s |" in updated
        assert "| `standard` | 旧standard | ~30s |" in updated
        assert "| `all` | 旧all | ~30s |" in updated
        assert "| `verify,regression` | ~28s（verify+regression 顺序之和） | ~30s |" in updated

    def test_duration_mode_cells_skips_timeout_and_unknown(self, runner_script):
        results = [_res("unit", 15.2), _res("edge", 300.0, timed_out=True), _res("live", 5.0)]
        cells = runner_script._duration_mode_cells(results)
        assert "unit" in cells
        assert "edge" not in cells
        assert "live" not in cells
        assert "verify,regression" not in cells
        # 无 verify 时组合行缺席
        cells2 = runner_script._duration_mode_cells([_res("unit", 15.2)])
        assert "verify,regression" not in cells2


# ── 模式对应测试量表 ────────────────────────────────────────


class TestModeCountTableUpdate:
    """模式对应测试量表：实测执行计数+耗时回填、未实测/超时保留、marker 缺失报错。"""

    def test_count_update_existing_rows_with_counts_and_durations(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        results = [
            _res("unit", 15.2, passed=4672, skipped=3),
            _res("all", 21.4, passed=5530),
            _res("edge", 300.0, timed_out=True),
        ]
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, results)
        # 覆盖项数=passed+failed+skipped+errors，耗时=实测约值
        assert "| `unit` | **4675** | ~15s |" in updated
        assert "| `all` | **5530** | ~21s |" in updated
        # 未实测模式保留原值
        assert "| `standard` | 旧值 | ~30s |" in updated
        # 超时模式保留原值（不计入覆盖项数）
        assert "| `edge` | 旧值 | ~30s |" in updated

    def test_count_update_partial_results_preserve_others(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        results = [_res("unit", 15.2, passed=4672)]
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, results)
        assert "| `unit` | **4672** | ~15s |" in updated
        assert "| `scenario` | 旧值 | ~30s |" in updated
        assert "| `all` | 旧值 | ~30s |" in updated

    def test_count_table_missing_marker_raises(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        doc = doc.replace("<!-- mode-count-table:start -->", "")
        with pytest.raises(ValueError):
            runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [_res("unit", 15.2)])


# ── 标记定位与区域替换 ──────────────────────────────────────


class TestTableRegion:
    """标记定位：缺失抛 ValueError、round-trip 幂等、区外文本不变。"""

    def test_missing_start_marker_raises(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"), with_markers=False)
        with pytest.raises(ValueError):
            runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])

    def test_missing_end_marker_raises(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        doc = doc.replace("<!-- env-table:end -->", "")
        with pytest.raises(ValueError):
            runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])

    def test_roundtrip_idempotent(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        results = [_res("unit", 15.2), _res("verify", 10.2), _res("regression", 17.4)]
        first = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, results)
        second = runner_script._update_test_coverage_doc(first, _MACHINE_INFO, results)
        assert second == first

    def test_preserves_surrounding_text_byte_for_byte(self, runner_script):
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        # 首个标记之前与末个标记之后的文本逐字节不变；标记区间的章节标题保留
        prefix = doc.split("<!-- mode-count-table:start -->")[0]
        suffix = doc.split("<!-- duration-table:end -->")[1]
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [_res("unit", 15.2)])
        assert updated.startswith(prefix)
        assert updated.endswith(suffix)
        assert "## 尾部内容" in updated and updated.rstrip().endswith("end")
        assert "### 环境耗时对照" in updated
        assert "#### 采集环境属性" in updated
        assert "#### 各模式耗时对照" in updated

    def test_prose_line_inside_region_raises(self, runner_script):
        # 标记间夹入非表格行（人工维护失误）→ 结构异常抛 ValueError，不静默破坏
        env_lines = _env_table(col2="旧值")
        env_lines.insert(3, "> 注：勿在标记内夹注说明文字")
        doc = _sample_doc(env_lines, _duration_table(col2="旧值"))
        with pytest.raises(ValueError):
            runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])

    def test_missing_separator_row_raises(self, runner_script):
        # 表缺分隔行 → 结构异常抛 ValueError（防止数据行被误当分隔行改写）
        env_lines = _env_table(col2="旧值")
        env_lines.pop(1)  # 删除分隔行
        doc = _sample_doc(env_lines, _duration_table(col2="旧值"))
        with pytest.raises(ValueError):
            runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])

    def test_backslash_in_unchanged_cell_no_crash(self, runner_script):
        # 未改动列含反斜杠（如历史路径）：替换块不得被 re 当模板解析（曾触发 re.error）
        env_lines = _env_table(col2="旧值", col3=r"C:\temp\logs")
        doc = _sample_doc(env_lines, _duration_table(col2="旧值", col3=r"C:\temp\logs"))
        updated = runner_script._update_test_coverage_doc(doc, _MACHINE_INFO, [])
        assert r"C:\temp\logs" in updated
        assert "| 操作系统 | Linux | C:\\temp\\logs |" in updated


# ── IO 封装与参数隐含 ───────────────────────────────────────


class TestDocFileAndArgs:
    """文件写盘仅内容变化时触发；--update-docs 隐含 --machine-info。"""

    def test_update_doc_file_writes_only_when_changed(self, runner_script, monkeypatch, tmp_path):
        target = tmp_path / "test-coverage.md"
        monkeypatch.setattr(runner_script, "_DOC_COVERAGE_PATH", str(target))
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        target.write_text(doc, encoding="utf-8")
        runner_script._update_test_coverage_doc_file(_MACHINE_INFO, [_res("unit", 15.2)])
        first = target.read_text(encoding="utf-8")
        assert first != doc  # 已更新
        # 相同输入再跑 → 内容不再变化（幂等，不重复写盘）
        runner_script._update_test_coverage_doc_file(_MACHINE_INFO, [_res("unit", 15.2)])
        assert target.read_text(encoding="utf-8") == first

    def test_update_doc_file_non_valueerror_degrades_to_err(self, runner_script, monkeypatch, tmp_path):
        # 写入器抛出非 ValueError 异常（防御性）：同样降级 [ERR] 且不落盘
        target = tmp_path / "test-coverage.md"
        monkeypatch.setattr(runner_script, "_DOC_COVERAGE_PATH", str(target))
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"))
        target.write_text(doc, encoding="utf-8")

        def boom(_doc, _info, _res):
            raise RuntimeError("simulated unexpected error")

        monkeypatch.setattr(runner_script, "_update_test_coverage_doc", boom)
        runner_script._update_test_coverage_doc_file(_MACHINE_INFO, [_res("unit", 15.2)])
        assert target.read_text(encoding="utf-8") == doc  # 未落盘

    def test_update_doc_file_missing_markers_no_write(self, runner_script, monkeypatch, tmp_path):
        target = tmp_path / "test-coverage.md"
        monkeypatch.setattr(runner_script, "_DOC_COVERAGE_PATH", str(target))
        doc = _sample_doc(_env_table(col2="旧值"), _duration_table(col2="旧值"), with_markers=False)
        target.write_text(doc, encoding="utf-8")
        runner_script._update_test_coverage_doc_file(_MACHINE_INFO, [_res("unit", 15.2)])
        assert target.read_text(encoding="utf-8") == doc  # 未落盘

    def test_parse_args_update_docs_implies_machine_info(self, runner_script, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["test_runner.py", "--mode", "bench", "--update-docs"])
        args = runner_script.parse_args()
        assert args.update_docs is True
        assert args.machine_info is True

    def test_parse_args_default_no_update(self, runner_script, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["test_runner.py", "--mode", "unit"])
        args = runner_script.parse_args()
        assert args.update_docs is False
        assert args.machine_info is False

    def test_display_path_cross_drive_fallback(self, runner_script):
        # rf-232 回归：Windows 跨盘符 relpath 抛 ValueError → 降级返回绝对路径
        # 不崩溃；POSIX 无盘符概念，正常返回相对路径（断言平台无关）。
        start = runner_script._PROJECT_ROOT
        if os.name == "nt":
            drive = os.path.splitdrive(start)[0]
            other = "C:" if drive.upper() != "C:" else "D:"
            target = os.path.join(other + os.sep, "unittest", "test-coverage.md")
            shown = runner_script._display_path(target, start)
            assert os.path.isabs(shown)
            assert shown == os.path.abspath(target)
        else:
            target = "/unittest/test-coverage.md"
            assert runner_script._display_path(target, start) == os.path.relpath(target, start)
