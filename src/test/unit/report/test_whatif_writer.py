"""调仓 What-if 报告输出（归档格式）单元测试。

测试 `write_whatif_excel` / `write_whatif_html` 的文件输出与归档惯例（对齐主报告）：
  - 最新版固定名 `调仓模拟.xlsx` / `调仓模拟.html`（每次覆盖为最新对比）
  - 归档版 `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.xlsx` / `.html`（日期子目录）
  - 输出后触发 `_cleanup_old_archives` 清理过期归档目录
  - Excel 最新版被占用时抛出 PermissionError；归档版写失败仅告警不中断

测试隔离：输出目录全部使用 `tmp_path` fixture，页签写入/模板渲染/Chart.js
资产复制均 mock，不触碰真实 `reports/`、配置与持仓文件。

运行：
  cd <项目根目录>
  pytest src/test/unit/report/test_whatif_writer.py -v
"""

from __future__ import annotations

import os
from unittest.mock import patch

import openpyxl
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _sample_data() -> dict:
    """构造最小数据契约 whatif_data（页签/模板被 mock，仅需可用性标记）。"""
    return {"available": True, "status": "ok"}


class TestWriteWhatifExcel:
    """write_whatif_excel 最新版固定名 + 日期目录归档。"""

    def test_writes_latest_and_date_archive(self, tmp_path) -> None:
        """同时写出最新版固定名与日期目录归档版，并触发清理。"""
        from src.python.report.whatif_writer import write_whatif_excel

        with (
            patch("src.python.report.whatif_writer.write_whatif_summary_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_category_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_changes_sheet"),
            patch("src.python.report.whatif_writer._cleanup_old_archives") as mock_cleanup,
        ):
            output_dir = str(tmp_path)
            result = write_whatif_excel(_sample_data(), output_dir)

        latest = tmp_path / "调仓模拟.xlsx"
        assert latest.is_file(), "最新版固定名文件应存在"
        assert result == os.path.abspath(str(latest))
        archives = list(tmp_path.glob("*/调仓模拟-*.xlsx"))
        assert len(archives) == 1, "应生成唯一日期目录归档版"
        mock_cleanup.assert_called_once_with(output_dir)

    def test_latest_save_permission_error_raises(self, tmp_path) -> None:
        """最新版文件被占用（PermissionError）时抛出，不静默。"""
        from src.python.report.whatif_writer import write_whatif_excel

        with (
            patch("src.python.report.whatif_writer.write_whatif_summary_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_category_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_changes_sheet"),
            patch("src.python.report.whatif_writer._cleanup_old_archives") as mock_cleanup,
            patch.object(openpyxl.Workbook, "save", side_effect=PermissionError("locked")),
        ):
            with pytest.raises(PermissionError):
                write_whatif_excel(_sample_data(), str(tmp_path))
        mock_cleanup.assert_not_called()

    def test_archive_save_failure_warns_not_raises(self, tmp_path) -> None:
        """归档版写失败仅告警，最新版正常返回。"""
        from src.python.report.whatif_writer import write_whatif_excel

        real_save = openpyxl.Workbook.save
        save_calls = {"n": 0}

        def fake_save(instance, filename) -> None:
            """第 1 次（最新版）真实写盘，第 2 次（归档版）模拟占用失败。"""
            save_calls["n"] += 1
            if save_calls["n"] == 1:
                return real_save(instance, filename)
            raise PermissionError("archive locked")

        with (
            patch("src.python.report.whatif_writer.write_whatif_summary_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_category_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_changes_sheet"),
            patch("src.python.report.whatif_writer._cleanup_old_archives") as mock_cleanup,
            patch.object(openpyxl.Workbook, "save", fake_save),
        ):
            output_dir = str(tmp_path)
            result = write_whatif_excel(_sample_data(), output_dir)

        assert (tmp_path / "调仓模拟.xlsx").is_file()
        assert result == os.path.abspath(str(tmp_path / "调仓模拟.xlsx"))
        mock_cleanup.assert_called_once_with(output_dir)


class TestWriteWhatifExcelSheets:
    """write_whatif_excel 固定 4 页签结构。"""

    def test_writes_four_sheets(self, tmp_path) -> None:
        """工作簿页签：摘要 / 分类配置 / 持仓变动明细 / 时序回测。"""
        from src.python.report.whatif_writer import write_whatif_excel

        with (
            patch("src.python.report.whatif_writer.write_whatif_summary_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_category_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_changes_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_backtest_sheet") as mock_bt,
            patch("src.python.report.whatif_writer._cleanup_old_archives"),
        ):
            write_whatif_excel(_sample_data(), str(tmp_path))

        wb = openpyxl.load_workbook(tmp_path / "调仓模拟.xlsx")
        assert wb.sheetnames == ["调仓摘要", "分类配置对比", "持仓变动明细", "时序回测"]
        mock_bt.assert_called_once()


