"""结构化日志读取 —— 为 CLI/TUI/Web 三端提供统一的日志查看能力。

核心层承载全部日志解析/过滤/尾部读取逻辑，渠道层（CLI/TUI/Web）
只做薄展示，不实现任何解析/聚合逻辑。

日志格式与 core/logger.py 一致：
    "%(asctime)s [%(levelname)s] %(message)s"
    asctime 默认格式：YYYY-MM-DD HH:MM:SS,mmm（逗号毫秒，非 ISO）
多行记录（如 traceback 异常堆栈）以续行方式存在于物理文件中——
续行不以时间戳起始，解析时归并到上一条记录。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

# 与 core/logger.py::_LOG_FORMAT 的时间戳前缀匹配（含级别，保证续行不误匹配）
_TIMESTAMP_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \[(?P<level>[A-Z]+)\] (?P<message>.*)$")

# 装饰性横幅/提示特征（如「⚗ 实验性功能已开启！」整块横幅）
_DECORATIVE_HINTS = ("⚗",)

# 日志级别阈值（标准 logging 语义：选择 ERROR 时同时包含 CRITICAL）
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# tail_log 反向分块读取的块大小（64KB）
_TAIL_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class LogEntry:
    """一条结构化日志记录。

    Attributes:
        time: 时间戳（"YYYY-MM-DD HH:MM:SS,mmm"，与日志格式一致）
        level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        message: 首行消息
        body: 完整记录内容（message + 多行续行/traceback），供展开查看
        is_decorative: 是否为装饰性横幅/分隔线（置灰显示，不作为级别筛选依据）
    """

    time: str
    level: str
    message: str
    body: str
    is_decorative: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化字典（供 Web 端渲染）。"""
        return {
            "time": self.time,
            "level": self.level,
            "message": self.message,
            "body": self.body,
            "is_decorative": self.is_decorative,
        }


def _is_decorative(message: str) -> bool:
    """判断消息是否为装饰性横幅/纯分隔线。

    特征：
    - 包含实验性功能提示符「⚗」（如「⚗ 实验性功能已开启！」）
    - 消息仅由 = - * — 分隔字符重复构成（纯分隔线横幅）
    - 空白行
    """
    if any(hint in message for hint in _DECORATIVE_HINTS):
        return True
    stripped = message.strip()
    if not stripped:
        return True
    for ch in stripped:
        if ch not in "=-*—":
            return False
    return len(stripped) >= 3


def _level_no(name: str) -> int:
    """将日志级别名映射为数值；无效级别抛 ValueError。"""
    if name not in LOG_LEVELS:
        raise ValueError(f"无效日志级别: {name}（可选: {', '.join(LOG_LEVELS)}）")
    return LOG_LEVELS[name]


def default_log_path() -> str:
    """返回当前环境下的默认日志文件路径。

    惰性引用 core/logger.py 的 _LOG_FILE（pytest 环境下自动为 test.log）。
    """
    from src.python.core.logger import _LOG_FILE

    return _LOG_FILE


def parse_log(text: str) -> list[LogEntry]:
    """解析日志文本为 LogEntry 列表（纯函数）。

    规则：
    - 以时间戳起始的行为新记录，非时间戳行归并到上一条记录（多行 traceback 续行）
    - 首条记录前的孤儿行丢弃（tail 边界处不完整的记录头）
    """
    entries: list[LogEntry] = []
    current: LogEntry | None = None
    for line in text.splitlines():
        match = _TIMESTAMP_RE.match(line)
        if match:
            if current is not None:
                entries.append(current)
            body = match.group("message")
            current = LogEntry(
                time=match.group("ts"),
                level=match.group("level"),
                message=body,
                body=body,
                is_decorative=_is_decorative(body),
            )
        elif current is not None:
            # 续行归并到上一条记录（不可变重建）
            current = LogEntry(
                time=current.time,
                level=current.level,
                message=current.message,
                body=current.body + "\n" + line,
                is_decorative=current.is_decorative,
            )
        # 无当前记录前的孤儿行丢弃（tail 边界不完整记录头）
    if current is not None:
        entries.append(current)
    return entries


def tail_log(path: str, limit: int = 5000) -> str:
    """从文件尾部反向读取最近 limit 行。

    从文件末尾向前分块读取（每块 64KB），收集到足够换行即停止，
    避免大日志文件（>100MB）全量读入内存导致解析卡顿。

    Args:
        path: 日志文件路径
        limit: 返回的最大行数

    Returns:
        最近 limit 行文本（若行数不足 limit 则返回全部行）
    """
    if not os.path.isfile(path):
        return ""
    size = os.path.getsize(path)
    if size == 0:
        return ""
    if limit < 1:
        limit = 1
    pos = size
    newline_count = 0
    pieces: list[bytes] = []
    with open(path, "rb") as f:
        while pos > 0:
            read_size = min(_TAIL_CHUNK_SIZE, pos)
            pos -= read_size
            f.seek(pos)
            raw = f.read(read_size)
            pieces.append(raw)
            newline_count += raw.count(b"\n")
            if newline_count > limit:
                break
    text = b"".join(reversed(pieces)).decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > limit:
        lines = lines[-limit:]
    return "\n".join(lines)


def read_log(
    path: str | None = None,
    *,
    limit: int = 5000,
    level: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[LogEntry]:
    """读取结构化日志条目（尾部读取 + 级别/时间过滤）。

    Args:
        path: 日志文件路径；None 时使用 default_log_path()
        limit: 尾部读取的最大物理行数（防止大日志卡顿）
        level: 最小级别阈值（ERROR 含 ERROR+CRITICAL，标准 logging 语义）；
               无效级别抛 ValueError
        since: 起始时间前缀过滤（词典序比较 entry.time[:len(since)]）
        until: 结束时间前缀过滤（含边界）

    Returns:
        LogEntry 列表（按时间升序）；文件缺失或为空时返回 []
    """
    log_path = path if path is not None else default_log_path()
    threshold: int | None = None
    if level is not None:
        threshold = _level_no(level)  # 无效级别立即抛 ValueError
    entries = parse_log(tail_log(log_path, limit=limit))
    if threshold is not None:
        entries = [e for e in entries if LOG_LEVELS.get(e.level, 0) >= threshold]
    if since is not None:
        entries = [e for e in entries if e.time[: len(since)] >= since]
    if until is not None:
        entries = [e for e in entries if e.time[: len(until)] <= until]
    return entries


__all__ = ["LOG_LEVELS", "LogEntry", "default_log_path", "parse_log", "read_log", "tail_log"]
