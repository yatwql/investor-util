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

# Windows GBK 控制台兜底：子进程捕获输出经 errors="replace" 处理后可能含 U+FFFD
# 替换字符，直接 print 会触发 UnicodeEncodeError 使 runner 中途崩溃（丢 Phase B）
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

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
        "desc": "全量单元测试（含 edge/data）",
        "timeout_sec": 720,
        "order": 1,
        "parallel": True,
    },
    "standard": {
        "marker": "unit and not (edge or data)",
        "desc": "常规单元测试（排除 edge/data 标记）",
        "timeout_sec": 720,
        "order": 2,
        "parallel": True,
    },
    "scenario": {
        "marker": "scenario",
        "desc": "业务场景集成测试（S0-S33 + T1-T21）",
        "timeout_sec": 600,
        "order": 3,
        "parallel": False,
    },
    "regression": {
        "marker": "scenario",
        "desc": "回归测试（场景模式，提交前快速验证）",
        "timeout_sec": 1200,
        "order": 4,
        "parallel": False,
    },
    "dev-verify": {
        "desc": "开发期快速验证（core/providers/fetcher/analysis 单元 + 基础场景，~2.5min）",
        "order": 5,
        "preflight": [[sys.executable, "scripts/check-task-numbering.py", "--ci"]],
        "phases": [
            {
                "marker": "(unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts) and not (edge or data)",
                "desc": "核心模块单元测试",
                "timeout_sec": 120,
                "parallel": True,
            },
            {"marker": "scenario_basic", "desc": "基础业务场景（145 项，~100s）", "timeout_sec": 300, "parallel": True},
        ],
    },
    "verify": {
        "marker": "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts",
        "desc": "合入验证（核心/配置/新闻/LLM 模块单元测试，不含场景——场景由 P0+P2 覆盖）",
        "timeout_sec": 300,
        "order": 6,
        "parallel": True,
    },
    "integration": {
        "marker": "scenario or integration",
        "desc": "集成测试（场景+模块契约/缓存/TUI 路由）",
        "timeout_sec": 600,
        "order": 7,
        "parallel": True,
    },
    "edge": {
        "marker": "edge",
        "desc": "边缘/异常场景测试",
        "timeout_sec": 600,
        "order": 8,
        "parallel": False,
    },
    "data": {
        "marker": "data",
        "desc": "数据正确性验证测试",
        "timeout_sec": 120,
        "order": 9,
        "parallel": False,
    },
    "all": {
        "marker": "",
        "desc": "全量测试",
        "timeout_sec": 1200,
        "order": 10,
        "parallel": True,
    },
    "all_no_unit": {
        "marker": "not unit",
        "desc": "全量测试（排除单元测试）",
        "timeout_sec": 1200,
        "order": 10,
        "parallel": True,
    },
    "smoke": {
        "marker": "smoke",
        "desc": "冒烟测试（24 项，~15s 快速验证核心通路）",
        "timeout_sec": 60,
        "order": 11,
        "parallel": False,
    },
    "report": {
        "marker": "unit_report",
        "desc": "仅报告模块测试（开发期快速验证报告变更）",
        "timeout_sec": 300,
        "order": 12,
        "parallel": True,
    },
    "scenario_extreme": {
        "marker": "scenario_extreme",
        "desc": "极限场景测试（S0c 超多持仓 + S10 极端值，~1min，手工触发）",
        "timeout_sec": 600,
        "order": 13,
        "parallel": False,
    },
}

# ── 帮助文本 ─────────────────────────────────────────────────

