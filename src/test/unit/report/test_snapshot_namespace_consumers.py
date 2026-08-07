"""快照命名空间消费层测试 — capture_snapshot / 组合演进 / 快照差异。

覆盖：
  - capture_snapshot(snapshot_namespace="web")：load_latest/save/prune 均在
    web 域内闭环，主目录零新增（T3）
  - build_evolution_data(snapshot_namespace="web")：只聚合 web/ 快照（T4）
  - build_snapshot_diff(snapshot_namespace="web")：只对比 web/ 快照（T4）
  - 反污染：共享 load_all() 不含 web/ 快照；web 域演进不读共享时间线（T10 基础）

测试隔离：conftest `_isolate_sensitive_paths` 已将 HISTORY_SNAPSHOT_DIR
重定向到 tmp_path，web/ 是其下子目录，天然隔离。
"""

from __future__ import annotations

import os

import pytest
from unittest.mock import MagicMock, patch

from src.python.analysis.portfolio_evolution import build_evolution_data
from src.python.analysis.snapshot_diff import build_snapshot_diff
from src.python.report import history_snapshot as hs
from src.python.report._snapshot import capture_snapshot
from src.python.report.orchestrator import generate_report
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _holding(code: str, name: str, mv: float, cost: float) -> SnapshotHolding:
    return SnapshotHolding(
        code=code,
        name=name,
        shares=0.0,
        cost_price=0.0,
        market_value=mv,
        daily_pnl=0.0,
        total_pnl=0.0,
        cost_total=cost,
    )


def _save(ts: str, holdings: list[SnapshotHolding], namespace: str | None = None) -> str:
    sd = SnapshotData(
        accounts=(AccountSnapshot(account_name="全部", holdings=tuple(holdings)),),
        total_value=sum(h.market_value for h in holdings),
        total_cost=sum(h.cost_total for h in holdings),
        total_pnl=0.0,
        timestamp=ts,
    )
    return hs.save(sd, namespace)


# ── capture_snapshot namespace 闭环 ─────────────────────────


class TestCaptureSnapshotNamespace:
    """capture_snapshot(snapshot_namespace="web") 域内闭环。"""

    def _make_detail(self, code="SH600001", name="测试", mv=1200.0, cost=1000.0, profit=200.0) -> MagicMock:
        d = MagicMock()
        d.code = code
        d.name = name
        d.market_value = mv
        d.cost = cost
        d.profit = profit
        return d

    def _make_holding(self, code="SH600001", name="测试", shares=100, cost_price=10.0) -> MagicMock:
        h = MagicMock()
        h.code = code
        h.name = name
        h.shares = shares
        h.cost_price = cost_price
        return h

    def test_capture_snapshot_namespace_closed_loop(self):
        """capture_snapshot(namespace="web") → load_latest 基于 web 域上一份，主目录零新增。"""
        reporter = MagicMock()
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}
        # 先在 web 域预置一份旧快照（模拟此前试算）
        _save("20260806T090000", [_holding("w", "W", 900.0, 800.0)], "web")
        r = capture_snapshot(
            [self._make_holding()],
            [self._make_detail(mv=1200.0)],
            config,
            reporter,
            snapshot_namespace="web",
        )
        assert r is not None
        assert r["diff"]["is_first_check"] is False
        # 环比基于 web 域上一份（1200 - 900）
        assert r["diff"]["total_value_diff"] == 300.0
        # 主目录零新增（反污染）
        assert len(hs.load_all()) == 0
        # web 域 2 份（预置 + 本次）
        assert len(hs.load_all("web")) == 2

    def test_capture_snapshot_default_still_main_dir(self):
        """不传 namespace → 默认写主目录（向后兼容）。"""
        reporter = MagicMock()
        config = {"history": {"snapshot_retention_days": 60, "snapshot_max_count": 365}}
        capture_snapshot(
            [self._make_holding()],
            [self._make_detail(mv=1000.0)],
            config,
            reporter,
        )
        assert len(hs.load_all()) == 1
        assert len(hs.load_all("web")) == 0

    def test_capture_snapshot_prune_namespace_passed(self):
        """prune 收到 namespace="web"（域内清理）。"""
        reporter = MagicMock()
        config = {"history": {"snapshot_retention_days": 99, "snapshot_max_count": 200}}
        with (
            patch("src.python.report.history_snapshot.load_latest", return_value=None),
            patch("src.python.report.history_snapshot.save"),
            patch("src.python.fetcher.history_diff.HistoryDiff") as mock_hd,
            patch("src.python.report.history_snapshot.prune") as mock_prune,
        ):
            mock_hd.compute.return_value = MagicMock(is_first_check=True)
            capture_snapshot(
                [self._make_holding()],
                [self._make_detail()],
                config,
                reporter,
                snapshot_namespace="web",
            )
        mock_prune.assert_called_once_with(retention_days=99, max_count=200, namespace="web")