def _full_bt_data() -> dict:
    """构造含可用 backtest 的完整数据契约。"""
    return {
        "available": True,
        "backtest": {
            "available": True,
            "status": "ok",
            "effective_date": "2026-07-01",
            "reason": "",
            "metrics": [{"key": "period_return_pct", "label": "区间收益"}],
            "series": {
                "labels": ["2026-07-01", "2026-07-02"],
                "base": [100.0, 124.0],
                "candidate": [100.0, 148.0],
                "base_drawdown": [0.0, 0.0],
                "candidate_drawdown": [0.0, 0.0],
            },
        },
    }


class TestTrimBacktestChartData:
    """_trim_whatif_backtest_chart_data 数据最小化。"""

    def test_trim_payload_only_series_fields(self) -> None:
        """只透传 available/effective_date/series，不携带 metrics/reason。"""
        from src.python.report.whatif_writer import _trim_whatif_backtest_chart_data

        trimmed = _trim_whatif_backtest_chart_data(_full_bt_data())
        assert trimmed is not None
        assert set(trimmed.keys()) == {"available", "effective_date", "series"}
        assert "metrics" not in trimmed
        assert "reason" not in trimmed
        assert trimmed["effective_date"] == "2026-07-01"
        assert trimmed["series"]["labels"] == ["2026-07-01", "2026-07-02"]
        assert trimmed["series"]["base"] == [100.0, 124.0]

    def test_trim_none_when_unavailable(self) -> None:
        """回测缺失/不可用/无序列 → None（模板不输出数据段）。"""
        from src.python.report.whatif_writer import _trim_whatif_backtest_chart_data

        assert _trim_whatif_backtest_chart_data(None) is None
        assert _trim_whatif_backtest_chart_data({"available": True}) is None

        degraded = _full_bt_data()
        degraded["backtest"]["available"] = False
        assert _trim_whatif_backtest_chart_data(degraded) is None

        empty_series = _full_bt_data()
        empty_series["backtest"]["series"] = {"labels": []}
        assert _trim_whatif_backtest_chart_data(empty_series) is None


class TestRenderWhatifHtmlContext:
    """render_whatif_html 向模板透传裁剪后的回测图表数据。"""

    def test_passes_backtest_chart_data(self) -> None:
        from unittest.mock import MagicMock

        from src.python.report.whatif_writer import render_whatif_html

        with patch("src.python.report.html_jinja_env._ENV") as mock_env:
            tmpl = MagicMock()
            tmpl.render.return_value = "<html/>"
            mock_env.get_template.return_value = tmpl

            render_whatif_html(_full_bt_data(), "2026-08-03 00:00:00")

        kwargs = tmpl.render.call_args.kwargs
        assert "whatif_backtest_chart_data" in kwargs
        payload = kwargs["whatif_backtest_chart_data"]
        assert payload is not None
        assert set(payload.keys()) == {"available", "effective_date", "series"}

    def test_passes_none_when_no_backtest(self) -> None:
        """未指定生效日/无回测 → 裁剪结果 None。"""
        from unittest.mock import MagicMock

        from src.python.report.whatif_writer import render_whatif_html

        with patch("src.python.report.html_jinja_env._ENV") as mock_env:
            tmpl = MagicMock()
            tmpl.render.return_value = "<html/>"
            mock_env.get_template.return_value = tmpl

            render_whatif_html({"available": True}, "2026-08-03 00:00:00")

        assert tmpl.render.call_args.kwargs["whatif_backtest_chart_data"] is None


class TestWhatifFeasibilitySection:
    """HTML 申购受限提示节（⑦）：命中渲染、缺席整节不出现。"""

    def _data(self, with_note: bool) -> dict:
        data = {"available": True, "changes": [], "summary": [], "categories": [], "stats": {}}
        if with_note:
            data["feasibility"] = [
                {
                    "code": "519674",
                    "name": "易方达蓝筹",
                    "action": "新增",
                    "status": "限大额",
                    "kind": "limited",
                    "amount": 1000.0,
                    "days": 10,
                    "feasible": True,
                    "limit_text": "100",
                    "next_open_text": "",
                    "note_text": "限大额，日限 100 元，预计需 10 个交易日（估算·以渠道显示为准）",
                }
            ]
        return data

    def test_note_section_rendered_when_present(self):
        from src.python.report.whatif_writer import render_whatif_html

        html = render_whatif_html(self._data(with_note=True), "2026-10-03 00:00:00")
        assert "申购受限提示" in html
        assert "易方达蓝筹" in html
        assert "预计需 10 个交易日" in html

    def test_note_section_absent_when_degraded(self):
        from src.python.report.whatif_writer import render_whatif_html

        html = render_whatif_html(self._data(with_note=False), "2026-10-03 00:00:00")
        assert "申购受限提示" not in html


