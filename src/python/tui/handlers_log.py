"""TUI 日志/健康历史查看命令处理器。

菜单 [V] 查看最近运行日志（可按级别筛选）、[H] 查看数据源健康历史。
所有解析/聚合逻辑委托核心层（core/log_reader.py、core/perf.py），
本模块仅保留 TUI 外壳（级别提示、彩色渲染、traceback 折叠、翻页等待）。
"""

from __future__ import annotations

from src.python.core.logger import setup_logger
from src.python.tui.tui_menu import GREEN, RED, RESET, YELLOW, press_any_key

logger = setup_logger()

# 单屏最多展示的日志条数（防止长日志刷屏）
_DISPLAY_LINES = 200

# 级别筛选提示文案
_LEVEL_PROMPT_TEXT = "（留空=全部，可选: DEBUG/INFO/WARNING/ERROR/CRITICAL）"


def _level_prompt() -> str | None:
    """交互式级别筛选提示；空回车返回 None（全部），无效级别提示后按全部处理。"""
    raw = input(f"  按级别筛选 {_LEVEL_PROMPT_TEXT}: ").strip().upper()
    if not raw:
        return None
    if raw in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return raw
    print(f"  {YELLOW}[!]{RESET} 无效级别「{raw}」，将显示全部日志")
    return None


def _level_color(level: str) -> str:
    """日志级别对应的终端颜色（ERROR/CRITICAL 红、WARNING 黄、其余无色）。"""
    if level in ("ERROR", "CRITICAL"):
        return RED
    if level == "WARNING":
        return YELLOW
    return ""


def _cmd_view_logs() -> None:
    """查看最近运行日志（可按级别筛选，traceback 折叠为提示行）。"""
    from src.python.core.log_reader import read_log

    level = _level_prompt()
    try:
        entries = read_log(limit=_DISPLAY_LINES, level=level)
    except (ValueError, OSError):
        logger.exception("读取运行日志失败")
        print(f"  {RED}[ERR]{RESET} 读取运行日志失败")
        press_any_key()
        return

    if not entries:
        print(f"  {YELLOW}[!]{RESET} 无匹配日志条目")
        press_any_key()
        return

    level_label = level or "全部"
    print()
    print(f"  {'=' * 40}")
    print(f"  最近日志（级别: {level_label}）")
    print(f"  {'=' * 40}")
    for entry in entries:
        color = _level_color(entry.level)
        line = f"  {entry.time} [{entry.level}] {entry.message}"
        print(f"{color}{line}{RESET}" if color else line)
        # traceback 等续行折叠为一行提示，避免刷屏
        body_lines = entry.body.splitlines()[1:]
        if body_lines:
            print(f"    ⤷ 堆栈详情 +{len(body_lines)} 行")
    press_any_key()


def _cmd_view_health_history() -> None:
    """查看数据源健康历史（最近 10 次检查记录）。"""
    from src.python.core.perf import summarize_health_history

    try:
        summaries = summarize_health_history(limit=10)
    except OSError:
        logger.exception("读取数据源健康历史失败")
        print(f"  {RED}[ERR]{RESET} 读取数据源健康历史失败")
        press_any_key()
        return

    if not summaries:
        print(f"  {YELLOW}[!]{RESET} 暂无数据源健康历史记录")
        press_any_key()
        return

    print()
    print(f"  {'=' * 40}")
    print("  数据源健康历史（最近 10 次检查）")
    print(f"  {'=' * 40}")
    for summary in summaries:
        ts = summary["timestamp"].replace("T", " ")
        ok_count = summary["ok_count"]
        total = summary["total"]
        fail_count = summary["fail_count"]
        status = GREEN if fail_count == 0 else RED
        extra = f"  |  {summary['report_type']}" if summary.get("report_type") else ""
        print(f"  {ts}  {status}{ok_count}/{total} 正常{RESET}{extra}  |  失败 {fail_count}")
        if summary["failed_sources"]:
            print(f"      失败源: {', '.join(summary['failed_sources'])}")
    press_any_key()