# ── 演进 / 差异 namespace 隔离 ──────────────────────────────


def test_evolution_namespace_only_web():
    """build_evolution_data(snapshot_namespace="web") 只聚合 web/ 快照。"""
    _save("20260701T090000", [_holding("a", "A", 100, 90)])
    _save("20260701T090000", [_holding("w1", "W1", 10, 9)], "web")
    _save("20260702T090000", [_holding("w1", "W1", 20, 9)], "web")
    _save("20260703T090000", [_holding("w1", "W1", 30, 9)], "web")
    # web 域 3 期 → available
    web_ev = build_evolution_data(snapshot_namespace="web")
    assert web_ev["available"] is True
    assert web_ev["snapshot_count"] == 3
    # 默认域只有 1 期 → 不足（反污染：共享演进不含 web/）
    main_ev = build_evolution_data()
    assert main_ev["available"] is False
    assert main_ev["snapshot_count"] == 1


def test_snapshot_diff_namespace_only_web():
    """build_snapshot_diff(snapshot_namespace="web") 只对比 web/ 快照。"""
    _save("20260701T090000", [_holding("a", "A", 100, 90)])
    _save("20260701T090000", [_holding("w1", "W1", 10, 9)], "web")
    _save("20260702T090000", [_holding("w1", "W1", 20, 9)], "web")
    # web 域 2 期 → available
    web_diff = build_snapshot_diff(snapshot_namespace="web")
    assert web_diff["available"] is True
    assert web_diff["snapshot_count"] == 2
    # 默认域只有 1 期 → 不足（共享差异不含 web/）
    main_diff = build_snapshot_diff()
    assert main_diff["available"] is False
    assert main_diff["snapshot_count"] == 1


def test_shared_evolution_excludes_web_namespace():
    """共享演进排除 web/ 快照（共享时间线不被试算域污染）。"""
    for i in range(3):
        _save(f"2026070{i + 1}T090000", [_holding("m", "M", 100, 90)])
    for i in range(3):
        _save(f"2026070{i + 1}T090000", [_holding("w", "W", 50, 40)], "web")
    main_ev = build_evolution_data()
    assert main_ev["available"] is True
    assert main_ev["snapshot_count"] == 3
    # web 域独立
    web_ev = build_evolution_data(snapshot_namespace="web")
    assert web_ev["snapshot_count"] == 3
    # 主目录无 web 子目录快照
    assert "web" not in os.listdir(hs.HISTORY_SNAPSHOT_DIR) or not any(
        f.startswith("snapshot_") for f in os.listdir(hs.HISTORY_SNAPSHOT_DIR)
    ) or len(hs.load_all()) == 3


# ── 编排层 generate_report 透传 ────────────────────────────


