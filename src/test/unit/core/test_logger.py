"""日志模块（core/logger）关闭竞态回归测试。

覆盖：进程退出阶段（模块级 atexit 注册的关闭日志）流已关闭时，
_ClosedStreamSilentHandler 静默降级，不产生 `--- Logging error ---` 噪声。

回归背景：全量测试（mode all）进程退出时，tui.py 模块级
`atexit.register(log_app_boundary, "关闭", "TUI模式")` 触发的关闭日志
在 pytest 关闭 sys.stderr 后执行，StreamHandler emit 抛
`ValueError: I/O operation on closed file`，logging 默认 handleError
打印 `--- Logging error ---` 噪声。修复：console handler 换用
_ClosedStreamSilentHandler，仅对 "closed file" 竞态静默。
"""

from __future__ import annotations

import io
import logging
from unittest import mock

import pytest

import src.python.core.logger as log_mod

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestClosedStreamSilentHandler:
    """流已关闭时的静默降级回归测试。"""

    @staticmethod
    def _make_record() -> logging.LogRecord:
        return logging.LogRecord(
            name="invest",
            level=logging.INFO,
            pathname="test_logger.py",
            lineno=1,
            msg="关闭日志",
            args=(),
            exc_info=None,
        )

    def test_emit_after_stream_closed_no_logging_error(self):
        """stream 关闭后 emit：不打印 logging error（静默降级、不抛异常）。"""
        buf = io.StringIO()
        handler = log_mod._ClosedStreamSilentHandler(buf)
        handler.setFormatter(logging.Formatter("%(message)s"))
        buf.close()  # 模拟进程退出阶段 stream 被关闭

        # StreamHandler.emit 内部 try/except → handleError，本类对
        # "closed file" 静默返回，不会打印 `--- Logging error ---`
        handler.emit(self._make_record())
        assert True  # 到达此处即未抛异常

    def test_handle_error_silent_for_closed_file(self):
        """handleError 对 "closed file" 异常静默（不委托父类打印路径）。"""
        handler = log_mod._ClosedStreamSilentHandler(io.StringIO())
        with mock.patch.object(logging.StreamHandler, "handleError") as mock_super:
            try:
                raise ValueError("I/O operation on closed file")
            except ValueError:
                handler.handleError(self._make_record())
            mock_super.assert_not_called()

    def test_handle_error_passthrough_for_other_errors(self):
        """handleError 对非 "closed file" 错误照常委托父类。"""
        handler = log_mod._ClosedStreamSilentHandler(io.StringIO())
        with mock.patch.object(logging.StreamHandler, "handleError") as mock_super:
            try:
                raise RuntimeError("boom")
            except RuntimeError:
                handler.handleError(self._make_record())
            mock_super.assert_called_once()

    def test_console_handler_is_silent_handler(self):
        """setup_logger 控制台 handler 为 _ClosedStreamSilentHandler。"""
        logger = log_mod.setup_logger("invest_test_console_type")
        console = next(h for h in logger.handlers if isinstance(h, logging.StreamHandler))
        assert isinstance(console, log_mod._ClosedStreamSilentHandler)
        # 清理，避免污染其他测试
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
