#!/usr/bin/env python3
"""测试驱动脚本 — 统一运行 pytest 并输出结构化 HTML 报告。

用法:
  python scripts/test_runner.py                          # 全量测试
  python scripts/test_runner.py --mode unit              # 仅单元测试
  python scripts/test_runner.py --mode edge              # 仅边缘测试
  python scripts/test_runner.py --mode scenario,edge     # 多模式组合
  python scripts/test_runner.py --coverage               # 全量 + 覆盖率报告
  python scripts/test_runner.py --help                   # 本帮助
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time as _time
from datetime import datetime


# ── 路径常量 ─────────────────────────────────────────────────

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORTS_DIR = os.path.join(_PROJECT_ROOT, "test-reports")
_LATEST_DIR = os.path.join(_REPORTS_DIR, "latest")
_ARCHIVES_DIR = os.path.join(_REPORTS_DIR, "archives")
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src", "test")

# ── 模式配置 ─────────────────────────────────────────────────

MODES: dict[str, dict] = {
    "unit": {
        "marker": "unit",
        "desc": "全量单元测试（含 edge/data，1993+ 项）",
        "timeout_sec": 720,
        "order": 1,
        "parallel": True,
    },
    "standard": {
        "marker": "unit and not (edge or data)",
        "desc": "常规单元测试（排除 edge/data 标记，1730 项）",
        "timeout_sec": 720,
        "order": 2,
        "parallel": True,
    },
    "scenario": {
        "marker": "scenario",
        "desc": "业务场景集成测试（S1-S28 + T1-T21，222 项）",
        "timeout_sec": 300,
        "order": 3,
        "parallel": False,
    },
    "regression": {
        "marker": "scenario",
        "desc": "回归测试（场景 222 项，~30s 提交前极速验证）",
        "timeout_sec": 120,
        "order": 4,
        "parallel": False,
    },
    "verify": {
        "marker": "scenario or unit_core or unit_providers or unit_fetcher",
        "desc": "合入验证（场景+核心模块 824 项，~12min）",
        "timeout_sec": 360,
        "order": 5,
        "parallel": True,
    },
    "integration": {
        "marker": "scenario or integration",
        "desc": "集成测试（场景+模块契约/缓存/TUI 路由 232 项）",
        "timeout_sec": 300,
        "order": 6,
        "parallel": True,
    },
    "edge": {
        "marker": "edge",
        "desc": "边缘/异常场景测试（198 项）",
        "timeout_sec": 300,
        "order": 7,
        "parallel": False,
    },
    "data": {
        "marker": "data",
        "desc": "数据正确性验证测试（65 项）",
        "timeout_sec": 60,
        "order": 8,
        "parallel": False,
    },
    "all": {
        "marker": "",
        "desc": "全量测试（2353 项）",
        "timeout_sec": 720,
        "order": 9,
        "parallel": True,
    },
    "smoke": {
        "marker": "smoke",
        "desc": "冒烟测试（24 项，~2s 快速验证核心通路）",
        "timeout_sec": 30,
        "order": 10,
        "parallel": False,
    },
    "report": {
        "marker": "unit_report",
        "desc": "仅报告模块测试（675 项，开发期快速验证报告变更）",
        "timeout_sec": 120,
        "order": 11,
        "parallel": True,
    },
}

# ── 帮助文本 ─────────────────────────────────────────────────

_HELP_TEXT = f"""测试驱动脚本 — 统一运行 pytest 并输出结构化 HTML 报告。

用法:
  python scripts/test_runner.py                          # 全量测试
  python scripts/test_runner.py --mode unit              # 仅单元测试
  python scripts/test_runner.py --mode edge              # 仅边缘测试
  python scripts/test_runner.py --mode scenario,edge     # 多模式组合
  python scripts/test_runner.py --coverage               # 全量 + 覆盖率报告
  python scripts/test_runner.py --help                   # 本帮助

