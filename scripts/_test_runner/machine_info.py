"""机器信息采集与耗时表格渲染（环境属性表 / 耗时对照表）。"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess

from _test_runner.modes import _MODE_TABLE_ORDER
from _test_runner.pytest_env import _calc_parallel_workers
import socket
from datetime import datetime


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
                    return int(line.split()[1]) / (1024**2)
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
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
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
            return stat.ullTotalPhys / (1024**3)
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
        info["mem_gib"] = round(int(mem) / (1024**3), 1) if mem and mem.isdigit() else None
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


_ENV_ATTR_LABELS: tuple[str, ...] = (
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
            cells["verify,regression"] = f"{_format_approx_duration(dur2)}（verify+regression 顺序之和）"
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
        cnt = res.get("passed", 0) + res.get("failed", 0) + res.get("skipped", 0) + res.get("errors", 0)
        lines.append(f"| `{mode}` | {cnt} | ~{_approx_sec(res.get('duration', 0.0) or 0.0)}s |")
        if mode == "regression" and "verify" in by_mode:
            v = by_mode["verify"]
            cnt2 = cnt + (v.get("passed", 0) + v.get("failed", 0) + v.get("skipped", 0) + v.get("errors", 0))
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