_HELP_TEXT = """测试驱动脚本 — 统一运行 pytest 并输出结构化 HTML 报告。

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
  --timeout SEC     覆盖超时时间（秒），所有模式统一使用此值
  --no-timeout      禁用超时，等待测试自然结束
  --phased          分阶段运行（对配置了 phases 的模式有效，前序失败跳过后续阶段）
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
    parser.add_argument(
        "--mode", default="all", help="运行模式 (unit/scenario/integration/regression/edge/all)，逗号分隔"
    )
    parser.add_argument("--coverage", action="store_true", help="同时生成 HTML 行覆盖率报告")
    parser.add_argument(
        "--parallel",
        nargs="?",
        const="medium",
        default=None,
        choices=["high", "medium", "low"],
        help="并行级别（high=100%核数, medium=50%核数, low=25%核数，缺省 medium）",
    )
    parser.add_argument(
        "--timeout", type=int, default=None, metavar="SEC", help="覆盖各模式的超时设置（秒），所有模式统一使用此值"
    )
    parser.add_argument("--no-timeout", action="store_true", help="禁用超时，等待测试自然结束")
    parser.add_argument(
        "--phased", action="store_true", help="分阶段运行（仅对支持分阶段的模式有效，前序失败则跳过后续）"
    )
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


def _build_pytest_args(
    mode_cfg: dict, mode_key: str, html_available: bool, coverage: bool, parallel_level: str | None = None
) -> list[str]:
    """构建 pytest 命令参数列表。"""
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
        report_path = os.path.join(_LATEST_DIR, mode_key, "report.html")
        args.extend(["--html", report_path, "--self-contained-html"])

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

    start = _time.time()
    timed_out = False
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
        timed_out = True
        elapsed = timeout
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


# ── 汇总页生成 ─────────────────────────────────────────────


def _overall_status(results: list[dict]) -> tuple[str, str]:
    """判断总体状态。"""
    all_ok = all(r.get("exit_code", 0) == 0 for r in results)
    if all_ok:
        return "PASS", "全部通过"
    ok_count = sum(1 for r in results if r.get("exit_code", 0) == 0)
    return "PARTIAL", f"{ok_count}/{len(results)} 模式通过"


def _render_index_html(results: list[dict], coverage: bool, archive_path: str | None) -> str:
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
        archive_note = f'<div class="note archive-note">📦 历史报告已归档: <code>{rel_archive}/</code></div>'

    # 覆盖率备注
    cov_note = ""
    if coverage:
        cov_index = os.path.join(_LATEST_DIR, "coverage", "index.html")
        if os.path.isfile(cov_index):
            cov_note = '<div class="note cov-note">📊 <a href="coverage/index.html">查看行覆盖率报告</a></div>'

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


# ── 分阶段执行 ──────────────────────────────────────────────


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
        pytest_args = _build_pytest_args(phase_cfg, mode_key, html_available, coverage, parallel_level)

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

    print("  [..] 测试报告系统 v1.0")
    print(f"  [..] 计划运行模式: {', '.join(modes_to_run)}")
    if args.coverage:
        print("  [..] 覆盖率报告: 已开启")
    if args.no_timeout:
        print("  [!] 超时: 已禁用（测试可能长时间运行）")
    elif args.timeout:
        print(f"  [..] 超时: 统一设为 {args.timeout}s")
    if args.phased:
        print("  [..] 分阶段: 已开启（前序阶段失败则跳过后续）")

    # 归档现有报告
    archive_path = archive_existing()

    # 创建目录结构
    _create_latest_structure(modes_to_run)

    # 运行各模式
    results: list[dict] = []
    for mode_key in modes_to_run:
        result = run_mode(
            mode_key,
            coverage=args.coverage,
            parallel_level=args.parallel,
            timeout_override=args.timeout,
            no_timeout=args.no_timeout,
            phased=args.phased,
        )
        results.append(result)

    # 生成汇总页
    index_html = _render_index_html(results, args.coverage, archive_path)
    index_path = os.path.join(_LATEST_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)

    print("\n  [OK] 汇总页已生成: test-reports/latest/index.html")

    # 总体结果
    exit_codes = [r.get("exit_code", -1) for r in results]
    any_timeout = any(r.get("timed_out", False) for r in results)
    if any_timeout:
        overall = 124  # 超时退出码（标准 timeout exit code）
    else:
        overall = 0 if all(ec == 0 for ec in exit_codes) else max(exit_codes)
    total_failed = sum(r.get("failed", 0) for r in results)
    total_passed = sum(r.get("passed", 0) for r in results)

    print()
    print(f"  {'=' * 54}")
    if overall == 0:
        print(
            f"  [OK] 全部完成 — {total_passed} 通过, {total_failed} 失败"
            f"  (总耗时 {sum(r.get('duration', 0) for r in results):.1f}s)"
        )
    else:
        print(f"  [ERR] 存在失败的测试 — {total_passed} 通过, {total_failed} 失败")
        print("        请检查 test-reports/latest/ 中的详细报告")
    print()

    sys.exit(overall)


if __name__ == "__main__":
    main()
