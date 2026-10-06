"""持仓源守卫 —— 非正式持仓源不写入真实快照历史（快照防污染）。

场景回归：demo/试算/临时持仓（路径不在 ``data/holdings/`` 正式目录下）经报告
管线 ``capture_snapshot`` 曾把幻影持仓写进用户真实快照历史，导致持仓变动复盘
把未持有品种报成清仓。守卫口径：共享主目录（namespace=None）只接受正式持仓源，
非正式源不落盘、不与真实历史比对（下游历史章随 pipeline_data 缺席同首次运行
口径隐藏）；命名空间域（web 试算）域内闭环，不受守卫限制。

覆盖：
  - 正式源判定：默认配置/显式正式目录 → 正式
  - 非正式源判定：外部 demo 目录 / 上传暂存区 → 非正式
  - capture 对非正式源：save/load_latest/prune 零调用、返回 None、reporter 提示
  - capture 对正式源：环比/落盘/清理行为与守卫引入前一致（首轮 + 二次运行）
  - 命名空间域绕过守卫（web 试算域照常域内闭环）

测试隔离：全 mock（save/load_latest/prune 打在 history_snapshot 模块上），
不读写真实快照目录、不触网。
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.python.core.constants import PROJECT_ROOT

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _detail(code="SH600001", name="测试", mv=1200.0, cost=1000.0, profit=200.0):
    d = MagicMock()
    d.code = code
    d.name = name
    d.market_value = mv
    d.cost = cost
    d.profit = profit
    return d


def _holding(code="SH600001", name="测试", shares=100, cost_price=10.0):
    h = MagicMock()
    h.code = code
    h.name = name
    h.shares = shares
    h.cost_price = cost_price
    return h


def _old_snapshot():
    from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

    return SnapshotData(
        accounts=(
            AccountSnapshot(
                account_name="全部",
                holdings=(
                    SnapshotHolding(
                        code="SH600001",
                        name="测试",
                        shares=100,
                        cost_price=10.0,
                        market_value=900.0,
                        total_pnl=0.0,
                        cost_total=900.0,
                    ),
                ),
            ),
        ),
        total_value=900.0,
        total_cost=900.0,
        total_pnl=0.0,
        timestamp="20260806T090000",
    )


class TestFormalHoldingsSourceJudge:
    """正式持仓源判定（config.is_formal_holdings_source）。"""

    def test_default_config_is_formal(self):
        """空配置回退默认持仓目录（data/holdings/）→ 正式源。"""
        from src.python.config import is_formal_holdings_source

        assert is_formal_holdings_source({}) is True

    def test_explicit_formal_dir_is_formal(self):
        """显式指向正式持仓目录 → 正式源。"""
        from src.python.config import is_formal_holdings_source

        config = {
            "holdings_dir": os.path.join(PROJECT_ROOT, "data", "holdings"),
            "holdings_filename": "持仓.xlsx",
        }
        assert is_formal_holdings_source(config) is True

    def test_external_demo_dir_is_not_formal(self):
        """外部 demo 目录（/tmp/demo/holdings）→ 非正式源（污染场景口径）。"""
        from src.python.config import is_formal_holdings_source

        config = {"holdings_dir": "/tmp/demo/holdings", "holdings_filename": "示例持仓.xlsx"}
        assert is_formal_holdings_source(config) is False

    def test_upload_staging_dir_is_not_formal(self):
        """上传暂存区（data/holdings/uploads/）→ 非正式源（外部上传内容）。"""
        from src.python.config import is_formal_holdings_source

        config = {
            "holdings_dir": os.path.join(PROJECT_ROOT, "data", "holdings", "uploads"),
            "holdings_filename": "持仓.xlsx",
        }
        assert is_formal_holdings_source(config) is False


class TestCaptureSnapshotSourceGuard:
    """capture_snapshot 对持仓源的门控行为。"""

    def test_non_formal_source_skips_entire_capture(self):
        """非正式源（namespace=None）：save/load_latest/prune 零调用、返回 None。"""
        from src.python.report._snapshot import capture_snapshot

        config = {
            "holdings_dir": "/tmp/demo/holdings",
            "holdings_filename": "示例持仓.xlsx",
            "history": {"snapshot_retention_days": 60, "snapshot_max_count": 365},
        }
        reporter = MagicMock()
        with (
            patch("src.python.report.history_snapshot.save") as mock_save,
            patch("src.python.report.history_snapshot.load_latest") as mock_load,
            patch("src.python.report.history_snapshot.prune") as mock_prune,
        ):
            result = capture_snapshot([_holding()], [_detail()], config, reporter)
        assert result is None, "非正式源不得产出环比数据（同首次运行口径）"
        mock_save.assert_not_called()
        mock_load.assert_not_called()
        mock_prune.assert_not_called()
        assert reporter.info.call_count == 1
        assert "正式持仓目录" in reporter.info.call_args.args[0]

    def test_formal_source_capture_unchanged(self):
        """正式源首轮：load/save/prune 照常（守卫零行为变化）。"""
        from src.python.report._snapshot import capture_snapshot

        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}
        reporter = MagicMock()
        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None) as mock_load,
            patch("src.python.report.history_snapshot.save") as mock_save,
            patch("src.python.report.history_snapshot.prune") as mock_prune,
        ):
            result = capture_snapshot([_holding()], [_detail()], config, reporter)
        mock_load.assert_called_once_with(None)
        mock_save.assert_called_once()
        mock_prune.assert_called_once()
        assert mock_save.call_args.args[1] is None, "正式源默认写共享主目录"
        assert result is None, "首轮（无历史快照）按首次运行口径返回 None"

    def test_formal_source_second_run_returns_diff(self):
        """正式源二次运行：load_latest 参与环比，pipeline_data 携带 diff。"""
        from src.python.report._snapshot import capture_snapshot

        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}
        reporter = MagicMock()
        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=_old_snapshot()),
            patch("src.python.report.history_snapshot.save") as mock_save,
            patch("src.python.report.history_snapshot.prune"),
        ):
            result = capture_snapshot([_holding()], [_detail(mv=1200.0)], config, reporter)
        assert result is not None
        assert result["diff"]["is_first_check"] is False
        assert result["diff"]["total_value_diff"] == 300.0
        mock_save.assert_called_once()

    def test_namespace_domain_not_restricted(self):
        """命名空间域（web 试算）不受守卫限制：非正式源照常域内闭环。"""
        from src.python.report._snapshot import capture_snapshot

        config = {
            "holdings_dir": "/tmp/demo/holdings",
            "holdings_filename": "示例持仓.xlsx",
            "history": {"snapshot_retention_days": 60, "snapshot_max_count": 365},
        }
        reporter = MagicMock()
        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None),
            patch("src.python.report.history_snapshot.save") as mock_save,
            patch("src.python.report.history_snapshot.prune") as mock_prune,
        ):
            capture_snapshot([_holding()], [_detail()], config, reporter, snapshot_namespace="web")
        mock_save.assert_called_once()
        assert mock_save.call_args.args[1] == "web"
        assert mock_prune.call_args.kwargs.get("namespace") == "web"
