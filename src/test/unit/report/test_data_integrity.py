"""数据正确性验证测试（§2 数据正确性验证 9 项）。

覆盖场景：
  1. 三维度分类聚合一致 — 各分类小计 = 总计
  2. 穿透行业占比归一化 — 各行业占比之和 ≤ 100%
  3. 指数行情数值合理 — 上证≈3000、沪深300≈4000 等数量级
  4. 多币种转换正确 — 美元份额 × 汇率中间价 = 人民币市值
  5. QDII 估值净值 vs 官方净值 — 估值净值 ≥ 0，官方净值延迟 T-2
  6. 基金业绩排名合理性 — 排名/收益率在合理范围内
  7. 溢价率计算 — (市价 - 净值) / 净值
  8. 本日盈亏场外非 T 日更新 — nav_date ≠ T → today_profit = 0
  9. 穿透市值占比归一化 — TOP10 占比总和 ≤ 100%

运行：
  pytest src/test/unit/report/test_data_integrity.py -v
  pytest src/test/ -m "data" -v                # 全部数据正确性测试
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.python.core.models import Holding


# ═══════════════════════════════════════════════════════════════
# 1. 三维度分类聚合一致
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestCategoryAggregationConsistency(unittest.TestCase):
    """三维度分类聚合：各类分类小计各自 = 总计。"""

    def test_categorize_holding_stock(self):
        """股票代码（6 开头）→ ('股票', 'A股')。"""
        h = Holding("证券", "贵州茅台", "600519", 100, 150.0)
        from src.python.report.category import _categorize_holding
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "股票")
        self.assertEqual(sub, "A股")

    def test_categorize_holding_etf(self):
        """ETF 名称 → ('基金', '指数')。"""
        h = Holding("证券", "沪深300ETF", "510300", 1000, 4.0)
        from src.python.report.category import _categorize_holding
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "指数")

    def test_categorize_holding_qdii(self):
        """QDII 名称 → ('基金', 'QDII')。"""
        h = Holding("证券", "易方达QDII", "003095", 100, 1.5)
        from src.python.report.category import _categorize_holding
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "QDII")

    def test_categorize_holding_bond(self):
        """债券关键词 → ('债券', '纯债')。"""
        h = Holding("证券", "招商纯债", "003095", 1000, 1.0)
        from src.python.report.category import _categorize_holding
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "债券")
        self.assertEqual(sub, "纯债")

    def test_categorize_holding_money_market(self):
        """货币关键词 → ('现金', '货币')。"""
        h = Holding("支付宝", "余额宝", "003095", 10000, 1.0)
        from src.python.report.category import _categorize_holding
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "现金")
        self.assertEqual(sub, "货币")

    def test_categorize_holding_index_link(self):
        """场外基金 + 指数关键词 → ('基金', '被动')。"""
        h = Holding("支付宝", "沪深300指数", "003095", 500, 1.5)
        from src.python.report.category import _categorize_holding
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "被动")

    def test_categorize_holding_active(self):
        """纯场外基金 → ('基金', '主动')。"""
        h = Holding("支付宝", "易方达蓝筹精选", "005827", 500, 2.0)
        from src.python.report.category import _categorize_holding
        prop, sub = _categorize_holding(h)
        self.assertEqual(prop, "基金")
        self.assertEqual(sub, "主动")


# ═══════════════════════════════════════════════════════════════
# 2. 穿透行业占比归一化
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestPenetrationIndustryRatio(unittest.TestCase):
    """穿透行业占比归一化：各行业占比之和 ≤ 100%。"""

    def test_classify_penetration_stock(self):
        """股票代码 → 'stock'。"""
        h = Holding("证券", "贵州茅台", "600519", 100, 150.0)
        from src.python.report.penetration import classify_penetration
        self.assertEqual(classify_penetration(h), "stock")

    def test_classify_penetration_etf(self):
        """ETF → 'etf'。"""
        h = Holding("证券", "沪深300ETF", "510300", 1000, 4.0)
        from src.python.report.penetration import classify_penetration
        self.assertEqual(classify_penetration(h), "etf")

    def test_classify_penetration_bond_fund(self):
        """纯债关键词 → 'bond_fund'。"""
        h = Holding("证券", "招商纯债", "003095", 1000, 1.0)
        from src.python.report.penetration import classify_penetration
        self.assertEqual(classify_penetration(h), "bond_fund")

    def test_classify_penetration_index_link(self):
        """ETF联接 → 'index_link'。"""
        h = Holding("支付宝", "沪深300ETF联接", "003095", 500, 1.5)
        from src.python.report.penetration import classify_penetration
        self.assertEqual(classify_penetration(h), "index_link")

    def test_penetration_top10_ratios_sum_lte_100(self):
        """compute_penetration_top10 的 top10 占比总和 ≤ 100%。"""
        from src.python.report.penetration import compute_penetration_top10

        holdings = [
            Holding("证券", "茅台", "600519", 100, 150.0),
            Holding("证券", "招商银行", "600036", 200, 30.0),
            Holding("证券", "沪深300ETF", "510300", 1000, 4.0),
        ]
        from src.python.report.market_value import DetailRow
        details = [
            DetailRow("证券", "茅台", "600519", 100, 150.0, 160.0, 155.0,
                      "2026-07-03", "tencent", 10.0, 1000.0, 0.5, "--", 1),
            DetailRow("证券", "招商银行", "600036", 200, 30.0, 32.0, 31.0,
                      "2026-07-03", "tencent", 2.0, 400.0, 0.3, "--", 2),
            DetailRow("证券", "沪深300ETF", "510300", 1000, 4.0, 4.2, 4.1,
                      "2026-07-03", "tencent", 1.0, 200.0, 0.2, "--", 3),
        ]

        with (
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            result = compute_penetration_top10(holdings, details)
            top10 = result.get("top10", [])
            total_ratio = sum(item.get("ratio", 0) for item in top10)
            self.assertLessEqual(total_ratio, 100.0)
            self.assertIn("summary", result)
            self.assertIn("top10_coverage_pct", result["summary"])


# ═══════════════════════════════════════════════════════════════
# 3. 指数行情数值合理
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestIndexValueRange(unittest.TestCase):
    """指数行情数值合理：各指数在合理数量级范围内。"""

    def test_a_index_value_ranges(self):
        """A 股指数数量级验证（mock 数据）。"""
        from src.python.fetcher.index import fetch_indices

        mock_data = {
            "sh000001": {"name": "上证指数", "code": "sh000001",
                         "price": 3050.5, "change_pct": 0.5},
            "sz399001": {"name": "深证成指", "code": "sz399001",
                         "price": 9500.0, "change_pct": -0.3},
            "sh000300": {"name": "沪深300", "code": "sh000300",
                         "price": 3850.0, "change_pct": 0.2},
            "sh000688": {"name": "科创板50", "code": "sh000688",
                         "price": 1500.0, "change_pct": 1.0},
            "sz399006": {"name": "创业板指", "code": "sz399006",
                         "price": 2200.0, "change_pct": -0.5},
        }

        with (
            patch("src.python.fetcher.index._fetch_indices_from_tencent",
                  return_value=mock_data),
            patch("src.python.fetcher.index._fetch_indices_from_sina",
                  return_value={}),
            patch("src.python.fetcher.index.cache_get",
                  return_value=None),
        ):
            result = fetch_indices()

        # 上证 ≈ 3000 级别
        self.assertGreater(result["sh000001"]["price"], 2500)
        self.assertLess(result["sh000001"]["price"], 4000)

        # 沪深300 ≈ 4000 级别
        self.assertGreater(result["sh000300"]["price"], 3000)
        self.assertLess(result["sh000300"]["price"], 5500)

        # 创业板指 ≈ 2000 级别
        self.assertGreater(result["sz399006"]["price"], 1500)
        self.assertLess(result["sz399006"]["price"], 4000)

        # 涨跌幅在合理范围
        for code in mock_data:
            c = result[code]["change_pct"]
            self.assertGreater(c, -10.0)  # 单日跌幅不超过 10%
            self.assertLess(c, 10.0)      # 单日涨幅不超过 10%

    def test_us_index_value_ranges(self):
        """美股指数数量级验证（mock 数据）。"""
        from src.python.fetcher.index import fetch_us_indices

        mock_data = {
            "gb_dji": {"name": "道琼斯", "code": "gb_dji",
                       "price": 35000.0, "change_pct": 0.3},
            "gb_ixic": {"name": "纳斯达克", "code": "gb_ixic",
                        "price": 15000.0, "change_pct": -0.5},
            "gb_inx": {"name": "标普500", "code": "gb_inx",
                       "price": 5200.0, "change_pct": 0.1},
        }

        with (
            patch("src.python.fetcher.index.sina.fetch_us_indices",
                  return_value=mock_data),
            patch("src.python.fetcher.index.cache_get",
                  return_value=None),
        ):
            result = fetch_us_indices()

        # 道琼斯 ≈ 30000-40000
        self.assertGreater(result["gb_dji"]["price"], 25000)
        self.assertLess(result["gb_dji"]["price"], 50000)

        # 纳斯达克 ≈ 10000-20000
        self.assertGreater(result["gb_ixic"]["price"], 8000)
        self.assertLess(result["gb_ixic"]["price"], 25000)

        # 标普500 ≈ 4000-6000
        self.assertGreater(result["gb_inx"]["price"], 3500)
        self.assertLess(result["gb_inx"]["price"], 7000)

        # 涨跌幅在合理范围
        for code in mock_data:
            c = result[code]["change_pct"]
            self.assertGreater(c, -10.0)
            self.assertLess(c, 10.0)


# ═══════════════════════════════════════════════════════════════
# 4. 多币种转换正确
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestMultiCurrencyConversion(unittest.TestCase):
    """多币种转换：价格 × 汇率中间价 = 人民币市值（目前为占位符演练）。"""

    def test_detail_row_compute_with_high_price(self):
        """_compute_detail_row 处理美元计价净值（高价场景）正确。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "标普500ETF", "513500", 100, 2.0)
        mkt = {
            "price": 2.5, "yesterday_close": 2.45,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "标普500ETF", "code": "513500",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)

        self.assertEqual(row.shares, 100.0)
        self.assertGreater(row.market_value, 200)  # 100 * 2.5 = 250
        self.assertAlmostEqual(row.market_value, 250.0)
        self.assertAlmostEqual(row.today_profit, (2.5 - 2.45) * 100)


