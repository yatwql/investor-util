"""HTML 报告生成模块单元测试。

测试目标：
  - write_html_report 中 a_indices/us_indices 以 dict 类型传入 generate_all_llm
  - 模板渲染使用独立 list 变量（不因 .values() 缺失崩溃）

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_html_writer -v
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from src.models import Holding


# ============================================================
#  write_html_report — LLM 内部调用路径
# ============================================================


class TestWriteHtmlReportLlmType(unittest.TestCase):
    """验证 enable_llm=True 且 llm_content=None 时 generate_all_llm 收到 dict。"""

    def setUp(self):
        self.holdings = [
            Holding("证券账户", "长江电力", "600900", 100, 50.0),
        ]
        self.mock_detail = MagicMock()
        self.mock_detail.market_value = 1000.0
        self.mock_detail.cost = 500.0
        self.mock_detail.profit = 500.0
        self.mock_detail.today_profit = 50.0
        self.mock_detail.name = "长江电力"
        self.mock_detail.code = "600900"
        self.mock_detail.price = 55.0
        self.mock_detail.yesterday_close = 54.0
        self.mock_detail.profit_rate = 1.0

    def _run_with_mocks(self, enable_llm=True):
        """用 ExitStack 统一管理 9 个补丁，调用 write_html_report 并返回 mock_llm。"""
        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.report.html_writer._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.report.html_writer.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.report.html_writer.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.report.html_writer.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.report.html_writer._build_category_data"))
            mock_status = stack.enter_context(patch("src.report.html_writer.price_update_status"))
            mock_perf = stack.enter_context(patch("src.report.html_writer._build_perf_data"))
            mock_llm = stack.enter_context(patch("src.llm_client.generate_all_llm"))
            mock_template = stack.enter_context(patch("src.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.mock_detail]
            mock_a_idx.return_value = {
                "sh000001": {"name": "上证指数", "price": 3120, "change": 10, "change_pct": 0.32},
            }
            mock_us_idx.return_value = {
                "gb_dji": {"name": "道琼斯", "price": 35000, "change": 100, "change_pct": 0.29},
            }
            mock_penetration.return_value = {}
            mock_cat.return_value = {}
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            mock_llm.return_value = ("<p>宏观</p>", "<p>复盘</p>")
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            from src.report.html_writer import write_html_report

            write_html_report(
                self.holdings,
                output_dir="reports",
                enable_llm=enable_llm,
                llm_content=None,
                include_news=False,
            )

        return mock_llm

    def test_generate_all_llm_receives_dict_indices(self):
        """LLM 内部调用路径：generate_all_llm 收到 dict 类型指数数据。"""
        mock_llm = self._run_with_mocks()

        mock_llm.assert_called_once()
        args, kwargs = mock_llm.call_args
        a_indices, us_indices = args[0], args[1]

        self.assertIsInstance(a_indices, dict,
                              "a_indices 应为 dict 类型（非 list）")
        self.assertIsInstance(us_indices, dict,
                              "us_indices 应为 dict 类型（非 list）")

        # 验证 .values() 安全运行
        self.assertIsNotNone(list(a_indices.values()))
        self.assertIsNotNone(list(us_indices.values()))

    def test_llm_path_no_crash_on_dict_values(self):
        """LLM 路径不会因 dict/list 类型不匹配崩溃。"""
        try:
            self._run_with_mocks()
        except AttributeError as e:
            if ".values" in str(e) or ".get" in str(e):
                self.fail(f"类型不匹配导致崩溃: {e}")
            raise

    def test_llm_path_not_called_when_disabled(self):
        """enable_llm=False → generate_all_llm 不被调用。"""
        mock_llm = self._run_with_mocks(enable_llm=False)
        mock_llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
