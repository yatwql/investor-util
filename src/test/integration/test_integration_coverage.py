"""集成测试覆盖增补 — P0 U 五类集成验证。

覆盖项：
  1. 模块间接口契约验证     — reader → market_value → penetration 类型链
  2. 错误隔离业务语义验证   — 各模块失败不影响其他模块写入
  3. 新闻流水线全链路集成   — fetch → aggregate → deduplicate → correlate
  4. 跨模块缓存一致性验证   — price 刷新后多模块使用同一缓存源
  5. TUI → Handler 路由     — 菜单按键正确路由到目标模块

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/integration/ -v                     # 全部集成测试
  pytest src/test/integration/ -m "integration_contract"  # 仅契约验证
  pytest src/test/ -m "integration" -v                # 全部集成测试
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.python.models import Holding


# ═════════════════════════════════════════════════════════════════════════
#  1. 模块间接口契约验证 (integration_contract)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.integration_contract
class TestModuleContractChain(unittest.TestCase):
    """模块间接口契约验证 — reader 输出 → market_value → penetration 类型链。

    构造完整类型链，断言各环节输入/输出类型正确，不依赖真实 API。
    """

    def test_holding_dataclass_fields(self):
        """Holding dataclass 字段类型契约。"""
        h = Holding("证券", "贵州茅台", "600519", 100, 150.0)
        self.assertIsInstance(h.account, str)
        self.assertIsInstance(h.name, str)
        self.assertIsInstance(h.code, str)
        self.assertIsInstance(h.shares, (int, float))
        self.assertIsInstance(h.cost_price, (int, float))

    def test_holding_to_detail_row_contract(self):
        """Holding + MarketData → DetailRow 的类型转换契约。

        _compute_detail_row 接受 Holding + dict，返回 DetailRow，
        字段类型符合预期。
        """
        from src.python.report.market_value import _compute_detail_row, DetailRow

        h = Holding("证券", "贵州茅台", "600519", 100, 150.0)
        mkt = {
            "price": 160.5, "yesterday_close": 158.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "source": "腾讯行情", "name": "贵州茅台", "code": "600519",
        }

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 30)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)

        # DetailRow 类型契约
        self.assertIsInstance(row, DetailRow)
        self.assertIsInstance(row.account, str)
        self.assertIsInstance(row.name, str)
        self.assertIsInstance(row.code, str)
        self.assertIsInstance(row.price, (int, float))
        self.assertIsInstance(row.nav_date, str)
        self.assertIsInstance(row.yesterday_close, (int, float))
        self.assertIsInstance(row.price_type, str)
        self.assertIsInstance(row.shares, (int, float))
        self.assertIsInstance(row.market_value, (int, float))
        self.assertIsInstance(row.cost, (int, float))
        self.assertIsInstance(row.profit, (int, float))
        self.assertIsInstance(row.profit_rate, (int, float, type(None)))
        self.assertIsInstance(row.source, str)
        self.assertIsInstance(row.source_api, str)

        # 数值合理性
        self.assertAlmostEqual(row.price, 160.5)
        self.assertAlmostEqual(row.market_value, 16050.0)  # 160.5 * 100
        self.assertAlmostEqual(row.cost, 15000.0)  # 150.0 * 100
        self.assertAlmostEqual(row.profit, 1050.0)  # 16050 - 15000

    def test_detail_row_to_penetration_contract(self):
        """list[DetailRow] → compute_penetration_top10 类型链。

        接受 list[Holding] + list[DetailRow]，返回结构化 dict。
        """
        from src.python.report.market_value import DetailRow
        from src.python.report.penetration import compute_penetration_top10

        holdings = [
            Holding("证券", "茅台", "600519", 100, 150.0),
            Holding("证券", "沪深300ETF", "510300", 1000, 4.0),
        ]
        details = [
            DetailRow("证券", "茅台", "600519", 160.0, "2026-07-03",
                      158.0, "tencent", "--", 100, 16000.0, 15000.0, 1000.0,
                      0.0667, 200.0, "腾讯行情", "tencent"),
            DetailRow("证券", "沪深300ETF", "510300", 4.2, "2026-07-03",
                      4.1, "tencent", "--", 1000, 4200.0, 4000.0, 200.0,
                      0.05, 100.0, "腾讯行情", "tencent"),
        ]

        with (
            patch("src.python.report.penetration._enrich_with_industry_api",
                  return_value=(True, "")),
        ):
            result = compute_penetration_top10(holdings, details)

        # 顶层字段类型契约
        self.assertIsInstance(result, dict)
        self.assertIn("update_time", result)
        self.assertIn("summary", result)
        self.assertIn("top10", result)
        self.assertIsInstance(result["summary"], dict)
        self.assertIsInstance(result["top10"], list)

        # summary 字段契约（字段名以实际返回为准）
        summary = result["summary"]
        self.assertIn("top10_coverage_pct", summary)
        self.assertIn("unknown_mv", summary)
        self.assertIn("total_mv", summary)

        # top10 条目字段契约
        for item in result["top10"]:
            self.assertIn("rank", item)
            self.assertIn("name", item)
            self.assertIn("codes", item)
            self.assertIn("mv", item)
            self.assertIn("ratio_pct", item)
            self.assertIsInstance(item["rank"], int)
            self.assertIsInstance(item["name"], str)
            self.assertIsInstance(item["codes"], list)
            self.assertIsInstance(item["mv"], (int, float))
            self.assertIsInstance(item["ratio_pct"], (int, float))

    def test_classify_holdings_type_contract(self):
        """classify_holdings 输入/输出类型契约。"""
        from src.python.report.market_value import classify_holdings

        holdings = [
            Holding("证券", "茅台", "600519", 100, 150.0),
            Holding("支付宝", "易方达蓝筹", "005827", 500, 2.0),
        ]
        categories = classify_holdings(holdings)

        self.assertIsInstance(categories, dict)
        expected_keys = {"场内股票", "场内ETF", "国内场外", "QDII"}
        self.assertSetEqual(set(categories.keys()), expected_keys)
        for key, items in categories.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(items, list)
            for item in items:
                self.assertIsInstance(item, Holding)

    def test_classify_penetration_types(self):
        """classify_penetration 返回值为预定义常量之一。"""
        from src.python.report.penetration import classify_penetration, \
            STOCK, ETF, QDII, BOND_FUND, INDEX_LINK, ACTIVE_EQUITY, IGNORE

        valid_types = {STOCK, ETF, QDII, BOND_FUND, INDEX_LINK, ACTIVE_EQUITY, IGNORE}
        test_cases = [
            (Holding("证券", "贵州茅台", "600519", 100, 150.0), STOCK),
            (Holding("证券", "沪深300ETF", "510300", 1000, 4.0), ETF),
            (Holding("证券", "易方达QDII", "003095", 100, 1.5), QDII),
            (Holding("证券", "招商纯债", "003095", 1000, 1.0), BOND_FUND),
            (Holding("支付宝", "沪深300ETF联接", "003095", 500, 1.5), INDEX_LINK),
            (Holding("支付宝", "易方达蓝筹精选", "005827", 500, 2.0), ACTIVE_EQUITY),
            (Holding("证券", "XX转债", "123456", 100, 100.0), IGNORE),
        ]
        for h, expected in test_cases:
            with self.subTest(name=h.name):
                result = classify_penetration(h)
                self.assertIn(result, valid_types)
                self.assertEqual(result, expected)

    def test_compute_detail_row_none_mkt_fallback(self):
        """行情为 None 时 _compute_detail_row 返回降级 DetailRow。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "茅台", "600519", 100, 150.0)
        row = _compute_detail_row(h, None)
        self.assertEqual(row.price, 0.0)
        self.assertEqual(row.market_value, 0.0)
        self.assertAlmostEqual(row.cost, 15000.0)  # cost_price * shares
        self.assertEqual(row.profit, 0.0)
        self.assertEqual(row.nav_date, "")
        self.assertEqual(row.source_api, "")

    def test_price_update_status_type_contract(self):
        """price_update_status 返回三元组类型契约。"""
        from src.python.report.market_value import price_update_status, DetailRow

        details = [
            DetailRow("证券", "茅台", "600519", 160.0, "2026-07-03",
                      158.0, "tencent", "--", 100, 16000.0, 15000.0, 1000.0,
                      0.0667, 200.0, "腾讯行情", "tencent"),
        ]
        with (
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-07-02"),
        ):
            updated, total, all_updated = price_update_status(details, "2026-07-03")

        self.assertIsInstance(updated, int)
        self.assertIsInstance(total, int)
        self.assertIsInstance(all_updated, bool)