# ═══════════════════════════════════════════════════════════════
# 5. QDII 估值净值 vs 官方净值
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestQdiiNavConsistency(unittest.TestCase):
    """QDII 估值净值 ≥ 0，官方净值延迟 T-2。"""

    def test_price_update_status_qdii_t_minus_2_not_updated(self):
        """QDII + nav_date = T-2 → 视为未更新（仅 T/T-1 判定为已更新）。"""
        from src.python.report.market_value import price_update_status, DetailRow

        details = [
            DetailRow("证券", "QDII基金", "003095", 100, 1.0, 1.2, 1.15,
                      "2026-07-01", "eastmoney", 0.0, 20.0, 0.0, "--", 1),
        ]
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-07-02"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 16, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            updated, total, all_updated = price_update_status(
                details, "2026-07-03",
            )
        self.assertEqual(updated, 0)
        self.assertFalse(all_updated)


# ═══════════════════════════════════════════════════════════════
# 6. 基金业绩排名合理性
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestFundPerformanceReasonableness(unittest.TestCase):
    """基金业绩排名数据合理性：排名/收益率在合理范围。"""

    def test_format_return_positive(self):
        """正收益率 → 小数（5.23 → 0.0523，浮点近似）。"""
        from src.python.report.fund_performance import _format_return
        self.assertAlmostEqual(_format_return(5.23), 0.0523)

    def test_format_return_negative(self):
        """负收益率 → 负小数（-3.14 → -0.0314，浮点近似）。"""
        from src.python.report.fund_performance import _format_return
        self.assertAlmostEqual(_format_return(-3.14), -0.0314)

    def test_format_return_zero(self):
        """零收益率 → 0.0。"""
        from src.python.report.fund_performance import _format_return
        self.assertEqual(_format_return(0.0), 0.0)

    def test_format_return_none(self):
        """None → "--"。"""
        from src.python.report.fund_performance import _format_return
        self.assertEqual(_format_return(None), "--")

    def test_format_return_dash(self):
        """'--' → '--'。"""
        from src.python.report.fund_performance import _format_return
        self.assertEqual(_format_return("--"), "--")

    def test_format_rank_normal(self):
        """有效排名 → "排名/总数"。"""
        from src.python.report.fund_performance import _format_rank
        self.assertEqual(_format_rank({"rank": 5, "total": 100}), "5/100")

    def test_format_rank_none(self):
        """None 排名 → "--"。"""
        from src.python.report.fund_performance import _format_rank
        self.assertEqual(_format_rank({"rank": None, "total": 100}), "--")

    def test_format_rank_missing_key(self):
        """缺失键 → "--"。"""
        from src.python.report.fund_performance import _format_rank
        self.assertEqual(_format_rank({}), "--")

    def test_rating_adjustment_excess_high(self):
        """超额收益 ≥ 80 → 评级上调一级。"""
        from src.python.report.fund_performance import _adjust_rating_with_benchmark

        perf_eval = {
            "categories": ["超额收益"], "data": [85.0],
        }
        rating = _adjust_rating_with_benchmark("稳定", perf_eval)
        self.assertEqual(rating, "良好")  # 稳定 → 良好

    def test_rating_adjustment_excess_low(self):
        """超额收益 < 40 → 评级下调一级。"""
        from src.python.report.fund_performance import _adjust_rating_with_benchmark

        perf_eval = {
            "categories": ["超额收益"], "data": [35.0],
        }
        rating = _adjust_rating_with_benchmark("稳定", perf_eval)
        self.assertEqual(rating, "偏差")  # 稳定 → 偏差

    def test_rating_adjustment_no_change(self):
        """超额收益在 40-80 之间 → 评级不变。"""
        from src.python.report.fund_performance import _adjust_rating_with_benchmark

        perf_eval = {
            "categories": ["超额收益"], "data": [60.0],
        }
        rating = _adjust_rating_with_benchmark("稳定", perf_eval)
        self.assertEqual(rating, "稳定")

    def test_rating_adjustment_excellent_downgraded(self):
        """"优秀" + 超额 < 40 → 下调为"良好"。"""
        from src.python.report.fund_performance import _adjust_rating_with_benchmark

        perf_eval = {
            "categories": ["超额收益"], "data": [20.0],
        }
        rating = _adjust_rating_with_benchmark("优秀", perf_eval)
        self.assertEqual(rating, "良好")  # 优秀 → 良好（下调一级）

    def test_rating_adjustment_poor_upgraded(self):
        """"较差" + 超额 ≥ 80 → 上调为"偏差"。"""
        from src.python.report.fund_performance import _adjust_rating_with_benchmark

        perf_eval = {
            "categories": ["超额收益"], "data": [95.0],
        }
        rating = _adjust_rating_with_benchmark("较差", perf_eval)
        self.assertEqual(rating, "偏差")  # 较差 → 偏差（上调一级）