模式说明:
"""

for _mode_key, _mode_val in sorted(MODES.items(), key=lambda x: x[1]["order"]):
    _HELP_TEXT += f"  {_mode_key:<15s} {_mode_val['desc']}\n"

_HELP_TEXT += """\
选项:
  --mode M[,M...]   运行指定模式（逗号分隔，默认: all）
  --coverage        同时生成 HTML 行覆盖率报告（pytest-cov）
  --parallel [LVL]  并行级别: high(100%%核数) / medium(50%%,默认) / low(25%%)
  --help            显示本帮助信息

输出目录结构:
  test-reports/latest/
    ├── index.html            汇总页
    ├── unit/report.html      单元测试报告
    ├── scenario/report.html  场景测试报告
    └── ...
  历史报告自动归档至:
  test-reports/archives/<YYYYMMDD>/<HHMMSS>/
"""


# ── 参数解析 ─────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", default="all",
                        help="运行模式 (unit/scenario/integration/regression/edge/all)，逗号分隔")
    parser.add_argument("--coverage", action="store_true",
                        help="同时生成 HTML 行覆盖率报告")
    parser.add_argument("--parallel", nargs="?", const="medium", default=None,
                        choices=["high", "medium", "low"],
                        help="并行级别（high=100%核数, medium=50%核数, low=25%核数，缺省 medium）")
    parser.add_argument("--help", action="store_true", help="显示帮助")
    return parser.parse_args()


# ── 目录管理 ─────────────────────────────────────────────────


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


# ── pytest 执行 ─────────────────────────────────────────────


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
    result: dict = {"passed": 0, "failed": 0, "skipped": 0,
                    "errors": 0, "subtests": 0, "duration": 0.0}

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


def _build_pytest_args(mode_cfg: dict, mode_key: str,
                       html_available: bool, coverage: bool,
                       parallel_level: str | None = None) -> list[str]:
    """构建 pytest 命令参数列表。"""
    args = [
        sys.executable, "-m", "pytest",
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
        print(f"      [!] pytest-xdist 未安装，降级单线程执行")

    if html_available:
        report_path = os.path.join(_LATEST_DIR, mode_key, "report.html")
        args.extend(["--html", report_path, "--self-contained-html"])

    if coverage:
        if _check_pytest_cov():
            cov_report_dir = os.path.join(_LATEST_DIR, "coverage")
            args.extend([
                "--cov=" + os.path.join(_PROJECT_ROOT, "src", "python"),
                "--cov-report=html:" + cov_report_dir,
                "--cov-report=term-missing:skip-covered",
            ])
        else:
            print(f"  [!] pytest-cov 未安装，跳过覆盖率收集")

    return args


def run_mode(mode_key: str, coverage: bool = False,
             parallel_level: str | None = None) -> dict:
    """运行指定模式的测试。

    Args:
        mode_key: 模式名
        coverage: 是否启用覆盖率

    Returns:
        包含测试结果统计的字典
    """
    mode_cfg = MODES.get(mode_key, {})
    html_available = _check_pytest_html()

    print(f"\n  {'=' * 54}")
    print(f"  [..] 正在运行 [{mode_key}] — {mode_cfg.get('desc', '')}")
    if not html_available:
        print(f"  [!] pytest-html 未安装，将使用默认文本输出")
    print()

    pytest_args = _build_pytest_args(mode_cfg, mode_key, html_available, coverage, parallel_level)
    timeout = mode_cfg.get("timeout_sec", 300)

    start = _time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            pytest_args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        print(f"  [ERR] {mode_key} 测试超时（{timeout}s）")
        timed_out = True
        elapsed = timeout
        stats: dict = {
            "mode": mode_key,
            "desc": mode_cfg.get("desc", ""),
            "passed": 0, "failed": 0, "skipped": 0,
            "errors": 0, "subtests": 0,
            "duration": float(timeout),
            "exit_code": -1,
        }
        stats["timed_out"] = True
        return stats
    else:
        elapsed = _time.time() - start

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
        if any(kw in stripped for kw in ("passed", "failed", "error",
                                         "warning", "===", "short test summary")):
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


# ── 汇总页生成 ─────────────────────────────────────────────


def _overall_status(results: list[dict]) -> tuple[str, str]:
    """判断总体状态。"""
    all_ok = all(r.get("exit_code", 0) == 0 for r in results)
    if all_ok:
        return "PASS", "全部通过"
    ok_count = sum(1 for r in results if r.get("exit_code", 0) == 0)
    return "PARTIAL", f"{ok_count}/{len(results)} 模式通过"


def _render_index_html(results: list[dict], coverage: bool,
                       archive_path: str | None) -> str:
    """生成汇总页 HTML。"""
    total_passed = sum(r.get("passed", 0) for r in results)
    total_failed = sum(r.get("failed", 0) for r in results)
    total_skipped = sum(r.get("skipped", 0) for r in results)
    total_errors = sum(r.get("errors", 0) for r in results)
    total_duration = sum(r.get("duration", 0) for r in results)
    overall, status_desc = _overall_status(results)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 各行
    rows_html = ""
    mode_order = {k: v["order"] for k, v in MODES.items()}
    for r in sorted(results, key=lambda x: mode_order.get(x.get("mode", ""), 99)):
        mode = r.get("mode", "")
        ec = r.get("exit_code", -1)
        if ec == 0:
            badge = '<span class="badge badge-pass">PASS</span>'
        elif ec == -1:
            badge = '<span class="badge badge-timeout">超时</span>'
        else:
            badge = f'<span class="badge badge-fail">FAIL ({ec})</span>'

        report_html = os.path.join(_LATEST_DIR, mode, "report.html")
        if os.path.isfile(report_html):
            report_link = f'<a href="{mode}/report.html">📄 查看</a>'
        else:
            report_link = '<span class="dim">无</span>'

        rows_html += f"""\
    <tr>
      <td><strong>{mode}</strong></td>
      <td>{r.get("desc", "")}</td>
      <td>{badge}</td>
      <td class="num">{r.get("passed", 0)}</td>
      <td class="num">{r.get("failed", 0)}</td>
      <td class="num">{r.get("skipped", 0)}</td>
      <td class="num">{r.get("errors", 0)}</td>
      <td class="num">{r.get("duration", 0):.1f}s</td>
      <td>{report_link}</td>
    </tr>"""

    overall_badge = f'<span class="badge badge-{overall.lower()}">{overall}</span>'

    # 存档备注
    archive_note = ""
    if archive_path:
        rel_archive = os.path.relpath(archive_path, _REPORTS_DIR)
        archive_note = (
            f'<div class="note archive-note">'
            f'📦 历史报告已归档: <code>{rel_archive}/</code>'
            f'</div>')

    # 覆盖率备注
    cov_note = ""
    if coverage:
        cov_index = os.path.join(_LATEST_DIR, "coverage", "index.html")
        if os.path.isfile(cov_index):
            cov_note = (
                f'<div class="note cov-note">'
                f'📊 <a href="coverage/index.html">查看行覆盖率报告</a>'
                f'</div>')

    html = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>测试报告汇总 — {now_str}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Microsoft YaHei', 'PingFang SC', sans-serif; margin: 0; padding: 24px; background: #f0f2f5; color: #1a1a2e; }}
  h1 {{ font-size: 1.4em; margin: 0 0 4px; }}
  .meta {{ color: #666; font-size: 0.88em; margin-bottom: 20px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; font-size: 0.92em; }}
  th {{ background: #f7f8fa; font-weight: 600; color: #444; }}
  tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 0.82em; font-weight: 600; }}
  .badge-pass {{ background: #d4edda; color: #155724; }}
  .badge-fail {{ background: #f8d7da; color: #721c24; }}
  .badge-partial {{ background: #fff3cd; color: #856404; }}
  .badge-timeout {{ background: #e2e3e5; color: #383d41; }}
  .summary {{ margin-top: 20px; padding: 16px 20px; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-top: 10px; }}
  .summary-item {{ text-align: center; padding: 8px; border-radius: 6px; background: #f8f9fa; }}
  .summary-item .num {{ font-size: 1.3em; font-weight: 700; display: block; }}
  .summary-item .lbl {{ font-size: 0.82em; color: #666; }}
  .note {{ margin-top: 12px; padding: 10px 16px; border-radius: 6px; font-size: 0.9em; }}
  .archive-note {{ background: #e8f4f8; color: #0c5460; }}
  .cov-note {{ background: #e8f4e8; color: #155724; }}
  .dim {{ color: #999; }}
  .footer {{ margin-top: 24px; color: #aaa; font-size: 0.82em; text-align: center; }}
  a {{ color: #0066cc; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>🧪 测试报告汇总</h1>
<p class="meta">生成时间: {now_str} &nbsp;|&nbsp; 总体: {overall_badge} &nbsp;|&nbsp; {status_desc}</p>

<table>
  <thead>
    <tr>
      <th>模式</th>
      <th>说明</th>
      <th>状态</th>
      <th class="num">通过</th>
      <th class="num">失败</th>
      <th class="num">跳过</th>
      <th class="num">错误</th>
      <th class="num">耗时</th>
      <th>报告</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>

<div class="summary">
  <strong>📋 总计</strong>
  <div class="summary-grid">
    <div class="summary-item"><span class="num" style="color:#155724;">{total_passed}</span><span class="lbl">通过</span></div>
    <div class="summary-item"><span class="num" style="color:#721c24;">{total_failed}</span><span class="lbl">失败</span></div>
    <div class="summary-item"><span class="num" style="color:#856404;">{total_skipped}</span><span class="lbl">跳过</span></div>
    <div class="summary-item"><span class="num" style="color:#721c24;">{total_errors}</span><span class="lbl">错误</span></div>
    <div class="summary-item"><span class="num">{total_duration:.1f}s</span><span class="lbl">总耗时</span></div>
  </div>
</div>

{cov_note}
{archive_note}

<div class="footer">
  Generated by test_runner.py · 个人投资分析报告生成小助手
</div>
</body>
</html>"""
    return html


