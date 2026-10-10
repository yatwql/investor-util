"""CLI 命令行模式单元测试。

覆盖参数解析、CliProgressReporter、报告/缓存路由、退出码。

兄弟分片：test_cli_subcommands.py（view-logs / doctor / cassettes 子命令）。
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from unittest.mock import MagicMock, patch

from src.python.cli import (
    _EXIT_SEVERE,
    _EXIT_SUCCESS,
    _apply_cli_experiments,
    _apply_cli_switches,
    _build_parser,
    _cli_read_holdings,
    _cli_read_holdings_with_flows,
    _handle_cache_update,
    _handle_report,
    _handle_whatif,
    main,
    run_cli,
)
from src.python.cli._handlers import _collect_degradation_summary
from src.python.core.constants import PROJECT_ROOT
from src.python.report.whatif_operations import WhatifRunResult

pytestmark = [pytest.mark.unit, pytest.mark.unit_cli]


# ═══════════════════════════════════════════════════════════════
# argparse 参数解析
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestArgparse:
    """CLI 参数解析测试。"""

    def test_whatif_effective_date_accepts_strict_format(self):
        """--effective-date 合法 YYYY-MM-DD → 解析保留归一化值（共享层规则）。"""
        args = _build_parser().parse_args(["whatif", "--candidate", "c.xlsx", "--effective-date", "2026-07-01"])
        assert args.effective_date == "2026-07-01"

    def test_whatif_effective_date_rejects_compact_format(self):
        """--effective-date 紧凑式（20260101）→ argparse 类型错误退出 2，不再进入业务链。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["whatif", "--candidate", "c.xlsx", "--effective-date", "20260101"])
        assert exc.value.code == 2

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
        assert args.history is None  # 未显式传 --history → 由配置层 history.fetch_mode 决定
        assert args.force_llm is False

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

    def test_experiment_absent_by_default(self):
        """未指定 --experiment 时为 None（不触碰运行时开关）。"""
        args = _build_parser().parse_args(["report"])
        assert args.experiment is None

    def test_experiment_by_flag_name(self):
        """--experiment 接受开关名。"""
        args = _build_parser().parse_args(["--experiment", "decision_reflection", "report"])
        assert args.experiment == [("decision_reflection",)]

    def test_experiment_by_display_name(self):
        """--experiment 接受中文显示名（与 TUI 菜单 S 同源）。"""
        from src.python.config.features import feature_switch_registry

        _label = feature_switch_registry["decision_reflection"].label
        args = _build_parser().parse_args(["--experiment", _label, "report"])
        assert args.experiment == [("decision_reflection",)]

    def test_experiment_repeatable(self):
        """--experiment 可重复指定，逐项独立解析。"""
        args = _build_parser().parse_args(
            ["--experiment", "decision_reflection", "--experiment", "factor_catalog", "report"]
        )
        assert args.experiment == [("decision_reflection",), ("factor_catalog",)]

    def test_experiment_all(self):
        """--experiment all 展开为全部实验功能。"""
        from src.python.config.features import GROUP_EXPERIMENTAL, switches_in_group

        expected = tuple(sorted(flag for flag, _d in switches_in_group(GROUP_EXPERIMENTAL)))
        args = _build_parser().parse_args(["--experiment", "all", "report"])
        assert args.experiment == [expected]

    def test_experiment_unknown_rejected(self):
        """未知名称 → argparse 报错 SystemExit(2)，不静默忽略。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["--experiment", "no_such_feature", "report"])
        assert exc.value.code == 2

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

    def test_whatif_subcommand(self):
        """whatif 子命令：--candidate 必填、--base 可选。"""
        args = _build_parser().parse_args(["whatif", "--candidate", "after.xlsx"])
        assert args.command == "whatif"
        assert args.candidate == "after.xlsx"
        assert args.base is None

        args = _build_parser().parse_args(["whatif", "--base", "before.xlsx", "--candidate", "after.xlsx"])
        assert args.base == "before.xlsx"
        assert args.candidate == "after.xlsx"

    def test_whatif_missing_candidate(self):
        """whatif 不带 --candidate → SystemExit(2)。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["whatif"])
        assert exc.value.code == 2

    def test_whatif_effective_date_parse(self):
        """whatif --effective-date 解析。"""
        args = _build_parser().parse_args(["whatif", "--candidate", "after.xlsx", "--effective-date", "2026-07-01"])
        assert args.effective_date == "2026-07-01"

        args = _build_parser().parse_args(["whatif", "--candidate", "after.xlsx"])
        assert args.effective_date is None


