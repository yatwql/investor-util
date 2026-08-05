"""CLI 命令行模式集成测试。

覆盖日志输出、verbose 模式、配置加载、退出码等跨模块场景。
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.integration_cli]


class TestCliIntegration:
    """CLI 集成测试。"""

    def test_cli_progress_logger(self, caplog):
        """CliProgressReporter 输出全部写入 logging。"""
        caplog.set_level(logging.DEBUG)
        from src.python.report.cli_progress import CliProgressReporter

        r = CliProgressReporter(verbose=False)
        r.info("集成测试信息")
        r.ok("集成测试成功")
        r.warn("集成测试警告")
        r.error("集成测试错误")

        log_text = caplog.text
        assert "集成测试信息" in log_text
        assert "集成测试成功" in log_text
        assert "集成测试警告" in log_text
        assert "集成测试错误" in log_text

    def test_cli_verbose_output_disabled_in_pipe(self, capsys, monkeypatch):
        """非 TTY + 无 NO_COLOR → verbose 输出无 ANSI 转义序列。"""
        monkeypatch.delenv("NO_COLOR", raising=False)
        from src.python.report.cli_progress import CliProgressReporter

        r = CliProgressReporter(verbose=True)
        r.info("管道测试")
        stderr = capsys.readouterr().err
        # stderr 非 TTY（pytest 捕获），不应有 ANSI 转义
        assert "\033[" not in stderr
        assert "[..]" in stderr

    def test_cli_report_config_respected(self):
        """report 子命令正确使用 config 参数。"""
        mock_holdings = [MagicMock()]
        test_config = {"output_dir": "/custom/path"}

        with (
            patch(
                "src.python.cli.cli._cli_read_holdings_with_flows",
                return_value=(mock_holdings, [], []),
            ),
            patch("src.python.report.orchestrator.generate_report") as mock_gen,
        ):
            from src.python.cli.cli import _handle_report
            args = MagicMock(type="basic", history="off", force_llm=False,
                              warm=False, output="/custom/path", verbose=False)
            _handle_report(args, test_config)

        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        assert kwargs["output_dir"] == "/custom/path"
        assert kwargs["report_type"] == "basic"

    def test_cli_cache_config_respected(self):
        """cache 子命令使用 config 中的 holdings 路径。"""
        from src.python.cli.cli import _handle_cache_update

        mock_result = MagicMock()
        mock_result.exit_code = 0
        test_config = {"holdings_dir": "/test/holdings",
                        "holdings_filename": "test.xlsx"}

        with (
            patch("src.python.cli.cli._cli_read_holdings") as mock_read,
            patch("src.python.cache.operations.update_basic_cache", return_value=mock_result),
        ):
            _handle_cache_update("basic", test_config, MagicMock())

        # 验证 config 被正确传递给 _cli_read_holdings
        mock_read.assert_called_once_with(test_config)

    def test_cli_exit_code_success(self):
        """正常完成 → exit 0。"""
        from src.python.cli.cli import _EXIT_SUCCESS
        assert _EXIT_SUCCESS == 0

    def test_cli_exit_code_partial(self):
        """部分失败 → exit 1。"""
        from src.python.cli.cli import _EXIT_PARTIAL
        assert _EXIT_PARTIAL == 1

    def test_cli_exit_code_severe(self):
        """严重错误 → exit 2。"""
        from src.python.cli.cli import _EXIT_SEVERE
        assert _EXIT_SEVERE == 2

    def test_handle_report_return_exit_code(self):
        """_handle_report 返回 orchestrator 的 exit_code。"""
        mock_holdings = [MagicMock()]
        mock_result = MagicMock()
        mock_result.exit_code = 0

        with (
            patch(
                "src.python.cli.cli._cli_read_holdings_with_flows",
                return_value=(mock_holdings, [], []),
            ),
            patch("src.python.report.orchestrator.generate_report", return_value=mock_result),
        ):
            from src.python.cli.cli import _handle_report
            args = MagicMock(type="basic", history="off", force_llm=False,
                              warm=False, output=None, verbose=False)
            code = _handle_report(args, {})
        assert code == 0
