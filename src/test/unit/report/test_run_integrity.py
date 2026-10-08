"""运行一致性守卫（run_integrity）测试 — 中断收口、原子落盘、已中断状态。

覆盖：
- 运行上下文生命周期与登记接口（无上下文空操作 / 有上下文精确登记）
- 遗留与本次临时文件清扫（产物前缀匹配，不动无关文件）
- 中断收口：清理临时文件 + 落 status=interrupted 运行记录 + 已写盘/已丢弃明细提示
- HTML / Excel 原子落盘（同目录 .tmp + os.replace，中断只留临时文件）
- PerfCollector 中断状态与 save 幂等（一次运行只落一条记录）
- generate_report 中断：收口后原样 re-raise，运行记录为已中断
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import Workbook

from src.python.report import run_integrity as ri
from src.python.report.run_integrity import (
    RunContext,
    begin_run,
    bind_health,
    bind_perf,
    clear_run,
    current_run,
    guard_run,
    handle_interruption,
    note_artifact,
    note_temp,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class _FakeReporter:
    """收集 warn 输出的最小进度通道。"""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def stage_progress(self, perf) -> None:  # noqa: ANN001 - PerfCollector 形状
        pass

    def info(self, msg: str) -> None:
        pass

    def ok(self, msg: str) -> None:
        pass

    def add_error(self, msg: str) -> None:
        pass


class _RunContextBase(unittest.TestCase):
    """公共基座：每个用例收尾清空 ContextVar，防跨用例串扰。"""

    def tearDown(self) -> None:
        clear_run()


class TestRunContextLifecycle(_RunContextBase):
    """运行上下文生命周期与登记接口。"""

    def test_begin_current_clear(self) -> None:
        """begin_run 建立上下文 → current 可读 → clear_run 归零。"""
        self.assertIsNone(current_run())
        ctx = begin_run("basic", "reports")
        self.assertIs(current_run(), ctx)
        self.assertEqual(ctx.report_type, "basic")
        clear_run()
        self.assertIsNone(current_run())

    def test_notes_are_noop_without_context(self) -> None:
        """无运行上下文（whatif / 独立调用）→ 登记接口全部空操作不抛。"""
        clear_run()
        note_temp("/nonexistent/file.tmp")
        note_artifact("xlsx", "/nonexistent/file.xlsx")
        bind_perf(object())
        bind_health(object(), "basic", [])
        self.assertIsNone(current_run())

    def test_notes_register_into_context(self) -> None:
        """有运行上下文 → 临时文件与产物精确登记。"""
        ctx = begin_run("both", "reports")
        note_temp("/tmp/a.tmp")
        note_artifact("html", "/tmp/a.html")
        note_artifact("xlsx", "/tmp/a.xlsx")
        self.assertEqual(ctx.temps, ["/tmp/a.tmp"])
        self.assertEqual([k for k, _ in ctx.artifacts], ["html", "xlsx"])
        self.assertEqual(ctx.written_kinds, {"html", "xlsx"})

    def test_bind_perf_and_health(self) -> None:
        """bind_perf / bind_health 绑定到当前上下文。"""
        ctx = begin_run("full", "reports")
        perf = object()
        fut = object()
        bind_perf(perf)
        bind_health(fut, "full", [{"code": "X"}])
        self.assertIs(ctx.perf, perf)
        self.assertEqual(ctx.health[1:], ("full", [{"code": "X"}]))

    def test_begin_run_sweeps_stale_product_tmps(self) -> None:
        """上次崩溃遗留的产物 .tmp 预清扫；无关 .tmp 不动。"""
        with tempfile.TemporaryDirectory() as tmp:
            product = Path(tmp) / "个人投资分析报告.xlsx.tmp"
            foreign = Path(tmp) / "别的工具.txt.tmp"
            product.write_text("stale", encoding="utf-8")
            foreign.write_text("keep", encoding="utf-8")
            begin_run("basic", tmp)
            self.assertFalse(product.exists())
            self.assertTrue(foreign.exists())


class TestInterruptionHandling(_RunContextBase):
    """中断收口：清理、已中断记录、明细提示、健康检查收敛。"""

    def _write_perf_file(self, tmp: str) -> str:
        path = os.path.join(tmp, "perf_history.jsonl")
        patcher = patch("src.python.core.perf._PERF_HISTORY_FILE", path)
        patcher.start()
        self.addCleanup(patcher.stop)
        return path

    def test_cleanup_registered_and_stray_tmps_only(self) -> None:
        """清理：登记的在写临时文件 + 产物前缀兜底；无关文件保留。"""
        with tempfile.TemporaryDirectory() as tmp:
            registered = Path(tmp) / "个人投资分析报告.xlsx.tmp"
            stray = Path(tmp) / "20261007"
            stray.mkdir()
            stray_file = stray / "个人投资分析报告-20261007-010101.html.tmp"
            foreign = Path(tmp) / "无关文件.tmp"
            registered.write_text("partial", encoding="utf-8")
            stray_file.write_text("partial", encoding="utf-8")
            foreign.write_text("keep", encoding="utf-8")

            begin_run("both", tmp)
            note_temp(str(registered))
            reporter = _FakeReporter()
            with self.assertRaises(KeyboardInterrupt):
                try:
                    raise KeyboardInterrupt
                except KeyboardInterrupt:
                    handle_interruption(reporter)
                    raise

            self.assertFalse(registered.exists())
            self.assertFalse(stray_file.exists())
            self.assertTrue(foreign.exists())

    def test_interrupted_perf_record_and_message(self) -> None:
        """收口落 status=interrupted 运行记录（含阶段），提示含已写盘/已丢弃/清理数。"""
        with tempfile.TemporaryDirectory() as tmp:
            perf_file = self._write_perf_file(tmp)
            from src.python.core.perf import PerfCollector

            ctx = begin_run("basic", tmp)
            perf = PerfCollector(report_type="basic", holdings=[1, 2])
            bind_perf(perf)
            perf.start("Excel 生成")  # 中断时活跃阶段
            tmp_left = Path(tmp) / "个人投资分析报告.xlsx.tmp"
            tmp_left.write_text("partial", encoding="utf-8")
            note_temp(str(tmp_left))

            reporter = _FakeReporter()
            handle_interruption(reporter)

            # 运行记录：已中断 + 阶段
            lines = Path(perf_file).read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[-1])
            self.assertEqual(record["status"], "interrupted")
            self.assertEqual(record["interrupted_stage"], "Excel 生成")
            # 明细提示：阶段 / 已写盘无 / 已丢弃 Excel / 清理 1 个
            (msg,) = reporter.warnings
            self.assertIn("生成已中断", msg)
            self.assertIn("Excel 生成", msg)
            self.assertIn("已写盘：无", msg)
            self.assertIn("未完成已丢弃：Excel", msg)
            self.assertIn("已清理临时文件 1 个", msg)
            self.assertFalse(tmp_left.exists())
            self.assertIs(current_run(), ctx)

    def test_message_lists_written_artifacts(self) -> None:
        """HTML 已写盘、Excel 未写 → 已写盘列相对路径、已丢弃列 Excel。"""
        with tempfile.TemporaryDirectory() as tmp:
            begin_run("both", tmp)
            note_artifact("html", os.path.join(tmp, "个人投资分析报告.html"))
            reporter = _FakeReporter()
            handle_interruption(reporter)
            (msg,) = reporter.warnings
            self.assertIn("已写盘：个人投资分析报告.html", msg)
            self.assertIn("未完成已丢弃：Excel", msg)

    def test_health_future_collected_on_interruption(self) -> None:
        """绑定的健康检查 future 在收口时被收敛（防线程残留）。"""
        with tempfile.TemporaryDirectory() as tmp:
            begin_run("basic", tmp)
            fut, holdings = object(), []
            bind_health(fut, "basic", holdings)
            with patch("src.python.report._report_health._collect_health_checks") as mock_collect:
                handle_interruption(_FakeReporter())
            mock_collect.assert_called_once_with(fut, "basic", holdings)

    def test_no_context_emits_empty_message(self) -> None:
        """上下文未建立即中断 → 提示未产生任何产物，不抛。"""
        clear_run()
        reporter = _FakeReporter()
        handle_interruption(reporter)
        self.assertIn("未产生任何产物", reporter.warnings[0])

    def test_stage_gap_labeled(self) -> None:
        """中断落在阶段间隙（无活跃阶段）→ 阶段记「阶段间隙」。"""
        with tempfile.TemporaryDirectory() as tmp:
            begin_run("basic", tmp)
            from src.python.core.perf import PerfCollector

            perf = PerfCollector(report_type="basic", holdings=[])
            bind_perf(perf)
            perf.start("行情获取")
            perf.stop()  # 阶段间隙
            reporter = _FakeReporter()
            handle_interruption(reporter)
            self.assertIn("阶段间隙", reporter.warnings[0])


class TestAtomicWrites(_RunContextBase):
    """HTML / Excel 原子落盘（.tmp + os.replace）。"""

    def test_html_write_atomic_and_registered(self) -> None:
        """正常写入：内容落最终文件、无 .tmp 残留、产物登记进上下文。"""
        from src.python.report.html_save import _write_html_atomic

        with tempfile.TemporaryDirectory() as tmp:
            begin_run("both", tmp)
            target = os.path.join(tmp, "个人投资分析报告.html")
            _write_html_atomic("<html>ok</html>", target)
            self.assertEqual(Path(target).read_text(encoding="utf-8"), "<html>ok</html>")
            self.assertFalse(os.path.exists(target + ".tmp"))
            self.assertIn(("html", target), current_run().artifacts)

    def test_html_interrupt_keeps_final_intact(self) -> None:
        """替换阶段中断 → 最终文件保持旧内容，临时文件被登记待清扫。"""
        from src.python.report.html_save import _write_html_atomic

        with tempfile.TemporaryDirectory() as tmp:
            begin_run("both", tmp)
            target = os.path.join(tmp, "个人投资分析报告.html")
            Path(target).write_text("旧报告", encoding="utf-8")
            with patch("src.python.report.html_save.os.replace", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    _write_html_atomic("新内容", target)
            self.assertEqual(Path(target).read_text(encoding="utf-8"), "旧报告")
            self.assertIn(target + ".tmp", current_run().temps)
            # 收口清掉半成品临时文件
            handle_interruption(_FakeReporter())
            self.assertFalse(os.path.exists(target + ".tmp"))

    def test_excel_save_atomic_and_no_tmp_left(self) -> None:
        """save_workbook 正常路径：最新+归档原子落盘、无 .tmp 残留。"""
        from src.python.report.excel_writer import save_workbook

        with tempfile.TemporaryDirectory() as tmp:
            begin_run("basic", tmp)
            wb = Workbook()
            wb.active.title = "测试"
            path = save_workbook(wb, output_dir=tmp)
            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(path + ".tmp"))
            kinds = [k for k, _ in current_run().artifacts]
            self.assertEqual(kinds, ["xlsx", "xlsx"])

    def test_excel_interrupt_keeps_previous_latest(self) -> None:
        """写临时文件中断 → 最新版不被半写截断（旧文件完好）。"""
        from src.python.report.excel_writer import save_workbook

        with tempfile.TemporaryDirectory() as tmp:
            begin_run("basic", tmp)
            latest = os.path.join(tmp, "个人投资分析报告.xlsx")
            Path(latest).write_bytes(b"OLD-CONTENT")
            wb = Workbook()

            def _raise(_self, _path):
                raise KeyboardInterrupt

            with patch("openpyxl.Workbook.save", _raise):
                with self.assertRaises(KeyboardInterrupt):
                    save_workbook(wb, output_dir=tmp)
            self.assertEqual(Path(latest).read_bytes(), b"OLD-CONTENT")
            # 收口清理已登记临时文件（若已写出）
            handle_interruption(_FakeReporter())
            self.assertFalse(os.path.exists(latest + ".tmp"))


class TestPerfInterruptedStatus(_RunContextBase):
    """PerfCollector 中断状态与 save 幂等。"""

    def test_snapshot_default_completed(self) -> None:
        """默认快照 status=completed、interrupted_stage=None。"""
        from src.python.core.perf import PerfCollector

        snap = PerfCollector(report_type="basic", holdings=[]).snapshot().to_json()
        self.assertEqual(snap["status"], "completed")
        self.assertIsNone(snap["interrupted_stage"])

    def test_mark_interrupted_carries_stage(self) -> None:
        """mark_interrupted → status=interrupted + 中断时活跃阶段名。"""
        from src.python.core.perf import PerfCollector

        perf = PerfCollector(report_type="both", holdings=[])
        perf.start("行情获取")
        perf.mark_interrupted()
        snap = perf.snapshot().to_json()
        self.assertEqual(snap["status"], "interrupted")
        self.assertEqual(snap["interrupted_stage"], "行情获取")

    def test_save_is_idempotent_per_run(self) -> None:
        """一次运行只落一条记录（正常完成后中断收口重复 save 跳过）。"""
        from src.python.core.perf import PerfCollector

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "perf_history.jsonl")
            with patch("src.python.core.perf._PERF_HISTORY_FILE", path):
                perf = PerfCollector(report_type="basic", holdings=[])
                perf.save()
                perf.mark_interrupted()
                perf.save()  # 幂等跳过
            lines = Path(path).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["status"], "completed")


class TestGuardRun(_RunContextBase):
    """guard_run 装饰器：收口 + re-raise + 上下文清理。"""

    def test_normal_path_clears_context(self) -> None:
        """正常返回 → 产出值原样透传，上下文已清空。"""

        @guard_run
        def _fake_generate(config: dict, reporter=None, report_type="basic", output_dir=None):  # noqa: ANN001
            self.assertIsNotNone(current_run())
            return "ok"

        self.assertEqual(_fake_generate(config={"output_dir": "reports"}), "ok")
        self.assertIsNone(current_run())

    def test_keyboard_interrupt_reraised_and_handled(self) -> None:
        """KeyboardInterrupt → 收口（经通道出提示）后原样 re-raise。"""

        @guard_run
        def _fake_generate(config: dict, reporter=None, report_type="basic", output_dir=None):  # noqa: ANN001
            raise KeyboardInterrupt

        reporter = _FakeReporter()
        with self.assertRaises(KeyboardInterrupt):
            _fake_generate(config={"output_dir": "reports"}, reporter=reporter, report_type="both")
        self.assertTrue(any("生成已中断" in w for w in reporter.warnings))
        self.assertIsNone(current_run())

    def test_output_dir_falls_back_to_config(self) -> None:
        """output_dir 未显式传 → 上下文取 config.output_dir。"""
        captured: dict = {}

        @guard_run
        def _fake_generate(config: dict, reporter=None, report_type="basic", output_dir=None):  # noqa: ANN001
            captured["output_dir"] = current_run().output_dir
            return None

        _fake_generate(config={"output_dir": "custom_out"}, output_dir=None)
        self.assertEqual(captured["output_dir"], "custom_out")

    def test_explicit_output_dir_wins(self) -> None:
        """显式 output_dir 优先于 config。"""
        captured: dict = {}

        @guard_run
        def _fake_generate(config: dict, reporter=None, report_type="basic", output_dir=None):  # noqa: ANN001
            captured["output_dir"] = current_run().output_dir
            return None

        _fake_generate(config={"output_dir": "cfg_out"}, output_dir="explicit_out")
        self.assertEqual(captured["output_dir"], "explicit_out")


class TestGenerateReportInterruption(_RunContextBase):
    """generate_report 集成：中断收口后 re-raise，运行记录为已中断。"""

    def test_basic_interrupt_recorded_and_reraised(self) -> None:
        """basic 路径 Excel 生成中断 → KI 冒泡 + perf 记录 interrupted（阶段=Excel 生成）。"""
        from src.python.report.orchestrator import generate_report

        with tempfile.TemporaryDirectory() as tmp:
            perf_file = os.path.join(tmp, "perf_history.jsonl")
            reporter = _FakeReporter()
            with (
                patch("src.python.core.perf._PERF_HISTORY_FILE", perf_file),
                patch(
                    "src.python.report.excel_generator.generate_excel_report",
                    side_effect=KeyboardInterrupt,
                ),
                patch(
                    "src.python.report._report_generation._spawn_health_checks",
                    return_value=None,
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    generate_report(
                        holdings=[{"code": "000001", "name": "测试"}],
                        config={"output_dir": tmp},
                        reporter=reporter,
                        report_type="basic",
                        fetch_history=False,
                        output_dir=tmp,
                    )

            # 运行记录已中断且带阶段
            lines = Path(perf_file).read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[-1])
            self.assertEqual(record["status"], "interrupted")
            self.assertEqual(record["interrupted_stage"], "Excel 生成")
            # 明细提示已给出：未写盘任何产物、Excel 丢弃
            self.assertTrue(any("未完成已丢弃：Excel" in w for w in reporter.warnings))
            # 上下文已清理、无临时文件残留
            self.assertIsNone(current_run())
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])


class TestRunIntegrityModuleContract(_RunContextBase):
    """模块契约：登记接口与清扫函数的形状约束。"""

    def test_run_context_is_dataclass_with_expected_fields(self) -> None:
        """RunContext 字段名与类型形状（写盘方依赖的稳定接口）。"""
        import dataclasses

        names = {f.name for f in dataclasses.fields(RunContext)}
        self.assertEqual(
            names,
            {"report_type", "output_dir", "perf", "health", "artifacts", "temps"},
        )

    def test_product_tmp_glob_scoped_to_output_dir(self) -> None:
        """产物临时文件匹配限定在输出目录内（含归档子目录），不越界。"""
        with tempfile.TemporaryDirectory() as tmp:
            inside = Path(tmp) / "20261007"
            inside.mkdir()
            (inside / "个人投资分析报告-20261007-010101.html.tmp").write_text("x", encoding="utf-8")
            outside = Path(tmp).parent / "个人投资分析报告.html.tmp"
            found = ri._product_tmp_files(tmp)
            self.assertEqual(len(found), 1)
            self.assertIn("20261007", found[0])
            self.assertNotIn(os.path.abspath(str(outside)), [os.path.abspath(p) for p in found])


if __name__ == "__main__":
    unittest.main()