@pytest.mark.unit
class TestArgparseFeatureOverrides:
    """--feature NAME=VALUE 参数解析（全注册表、双向、即时校验）。"""

    def test_feature_absent_by_default(self):
        """未指定 --feature 时为 None（不触碰运行时开关）。"""
        args = _build_parser().parse_args(["report"])
        assert args.feature is None

    def test_feature_off_on_standard_switch(self):
        """常规开关也能经 --feature 关闭——本批次补上的正是这条通道。"""
        args = _build_parser().parse_args(["--feature", "doctor_check=off", "report"])
        assert args.feature == [("doctor_check", False)]

    def test_feature_on_experimental_switch(self):
        """实验开关同样可经 --feature 打开（与 --experiment 等价路径）。"""
        args = _build_parser().parse_args(["--feature", "deterministic_signal=on", "report"])
        assert args.feature == [("deterministic_signal", True)]

    def test_feature_repeatable(self):
        """可重复指定，逐项独立解析并保留顺序。"""
        args = _build_parser().parse_args(
            ["--feature", "metrics_enabled=off", "--feature", "enable_interactive_charts=off", "report"]
        )
        assert args.feature == [("metrics_enabled", False), ("enable_interactive_charts", False)]

    def test_feature_unknown_name_rejected(self):
        """未知开关名 → SystemExit(2)（解析期报错，不留到运行时静默失效）。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["--feature", "no_such_switch=on", "report"])
        assert exc.value.code == 2

    def test_feature_bad_value_rejected(self):
        """取值不在词表内 → SystemExit(2)。"""
        with pytest.raises(SystemExit) as exc:
            _build_parser().parse_args(["--feature", "doctor_check=maybe", "report"])
        assert exc.value.code == 2


# ═══════════════════════════════════════════════════════════════
# 实验功能命令行开关
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestApplyCliExperiments:
    """_apply_cli_experiments 行为测试。"""

    def test_none_is_noop(self, monkeypatch):
        """未传 --experiment 时不改动任何开关。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "deterministic_signal", False)
        _apply_cli_experiments(None)
        assert feat.FEATURE_FLAGS["deterministic_signal"] is False

    def test_empty_groups_is_noop(self, monkeypatch):
        """空列表同样不改动开关。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "decision_reflection", False)
        _apply_cli_experiments([])
        assert feat.FEATURE_FLAGS["decision_reflection"] is False

    def test_enables_requested_flags(self, monkeypatch):
        """逐项启用命令行指定的实验功能。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "prosperity_framework", False)
        monkeypatch.setitem(feat.FEATURE_FLAGS, "decision_reflection", False)
        _apply_cli_experiments([("prosperity_framework",), ("decision_reflection",)])
        assert feat.FEATURE_FLAGS["prosperity_framework"] is True
        assert feat.FEATURE_FLAGS["decision_reflection"] is True

    def test_does_not_touch_other_flags(self, monkeypatch):
        """未指定的实验功能保持原值（不误开）。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "prosperity_framework", False)
        monkeypatch.setitem(feat.FEATURE_FLAGS, "llm_debate_conditional", False)
        _apply_cli_experiments([("prosperity_framework",)])
        assert feat.FEATURE_FLAGS["llm_debate_conditional"] is False
        assert feat.FEATURE_FLAGS["llm_debate_procon"] is False

    def test_not_persisted(self, monkeypatch):
        """命令行开关仅影响本次运行，不写 features.json。"""
        from src.python.config import features as feat

        called: list[dict] = []
        monkeypatch.setattr(feat, "save_feature_overrides", lambda *a, **k: called.append({"a": a}))
        _apply_cli_experiments([("decision_reflection",)])
        assert called == []


@pytest.mark.unit
class TestApplyCliSwitches:
    """_apply_cli_switches 行为测试（--feature 双向覆写）。"""

    def test_none_is_noop(self, monkeypatch):
        """未传 --feature 时不改动任何开关。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "doctor_check", True)
        _apply_cli_switches(None)
        assert feat.FEATURE_FLAGS["doctor_check"] is True

    def test_disables_standard_switch(self, monkeypatch):
        """关闭常规开关——本参数相对 --experiment 的核心能力。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "doctor_check", True)
        _apply_cli_switches([("doctor_check", False)])
        assert feat.FEATURE_FLAGS["doctor_check"] is False

    def test_enables_and_disables_in_one_run(self, monkeypatch):
        """同一次运行内双向覆写互不干扰。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "metrics_enabled", True)
        monkeypatch.setitem(feat.FEATURE_FLAGS, "deterministic_signal", False)
        _apply_cli_switches([("metrics_enabled", False), ("deterministic_signal", True)])
        assert feat.FEATURE_FLAGS["metrics_enabled"] is False
        assert feat.FEATURE_FLAGS["deterministic_signal"] is True

    def test_duplicate_key_last_wins(self, monkeypatch):
        """同名重复以最后一次为准（命令行从左到右覆盖）。"""
        from src.python.config import features as feat

        monkeypatch.setitem(feat.FEATURE_FLAGS, "metrics_enabled", True)
        _apply_cli_switches([("metrics_enabled", False), ("metrics_enabled", True)])
        assert feat.FEATURE_FLAGS["metrics_enabled"] is True

    def test_not_persisted(self, monkeypatch):
        """仅本次运行生效，不写 features.json（实验开关的关闭路径仍走面板/文件）。"""
        from src.python.config import features as feat

        called: list[dict] = []
        monkeypatch.setattr(feat, "save_feature_overrides", lambda *a, **k: called.append({"a": a}))
        _apply_cli_switches([("doctor_check", False)])
        assert called == []


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
        assert any("持仓文件不存在" in r.message for r in caplog.records if r.levelname == "ERROR")


