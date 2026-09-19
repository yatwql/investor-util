"""运行编排（目录准备与归档 / 单模式执行 / 分阶段执行）。"""

from __future__ import annotations

import os
import shutil
import subprocess

from _test_runner.paths import _ARCHIVES_DIR, _LATEST_DIR, _PROJECT_ROOT, _REPORTS_DIR
from _test_runner.modes import MODES
from _test_runner.pytest_env import _build_pytest_args, _check_pytest_html, _parse_pytest_output
import time as _time
from datetime import datetime


def _ensure_dirs(path: str) -> None:
    """确保目录存在。"""
    os.makedirs(path, exist_ok=True)


def _create_latest_structure(modes_to_run: list[str]) -> None:
    """创建 latest/ 下的子目录结构。"""
    for mode_key in modes_to_run:
        _ensure_dirs(os.path.join(_LATEST_DIR, mode_key))
    _ensure_dirs(os.path.join(_LATEST_DIR, "coverage"))


def archive_existing() -> str | None:
    """将现有的 latest/ 报告归档到 archives/<YYYYMMDD>/<HHMMSS>/。

    Returns:
        存档目标路径（若无现存报告则返回 None）
    """
    if not os.path.isdir(_LATEST_DIR):
        return None
    # 检查 latest/ 下是否有报告文件
    has_reports = False
    for root, _dirs, files in os.walk(_LATEST_DIR):
        if any(f.endswith((".html", ".xml", ".json")) for f in files):
            has_reports = True
            break
    if not has_reports:
        return None

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    archive_dir = os.path.join(_ARCHIVES_DIR, date_str, time_str)
    _ensure_dirs(os.path.dirname(archive_dir))

    shutil.move(_LATEST_DIR, archive_dir)
    rel_path = os.path.relpath(archive_dir, _REPORTS_DIR)
    print(f"  [..] 历史报告已归档: {rel_path}/")
    return archive_dir


def run_mode(
    mode_key: str,
    coverage: bool = False,
    parallel_level: str | None = None,
    timeout_override: int | None = None,
    no_timeout: bool = False,
    phased: bool = False,
) -> dict:
    """运行指定模式的测试。

    Args:
        mode_key: 模式名
        coverage: 是否启用覆盖率
        phased: 启用分阶段运行（模式支持时有效）

    Returns:
        包含测试结果统计的字典
    """
    mode_cfg = MODES.get(mode_key, {})

    # 分阶段模式：若模式定义了 phases 则自动启用分阶段运行
    if "phases" in mode_cfg:
        return _run_phased(mode_cfg["phases"], mode_key, coverage, parallel_level, timeout_override, no_timeout)
    html_available = _check_pytest_html()

    print(f"\n  {'=' * 54}")
    print(f"  [..] 正在运行 [{mode_key}] — {mode_cfg.get('desc', '')}")
    if not html_available:
        print("  [!] pytest-html 未安装，将使用默认文本输出")
    print()

    pytest_args = _build_pytest_args(mode_cfg, mode_key, html_available, coverage, parallel_level)
    timeout = mode_cfg.get("timeout_sec", 300)
    if no_timeout:
        timeout = None
    elif timeout_override is not None:
        timeout = timeout_override

    try:
        # 设置测试环境标识，使子进程（含 xdist worker）正确将日志写入 test.log
        _env = os.environ.copy()
        _env["INVEST_RUNNING_TESTS"] = "1"
        proc = subprocess.run(
            pytest_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=_PROJECT_ROOT,
            env=_env,
        )
    except subprocess.TimeoutExpired:
        print(f"  [ERR] {mode_key} 测试超时（{timeout}s）")
        stats: dict = {
            "mode": mode_key,
            "desc": mode_cfg.get("desc", ""),
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "subtests": 0,
            "duration": float(timeout),
            "exit_code": -1,
        }
        stats["timed_out"] = True
        return stats

    # 合并 stdout + stderr
    output = (proc.stdout or "") + (proc.stderr or "")
    stats = _parse_pytest_output(output)
    stats["mode"] = mode_key
    stats["desc"] = mode_cfg.get("desc", "")
    stats["exit_code"] = proc.returncode
    stats["timed_out"] = False

    # 打印关键摘要行
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(kw in stripped for kw in ("passed", "failed", "error", "warning", "===", "short test summary")):
            print(f"    {stripped}")

    # 结果概览
    ok = proc.returncode == 0
    tag = "OK" if ok else "ERR"
    parts = [f"{stats['passed']} passed", f"{stats['failed']} failed"]
    if stats["skipped"]:
        parts.append(f"{stats['skipped']} skipped")
    if stats["errors"]:
        parts.append(f"{stats['errors']} errors")
    if stats["subtests"]:
        parts.append(f"{stats['subtests']} subtests")
    print(f"\n  [{tag}] {mode_key}: {', '.join(parts)}  ({stats['duration']:.1f}s)")

    return stats


