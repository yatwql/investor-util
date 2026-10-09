"""报告生成管线性能收集 —— 轻量阶段计时、持久化、趋势查看。

三层体系：
    Layer 1 — 本模块（PerfCollector）+ orchestrator.py 埋点
    Layer 2 — scripts/perf-report.py（独立基准，mock 外部数据源）
    Layer 3 — scripts/perf-view.py（历史趋势可视化）

设计约束遵从（详见 technical.md §8）：
    缓存原子写入  — 原子写入：tempfile.mkstemp + os.replace
    日志统一  — 统一日志：logging.getLogger("invest")
    PerfCollector 为普通局部对象，非模块级单例
    路径从 PROJECT_ROOT 绝对化

数据收集策略：
    - 每次 generate_report() 自动收集各阶段耗时
    - 阶段开始时可经 stage_announcer 向进度通道广播状态行（当前阶段 / 已耗时 /
      预计剩余，ETA 基于本文件历史同阶段中位数，计算失败静默降级）
    - 写入 data/state/perf_history.jsonl（JSONL 格式，一行一次运行）
    - 同时通过 logging 输出 INFO 级计时日志
    - 结果包含版本号，支持跨版本性能趋势追踪
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.python.core.constants import APP_VERSION, PROJECT_ROOT
from src.python.core.jsonl_store import append_jsonl_atomic

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
    status: str = "completed"  # 运行状态：completed / interrupted（中断收口写入）
    interrupted_stage: str | None = None  # 中断时活跃阶段名（仅 status=interrupted）

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
            "status": self.status,
            "interrupted_stage": self.interrupted_stage,
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
    - stage_announcer 为可选的阶段状态广播回调（进度通道显示当前阶段/
      预计剩余），回调异常静默吞掉，不影响计时与生成流程
    """

    def __init__(
        self,
        report_type: str,
        holdings: list,
        *,
        stage_announcer: Callable[["PerfCollector"], None] | None = None,
    ) -> None:
        self._report_type = report_type
        self._holdings_count = len(holdings)
        self._phases: list[_PhaseRecord] = []
        self._errors: list[str] = []
        self._warnings_count: int = 0
        self._current_name: str | None = None
        self._current_start: float | None = None
        self._stage_announcer = stage_announcer
        self._interrupted = False
        self._interrupted_stage: str | None = None
        self._saved = False

    @property
    def report_type(self) -> str:
        """本次运行的报告类型（basic/both/full，供 ETA 预估按类型筛样本）。"""
        return self._report_type

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
        self._announce_stage()

    def stage_status(self) -> dict[str, Any] | None:
        """当前活跃阶段状态 {"phase": 阶段名, "elapsed": 已耗时秒}；无活跃阶段时 None。"""
        if self._current_name is None or self._current_start is None:
            return None
        return {
            "phase": self._current_name,
            "elapsed": round(time.perf_counter() - self._current_start, 1),
        }

    def _announce_stage(self) -> None:
        """阶段开始时向进度通道广播状态行（回调异常静默，不影响计时）。"""
        if self._stage_announcer is None:
            return
        try:
            self._stage_announcer(self)
        except Exception:
            logger.debug("[perf] 阶段状态广播失败，已忽略", exc_info=True)

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

    def mark_interrupted(self) -> None:
        """标记本次运行为「已中断」（快照 status=interrupted，随附活跃阶段名）。

        由 run_integrity 中断收口调用；阶段间隙中断时活跃阶段为 None。
        """
        self._interrupted = True
        self._interrupted_stage = self._current_name

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
            status="interrupted" if self._interrupted else "completed",
            interrupted_stage=self._interrupted_stage if self._interrupted else None,
        )

    def save(self) -> None:
        """将本次运行耗时追加到 perf_history.jsonl（遵循原子写入）。

        幂等：一次运行只落一条记录（正常完成先落、随后中断收口再落时跳过）。
        """
        if self._saved:
            logger.debug("[perf] 本次运行已记录，跳过重复落盘")
            return
        line = json.dumps(self.snapshot().to_json(), ensure_ascii=False) + "\n"
        _append_jsonl_atomic(_PERF_HISTORY_FILE, line)
        self._saved = True
        logger.info("[perf] 耗时已记录到 %s", _PERF_HISTORY_FILE)


# ── 原子写入工具 ────────────────────────────