@pytest.mark.unit
class TestCliReadHoldingsWithFlows:
    """_cli_read_holdings_with_flows 行为测试（含交易/分红流水页签）。"""

    def test_returns_holdings_and_flows(self):
        """有流水页签时返回 (holdings, transactions, dividends) 三元组。"""
        mock_parsed = MagicMock()
        mock_parsed.holdings = [MagicMock(), MagicMock()]
        mock_parsed.transactions = [MagicMock()]
        mock_parsed.dividends = [MagicMock()]
        with (
            patch("src.python.cli._handlers._cli_resolve_holdings_file", return_value="/tmp/h.xlsx"),
            patch("src.python.core.reader.read_holdings_with_flows", return_value=mock_parsed),
        ):
            result = _cli_read_holdings_with_flows({"holdings_dir": "/tmp", "holdings_filename": "h.xlsx"})
        assert result is not None
        holdings, transactions, dividends = result
        assert len(holdings) == 2
        assert len(transactions) == 1
        assert len(dividends) == 1

    def test_empty_flows_when_no_flow_sheets(self):
        """无流水页签时 transactions/dividends 为空列表。"""
        mock_parsed = MagicMock()
        mock_parsed.holdings = [MagicMock()]
        mock_parsed.transactions = []
        mock_parsed.dividends = []
        with (
            patch("src.python.cli._handlers._cli_resolve_holdings_file", return_value="/tmp/h.xlsx"),
            patch("src.python.core.reader.read_holdings_with_flows", return_value=mock_parsed),
        ):
            result = _cli_read_holdings_with_flows({})
        assert result is not None
        holdings, transactions, dividends = result
        assert len(holdings) == 1
        assert transactions == []
        assert dividends == []

    def test_none_when_holdings_empty(self, caplog):
        """主表为空 → 返回 None + ERROR 日志。"""
        caplog.set_level(10)
        mock_parsed = MagicMock()
        mock_parsed.holdings = []
        with (
            patch("src.python.cli._handlers._cli_resolve_holdings_file", return_value="/tmp/h.xlsx"),
            patch("src.python.core.reader.read_holdings_with_flows", return_value=mock_parsed),
        ):
            result = _cli_read_holdings_with_flows({})
        assert result is None
        assert any("持仓文件为空" in r.message for r in caplog.records if r.levelname == "ERROR")


