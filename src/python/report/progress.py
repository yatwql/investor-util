"""进度报告及耗时记录 — 解耦报告模块与 TUI 显示。

报告模块通过 ProgressReporter 接口输出进度消息和错误，
不直接依赖 TUI 或 print()，方便在无终端环境下运行。
"""

from __future__ import annotations

import logging
import time as _time_module
from collections.abc import Callable
from typing import Any

from src.python.ansi_colors import CYAN, GREEN, RED, RESET, YELLOW

logger = logging.getLogger("invest")

# ── 模块耗时记录（跨模块共享） ───────────────────────────────
timing_records: list[tuple[str, float]] = []


class Timer:
    """简单计时器上下文管理器，记录各模块耗时。"""

    def __init__(self, label: str) -> None:
        self.label = label
        self.start: float = 0.0

    def __enter__(self) -> Timer:
        self.start = _time_module.time()
        return self

    def __exit__(self, *args) -> None:
        elapsed = _time_module.time() - self.start
        timing_records.append((self.label, elapsed))


# ── 进度报告接口 ─────────────────────────────────────────────


class ProgressReporter:
    """报告进度回调接口。报告模块通过此接口输出进度和错误，不依赖 TUI。

    子类可覆盖各方法自定义输出格式（终端、日志、静默等）。
    """

    def __init__(self) -> None:
        self._errors: list[str] = []

    def info(self, msg: str) -> None:
        """进行中消息（对应 [..] 前缀）。"""

    def ok(self, msg: str) -> None:
        """成功消息（对应 [OK] 前缀）。"""

    def warn(self, msg: str) -> None:
        """警告消息（对应 [!] 前缀）。"""

    def error(self, msg: str) -> None:
        """错误消息（对应 [ERR] 前缀）。"""

    def add_error(self, msg: str) -> None:
        """记录非致命错误，不影响继续执行。"""
        self._errors.append(msg)
        logger.warning("生成异常: %s", msg)

    def get_errors(self) -> list[str]:
        """返回已记录的错误列表。"""
        return list(self._errors)

    def call_sheet(self, label: str, fn: Callable | None, *args: Any, **kwargs: Any) -> bool:
        """安全调用单页写入函数，记录耗时，失败时记录错误并继续。

        Args:
            label: 页面名称（中文，用于日志/输出）
            fn: 要调用的写入函数（为 None 时视为模块缺失）
            args, kwargs: 传递给 fn 的参数

        Returns:
            True 表示成功，False 表示失败/未调用
        """
        if fn is None:
            self.add_error(f"{label}模块缺失，跳过")
            return False
        with Timer(label):
            try:
                fn(*args, **kwargs)
                return True
            except Exception:
                self.add_error(f"{label}生成失败（详情请查看日志）")
                logger.exception("%s写入异常", label)
                return False

    def print_timing_summary(self) -> None:
        """输出耗时汇总。默认空实现，子类可覆盖。"""

    def timer(self, label: str) -> Timer:
        """返回计时器上下文管理器，用于包裹耗时较长的操作。"""
        return Timer(label)


class SilentProgressReporter(ProgressReporter):
    """静默进度报告器 — 所有消息不输出（默认），适合库调用场景。"""
    pass


class TuiProgressReporter(ProgressReporter):
    """终端进度报告器 — 将进度消息格式化为 [..]/[OK]/[ERR]/[!] 前缀输出。"""

    def __init__(self) -> None:
        self._errors: list[str] = []

    def info(self, msg: str) -> None:
        print(f"  {CYAN}[..]{RESET} {msg}")

    def ok(self, msg: str) -> None:
        print(f"  {GREEN}[OK]{RESET} {msg}")

    def warn(self, msg: str) -> None:
        print(f"  {YELLOW}[!]{RESET} {msg}")

    def error(self, msg: str) -> None:
        print(f"  {RED}[ERR]{RESET} {msg}")

    def add_error(self, msg: str) -> None:
        self._errors.append(msg)
        logger.warning("生成异常: %s", msg)

    def get_errors(self) -> list[str]:
        return list(self._errors)

    def call_sheet(self, label: str, fn: Callable | None, *args: Any, **kwargs: Any) -> bool:
        """终端风格的安全页签写入调用。"""
        if fn is None:
            self.add_error(f"{label}模块缺失，跳过")
            return False
        self.info(f"正在生成{label}...")
        try:
            with Timer(label):
                fn(*args, **kwargs)
        except Exception:
            self.add_error(f"{label}生成失败（详情请查看日志）")
            logger.exception("%s写入异常", label)
            return False
        self.ok(f"{label}生成完成")
        return True

    def print_timing_summary(self) -> None:
        """输出本次运行时各模块耗时排行。"""
        if not timing_records:
            return
        # 合并同名 label
        merged: dict[str, float] = {}
        for label, t in timing_records:
            merged[label] = merged.get(label, 0.0) + t
        total = sum(merged.values())
        print()
        print(f"  ┌{'─' * 48}┐")
        print(f"  │  ⏱ 模块耗时排行（总计 {total:.1f}s）{' ' * 17}│")
        print(f"  ├{'─' * 48}┤")
        sorted_records = sorted(merged.items(), key=lambda x: -x[1])
        for label, t in sorted_records:
            pct = t / total * 100 if total > 0 else 0
            bar_len = int(pct / 100 * 24)
            bar = "█" * bar_len + "░" * (24 - bar_len)
            print(f"  │ {label:<18s} {t:>6.1f}s {pct:>5.1f}% {bar} │")
        print(f"  └{'─' * 48}┘")
        timing_records.clear()

    def print_error_summary(self) -> None:
        """如果存在错误，在终端输出汇总。"""
        if not self._errors:
            return
        print("\n  [!] 以下模块遇到问题（不影响已有结果）:")
        for e in self._errors:
            print(f"    - {e}")
        self._errors.clear()
