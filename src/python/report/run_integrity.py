"""报告生成运行一致性守卫（语义名 run_integrity）。

职责（生成中断缺清理与产物一致性保障）：

- **运行上下文**：``guard_run`` 装饰 ``generate_report``，入口 ``begin_run`` 建立
  当前运行上下文（ContextVar，按线程隔离，Web 并行运行互不串扰），登记报告类型 /
  输出目录 / PerfCollector / 健康检查 future / 已写盘产物 / 在写临时文件；
  ``finally`` 中 ``clear_run`` 收尾。
- **原子落盘配套**：写盘方先 ``note_temp`` 登记同目录临时文件（`<目标>.tmp`），
  ``os.replace`` 成功后 ``note_artifact`` 登记产物——单文件原子写只保单文件，
  整批一致性由产物登记 + 中断收口共同保障。无运行上下文时两者均为空操作
  （whatif / 独立调用不受影响）。
- **中断收口**：``handle_interruption`` 在 KeyboardInterrupt 安全落点执行——
  ① 清理本次登记的未完成临时文件（含按产物名前缀的遗留 ``.tmp`` 兜底清扫，
  上次崩溃遗留亦在下次 ``begin_run`` 预清扫）② PerfCollector 以 status=interrupted
  落 perf_history 运行记录（下次启动消费方读到「已中断」，不误判为成功）
  ③ 经 reporter 明确提示「已写盘 / 未完成已丢弃 / 已清理临时文件」
  ④ 收敛后台健康检查（best-effort，防线程残留）。
- 每步独立 try/except：收口过程绝不吞掉 KeyboardInterrupt 本身，调用方负责 re-raise。
"""

from __future__ import annotations

import functools
import glob
import inspect
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable

from src.python.core.constants import REPORT_FILE_BASE

logger = logging.getLogger("invest")

#: 产物临时文件后缀（原子落盘：同目录写 `<目标>.tmp` → os.replace）
TEMP_SUFFIX = ".tmp"

#: 产物 kind → 中文标签（中断提示用）
_KIND_LABELS = {"html": "HTML", "xlsx": "Excel"}


@dataclass
class RunContext:
    """单次报告运行的一致性上下文。"""

    report_type: str
    output_dir: str
    perf: Any = None
    health: Any = None  # (future, report_type, holdings)
    artifacts: list[tuple[str, str]] = field(default_factory=list)
    temps: list[str] = field(default_factory=list)

    @property
    def written_kinds(self) -> set[str]:
        """已原子落盘的产物 kind 集合（"html" / "xlsx"）。"""
        return {kind for kind, _ in self.artifacts}


_current: ContextVar[RunContext | None] = ContextVar("run_integrity_context", default=None)


# ── 上下文生命周期 ──────────────────────────────────────────


def begin_run(report_type: str, output_dir: str) -> RunContext:
    """建立当前运行上下文，并预清扫上次崩溃遗留的产物临时文件。"""
    ctx = RunContext(report_type=report_type, output_dir=output_dir)
    _current.set(ctx)
    try:
        stale = _sweep_product_tmps(output_dir)
        if stale:
            logger.info("[run_integrity] 预清扫遗留产物临时文件 %d 个", stale)
    except Exception:
        logger.warning("[run_integrity] 预清扫遗留临时文件失败（非关键）", exc_info=True)
    return ctx


def current_run() -> RunContext | None:
    """当前运行上下文（无则 None）。"""
    return _current.get()


def clear_run() -> None:
    """清空当前运行上下文（generate_report finally 收尾）。"""
    _current.set(None)


