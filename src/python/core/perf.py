"""报告生成管线性能收集 —— 轻量阶段计时、持久化、趋势查看。

三层体系：
    Layer 1 — 本模块（PerfCollector）+ orchestrator.py 埋点
    Layer 2 — scripts/perf_report.py（独立基准，mock 外部数据源）
    Layer 3 — scripts/perf_view.py（历史趋势可视化）

设计约束遵从（详见 technical.md §8）：
    缓存原子写入  — 原子写入：tempfile.mkstemp + os.replace
    日志统一  — 统一日志：logging.getLogger("invest")
    PerfCollector 为普通局部对象，非模块级单例
    路径从 PROJECT_ROOT 绝对化

数据收集策略：
    - 每次 generate_report() 自动收集各阶段耗时
    - 写入 data/state/perf_history.jsonl（JSONL 格式，一行一次运行）
    - 同时通过 logging 输出 INFO 级计时日志
    - 结果包含版本号，支持跨版本性能趋势追踪
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.python.core.constants import APP_VERSION, PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 持久化路径 ──────────────────────────────────────────
# module-level 变量，测试时可通过 setattr 重定向（测试隔离模式）
_PERF_HISTORY_DIR = os.path.join(PROJECT_ROOT, "data", "state")
_PERF_HISTORY_FILE = os.path.join(_PERF_HISTORY_DIR, "perf_history.jsonl")


# ── 数据结构 ────────────────────────────────────────────


@dataclass
class _PhaseRecord:
    """单个阶段的耗时记录。"""

    name: str
    seconds: float


@dataclass
class ReportRunSnapshot:
    """一次报告生成运行的完整耗时快照。"""

    version: str
    timestamp: str
    report_type: str  # basic / both / full
    holdings_count: int
    phases: list[_PhaseRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings_count: int = 0

    @property
    def total_seconds(self) -> float:
        return sum(p.seconds for p in self.phases)

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "report_type": self.report_type,
            "holdings_count": self.holdings_count,
            "phases": {p.name: round(p.seconds, 3) for p in self.phases},
            "total_seconds": round(self.total_seconds, 3),
            "errors": self.errors,
            "warnings_count": self.warnings_count,
        }


# ── PerfCollector ──────────────────────────────────────


class PerfCollector:
    """一次报告生成会话内的阶段计时收集器。

    用法::

        perf = PerfCollector(report_type="both", holdings=holdings)
        perf.start("行情获取")
        ...
        perf.stop()
        ...
        perf.save()  # 持久化到 perf_history.jsonl

    设计原则:
    - 非单例、非模块级全局
    - 所有时间基于 time.perf_counter()
    - start/stop 成对调用；嵌套时自动关闭前一个并记录警告
    """

    def __init__(self, report_type: str, holdings: list) -> None:
        self._report_type = report_type
        self._holdings_count = len(holdings)
        self._phases: list[_PhaseRecord] = []
        self._errors: list[str] = []
        self._warnings_count: int = 0
        self._current_name: str | None = None
        self._current_start: float | None = None

    # ── 阶段计时 ──

    def start(self, phase_name: str) -> None:
        """开始一个新阶段计时。若前一阶段尚未关闭，自动关闭并记录警告。"""
        if self._current_name is not None:
            logger.warning(
                "[perf] 阶段 '%s' 未结束即启动 '%s'，自动关闭前一阶段",
                self._current_name,
                phase_name,
            )
            self.stop()
        self._current_name = phase_name
        self._current_start = time.perf_counter()

    def stop(self) -> float | None:
        """结束当前阶段计时。

        Returns:
            耗时秒数（已四舍五入到 3 位小数），无活跃阶段时返回 None。
        """
        if self._current_name is None or self._current_start is None:
            return None
        elapsed = round(time.perf_counter() - self._current_start, 3)
        self._phases.append(_PhaseRecord(name=self._current_name, seconds=elapsed))
        logger.info("[perf] %s: %.3fs", self._current_name, elapsed)
        self._current_name = None
        self._current_start = None
        return elapsed

    # ── 辅助记录 ──

    def add_error(self, message: str) -> None:
        """记录一条错误。"""
        self._errors.append(message)

    def inc_warning(self) -> None:
        """增加警告计数。"""
        self._warnings_count += 1

    # ── 快照输出 ──

    def snapshot(self) -> ReportRunSnapshot:
        """生成当前会话的运行时快照。"""
        return ReportRunSnapshot(
            version=APP_VERSION,
            timestamp=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            report_type=self._report_type,
            holdings_count=self._holdings_count,
            phases=list(self._phases),
            errors=list(self._errors),
            warnings_count=self._warnings_count,
        )

    def save(self) -> None:
        """将本次运行耗时追加到 perf_history.jsonl（遵循原子写入）。"""
        line = json.dumps(self.snapshot().to_json(), ensure_ascii=False) + "\n"
        _append_jsonl_atomic(_PERF_HISTORY_FILE, line)
        logger.info("[perf] 耗时已记录到 %s", _PERF_HISTORY_FILE)


# ── 原子写入工具 ────────────────────────────


def _append_jsonl_atomic(path: str, line: str) -> None:
    """向 JSONL 文件原子追加一行。

    策略：读全部现有内容 → 追加新行 → tempfile.mkstemp + os.replace 写回。
    遵循原子写入：直接覆写会因断电/崩溃产生半写损坏文件。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = ""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
        except OSError:
            logger.warning("[perf] 历史文件不可读，将重新创建: %s", path)

    content = existing + line
    fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(path),
        prefix=".perf_history_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        logger.exception("[perf] 写入历史文件失败: %s", path)