# ── 主入口 ────────────────────────────────────────────────────


def main() -> None:
    """主入口：归档 → 执行 → 汇总。"""
    args = parse_args()

    if args.help:
        print(_HELP_TEXT)
        return

    # 解析模式列表
    modes_to_run = [m.strip() for m in args.mode.split(",")]
    invalid = [m for m in modes_to_run if m not in MODES]
    if invalid:
        print(f"  [ERR] 无效模式: {', '.join(invalid)}")
        print(f"       有效模式: {', '.join(MODES.keys())}")
        sys.exit(1)

    print(f"  [..] 测试报告系统 v1.0")
    print(f"  [..] 计划运行模式: {', '.join(modes_to_run)}")
    if args.coverage:
        print(f"  [..] 覆盖率报告: 已开启")

    # 归档现有报告
    archive_path = archive_existing()

    # 创建目录结构
    _create_latest_structure(modes_to_run)

    # 运行各模式
    results: list[dict] = []
    for mode_key in modes_to_run:
        result = run_mode(mode_key, coverage=args.coverage,
                          parallel_level=args.parallel)
        results.append(result)

    # 生成汇总页
    index_html = _render_index_html(results, args.coverage, archive_path)
    index_path = os.path.join(_LATEST_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"\n  [OK] 汇总页已生成: test-reports/latest/index.html")

    # 总体结果
    exit_codes = [r.get("exit_code", -1) for r in results]
    overall = 0 if all(ec == 0 for ec in exit_codes) else max(exit_codes)
    total_failed = sum(r.get("failed", 0) for r in results)
    total_passed = sum(r.get("passed", 0) for r in results)

    print()
    print(f"  {'=' * 54}")
    if overall == 0:
        print(f"  [OK] 全部完成 — {total_passed} 通过, {total_failed} 失败"
              f"  (总耗时 {sum(r.get('duration', 0) for r in results):.1f}s)")
    else:
        print(f"  [ERR] 存在失败的测试 — {total_passed} 通过, {total_failed} 失败")
        print(f"        请检查 test-reports/latest/ 中的详细报告")
    print()

    sys.exit(overall)


if __name__ == "__main__":
    main()
