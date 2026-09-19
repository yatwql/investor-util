#!/usr/bin/env python3
"""测试驱动入口 — pytest 模式封装（CLI 解析与编排）。

内部实现按职责拆在 `_test_runner/` 包内（paths / modes / pytest_env / machine_info /
doc_writer / report_html / runner）；本入口保留 CLI 与主流程，并**原面 re-export**
全部内部分符号，使既有测试与调用方无需改动。

用法：
  python scripts/test-runner.py --mode dev-verify      # 开发期快速验证（提交前门禁）
  python scripts/test-runner.py --mode verify          # 核心模块单元测试（合入门禁）
  python scripts/test-runner.py --mode verify,regression  # 单元 + 场景（发布门禁）
  python scripts/test-runner.py --help                 # 查看全部模式与选项
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib / _test_runner）
import os

# Windows GBK 控制台兜底：子进程捕获输出经 errors="replace" 处理后可能含 U+FFFD
# 替换字符，直接 print 会触发 UnicodeEncodeError 使 runner 中途崩溃（丢 Phase B）
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

# 原面 re-export：既有测试按本模块名访问（_checklib 提供）
from _checklib import (  # noqa: F401
    extract_table_region as _extract_table_region,
    replace_table_region as _replace_table_region,
)

# 原面 re-export：测试与调用方按本模块名访问
from _test_runner.paths import (  # noqa: F401
    _PROJECT_ROOT,
    _REPORTS_DIR,
    _LATEST_DIR,
    _ARCHIVES_DIR,
    _SRC_DIR,
)
from _test_runner.modes import (  # noqa: F401
    MODES,
    _BENCH_MODES,
    _MODE_TABLE_ORDER,
    _HELP_TEXT,
    _resolve_modes,
)
from _test_runner.pytest_env import (  # noqa: F401
    _PARALLEL_FACTOR,
    _check_pytest_html,
    _check_pytest_cov,
    _check_xdist,
    _calc_parallel_workers,
    _extract_count,
    _parse_pytest_output,
    _phase_report_path,
    _build_pytest_args,
)
from _test_runner.machine_info import (  # noqa: F401
    _ENV_ATTR_LABELS,
    _read_cpu_model_linux,
    _count_physical_cores_linux,
    _mem_gib_linux,
    _linux_disk_info,
    _sysctl_value,
    _mem_gib_windows,
    _collect_machine_info,
    _format_machine_info,
    _env_value,
    _render_env_table,
    _approx_sec,
    _format_approx_duration,
    _duration_mode_cells,
    _render_duration_table,
    _print_machine_report,
)
from _test_runner.doc_writer import (  # noqa: F401
    _DOC_ENV_TABLE_MARKERS,
    _DOC_DURATION_TABLE_MARKERS,
    _DOC_MODE_COUNT_MARKERS,
    _DOC_COVERAGE_PATH,
    _find_machine_column,
    _new_separator_cell,
    _update_machine_table,
    _update_mode_count_table,
    _update_test_coverage_doc,
    _display_path,
    _update_test_coverage_doc_file,
)
from _test_runner.report_html import (  # noqa: F401
    _overall_status,
    _report_links_html,
    _render_index_html,
)
from _test_runner.runner import (  # noqa: F401
    _ensure_dirs,
    _create_latest_structure,
    archive_existing,
    run_mode,
    _run_phased,
)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--mode",
        default="all",
        help="运行模式 (unit/scenario/integration/regression/edge/all)，逗号分隔；bench 为环境耗时对照的 14 模式聚合",
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
    parser.add_argument(
        "--machine-info",
        action="store_true",
        help="输出机器硬件信息 + 各模式实测耗时 markdown 表格（供 test-coverage.md 环境耗时对照更新）",
    )
    parser.add_argument(
        "--update-docs",
        action="store_true",
        help="自动更新 docs-stm/managements/test-coverage.md 环境耗时对照（隐含 --machine-info）",
    )
    parser.add_argument("--help", action="store_true", help="显示帮助")
    args = parser.parse_args()
    if args.update_docs:
        args.machine_info = True
    return args


def main() -> None:
    """主入口：归档 → 执行 → 汇总。"""
    args = parse_args()

    if args.help:
        print(_HELP_TEXT)
        return

    # 解析模式列表（bench 别名展开为对照表模式序列）
    modes_to_run = _resolve_modes([m.strip() for m in args.mode.split(",")])
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
    if args.update_docs:
        print("  [..] 文档更新: 开启（结束后自动回填 test-coverage.md 环境耗时对照）")

    # 机器信息采集（--machine-info 时启用）
    machine_info: dict | None = None
    if args.machine_info:
        machine_info = _collect_machine_info(args.parallel or "medium")
        print(_format_machine_info(machine_info))

    # 归档现有报告
    archive_path = archive_existing()

    # 创建目录结构
    _create_latest_structure(modes_to_run)

    # 运行各模式
    results: list[dict] = []
    try:
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
    except KeyboardInterrupt:
        print("\n  [!] 手动中断，输出已完成模式的结果")
        _print_machine_report(machine_info, results)
        if args.update_docs and machine_info is not None and results:
            print("\n  [..] 更新已完成模式的耗时对照")
            _update_test_coverage_doc_file(machine_info, results)
        sys.exit(130)

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

    # 机器环境 + 耗时表格输出（--machine-info 时启用）
    _print_machine_report(machine_info, results)

    # 自动更新环境耗时对照文档（--update-docs 时启用）
    if args.update_docs and machine_info is not None:
        _update_test_coverage_doc_file(machine_info, results)

    sys.exit(overall)


if __name__ == "__main__":
    main()
