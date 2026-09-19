"""pytest 环境探测与命令构建（插件检查 / xdist worker 数 / 参数拼装 / 结果解析）。"""

from __future__ import annotations

import os
import re
import sys

from _test_runner.paths import _LATEST_DIR, _PROJECT_ROOT, _SRC_DIR


def _check_pytest_html() -> bool:
    """检查 pytest-html 是否已安装。"""
    try:
        import pytest_html  # noqa: F401

        return True
    except ImportError:
        return False


def _check_pytest_cov() -> bool:
    """检查 pytest-cov 是否已安装。"""
    try:
        import pytest_cov  # noqa: F401

        return True
    except ImportError:
        return False


def _extract_count(text: str, pattern: str) -> int:
    """从文本中提取匹配的数字，未匹配返回 0。"""
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def _parse_pytest_output(output: str) -> dict:
    """从 pytest 输出中解析测试计数。

    Returns:
        {passed, failed, skipped, errors, subtests, duration}
    """
    result: dict = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "subtests": 0, "duration": 0.0}

    lines = output.strip().splitlines()
    summary_line = ""
    for line in reversed(lines):
        cleaned = line.strip()
        if cleaned and ("passed" in cleaned or "failed" in cleaned):
            summary_line = cleaned
            break

    if not summary_line:
        return result

    result["passed"] = _extract_count(summary_line, r"(\d+)\s+passed")
    result["failed"] = _extract_count(summary_line, r"(\d+)\s+failed")
    result["skipped"] = _extract_count(summary_line, r"(\d+)\s+skipped")
    result["errors"] = _extract_count(summary_line, r"(\d+)\s+error")
    result["subtests"] = _extract_count(summary_line, r"(\d+)\s+subtests passed")

    dur_match = re.search(r"in\s+([\d.]+)s", summary_line)
    if dur_match:
        result["duration"] = float(dur_match.group(1))

    return result


def _check_xdist() -> bool:
    """检查 pytest-xdist 是否已安装。"""
    try:
        import xdist  # noqa: F401

        return True
    except ImportError:
        return False


_PARALLEL_FACTOR: dict[str, float] = {
    "high": 1.0,
    "medium": 0.5,
    "low": 0.25,
}


def _calc_parallel_workers(level: str | bool) -> str:
    """根据并行级别计算 worker 数。

    Args:
        level: "high"（100% 核数）/ "medium"（50%，默认）/ "low"（25%，最小 2）
               或 True（等价 medium）

    Returns:
        "-n" 参数的字符串值，如 "8"、"4"、"2"
    """
    if level is True:
        level = "medium"
    factor = _PARALLEL_FACTOR.get(level, 0.5)
    n_cores = os.cpu_count() or 4
    workers = max(1, int(n_cores * factor))
    if level == "low":
        workers = max(2, workers)
    return str(workers)


def _phase_report_path(mode_key: str, phase_tag: str = "") -> str:
    """该模式的 pytest-html 报告路径。

    分阶段模式（dev-verify = Phase A 核心单元 + Phase B 基础场景）**每阶段一个文件**：
    两阶段共用 ``report.html`` 会让后跑的阶段覆盖前者，详细报告只剩最后一阶段
    （实测只剩 152 个场景用例、Phase A 的 2700+ 用例全丢），排查时看不到真正的失败面。
    """
    name = f"report_phase_{phase_tag}.html" if phase_tag else "report.html"
    return os.path.join(_LATEST_DIR, mode_key, name)


def _build_pytest_args(
    mode_cfg: dict,
    mode_key: str,
    html_available: bool,
    coverage: bool,
    parallel_level: str | None = None,
    phase_tag: str = "",
) -> list[str]:
    """构建 pytest 命令参数列表（``phase_tag`` 非空时报告文件名带阶段后缀）。"""
    args = [
        sys.executable,
        "-m",
        "pytest",
        _SRC_DIR,
        "-q",
        "--tb=short",
    ]

    marker = mode_cfg["marker"]
    if marker:
        args.extend(["-m", marker])

    # ── 并行执行 ──
    parallel_enabled = mode_cfg.get("parallel", False)
    if parallel_enabled and _check_xdist():
        level = parallel_level or "medium"
        workers = _calc_parallel_workers(level)
        args.extend(["-n", workers])
        print(f"      [..] 并行 worker={workers}（级别: {level}）")
    elif parallel_enabled:
        print("      [!] pytest-xdist 未安装，降级单线程执行")

    if html_available:
        args.extend(["--html", _phase_report_path(mode_key, phase_tag), "--self-contained-html"])

    if coverage:
        if _check_pytest_cov():
            cov_report_dir = os.path.join(_LATEST_DIR, "coverage")
            args.extend(
                [
                    "--cov=" + os.path.join(_PROJECT_ROOT, "src", "python"),
                    "--cov-report=html:" + cov_report_dir,
                    "--cov-report=term-missing:skip-covered",
                ]
            )
        else:
            print("  [!] pytest-cov 未安装，跳过覆盖率收集")

    return args