def guard_run(fn: Callable) -> Callable:
    """generate_report 中断收口装饰器：begin_run → 执行 → KeyboardInterrupt 安全落点。

    收口（清理临时产物 / 落 status=interrupted 记录 / 提示已写盘明细）完成后
    原样 re-raise，保持各渠道既有中断语义（CLI 退出码 130、菜单层「操作已取消」）。
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        bound = inspect.signature(fn).bind(*args, **kwargs)
        bound.apply_defaults()
        config = bound.arguments.get("config") or {}
        output_dir = bound.arguments.get("output_dir") or config.get("output_dir", "reports")
        begin_run(str(bound.arguments.get("report_type") or "basic"), str(output_dir))
        try:
            return fn(*args, **kwargs)
        except KeyboardInterrupt:
            handle_interruption(bound.arguments.get("reporter"))
            raise
        finally:
            clear_run()

    return wrapper


# ── 登记接口（写盘方调用） ─────────────────────────────────


def bind_perf(perf: Any) -> None:
    """绑定本次运行的 PerfCollector（中断时据此落 status=interrupted 记录）。"""
    ctx = _current.get()
    if ctx is not None:
        ctx.perf = perf


def bind_health(future: Any, report_type: str, holdings: list) -> None:
    """绑定后台健康检查 future（中断时收敛，防线程残留）。"""
    ctx = _current.get()
    if ctx is not None and future is not None:
        ctx.health = (future, report_type, holdings)


def note_temp(path: str) -> None:
    """登记在写临时文件（写临时文件前调用；中断收口按登记精确清理）。"""
    ctx = _current.get()
    if ctx is not None:
        ctx.temps.append(path)


def note_artifact(kind: str, path: str) -> None:
    """登记已原子落盘的产物（os.replace 成功后调用；kind ∈ {"html","xlsx"}）。"""
    ctx = _current.get()
    if ctx is not None:
        ctx.artifacts.append((kind, path))


# ── 临时文件清扫 ────────────────────────────────────────────


def _product_tmp_files(output_dir: str) -> list[str]:
    """输出目录下本程序产物的 ``.tmp`` 文件（含日期归档子目录）。"""
    pattern = os.path.join(output_dir, "**", f"*{REPORT_FILE_BASE}*{TEMP_SUFFIX}")
    return [p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p)]


def _unlink_quiet(path: str) -> bool:
    """尽力删除单个文件；不存在返回 False，其它失败记告警返回 False。"""
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        logger.warning("[run_integrity] 删除临时文件失败: %s", path, exc_info=True)
        return False


def _sweep_product_tmps(output_dir: str) -> int:
    """按产物名前缀清扫输出目录下的 ``.tmp`` 文件，返回删除数。"""
    return sum(1 for path in _product_tmp_files(output_dir) if _unlink_quiet(path))


def _cleanup_context_temps(ctx: RunContext) -> list[str]:
    """清理本运行登记的在写临时文件 + 产物前缀兜底清扫，返回被删路径。"""
    removed: list[str] = []
    seen: set[str] = set()
    for path in list(dict.fromkeys(ctx.temps)):
        seen.add(os.path.abspath(path))
        if _unlink_quiet(path):
            removed.append(path)
    for path in _product_tmp_files(ctx.output_dir):
        if os.path.abspath(path) in seen:
            continue
        if _unlink_quiet(path):
            removed.append(path)
    return removed


# ── 中断收口 ────────────────────────────────────────────────


def _display_path(path: str, output_dir: str) -> str:
    """产物路径转展示形态（输出目录内用相对路径）。"""
    try:
        rel = os.path.relpath(path, output_dir)
        return rel if not rel.startswith("..") else path
    except ValueError:
        return path


def _emit(reporter: Any, msg: str) -> None:
    """经进度通道输出提示（通道缺失/异常静默，不影响收口）。"""
    try:
        warn = getattr(reporter, "warn", None)
        if callable(warn):
            warn(msg)
    except Exception:
        logger.debug("[run_integrity] 中断提示输出失败", exc_info=True)


def handle_interruption(reporter: Any = None) -> None:
    """KeyboardInterrupt 安全落点收口（不吞异常，装饰器负责 re-raise）。

    步骤：记录中断阶段 → 清理未完成临时文件 → 落 status=interrupted 运行记录 →
    输出「已写盘 / 未完成已丢弃 / 已清理临时文件」明细 → 收敛健康检查。
    各步独立 best-effort，任一步失败不影响后续步骤与中断传播。
    """
    ctx = _current.get()
    if ctx is None:
        logger.warning("[run_integrity] 生成在运行上下文建立前被中断")
        _emit(reporter, "生成已中断——未产生任何产物")
        return

    # 1) 中断阶段（perf 活跃阶段名；阶段间隙记「阶段间隙」）
    stage = "启动准备"
    try:
        if ctx.perf is not None:
            status = ctx.perf.stage_status()
            stage = status["phase"] if status else "阶段间隙"
    except Exception:
        logger.debug("[run_integrity] 读取中断阶段失败", exc_info=True)

    # 2) 清理本次未完成临时文件（登记路径 + 产物前缀兜底）
    cleaned: list[str] = []
    try:
        cleaned = _cleanup_context_temps(ctx)
    except Exception:
        logger.warning("[run_integrity] 清理临时文件失败", exc_info=True)

    # 3) 落 status=interrupted 运行记录（perf_history 单源；已落盘则 save 幂等跳过）
    try:
        if ctx.perf is not None:
            ctx.perf.mark_interrupted()
            ctx.perf.save()
    except Exception:
        logger.warning("[run_integrity] 中断运行记录落盘失败", exc_info=True)

    # 4) 明确提示：已写盘 / 未完成已丢弃 / 已清理临时文件
    try:
        from src.python.report.orchestrator import artifacts_for_report_type

        written = [_display_path(path, ctx.output_dir) for _, path in ctx.artifacts]
        missing = [kind for kind in artifacts_for_report_type(ctx.report_type) if kind not in ctx.written_kinds]
        missing_desc = "、".join(_KIND_LABELS.get(k, k) for k in missing) or "无"
        msg = (
            f"生成已中断（阶段：{stage}）——已写盘：{'、'.join(written) or '无'}；"
            f"未完成已丢弃：{missing_desc}；已清理临时文件 {len(cleaned)} 个"
        )
        logger.warning("[run_integrity] %s", msg)
        _emit(reporter, msg)
    except Exception:
        logger.warning("[run_integrity] 组装中断提示失败", exc_info=True)

    # 5) 收敛后台健康检查（best-effort，防线程残留）
    try:
        if ctx.health is not None:
            from src.python.report._report_health import _collect_health_checks

            future, rtype, holdings = ctx.health
            _collect_health_checks(future, rtype, holdings)
    except Exception:
        logger.debug("[run_integrity] 健康检查收敛失败（非关键）", exc_info=True)