# ── 数据源健康检查持久化 ──────────────────────────────

# 健康检查历史文件（同 data/state/ 目录）
_HEALTH_CHECK_FILE = os.path.join(_PERF_HISTORY_DIR, "datasource_health.jsonl")


def save_health_check_snapshot(
    results: list[dict],
    report_type: str = "",
    holdings_count: int = 0,
) -> None:
    """将一次数据源健康检查结果追加到 datasource_health.jsonl。

    Args:
        results: run_health_checks() 返回的结构化结果列表
        report_type: 本次运行报告类型（basic/both/full）
        holdings_count: 持仓数量
    """
    snapshot = {
        "version": APP_VERSION,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "report_type": report_type,
        "holdings_count": holdings_count,
        "sources": {
            r["name"]: {"ok": r["ok"], "latency_ms": r["latency_ms"], "message": r["message"]} for r in results
        },
        "total": len(results),
        "ok_count": sum(1 for r in results if r["ok"]),
        "fail_count": sum(1 for r in results if not r["ok"]),
    }
    line = json.dumps(snapshot, ensure_ascii=False) + "\n"
    _append_jsonl_atomic(_HEALTH_CHECK_FILE, line)
    logger.info("[health] 数据源健康检查结果已记录到 %s", _HEALTH_CHECK_FILE)


def load_health_history(path: str | None = None) -> list[dict[str, Any]]:
    """加载 datasource_health.jsonl，返回运行记录列表。"""
    path = path or _HEALTH_CHECK_FILE
    if not os.path.isfile(path):
        return []
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("[health] 忽略损坏行: %s", line[:80])
    return records


# ── 工具函数（供 Layer 3 脚本使用） ─────────────────────


def load_history(path: str | None = None) -> list[dict[str, Any]]:
    """加载 perf_history.jsonl，返回运行记录列表。

    Args:
        path: JSONL 文件路径，默认使用 _PERF_HISTORY_FILE。

    Returns:
        按时间升序排列的运行记录列表。
    """
    path = path or _PERF_HISTORY_FILE
    if not os.path.isfile(path):
        return []
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("[perf] 忽略损坏行: %s", line[:80])
    return records
