#!/usr/bin/env python3
"""测试驱动脚本 — 统一运行 pytest 并输出结构化 HTML 报告。

用法:
  python scripts/test_runner.py                          # 全量测试
  python scripts/test_runner.py --mode unit              # 仅单元测试
  python scripts/test_runner.py --mode edge              # 仅边缘测试
  python scripts/test_runner.py --mode scenario,edge     # 多模式组合
  python scripts/test_runner.py --coverage               # 全量 + 覆盖率报告
  python scripts/test_runner.py --mode bench --machine-info  # 跨机器耗时采集（环境 + 各模式实测表格）
  python scripts/test_runner.py --mode bench --update-docs   # 采集并自动回填环境耗时对照表
  python scripts/test_runner.py --help                   # 本帮助
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time as _time
from datetime import datetime
from typing import Callable

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
        "desc": "开发期快速验证（core/providers/fetcher/analysis 单元 + 基础场景；耗时参考 docs-stm/managements/test-coverage.md 环境耗时对照）",
        "order": 5,
        "preflight": [[sys.executable, "scripts/check-task-numbering.py", "--ci"]],
        "phases": [
            {
                "marker": "(unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts or unit_web) and not (edge or data)",
                "desc": "核心模块单元测试",
                "timeout_sec": 300,
                "parallel": True,
            },
            {"marker": "scenario_basic", "desc": "基础业务场景（耗时参考 docs-stm/managements/test-coverage.md 环境耗时对照）", "timeout_sec": 300, "parallel": True},
        ],
    },
    "verify": {
        "marker": "unit_core or unit_providers or unit_fetcher or unit_config or unit_news or unit_llm or unit_analysis or unit_scripts or unit_web",
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
        "desc": "冒烟测试（快速验证核心通路；耗时参考 docs-stm/managements/test-coverage.md 环境耗时对照）",
        "timeout_sec": 60,
        "order": 11,
        "parallel": False,
    },
    "report": {
        "marker": "unit_report",
        "desc": "仅报告模块测试（开发期快速验证报告变更）",
        "timeout_sec": 600,
        "order": 12,
        "parallel": True,
    },
    "scenario_extreme": {
        "marker": "scenario_extreme",
        "desc": "极限场景测试（S0c 超多持仓 + S10 极端值，手工触发；耗时参考 docs-stm/managements/test-coverage.md 环境耗时对照）",
        "timeout_sec": 600,
        "order": 13,
        "parallel": False,
    },
    "live": {
        "marker": "live",
        "desc": "真实网络验证套件（opt-in，仅 `--mode live` 手工运行；不入门禁）",
        "timeout_sec": 300,
        "order": 14,
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
  python scripts/test_runner.py --mode bench --machine-info  # 跨机器耗时采集（环境 + 各模式实测表格）
  python scripts/test_runner.py --mode bench --update-docs   # 采集并自动回填环境耗时对照表
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
  --machine-info    输出机器硬件信息 + 各模式实测耗时 markdown 表格（供耗时对照更新）
  --update-docs     自动更新 test-coverage.md 环境耗时对照表（隐含 --machine-info）
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


# ── 机器信息与耗时表格 ─────────────────────────────────────────


# 「环境耗时对照」表标准顺序（对齐 docs-stm/managements/test-coverage.md），
# 供耗时表格排序；live 为 opt-in 网络套件，不纳入对照表。
_MODE_TABLE_ORDER: tuple[str, ...] = (
    "unit", "standard", "scenario", "regression",
    "dev-verify", "verify", "integration", "edge", "data",
    "all", "smoke", "report", "all_no_unit", "scenario_extreme",
)

# bench 运行顺序：将最重的 all 置于末尾，慢机器前序轻量模式跑完可随时中断。
_BENCH_MODES: tuple[str, ...] = tuple(m for m in _MODE_TABLE_ORDER if m != "all") + ("all",)


def _resolve_modes(modes_to_run: list[str]) -> list[str]:
    """展开模式列表：将 bench 别名替换为基准模式序列，按首次出现去重保序。

    Args:
        modes_to_run: 用户输入的模式列表（可含 bench）

    Returns:
        展开去重后的模式列表（仅含 MODES 键）
    """
    seen: set[str] = set()
    resolved: list[str] = []
    for mode in modes_to_run:
        candidates = list(_BENCH_MODES) if mode == "bench" else [mode]
        for cand in candidates:
            if cand not in seen:
                seen.add(cand)
                resolved.append(cand)
    return resolved


def _read_cpu_model_linux() -> str | None:
    """读 Linux /proc/cpuinfo 首个 model name；文件缺失返回 None。"""
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        return None
    return None


def _count_physical_cores_linux() -> int | None:
    """按 (physical id, core id) 去重统计 Linux 物理核数；缺失返回 None。"""
    pairs: set[tuple[str, str]] = set()
    phys = core = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                lowered = stripped.lower()
                if lowered.startswith("physical id"):
                    phys = stripped.split(":", 1)[1].strip()
                elif lowered.startswith("core id"):
                    core = stripped.split(":", 1)[1].strip()
                    pairs.add((phys, core))
    except OSError:
        return None
    return len(pairs) or None


def _mem_gib_linux() -> float | None:
    """读 Linux /proc/meminfo MemTotal（KB）换算 GiB；缺失返回 None。"""
    try:
        with open("/proc/meminfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lower().startswith("memtotal"):
                    return int(line.split()[1]) / (1024 ** 2)
    except (OSError, ValueError, IndexError):
        return None
    return None


def _linux_disk_info() -> tuple[str | None, str | None]:
    """探测 Linux 根分区文件系统类型与磁盘类型。

    Returns:
        (文件系统类型, 磁盘类型)；不可用时分别为 None
    """
    fs_type = None
    device = None
    try:
        with open("/proc/mounts", encoding="utf-8", errors="replace") as f:
            for line in f:
                fields = line.split()
                if len(fields) >= 3 and fields[1] == "/":
                    device, fs_type = fields[0], fields[2]
                    break
    except OSError:
        return None, None

    disk_type = None
    if device:
        base = os.path.basename(device)  # 兼容 /dev/mapper/xxx
        base = re.sub(r"[0-9]+$", "", base)  # 去掉分区尾号
        if base.startswith("nvme"):
            disk_type = "NVMe SSD"
        else:
            try:
                with open(f"/sys/block/{base}/queue/rotational", encoding="utf-8") as f:
                    disk_type = "HDD" if f.read().strip() == "1" else "SSD"
            except OSError:
                disk_type = None
    return fs_type, disk_type


def _sysctl_value(name: str) -> str | None:
    """读 macOS sysctl 值；命令不可用或失败返回 None。"""
    cmd = shutil.which("sysctl")
    if not cmd:
        return None
    try:
        proc = subprocess.run(
            [cmd, "-n", name],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _mem_gib_windows() -> float | None:
    """读 Windows 全局内存状态（ctypes）换算 GiB；不可用返回 None。"""
    import ctypes

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        stat = _MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        return None
    return None


def _collect_machine_info(parallel_level: str = "medium") -> dict:
    """采集机器硬件与环境信息，供耗时对照标注。

    各字段尽力采集，失败回退 None；None 在展示时以"未知"占位。
    """
    system = platform.system()
    info: dict = {
        "os": system,
        "os_release": platform.release(),
        "arch": platform.machine(),
        "hostname": socket.gethostname(),
        "cpu_model": None,
        "cpu_physical_cores": None,
        "cpu_threads": os.cpu_count(),
        "mem_gib": None,
        "disk_type": None,
        "fs_type": None,
        "python_version": platform.python_version(),
        "parallel_level": parallel_level,
        "parallel_workers": _calc_parallel_workers(parallel_level),
        "date": datetime.now().strftime("%Y-%m-%d"),
    }
    if system == "Linux":
        info["cpu_model"] = _read_cpu_model_linux()
        info["cpu_physical_cores"] = _count_physical_cores_linux()
        info["mem_gib"] = _mem_gib_linux()
        info["fs_type"], info["disk_type"] = _linux_disk_info()
    elif system == "Darwin":
        info["cpu_model"] = _sysctl_value("machdep.cpu.brand_string") or None
        phys = _sysctl_value("hw.physicalcpu")
        info["cpu_physical_cores"] = int(phys) if phys and phys.isdigit() else None
        mem = _sysctl_value("hw.memsize")
        info["mem_gib"] = round(int(mem) / (1024 ** 3), 1) if mem and mem.isdigit() else None
    elif system == "Windows":
        info["cpu_model"] = platform.processor() or None
        info["cpu_physical_cores"] = os.cpu_count()
        info["mem_gib"] = _mem_gib_windows()
    return info


def _format_machine_info(info: dict) -> str:
    """将机器信息渲染为单行 markdown 引用说明（字段缺失以"未知"占位）。"""
    os_arch = f"{info.get('os') or '未知'} {info.get('arch') or ''}".strip()
    cpu = info.get("cpu_model") or "未知"
    phys = info.get("cpu_physical_cores")
    threads = info.get("cpu_threads")
    if phys is not None and threads is not None:
        cpu_count = f"{phys} 核 {threads} 线程"
    elif threads is not None:
        cpu_count = f"逻辑 {threads} 线程"
    else:
        cpu_count = "未知"
    mem = info.get("mem_gib")
    mem_s = f"{mem:.1f} GiB" if isinstance(mem, (int, float)) else "内存未知"
    disk = info.get("disk_type") or "磁盘未知"
    fs = info.get("fs_type") or ""
    disk_s = f"{disk}{' · ' + fs if fs else ''}"
    level = info.get("parallel_level") or "medium"
    workers = info.get("parallel_workers") or "?"
    date_s = info.get("date") or ""
    date_part = f" · {date_s}" if date_s else ""
    host = info.get("hostname") or ""
    host_part = f" · 主机 {host}" if host else ""
    return (
        f"> 采集环境：{os_arch} · {cpu} · {cpu_count} · {mem_s} · {disk_s} · "
        f"Python {info.get('python_version') or '未知'} · 并行 {level}（worker={workers}）{host_part}{date_part}"
    )


# 环境属性表行标签（14 行，与 test-coverage.md「采集环境属性」表结构一致；
# 操作系统/系统版本分列，供渲染与文档写入共用单一事实源）。
_ENV_ATTR_LABELS: tuple[str, ...] = (
    "操作系统", "系统版本", "架构", "主机名", "CPU 型号", "物理核数", "逻辑线程",
    "内存", "磁盘类型", "文件系统", "Python 版本", "并行级别", "worker 数", "采集日期",
)


def _env_value(label: str, info: dict) -> str | None:
    """按属性名取环境值（缺失以"未知"占位）；未知属性返回 None 表示不更新该行。"""
    if label == "操作系统":
        return info.get("os") or "未知"
    if label == "系统版本":
        return info.get("os_release") or "未知"
    if label == "架构":
        return info.get("arch") or "未知"
    if label == "主机名":
        return info.get("hostname") or "未知"
    if label == "CPU 型号":
        return info.get("cpu_model") or "未知"
    if label == "物理核数":
        cores = info.get("cpu_physical_cores")
        return str(cores) if cores is not None else "未知"
    if label == "逻辑线程":
        threads = info.get("cpu_threads")
        return str(threads) if threads is not None else "未知"
    if label == "内存":
        mem = info.get("mem_gib")
        return f"{mem:.1f} GiB" if isinstance(mem, (int, float)) else "未知"
    if label == "磁盘类型":
        return info.get("disk_type") or "未知"
    if label == "文件系统":
        return info.get("fs_type") or "未知"
    if label == "Python 版本":
        return info.get("python_version") or "未知"
    if label == "并行级别":
        return str(info.get("parallel_level") or "未知")
    if label == "worker 数":
        return str(info.get("parallel_workers") or "未知")
    if label == "采集日期":
        return info.get("date") or "未知"
    return None


def _render_env_table(info: dict) -> str:
    """渲染机器环境属性 markdown 表格（14 行，与文档「采集环境属性」表结构一致）。"""
    rows = [(label, _env_value(label, info)) for label in _ENV_ATTR_LABELS]
    lines = [
        "| 环境属性 | 值 |",
        "|:---------|:---|",
    ]
    lines.extend(f"| {key} | {val} |" for key, val in rows)
    return "\n".join(lines) + "\n"


def _approx_sec(seconds: float) -> int:
    """耗时取整为约值（下限 1 秒），用于表格"~Ns"展示。"""
    return max(1, round(seconds))


def _format_approx_duration(seconds: float) -> str:
    """耗时约值文本：≥60s 显示 ~{M}min，否则 ~{N}s（对齐文档旧列风格）。"""
    secs = _approx_sec(seconds)
    if secs >= 60:
        return f"~{round(secs / 60)}min"
    return f"~{secs}s"


def _duration_mode_cells(results: list[dict]) -> dict[str, str]:
    """按模式名聚合实测耗时单元格文本（未实测/超时模式缺席）。

    组合行 verify,regression 为 verify 与 regression 顺序耗时之和。
    """
    by_mode = {r.get("mode", ""): r for r in results if not r.get("timed_out")}
    cells: dict[str, str] = {}
    for mode in _MODE_TABLE_ORDER:
        res = by_mode.get(mode)
        if res is None:
            continue
        cells[mode] = _format_approx_duration(res.get("duration", 0.0) or 0.0)
        if mode == "regression" and "verify" in by_mode:
            v = by_mode["verify"]
            dur2 = (res.get("duration", 0.0) or 0.0) + (v.get("duration", 0.0) or 0.0)
            cells["verify,regression"] = (
                f"{_format_approx_duration(dur2)}（verify+regression 顺序之和）"
            )
    return cells


def _render_duration_table(results: list[dict]) -> str:
    """渲染各模式实测耗时 markdown 表格（对齐「环境耗时对照」顺序）。

    含 verify,regression 组合行；超时与不在对照表内的模式跳过。
    """
    by_mode = {r.get("mode", ""): r for r in results if not r.get("timed_out")}
    lines = [
        "| `--mode` | 覆盖项数 | 耗时 |",
        "|:---------|:--------:|:--------:|",
    ]
    for mode in _MODE_TABLE_ORDER:
        res = by_mode.get(mode)
        if res is None:
            continue
        cnt = (
            res.get("passed", 0) + res.get("failed", 0)
            + res.get("skipped", 0) + res.get("errors", 0)
        )
        lines.append(f"| `{mode}` | {cnt} | ~{_approx_sec(res.get('duration', 0.0) or 0.0)}s |")
        if mode == "regression" and "verify" in by_mode:
            v = by_mode["verify"]
            cnt2 = cnt + (
                v.get("passed", 0) + v.get("failed", 0)
                + v.get("skipped", 0) + v.get("errors", 0)
            )
            dur2 = (res.get("duration", 0.0) or 0.0) + (v.get("duration", 0.0) or 0.0)
            lines.append(f"| `verify,regression` | {cnt2} | ~{_approx_sec(dur2)}s（verify+regression 之和） |")
    return "\n".join(lines) + "\n"


def _print_machine_report(machine_info: dict | None, results: list[dict]) -> None:
    """输出机器环境属性表 + 各模式耗时表（仅 --machine-info 时启用）。"""
    if machine_info is None:
        return
    print()
    print(_format_machine_info(machine_info))
    print()
    print(_render_env_table(machine_info))
    print()
    print(_render_duration_table(results))
    timed_out_modes = [r.get("mode", "") for r in results if r.get("timed_out")]
    if timed_out_modes:
        print(f"> 超时未纳入耗时表：{', '.join(timed_out_modes)}")


# ── 环境耗时对照文档自动更新 ─────────────────────────────────
# 两张表用 HTML 注释标记定位（渲染不可见，供脚本增改表结构）。

_DOC_ENV_TABLE_MARKERS = ("<!-- env-table:start -->", "<!-- env-table:end -->")
_DOC_DURATION_TABLE_MARKERS = ("<!-- duration-table:start -->", "<!-- duration-table:end -->")
_DOC_COVERAGE_PATH = os.path.join(_PROJECT_ROOT, "docs-stm", "managements", "test-coverage.md")


def _find_machine_column(header_row: list[str], hostname: str) -> int | None:
    """在表头 token 网格中查找含 `{hostname}（` 的列序号（第 1 列为序号 1）。

    header_row 为按 `|` 拆分后的 token 列表（行首/行尾 token 为空串）。
    旧慢笔记本等非本机列因主机名不匹配而天然豁免。
    """
    marker = hostname + "（"
    for idx in range(1, len(header_row) - 1):
        if marker in header_row[idx].strip():
            return idx
    return None


def _new_separator_cell(last_sep: str) -> str:
    """由既有数据列分隔标记推断新增列对齐样式（居中 :---: 或左对齐 :---）。"""
    return ":---:" if last_sep.rstrip().endswith(":") else ":---"


def _update_machine_table(
    table_lines: list[str],
    header_cell: str,
    row_value: Callable[[str], str | None],
) -> list[str]:
    """更新或新增当前主机名列（其余单元格字节原样保留）。

    Args:
        table_lines: 两 marker 之间的表格行（含表头/分隔行/数据行）
        header_cell: 主机名列表头文本 `{hostname}（{date} 实测）`
        row_value: 数据行第一列 label → 该主机列值；返回 None 保留原值不更新

    Returns:
        更新后的表格行列表

    Raises:
        ValueError: 区域首行不是表格行
    """
    if not table_lines or not table_lines[0].lstrip().startswith("|"):
        raise ValueError("表区域首行不是 `|` 开头的表格行")
    grid = [line.split("|") for line in table_lines]

    hostname = header_cell.split("（", 1)[0]
    col = _find_machine_column(grid[0], hostname)
    new_col = col is None
    if new_col:
        col = len(grid[0]) - 1  # 行尾空 token 前插入新列

    if new_col:
        grid[0].insert(col, f" {header_cell} ")  # 新列：插入以保留行尾空 token
    else:
        grid[0][col] = f" {header_cell} "  # 更新（含日期刷新）

    if new_col and len(grid) >= 2:  # 分隔行：新增列补对齐标记
        grid[1].insert(col, _new_separator_cell(grid[1][-2]))

    for tokens in grid[2:]:  # 数据行：按行 label 取值
        label = tokens[1].strip()
        value = row_value(label)
        if new_col:
            tokens.insert(col, f" {value} " if value is not None else " ")
        elif value is not None:
            tokens[col] = f" {value} "  # 缺失（None）→ 保留原单元格

    return ["|".join(tokens) for tokens in grid]


def _table_region_pattern(markers: tuple[str, str]) -> re.Pattern:
    """构建表区域正则（起始标记 → 表格 → 结束标记，跨行）。"""
    start_marker, end_marker = markers
    return re.compile(
        re.escape(start_marker) + r"\n(.*?)\n" + re.escape(end_marker),
        re.DOTALL,
    )


def _extract_table_region(doc_text: str, markers: tuple[str, str]) -> list[str]:
    """抽取两 marker 之间的表格行（不含 marker 行与空行）。

    Raises:
        ValueError: marker 缺失或区域不是表格
    """
    m = _table_region_pattern(markers).search(doc_text)
    if not m:
        raise ValueError(f"文档缺少成对的表区域标记 {markers[0]} … {markers[1]}")
    lines = [ln for ln in m.group(1).splitlines() if ln.strip()]
    if not lines or not lines[0].lstrip().startswith("|"):
        raise ValueError(f"标记 {markers[0]} 与 {markers[1]} 之间未找到表格")
    # 全行校验：任一非表格行（如夹入说明文字）或分隔行缺失都判结构异常，
    # 防止后续 token 网格编辑把数据行误当分隔行而静默破坏表格。
    if any(not ln.lstrip().startswith("|") for ln in lines):
        raise ValueError(f"标记 {markers[0]} 与 {markers[1]} 之间夹有非表格行")
    if len(lines) < 2 or "---" not in lines[1]:
        raise ValueError(f"标记 {markers[0]} 与 {markers[1]} 之间的表格缺少分隔行")
    return lines


def _replace_table_region(
    doc_text: str, markers: tuple[str, str], updated_lines: list[str]
) -> str:
    """以更新后的表格行替换 marker 之间的表区域。

    Raises:
        ValueError: marker 未配对匹配（防御性，正常不会触发）
    """
    block = markers[0] + "\n" + "\n".join(updated_lines) + "\n" + markers[1]
    # 用可调用替换避免 re 把块内容当模板解析（单元格含反斜杠会触发 re.error）。
    new_text, count = _table_region_pattern(markers).subn(
        lambda _match: block, doc_text, count=1
    )
    if count != 1:
        raise ValueError(f"表区域标记 {markers[0]} 与 {markers[1]} 未匹配")
    return new_text


def _update_test_coverage_doc(
    doc_text: str, machine_info: dict, results: list[dict]
) -> str:
    """更新 test-coverage.md 两张「环境耗时对照」表（纯函数，不落盘）。

    Args:
        doc_text: test-coverage.md 全文
        machine_info: _collect_machine_info 结果
        results: 各模式运行结果列表

    Returns:
        更新后的全文；marker 缺失/结构异常时抛 ValueError，绝不擅自改写

    Raises:
        ValueError: 表区域标记缺失或表格结构异常
    """
    hostname = machine_info.get("hostname") or "未知主机"
    date = machine_info.get("date") or ""
    header_cell = f"{hostname}（{date} 实测）"

    env_lines = _extract_table_region(doc_text, _DOC_ENV_TABLE_MARKERS)
    env_updated = _update_machine_table(
        env_lines, header_cell, lambda label: _env_value(label, machine_info)
    )
    doc_text = _replace_table_region(doc_text, _DOC_ENV_TABLE_MARKERS, env_updated)

    duration_cells = _duration_mode_cells(results)
    dur_lines = _extract_table_region(doc_text, _DOC_DURATION_TABLE_MARKERS)
    dur_updated = _update_machine_table(
        dur_lines, header_cell,
        # 数据更新时间行按本机采集日期填充；其余行按模式实测耗时（未测留空）
        lambda label: date if label == "数据更新时间" else duration_cells.get(label.strip("`")),
    )
    doc_text = _replace_table_region(doc_text, _DOC_DURATION_TABLE_MARKERS, dur_updated)

    return doc_text


def _display_path(path: str, start: str) -> str:
    """返回相对 start 的展示路径；Windows 跨盘符时 relpath 抛 ValueError，
    降级返回绝对路径，避免仅用于打印的路径换算崩溃（测试重定向文档路径到
    其他驱动器时会触发）。"""
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return os.path.abspath(path)


def _update_test_coverage_doc_file(machine_info: dict, results: list[dict]) -> None:
    """将本机环境与实测耗时写入 test-coverage.md（仅内容变化时落盘）。

    文档缺标记/结构异常时打印 [ERR] 并返回，绝不破坏既有文档。
    """
    if not os.path.exists(_DOC_COVERAGE_PATH):
        print(f"  [ERR] 未找到 {_DOC_COVERAGE_PATH}，无法更新环境耗时对照")
        return
    with open(_DOC_COVERAGE_PATH, encoding="utf-8") as f:
        original = f.read()
    try:
        updated = _update_test_coverage_doc(original, machine_info, results)
    except Exception as exc:  # 结构异常一律降级 [ERR]，绝不破坏既有文档
        print(f"  [ERR] 未更新环境耗时对照：{exc}")
        return
    if updated == original:
        print(f"  [..] {_display_path(_DOC_COVERAGE_PATH, _PROJECT_ROOT)} 内容未变化，跳过写入")
        return
    with open(_DOC_COVERAGE_PATH, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"  [OK] 已更新 {_display_path(_DOC_COVERAGE_PATH, _PROJECT_ROOT)}（环境耗时对照）")


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
