"""ANSI 终端颜色常量 — 共享模块，避免 report 层依赖 UI 层。

使用方：
  - tui_menu.py（UI 层）
  - report/progress.py（报告层）
  - handlers_report.py、handlers_config.py、handlers_cache.py（处理层）
  - logger.py（日志层）
"""

from __future__ import annotations

import os
import sys

try:
    import colorama

    colorama.init()  # 包装 stdout，ANSI → Win32 API，不依赖终端原生 ANSI 支持
except ImportError:
    pass  # 无 colorama 时 Windows 控制台可能无法正确显示颜色，但功能不受影响

# ANSI 颜色：非 TTY 或设置了 NO_COLOR 环境变量时禁用颜色输出
if "NO_COLOR" in os.environ or not sys.stdout.isatty():
    GREEN = RED = YELLOW = CYAN = RESET = ""
else:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
