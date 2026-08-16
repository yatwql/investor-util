"""TUI 日志/健康历史查看命令处理器单元测试。

覆盖 `tui/handlers_log.py`：
  - _cmd_view_logs — 输出渲染 / 级别提示透传 / traceback 折叠 / 空结果 / 异常兜底
  - _cmd_view_health_history — 摘要输出 / 空结果 / 异常兜底

数据源健康历史（data/state/datasource_health.jsonl）已被 conftest 隔离，
测试统一 mock 核心层函数，不触真实状态文件。

运行：
  python -m pytest src/test/unit/ui/test_handlers_log.py -v
"""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from src.python.core.log_reader import LogEntry
from src.python.tui.handlers_log import _cmd_view_health_history, _cmd_view_logs
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_ui]


class TestCmdViewLogs(unittest.TestCase):
    """_cmd_view_logs 日志查看。"""

    def _run(self, level_input: str = "") -> str:
        """执行命令并捕获输出（mock 输入与翻页等待）。"""
        out = io.StringIO()
        with (
            patch("sys.stdout", out),
            patch("src.python.tui.handlers_log.input", return_value=level_input),
            patch("src.python.tui.handlers_log.press_any_key"),
        ):
            _cmd_view_logs()
        return out.getvalue()

    def test_output_entries(self):
        """有日志时输出条目，traceback 折叠为提示行。"""
        entries = [
            LogEntry(time="2026-08-16 10:00:00,123", level="INFO", message="应用启动", body="应用启动"),
            LogEntry(
                time="2026-08-16 10:00:01,456",
                level="ERROR",
                message="读取行情失败",
                body="读取行情失败\n  堆栈行1\n  堆栈行2",
            ),
        ]
        with patch("src.python.core.log_reader.read_log", return_value=entries):
            out = self._run()
        self.assertIn("应用启动", out)
        self.assertIn("读取行情失败", out)
        self.assertIn("⤷ 堆栈详情 +2 行", out)

    def test_level_filter_passthrough(self):
        """级别提示输入 ERROR → read_log(level="ERROR")。"""
        with (
            patch("src.python.core.log_reader.read_log", return_value=[]) as mock_read,
            patch("src.python.tui.handlers_log.input", return_value="ERROR"),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            _cmd_view_logs()
        self.assertEqual(mock_read.call_args.kwargs["level"], "ERROR")

    def test_empty_level_means_all(self):
        """空回车 → level=None（全部）。"""
        with (
            patch("src.python.core.log_reader.read_log", return_value=[]) as mock_read,
            patch("src.python.tui.handlers_log.input", return_value=""),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            _cmd_view_logs()
        self.assertIsNone(mock_read.call_args.kwargs["level"])

    def test_invalid_level_shows_all(self):
        """无效级别 → 提示并将 level 置 None（显示全部）。"""
        with (
            patch("src.python.core.log_reader.read_log", return_value=[]) as mock_read,
            patch("src.python.tui.handlers_log.input", return_value="VERBOSE"),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        ):
            _cmd_view_logs()
        self.assertIsNone(mock_read.call_args.kwargs["level"])
        self.assertIn("无效级别", mock_out.getvalue())

    def test_no_match(self):
        """无匹配条目提示。"""
        with (
            patch("src.python.core.log_reader.read_log", return_value=[]),
            patch("src.python.tui.handlers_log.input", return_value=""),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        ):
            _cmd_view_logs()
        self.assertIn("无匹配日志条目", mock_out.getvalue())

    def test_exception_fallback(self):
        """read_log 抛异常 → [ERR] 提示且不崩溃。"""
        with (
            patch("src.python.core.log_reader.read_log", side_effect=OSError("IO error")),
            patch("src.python.tui.handlers_log.input", return_value=""),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        ):
            _cmd_view_logs()
        self.assertIn("[ERR]", mock_out.getvalue())


class TestCmdViewHealthHistory(unittest.TestCase):
    """_cmd_view_health_history 健康历史查看。"""

    def test_output_summaries(self):
        """有摘要时输出时间线（ok/total 与失败源）。"""
        summaries = [
            {
                "timestamp": "2026-08-16T10:00:00",
                "report_type": "basic",
                "holdings_count": 3,
                "total": 10,
                "ok_count": 8,
                "fail_count": 2,
                "failed_sources": ["腾讯K线", "财联社"],
            }
        ]
        with (
            patch("src.python.core.perf.summarize_health_history", return_value=summaries),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        ):
            _cmd_view_health_history()
        out = mock_out.getvalue()
        self.assertIn("2026-08-16 10:00:00", out)
        self.assertIn("8/10", out)
        self.assertIn("腾讯K线", out)

    def test_empty(self):
        """无历史记录提示。"""
        with (
            patch("src.python.core.perf.summarize_health_history", return_value=[]),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        ):
            _cmd_view_health_history()
        self.assertIn("暂无数据源健康历史记录", mock_out.getvalue())

    def test_exception_fallback(self):
        """异常 → [ERR] 提示且不崩溃。"""
        with (
            patch("src.python.core.perf.summarize_health_history", side_effect=OSError("IO error")),
            patch("src.python.tui.handlers_log.press_any_key"),
            patch("sys.stdout", new_callable=io.StringIO) as mock_out,
        ):
            _cmd_view_health_history()
        self.assertIn("[ERR]", mock_out.getvalue())