def _run_phased(
    phases: list[dict],
    mode_key: str,
    coverage: bool,
    parallel_level: str | None = None,
    timeout_override: int | None = None,
    no_timeout: bool = False,
) -> dict:
    """分阶段运行测试，前序失败则跳过后续阶段。

    每个阶段调用一次 subprocess.run，支持不同 marker/parallel/timeout。
    """
    mode_cfg = MODES.get(mode_key, {})
    html_available = _check_pytest_html()

    combined: dict = {
        "mode": mode_key,
        "desc": mode_cfg.get("desc", ""),
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "subtests": 0,
        "duration": 0.0,
        "exit_code": 0,
        "timed_out": False,
    }

    # 预检门禁：非 pytest 脚本（如任务编号一致性检查），失败则中止本模式
    for preflight_cmd in mode_cfg.get("preflight", []):
        proc = subprocess.run(
            preflight_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_PROJECT_ROOT,
        )
        if proc.returncode != 0:
            output = (proc.stdout or "") + (proc.stderr or "")
            print(f"    [ERR] 预检失败: {' '.join(preflight_cmd)}")
            for line in output.splitlines():
                print(f"      {line}")
            combined["exit_code"] = proc.returncode
            print(f"\n  [ERR] {mode_key}（分阶段）: 预检未通过，跳过测试阶段")
            return combined

    for i, phase in enumerate(phases):
        tag = chr(65 + i)  # A, B, C, …
        print(f"\n    ── [Phase {tag}]: {phase.get('desc', '')} ──")

        phase_cfg = {
            "marker": phase["marker"],
            "parallel": phase.get("parallel", False),
        }
        pytest_args = _build_pytest_args(phase_cfg, mode_key, html_available, coverage, parallel_level, phase_tag=tag)

        timeout = phase.get("timeout_sec", 300)
        if no_timeout:
            timeout = None
        elif timeout_override is not None:
            timeout = timeout_override

        start = _time.time()
        try:
            _env = os.environ.copy()
            _env["INVEST_RUNNING_TESTS"] = "1"
            proc = subprocess.run(
                pytest_args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=_PROJECT_ROOT,
                env=_env,
            )
        except subprocess.TimeoutExpired:
            print(f"    [ERR] [Phase {tag}] 测试超时（{timeout}s）")
            combined["exit_code"] = -1
            combined["timed_out"] = True
            combined["duration"] += timeout or 0
            break

        elapsed = _time.time() - start
        combined["duration"] += elapsed

        output = (proc.stdout or "") + (proc.stderr or "")
        stats = _parse_pytest_output(output)

        combined["passed"] += stats["passed"]
        combined["failed"] += stats["failed"]
        combined["skipped"] += stats["skipped"]
        combined["errors"] += stats["errors"]
        combined["subtests"] += stats["subtests"]

        # 打印 pytest 摘要行（含 FAILURES 段详情）
        # 注：默认过滤只保留关键词行，会丢弃失败详情（测试名/断言错误）。
        # 失败时（FAILURES 段出现）需完整打印该段，便于定位失败测试。
        in_failures = False
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("====="):
                if "FAILURES" in stripped:
                    in_failures = True
                elif in_failures:
                    in_failures = False
            if in_failures:
                print(f"      {line}")
                continue
            if not stripped:
                continue
            if any(
                kw in stripped for kw in ("passed", "failed", "error", "warning", "===", "short test summary", "ERROR")
            ):
                print(f"      {stripped}")

        # 阶段失败时保存完整输到调试文件（可在 CI artifact 中查看）
        if proc.returncode != 0:
            debug_path = os.path.join(_LATEST_DIR, mode_key, f"phase_{tag}_debug.log")
            try:
                with open(debug_path, "w", encoding="utf-8") as df:
                    df.write(output)
                print(f"      [Phase {tag}] 详细日志已保存: {debug_path}")
            except Exception:
                pass

        ok = proc.returncode == 0
        tag2 = "OK" if ok else "ERR"
        parts = [f"{stats['passed']} passed", f"{stats['failed']} failed"]
        if stats["skipped"]:
            parts.append(f"{stats['skipped']} skipped")
        print(f"    [{tag2}] [Phase {tag}] {', '.join(parts)}  ({elapsed:.1f}s)")

        if not ok:
            combined["exit_code"] = proc.returncode
            # 打印完整 pytest 短摘要（自动包含末尾）
            print(f"    [!] [Phase {tag}] 未通过（exit={proc.returncode}），跳过后续阶段")
            break

    # 汇总一行
    ok = combined["exit_code"] == 0
    tag2 = "OK" if ok else "ERR"
    parts = [f"{combined['passed']} passed", f"{combined['failed']} failed"]
    if combined["skipped"]:
        parts.append(f"{combined['skipped']} skipped")
    print(f"\n  [{tag2}] {mode_key}（分阶段）: {', '.join(parts)}  ({combined['duration']:.1f}s)")

    return combined