def _append_jsonl_atomic(path: str, line: str) -> None:
    """向 JSONL 文件原子追加一行（原语见 `core/jsonl_store.py`）。

    策略：读全部现有内容 → 追加新行 → tempfile.mkstemp + os.replace 写回。
    遵循原子写入：直接覆写会因断电/崩溃产生半写损坏文件。
    """
    append_jsonl_atomic(path, line, prefix=".perf_history_", log_tag="perf", noun="历史文件")


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


def summarize_health_history(limit: int = 10) -> list[dict[str, Any]]:
    """聚合数据源健康历史为最近 limit 次运行摘要。

    每条摘要包含：时间戳、报告类型、持仓数量、源总数/成功数/失败数、
    失败源名称列表（最多前 5 个）。聚合逻辑集中在核心层，
    供 TUI/Web 端展示「数据源健康历史」。

    Args:
        limit: 返回最近多少次运行（默认 10）

    Returns:
        按时间升序的摘要列表；无历史记录时返回 []
    """
    records = load_health_history()
    recent = records[-limit:] if limit > 0 else []
    summaries: list[dict[str, Any]] = []
    for record in recent:
        sources = record.get("sources") or {}
        failed = [name for name, s in sources.items() if not s.get("ok")][:5]
        summaries.append(
            {
                "timestamp": record.get("timestamp", ""),
                "report_type": record.get("report_type", ""),
                "holdings_count": record.get("holdings_count", 0),
                "total": record.get("total", len(sources)),
                "ok_count": record.get("ok_count", sum(1 for s in sources.values() if s.get("ok"))),
                "fail_count": record.get("fail_count", sum(1 for s in sources.values() if not s.get("ok"))),
                "failed_sources": failed,
            }
        )
    return summaries


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


# ── 阶段 ETA 预估（事中进度显示） ────────────────────────

_ETA_LOOKBACK_RUNS = 20  # 预估取最近 N 次运行的同阶段样本


def estimate_stage_eta(
    phase_name: str,
    elapsed_seconds: float,
    *,
    history: list[dict[str, Any]] | None = None,
    report_type: str | None = None,
) -> float | None:
    """基于 perf 历史同阶段中位数，估算当前阶段剩余秒数。

    口径：取最近 ``_ETA_LOOKBACK_RUNS`` 次运行中同名阶段的耗时中位数，
    剩余 = 中位数 − 已耗时（下限 0）。

    Args:
        phase_name: 阶段名（与 PerfCollector.start 传入一致）。
        elapsed_seconds: 当前阶段已耗时秒数。
        history: 历史记录注入（测试用）；None 时读 perf_history.jsonl。
        report_type: 限定样本的报告类型（None = 不限定）。

    Returns:
        预计剩余秒数；历史无该阶段样本（含 history 缺失、report_type 不匹配）
        返回 None；**任何异常静默返回 None**（调用方降级为无 ETA，不打断生成）。
    """
    try:
        records = load_history() if history is None else history
        samples: list[float] = []
        for rec in records[-_ETA_LOOKBACK_RUNS:]:
            if report_type is not None and rec.get("report_type") != report_type:
                continue
            sec = _phase_seconds(rec.get("phases"), phase_name)
            if sec is not None:
                samples.append(sec)
        if not samples:
            return None
        return max(0.0, round(statistics.median(samples) - float(elapsed_seconds), 1))
    except Exception:
        logger.debug("[perf] 阶段 ETA 预估失败（%s），静默降级为无 ETA", phase_name, exc_info=True)
        return None


def _phase_seconds(phases: Any, phase_name: str) -> float | None:
    """从历史记录的 phases 字段取指定阶段耗时（兼容 dict / 早期 list 两种形状）。"""
    if isinstance(phases, dict):
        sec = phases.get(phase_name)
    elif isinstance(phases, list):
        sec = next(
            (p.get("seconds") for p in phases if isinstance(p, dict) and p.get("name") == phase_name),
            None,
        )
    else:
        return None
    if isinstance(sec, bool) or not isinstance(sec, (int, float)) or sec < 0:
        return None
    return float(sec)


def format_stage_status(status: dict[str, Any], eta: float | None) -> str:
    """阶段状态单行文案 — 所有进度通道共用的唯一格式化点（同源）。

    形如 ``「LLM+新闻」· 已耗时 12s · 预计剩余 ~284s``；eta 为 None 时仅显示
    已耗时。Web 前端展示时外层自带「当前阶段（第 N 步）：」前缀。
    """
    phase = status.get("phase") or ""
    elapsed = float(status.get("elapsed") or 0.0)
    line = f"「{phase}」· 已耗时 {elapsed:.0f}s"
    if eta is not None:
        line += f" · 预计剩余 ~{eta:.0f}s"
    return line
