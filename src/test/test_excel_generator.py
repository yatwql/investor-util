"""Excel 报告生成单元测试 — 页签写入隔离、模块缺失降级、数据路径。

测试目标：
  - 基本路径：外部传入明细/指数，跳过获取
  - 新闻/LLM 包含路径：页签创建 + 内容写入
  - 模块缺失降级：ImportError → add_error + 其他页签继续
  - 异常隔离：单页签 throw → add_error + 不影响其他
  - ProgressReporter 接口：info/ok/add_error 回调

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_excel_generator.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from collections import namedtuple

from src.python.report.progress import SilentProgressReporter


# ═══════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════


DetailRow = namedtuple("DetailRow", [
    "market_value", "cost", "profit", "today_profit",
    "code", "name", "change_pct", "price_type", "nav_date",
    "profit_rate", "price",
])


def _make_detail(mv: float = 1000, cost: float = 800, profit: float = 200,
                 today_profit: float = 50, code: str = "600900",
                 name: str = "长江电力") -> DetailRow:
    return DetailRow(
        market_value=mv, cost=cost, profit=profit, today_profit=today_profit,
        code=code, name=name, change_pct=1.5, price_type="tencent",
        nav_date="", profit_rate=25.0, price=28.5,
    )


# ═══════════════════════════════════════════════════════════
#  辅助：模拟各模块函数，避免真实导入依赖
# ═══════════════════════════════════════════════════════════


class _SheetMocks:
    """持有所有 mock 引用，便于断言。"""

    def __init__(self) -> None:
        self.write_summary = MagicMock()
        self.write_market_value = MagicMock(return_value=(
            10000.0, 8000.0, 2000.0, 500.0,
            [_make_detail()],
        ))
        self.classify_holdings = MagicMock(return_value={})
        self.get_last_trading_day = MagicMock(return_value="2026-07-01")
        self.price_update_status = MagicMock(return_value=(1, 0, True))
        self.write_category = MagicMock()
        self.compute_penetration = MagicMock(return_value={})
        self.write_penetration = MagicMock()
        self.write_fund_performance = MagicMock()

    def start(self) -> list:
        """启动所有 patch，返回 patcher 列表以便 stop。"""
        self.patchers = [
            patch("src.python.report.summary.write_summary_sheet", self.write_summary),
            patch("src.python.report.excel_writer.create_workbook"),
            patch("src.python.report.excel_writer.save_workbook", return_value="reports/test.xlsx"),
            patch("src.python.report.market_value.write_market_value_sheet", self.write_market_value),
            patch("src.python.report.market_value.classify_holdings", self.classify_holdings),
            patch("src.python.report.market_value.get_last_trading_day", self.get_last_trading_day),
            patch("src.python.report.market_value.price_update_status", self.price_update_status),
            patch("src.python.report.category.write_category_sheet", self.write_category),
            patch("src.python.report.penetration.compute_penetration_top10", self.compute_penetration),
            patch("src.python.report.penetration.write_penetration_sheet", self.write_penetration),
            patch("src.python.report.fund_performance.write_fund_performance_sheet", self.write_fund_performance),
            patch("src.python.report.excel_generator.get_report_sheet_name", side_effect=lambda k: k),
            patch("src.python.report.excel_generator.get_llm_module_name", MagicMock()),
        ]
        for p in self.patchers:
            p.start()
        # 保存 create_workbook mock 引用
        self.mock_create_wb = self.patchers[1].new
        self.mock_wb = MagicMock()
        self.mock_ws = MagicMock()
        self.mock_wb.active = self.mock_ws
        self.mock_wb.create_sheet.return_value = MagicMock()
        self.mock_create_wb.return_value = self.mock_wb
        return self.patchers

    def stop(self) -> None:
        for p in self.patchers:
            p.stop()


class TestGenerateExcelReport(unittest.TestCase):
    """generate_excel_report 主流程。"""

    def setUp(self) -> None:
        self.progress = SilentProgressReporter()
        self.holdings = []
        self.sheets = _SheetMocks()
        self.sheets.start()
        # mock 指数获取
        self.idx_patcher = patch("src.python.fetcher.index.fetch_indices", return_value={})
        self.mock_fetch_idx = self.idx_patcher.start()
        self.us_idx_patcher = patch("src.python.fetcher.index.fetch_us_indices", return_value={})
        self.mock_fetch_us_idx = self.us_idx_patcher.start()

    def tearDown(self) -> None:
        self.sheets.stop()
        self.idx_patcher.stop()
        self.us_idx_patcher.stop()

    # ── 基本路径 ──

    def test_basic_generation(self) -> None:
        """基本路径：所有模块正常，外部传入明细+指数。"""
        from src.python.report.excel_generator import generate_excel_report
        details = [_make_detail()]
        a_idx = {"sh000001": {"name": "上证指数", "price": 3120, "change_pct": 0.5}}

        generate_excel_report(
            self.holdings, details=details,
            a_indices=a_idx, us_indices={},
            progress=self.progress,
        )

        self.assertEqual(len(self.progress.get_errors()), 0)

    def test_generation_without_external_data(self) -> None:
        """无外部传入数据 → 内部获取指数。"""
        from src.python.report.excel_generator import generate_excel_report

        generate_excel_report(self.holdings, progress=self.progress)

        self.assertEqual(len(self.progress.get_errors()), 0)
        self.mock_fetch_idx.assert_called_once()
        self.mock_fetch_us_idx.assert_called_once()

    # ── 新闻路径 ──

    def test_with_news(self) -> None:
        """include_news=True → 新闻页签创建 + 预警页签。"""
        from src.python.report.excel_generator import generate_excel_report

        with patch("src.python.report.news_correlation.write_news_sheet") as mock_news:
            with patch("src.python.report.news_correlation.build_news_data",
                       return_value=([], {})):
                with patch("src.python.report.early_warning.write_early_warning_sheet"):
                    generate_excel_report(
                        self.holdings, include_news=True,
                        progress=self.progress,
                    )

        self.assertEqual(len(self.progress.get_errors()), 0)

    def test_with_news_external_data(self) -> None:
        """include_news + 外部新闻数据 → 复用。"""
        from src.python.report.excel_generator import generate_excel_report
        news_data = [{"title": "新闻1", "intro": "简介", "matched_keywords": ["test"]}]
        news_llm_meta = {"llm_enabled": False}

        with patch("src.python.report.news_correlation.write_news_sheet") as mock_news:
            with patch("src.python.report.early_warning.write_early_warning_sheet"):
                generate_excel_report(
                    self.holdings, include_news=True,
                    news_data=news_data, news_llm_meta=news_llm_meta,
                    progress=self.progress,
                )

        self.assertEqual(len(self.progress.get_errors()), 0)

    # ── LLM 路径 ──

    def test_with_llm(self) -> None:
        """include_llm=True → LLM 内容写入。"""
        from src.python.report.excel_generator import generate_excel_report
        llm_content = ("<p>宏</p>", "<p>策略</p>", "<p>体检</p>", "<p>穿透</p>")

        with patch("src.python.report.llm_content.write_llm_sheets") as mock_llm:
            mock_llm.return_value = ("<p>宏</p>", "<p>策略</p>", "<p>体检</p>", "<p>穿透</p>")
            with patch("src.python.llm.session.get_session_usage",
                       return_value={"call_count": 0, "per_module": {}}):
                generate_excel_report(
                    self.holdings, include_llm=True,
                    llm_content=llm_content,
                    progress=self.progress,
                )

        mock_llm.assert_called_once()
        self.assertLessEqual(len(self.progress.get_errors()), 1)

    def test_with_llm_and_session_usage(self) -> None:
        """include_llm + 有会话统计 → 写入用量页签 + 汇总页追加。"""
        from src.python.report.excel_generator import generate_excel_report
        llm_content = ("<p>宏</p>", "<p>策略</p>", "<p>体检</p>", "<p>穿透</p>")
        session_usage = {
            "call_count": 2,
            "input_tokens": 1000, "output_tokens": 500,
            "cache_hit_tokens": 200, "models": ["deepseek-v4-flash"],
            "per_module": {
                "global_macro": {"input_tokens": 500, "output_tokens": 200,
                                 "model": "deepseek-v4-flash", "cached": False,
                                 "thinking": False, "endpoint": "", "cache_hit_tokens": 0,
                                 "cost": 0.0},
                "expert_review": {"input_tokens": 500, "output_tokens": 300,
                                  "model": "deepseek-v4-flash", "cached": False,
                                  "thinking": True, "endpoint": "", "cache_hit_tokens": 0,
                                  "cost": 0.0},
            },
        }

        with patch("src.python.report.llm_content.write_llm_sheets") as mock_llm:
            mock_llm.return_value = ("<p>宏</p>", "<p>策略</p>", "<p>体检</p>", "<p>穿透</p>")
            with patch("src.python.llm.session.get_session_usage",
                       return_value=session_usage):
                with patch("src.python.llm.session.format_session_usage") as mock_fmt:
                    mock_fmt.return_value = {
                        "has_usage": True, "call_count": 2,
                        "total_tokens": 1500, "cost_display": "¥0.002",
                        "per_module": session_usage["per_module"],
                    }
                    with patch("src.python.report.summary.write_llm_usage_block"):
                        with patch("src.python.report.summary.write_llm_usage_sheet"):
                            generate_excel_report(
                                self.holdings, include_llm=True,
                                llm_content=llm_content,
                                progress=self.progress,
                            )

        mock_llm.assert_called_once()

    # ── 智能预警 ──

    def test_early_warnings_passthrough(self) -> None:
        """外部传入 early_warnings → 透传到预警页签。"""
        from src.python.report.excel_generator import generate_excel_report
        early_warnings = {
            "sector_alerts": [{"asset": "茅台", "level": "关注"}],
            "sentiment_alerts": [],
            "has_warnings": True, "has_sector_data": True,
            "has_llm_news": False,
        }

        with patch("src.python.report.news_correlation.write_news_sheet"):
            with patch("src.python.report.news_correlation.build_news_data",
                       return_value=([], {"llm_enabled": False})):
                with patch("src.python.report.early_warning.write_early_warning_sheet") as mock_ew:
                    generate_excel_report(
                        self.holdings, include_news=True,
                        news_data=[], news_llm_meta={},
                        early_warnings=early_warnings,
                        progress=self.progress,
                    )

        mock_ew.assert_called_once()

    # ── 模块缺失降级 ──

    def test_summary_module_missing(self) -> None:
        """汇总模块缺失 → add_error + 其他模块继续。"""
        from src.python.report.excel_generator import generate_excel_report

        with patch("src.python.report.summary.write_summary_sheet", None):
            generate_excel_report(
                self.holdings, progress=self.progress,
            )

        errors = self.progress.get_errors()
        self.assertTrue(any("summary" in e.lower() or "汇总" in e for e in errors),
                        f"预期 summary 错误，得到: {errors}")

    def test_market_value_module_missing(self) -> None:
        """行情市值模块缺失 → add_error + 后续模块继续。"""
        from src.python.report.excel_generator import generate_excel_report

        with patch("src.python.report.market_value.write_market_value_sheet", None):
            generate_excel_report(
                self.holdings, progress=self.progress,
            )

        errors = self.progress.get_errors()
        self.assertTrue(any("market_value" in e.lower() or "行情市值" in e for e in errors),
                        f"预期 market_value 错误，得到: {errors}")

    # ── 页签写入异常隔离 ──

    def test_sheet_exception_isolation(self) -> None:
        """某个页签抛出异常 → add_error + 不影响其他页签写入。"""
        from src.python.report.excel_generator import generate_excel_report

        broken_sheet = MagicMock(side_effect=ValueError("写入失败"))
        # 替换 summary 的 mock 为会抛异常的版本
        with patch("src.python.report.summary.write_summary_sheet", broken_sheet):
            generate_excel_report(
                self.holdings, progress=self.progress,
            )

        errors = self.progress.get_errors()
        self.assertTrue(any("写入失败" in e for e in errors),
                        f"预期 sheet 写入错误，得到: {errors}")

    # ── ProgressReporter 默认值 ──

    def test_default_progress_reporter(self) -> None:
        """progress=None → 使用 SilentProgressReporter（不抛异常）。"""
        from src.python.report.excel_generator import generate_excel_report

        try:
            generate_excel_report(self.holdings)
        except Exception as e:
            self.fail(f"progress=None 时抛出异常: {e}")

    def test_timer_records(self) -> None:
        """模块耗时应有记录（_Timer 上下文管理器）。"""
        from src.python.report.excel_generator import generate_excel_report
        from src.python.report.progress import _timing_records

        _timing_records.clear()
        details = [_make_detail()]

        generate_excel_report(
            self.holdings, details=details,
            a_indices={}, us_indices={},
            progress=self.progress,
        )

        self.assertGreater(len(_timing_records), 0)


# ═══════════════════════════════════════════════════════════
#  ProgressReporter 单元测试（补充 test_progress.py 未覆盖）
# ═══════════════════════════════════════════════════════════


class TestProgressReporterCallSheet(unittest.TestCase):
    """ProgressReporter.call_sheet 的完整行为。"""

    def setUp(self) -> None:
        self.prog = SilentProgressReporter()

    def test_call_sheet_success(self) -> None:
        """fn 正常 → 返回 True。"""
        fn = MagicMock(return_value=42)
        result = self.prog.call_sheet("测试", fn, 1, 2, key="val")
        self.assertTrue(result)
        fn.assert_called_once_with(1, 2, key="val")

    def test_call_sheet_fn_none(self) -> None:
        """fn=None → 返回 False + add_error。"""
        result = self.prog.call_sheet("缺失模块", None)
        self.assertFalse(result)
        errors = self.prog.get_errors()
        self.assertTrue(any("缺失" in e for e in errors))

    def test_call_sheet_exception(self) -> None:
        """fn 抛出异常 → 返回 False + add_error。"""
        def _broken(*a, **kw):
            raise RuntimeError("写入失败")
        result = self.prog.call_sheet("损坏模块", _broken)
        self.assertFalse(result)
        errors = self.prog.get_errors()
        self.assertTrue(any("写入失败" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
