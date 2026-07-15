"""ProgressReporter 接口单元测试。

测试目标：
  - ProgressReporter 基类无副作用
  - SilentProgressReporter 静默行为
  - TuiProgressReporter 格式化 + 错误跟踪 + 耗时排行
  - Timer 上下文管理器

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_progress.py -v
"""

from __future__ import annotations

import io
import os
import sys
import time as _time_module
import unittest
from unittest.mock import patch

from src.python.report.progress import (

    ProgressReporter, SilentProgressReporter, TuiProgressReporter,
    Timer, timing_records,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_report]



class TestProgressReporter(unittest.TestCase):
    """基类方法应无副作用（静默不输出）。"""

    def setUp(self):
        self.r = ProgressReporter()

    def test_info_no_op(self) -> None:
        """info 不应抛出异常。"""
        self.r.info("test")

    def test_ok_no_op(self) -> None:
        """ok 不应抛出异常。"""
        self.r.ok("test")

    def test_warn_no_op(self) -> None:
        """warn 不应抛出异常。"""
        self.r.warn("test")

    def test_error_no_op(self) -> None:
        """error 不应抛出异常。"""
        self.r.error("test")

    def test_add_error_no_op(self) -> None:
        """add_error 不应抛出异常。"""
        self.r.add_error("test error")

    def test_get_errors_empty(self) -> None:
        """get_errors 默认返回空列表。"""
        self.assertEqual(self.r.get_errors(), [])

    def test_call_sheet_with_fn_success(self) -> None:
        """call_sheet 成功调用函数返回 True。"""
        called = []

        def my_fn():
            called.append(1)

        result = self.r.call_sheet("测试", my_fn)
        self.assertTrue(result)
        self.assertEqual(called, [1])

    def test_call_sheet_fn_none(self) -> None:
        """call_sheet 传入 None 返回 False 并记录错误。"""
        result = self.r.call_sheet("缺失模块", None)
        self.assertFalse(result)

    def test_call_sheet_fn_exception(self) -> None:
        """call_sheet 函数抛出异常返回 False。"""

        def failing_fn():
            raise ValueError("模拟失败")

        result = self.r.call_sheet("失败模块", failing_fn)
        self.assertFalse(result)

    def test_timer_context(self) -> None:
        """Timer 上下文管理器记录耗时。"""
        saved = list(timing_records)
        timing_records.clear()
        try:
            with Timer("测试计时"):
                pass
            self.assertEqual(len(timing_records), 1)
            label, elapsed = timing_records[0]
            self.assertEqual(label, "测试计时")
            self.assertGreaterEqual(elapsed, 0.0)
        finally:
            timing_records.clear()
            timing_records.extend(saved)

    def test_timer_context_elapsed_time(self) -> None:
        """Timer 记录的实际耗时接近真实耗时。"""
        saved = list(timing_records)
        timing_records.clear()
        try:
            with Timer("延时"):
                _time_module.sleep(0.01)
            _, elapsed = timing_records[0]
            self.assertAlmostEqual(elapsed, 0.01, delta=0.05)
        finally:
            timing_records.clear()
            timing_records.extend(saved)


class TestSilentProgressReporter(unittest.TestCase):
    """静默报告器不应输出任何内容。"""

    def setUp(self):
        self.r = SilentProgressReporter()

    def test_info_no_output(self) -> None:
        """info 不产生 stdout。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.info("should not appear")
            self.assertEqual(captured.getvalue(), "")
        finally:
            sys.stdout = sys.__stdout__

    def test_ok_no_output(self) -> None:
        """ok 不产生 stdout。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.ok("should not appear")
            self.assertEqual(captured.getvalue(), "")
        finally:
            sys.stdout = sys.__stdout__

    def test_add_error_no_side_effect(self) -> None:
        """add_error 不报错（logger 调用但不应抛出）。"""
        self.r.add_error("test error")

    def test_get_errors_empty_list(self) -> None:
        """get_errors 从基类继承返回空列表。"""
        self.assertEqual(self.r.get_errors(), [])


