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
    """构造最小 C19 契约 whatif_data（页签/模板被 mock，仅需可用性标记）。"""
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
    """构造含可用 backtest 的完整 C19 契约。"""
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
    """_trim_whatif_backtest_chart_data R9 数据最小化。"""

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
        mock_cleanup.assert_called_once_with(output_dir)
