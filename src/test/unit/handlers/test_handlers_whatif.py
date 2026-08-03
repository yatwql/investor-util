"""TUI 调仓 What-if 模拟命令处理器单元测试。

测试 `_select_candidate_file`（目标持仓文件选择）与 `_cmd_whatif`（整体流程）。
全程 mock 文件系统与计算/输出函数，避免真实文件读写与报告产物残留。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/handlers/test_handlers_whatif.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.report.whatif_operations import WhatifRunResult

pytestmark = [pytest.mark.unit, pytest.mark.unit_ui]


class TestSelectCandidateFile(unittest.TestCase):
    """_select_candidate_file 目标持仓文件选择逻辑。"""

    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_excludes_base_and_auto_select(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
    ) -> None:
        """基准文件被排除后仅剩一个候选时自动选择。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/base.xlsx", "dummy_dir/target.xlsx"]
        out = __import__("io").StringIO()
        with patch("sys.stdout", out):
            result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertEqual(result, "dummy_dir/target.xlsx")
        self.assertIn("唯一找到", out.getvalue())

    @patch("builtins.input")
    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_only_base_no_candidate(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        """目录下只有基准文件时引导手动输入；直接回车取消返回 None。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/base.xlsx"]
        mock_input.return_value = ""
        out = __import__("io").StringIO()
        with patch("sys.stdout", out):
            result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertIsNone(result)
        self.assertIn("未找到", out.getvalue())

    @patch("builtins.input")
    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_only_base_manual_input_valid(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        """目录下只有基准文件时手动输入有效路径，返回该路径。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/base.xlsx"]
        mock_input.return_value = "/tmp/after.xlsx"
        with patch("src.python.tui.handlers_whatif.os.path.isfile", return_value=True):
            result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertEqual(result, "/tmp/after.xlsx")

    @patch("builtins.input")
    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_manual_input_not_exist_then_cancel(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        """手动输入的文件不存在时递归重输；再次回车取消返回 None。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/base.xlsx"]
        mock_input.side_effect = ["/no/such.xlsx", ""]
        with patch("src.python.tui.handlers_whatif.os.path.isfile", return_value=False):
            result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertIsNone(result)

    @patch("builtins.input")
    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_manual_input_eof(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        """手动输入时 input 引发 EOFError 返回 None。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/base.xlsx"]
        mock_input.side_effect = EOFError()
        with patch("src.python.tui.handlers_whatif.os.path.isfile", return_value=True):
            result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertIsNone(result)

    @patch("builtins.input")
    @patch("os.path.getmtime")
    @patch("os.path.getsize")
    @patch("src.python.tui.handlers_whatif.get_xlsx_info")
    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_multiple_user_select(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
        mock_info: MagicMock,
        mock_size: MagicMock,
        mock_mtime: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        """多个候选时用户输入编号选择。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/a.xlsx", "dummy_dir/b.xlsx", "dummy_dir/c.xlsx"]
        mock_info.return_value = {"accounts": 3}
        mock_input.return_value = "2"
        mock_size.return_value = 2048
        mock_mtime.return_value = 1000000.0
        result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertEqual(result, "dummy_dir/b.xlsx")

    @patch("builtins.input")
    @patch("os.path.getmtime")
    @patch("os.path.getsize")
    @patch("src.python.tui.handlers_whatif.get_xlsx_info")
    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_invalid_input(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
        mock_info: MagicMock,
        mock_size: MagicMock,
        mock_mtime: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        """无效编号输入返回 None。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/a.xlsx", "dummy_dir/b.xlsx"]
        mock_info.return_value = {"accounts": 3}
        mock_input.return_value = "abc"
        mock_size.return_value = 2048
        mock_mtime.return_value = 1000000.0
        result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertIsNone(result)

    @patch("builtins.input")
    @patch("os.path.getmtime")
    @patch("os.path.getsize")
    @patch("src.python.tui.handlers_whatif.get_xlsx_info")
    @patch("src.python.tui.handlers_whatif.list_xlsx_files")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    def test_eof_error(
        self,
        mock_config: MagicMock,
        mock_list: MagicMock,
        mock_info: MagicMock,
        mock_size: MagicMock,
        mock_mtime: MagicMock,
        mock_input: MagicMock,
    ) -> None:
        """input 引发 EOFError 时返回 None。"""
        from src.python.tui.handlers_whatif import _select_candidate_file

        mock_config.return_value = {"holdings_dir": "dummy_dir"}
        mock_list.return_value = ["dummy_dir/a.xlsx", "dummy_dir/b.xlsx"]
        mock_info.return_value = {"accounts": 3}
        mock_input.side_effect = EOFError()
        mock_size.return_value = 2048
        mock_mtime.return_value = 1000000.0
        result = _select_candidate_file("dummy_dir/base.xlsx")
        self.assertIsNone(result)


class TestCmdWhatif(unittest.TestCase):
    """_cmd_whatif 调仓模拟整体流程。"""

    @patch("src.python.tui.handlers_whatif.press_any_key")
    @patch("src.python.tui.handlers_whatif.get_config_cache")
    @patch("src.python.report.whatif_operations.run_whatif_simulation")
    @patch("src.python.tui.handlers_whatif.read_holdings")
    @patch("src.python.tui.handlers_whatif._select_candidate_file")
    @patch("src.python.tui.handlers_whatif.select_holdings_file")
    def test_success_flow(
        self,
        mock_select_base: MagicMock,
        mock_select_cand: MagicMock,
        mock_read: MagicMock,
        mock_run: MagicMock,
        mock_config: MagicMock,
        mock_key: MagicMock,
    ) -> None:
        """正常流程：两份持仓 → 共享层计算 → 输出报告路径。"""
        from src.python.tui.handlers_whatif import _cmd_whatif

        mock_config.return_value = {"output_dir": "reports"}
        mock_select_base.return_value = "dummy_dir/base.xlsx"
        mock_select_cand.return_value = "dummy_dir/target.xlsx"
        mock_read.side_effect = lambda p: [{"code": "000001", "name": "测试"}]
        mock_run.return_value = WhatifRunResult(ok=True, excel="/r/调仓模拟.xlsx", html="/r/调仓模拟.html")

        out = __import__("io").StringIO()
        with patch("sys.stdout", out):
            _cmd_whatif()

        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs["output_dir"], "reports")
        self.assertIn("调仓模拟报告已生成", out.getvalue())
        self.assertIn("调仓模拟.xlsx", out.getvalue())
        mock_key.assert_called_once()

    @patch("src.python.tui.handlers_whatif.press_any_key")
    @patch("src.python.report.whatif_operations.run_whatif_simulation")
    @patch("src.python.tui.handlers_whatif.select_holdings_file")
    def test_base_not_selected(
        self,
        mock_select_base: MagicMock,
        mock_run: MagicMock,
        mock_key: MagicMock,
    ) -> None:
        """基准文件未选择时提前返回，不触发共享层。"""
        from src.python.tui.handlers_whatif import _cmd_whatif

        mock_select_base.return_value = None
        with patch("sys.stdout", __import__("io").StringIO()):
            _cmd_whatif()
        mock_run.assert_not_called()
        mock_key.assert_not_called()

    @patch("src.python.tui.handlers_whatif.press_any_key")
    @patch("src.python.tui.handlers_whatif._select_candidate_file")
    @patch("src.python.tui.handlers_whatif.select_holdings_file")
    def test_candidate_not_selected(
        self,
        mock_select_base: MagicMock,
        mock_select_cand: MagicMock,
        mock_key: MagicMock,
    ) -> None:
        """目标文件未选择时提前返回，不生成报告。"""
        from src.python.tui.handlers_whatif import _cmd_whatif

        mock_select_base.return_value = "dummy_dir/base.xlsx"
        mock_select_cand.return_value = None
        with patch("sys.stdout", __import__("io").StringIO()):
            _cmd_whatif()
        mock_key.assert_not_called()

    @patch("src.python.tui.handlers_whatif.press_any_key")
    @patch("src.python.report.whatif_operations.run_whatif_simulation")
    @patch("src.python.tui.handlers_whatif.read_holdings")
    @patch("src.python.tui.handlers_whatif._select_candidate_file")
    @patch("src.python.tui.handlers_whatif.select_holdings_file")
    def test_empty_base_holdings(
        self,
        mock_select_base: MagicMock,
        mock_select_cand: MagicMock,
        mock_read: MagicMock,
        mock_run: MagicMock,
        mock_key: MagicMock,
    ) -> None:
        """基准持仓为空时提示错误，不触发共享层。"""
        from src.python.tui.handlers_whatif import _cmd_whatif

        mock_select_base.return_value = "dummy_dir/base.xlsx"
        mock_select_cand.return_value = "dummy_dir/target.xlsx"
        mock_read.side_effect = lambda p: []
        out = __import__("io").StringIO()
        with patch("sys.stdout", out):
            _cmd_whatif()
        mock_run.assert_not_called()
        self.assertIn("基准持仓读取失败或为空", out.getvalue())
        mock_key.assert_called_once()

    @patch("src.python.tui.handlers_whatif.press_any_key")
    @patch("src.python.report.whatif_operations.run_whatif_simulation")
    @patch("src.python.tui.handlers_whatif.read_holdings")
    @patch("src.python.tui.handlers_whatif._select_candidate_file")
    @patch("src.python.tui.handlers_whatif.select_holdings_file")
    def test_data_not_available(
        self,
        mock_select_base: MagicMock,
        mock_select_cand: MagicMock,
        mock_read: MagicMock,
        mock_run: MagicMock,
        mock_key: MagicMock,
    ) -> None:
        """共享层返回不可用时提示错误，不打印报告路径。"""
        from src.python.tui.handlers_whatif import _cmd_whatif

        mock_select_base.return_value = "dummy_dir/base.xlsx"
        mock_select_cand.return_value = "dummy_dir/target.xlsx"
        mock_read.side_effect = lambda p: [{"code": "000001", "name": "测试"}]
        mock_run.return_value = WhatifRunResult(ok=False, reason="两侧均为空")
        out = __import__("io").StringIO()
        with patch("sys.stdout", out):
            _cmd_whatif()
        mock_run.assert_called_once()
        self.assertIn("调仓对比数据不可用", out.getvalue())
        self.assertNotIn("调仓模拟报告已生成", out.getvalue())
        mock_key.assert_called_once()


if __name__ == "__main__":
    unittest.main()
