"""调仓 What-if 报告输出（归档格式）单元测试。

测试 `write_whatif_excel` / `write_whatif_html` 的文件输出与归档惯例（对齐主报告）：
  - 最新版固定名 `调仓模拟.xlsx` / `调仓模拟.html`（每次覆盖为最新对比）
  - 归档版 `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.xlsx` / `.html`（日期子目录）
  - 输出后触发 `_cleanup_old_archives` 清理过期归档目录
  - Excel 最新版被占用时抛出 PermissionError；归档版写失败仅告警不中断

测试隔离：输出目录全部使用 `tmp_path` fixture，页签写入/模板渲染/Chart.js
资产复制均 mock，不触碰真实 `reports/`、配置与持仓文件。

另覆盖匿名化接入（anonymization.mode × 双产物）：字段层代号映射、
渲染点 `| anon_code`、产物清扫（含金额串边界安全）、summary 拦截点、
off 模式零变化恒等回归。

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


# ── 匿名化接入（anonymization.mode × 双产物回归） ────────────────────


_REAL_NAME_TOKENS = ("贵州茅台", "招商银行", "宁德时代", "广发多因子灵活配置混合", "某债券基金", "长江电力")
_REAL_CODE_TOKENS = ("600519", "600036", "300750", "002943", "096001", "600900")
_ANON_NOW = "2026-10-09 00:00:00"


def _patch_mode(monkeypatch, mode: str) -> None:
    """mock 匿名模式读取（不触碰真实配置文件）。"""
    monkeypatch.setattr("src.python.config.anonymizer.get_anonymization_mode", lambda: mode)


def _identity_data() -> dict:
    """含身份面（changes/legs/feasibility）与聚合面（summary/categories/cost）的契约夹具。"""
    data = _rich_data(with_cost=True)
    data["base_file"] = "基准组合.xlsx"
    data["candidate_file"] = "目标组合.xlsx"
    data["summary"] = [
        {
            "key": "total_cost",
            "label": "总成本(元)",
            "unit": "money",
            "base": 30000.0,
            "candidate": 30000.0,
            "delta": 0.0,
            "arrow": "→",
        },
    ]
    data["categories"] = [
        {
            "key": "stock",
            "label": "股票",
            "base_cost": 30000.0,
            "cand_cost": 30000.0,
            "base_weight": 100.0,
            "cand_weight": 100.0,
            "delta_pct": 0.0,
        },
    ]
    data["stats"] = {"added": 1, "removed": 0, "increased": 0, "decreased": 1, "unchanged": 1}
    data["changes"] = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "action": "减仓",
            "base_shares": 100.0,
            "cand_shares": 50.0,
            "shares_diff": -50.0,
            "base_cost": 20000.0,
            "cand_cost": 10000.0,
            "cost_diff": -10000.0,
            "base_weight": 50.0,
            "cand_weight": 25.0,
            "weight_delta_pct": -25.0,
        },
        {
            "code": "600036",
            "name": "招商银行",
            "action": "不变",
            "base_shares": 100.0,
            "cand_shares": 100.0,
            "shares_diff": 0.0,
            "base_cost": 10000.0,
            "cand_cost": 10000.0,
            "cost_diff": 0.0,
            "base_weight": 25.0,
            "cand_weight": 25.0,
            "weight_delta_pct": 0.0,
        },
        {
            "code": "300750",
            "name": "宁德时代",
            "action": "新增",
            "base_shares": 0.0,
            "cand_shares": 100.0,
            "shares_diff": 100.0,
            "base_cost": 0.0,
            "cand_cost": 10000.0,
            "cost_diff": 10000.0,
            "base_weight": 0.0,
            "cand_weight": 25.0,
            "weight_delta_pct": 25.0,
        },
    ]
    data["feasibility"] = [
        {
            "code": "300750",
            "name": "宁德时代",
            "action": "新增",
            "status": "限大额",
            "kind": "purchase_limit",
            "amount": 10000.0,
            "days": 3,
            "feasible": True,
            "limit_text": "100",
            "next_open_text": "",
            "note_text": "限大额，日限 100 元，预计需 3 个交易日（估算·以渠道显示为准）",
        },
    ]
    return data


def _excel_strings(path) -> list[str]:
    """工作簿全部字符串单元格值（产物文本面）。"""
    wb = openpyxl.load_workbook(path)
    return [
        str(cell.value)
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value
    ]


def _excel_numbers(path) -> list[float]:
    """工作簿全部数值单元格值（数值面，金额不误伤断言用）。"""
    wb = openpyxl.load_workbook(path)
    return [
        cell.value
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    ]


def _excel_cells(path) -> dict[str, list]:
    """按页签顺序展开的全单元格值（off 模式内容恒等比对用）。"""
    wb = openpyxl.load_workbook(path)
    return {ws.title: [cell.value for row in ws.iter_rows() for cell in row] for ws in wb.worksheets}


class TestWhatifFieldLayerAnonymization:
    """装配边字段层：off/summary 恒等原样，code_display/full 匿名且派生容器同代号。"""

    def test_off_mode_returns_input_identity(self):
        """off → 原对象恒等返回（零开销）。"""
        from src.python.report.whatif_writer import _anonymize_whatif_data

        data = _identity_data()
        assert _anonymize_whatif_data(data, mode="off") is data

    def test_summary_passes_contract_through(self):
        """summary → 契约原样（差异行不适配大类折叠，拦截在渲染/写入层）。"""
        from src.python.report.whatif_writer import _anonymize_whatif_data

        data = _identity_data()
        assert _anonymize_whatif_data(data, mode="summary") is data

    @pytest.mark.parametrize("mode", ["code_display", "full_anonymous"])
    def test_names_replaced_with_shared_alias(self, mode):
        """changes 主明细与 legs/feasibility 派生容器共用同一代号映射；输入不被就地改写。"""
        from src.python.report.whatif_writer import _anonymize_whatif_data, _whatif_anonymization_maps

        data = _identity_data()
        alias_map, _ = _whatif_anonymization_maps(data, mode=mode)
        anon = _anonymize_whatif_data(data, mode=mode)

        assert anon is not data
        pairs = (
            list(zip(data["changes"], anon["changes"]))
            + list(zip(data["cost"]["trade_cost"]["legs"], anon["cost"]["trade_cost"]["legs"]))
            + list(zip(data["feasibility"], anon["feasibility"]))
        )
        for src, dst in pairs:
            assert dst["name"] == alias_map[src["name"]], "派生容器与主明细代号不一致"
        # 输入契约未被就地修改
        assert data["changes"][0]["name"] == "贵州茅台"
        assert data["feasibility"][0]["name"] == "宁德时代"
        assert data["cost"]["trade_cost"]["legs"][0]["name"] == "广发多因子灵活配置混合"

    @pytest.mark.parametrize("mode", ["code_display", "full_anonymous"])
    def test_contract_keys_and_numeric_face_unchanged(self, mode):
        """键集与数值面原样：匿名化不改 whatif 计算结果，代码保留真值供键控链路。"""
        from src.python.report.whatif_writer import _anonymize_whatif_data

        data = _identity_data()
        anon = _anonymize_whatif_data(data, mode=mode)
        for src, dst in zip(data["changes"], anon["changes"]):
            assert set(dst) == set(src)
            assert dst["base_cost"] == src["base_cost"]
            assert dst["cand_cost"] == src["cand_cost"]
            assert dst["code"] == src["code"]

    def test_full_strips_derived_detail_keys(self):
        """full 的明细派生键（profit/profit_rate）不落到 whatif 契约上。"""
        from src.python.report.whatif_writer import _anonymize_whatif_data

        anon = _anonymize_whatif_data(_identity_data(), mode="full_anonymous")
        row = anon["changes"][0]
        assert "profit" not in row
        assert "profit_rate" not in row
        assert row["cand_cost"] == 10000.0  # 千位模糊不落到 whatif 数值面


class TestWhatifAnonymizationMaps:
    """渲染点/清扫层单源映射：名称映射不含代码，代码掩码只在折叠模式构建。"""

    def test_off_mode_builds_empty_maps(self):
        from src.python.report.whatif_writer import _whatif_anonymization_maps

        alias_map, code_map = _whatif_anonymization_maps(_identity_data(), mode="off")
        assert alias_map == {}
        assert code_map == {}

    def test_code_display_names_only(self):
        from src.python.report.whatif_writer import _whatif_anonymization_maps

        alias_map, code_map = _whatif_anonymization_maps(_identity_data(), mode="code_display")
        assert "贵州茅台" in alias_map
        assert not any(code in alias_map for code in _REAL_CODE_TOKENS)  # 自由文本清扫不含代码
        assert code_map == {}  # code_display 契约保留真码 → 渲染点/清扫不掩

    def test_full_builds_code_display_map(self):
        from src.python.report.whatif_writer import _whatif_anonymization_maps

        _, code_map = _whatif_anonymization_maps(_identity_data(), mode="full_anonymous")
        for code in _REAL_CODE_TOKENS:
            assert code_map[code] == "000XXX"


class TestWhatifHtmlAnonymization:
    """HTML 渲染点与产物：字段层 + | anon_code + 自由文本清扫。"""

    @pytest.mark.parametrize("mode", ["code_display", "full_anonymous"])
    def test_render_hides_real_names(self, mode, monkeypatch):
        _patch_mode(monkeypatch, mode)
        from src.python.report.whatif_writer import render_whatif_html

        html = render_whatif_html(_identity_data(), _ANON_NOW)
        for token in _REAL_NAME_TOKENS:
            assert token not in html, f"render 泄漏真实名称: {token}"
        assert "品种A" in html  # 代号正向对照
        assert "99000.00" in html  # 数值面原值（impact 金额不模糊）
        if mode == "full_anonymous":
            for token in _REAL_CODE_TOKENS:
                assert token not in html, f"render 泄漏真实代码: {token}"
            assert "000XXX" in html  # anon_code 渲染点生效
        else:
            assert "600519" in html  # code_display 契约保留真码（防过度掩码）

    def test_off_mode_render_byte_identical_to_bypass(self, monkeypatch):
        """off 模式渲染与匿名化完全旁路逐字节一致（零变化回归）。"""
        from src.python.report.whatif_writer import render_whatif_html

        data = _identity_data()
        _patch_mode(monkeypatch, "off")
        html_off = render_whatif_html(data, _ANON_NOW)
        with (
            patch(
                "src.python.report.whatif_writer._anonymize_whatif_data",
                side_effect=lambda d, mode=None: d,
            ),
            patch("src.python.report.whatif_writer._whatif_anonymization_maps", return_value=({}, {})),
        ):
            html_bypass = render_whatif_html(data, _ANON_NOW)

        assert html_off == html_bypass
        for token in _REAL_NAME_TOKENS + _REAL_CODE_TOKENS:
            assert token in html_off, f"off 模式应原样: {token}"
        assert "品种A" not in html_off
        assert "000XXX" not in html_off

    def test_summary_interception(self, monkeypatch):
        """summary 拦截：明细区空态/缺席，聚合面保留，身份面零出现。"""
        from src.python.report.whatif_writer import render_whatif_html

        _patch_mode(monkeypatch, "summary")
        html = render_whatif_html(_identity_data(), _ANON_NOW)
        assert "暂无单条持仓变动明细" in html  # ⑥ 明细区空态
        assert "申购受限提示" not in html  # ⑦ 受限节整节缺席
        assert "费率来源" not in html  # ⑧ 逐腿明细表不出
        assert "分类配置对比" in html  # ⑤ 大类聚合面保留
        assert "申购费合计" in html  # 成本汇总聚合面保留
        assert "总成本(元)" in html
        for token in _REAL_NAME_TOKENS + _REAL_CODE_TOKENS:
            assert token not in html, f"summary 泄漏身份面: {token}"

    def test_html_product_sweep_covers_derived_surface(self, tmp_path, monkeypatch):
        """产物清扫：字段层未覆盖的派生面（文件名）归代号；金额串内真码子串不误伤。"""
        from pathlib import Path

        from src.python.report.whatif_writer import write_whatif_html

        _patch_mode(monkeypatch, "full_anonymous")
        data = _identity_data()
        data["base_file"] = "贵州茅台持仓.xlsx"  # 字段层不覆盖 → 靠产物清扫兜底
        data["cost"]["impact"]["cand_t0_value"] = 1600900.0  # 金额串含真码 600900 子串
        with (
            patch("src.python.report.whatif_writer._copy_js_assets"),
            patch("src.python.report.whatif_writer._inline_js_assets", side_effect=lambda html: html),
        ):
            path = write_whatif_html(data, str(tmp_path))
        html = Path(path).read_text(encoding="utf-8")

        assert "贵州茅台持仓" not in html  # 清扫层覆盖派生面
        assert "1600900.00" in html  # 边界安全：金额保留原值
        # 金额的展示串与 JSON 数值串均含真码子串，属刻意保留面（数值不被改写）
        swept = html.replace("1600900.00", "").replace("1600900.0", "")
        for token in _REAL_NAME_TOKENS + _REAL_CODE_TOKENS:
            assert token not in swept, f"HTML 产物泄漏身份面: {token}"
        assert "000XXX" in html


class TestWhatifExcelAnonymization:
    """Excel 产物：字符串单元格清扫 + 边界安全代码替换 + 数值单元格不误伤。"""

    @pytest.mark.parametrize("mode", ["code_display", "full_anonymous"])
    def test_excel_hides_identity_keeps_numbers(self, mode, tmp_path, monkeypatch):
        from src.python.report.whatif_writer import write_whatif_excel

        _patch_mode(monkeypatch, mode)
        data = _identity_data()
        data["base_file"] = "贵州茅台持仓.xlsx"  # 靠产物清扫兜底
        path = write_whatif_excel(data, str(tmp_path))
        strings = _excel_strings(path)

        for token in _REAL_NAME_TOKENS:
            assert not any(token in s for s in strings), f"Excel 泄漏真实名称: {token}"
        if mode == "full_anonymous":
            for token in _REAL_CODE_TOKENS:
                assert not any(token in s for s in strings), f"Excel 泄漏真实代码: {token}"
            assert any("000XXX" in s for s in strings)
        else:
            assert any("600519" in s for s in strings)  # code_display 契约保留真码
        numbers = _excel_numbers(path)
        assert 115.0 in numbers  # 交易总成本数值原样
        assert 10000.0 in numbers  # 变动明细成本数值原样

    def test_excel_amount_with_embedded_code_not_damaged(self, tmp_path, monkeypatch):
        """字符串金额含真码子串 → 边界安全替换不误伤；独立代码单元格仍折叠。"""
        from src.python.report.whatif_writer import write_whatif_excel

        _patch_mode(monkeypatch, "full_anonymous")
        data = _identity_data()
        data["cost"]["impact"]["cand_t0_value"] = 1600900.0
        path = write_whatif_excel(data, str(tmp_path))
        strings = _excel_strings(path)

        assert any("1600900.00" in s for s in strings)  # 金额原样（不误伤）
        standalone = {s.strip() for s in strings}
        for token in _REAL_CODE_TOKENS:
            assert token not in standalone, "独立代码单元格应折叠为掩码"
        assert any("000XXX" in s for s in strings)

    def test_summary_placeholder_and_aggregate_surface(self, tmp_path, monkeypatch):
        """summary 拦截：明细页占位、逐腿明细不出，分类配置对比聚合面仍在。"""
        from src.python.report.whatif_writer import write_whatif_excel

        _patch_mode(monkeypatch, "summary")
        path = write_whatif_excel(_identity_data(), str(tmp_path))
        strings = _excel_strings(path)

        assert any("暂无单条持仓变动明细" in s for s in strings)  # 明细页占位
        assert not any("交易腿明细" in s for s in strings)  # 逐腿明细不出
        assert any("资产大类" in s for s in strings)  # 分类配置对比聚合面保留
        assert any("申购费合计" in s for s in strings)  # 成本汇总聚合面保留
        for token in _REAL_NAME_TOKENS + _REAL_CODE_TOKENS:
            assert not any(token in s for s in strings), f"summary Excel 泄漏身份面: {token}"

    def test_off_mode_excel_identical_to_bypass(self, tmp_path, monkeypatch):
        """off 模式产物与匿名化完全旁路内容恒等（零变化回归）。"""
        from src.python.report.whatif_writer import write_whatif_excel

        _patch_mode(monkeypatch, "off")
        data = _identity_data()
        path_a = write_whatif_excel(data, str(tmp_path / "with_seam"))
        with (
            patch(
                "src.python.report.whatif_writer._anonymize_whatif_data",
                side_effect=lambda d, mode=None: d,
            ),
            patch("src.python.report.whatif_writer._whatif_anonymization_maps", return_value=({}, {})),
        ):
            path_b = write_whatif_excel(data, str(tmp_path / "bypass"))

        assert _excel_cells(path_a) == _excel_cells(path_b)
        strings = _excel_strings(path_a)
        for token in _REAL_NAME_TOKENS + _REAL_CODE_TOKENS:
            assert any(token in s for s in strings), f"off 模式应原样: {token}"
        assert not any("000XXX" in s for s in strings)
