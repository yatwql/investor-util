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
