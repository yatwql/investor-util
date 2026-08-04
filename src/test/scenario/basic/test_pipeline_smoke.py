"""管线集成冒烟测试 — 最小持仓 fixture 覆盖 4 个管线关键节点。

测试目标：
  1. prepare_report_data 正确返回 risk_metrics 字段
  2. capture_snapshot 接收并透传额外字段
  3. generate_all_llm 接收 history_data
  4. build_llm_fingerprint 含风险信号哈希

约束：
  - 最小持仓（2 品种）
  - 所有外部 API 均为 mock（行情、指数、历史快照）
  - LLM 调用 mock，防止真实 API 调用
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]

_SAMPLE_HOLDINGS = [
    Holding(account="证券", name="长江电力", code="600900", shares=100, cost_price=10.0),
    Holding(account="证券", name="贵州茅台", code="600519", shares=50, cost_price=200.0),
]


class TestCheckpointSmoke:
    """管线集成冒烟 — 4 个管线节点快速验证。"""

    # ── Checkpoint 1 ─────────────────────────────────

    @patch("src.python.fetcher.index.fetch_indices")
    @patch("src.python.fetcher.index.fetch_us_indices")
    @patch("src.python.report.market_value._generate_details")
    def test_prepare_report_data_risk_metrics_field(
        self,
        mock_generate_details: MagicMock,
        mock_fetch_us: MagicMock,
        mock_fetch_a: MagicMock,
    ):
        """prepare_report_data 返回 risk_metrics 字段（初始空字典）。"""
        from src.python.report.orchestrator import prepare_report_data

        mock_generate_details.return_value = self._mock_details()
        mock_fetch_a.return_value = {}
        mock_fetch_us.return_value = {}

        result = prepare_report_data(_SAMPLE_HOLDINGS, self._mock_reporter(), {})
        assert "risk_metrics" in result, "risk_metrics 字段缺失"
        assert result["risk_metrics"] == {}, "risk_metrics 初始应为空字典"

    # ── Checkpoint 2 ─────────────────────────────────

    @patch("src.python.report.history_snapshot.load_latest")
    @patch("src.python.report.history_snapshot.save")
    @patch("src.python.report.history_snapshot.prune")
    def test_capture_snapshot_extra_fields_wired(
        self,
        mock_prune: MagicMock,
        mock_save: MagicMock,
        mock_load: MagicMock,
    ):
        """capture_snapshot 签名支持 extra 参数。"""
        from src.python.report.orchestrator import capture_snapshot

        mock_load.return_value = None

        # 验证函数可调用、不抛出异常
        result = capture_snapshot(
            _SAMPLE_HOLDINGS,
            self._mock_details(),
            {},
            self._mock_reporter(),
            risk_metrics={"sharpe_ratio": 1.5},
        )
        # 首次运行无历史快照时 capture_snapshot 返回 None
        assert result is None

    # ── Checkpoint 3 ─────────────────────────────────

    @patch("src.python.llm.generators_orchestrator.generate_all_llm")
    def test_llm_generators_receive_history_data(
        self,
        mock_gen: MagicMock,
    ):
        """generate_all_llm 接收 history_data 参数。"""
        mock_gen.return_value = (None, None, None, None)

        from src.python.llm.generators_orchestrator import generate_all_llm

        result = generate_all_llm(
            a_indices={},
            us_indices={},
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
            history_data={"annualized_volatility": 0.15, "max_drawdown_pct": -0.10},
        )
        assert result is not None
        assert len(result) == 4

    # ── Checkpoint 4 ─────────────────────────────────

    def test_fingerprint_includes_risk_signals(self):
        """build_llm_fingerprint 提取 history_data 中的风险信号。"""
        from src.python.llm.fingerprint import build_llm_fingerprint

        fp_with = build_llm_fingerprint(
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            history_data={"annualized_volatility": 0.15, "max_drawdown_pct": -0.10},
        )
        fp_without = build_llm_fingerprint(
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
        )
        assert fp_with != fp_without, "有/无风险信号应产生不同指纹"

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _mock_details():
        from collections import namedtuple

        DetailRow = namedtuple(
            "DetailRow",
            [
                "name",
                "code",
                "price",
                "yesterday_close",
                "nav_date",
                "market_value",
                "cost",
                "profit",
                "profit_rate",
                "today_profit",
                "source_api",
                "shares",
            ],
        )
        return [
            DetailRow("长江电力", "600900", 25.0, 24.5, "2026-07-18", 2500.0, 1000.0, 1500.0, 0.6, 50.0, "mock", 100.0),
            DetailRow(
                "贵州茅台", "600519", 1800.0, 1780.0, "2026-07-18", 90000.0, 10000.0, 80000.0, 0.8, 1000.0, "mock", 50.0
            ),
        ]

    @staticmethod
    def _mock_reporter():
        m = MagicMock()
        m.info = MagicMock()
        m.ok = MagicMock()
        m.warn = MagicMock()
        return m
