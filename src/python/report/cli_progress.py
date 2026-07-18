"""CLI 专属进度报告器 — logging 输出（常规）或 stderr 同步（--verbose 模式）。"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from typing import Any

from src.python.report.progress import ProgressReporter

_logger = logging.getLogger("invest")

# ── ANSI 颜色常量（用于 verbose stderr 输出 — 本地维护，不依赖 ansi_colors） ──

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _should_color() -> bool:
    """检测 stderr 是否支持 ANSI 颜色输出。

    基于 stderr.isatty()（而非 stdout）+ NO_COLOR 环境变量，
    适用于 CLI 模式的标准错误输出。
    """
    if "NO_COLOR" in os.environ:
        return False
    return sys.stderr.isatty()


def _clr(text: str, color: str) -> str:
    """如果支持颜色，返回着色文本；否则返回纯文本。"""
    return f"{color}{text}{_RESET}" if _should_color() else text


class CliProgressReporter(ProgressReporter):
    """CLI 进度报告器。

    常规模式（verbose=False）：
      所有消息通过 logging 输出，不写 stderr。
      info/ok → logging.INFO, warn → logging.WARNING, error → logging.ERROR。
      消息**不含** [OK]/[!] 前缀——logger 的 _ColoredFormatter 已输出 [%(levelname)s]。

    --verbose 模式（verbose=True）：
      同步输出带前缀的彩色消息到 stderr（[..]/[OK]/[!]/[ERR]），
      颜色基于 stderr.isatty() + NO_COLOR 自动控制。

    颜色本地维护，不依赖 ansi_colors 模块级常量（ansi_colors 基于 stdout.isatty()
    判断，而 CLI 输出通道为 stderr）。
    """

    def __init__(self, verbose: bool = False) -> None:
        super().__init__()
        self._verbose = verbose

    # ── 基础消息输出 ───────────────────────────────────────

    def info(self, msg: str) -> None:
        """进行中消息 — 记录 INFO 日志；verbose 时同步到 stderr（[..] 前缀）。"""
        _logger.info(msg)
        if self._verbose:
            print(f"  {_clr('[..]', _CYAN)} {msg}", file=sys.stderr)

    def ok(self, msg: str) -> None:
        """成功消息 — 记录 INFO 日志；verbose 时同步到 stderr（[OK] 前缀）。"""
        _logger.info(msg)
        if self._verbose:
            print(f"  {_clr('[OK]', _GREEN)} {msg}", file=sys.stderr)

    def warn(self, msg: str) -> None:
        """警告消息 — 记录 WARNING 日志；verbose 时同步到 stderr（[!] 前缀）。"""
        _logger.warning(msg)
        if self._verbose:
            print(f"  {_clr('[!]', _YELLOW)} {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        """错误消息 — 记录 ERROR 日志；verbose 时同步到 stderr（[ERR] 前缀）。"""
        _logger.error(msg)
        if self._verbose:
            print(f"  {_clr('[ERR]', _RED)} {msg}", file=sys.stderr)

    def add_error(self, msg: str) -> None:
        """记录非致命错误。"""
        self._errors.append(msg)
        _logger.warning("生成异常: %s", msg)

    # ── 安全调用 ──────────────────────────────────────────

    def call_sheet(self, label: str, fn: Callable | None, *args: Any, **kwargs: Any) -> bool:
        """安全调用单页写入函数，记录耗时，失败时记录错误并继续。

        verbose 模式：同步输出 开始/完成 进度到 stderr。
        无论 verbose 与否均使用 Timer 记录耗时。
        """
        if fn is None:
            self.add_error(f"{label}模块缺失，跳过")
            return False
        if self._verbose:
            self.info(f"正在生成{label}...")
        try:
            with self.timer(label):
                fn(*args, **kwargs)
        except Exception:
            self.add_error(f"{label}生成失败（详情请查看日志）")
            _logger.exception("%s写入异常", label)
            return False
        if self._verbose:
            self.ok(f"{label}生成完成")
        return True

    # ── 耗时汇总 ──────────────────────────────────────────

    def print_timing_summary(self) -> None:
        """输出本次运行时各模块耗时排行到 logging，verbose 时同步到 stderr。

        日志输出不含转义序列（纯文本）。verbose 模式 stderr 输出含颜色。
        """
        records = self._timing_records
        if not records:
            return

        # 合并同名 label
        merged: dict[str, float] = {}
        for label, t in records:
            merged[label] = merged.get(label, 0.0) + t
        total = sum(merged.values())

        lines: list[str] = []
        lines.append(f"  模块耗时排行（总计 {total:.1f}s）")
        sorted_records = sorted(merged.items(), key=lambda x: -x[1])
        for label, t in sorted_records:
            pct = t / total * 100 if total > 0 else 0
            bar_len = int(pct / 100 * 24)
            bar = "█" * bar_len + "░" * (24 - bar_len)
            lines.append(f"  {label:<18s} {t:>6.1f}s {pct:>5.1f}% {bar}")

        for line in lines:
            _logger.info(line)
        if self._verbose:
            for line in lines:
                print(line, file=sys.stderr)

        records.clear()
