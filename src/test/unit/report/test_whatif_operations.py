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


if __name__ == "__main__":
    unittest.main()