class TestTuiProgressReporter(unittest.TestCase):
    """终端报告器格式化 + 错误跟踪 + 耗时排行。"""

    def setUp(self):
        self.r = TuiProgressReporter()

    # ── 格式化输出 ──

    def test_info_prefix(self) -> None:
        """info 输出带 [..] 前缀。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.info("加载中")
            self.assertIn("[..]", captured.getvalue())
            self.assertIn("加载中", captured.getvalue())
        finally:
            sys.stdout = sys.__stdout__

    def test_ok_prefix(self) -> None:
        """ok 输出带 [OK] 前缀。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.ok("成功")
            self.assertIn("[OK]", captured.getvalue())
            self.assertIn("成功", captured.getvalue())
        finally:
            sys.stdout = sys.__stdout__

    def test_warn_prefix(self) -> None:
        """warn 输出带 [!] 前缀。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.warn("警告")
            self.assertIn("[!]", captured.getvalue())
            self.assertIn("警告", captured.getvalue())
        finally:
            sys.stdout = sys.__stdout__

    def test_error_prefix(self) -> None:
        """error 输出带 [ERR] 前缀。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.error("错误")
            self.assertIn("[ERR]", captured.getvalue())
            self.assertIn("错误", captured.getvalue())
        finally:
            sys.stdout = sys.__stdout__

    # ── 错误跟踪 ──

    def test_add_error_records(self) -> None:
        """add_error 记录到 _errors 列表。"""
        self.r.add_error("错误1")
        self.r.add_error("错误2")
        self.assertEqual(self.r.get_errors(), ["错误1", "错误2"])

    def test_get_errors_returns_copy(self) -> None:
        """get_errors 返回副本，修改不影响内部。"""
        self.r.add_error("错误1")
        errs = self.r.get_errors()
        errs.append("额外")
        self.assertEqual(len(self.r.get_errors()), 1)

    def test_error_summary_output(self) -> None:
        """print_error_summary 输出错误汇总。"""
        self.r.add_error("数据获取失败")
        self.r.add_error("报告生成异常")
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.print_error_summary()
            output = captured.getvalue()
            self.assertIn("数据获取失败", output)
            self.assertIn("报告生成异常", output)
        finally:
            sys.stdout = sys.__stdout__

    def test_error_summary_empty_prints_nothing(self) -> None:
        """无错误时 print_error_summary 不输出。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            self.r.print_error_summary()
            self.assertEqual(captured.getvalue(), "")
        finally:
            sys.stdout = sys.__stdout__

    def test_error_summary_clears_after_print(self) -> None:
        """print_error_summary 输出后清空错误列表。"""
        self.r.add_error("临时错误")
        self.r.print_error_summary()
        self.assertEqual(self.r.get_errors(), [])

    # ── call_sheet ──

    def test_call_sheet_info_prefix(self) -> None:
        """call_sheet 成功输出 [..] 和 [OK] 消息。"""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            result = self.r.call_sheet("持仓明细", lambda: None)
            output = captured.getvalue()
            self.assertTrue(result)
            self.assertIn("[..]", output)
            self.assertIn("持仓明细", output)
            self.assertIn("[OK]", output)
        finally:
            sys.stdout = sys.__stdout__

    def test_call_sheet_fn_none_returns_false(self) -> None:
        """call_sheet 传入 None 返回 False 且记录错误。"""
        result = self.r.call_sheet("缺失模块", None)
        self.assertFalse(result)
        self.assertIn("缺失模块", self.r.get_errors()[0])

    def test_call_sheet_fn_exception_returns_false(self) -> None:
        """call_sheet 函数异常返回 False 且记录错误。"""

        def fail():
            raise RuntimeError("写入失败")

        result = self.r.call_sheet("失败页", fail)
        self.assertFalse(result)
        self.assertIn("失败页", self.r.get_errors()[0])

    # ── 计时器 ──

    def test_timer_context_manager(self) -> None:
        """timer() 返回可用的 Timer。"""
        saved = list(timing_records)
        timing_records.clear()
        try:
            with self.r.timer("模块A"):
                pass
            self.assertEqual(len(timing_records), 1)
        finally:
            timing_records.clear()
            timing_records.extend(saved)

    # ── 耗时排行 ──

    def test_print_timing_summary_output(self) -> None:
        """print_timing_summary 输出耗时排行。"""
        saved = list(timing_records)
        timing_records.clear()
        try:
            timing_records.append(("模块A", 1.5))
            timing_records.append(("模块B", 0.5))
            captured = io.StringIO()
            sys.stdout = captured
            try:
                self.r.print_timing_summary()
                output = captured.getvalue()
                self.assertIn("模块A", output)
                self.assertIn("模块B", output)
            finally:
                sys.stdout = sys.__stdout__
        finally:
            timing_records.clear()
            timing_records.extend(saved)

    def test_print_timing_summary_empty(self) -> None:
        """无计时记录时 print_timing_summary 不输出。"""
        saved = list(timing_records)
        timing_records.clear()
        try:
            captured = io.StringIO()
            sys.stdout = captured
            try:
                self.r.print_timing_summary()
                self.assertEqual(captured.getvalue(), "")
            finally:
                sys.stdout = sys.__stdout__
        finally:
            timing_records.clear()
            timing_records.extend(saved)

    def test_print_timing_summary_clears_records(self) -> None:
        """print_timing_summary 输出后清空 timing_records。"""
        saved = list(timing_records)
        timing_records.clear()
        try:
            timing_records.append(("模块A", 1.0))
            self.r.print_timing_summary()
            self.assertEqual(len(timing_records), 0)
        finally:
            timing_records.clear()
            timing_records.extend(saved)


if __name__ == "__main__":
    unittest.main()