class TestWriteWhatifHtml:
    """write_whatif_html 最新版固定名 + 日期目录归档。"""

    def test_writes_latest_and_date_archive(self, tmp_path) -> None:
        """最新版固定名 + 日期目录归档版，两者内容一致，并触发清理。"""
        from src.python.report.whatif_writer import write_whatif_html

        with (
            patch(
                "src.python.report.whatif_writer.render_whatif_html",
                return_value="<html>调仓模拟</html>",
            ) as mock_render,
            patch("src.python.report.whatif_writer._copy_js_assets") as mock_copy,
            patch(
                "src.python.report.whatif_writer._inline_js_assets",
                side_effect=lambda html: html,
            ) as mock_inline,
            patch("src.python.report.whatif_writer._cleanup_old_archives") as mock_cleanup,
        ):
            output_dir = str(tmp_path)
            result = write_whatif_html(_sample_data(), output_dir)

        latest = tmp_path / "调仓模拟.html"
        assert latest.is_file(), "最新版固定名文件应存在"
        assert result == os.path.abspath(str(latest))
        archives = list(tmp_path.glob("*/调仓模拟-*.html"))
        assert len(archives) == 1, "应生成唯一日期目录归档版"
        assert latest.read_text(encoding="utf-8") == "<html>调仓模拟</html>"
        assert archives[0].read_text(encoding="utf-8") == "<html>调仓模拟</html>"
        mock_render.assert_called_once()
        mock_copy.assert_called_once_with(output_dir)
        mock_inline.assert_called_once_with("<html>调仓模拟</html>")
        mock_cleanup.assert_called_once_with(output_dir)


def _rich_data(with_cost: bool = False) -> dict:
    """可渲染 whatif_data（区段齐全），可选挂载 cost 面板。"""
    data = {
        "available": True,
        "status": "ok",
        "base_file": "before.xlsx",
        "candidate_file": "after.xlsx",
        "base": {"total_cost": 30000.0, "total_shares": 3000.0, "holding_count": 2, "hhi": 0.5},
        "candidate": {"total_cost": 29000.0, "total_shares": 2900.0, "holding_count": 2, "hhi": 0.6},
        "summary": [],
        "categories": [],
        "changes": [],
        "stats": {"added": 0, "removed": 0, "increased": 0, "decreased": 0, "unchanged": 0},
    }
    if with_cost:
        from src.test.unit.report.test_whatif_sheet import _cost_data

        data["cost"] = _cost_data()["cost"]
    return data


class TestCostSheetWiring:
    """交易成本对比页签的条件挂载（开关关闭 → 页签集不变）。"""

    def test_excel_adds_cost_sheet_when_cost_present(self, tmp_path) -> None:
        """带 cost → 追加「交易成本对比」页签（真实写入内容）。"""
        from src.python.report.whatif_writer import write_whatif_excel

        with (
            patch("src.python.report.whatif_writer.write_whatif_summary_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_category_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_changes_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_backtest_sheet"),
            patch("src.python.report.whatif_writer._cleanup_old_archives"),
        ):
            result = write_whatif_excel(_rich_data(with_cost=True), str(tmp_path))

        wb = openpyxl.load_workbook(result)
        assert "交易成本对比" in wb.sheetnames
        assert wb.sheetnames.index("交易成本对比") > wb.sheetnames.index("时序回测"), "成本页在回测页之后"

    def test_excel_without_cost_keeps_sheet_set(self, tmp_path) -> None:
        """无 cost（开关关闭）→ 不追加成本页签，页签集与现状一致。"""
        from src.python.report.whatif_writer import write_whatif_excel

        with (
            patch("src.python.report.whatif_writer.write_whatif_summary_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_category_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_changes_sheet"),
            patch("src.python.report.whatif_writer.write_whatif_backtest_sheet"),
            patch("src.python.report.whatif_writer._cleanup_old_archives"),
        ):
            result = write_whatif_excel(_rich_data(with_cost=False), str(tmp_path))

        wb = openpyxl.load_workbook(result)
        assert "交易成本对比" not in wb.sheetnames