@pytest.mark.unit
class TestHandleReport:
    """_handle_report 委托 generate_report 并透传交易/分红流水。"""

    def test_threads_transactions_and_dividends(self):
        """报告生成将持仓 + 交易/分红流水一并传给 generate_report。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0
        with (
            patch(
                "src.python.cli._handlers._cli_read_holdings_with_flows",
                return_value=([MagicMock()], [MagicMock()], [MagicMock()]),
            ),
            patch("src.python.report.cli_progress.CliProgressReporter"),
            patch("src.python.report.orchestrator.generate_report", return_value=mock_result) as mock_gen,
        ):
            args = MagicMock()
            args.type = "basic"
            args.history = "auto"
            args.force_llm = False
            args.output = None
            args.verbose = False
            code = _handle_report(args, {})
        assert code == 0
        kwargs = mock_gen.call_args[1]
        assert len(kwargs["holdings"]) == 1
        assert len(kwargs["transactions"]) == 1
        assert len(kwargs["dividends"]) == 1

    def test_none_holdings_returns_severe(self):
        """持仓读取失败 → 返回 SEVERE 且不调用 generate_report。"""
        with (
            patch("src.python.cli._handlers._cli_read_holdings_with_flows", return_value=None),
            patch("src.python.report.orchestrator.generate_report") as mock_gen,
        ):
            args = MagicMock()
            args.verbose = False
            code = _handle_report(args, {})
        assert code == _EXIT_SEVERE
        mock_gen.assert_not_called()

    def test_prints_run_resource_summary(self):
        """报告完成后调用 LLM 成本 + 缓存命中率摘要方法（无调用时各自自行静默）。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_reporter = MagicMock()
        with (
            patch(
                "src.python.cli._handlers._cli_read_holdings_with_flows",
                return_value=([MagicMock()], [], []),
            ),
            patch("src.python.report.cli_progress.CliProgressReporter", return_value=mock_reporter),
            patch("src.python.report.orchestrator.generate_report", return_value=mock_result),
        ):
            args = MagicMock()
            args.type = "basic"
            args.history = "auto"
            args.force_llm = False
            args.output = None
            args.verbose = False
            code = _handle_report(args, {})
        assert code == 0
        mock_reporter.print_llm_cost_summary.assert_called_once()
        mock_reporter.print_cache_hit_summary.assert_called_once()

    def test_notify_dispatched_on_completion(self):
        """通知门控通过 → 构造事件并分发（报告类型/退出码/结果标志透传）。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.errors = []
        mock_result.excel_ok = True
        mock_result.html_ok = False
        cfg = {"notify": {"webhook_url": "https://hooks.example.test/x", "on_success": True}}
        with (
            patch(
                "src.python.cli._handlers._cli_read_holdings_with_flows",
                return_value=([MagicMock()], [], []),
            ),
            patch("src.python.report.cli_progress.CliProgressReporter"),
            patch("src.python.report.orchestrator.generate_report", return_value=mock_result),
            patch("src.python.core.completion_notify.dispatch_completion_notification") as mock_dispatch,
        ):
            args = MagicMock()
            args.type = "both"
            args.history = "auto"
            args.force_llm = False
            args.output = None
            args.verbose = False
            code = _handle_report(args, cfg)
        assert code == 0
        mock_dispatch.assert_called_once()
        event, notify_cfg = mock_dispatch.call_args[0]
        assert event["report_type"] == "both"
        assert event["ok"] is True
        assert event["exit_code"] == 0
        assert event["artifacts"], "excel_ok=True 应列示产物路径"
        assert notify_cfg["webhook_url"] == "https://hooks.example.test/x"

    def test_notify_silent_when_unconfigured(self):
        """config 无 notify 节 → 门控前置，不触达分发（静默跳过）。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0
        with (
            patch(
                "src.python.cli._handlers._cli_read_holdings_with_flows",
                return_value=([MagicMock()], [], []),
            ),
            patch("src.python.report.cli_progress.CliProgressReporter"),
            patch("src.python.report.orchestrator.generate_report", return_value=mock_result),
            patch("src.python.core.completion_notify.dispatch_completion_notification") as mock_dispatch,
        ):
            args = MagicMock()
            args.type = "basic"
            args.history = "auto"
            args.force_llm = False
            args.output = None
            args.verbose = False
            code = _handle_report(args, {})
        assert code == 0
        mock_dispatch.assert_not_called()

    def test_notify_failure_never_changes_exit_code(self):
        """通知流程内部抛异常 → 退出码原样返回（尽力而为契约）。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0
        mock_result.errors = []
        cfg = {"notify": {"webhook_url": "https://hooks.example.test/x", "on_success": True}}
        with (
            patch(
                "src.python.cli._handlers._cli_read_holdings_with_flows",
                return_value=([MagicMock()], [], []),
            ),
            patch("src.python.report.cli_progress.CliProgressReporter"),
            patch("src.python.report.orchestrator.generate_report", return_value=mock_result),
            patch(
                "src.python.core.completion_notify.build_completion_event",
                side_effect=RuntimeError("事件构造爆炸"),
            ),
        ):
            args = MagicMock()
            args.type = "full"
            args.history = "auto"
            args.force_llm = False
            args.output = None
            args.verbose = False
            code = _handle_report(args, cfg)
        assert code == 0


class TestDegradationSummary:
    """_collect_degradation_summary：跟踪器降级事件 → 摘要行（最新在前、按源去重）。"""

    def test_dedupes_latest_first(self):
        """同源多事件只留最新一条；未降级事件不入摘要。"""
        events = [
            {"source_key": "tencent", "degraded": True, "failure_type": "timeout", "count": 1},
            {"source_key": "akshare", "degraded": True, "failure_type": "circuit", "count": 3},
            {"source_key": "tencent", "degraded": True, "failure_type": "timeout", "count": 5},
            {"source_key": "sina", "degraded": False, "failure_type": None, "count": 0},
        ]
        tracker = MagicMock()
        tracker.get_log.return_value = events
        with patch("src.python.report.data_status.get_tracker", return_value=tracker):
            lines = _collect_degradation_summary()
        assert lines == [
            "tencent: timeout（累计5次）",
            "akshare: circuit（累计3次）",
        ]

    def test_tracker_failure_returns_empty(self):
        """跟踪器异常 → 返回空列表（通知摘要非关键，不拖垮收尾）。"""
        with patch("src.python.report.data_status.get_tracker", side_effect=RuntimeError("boom")):
            assert _collect_degradation_summary() == []


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
            patch("src.python.cli._handlers._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.cache.operations.update_basic_cache", return_value=mock_result),
        ):
            code = _handle_cache_update("basic", {}, MagicMock())
        assert code == 0

    def test_update_position(self):
        """--update position 委托 update_position_cache。"""
        mock_result = MagicMock()
        mock_result.exit_code = 0

        with (
            patch("src.python.cli._handlers._cli_read_holdings", return_value=[MagicMock()]),
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
            patch("src.python.cli._handlers._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.cache.operations.update_basic_cache", return_value=mock_basic),
            patch("src.python.cache.operations.update_position_cache", return_value=mock_pos),
        ):
            code = _handle_cache_update("all", {}, MagicMock())
        assert code == 1  # max(1, 0)

    def test_holdings_none_returns_severe(self):
        """持仓为 None 时返回 _EXIT_SEVERE。"""
        with patch("src.python.cli._handlers._cli_read_holdings", return_value=None):
            code = _handle_cache_update("basic", {}, MagicMock())
        assert code == _EXIT_SEVERE


# ═══════════════════════════════════════════════════════════════
# _handle_whatif
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestHandleWhatif:
    """_handle_whatif 委托测试。"""

    def _args(self, base=None, candidate="after.xlsx"):
        return _build_parser().parse_args(["whatif", "--candidate", candidate] + (["--base", base] if base else []))

    def test_success_explicit_base(self):
        """显式 --base + --candidate → 委托共享层生成报告并返回成功。"""
        with (
            patch("src.python.core.reader.read_holdings", side_effect=[[MagicMock()], [MagicMock()]]),
            patch("src.python.report.whatif_operations.run_whatif_simulation") as mock_run,
        ):
            mock_run.return_value = WhatifRunResult(ok=True, excel="/r/调仓模拟.xlsx", html="/r/调仓模拟.html")
            code = _handle_whatif(self._args(base="before.xlsx"), {})
        assert code == _EXIT_SUCCESS
        mock_run.assert_called_once()
        from src.python.config import get_default

        assert mock_run.call_args.kwargs["base_file"] == "before.xlsx"
        assert mock_run.call_args.kwargs["output_dir"] == get_default("output_dir")

    def test_success_config_default_base(self):
        """缺省 --base → 用 config 持仓文件（_cli_read_holdings）。"""
        with (
            patch("src.python.cli._handlers._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.core.reader.read_holdings", return_value=[MagicMock()]),
            patch("src.python.report.whatif_operations.run_whatif_simulation") as mock_run,
        ):
            mock_run.return_value = WhatifRunResult(ok=True, excel="/r/e.xlsx", html="/r/e.html")
            code = _handle_whatif(self._args(), {"holdings_dir": "data/holdings", "holdings_filename": "cur.xlsx"})
        assert code == _EXIT_SUCCESS
        mock_run.assert_called_once()

    def test_base_read_failure_severe(self):
        """基准持仓读取失败 → 返回 _EXIT_SEVERE，不触发共享层。"""
        with (
            patch("src.python.cli._handlers._cli_read_holdings", return_value=None),
            patch("src.python.core.reader.read_holdings", return_value=None),
            patch("src.python.report.whatif_operations.run_whatif_simulation") as mock_run,
        ):
            code = _handle_whatif(self._args(base="before.xlsx"), {})
        assert code == _EXIT_SEVERE
        mock_run.assert_not_called()

    def test_candidate_read_failure_severe(self):
        """目标持仓读取失败 → 返回 _EXIT_SEVERE，不触发共享层。"""
        with (
            patch("src.python.cli._handlers._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.core.reader.read_holdings", return_value=None),
            patch("src.python.report.whatif_operations.run_whatif_simulation") as mock_run,
        ):
            code = _handle_whatif(self._args(), {})
        assert code == _EXIT_SEVERE
        mock_run.assert_not_called()

    def test_unavailable_data_severe(self):
        """共享层返回不可用 → 返回 _EXIT_SEVERE。"""
        with (
            patch("src.python.cli._handlers._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.core.reader.read_holdings", return_value=[MagicMock()]),
            patch("src.python.report.whatif_operations.run_whatif_simulation") as mock_run,
        ):
            mock_run.return_value = WhatifRunResult(ok=False, reason="调仓对比数据为空")
            code = _handle_whatif(self._args(), {})
        assert code == _EXIT_SEVERE
        mock_run.assert_called_once()

    def test_effective_date_passthrough(self):
        """--effective-date → 透传到 run_whatif_simulation kwargs。"""
        with (
            # 基准持仓（未传 --base）走 _cli_read_holdings，目标持仓走 read_holdings；
            # 两者都要 stub，否则会真读 data/holdings/ 而依赖开发机本地文件
            patch("src.python.cli._handlers._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.core.reader.read_holdings", side_effect=[[MagicMock()], [MagicMock()]]),
            patch("src.python.report.whatif_operations.run_whatif_simulation") as mock_run,
        ):
            mock_run.return_value = WhatifRunResult(ok=True, excel="/r/e.xlsx", html="/r/e.html")
            args = _build_parser().parse_args(["whatif", "--candidate", "after.xlsx", "--effective-date", "2026-07-01"])
            code = _handle_whatif(args, {})
        assert code == _EXIT_SUCCESS
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["effective_date"] == "2026-07-01"


# ═══════════════════════════════════════════════════════════════
# main() — 参数透传
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestMain:
    """main() 入口参数透传测试。"""

    def test_report_param_passthrough(self):
        """report 子命令参数正确透传给 _handle_report。"""
        with (
            patch("src.python.cli.cli._handle_report", return_value=_EXIT_SUCCESS) as mock_report,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config", return_value={}),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(
                __import__("sys"),
                "argv",
                ["cli.py", "report", "--type", "full", "--history", "auto", "--force-llm"],
            ):
                main()

        mock_report.assert_called_once()
        args = mock_report.call_args[0][0]
        assert args.type == "full"
        assert args.history == "auto"
        assert args.force_llm is True

    def test_cache_param_passthrough(self):
        """cache 子命令参数正确透传给 _handle_cache。"""
        with (
            patch("src.python.cli.cli._handle_cache", return_value=_EXIT_SUCCESS) as mock_cache,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config", return_value={}),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(
                __import__("sys"),
                "argv",
                ["cli.py", "cache", "--update", "all"],
            ):
                main()

        mock_cache.assert_called_once()
        args = mock_cache.call_args[0][0]
        assert args.update == "all"

    def test_whatif_param_passthrough(self):
        """whatif 子命令参数正确透传给 _handle_whatif。"""
        with (
            patch("src.python.cli.cli._handle_whatif", return_value=_EXIT_SUCCESS) as mock_whatif,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config", return_value={}),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(
                __import__("sys"),
                "argv",
                ["cli.py", "whatif", "--base", "before.xlsx", "--candidate", "after.xlsx"],
            ):
                main()

        mock_whatif.assert_called_once()
        args = mock_whatif.call_args[0][0]
        assert args.command == "whatif"
        assert args.base == "before.xlsx"
        assert args.candidate == "after.xlsx"

    def test_whatif_effective_date_param_passthrough(self):
        """whatif --effective-date → _handle_whatif 收到 args.effective_date。"""
        with (
            patch("src.python.cli.cli._handle_whatif", return_value=_EXIT_SUCCESS) as mock_whatif,
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config", return_value={}),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(
                __import__("sys"),
                "argv",
                [
                    "cli.py",
                    "whatif",
                    "--base",
                    "before.xlsx",
                    "--candidate",
                    "after.xlsx",
                    "--effective-date",
                    "2026-07-01",
                ],
            ):
                main()

        mock_whatif.assert_called_once()
        args = mock_whatif.call_args[0][0]
        assert args.effective_date == "2026-07-01"


@pytest.mark.unit
class TestMainEarlyExitExperiments:
    """早返回命令（doctor/check-sources）的命令行实验开关（早返回命令分派回归）。

    这些命令在 ``init_config()`` 之前分派，命令行 ``--experiment`` 若不随早返回
    路径一并应用，会被静默忽略——doctor 会报告「实验开关关闭」，而用户明明
    指定了该开关，据此判断实验功能状态即得到相反答案。
    """

    @staticmethod
    def _enabled_during_dispatch(argv: list[str], patch_target: str) -> dict[str, bool]:
        """跑一次 main()，返回被分派函数执行瞬间各实验开关的生效值。"""
        from src.python.config.features import (
            GROUP_EXPERIMENTAL,
            GROUP_STANDARD,
            is_feature_enabled,
            switches_in_group,
        )

        seen: dict[str, bool] = {}

        def _record(*_args, **_kwargs) -> int:
            seen.update({flag: is_feature_enabled(flag) for flag, _d in switches_in_group(GROUP_STANDARD)})
            seen.update({flag: is_feature_enabled(flag) for flag, _d in switches_in_group(GROUP_EXPERIMENTAL)})
            return _EXIT_SUCCESS

        with (
            patch(patch_target, side_effect=_record),
            patch("src.python.config.init_config"),
            patch("src.python.config.get_config"),
            patch("src.python.core.logger.setup_logger"),
        ):
            with patch.object(__import__("sys"), "argv", argv):
                main()
        return seen

    @pytest.mark.parametrize(
        ("command", "patch_target"),
        [
            ("doctor", "src.python.cli.cli._handle_doctor"),
            ("check-sources", "src.python.cli.cli._handle_check_sources"),
            ("cassettes", "src.python.cli.cli._handle_cassettes"),
        ],
    )
    def test_experiment_flag_effective_on_early_exit_command(self, command, patch_target):
        """--experiment 指定的开关在该命令分派前已生效。"""
        seen = self._enabled_during_dispatch(
            ["cli.py", "--experiment", "decision_reflection", command],
            patch_target,
        )
        assert seen["decision_reflection"] is True
        assert seen["factor_catalog"] is False  # 未指定的实验开关不受影响

    def test_without_experiment_flag_keeps_defaults(self):
        """不传开关参数 → 实验组保持默认关闭（对照组，防误判为恒真）。"""
        from src.python.config.features import GROUP_EXPERIMENTAL, switches_in_group

        seen = self._enabled_during_dispatch(["cli.py", "doctor"], "src.python.cli.cli._handle_doctor")
        experimental = [flag for flag, _d in switches_in_group(GROUP_EXPERIMENTAL)]
        assert not any(seen[flag] for flag in experimental)

    @pytest.mark.parametrize(
        ("command", "patch_target"),
        [
            ("doctor", "src.python.cli.cli._handle_doctor"),
            ("cassettes", "src.python.cli.cli._handle_cassettes"),
        ],
    )
    def test_feature_flag_effective_on_early_exit_command(self, command, patch_target):
        """--feature 在早返回命令分派前已生效（含关闭常规开关的反向取值）。"""
        seen = self._enabled_during_dispatch(
            ["cli.py", "--feature", "doctor_check=off", command],
            patch_target,
        )
        assert seen["doctor_check"] is False

    def test_feature_flag_overrides_experiment_flag(self):
        """同名时显式取值覆盖 --experiment 的隐式「只开」（后者先应用）。"""
        seen = self._enabled_during_dispatch(
            ["cli.py", "--experiment", "decision_reflection", "--feature", "decision_reflection=off", "doctor"],
            "src.python.cli.cli._handle_doctor",
        )
        assert seen["decision_reflection"] is False

    def test_features_json_overrides_loaded_before_cli_flags(self):
        """早返回路径同样先读 features.json 覆写，再叠加命令行增量。"""
        import json
        import os

        from src.python.config import features

        os.makedirs(os.path.dirname(features.FEATURES_FILE), exist_ok=True)
        with open(features.FEATURES_FILE, "w", encoding="utf-8") as f:
            json.dump({"decision_reflection": True}, f)

        seen = self._enabled_during_dispatch(["cli.py", "doctor"], "src.python.cli.cli._handle_doctor")
        assert seen["decision_reflection"] is True
        # 常规开关（默认开、非实验项）不受 --experiment 取值域影响，保持默认
        from src.python.config.features import is_feature_enabled

        assert is_feature_enabled("datasource_adapter") is True


# ═══════════════════════════════════════════════════════════════
# 进程入口与退出码传递
# ═══════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRunCli:
    """run_cli() 把 main() 的返回值/异常翻译为进程退出码。"""

    def test_propagates_return_code(self):
        """main() 返回的非零码必须向上抛 SystemExit（否则失败被吞成 0）。"""
        with (
            patch("src.python.cli.cli.main", return_value=_EXIT_SEVERE),
            patch("src.python.core.logger.log_app_boundary"),
        ):
            with pytest.raises(SystemExit) as exc:
                run_cli()

        assert exc.value.code == _EXIT_SEVERE

    def test_keyboard_interrupt_maps_to_130(self, caplog):
        """Ctrl-C → 130（shell 约定），不当作崩溃。"""
        with (
            patch("src.python.cli.cli.main", side_effect=KeyboardInterrupt),
            patch("src.python.core.logger.log_app_boundary"),
        ):
            with pytest.raises(SystemExit) as exc:
                run_cli()

        assert exc.value.code == 130

    def test_unhandled_exception_maps_to_severe(self):
        """未处理异常 → 2，且不得把 traceback 直接抛给用户。"""
        with (
            patch("src.python.cli.cli.main", side_effect=RuntimeError("boom")),
            patch("src.python.core.logger.log_app_boundary"),
        ):
            with pytest.raises(SystemExit) as exc:
                run_cli()

        assert exc.value.code == _EXIT_SEVERE

    def test_boundary_log_written_on_exit(self):
        """退出时记录应用边界（日志可追溯本次运行）。"""
        with (
            patch("src.python.cli.cli.main", return_value=_EXIT_SUCCESS),
            patch("src.python.core.logger.log_app_boundary") as mock_boundary,
        ):
            with pytest.raises(SystemExit):
                run_cli()

        assert mock_boundary.call_args[0][0] == "关闭"


@pytest.mark.unit
class TestModuleEntryPoint:
    """``python -m src.python.cli`` 必须把退出码传给 shell。

    回归：``__main__.py`` 曾只调 ``main()`` 而丢弃返回值，导致 ``scripts/cli.sh``
    / ``scripts/cli.ps1`` / cron / CI 调用的退出码恒为 0——``doctor``（部分失败=1、
    严重=2）与 ``cassettes --verify``（解析失败=2）的结论对外部不可见。
    这里用 ``runpy`` 以 ``__main__`` 身份执行该入口，并预先把 ``main`` 打桩为固定
    返回码，断言进程退出码就是它（而非恒 0）。
    """

    _PROBE = (
        "import runpy, src.python.cli.cli as cli; "
        "cli.main = lambda: 7; "
        "runpy.run_module('src.python.cli', run_name='__main__')"
    )

    def test_module_entry_propagates_exit_code(self):
        proc = subprocess.run(
            [sys.executable, "-c", self._PROBE],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

        assert proc.returncode == 7, f"退出码未传递（stdout={proc.stdout!r} stderr={proc.stderr!r})"


class TestLlmStatusLogging:
    """_show_llm_config_status_cli — 消费 llm_status 单源的日志渲染。"""

    @staticmethod
    def _records(caplog) -> str:
        from src.python.cli._handlers import _show_llm_config_status_cli

        with caplog.at_level("INFO", logger="invest"):
            _show_llm_config_status_cli()
        return "\n".join(r.getMessage() for r in caplog.records)

    def test_unconfigured(self, caplog, monkeypatch):
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: None)
        assert "状态: 未配置" in self._records(caplog)

    def test_flat_configured(self, caplog, monkeypatch):
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: {"api_key": "k", "provider": "claude"})
        text = self._records(caplog)
        assert "状态: 已配置" in text
        assert "provider=claude" in text

    def test_multi_chain(self, caplog, monkeypatch):
        monkeypatch.setattr(
            "src.python.config.get_llm_config",
            lambda: {"_provider_list": [{"name": "alpha", "provider": "claude"}]},
        )
        text = self._records(caplog)
        assert "多链服务: 1 provider" in text
        assert "alpha" in text
