"""CLI 命令行模式单元测试 — 子命令解析、处理器与入口。

覆盖子命令：view-logs（日志查看）、doctor（体检）、cassettes（回放带）。

运行：
  pytest src/test/unit/cli/test_cli_subcommands.py -v
"""

from __future__ import annotations


import pytest

from unittest.mock import MagicMock, patch

from src.python.cli import (
    _EXIT_PARTIAL,
    _EXIT_SEVERE,
    _EXIT_SUCCESS,
    _build_parser,
    _handle_cassettes,
    _handle_doctor,
    _handle_view_logs,
    main,
)
from src.python.core.log_reader import LogEntry

pytestmark = [pytest.mark.unit, pytest.mark.unit_cli]


# ═══════════════════════════════════════════════════════════════
# view-logs 子命令
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestArgparseViewLogs:
    """view-logs 子命令参数解析。"""

    def test_view_logs_subcommand(self):
        """view-logs 默认参数。"""
        args = _build_parser().parse_args(["view-logs"])
        assert args.command == "view-logs"
        assert args.level is None
        assert args.lines == 5000
        assert args.since is None
        assert args.until is None

    def test_view_logs_params(self):
        """view-logs --level/--lines/--since/--until 透传。"""
        args = _build_parser().parse_args(
            [
                "view-logs",
                "--level",
                "ERROR",
                "--lines",
                "200",
                "--since",
                "2026-08-16",
                "--until",
                "2026-08-16 12:00:00",
            ]
        )
        assert args.level == "ERROR"
        assert args.lines == 200
        assert args.since == "2026-08-16"
        assert args.until == "2026-08-16 12:00:00"

    def test_view_logs_invalid_level(self):
        """非法 --level 被 argparse 拒绝。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["view-logs", "--level", "VERBOSE"])
        assert exc.value.code == 2


@pytest.mark.unit
class TestHandleViewLogs:
    """_handle_view_logs 输出与退出码。"""

    def test_output_entries(self, capsys):
        """有日志条目时输出时间/级别/消息（续行缩进）并返回成功。"""
        entries = [
            LogEntry(time="2026-08-16 10:00:00,123", level="INFO", message="应用启动", body="应用启动"),
            LogEntry(
                time="2026-08-16 10:00:01,456",
                level="ERROR",
                message="读取行情失败",
                body="读取行情失败\n  堆栈行",
            ),
        ]
        with patch("src.python.core.log_reader.read_log", return_value=entries):
            code = _handle_view_logs(MagicMock(lines=100, level=None, since=None, until=None))
        out = capsys.readouterr().out
        assert code == _EXIT_SUCCESS
        assert "运行日志" in out
        assert "2026-08-16 10:00:00,123 [INFO] 应用启动" in out
        assert "2026-08-16 10:00:01,456 [ERROR] 读取行情失败" in out
        assert "    堆栈行" in out

    def test_no_match(self, capsys):
        """无匹配条目时提示并返回成功。"""
        with patch("src.python.core.log_reader.read_log", return_value=[]):
            code = _handle_view_logs(MagicMock(lines=100, level=None, since=None, until=None))
        assert code == _EXIT_SUCCESS
        assert "无匹配日志条目" in capsys.readouterr().out

    def test_value_error_severe(self, capsys):
        """read_log 抛 ValueError → 返回 _EXIT_SEVERE。"""
        with patch("src.python.core.log_reader.read_log", side_effect=ValueError("无效日志级别")):
            code = _handle_view_logs(MagicMock(lines=100, level=None, since=None, until=None))
        assert code == _EXIT_SEVERE
        assert "[ERR]" in capsys.readouterr().err

    def test_os_error_severe(self, capsys):
        """read_log 抛 OSError → 返回 _EXIT_SEVERE。"""
        with patch("src.python.core.log_reader.read_log", side_effect=OSError("IO error")):
            code = _handle_view_logs(MagicMock(lines=100, level=None, since=None, until=None))
        assert code == _EXIT_SEVERE

    def test_lines_clamped_to_min_one(self):
        """lines 负数/零被钳制为 1。"""
        with patch("src.python.core.log_reader.read_log", return_value=[]) as mock_read:
            _handle_view_logs(MagicMock(lines=-5, level=None, since=None, until=None))
        assert mock_read.call_args.kwargs["limit"] == 1


@pytest.mark.unit
class TestMainViewLogs:
    """main() view-logs 分派（config 之前）。"""

    def test_dispatches_before_init_config(self):
        """view-logs 在 init_config 之前分派，不触发配置加载。"""
        with (
            patch("src.python.cli.cli._handle_view_logs", return_value=_EXIT_SUCCESS) as mock_handle,
            patch("src.python.config.init_config") as mock_init,
            patch("src.python.config.get_config"),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(__import__("sys"), "argv", ["cli.py", "view-logs", "--level", "ERROR"]):
                code = main()

        assert code == _EXIT_SUCCESS
        mock_handle.assert_called_once()
        mock_init.assert_not_called()

    def test_passes_args_to_handler(self):
        """main 分派将解析后的 args 传给 _handle_view_logs。"""
        with (
            patch("src.python.cli.cli._handle_view_logs", return_value=_EXIT_SUCCESS) as mock_handle,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config"),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(__import__("sys"), "argv", ["cli.py", "view-logs", "--lines", "300"]):
                main()

        args = mock_handle.call_args[0][0]
        assert args.command == "view-logs"
        assert args.lines == 300


# ═══════════════════════════════════════════════════════════════
# doctor 子命令
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestArgparseDoctor:
    """doctor 子命令参数解析。"""

    def test_doctor_defaults(self):
        """doctor 默认联网 + 8s 超时。"""
        args = _build_parser().parse_args(["doctor"])
        assert args.command == "doctor"
        assert args.offline is False
        assert args.timeout == 8.0

    def test_doctor_params(self):
        """--offline / --timeout 透传。"""
        args = _build_parser().parse_args(["doctor", "--offline", "--timeout", "3.5"])
        assert args.offline is True
        assert args.timeout == 3.5


@pytest.mark.unit
class TestHandleDoctor:
    """_handle_doctor 输出与退出码。"""

    _OK = [{"group": "环境", "label": "Python 版本", "ok": True, "message": "3.12", "hint": ""}]
    _BAD = [{"group": "目录", "label": "输出目录", "ok": False, "message": "不可写", "hint": "chmod +w"}]

    def test_all_ok_returns_success(self, capsys):
        with patch("src.python.core.doctor.run_doctor_checks", return_value=self._OK):
            code = _handle_doctor(MagicMock(offline=False, timeout=8.0))

        assert code == _EXIT_SUCCESS
        assert "Python 版本" in capsys.readouterr().out

    def test_any_bad_returns_partial(self, capsys):
        """有失败项 → _EXIT_PARTIAL（命令跑完了，只是结论不佳；非 SEVERE）。"""
        with patch("src.python.core.doctor.run_doctor_checks", return_value=self._BAD):
            code = _handle_doctor(MagicMock(offline=False, timeout=8.0))

        assert code == _EXIT_PARTIAL
        assert "chmod +w" in capsys.readouterr().out

    def test_offline_skips_network(self):
        """--offline 不触发联网检查。"""
        with patch("src.python.core.doctor.run_doctor_checks", return_value=self._OK) as mock_run:
            _handle_doctor(MagicMock(offline=True, timeout=8.0))

        assert mock_run.call_args.kwargs["include_network"] is False

    def test_timeout_passthrough(self):
        with patch("src.python.core.doctor.run_doctor_checks", return_value=self._OK) as mock_run:
            _handle_doctor(MagicMock(offline=False, timeout=2.5))

        assert mock_run.call_args.kwargs["max_timeout"] == 2.5

    def test_no_color_env_plain_output(self, capsys, monkeypatch):
        """NO_COLOR 下输出不含 ANSI 转义（管道/日志场景）。"""
        monkeypatch.setenv("NO_COLOR", "1")
        with patch("src.python.core.doctor.run_doctor_checks", return_value=self._OK):
            _handle_doctor(MagicMock(offline=False, timeout=8.0))

        assert "\033[" not in capsys.readouterr().out


@pytest.mark.unit
class TestMainDoctor:
    """main() doctor 分派（config 之前，与 view-logs 同理）。"""

    def test_dispatches_before_init_config(self):
        """配置损坏正是 doctor 要诊断的场景，故不得先 init_config。"""
        with (
            patch("src.python.cli.cli._handle_doctor", return_value=_EXIT_SUCCESS) as mock_handle,
            patch("src.python.config.init_config") as mock_init,
            patch("src.python.config.get_config"),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(__import__("sys"), "argv", ["cli.py", "doctor", "--offline"]):
                code = main()

        assert code == _EXIT_SUCCESS
        mock_handle.assert_called_once()
        mock_init.assert_not_called()

    def test_passes_args_to_handler(self):
        with (
            patch("src.python.cli.cli._handle_doctor", return_value=_EXIT_SUCCESS) as mock_handle,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config"),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(__import__("sys"), "argv", ["cli.py", "doctor", "--timeout", "4"]):
                main()

        args = mock_handle.call_args[0][0]
        assert args.command == "doctor"
        assert args.timeout == 4.0


# ═══════════════════════════════════════════════════════════════
# cassettes 子命令
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestArgparseCassettes:
    """cassettes 子命令参数解析。"""

    def test_defaults_to_listing(self):
        """不带 --verify → 列表模式（不触发解析校验）。"""
        args = _build_parser().parse_args(["cassettes"])
        assert args.command == "cassettes"
        assert args.verify is False

    def test_verify_flag(self):
        args = _build_parser().parse_args(["cassettes", "--verify"])
        assert args.verify is True


@pytest.mark.unit
class TestHandleCassettes:
    """_handle_cassettes 输出与退出码。"""

    _OK_ENTRY = {
        "name": "tencent_quote",
        "path": "/x/tencent_quote.json",
        "size_bytes": 2048,
        "source": "腾讯行情",
        "recorded_at": "2026-09-10T18:38:37+08:00",
        "interactions": 1,
    }
    _BAD_ENTRY = {"name": "broken", "path": "/x/broken.json", "size_bytes": 3, "error": "cassette 不是合法 JSON"}

    def test_empty_directory_returns_success(self, capsys):
        """未录制任何 cassette：提示目录并正常退出（非错误）。"""
        with patch("src.python.core.cassette.list_cassettes", return_value=[]):
            code = _handle_cassettes(MagicMock(verify=False))

        assert code == _EXIT_SUCCESS
        assert "未找到已录制的数据源响应" in capsys.readouterr().out

    def test_listing_shows_source_and_interactions(self, capsys):
        with patch("src.python.core.cassette.list_cassettes", return_value=[self._OK_ENTRY]):
            code = _handle_cassettes(MagicMock(verify=False))

        out = capsys.readouterr().out
        assert code == _EXIT_SUCCESS
        assert "tencent_quote" in out
        assert "腾讯行情" in out
        assert "交互=1" in out

    def test_unreadable_cassette_marked_error(self, capsys):
        """损坏文件如实以 [ERR] 呈现，不静默跳过（否则「已录制」是假的）。"""
        with patch("src.python.core.cassette.list_cassettes", return_value=[self._BAD_ENTRY]):
            code = _handle_cassettes(MagicMock(verify=False))

        out = capsys.readouterr().out
        assert code == _EXIT_SUCCESS
        assert "[ERR] broken" in out
        assert "不是合法 JSON" in out

    def test_verify_all_ok_returns_success(self, capsys):
        verdicts = [{"name": "tencent_quote", "status": "ok", "detail": "", "interactions": 1}]
        with patch("src.python.core.cassette.verify_cassettes", return_value=verdicts):
            code = _handle_cassettes(MagicMock(verify=True))

        out = capsys.readouterr().out
        assert code == _EXIT_SUCCESS
        assert "[OK] tencent_quote" in out
        assert "全部录制的解析路径正常" in out

    def test_verify_any_fail_returns_severe(self, capsys):
        """有解析失败 → _EXIT_SEVERE（回放通道坏了，须重新录制）。"""
        verdicts = [{"name": "tencent_quote", "status": "fail", "detail": "KeyError: 'data'"}]
        with patch("src.python.core.cassette.verify_cassettes", return_value=verdicts):
            code = _handle_cassettes(MagicMock(verify=True))

        out = capsys.readouterr().out
        assert code == _EXIT_SEVERE
        assert "[ERR] tencent_quote" in out
        assert "1 份录制的解析路径失败" in out

    def test_verify_skipped_is_partial_marker_but_not_failure(self, capsys):
        """未登记解析器的 cassette 记 [!] 跳过，不算失败（也不伪造成 OK）。"""
        verdicts = [{"name": "future_source", "status": "skipped", "detail": "未登记解析器，仅校验文件可读"}]
        with patch("src.python.core.cassette.verify_cassettes", return_value=verdicts):
            code = _handle_cassettes(MagicMock(verify=True))

        out = capsys.readouterr().out
        assert code == _EXIT_SUCCESS
        assert "[!] future_source" in out
        assert "[OK] future_source" not in out

    def test_verify_uses_registered_parsers(self):
        """--verify 必须带上解析器登记表，否则校验退化为「只查文件可读」。"""
        from src.python.fetcher.cassette_checks import CASSETTE_CHECKS

        with patch("src.python.core.cassette.verify_cassettes", return_value=[]) as mock_verify:
            _handle_cassettes(MagicMock(verify=True))

        assert mock_verify.call_args[0][0] is CASSETTE_CHECKS


@pytest.mark.unit
class TestMainCassettes:
    """main() cassettes 分派（config 之前，只读离线维护）。"""

    def test_dispatches_before_init_config(self):
        """cassettes 不碰用户配置：损坏配置下也须可用。"""
        with (
            patch("src.python.cli.cli._handle_cassettes", return_value=_EXIT_SUCCESS) as mock_handle,
            patch("src.python.config.init_config") as mock_init,
            patch("src.python.config.get_config"),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(__import__("sys"), "argv", ["cli.py", "cassettes"]):
                code = main()

        assert code == _EXIT_SUCCESS
        mock_handle.assert_called_once()
        mock_init.assert_not_called()

    def test_passes_verify_to_handler(self):
        with (
            patch("src.python.cli.cli._handle_cassettes", return_value=_EXIT_SUCCESS) as mock_handle,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config"),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(__import__("sys"), "argv", ["cli.py", "cassettes", "--verify"]):
                main()

        args = mock_handle.call_args[0][0]
        assert args.command == "cassettes"
        assert args.verify is True