class TestCostChartTrim:
    """_trim_whatif_cost_chart_data 只透传三线所需字段。"""

    def test_none_without_cost_or_chart(self) -> None:
        from src.python.report.whatif_writer import _trim_whatif_cost_chart_data

        assert _trim_whatif_cost_chart_data(None) is None
        assert _trim_whatif_cost_chart_data(_rich_data()) is None
        data = _rich_data(with_cost=True)
        data["cost"]["chart"] = None
        assert _trim_whatif_cost_chart_data(data) is None

    def test_passes_only_chart_fields(self) -> None:
        from src.python.report.whatif_writer import _trim_whatif_cost_chart_data

        trimmed = _trim_whatif_cost_chart_data(_rich_data(with_cost=True))
        assert trimmed is not None
        assert set(trimmed) == {
            "labels",
            "base",
            "candidate_after",
            "candidate_before",
            "benchmark",
            "benchmark_name",
            "impact",
        }
        assert trimmed["benchmark_name"] == "沪深300"
        assert trimmed["impact"]["delta_pct_points"] == -0.12


class TestCostSectionRender:
    """HTML 成本区段条件渲染与说明区段动态编号。"""

    def test_render_without_cost_no_section(self) -> None:
        """cost 键缺席 → 无成本区段/图表画布，说明区保持⑧（关态零变化）。"""
        from src.python.report.whatif_writer import render_whatif_html

        html = render_whatif_html(_rich_data(with_cost=False), "2026-10-07 10:00:00")
        assert "⑧ 交易成本对比" not in html
        assert "chart_whatif_cost_nav" not in html
        assert "whatif-cost-chart-data" not in html
        assert "⑧ 说明" in html
        assert "⑨ 说明" not in html

    def test_render_with_cost_section_and_renumbered_note(self) -> None:
        """cost 在场 → 追加⑧成本区段，说明区顺延⑨，输出图表数据段。"""
        from src.python.report.whatif_writer import render_whatif_html

        html = render_whatif_html(_rich_data(with_cost=True), "2026-10-07 10:00:00")
        assert "⑧ 交易成本对比" in html
        assert '<div class="section-title">⑨ 说明</div>' in html
        assert '<div class="section-title">⑧ 说明</div>' not in html
        assert "whatif-cost-chart-data" in html
        assert "chart_whatif_cost_nav" in html
        assert "sh000300" in html  # 基准三线参照入渲染

    def test_render_cost_without_chart_skips_data_segment(self) -> None:
        """面板无 chart（如未启用回测）→ 区段照常但不出图表数据段。"""
        from src.python.report.whatif_writer import render_whatif_html

        data = _rich_data(with_cost=True)
        data["cost"]["chart"] = None
        html = render_whatif_html(data, "2026-10-07 10:00:00")
        assert "⑧ 交易成本对比" in html
        assert "whatif-cost-chart-data" not in html


class TestCostCrossEndConsistency:
    """双端渲染一致：同一 cost 契约 → Excel 与 HTML 的成本合计数字同源同值。"""

    @staticmethod
    def _excel_totals(data: dict, tmp_path) -> dict:
        from src.python.report.whatif_sheet import write_whatif_cost_sheet

        wb = openpyxl.Workbook()
        write_whatif_cost_sheet(wb.active, data)
        totals: dict = {}
        rows = list(wb.active.iter_rows(values_only=True))
        for row in rows:
            cells = [c for c in row if c is not None]
            if cells and cells[0] in ("申购费合计", "赎回费合计", "交易总成本") and len(cells) > 1:
                totals[cells[0]] = float(cells[1])
        return totals

    @staticmethod
    def _html_totals(html: str) -> dict:
        import re

        totals: dict = {}
        for label in ("申购费合计", "赎回费合计", "交易总成本"):
            m = re.search(rf"<h3>{label}</h3>\s*<div class=\"value\">([^<]+)</div>", html)
            assert m, f"HTML 应含 {label} 卡片"
            nums = re.sub(r"[^0-9.\-]", "", m.group(1))
            totals[label] = float(nums)
        return totals

    def test_totals_identical_in_excel_and_html(self, tmp_path) -> None:
        """双端合计逐值相等（同一契约、同一渲染源，无二次计算）。"""
        from src.python.report.whatif_writer import render_whatif_html

        data = _rich_data(with_cost=True)
        excel_totals = self._excel_totals(data, tmp_path)
        html_totals = self._html_totals(render_whatif_html(data, "2026-10-07 10:00:00"))
        assert set(excel_totals) == set(html_totals)
        for key in excel_totals:
            assert excel_totals[key] == html_totals[key], f"{key} 双端不一致"
        assert excel_totals["交易总成本"] == 115.0