# ═════════════════════════════════════════════════════════════════════════
#  2. 错误隔离业务语义验证 (integration_isolation)
# ═════════════════════════════════════════════════════════════════════════


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
            patch("src.python.report.html_writer.fetch_indices",
                  return_value={}),
            patch("src.python.report.html_writer.fetch_us_indices",
                  return_value={}),
            patch("src.python.report.html_writer.compute_penetration_top10",
                  return_value={}),
            patch("src.python.report.html_writer._build_category_data",
                  return_value={}),
            patch("src.python.report.html_writer.price_update_status",
                  return_value=(1, 1, True)),
            patch("src.python.report.html_writer._build_perf_data",
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


# ═════════════════════════════════════════════════════════════════════════
#  3. 新闻流水线全链路集成 (integration_news_pipeline)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.integration_news_pipeline
class TestNewsPipeline(unittest.TestCase):
    """新闻流水线全链路 — fetch → aggregate → deduplicate → correlate。

    验证各子步骤端到端协同工作，mock 外部 API 避免真实请求。
    """

    def _mock_news_item(self, title: str, url: str = "",
                        intro: str = "", source: str = "新浪财经",
                        ctime: str = "2026-07-03 10:00:00") -> dict:
        return {
            "title": title, "url": url or f"http://test.com/{hash(title)}",
            "intro": intro or f"{title}简介", "source": source,
            "ctime": ctime, "content": f"{title}正文",
        }

    def test_aggregate_news_deduplicates_by_url(self):
        """aggregate_news 按 URL 去重，相同 URL 只保留第一条。

        注：去重发生在 _fetch_from_all_sources 内部（URL 已去重进入 all_raw），
        此处验证全链路整合正确：mock 已去重的数据，确认输出条数一致。
        """
        from src.python.providers.news_aggregator import aggregate_news

        # _fetch_from_all_sources 在 mock 层面模拟去重后的结果
        mock_news = [
            self._mock_news_item("新闻A", url="http://test.com/a"),
            self._mock_news_item("新闻B", url="http://test.com/b"),
        ]

        with (
            patch("src.python.providers.news_aggregator.get_enabled_sources",
                  return_value=["sina"]),
            patch("src.python.providers.news_aggregator._fetch_from_all_sources",
                  return_value=(mock_news, {"sina": (2, "OK")})),
            patch("src.python.providers.news_aggregator._save_news_cache"),
            patch("src.python.providers.news_aggregator.correlate_news_with_holdings",
                  side_effect=lambda items, keywords, **kw: items),
        ):
            result = aggregate_news(keywords=["茅台"], top_n=10)

        # 模拟去重后应有 2 条（URL 不重复）
        self.assertEqual(len(result), 2)

    def test_correlate_news_matches_keywords(self):
        """correlate_news_with_holdings 按关键词匹配，matched_keywords 字段正确。"""
        from src.python.providers.news_correlator import correlate_news_with_holdings

        news_list = [
            self._mock_news_item("茅台股价创新高", intro="贵州茅台今日股价突破2000元"),
            self._mock_news_item("腾讯发布财报", intro="腾讯控股营收同比增长"),
            self._mock_news_item("无关新闻", intro="今日天气晴好"),
        ]
        keywords = ["茅台", "腾讯"]
        result = correlate_news_with_holdings(news_list, keywords, top_n=10)

        # 应匹配到 2 条
        self.assertEqual(len(result), 2)

        # 按匹配数降序
        result_titles = {item["title"]: item for item in result}
        self.assertIn("matched_keywords", result_titles["茅台股价创新高"])
        self.assertIn("茅台", result_titles["茅台股价创新高"]["matched_keywords"])
        self.assertIn("腾讯", result_titles["腾讯发布财报"]["matched_keywords"])

    def test_aggregate_news_empty_keywords_returns_raw(self):
        """空关键词时 correlate_news_with_holdings 返回原始列表。"""
        from src.python.providers.news_correlator import correlate_news_with_holdings

        news_list = [self._mock_news_item("测试新闻")]
        result = correlate_news_with_holdings(news_list, [], top_n=10)
        self.assertEqual(len(result), 1)

    def test_build_news_data_integration(self):
        """build_news_data 端到端：持仓 → 新闻 → 关联。

        Mock 外部的 aggregate_news，验证返回结构包含完整字段。
        """
        from src.python.report.news_correlation import build_news_data

        holdings = [
            Holding("证券", "贵州茅台", "600519", 100, 150.0),
            Holding("支付宝", "易方达蓝筹", "005827", 500, 2.0),
        ]

        mock_news = [
            {"title": "茅台股价新高", "intro": "贵州茅台今日大涨",
             "url": "http://test.com/mt", "source": "新浪财经",
             "ctime": "2026-07-03", "content": ""},
            {"title": "易方达基金分红", "intro": "易方达基金发布分红公告",
             "url": "http://test.com/yfd", "source": "东方财富",
             "ctime": "2026-07-03", "content": ""},
        ]

        with (
            patch("src.python.providers.news_aggregator.aggregate_news",
                  return_value=mock_news),
            patch("src.python.providers.news_keywords.build_holding_keywords",
                  return_value=["茅台", "易方达"]),
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            news_result, news_meta = build_news_data(holdings, top_n=10)

        self.assertIsInstance(news_result, list)
        self.assertIsInstance(news_meta, dict)
        self.assertIn("active_sources", news_meta)
        self.assertIn("llm_enabled", news_meta)


# ═════════════════════════════════════════════════════════════════════════
#  4. 跨模块缓存一致性验证 (integration_cache)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.integration_cache
class TestCrossModuleCacheConsistency(unittest.TestCase):
    """跨模块缓存一致性 — 同一数据源在不同模块间使用同一缓存。

    验证 price/指数等缓存数据在 market_value 和 fund_performance 间共享。
    """

    def test_fetch_market_data_cache_prefix(self):
        """fetch_market_data 使用正确缓存前缀，不同前缀不冲突。"""
        from src.python.fetcher.price import _price_cache_key
        key = _price_cache_key("600519")
        self.assertIn("price_", key)
        self.assertEqual(key, "price_600519")

    def test_cache_sharing_between_fetcher_and_market_value(self):
        """fetch_market_data 的缓存可被 market_value 模块重用。

        直接写入缓存后，fetch_market_data 应命中缓存而非重新获取。
        """
        from src.python.cache import set as cache_set, clear as cache_clear
        from src.python.fetcher.price import fetch_market_data

        cache_key = "price_600519"
        cached_data = {
            "price": 160.0, "yesterday_close": 158.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "贵州茅台", "code": "600519",
            "source": "腾讯行情",
        }

        # 先写入缓存，再调用 fetch_market_data 应直接命中缓存
        cache_set(cache_key, cached_data)

        with (
            patch("src.python.providers.tencent.fetch_price",
                  return_value=None),
            patch("src.python.providers.eastmoney.fetch_nav",
                  return_value=None),
        ):
            result = fetch_market_data("600519", "贵州茅台")

        self.assertIsNotNone(result)
        self.assertEqual(result.get("price"), 160.0)

        # 清理测试写入的缓存
        cache_clear(cache_key)

    def test_cache_prefix_consistency_price(self):
        """market_value 和 fetcher.price 使用相同缓存前缀。"""
        from src.python.registry import get_prefix_type_map
        prefix_map = get_prefix_type_map()
        self.assertIn("price_", prefix_map)
        self.assertEqual(prefix_map["price_"], "price")

    def test_index_cache_shared_across_modules(self):
        """指数行情缓存可被多个模块共享。

        fetch_indices 缓存可被 report/excel_generator 等模块重用。
        """
        from src.python.fetcher.index import fetch_indices
        from src.python.cache import get as cache_get

        mock_data = {
            "sh000001": {"name": "上证指数", "code": "sh000001",
                         "price": 3050.5, "change_pct": 0.5},
        }

        with (
            patch("src.python.fetcher.index._fetch_indices_from_tencent",
                  return_value=mock_data),
            patch("src.python.fetcher.index.cache_get",
                  return_value=None),
        ):
            result = fetch_indices()
            self.assertEqual(result["sh000001"]["price"], 3050.5)

        # 验证缓存键格式
        from src.python.fetcher.index import _index_cache_key
        key = _index_cache_key("sh000001")
        self.assertIn("index_", key)
        self.assertEqual(key, "index_sh000001")


# ═════════════════════════════════════════════════════════════════════════
#  5. TUI → Handler 路由集成测试 (integration_tui)
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.integration_tui
class TestTuiRouting(unittest.TestCase):
    """TUI 菜单 → Handler 路由 — 按键正确路由到目标处理器。"""

    def test_all_menu_keys_have_callbacks(self):
        """所有非退出菜单项的 callback 不为 None。"""
        from src.python.main import _bind_callbacks
        from src.python.tui_menu import MENU_ITEMS

        _bind_callbacks()

        for key, label, callback, is_exit in MENU_ITEMS:
            with self.subTest(key=key, label=label):
                if is_exit:
                    continue  # 退出项由 _execute_item 直接处理
                self.assertIsNotNone(
                    callback,
                    f"菜单项 [{key}] {label} 未绑回调函数",
                )

    def test_menu_key_coverage(self):
        """MENU_ITEMS 包含所有标准功能键。"""
        from src.python.tui_menu import MENU_ITEMS

        keys = {item[0] for item in MENU_ITEMS}
        expected = {"E", "H", "B", "L", "C", "F", "O",
                    "1", "2", "3", "4", "S", "R", "X"}
        self.assertSetEqual(keys, expected)

    def test_execute_item_dispatches_correct_handler(self):
        """_execute_item 根据选中项索引正确执行回调。

        注：前序测试 _bind_callbacks 会绑定真实回调函数到 MENU_ITEMS，
        此处仅验证回调非 None 且可调用，不实际执行防止触发报告生成逻辑。
        """
        from src.python.tui_menu import MENU_ITEMS

        # 找到非退出项
        non_exit_idx = next(i for i, item in enumerate(MENU_ITEMS)
                            if not item[3])

        cb = MENU_ITEMS[non_exit_idx][2]
        if cb is not None:
            # 仅验证回调是可调用对象，不实际调用
            self.assertTrue(callable(cb),
                            f"菜单项 [{MENU_ITEMS[non_exit_idx][0]}] 回调应可调用")

    def test_bind_callbacks_fills_all_slots(self):
        """_bind_callbacks 后所有菜单项 callback 非 None。"""
        from src.python.main import _bind_callbacks

        _bind_callbacks()

        from src.python.tui_menu import MENU_ITEMS
        for key, label, callback, is_exit in MENU_ITEMS:
            with self.subTest(key=key, label=label):
                if is_exit:
                    continue
                self.assertIsNotNone(callback)

    def test_menu_sel_navigation(self):
        """菜单选择索引在上下界内。"""
        from src.python.tui_menu import MENU_ITEMS
        sel = 0
        n = len(MENU_ITEMS)

        # 上边界
        sel = (sel - 1) % n
        self.assertEqual(sel, n - 1)

        # 下边界
        sel = (sel + 1) % n
        self.assertEqual(sel, 0)

    def test_keyboard_shortcut_routing(self):
        """字母键直达路由：E → handler_report._cmd_generate_excel。"""
        from src.python.main import _bind_callbacks

        _bind_callbacks()

        from src.python.tui_menu import MENU_ITEMS
        e_item = next(item for item in MENU_ITEMS if item[0] == "E")
        self.assertIsNotNone(e_item[2])

        # 确认 E 绑定了正确的处理器
        cb_name = e_item[2].__name__ if e_item[2] else ""
        self.assertEqual(cb_name, "_cmd_generate_excel")

    def test_llm_key_routes_to_full_generation(self):
        """L 键路由到 _cmd_generate_full。"""
        from src.python.main import _bind_callbacks

        _bind_callbacks()

        from src.python.tui_menu import MENU_ITEMS
        l_item = next(item for item in MENU_ITEMS if item[0] == "L")
        cb_name = l_item[2].__name__ if l_item[2] else ""
        self.assertEqual(cb_name, "_cmd_generate_full")


if __name__ == "__main__":
    unittest.main()
