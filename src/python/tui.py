"""终端键盘输入封装，跨平台支持方向键操作。

Windows: 使用 msvcrt
Linux:   使用 tty + termios + select（超时）
"""

from __future__ import annotations

import os
import sys

# 标准键名常量
KEY_UP = "KEY_UP"
KEY_DOWN = "KEY_DOWN"
KEY_ENTER = "KEY_ENTER"
KEY_CTRL_C = "KEY_CTRL_C"
KEY_UNKNOWN = "KEY_UNKNOWN"

# Linux ESC 序列读取超时（秒）
_ESC_TIMEOUT = 0.15


def get_key() -> str:
    """读取一个键盘输入，返回标准化键名。

    支持方向键、回车、Ctrl+C 和普通字母键（字母统一转为大写）。

    Returns:
        标准键名字符串
    """
    if os.name == "nt":
        return _get_key_windows()
    return _get_key_linux()


# ── Windows ──────────────────────────────────────────────────


def _get_key_windows() -> str:
    import msvcrt  # Windows 标准库，无需额外安装

    try:
        ch = msvcrt.getch()
    except KeyboardInterrupt:
        return KEY_CTRL_C

    if ch == b"\x03":  # Ctrl+C
        return KEY_CTRL_C
    if ch == b"\r":  # Enter
        return KEY_ENTER
    if ch in (b"\xe0", b"\x00"):  # 方向键/功能键前缀
        try:
            ch2 = msvcrt.getch()
        except KeyboardInterrupt:
            return KEY_CTRL_C
        mapping = {b"H": KEY_UP, b"P": KEY_DOWN}
        return mapping.get(ch2, KEY_UNKNOWN)
    try:
        return ch.decode("utf-8").upper()
    except (UnicodeDecodeError, KeyboardInterrupt):
        return KEY_UNKNOWN


# ── Linux ────────────────────────────────────────────────────


def _get_key_linux() -> str:
    import select
    import tty
    import termios

    if not sys.stdin.isatty():
        # 非 TTY 环境（管道/重定向/CI），无法读取方向键
        return KEY_UNKNOWN
    ch = ""
    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    except (termios.error, ValueError, OSError):
        pass
    except KeyboardInterrupt:
        ch = "\x03"  # 让下游 KEY_CTRL_C 分支处理

    try:
        if ch == "\x03":
            return KEY_CTRL_C
        if ch in ("\r", "\n"):
            return KEY_ENTER
        if ch == "\x1b":  # ESC 序列 -> 方向键
            # 带超时逐字节读取，每字节使用 select 确保可读，防止 read(2) 死等
            rdy, _, _ = select.select([sys.stdin], [], [], _ESC_TIMEOUT)
            if not rdy:
                return KEY_UNKNOWN  # 单独 ESC 键
            b1 = sys.stdin.read(1)
            if not b1:
                return KEY_UNKNOWN
            rdy2, _, _ = select.select([sys.stdin], [], [], _ESC_TIMEOUT)
            if not rdy2:
                return KEY_UNKNOWN  # 仅收到一个后续字节（不完整序列）
            b2 = sys.stdin.read(1)
            if not b2:
                return KEY_UNKNOWN
            seq = ch + b1 + b2
            mapping = {"\x1b[A": KEY_UP, "\x1b[B": KEY_DOWN}
            return mapping.get(seq, KEY_UNKNOWN)
        if ch:
            return ch.upper()
        return KEY_UNKNOWN
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
