"""CLI 命令行模式单元测试。

覆盖参数解析、CliProgressReporter、报告/缓存路由、退出码。
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.python.cli import (
    _EXIT_PARTIAL,
    _EXIT_SEVERE,
    _EXIT_SUCCESS,
    _build_parser,
    _cli_read_holdings,
    _handle_cache_update,
    main,
)


# ═══════════════════════════════════════════════════════════════
# argparse 参数解析
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestArgparse:
    """CLI 参数解析测试。"""

    def test_global_help(self):
        """--help 输出主帮助信息。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["--help"])
        assert exc.value.code == 0

    def test_global_version(self):
        """--version 输出版本号。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["--version"])
        assert exc.value.code == 0

    def test_report_subcommand(self):
        """report 子命令默认参数。"""
        args = _build_parser().parse_args(["report"])
        assert args.command == "report"
        assert args.type == "basic"
        assert args.history == "off"
        assert args.force_llm is False
        assert args.warm is False

    def test_report_type_both(self):
        """report --type both 解析。"""
        args = _build_parser().parse_args(["report", "--type", "both"])
        assert args.type == "both"

    def test_report_type_full(self):
        """report --type full 解析。"""
        args = _build_parser().parse_args(["report", "--type", "full"])
        assert args.type == "full"

    def test_report_history_auto(self):
        """report --history auto 解析。"""
        args = _build_parser().parse_args(["report", "--history", "auto"])
        assert args.history == "auto"

    def test_report_force_llm(self):
        """report --force-llm 标志解析。"""
        args = _build_parser().parse_args(["report", "--force-llm"])
        assert args.force_llm is True

    def test_report_warm(self):
        """report --warm 标志解析。"""
        args = _build_parser().parse_args(["report", "--warm"])
        assert args.warm is True

    def test_cache_subcommands(self):
        """cache 子命令及其互斥操作。"""
        args = _build_parser().parse_args(["cache", "--clean"])
        assert args.command == "cache"
        assert args.clean is True

        args = _build_parser().parse_args(["cache", "--stats"])
        assert args.stats is True

        args = _build_parser().parse_args(["cache", "--update", "basic"])
        assert args.update == "basic"

    def test_global_config(self):
        """--config 全局参数解析。"""
        args = _build_parser().parse_args(["--config", "/tmp/test.json", "report"])
        assert args.config == "/tmp/test.json"

    def test_global_verbose(self):
        """--verbose 全局标志解析。"""
        args = _build_parser().parse_args(["--verbose", "report"])
        assert args.verbose is True

    def test_global_output(self):
        """--output 全局参数解析。"""
        args = _build_parser().parse_args(["--output", "/tmp/reports", "report"])
        assert args.output == "/tmp/reports"

    def test_invalid_command(self):
        """未知命令 → SystemExit(2)。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["unknown"])
        assert exc.value.code == 2

    def test_cache_missing_action(self):
        """cache 不带操作参数 → SystemExit(2)（互斥组 required=True）。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["cache"])
        assert exc.value.code == 2


# ═══════════════════════════════════════════════════════════════
# CliProgressReporter
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestCliProgressReporter:
    """CliProgressReporter 行为测试。"""

    def test_info_logging(self, caplog):
        """非 verbose 模式：info 写入日志。"""
        from src.python.report.cli_progress import CliProgressReporter

        caplog.set_level(10)  # DEBUG
        r = CliProgressReporter(verbose=False)
        r.info("测试信息")
        assert "测试信息" in caplog.text

    def test_ok_logging(self, caplog):
        """非 verbose 模式：ok 写入日志。"""
        from src.python.report.cli_progress import CliProgressReporter

        caplog.set_level(10)
        r = CliProgressReporter(verbose=False)
        r.ok("成功")
        assert "成功" in caplog.text

    def test_warn_logging(self, caplog):
        """非 verbose 模式：warn 写入日志。"""
        from src.python.report.cli_progress import CliProgressReporter

        caplog.set_level(10)
        r = CliProgressReporter(verbose=False)
        r.warn("警告")
        # WARNING 级别
        assert "警告" in caplog.text
        assert any(r.levelname == "WARNING" for r in caplog.records if "警告" in r.message)

    def test_error_logging(self, caplog):
        """非 verbose 模式：error 写入日志。"""
        from src.python.report.cli_progress import CliProgressReporter

        caplog.set_level(10)
        r = CliProgressReporter(verbose=False)
        r.error("错误")
        assert "错误" in caplog.text

    def test_verbose_stderr(self, capsys):
        """verbose 模式：消息同步到 stderr 带 [..]/[OK] 前缀。"""
        from src.python.report.cli_progress import CliProgressReporter

        r = CliProgressReporter(verbose=True)
        r.info("进度消息")
        r.ok("成功消息")
        stderr = capsys.readouterr().err
        assert "[..]" in stderr
        assert "[OK]" in stderr
        assert "进度消息" in stderr
        assert "成功消息" in stderr

    def test_non_verbose_no_stderr(self, capsys):
        """非 verbose 模式：stderr 无输出。"""
        from src.python.report.cli_progress import CliProgressReporter

        r = CliProgressReporter(verbose=False)
        r.info("不应出现")
        r.ok("也不应出现")
        stderr = capsys.readouterr().err
        assert stderr == ""

    def test_call_sheet_success(self, capsys, caplog):
        """call_sheet 成功时 verbose 模式输出开始/完成。"""
        from src.python.report.cli_progress import CliProgressReporter

        caplog.set_level(10)
        r = CliProgressReporter(verbose=True)
        fn = MagicMock(return_value=True)
        result = r.call_sheet("测试页", fn)
        assert result is True
        fn.assert_called_once()
        stderr = capsys.readouterr().err
        assert "测试页" in stderr

    def test_call_sheet_fn_none(self):
        """call_sheet 函数为 None 时返回 False。"""
        from src.python.report.cli_progress import CliProgressReporter

        r = CliProgressReporter()
        result = r.call_sheet("缺失模块", None)
        assert result is False
        assert len(r.get_errors()) == 1

    def test_call_sheet_exception(self):
        """call_sheet 函数抛出异常时返回 False。"""
        from src.python.report.cli_progress import CliProgressReporter

        def _broken():
            raise ValueError("测试异常")

        r = CliProgressReporter()
        result = r.call_sheet("异常页", _broken)
        assert result is False

    def test_add_error(self):
        """add_error 记录非致命错误。"""
        from src.python.report.cli_progress import CliProgressReporter

        r = CliProgressReporter()
        r.add_error("测试错误")
        assert "测试错误" in r.get_errors()

    def test_print_timing_summary_empty(self, caplog):
        """无耗时记录时 print_timing_summary 不输出。"""
        from src.python.report.cli_progress import CliProgressReporter

        caplog.set_level(10)
        r = CliProgressReporter()
        r.print_timing_summary()
        # 不应有耗时相关日志
        assert not any("耗时" in r.message for r in caplog.records)

    def test_print_timing_summary_with_records(self, caplog):
        """有耗时记录时输出排行。"""
        from src.python.report.cli_progress import CliProgressReporter

        caplog.set_level(10)
        r = CliProgressReporter()
        r._timing_records.append(("测试模块", 1.5))
        r.print_timing_summary()
        assert any("测试模块" in r.message for r in caplog.records)
        assert any("耗时" in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════
# _cli_read_holdings
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestCliReadHoldings:
    """_cli_read_holdings 行为测试。"""

    def test_file_not_found(self, caplog):
        """文件不存在时返回 None + ERROR 日志。"""
        caplog.set_level(10)
        config = {"holdings_dir": "/nonexistent", "holdings_filename": "test.xlsx"}
        result = _cli_read_holdings(config)
        assert result is None
        assert any("持仓文件不存在" in r.message for r in caplog.records
                    if r.levelname == "ERROR")


# ═══════════════════════════════════════════════════════════════
# _handle_cache_update
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestHandleCacheUpdate:
    """_handle_cache_update 委托测试。"""

    def test_update_basic(self):
        """--update basic 委托 update_basic_cache 并返回 exit_code。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0

        with (
            patch("src.python.cli._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.cache.operations.update_basic_cache", return_value=mock_result),
        ):
            code = _handle_cache_update("basic", {}, MagicMock())
        assert code == 0

    def test_update_position(self):
        """--update position 委托 update_position_cache。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0

        with (
            patch("src.python.cli._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.cache.operations.update_position_cache", return_value=mock_result),
        ):
            code = _handle_cache_update("position", {}, MagicMock())
        assert code == 0

    def test_update_all_max_effort(self):
        """--update all 最大努力：basic 失败后仍执行 position。"""
        mock_basic = MagicMock()
        mock_basic.exit_code = 1
        mock_pos = MagicMock()
        mock_pos.exit_code = 0

        with (
            patch("src.python.cli._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.cache.operations.update_basic_cache", return_value=mock_basic),
            patch("src.python.cache.operations.update_position_cache", return_value=mock_pos),
        ):
            code = _handle_cache_update("all", {}, MagicMock())
        assert code == 1  # max(1, 0)

    def test_holdings_none_returns_severe(self):
        """持仓为 None 时返回 _EXIT_SEVERE。"""
        with patch("src.python.cli._cli_read_holdings", return_value=None):
            code = _handle_cache_update("basic", {}, MagicMock())
        assert code == _EXIT_SEVERE


# ═══════════════════════════════════════════════════════════════
# main() — 参数透传
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestMain:
    """main() 入口参数透传测试。"""

    def test_report_param_passthrough(self):
        """report 子命令参数正确透传给 _handle_report。"""
        with (
            patch("src.python.cli._handle_report", return_value=_EXIT_SUCCESS) as mock_report,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config", return_value={}),
            patch("src.python.logger.setup_logger"),
        ):
            with patch.object(
                __import__("sys"), "argv",
                ["cli.py", "report", "--type", "full", "--history", "auto", "--force-llm", "--warm"],
            ):
                main()

        mock_report.assert_called_once()
        args = mock_report.call_args[0][0]
        assert args.type == "full"
        assert args.history == "auto"
        assert args.force_llm is True
        assert args.warm is True

    def test_cache_param_passthrough(self):
        """cache 子命令参数正确透传给 _handle_cache。"""
        with (
            patch("src.python.cli._handle_cache", return_value=_EXIT_SUCCESS) as mock_cache,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config", return_value={}),
            patch("src.python.logger.setup_logger"),
        ):
            with patch.object(
                __import__("sys"), "argv",
                ["cli.py", "cache", "--update", "all"],
            ):
                main()

        mock_cache.assert_called_once()
        args = mock_cache.call_args[0][0]
        assert args.update == "all"
