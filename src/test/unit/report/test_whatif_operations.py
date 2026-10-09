"""调仓 What-if 模拟共享层单元测试。

测试 `run_whatif_simulation` 业务核心：
  - 数据可用 → build + write，返回 ok=True 与双产物路径
  - 数据不可用（两侧均空）→ 返回 ok=False 与原因，不写报告
全程 mock 计算与输出函数，避免真实文件读写与报告产物残留。

运行：
  cd <项目根目录>
  pytest src/test/unit/report/test_whatif_operations.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestRunWhatifSimulation(unittest.TestCase):
    """run_whatif_simulation 共享业务核心。"""

    def setUp(self) -> None:
        # 申购受限索引为本层新增挂载：统一兜底空索引（索引行为由独立用例覆盖），
        # 避免既有用例触发真实契约取数（测试隔离：whatif 路径 mock 契约获取）
        patcher = patch(
            "src.python.report.whatif_operations._purchase_restricted_index",
            return_value={},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("src.python.report.whatif_operations.write_whatif_report")
    @patch("src.python.report.whatif_operations.build_whatif_data")
    def test_success_outputs_both_reports(
        self,
        mock_build: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """数据可用 → build + write，返回 ok=True 与双产物路径。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        mock_build.return_value = {"available": True, "changes": []}
        mock_write.return_value = {"excel": "/r/调仓模拟.xlsx", "html": "/r/调仓模拟.html"}

        result = run_whatif_simulation(
            [MagicMock()],
            [MagicMock()],
            base_file="/x/基准.xlsx",
            candidate_file="/x/目标.xlsx",
            output_dir="reports",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.excel, "/r/调仓模拟.xlsx")
        self.assertEqual(result.html, "/r/调仓模拟.html")
        mock_write.assert_called_once()
        # build 收到 basename 展示名（与调用方传全路径解耦）
        self.assertEqual(mock_build.call_args.kwargs["base_file"], "基准.xlsx")
        self.assertEqual(mock_build.call_args.kwargs["candidate_file"], "目标.xlsx")

    @patch("src.python.report.whatif_operations.write_whatif_report")
    @patch("src.python.report.whatif_operations.build_whatif_data")
    def test_unavailable_returns_reason(
        self,
        mock_build: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """数据不可用 → 返回 ok=False 与原因，不写报告。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        mock_build.return_value = {"available": False, "reason": "调仓对比数据为空"}

        result = run_whatif_simulation(
            [],
            [],
            base_file="/x/基准.xlsx",
            candidate_file="/x/目标.xlsx",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "调仓对比数据为空")
        self.assertEqual(result.excel, "")
        self.assertEqual(result.html, "")
        mock_write.assert_not_called()

    @patch("src.python.report.whatif_operations.write_whatif_report")
    @patch("src.python.report.whatif_operations.build_whatif_data")
    def test_unavailable_without_reason_falls_back(
        self,
        mock_build: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """不可用但缺 reason 时使用默认文案。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        mock_build.return_value = {"available": False}

        result = run_whatif_simulation([], [], "/x/base.xlsx", "/x/cand.xlsx")

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "调仓对比数据不可用")
        mock_write.assert_not_called()


