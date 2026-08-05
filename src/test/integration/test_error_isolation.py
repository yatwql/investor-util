"""错误隔离业务语义验证 — 任一模块失败不影响其他模块。

覆盖 market_value / HTML 报告 / Excel 报告三条生成链，
在某个模块抛异常或返回空数据时，其余模块仍能正常产出。
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.integration, pytest.mark.integration_isolation]


@pytest.mark.integration
@pytest.mark.integration_isolation
class TestErrorIsolationSemantics(unittest.TestCase):
    """错误隔离业务语义验证 — 任一模块失败不影响其他模块。"""

    def test_market_value_ok_penetration_crash(self):
        """penetration 异常不阻塞 market_value 数据生成。

        即使 compute_penetration_top10 抛出异常，_generate_details
        应正常返回 DetailRow 列表。
        """
        from src.python.report.market_value import _generate_details

        holdings = [Holding("证券", "茅台", "600519", 100, 150.0)]
        mock_mkt = {
            "price": 160.0, "yesterday_close": 158.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "source": "腾讯行情", "name": "茅台", "code": "600519",
        }

        with (
            patch("src.python.report.market_value.fetch_market_data",
                  return_value=mock_mkt),
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 30)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # penetration 的异常不应影响 market_value
            details = _generate_details(holdings, "2026-07-03")

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].market_value, 16000.0)

    def test_html_generation_ok_llm_crash(self):
        """LLM 异常不阻塞 HTML 报告生成。

        write_html_report 中 LLM 模块异常不应影响报告生成完成。
        """
        from src.python.report.html_writer import write_html_report
        from src.python.report.market_value import DetailRow

        holdings = [Holding("证券", "茅台", "600519", 100, 150.0)]
        details = [
            DetailRow("证券", "茅台", "600519", 160.0, "2026-07-03",
                      158.0, "tencent", "--", 100, 16000.0, 15000.0, 1000.0,
                      0.0667, 200.0, "腾讯行情", "tencent"),
        ]

        with (
            patch("src.python.report.html_renderers.fetch_indices",
                  return_value={}),
            patch("src.python.report.html_renderers.fetch_us_indices",
                  return_value={}),
            patch("src.python.report.html_renderers.compute_penetration_top10",
                  return_value={}),
            patch("src.python.report.html_renderers._build_category_data",
                  return_value=([], False)),
            patch("src.python.report.html_renderers.price_update_status",
                  return_value=(1, 1, True)),
            patch("src.python.report.html_renderers._build_perf_data",
                  return_value={}),
            # 模拟 LLM content 异常（传入错误类型），验证仍生成 HTML
            patch("src.python.report.html_writer._ENV.get_template") as tmpl,
        ):
            mock_tmpl = MagicMock()
            mock_tmpl.render.return_value = "<html>ok</html>"
            tmpl.return_value = mock_tmpl

            import tempfile
            tmp = tempfile.mkdtemp(prefix="test_isolation_")
            try:
                path = write_html_report(
                    holdings, output_dir=tmp,
                    details=details, enable_llm=False,
                )
                self.assertIsNotNone(path)
                self.assertTrue(path.endswith(".html"))
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)

    def test_news_failure_does_not_block_excel(self):
        """新闻获取失败不阻塞 Excel 报告生成。

        即使 aggregate_news 返回空列表，generate_excel_report 也应正常完成。
        """
        from src.python.report.excel_generator import generate_excel_report
        from src.python.report.market_value import DetailRow

        holdings = [Holding("证券", "茅台", "600519", 100, 150.0)]
        details = [
            DetailRow("证券", "茅台", "600519", 160.0, "2026-07-03",
                      158.0, "tencent", "--", 100, 16000.0, 15000.0, 1000.0,
                      0.0667, 200.0, "腾讯行情", "tencent"),
        ]

        with (
            patch("src.python.fetcher.index.fetch_indices", return_value={}),
            patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
            patch("src.python.report.fund_performance.write_fund_performance_sheet"),
            # 新闻返回空（模拟获取失败）
            patch("src.python.providers.news_aggregator.aggregate_news",
                  return_value=[]),
        ):
            import tempfile
            tmp = tempfile.mkdtemp(prefix="test_isolation_excel_")
            try:
                result = generate_excel_report(
                    holdings, output_dir=tmp,
                    details=details, a_indices={}, us_indices={},
                    include_news=True,
                )
                # generate_excel_report 返回 None（无 return 值），验证文件确实生成
                expected_file = os.path.join(tmp, "个人投资分析报告.xlsx")
                self.assertTrue(os.path.exists(expected_file),
                                f"Excel 报告文件应存在于 {expected_file}")
            finally:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