class TestGenerateReportNamespace:
    """generate_report(snapshot_namespace) → both/full 路径透传到 capture_snapshot。"""

    def _both_run(self, **kwargs):
        """运行 both 路径（最小 mock 集），返回 (capture_snapshot_mock, result)。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {"output_dir": "reports"}

        with (
            patch("src.python.report.market_value._generate_details", return_value=[MagicMock()]),
            patch("src.python.report._snapshot.capture_snapshot") as mock_cap,
            patch("src.python.report._snapshot.fetch_history_data"),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order"),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch(
                "src.python.core.data_freshness.build_freshness_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.core.holding_status.build_coverage_summary",
                return_value={"available": True, "items": [], "abnormal_count": 0, "summary": ""},
            ),
            patch(
                "src.python.analysis.action_advisor.build_action_data",
                return_value={"available": True, "summary": "", "rebalance_signals": []},
            ),
        ):
            mock_cap.return_value = {"diff": {}}
            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="both",
                fetch_history=True,
                **kwargs,
            )
        return mock_cap, result

    def test_generate_report_both_passes_namespace(self):
        """generate_report(snapshot_namespace="web") both → capture_snapshot 收到 web 域。"""
        mock_cap, result = self._both_run(snapshot_namespace="web")
        assert result.report_generated is True
        mock_cap.assert_called_once()
        assert mock_cap.call_args.kwargs.get("snapshot_namespace") == "web"

    def test_generate_report_both_default_namespace_none(self):
        """不传 snapshot_namespace → both 路径默认 None（共享主目录，向后兼容）。"""
        mock_cap, result = self._both_run()
        assert result.report_generated is True
        mock_cap.assert_called_once()
        assert mock_cap.call_args.kwargs.get("snapshot_namespace") is None

    def test_generate_report_full_passes_namespace(self):
        """generate_report(snapshot_namespace="web") full → capture_snapshot 收到 web 域。"""
        mock_reporter = MagicMock()
        mock_holdings = [MagicMock(code="SH600001", name="测试", shares=100, cost_price=10.0)]
        config = {"output_dir": "reports", "news_top_count": 100, "history": {"fetch_mode": "auto"}}

        with (
            patch("src.python.report.orchestrator.prepare_report_data") as mock_prep,
            patch("src.python.report._snapshot.capture_snapshot") as mock_cap,
            patch("src.python.report._snapshot.fetch_history_data"),
            patch(
                "src.python.report._llm_news._fetch_llm_and_news",
                return_value=(["llm"] * 4, [], None, True, None),
            ),
            patch("src.python.report.html_writer.write_html_report"),
            patch("src.python.report.excel_generator.generate_excel_report"),
            patch("src.python.core.registry.get_report_section_order", return_value=[]),
            patch("src.python.providers.akshare_extras.get_sector_fund_flow", return_value=[]),
            patch("src.python.config.is_enable_fund_deep_analysis", return_value=True),
            patch("src.python.config.is_enable_news", return_value=True),
            patch("src.python.config.is_enable_history", return_value=True),
            patch("src.python.config.is_enable_llm", return_value=True),
            patch("src.python.llm.fallback.build_fallback_llm_content"),
        ):
            mock_cap.return_value = {"diff": {}}
            mock_prep.return_value = {
                "details": [],
                "total_mv": 0,
                "total_cost": 0,
                "total_profit": 0,
                "total_today_profit": 0,
                "categories": [],
                "a_indices": {},
                "us_indices": {},
                "penetrated_assets": [],
                "holdings_details": [],
                "today_str": "2026-07-16",
                "output_dir": "reports",
                "news_top_count": 100,
                "style_factor_data": None,
                "position_relationship_data": None,
                "position_status": None,
                "data_freshness": None,
                "action_data": None,
                "valuation_data": None,
                "market_temperature_data": None,
            }
            result = generate_report(
                holdings=mock_holdings,
                config=config,
                reporter=mock_reporter,
                report_type="full",
                fetch_history=True,
                force_llm=False,
                snapshot_namespace="web",
            )

        assert result.report_generated is True
        mock_cap.assert_called_once()
        assert mock_cap.call_args.kwargs.get("snapshot_namespace") == "web"