class TestRunWhatifSimulationBacktest(unittest.TestCase):
    """run_whatif_simulation 指定生效日时序回测集成（mock build_whatif_backtest）。"""

    def setUp(self) -> None:
        # 同 TestRunWhatifSimulation：申购受限索引统一兜底空索引（隔离契约取数）
        patcher = patch(
            "src.python.report.whatif_operations._purchase_restricted_index",
            return_value={},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("src.python.report.whatif_operations.write_whatif_report")
    @patch("src.python.report.whatif_operations.build_whatif_data")
    @patch("src.python.report.whatif_operations.build_whatif_backtest")
    def test_no_effective_date_no_backtest_call(
        self,
        mock_bt: MagicMock,
        mock_build: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """未指定生效日 → 不调用 build_whatif_backtest，data 无 backtest 键。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        mock_build.return_value = {"available": True, "changes": []}
        mock_write.return_value = {"excel": "/r/调仓模拟.xlsx", "html": "/r/调仓模拟.html"}

        run_whatif_simulation(
            [MagicMock()],
            [MagicMock()],
            base_file="/x/基准.xlsx",
            candidate_file="/x/目标.xlsx",
            output_dir="reports",
        )

        mock_bt.assert_not_called()
        written = mock_write.call_args.args[0]
        self.assertNotIn("backtest", written)

    @patch("src.python.report.whatif_operations.write_whatif_report")
    @patch("src.python.report.whatif_operations.build_whatif_data")
    @patch("src.python.report.whatif_operations.build_whatif_backtest")
    def test_effective_date_merges_backtest(
        self,
        mock_bt: MagicMock,
        mock_build: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """指定生效日 → 调用回测构建并合并进 data。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        mock_build.return_value = {"available": True, "changes": []}
        mock_bt.return_value = {"available": True, "status": "ok", "effective_date": "2026-07-01"}
        mock_write.return_value = {"excel": "/r/e.xlsx", "html": "/r/e.html"}

        result = run_whatif_simulation(
            [MagicMock()],
            [MagicMock()],
            "/x/base.xlsx",
            "/x/cand.xlsx",
            effective_date="2026-07-01",
        )

        self.assertTrue(result.ok)
        mock_bt.assert_called_once()
        self.assertEqual(mock_bt.call_args.kwargs["effective_date"], "2026-07-01")
        written = mock_write.call_args.args[0]
        self.assertEqual(written["backtest"]["status"], "ok")
        self.assertEqual(written["backtest"]["effective_date"], "2026-07-01")

    @patch("src.python.report.whatif_operations.write_whatif_report")
    @patch("src.python.report.whatif_operations.build_whatif_data")
    @patch("src.python.report.whatif_operations.build_whatif_backtest")
    def test_effective_date_exception_degrades(
        self,
        mock_bt: MagicMock,
        mock_build: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """回测异常 → 主报告仍 ok=True，backtest 降级 available=False。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        mock_build.return_value = {"available": True, "changes": []}
        mock_bt.side_effect = RuntimeError("boom")
        mock_write.return_value = {"excel": "/r/e.xlsx", "html": "/r/e.html"}

        result = run_whatif_simulation(
            [MagicMock()],
            [MagicMock()],
            "/x/base.xlsx",
            "/x/cand.xlsx",
            effective_date="2026-07-01",
        )

        self.assertTrue(result.ok)
        written = mock_write.call_args.args[0]
        self.assertFalse(written["backtest"]["available"])
        self.assertEqual(written["backtest"]["status"], "unavailable")
        self.assertIn("时序回测计算失败", written["backtest"]["reason"])

    @patch("src.python.report.whatif_operations.write_whatif_report")
    @patch("src.python.report.whatif_operations.build_whatif_data")
    @patch("src.python.report.whatif_operations.build_whatif_backtest")
    def test_effective_date_bt_none_no_key(
        self,
        mock_bt: MagicMock,
        mock_build: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """build_whatif_backtest 返回 None → 不加 backtest 键。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        mock_build.return_value = {"available": True, "changes": []}
        mock_bt.return_value = None
        mock_write.return_value = {"excel": "/r/e.xlsx", "html": "/r/e.html"}

        result = run_whatif_simulation(
            [MagicMock()],
            [MagicMock()],
            "/x/base.xlsx",
            "/x/cand.xlsx",
            effective_date="2026-07-01",
        )

        self.assertTrue(result.ok)
        written = mock_write.call_args.args[0]
        self.assertNotIn("backtest", written)


class TestNormalizeEffectiveDate(unittest.TestCase):
    """normalize_effective_date：三渠道共享的生效日格式校验（Web 400 / TUI 重问 / CLI 类型错）。"""

    def test_none_and_blank_yield_none(self):
        from src.python.report.whatif_operations import normalize_effective_date

        self.assertIsNone(normalize_effective_date(None))
        self.assertIsNone(normalize_effective_date(""))
        self.assertIsNone(normalize_effective_date("   "))

    def test_strict_format_kept_and_stripped(self):
        from src.python.report.whatif_operations import normalize_effective_date

        self.assertEqual(normalize_effective_date("2026-07-01"), "2026-07-01")
        self.assertEqual(normalize_effective_date("  2026-07-01  "), "2026-07-01")

    def test_compact_format_rejected(self):
        from src.python.report.whatif_operations import normalize_effective_date

        with self.assertRaises(ValueError):
            normalize_effective_date("20260101")

    def test_partial_and_out_of_range_rejected(self):
        from src.python.report.whatif_operations import normalize_effective_date

        for bad in ("2026-7-1", "2026-13-01", "07-01-2026", "not-a-date"):
            with self.assertRaises(ValueError):
                normalize_effective_date(bad)


if __name__ == "__main__":
    unittest.main()


class TestPurchaseRestrictedIndex(unittest.TestCase):
    """申购受限索引挂载（单点 helper：透传 / 异常兜底 / 接线存在性）。"""

    def test_helper_builds_index_via_single_mount(self):
        """helper 经缓存链契约 + 目标 codes 构索引（单点挂载，返回 build 结果）。"""
        from src.python.report import whatif_operations as wop

        contract = {"available": True, "rows": {}, "fetched_at": None}
        with (
            patch("src.python.config.get_config", return_value={}),
            patch(
                "src.python.report.orchestrator.compute_purchase_status_data",
                return_value=contract,
            ),
            patch(
                "src.python.report.purchase_status.build_restricted_index",
                return_value={"519674": {"status": "限大额"}},
            ) as m_build,
        ):
            index = wop._purchase_restricted_index([MagicMock(code="519674")])
        self.assertEqual(index, {"519674": {"status": "限大额"}})
        m_build.assert_called_once()
        self.assertIs(m_build.call_args.args[0], contract)
        self.assertEqual(m_build.call_args.args[1], ["519674"])

    def test_helper_contract_failure_degrades_to_empty(self):
        """取契约异常 → 兜底空索引（不阻断模拟；仅 Exception，不吞 BaseException）。"""
        from src.python.report import whatif_operations as wop

        with (
            patch("src.python.config.get_config", return_value={}),
            patch(
                "src.python.report.orchestrator.compute_purchase_status_data",
                side_effect=RuntimeError("boom"),
            ),
        ):
            self.assertEqual(wop._purchase_restricted_index([]), {})

    def test_restricted_index_passed_to_build(self):
        """run_whatif_simulation 把索引透传给 build_whatif_data（接线存在性）。"""
        from src.python.report.whatif_operations import run_whatif_simulation

        fake_index = {"519674": {"status": "限大额"}}
        with (
            patch(
                "src.python.report.whatif_operations._purchase_restricted_index",
                return_value=fake_index,
            ),
            patch("src.python.report.whatif_operations.build_whatif_data") as m_build,
            patch("src.python.report.whatif_operations.write_whatif_report") as m_write,
        ):
            m_build.return_value = {"available": True, "changes": []}
            m_write.return_value = {"excel": "/r/e.xlsx", "html": "/r/h.html"}
            result = run_whatif_simulation(
                [MagicMock()],
                [MagicMock()],
                base_file="/x/基准.xlsx",
                candidate_file="/x/目标.xlsx",
                output_dir="reports",
            )
        self.assertTrue(result.ok)
        self.assertIs(m_build.call_args.kwargs["restricted_index"], fake_index)


class TestCostPanelSwitch(unittest.TestCase):
    """whatif_trade_cost 开关接线：开 → cost 键挂载；关 → 键缺席；装配异常 → 降级。"""

    def _run(self, enabled: bool, *, panel_return=None, panel_side_effect=None):
        from src.python.report.whatif_operations import run_whatif_simulation

        with (
            patch(
                "src.python.report.whatif_operations._purchase_restricted_index",
                return_value={},
            ),
            patch(
                "src.python.report.whatif_operations.build_whatif_data",
                return_value={"available": True, "changes": []},
            ),
            patch(
                "src.python.report.whatif_operations.is_feature_enabled",
                return_value=enabled,
            ) as m_feat,
            patch(
                "src.python.report.whatif_operations.build_whatif_cost_panel",
                return_value=panel_return or {"available": True},
            ) as m_panel,
            patch(
                "src.python.report.whatif_operations.write_whatif_report",
                return_value={"excel": "/r/e.xlsx", "html": "/r/h.html"},
            ) as m_write,
        ):
            if panel_side_effect is not None:
                m_panel.side_effect = panel_side_effect
            result = run_whatif_simulation(
                [MagicMock()],
                [MagicMock()],
                base_file="/x/基准.xlsx",
                candidate_file="/x/目标.xlsx",
                output_dir="reports",
            )
        return result, m_feat, m_panel, m_write.call_args.args[0]

    def test_switch_on_attaches_cost(self):
        """开关开 → is_feature_enabled 读取该开关，面板结果挂载为 cost 键。"""
        result, m_feat, m_panel, data = self._run(True, panel_return={"available": True, "trade_cost": {}})
        self.assertTrue(result.ok)
        m_feat.assert_called_once_with("whatif_trade_cost")
        m_panel.assert_called_once()
        self.assertIn("cost", data)
        self.assertEqual(data["cost"]["trade_cost"], {})

    def test_switch_off_cost_key_absent(self):
        """开关关（出厂默认）→ 面板不调用、cost 键缺席，数据与开态前完全一致。"""
        result, m_feat, m_panel, data = self._run(False)
        self.assertTrue(result.ok)
        m_feat.assert_called_once_with("whatif_trade_cost")
        m_panel.assert_not_called()
        self.assertNotIn("cost", data)
        self.assertEqual(data, {"available": True, "changes": []})

    def test_panel_exception_degrades_to_absent(self):
        """面板装配抛异常 → 降级缺席（cost 键不出现），模拟照常成功。"""
        result, _, _, data = self._run(True, panel_side_effect=RuntimeError("boom"))
        self.assertTrue(result.ok)
        self.assertNotIn("cost", data)


# ── 开关注册表 ───────────────────────────────────────────


class TestCostPanelSwitchRegistry:
    """whatif_trade_cost 已登记于报告章节与增强组（页签类转正）、默认关、影响报告。"""

    def test_switch_registered_in_report_group_off_by_default(self):
        """分组/默认值/产物影响随注册表声明（结构关系断言，不写死分组计数）。"""
        from src.python.config.features import feature_switch_registry, is_feature_enabled

        sw = feature_switch_registry["whatif_trade_cost"]
        assert sw.label == "What-if 交易成本对比"
        assert sw.group == "report"
        assert sw.default is False
        assert sw.affects_report is True
        assert is_feature_enabled("whatif_trade_cost") is False