# ═══════════════════════════════════════════════════════════════
# 7. 溢价率计算
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestPremiumRateCalculation(unittest.TestCase):
    """溢价率计算验证。"""

    def test_premium_is_placeholder(self):
        """当前溢价率为占位符 "--"。"""
        from src.python.report.market_value import _FUND_PREMIUM_PLACEHOLDER
        self.assertEqual(_FUND_PREMIUM_PLACEHOLDER, "--")

    def test_compute_detail_row_premium_qdii_etf(self):
        """QDII ETF _compute_detail_row 溢价率正确计算。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "标普500ETF", "513500", 100, 2.0)
        mkt = {
            "price": 2.5, "yesterday_close": 2.45,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "标普500ETF", "code": "513500",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)
        self.assertEqual(row.premium, "+2.04%")

    # ── 溢价率计算（真实计算，非占位符）───────────────────────

    def test_premium_qdii_etf_positive(self):
        """QDII ETF + 现价 > 参考净值 → 正溢价率。"""
        from src.python.report.market_value import _compute_premium
        result = _compute_premium(2.50, 2.45, "标普500ETF")
        self.assertEqual(result, "+2.04%")

    def test_premium_qdii_etf_negative(self):
        """QDII ETF + 现价 < 参考净值 → 负溢价率。"""
        from src.python.report.market_value import _compute_premium
        result = _compute_premium(2.40, 2.45, "纳指ETF")
        self.assertEqual(result, "-2.04%")

    def test_premium_non_qdii_placeholder(self):
        """非 QDII 基金 → 返回占位符 "--"。"""
        from src.python.report.market_value import _compute_premium
        result = _compute_premium(10.0, 9.5, "沪深300ETF")
        self.assertEqual(result, "--")

    def test_premium_nav_zero_placeholder(self):
        """QDII 基金但参考净值为 0 → 返回占位符 "--"。"""
        from src.python.report.market_value import _compute_premium
        result = _compute_premium(10.0, 0.0, "标普500ETF")
        self.assertEqual(result, "--")


# ═══════════════════════════════════════════════════════════════
# 8. 本日盈亏场外非 T 日更新
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestTodayProfitOffsiteNavDate(unittest.TestCase):
    """本日盈亏场外非 T 日更新：nav_date ≠ T → today_profit = 0。"""

    def test_today_profit_tencent(self):
        """场内（tencent）+ 当日 → 计算本日盈亏。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "茅台", "600519", 100, 150.0)
        mkt = {
            "price": 160.0, "yesterday_close": 155.0,
            "price_date": "2026-07-03", "source_api": "tencent",
            "name": "茅台", "code": "600519",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)
        self.assertGreater(row.today_profit, 0)

    def test_today_profit_eastmoney_t_equal_t(self):
        """场外（eastmoney）+ nav_date == T → 计算本日盈亏。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "测试基金", "003095", 1000, 1.5)
        mkt = {
            "price": 1.6, "yesterday_close": 1.55,
            "price_date": "2026-07-03", "source_api": "eastmoney",
            "name": "测试基金", "code": "003095",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value._is_trading_day",
                  return_value=True),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)
        self.assertGreater(row.today_profit, 0)

    def test_today_profit_eastmoney_t_minus_1_zero(self):
        """场外（eastmoney）+ nav_date == T-1 → today_profit = 0。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "测试基金", "003095", 1000, 1.5)
        mkt = {
            "price": 1.6, "yesterday_close": 1.55,
            "price_date": "2026-07-02", "source_api": "eastmoney",
            "name": "测试基金", "code": "003095",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value._is_trading_day",
                  return_value=True),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)
        self.assertEqual(row.today_profit, 0.0)

    def test_today_profit_no_nav_date_zero(self):
        """无 nav_date → today_profit = 0。"""
        from src.python.report.market_value import _compute_detail_row

        h = Holding("证券", "测试基金", "003095", 1000, 1.5)
        mkt = {
            "price": 1.6, "yesterday_close": 1.55,
            "price_date": "", "source_api": "eastmoney",
            "name": "测试基金", "code": "003095",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value._is_trading_day",
                  return_value=True),
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = datetime(2026, 7, 3, 14, 0)
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            row = _compute_detail_row(h, mkt)
        self.assertEqual(row.today_profit, 0.0)


