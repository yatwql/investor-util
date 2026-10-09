"""阶段 ETA 预估单元测试（core/perf.py）。

测试目标：
  - estimate_stage_eta：同阶段中位数口径、历史不足 → None、异常静默降级
  - stage_status / format_stage_status：状态采集与唯一格式化点
  - stage_announcer：阶段开始广播、回调异常不影响计时

运行：
  pytest src/test/unit/core/test_perf_stage_eta.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.python.core.perf import (
    PerfCollector,
    estimate_stage_eta,
    format_stage_status,
)
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


def _record(report_type: str, phases: dict) -> dict:
    """构造一条 perf_history 历史记录（与 ReportRunSnapshot.to_json 同形状）。"""
    return {
        "version": "0.0.0",
        "timestamp": "2026-10-07T00:00:00",
        "report_type": report_type,
        "holdings_count": 1,
        "phases": phases,
        "total_seconds": sum(phases.values()),
        "errors": [],
        "warnings_count": 0,
    }


class TestEstimateStageEta(unittest.TestCase):
    """estimate_stage_eta — 同阶段中位数减已耗时。"""

    def test_median_based_remaining(self) -> None:
        """剩余 = 同阶段中位数 − 已耗时。"""
        history = [_record("full", {"LLM+新闻": s}) for s in (80.0, 100.0, 120.0)]
        eta = estimate_stage_eta("LLM+新闻", 40.0, history=history, report_type="full")
        self.assertEqual(eta, 60.0)  # median 100.0 − 40.0

    def test_empty_history_returns_none(self) -> None:
        """历史为空（首次运行/文件缺失）→ None（历史不足）。"""
        self.assertIsNone(estimate_stage_eta("行情获取", 1.0, history=[]))

    def test_missing_phase_returns_none(self) -> None:
        """历史中无同名阶段 → None。"""
        history = [_record("full", {"数据准备": 5.0})]
        self.assertIsNone(estimate_stage_eta("行业资金流向", 1.0, history=history))

    def test_report_type_mismatch_returns_none(self) -> None:
        """限定报告类型但样本类型不匹配 → None。"""
        history = [_record("both", {"Excel 生成": 30.0})]
        self.assertIsNone(estimate_stage_eta("Excel 生成", 1.0, history=history, report_type="full"))

    def test_elapsed_beyond_median_clamps_to_zero(self) -> None:
        """已耗时超过中位数 → 0.0（下限，不返回负数）。"""
        history = [_record("full", {"快照对比": 10.0})]
        eta = estimate_stage_eta("快照对比", 99.0, history=history, report_type="full")
        self.assertEqual(eta, 0.0)

    def test_negative_sample_ignored(self) -> None:
        """负数耗时样本不计入（无有效样本 → None）。"""
        history = [_record("full", {"阶段X": -5.0})]
        self.assertIsNone(estimate_stage_eta("阶段X", 0.0, history=history))

    def test_list_shape_phases_compat(self) -> None:
        """早期 list 形状 phases（[{name, seconds}]）同样可取样本。"""
        rec = _record("full", {"阶段Y": 42.0})
        rec["phases"] = [{"name": "阶段Y", "seconds": 42.0}]
        eta = estimate_stage_eta("阶段Y", 2.0, history=[rec], report_type="full")
        self.assertEqual(eta, 40.0)

    def test_lookback_window_excludes_older_runs(self) -> None:
        """仅取最近 N 次运行：目标阶段只出现在窗口外的历史 → None。"""
        phase_only_in_old = [_record("full", {"阶段旧": 50.0}) for _ in range(5)]
        recent = [_record("full", {"其他阶段": 1.0}) for _ in range(20)]
        history = phase_only_in_old + recent
        self.assertIsNone(estimate_stage_eta("阶段旧", 0.0, history=history))

    def test_load_failure_returns_none(self) -> None:
        """读取历史文件异常 → 静默返回 None（计算失败降级为无 ETA）。"""
        with patch("src.python.core.perf.load_history", side_effect=OSError("磁盘故障")):
            self.assertIsNone(estimate_stage_eta("行情获取", 3.0))


class TestStageStatus(unittest.TestCase):
    """stage_status — 活跃阶段状态采集。"""

    def test_none_when_idle(self) -> None:
        """无活跃阶段 → None。"""
        perf = PerfCollector(report_type="both", holdings=[])
        self.assertIsNone(perf.stage_status())

    def test_returns_phase_and_elapsed_after_start(self) -> None:
        """start 后返回阶段名与非负已耗时；stop 后回到 None。"""
        perf = PerfCollector(report_type="both", holdings=[])
        perf.start("行情获取")
        status = perf.stage_status()
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status["phase"], "行情获取")
        self.assertGreaterEqual(status["elapsed"], 0.0)
        perf.stop()
        self.assertIsNone(perf.stage_status())

    def test_report_type_property(self) -> None:
        """report_type 暴露构造时的报告类型（供 ETA 按类型筛样本）。"""
        perf = PerfCollector(report_type="full", holdings=[])
        self.assertEqual(perf.report_type, "full")


class TestFormatStageStatus(unittest.TestCase):
    """format_stage_status — 所有进度通道共用的唯一格式化点。"""

    def test_with_eta(self) -> None:
        """ETA 可得 → 已耗时 + 预计剩余。"""
        line = format_stage_status({"phase": "LLM+新闻", "elapsed": 12.0}, 284.4)
        self.assertEqual(line, "「LLM+新闻」· 已耗时 12s · 预计剩余 ~284s")

    def test_without_eta_only_elapsed(self) -> None:
        """ETA 不可得（历史不足）→ 仅已耗时。"""
        line = format_stage_status({"phase": "行情获取", "elapsed": 5.0}, None)
        self.assertEqual(line, "「行情获取」· 已耗时 5s")
        self.assertNotIn("预计剩余", line)


class TestStageAnnouncer(unittest.TestCase):
    """stage_announcer — 阶段开始广播与故障隔离。"""

    def test_announcer_called_on_start(self) -> None:
        """start 后回调收到收集器自身一次。"""
        seen: list[object] = []
        perf = PerfCollector(report_type="both", holdings=[], stage_announcer=seen.append)
        perf.start("数据准备")
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0], perf)

    def test_announcer_failure_does_not_break_start(self) -> None:
        """回调抛异常 → start 不传播，计时状态正常建立。"""

        def broken(_perf: PerfCollector) -> None:
            raise RuntimeError("通道故障")

        perf = PerfCollector(report_type="both", holdings=[], stage_announcer=broken)
        perf.start("数据准备")  # 不应抛出
        status = perf.stage_status()
        self.assertIsNotNone(status)
        assert status is not None
        self.assertEqual(status["phase"], "数据准备")
        perf.stop()

    def test_without_announcer_default_construction(self) -> None:
        """不传回调（既有调用面零改动）→ start/stop 正常。"""
        perf = PerfCollector(report_type="basic", holdings=[])
        perf.start("Excel 生成")
        self.assertIsNotNone(perf.stage_status())
        self.assertIsNotNone(perf.stop())


if __name__ == "__main__":
    unittest.main()