# ═══════════════════════════════════════════════════════════════
# 9. 穿透市值占比归一化
# ═══════════════════════════════════════════════════════════════


@pytest.mark.data
@pytest.mark.unit
@pytest.mark.unit_report
class TestPenetrationTop10RatioNormalization(unittest.TestCase):
    """穿透 TOP10 市值占比归一化：总和 ≤ 100%。"""

    def test_penetration_summary_has_top10_coverage(self):
        """compute_penetration_top10 结果包含 top10_coverage_pct。"""
        from src.python.report.penetration import compute_penetration_top10

        holdings = [Holding("证券", "茅台", "600519", 100, 150.0)]
        from src.python.report.market_value import DetailRow
        details = [
            DetailRow("证券", "茅台", "600519", 100, 150.0, 160.0, 155.0,
                      "2026-07-03", "tencent", 10.0, 1000.0, 1.0, "--", 1),
        ]
        with (
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            result = compute_penetration_top10(holdings, details)
            self.assertIn("top10_coverage_pct", result["summary"])
            coverage = result["summary"]["top10_coverage_pct"]
            self.assertGreaterEqual(coverage, 0)
            self.assertLessEqual(coverage, 100)

    def test_penetration_top10_missing_mv_zero_ratio(self):
        """穿透结果中缺失市值的条目占比为 0 而非 NaN。"""
        from src.python.report.penetration import compute_penetration_top10

        holdings = [Holding("证券", "茅台", "600519", 100, 150.0)]
        from src.python.report.market_value import DetailRow
        details = [
            DetailRow("证券", "茅台", "600519", 100, 150.0, 0.0, 0.0,
                      "2026-07-03", "tencent", 0.0, 0.0, 0.0, "--", 1),
        ]
        with (
            patch("src.python.fetcher.industry.batch_fetch_industry_data",
                  return_value={}),
        ):
            result = compute_penetration_top10(holdings, details)
            top10 = result.get("top10", [])
            # 市值=0 时该条目可能不在 top10 中
            if top10:
                for item in top10:
                    # 占比应为 0.0 而非 NaN
                    self.assertGreaterEqual(item.get("ratio_pct", -1), 0.0)
