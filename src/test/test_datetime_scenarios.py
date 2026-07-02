"""日期/时间数据获取场景测试 — T1~T16。

覆盖不同市场状态（盘中/盘前/午休/盘后/非交易日/长假）、
产品类型（场外/QDII/ETF/股票/混合）、以及边界 Edge Case
下的数据获取行为正确性。

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_datetime_scenarios.py -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.python.models import Holding


# ═══════════════════════════════════════════════════════════
# T1-T6: 市场状态组合 — get_ttl 市场时段感知
# ═══════════════════════════════════════════════════════════


class TestGetTtlMarketAware(unittest.TestCase):
    """get_ttl 市场时段感知测试。

    核心要求（T1 盘中 / T2 盘前 / T4 盘后 / T5 非交易日）：
      - 交易时段内，price/index 使用短 TTL（30s）
      - 非交易时段，price/index 使用配置的长 TTL（86400）
      - 非感知类型（rank/hold 等）不受市场状态影响
    """

    def setUp(self):
        self._config_patcher = patch("src.python.config.get_config")
        self._mock_get_config = self._config_patcher.start()
        self._is_open_patcher = patch("src.python.cache._is_market_open")
        self._mock_is_open = self._is_open_patcher.start()

    def tearDown(self):
        self._is_open_patcher.stop()
        self._config_patcher.stop()

    def _setup_config(self, market_hour_aware: list | None = None,
                      cache_ttl: dict | None = None,
                      market_hour_ttl: int = 30):
        """构造 mock config。"""
        cfg: dict = {}
        if market_hour_aware is not None:
            cfg["market_hour_aware"] = market_hour_aware
        if cache_ttl is not None:
            cfg["cache_ttl"] = cache_ttl
        if "market_hour_aware" in cfg or market_hour_ttl != 30:
            cfg["market_hour_ttl"] = market_hour_ttl
        self._mock_get_config.return_value = cfg

    # ── T1: 盘中 — short TTL for price/index ───────────────

    def test_intraday_price_short_ttl(self):
        """T1: 交易时段内 get_ttl("price") → 短 TTL（30s）。"""
        self._mock_is_open.return_value = True
        self._setup_config(
            market_hour_aware=["price", "index"],
            cache_ttl={"price": 86400, "index": 86400},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        self.assertEqual(ttl, 30)

    def test_intraday_index_short_ttl(self):
        """T1: 交易时段内 get_ttl("index") → 短 TTL（30s）。"""
        self._mock_is_open.return_value = True
        self._setup_config(
            market_hour_aware=["price", "index"],
            cache_ttl={"price": 86400, "index": 86400},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("index")
        self.assertEqual(ttl, 30)

    def test_intraday_market_hour_ttl_custom(self):
        """T1: 自定义 market_hour_ttl=60 → 使用 60s。"""
        self._mock_is_open.return_value = True
        self._setup_config(
            market_hour_aware=["price"],
            cache_ttl={"price": 86400},
            market_hour_ttl=60,
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        self.assertEqual(ttl, 60)

    # ── T2/T4/T5: 非交易时段 — long TTL ──────────────────

    def test_pre_market_price_long_ttl(self):
        """T2: 盘前 get_ttl("price") → 配置的长 TTL（86400）。"""
        self._mock_is_open.return_value = False
        self._setup_config(
            market_hour_aware=["price", "index"],
            cache_ttl={"price": 86400, "index": 86400},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        self.assertEqual(ttl, 86400)

    def test_post_market_index_long_ttl(self):
        """T4: 盘后 get_ttl("index") → 配置的长 TTL（86400）。"""
        self._mock_is_open.return_value = False
        self._setup_config(
            market_hour_aware=["price", "index"],
            cache_ttl={"price": 86400, "index": 86400},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("index")
        self.assertEqual(ttl, 86400)

    def test_weekend_price_long_ttl(self):
        """T5: 非交易日 get_ttl("price") → 配置的长 TTL。"""
        self._mock_is_open.return_value = False
        self._setup_config(
            market_hour_aware=["price", "index"],
            cache_ttl={"price": 86400},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        self.assertEqual(ttl, 86400)

    # ── 非感知类型不受市场状态影响 ─────────────────────────

    def test_non_aware_type_ignores_market_state(self):
        """非感知类型 get_ttl("rank") 盘中 → 配置的 rank TTL。"""
        self._mock_is_open.return_value = True
        self._setup_config(
            market_hour_aware=["price", "index"],
            cache_ttl={"rank": 7200},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("rank")
        self.assertEqual(ttl, 7200)

    def test_non_aware_type_post_market(self):
        """非感知类型 get_ttl("hold") 盘后 → 配置的 hold TTL。"""
        self._mock_is_open.return_value = False
        self._setup_config(
            market_hour_aware=["price", "index"],
            cache_ttl={"hold": 604800},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("hold")
        self.assertEqual(ttl, 604800)

    # ── 边界：TTL 钳位 ──────────────────────────────────

    def test_market_ttl_clamped_minimum(self):
        """market_hour_ttl < 30 → 钳位到 30。"""
        self._mock_is_open.return_value = True
        self._setup_config(
            market_hour_aware=["price"],
            cache_ttl={"price": 86400},
            market_hour_ttl=10,
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        self.assertEqual(ttl, 30)

    def test_market_ttl_clamped_maximum(self):
        """market_hour_ttl > 86400 → 钳位到 86400。"""
        self._mock_is_open.return_value = True
        self._setup_config(
            market_hour_aware=["price"],
            cache_ttl={"price": 86400},
            market_hour_ttl=999999,
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        self.assertEqual(ttl, 86400)

    # ── 配置缺失回退 ─────────────────────────────────────

    def test_no_config_falls_back_to_default(self):
        """无配置时 get_ttl("price") → 使用注册表默认值（CACHE_DAILY）。"""
        self._mock_is_open.return_value = False
        self._setup_config()  # 空配置
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        from src.python.constants import CACHE_DAILY
        self.assertEqual(ttl, CACHE_DAILY)

    def test_market_open_no_aware_list(self):
        """交易时段但 market_hour_aware 为空 → 使用配置的 cache_ttl。"""
        self._mock_is_open.return_value = True
        self._setup_config(
            market_hour_aware=[],
            cache_ttl={"price": 3600},
        )
        from src.python.cache import get_ttl

        ttl = get_ttl("price")
        self.assertEqual(ttl, 3600)


# ═══════════════════════════════════════════════════════════
# T3: 午间休市 — is_midday_break
# ═══════════════════════════════════════════════════════════


class TestIsMiddayBreak(unittest.TestCase):
    """测试 is_midday_break() 午间休市判断。

    午间休市时段：11:30-13:00（北京时区，不含端点）。
    """

    def _run_at(self, hour: int, minute: int, weekday: int = 0) -> bool:
        """在 mock 的北京时间下调用 is_midday_break。"""
        with patch("src.python.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 7, 6 + weekday, hour, minute,
                tzinfo=timezone(timedelta(hours=8)),
            )
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            from src.python.market_hours import is_midday_break
            return is_midday_break()

    def test_morning_session(self):
        """早盘 10:00 → False。"""
        self.assertFalse(self._run_at(10, 0))

    def test_lunch_break(self):
        """T3: 午间休市 12:00 → True。"""
        self.assertTrue(self._run_at(12, 0))

    def test_afternoon_session(self):
        """午盘 14:00 → False。"""
        self.assertFalse(self._run_at(14, 0))

    def test_weekend(self):
        """T5: 周六 12:00 → False（周末无午休概念）。"""
        self.assertFalse(self._run_at(12, 0, weekday=5))

    def test_boundary_morning_end(self):
        """11:30 → False（仍在交易时段）。"""
        self.assertFalse(self._run_at(11, 30))

    def test_boundary_lunch_start(self):
        """11:31 → True（进入午休）。"""
        self.assertTrue(self._run_at(11, 31))

    def test_boundary_afternoon_start(self):
        """13:00 → False（午盘开始）。"""
        self.assertFalse(self._run_at(13, 0))


# ═══════════════════════════════════════════════════════════
# T7-T11: 产品类型识别 — classify_holdings
# ═══════════════════════════════════════════════════════════


class TestClassifyHoldings(unittest.TestCase):
    """测试 market_value.classify_holdings 产品类型分类。

    T7: 国内场外 / T8: QDII / T9: ETF / T10: 股票 / T11: 混合。
    """

    def _classify(self, holdings: list[Holding]) -> dict[str, list]:
        from src.python.report.market_value import classify_holdings
        return classify_holdings(holdings)

    # ── T8: QDII ──────────────────────────────────────────

    def test_qdii_identified_by_name(self):
        """T8: 名称含 "QDII" → 归入 QDII。"""
        h = Holding(account="证券账户", name="易方达纳斯达克100QDII", code="01878", shares=100, cost_price=1.0)
        cats = self._classify([h])
        self.assertIn("QDII", cats)
        self.assertEqual(len(cats["QDII"]), 1)
        self.assertEqual(len(cats["国内场外"]), 0)

    def test_qdii_lowercase(self):
        """QDII 大小写不敏感。"""
        h = Holding(account="证券账户", name="纳斯达克qdiiETF", code="51310", shares=100, cost_price=1.0)
        cats = self._classify([h])
        self.assertIn("QDII", cats)
        self.assertEqual(len(cats["QDII"]), 1)

    def test_qdii_precedes_channel(self):
        """QDII 优先级高于场外渠道判断（账户含基金关键词但名称含 QDII）。"""
        h = Holding(account="基金账户", name="华夏全球QDII", code="000041", shares=100, cost_price=1.0)
        cats = self._classify([h])
        self.assertIn("QDII", cats)
        self.assertEqual(len(cats["QDII"]), 1)
        self.assertEqual(len(cats["国内场外"]), 0)

    # ── T7: 国内场外 ──────────────────────────────────────

    def test_otc_by_fund_account(self):
        """T7: 基金账户持有 → 归入国内场外。"""
        h = Holding(account="蚂蚁基金", name="中欧医疗健康混合", code="003095", shares=500, cost_price=1.5)
        cats = self._classify([h])
        self.assertIn("国内场外", cats)
        self.assertEqual(len(cats["国内场外"]), 1)

    def test_otc_by_alipay_account(self):
        """支付宝账户 → 国内场外。"""
        h = Holding(account="支付宝", name="天弘沪深300", code="000961", shares=1000, cost_price=1.2)
        cats = self._classify([h])
        self.assertEqual(len(cats["国内场外"]), 1)

    def test_otc_by_wechat_account(self):
        """微信账户 → 国内场外。"""
        h = Holding(account="微信理财通", name="易方达中小盘", code="110011", shares=200, cost_price=2.0)
        cats = self._classify([h])
        self.assertEqual(len(cats["国内场外"]), 1)

    def test_otc_by_bank_account(self):
        """银行账户 → 国内场外。"""
        h = Holding(account="招商银行", name="富国天惠", code="161005", shares=300, cost_price=1.8)
        cats = self._classify([h])
        self.assertEqual(len(cats["国内场外"]), 1)

    # ── T9: ETF ──────────────────────────────────────────

    def test_etf_by_name(self):
        """T9: 名称含 "ETF" → 归入场内ETF。"""
        h = Holding(account="证券账户", name="电池ETF", code="561910", shares=1000, cost_price=10.0)
        cats = self._classify([h])
        self.assertIn("场内ETF", cats)
        self.assertEqual(len(cats["场内ETF"]), 1)

    def test_etf_by_code_5xxx(self):
        """5xxx 代码 → 场内ETF。"""
        h = Holding(account="证券账户", name="上证50", code="510050", shares=500, cost_price=3.0)
        cats = self._classify([h])
        self.assertEqual(len(cats["场内ETF"]), 1)

    def test_etf_by_code_1xxx(self):
        """1xxx 代码 → 场内ETF。"""
        h = Holding(account="证券账户", name="创业板ETF", code="159915", shares=800, cost_price=2.0)
        cats = self._classify([h])
        self.assertEqual(len(cats["场内ETF"]), 1)

    # ── T10: 股票 ─────────────────────────────────────────

    def test_stock_by_code_6xxx(self):
        """T10: 6xxx 代码 → 场内股票。"""
        h = Holding(account="证券账户", name="长江电力", code="600900", shares=500, cost_price=28.0)
        cats = self._classify([h])
        self.assertIn("场内股票", cats)
        self.assertEqual(len(cats["场内股票"]), 1)

    def test_stock_by_code_0xxx(self):
        """0xxx 代码 → 场内股票。"""
        h = Holding(account="证券账户", name="中兴通讯", code="000063", shares=300, cost_price=35.0)
        cats = self._classify([h])
        self.assertEqual(len(cats["场内股票"]), 1)

    def test_stock_by_code_3xxx(self):
        """3xxx 代码 → 场内股票。"""
        h = Holding(account="证券账户", name="宁德时代", code="300750", shares=100, cost_price=200.0)
        cats = self._classify([h])
        self.assertEqual(len(cats["场内股票"]), 1)

    # ── T11: 混合持仓 ────────────────────────────────────

    def test_mixed_holdings_separated_correctly(self):
        """T11: 混合持仓（QDII + 场外 + ETF + 股票）各归各类。"""
        holdings = [
            Holding("证券账户", "纳斯达克100QDII", "01878", 100, 1.0),   # QDII
            Holding("支付宝", "天弘沪深300", "000961", 1000, 1.2),       # 国内场外
            Holding("证券账户", "电池ETF", "561910", 1000, 10.0),         # 场内ETF
            Holding("证券账户", "长江电力", "600900", 500, 28.0),        # 场内股票
        ]
        cats = self._classify(holdings)
        self.assertEqual(len(cats["QDII"]), 1)
        self.assertEqual(len(cats["国内场外"]), 1)
        self.assertEqual(len(cats["场内ETF"]), 1)
        self.assertEqual(len(cats["场内股票"]), 1)

    def test_etf_precedes_stock(self):
        """ETF 判断优先于股票（代码 5xxx 但非 ETF 名称 → 仍归 ETF）。"""
        h = Holding(account="证券账户", name="某封闭基金", code="501025", shares=100, cost_price=1.0)
        cats = self._classify([h])
        self.assertEqual(len(cats["场内ETF"]), 1)
        self.assertEqual(len(cats["场内股票"]), 0)

    def test_default_to_otc(self):
        """无法识别的品种 → 默认归入国内场外。"""
        h = Holding(account="未知账户", name="某特殊产品", code="999999", shares=100, cost_price=1.0)
        cats = self._classify([h])
        self.assertEqual(len(cats["国内场外"]), 1)
        self.assertEqual(len(cats["场内股票"]), 0)
        self.assertEqual(len(cats["场内ETF"]), 0)
        self.assertEqual(len(cats["QDII"]), 0)

    def test_empty_holdings(self):
        """空持仓 → 所有分类为空列表。"""
        cats = self._classify([])
        for cat in ("场内股票", "场内ETF", "国内场外", "QDII"):
            self.assertEqual(len(cats[cat]), 0)


# ═══════════════════════════════════════════════════════════
# T7-T8: _count_trading_days_back
# ═══════════════════════════════════════════════════════════


class TestCountTradingDaysBack(unittest.TestCase):
    """测试 _count_trading_days_back 交易日回退计数。

    用于场外基金净值日期 T-N 标签判定。
    """

    def setUp(self):
        # 模拟交易日历：包含必要的前后交易日
        # 以 2026-07-03（周五）为 T
        self._calendar_patcher = patch(
            "src.python.report.market_value._get_trading_calendar",
        )
        self._mock_calendar = self._calendar_patcher.start()
        # 7月：1(三) 2(四) 3(五) 6(一) 7(二) 8(三) 9(四) 10(五)
        # 6月：26(五) 29(一) 30(二)
        self._mock_calendar.return_value = {
            "2026-06-26", "2026-06-29", "2026-06-30",
            "2026-07-01", "2026-07-02", "2026-07-03",
            "2026-07-06", "2026-07-07", "2026-07-08",
            "2026-07-09", "2026-07-10",
        }

    def tearDown(self):
        self._calendar_patcher.stop()

    def _count(self, trading_day: str, nav_date: str) -> int | None:
        from src.python.report.market_value import _count_trading_days_back
        return _count_trading_days_back(trading_day, nav_date)

    def test_same_day_returns_none(self):
        """nav_date == trading_day → None。"""
        self.assertIsNone(self._count("2026-07-03", "2026-07-03"))

    def test_prev_trading_day_returns_1(self):
        """nav_date == T-1（2026-07-02）→ 1。"""
        self.assertEqual(self._count("2026-07-03", "2026-07-02"), 1)

    def test_three_days_back_returns_3(self):
        """nav_date == T-3（2026-06-30）→ 3。"""
        self.assertEqual(self._count("2026-07-03", "2026-06-30"), 3)

    def test_five_days_back_returns_5(self):
        """nav_date == T-5（2026-06-26）→ 5。"""
        self.assertEqual(self._count("2026-07-03", "2026-06-26"), 5)

    def test_six_days_back_returns_none(self):
        """nav_date > T-5（如 2026-06-25 非交易日列表）→ None。"""
        result = self._count("2026-07-03", "2026-06-25")
        self.assertIsNone(result)

    def test_future_date_returns_none(self):
        """nav_date > trading_day → None。"""
        self.assertIsNone(self._count("2026-07-03", "2026-07-06"))

    def test_invalid_date_format_returns_none(self):
        """无效日期格式 → None。"""
        self.assertIsNone(self._count("2026-07-03", "not-a-date"))
        self.assertIsNone(self._count("not-a-date", "2026-07-01"))
        self.assertIsNone(self._count("not-a-date", "also-bad"))

    def test_empty_calendar_still_counts(self):
        """交易日历为空 → 按自然日回退判断（仅排除周末）。"""
        self._mock_calendar.return_value = set()
        # 2026-07-03（周五）→ 2026-06-30（周二）中间跳过 7/1(三) 7/2(四)
        # 自然日：7/2(四) 1天, 7/1(三) 2天, 6/30(二) 3天
        # 因为 calendar 为空，回退到 weekday<5 判断
        # 6/30(二) weekday=1 → 是交易日
        # 7/1(三) weekday=2 → 是交易日
        # 7/2(四) weekday=3 → 是交易日
        # 所以从 7/3 到 6/30 有 3 个"交易日"
        result = self._count("2026-07-03", "2026-06-30")
        self.assertEqual(result, 3)

    def test_holiday_skipped(self):
        """节假日被跳过不计数（2026-07-03→2026-06-29 跳过 6/30+7/1+7/2）。"""
        # 模拟 6/30(二) 也被标记为非交易日（节假日）
        self._mock_calendar.return_value = {
            "2026-06-26", "2026-06-29",
            "2026-07-03",
        }
        # 从 7/3(五) 回退：7/2(四)不在日历→跳过, 7/1(三)不在→跳过,
        # 6/30(二)不在→跳过, 6/29(一)在日历→T-1
        result = self._count("2026-07-03", "2026-06-29")
        self.assertEqual(result, 1)


# ═══════════════════════════════════════════════════════════
# T6: 长假边界 — _get_trading_calendar 缓存行为
# ═══════════════════════════════════════════════════════════


class TestGetTradingCalendarCache(unittest.TestCase):
    """测试 _get_trading_calendar 的缓存获取和回退行为。"""

    def setUp(self):
        self._cache_get_patcher = patch("src.python.report.market_value.cache.get")
        self._mock_cache_get = self._cache_get_patcher.start()
        self._cache_set_patcher = patch("src.python.report.market_value.cache.set")
        self._mock_cache_set = self._cache_set_patcher.start()
        self._get_ttl_patcher = patch("src.python.report.market_value.cache.get_ttl",
                                       return_value=1209600)
        self._mock_get_ttl = self._get_ttl_patcher.start()

    def tearDown(self):
        self._get_ttl_patcher.stop()
        self._cache_set_patcher.stop()
        self._cache_get_patcher.stop()

    def test_cache_hit_returns_set(self):
        """缓存命中 → 返回日期 set。"""
        from src.python.report.market_value import _get_trading_calendar

        self._mock_cache_get.return_value = ["2026-07-01", "2026-07-02", "2026-07-03"]
        result = _get_trading_calendar()
        self.assertEqual(result, {"2026-07-01", "2026-07-02", "2026-07-03"})
        self._mock_cache_set.assert_not_called()

    def test_cache_miss_calls_akshare(self):
        """缓存未命中 → 调用 akshare 并写入缓存。"""
        from src.python.report.market_value import _get_trading_calendar

        self._mock_cache_get.return_value = None
        with patch("akshare.tool_trade_date_hist_sina") as mock_fn:
            import pandas as pd
            mock_fn.return_value = pd.DataFrame({
                "trade_date": ["2026-07-01", "2026-07-02"],
            })
            result = _get_trading_calendar()
            self.assertEqual(result, {"2026-07-01", "2026-07-02"})
            self._mock_cache_set.assert_called_once()

    def test_akshare_failure_returns_empty(self):
        """akshare 不可用 → 返回空 set。"""
        from src.python.report.market_value import _get_trading_calendar

        self._mock_cache_get.return_value = None
        with patch("akshare.tool_trade_date_hist_sina", side_effect=Exception("API error")):
            result = _get_trading_calendar()
            self.assertEqual(result, set())
        self._mock_cache_set.assert_not_called()

    def test_akshare_exception_returns_empty(self):
        """akshare 抛异常 → 返回空 set。"""
        from src.python.report.market_value import _get_trading_calendar

        self._mock_cache_get.return_value = None
        with patch("akshare.tool_trade_date_hist_sina", side_effect=Exception("API error")):
            result = _get_trading_calendar()
            self.assertEqual(result, set())
        self._mock_cache_set.assert_not_called()

    def test_cached_non_list_ignored(self):
        """缓存值非 list → 视为未命中，重新获取。"""
        from src.python.report.market_value import _get_trading_calendar

        self._mock_cache_get.return_value = {"not": "a list"}
        with patch("akshare.tool_trade_date_hist_sina") as mock_fn:
            import pandas as pd
            mock_fn.return_value = pd.DataFrame({
                "trade_date": ["2026-07-01"],
            })
            result = _get_trading_calendar()
            self.assertEqual(result, {"2026-07-01"})


# ═══════════════════════════════════════════════════════════
# T6: get_last_trading_day 长假边界补充
# ═══════════════════════════════════════════════════════════


class TestLastTradingDayExtended(unittest.TestCase):
    """get_last_trading_day 长假边界场景补充测试。

    现有 test_market_value.py 已覆盖基本场景，
    这里补充长假跨周和盘前判断的特定场景。
    """

    def _run_at(self, dt: datetime, calendar: set[str] | None = None) -> str:
        """在 mock 时间和日历下调用 get_last_trading_day。"""
        with (
            patch("src.python.report.market_value._is_trading_day") as mock_td,
            patch("src.python.report.market_value.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = dt
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            if calendar is not None:
                mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in calendar
            else:
                mock_td.side_effect = lambda d: d.weekday() < 5

            from src.python.report.market_value import get_last_trading_day
            return get_last_trading_day()

    # ── 长假：国庆节 ──────────────────────────────────────

    def test_during_holiday_week_returns_pre_holiday(self):
        """T6: 国庆假期中运行 → 返回节前最后交易日。"""
        # 2026-10-03（周六）在国庆长假中
        dt = datetime(2026, 10, 3, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        # 交易日历：9/30（三）为节前最后交易日，10/1~10/7 为非交易日
        calendar = {
            "2026-09-28", "2026-09-29", "2026-09-30",  # 节前
            "2026-10-09", "2026-10-10",  # 节后
        }
        result = self._run_at(dt, calendar)
        self.assertEqual(result, "2026-09-30")

    def test_holiday_pre_market_returns_pre_holiday(self):
        """T6: 节后首个交易日盘前（9:00）→ 返回节前最后交易日。"""
        dt = datetime(2026, 10, 9, 9, 0, tzinfo=timezone(timedelta(hours=8)))
        calendar = {
            "2026-09-30",  # 节前
            "2026-10-09",  # 节后首个交易日
        }
        result = self._run_at(dt, calendar)
        # 盘前（< 9:30）退回昨天即 10/8，但 10/8 非交易日
        # 再向前找 10/7~10/1 都非交易日，退回 9/30
        self.assertEqual(result, "2026-09-30")

    def test_holiday_post_market_returns_today(self):
        """T6: 节后首个交易日盘后（15:30）→ 返回当天。"""
        dt = datetime(2026, 10, 9, 15, 30, tzinfo=timezone(timedelta(hours=8)))
        calendar = {
            "2026-09-30", "2026-10-09",
        }
        result = self._run_at(dt, calendar)
        self.assertEqual(result, "2026-10-09")

    # ── 盘前边界 ─────────────────────────────────────────

    def test_monday_pre_market_returns_friday(self):
        """T2: 周一 9:00（盘前）→ 上周五。"""
        dt = datetime(2026, 7, 6, 9, 0, tzinfo=timezone(timedelta(hours=8)))
        calendar = {"2026-07-03", "2026-07-06"}  # 周五, 周一
        result = self._run_at(dt, calendar)
        self.assertEqual(result, "2026-07-03")

    def test_monday_market_open_returns_monday(self):
        """周一 10:00（盘中）→ 当天。"""
        dt = datetime(2026, 7, 6, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        calendar = {"2026-07-03", "2026-07-06"}
        result = self._run_at(dt, calendar)
        self.assertEqual(result, "2026-07-06")

    # ── 跨 UTC 日期线 ────────────────────────────────────

    def test_utc_midnight_beijing_morning(self):
        """系统 UTC 时区，北京时间周二 09:00（盘前）→ 周一。"""
        # 北京时间周二 09:00 = UTC 周二 01:00
        # 系统时区 UTC → datetime.now() 返回 UTC 时间
        # 但盘前判断基于北京时间 < 9:30
        from unittest.mock import patch as _patch
        beijing_tz = timezone(timedelta(hours=8))
        utc_tz = timezone.utc

        # 北京时间 2026-07-07（周二）09:00
        beijing_dt = datetime(2026, 7, 7, 9, 0, tzinfo=beijing_tz)
        utc_dt = beijing_dt.astimezone(utc_tz)  # 2026-07-07 01:00 UTC

        calendar = {"2026-07-06", "2026-07-07"}

        with _patch("src.python.report.market_value._is_trading_day") as mock_td:
            mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in calendar
            with _patch("src.python.report.market_value.datetime") as mock_dt_mod:
                # 模拟系统时区 UTC，当前时间为 utc_dt
                mock_dt_mod.now.return_value = utc_dt
                mock_dt_mod.timezone = timezone
                mock_dt_mod.timedelta = timedelta
                mock_dt_mod.side_effect = lambda *a, **kw: datetime(*a, **kw)
                from src.python.report.market_value import get_last_trading_day
                result = get_last_trading_day()
                # 北京时间 09:00 < 09:30，盘前退回昨天
                # 昨天 = 2026-07-06（周一），且在交易日历中
                self.assertEqual(result, "2026-07-06")


# ═══════════════════════════════════════════════════════════
# T12: 盘中→盘后 缓存 TTL 变更
# ═══════════════════════════════════════════════════════════


class TestGetTtlTransition(unittest.TestCase):
    """T12: 盘中→盘后 get_ttl 返回值变化。

    确保同一天从交易时段到收盘后，get_ttl 返回正确的 TTL。
    """

    def test_open_to_close_price_ttl_changes(self):
        """盘中 30s → 盘后 86400。"""
        from src.python.cache import get_ttl

        with (
            patch("src.python.cache._is_market_open", return_value=True),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "cache_ttl": {"price": 86400},
                "market_hour_ttl": 30,
            }
            open_ttl = get_ttl("price")
            self.assertEqual(open_ttl, 30)

        with (
            patch("src.python.cache._is_market_open", return_value=False),
            patch("src.python.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = {
                "market_hour_aware": ["price"],
                "cache_ttl": {"price": 86400},
                "market_hour_ttl": 30,
            }
            closed_ttl = get_ttl("price")
            self.assertEqual(closed_ttl, 86400)

        self.assertNotEqual(open_ttl, closed_ttl)


# ═══════════════════════════════════════════════════════════
# T14: 首次启动 + 非交易日 — 无缓存时市场状态影响
# ═══════════════════════════════════════════════════════════


class TestFirstLaunchNonTradingDay(unittest.TestCase):
    """T14: 首次启动 + 非交易日 场景测试。

    无缓存时各数据获取接口在非交易日的表现。
    """

    def test_cache_miss_returns_none(self):
        """非交易日 + 无缓存 → cache.get 返回 None。"""
        from src.python.cache import get as cache_get

        with patch("src.python.cache._CACHE_DIR", new="d:/__nonexistent_cache_dir__"):
            result = cache_get("nonexistent_key", 9999)
            self.assertIsNone(result)

    def test_non_trading_day_fallback_closed(self):
        """非交易日 → is_market_open fallback 返回 False。"""
        # 周六 10:00 北京时间
        with patch("src.python.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 7, 4, 10, 0, tzinfo=timezone(timedelta(hours=8)),
            )
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            from src.python.market_hours import is_market_open
            self.assertFalse(is_market_open())


# ═══════════════════════════════════════════════════════════
# T15/T16: 断网 + 市场状态 — fetch_market_data 使用 market-aware TTL
# ═══════════════════════════════════════════════════════════


class TestFetchMarketDataMarketAware(unittest.TestCase):
    """T15/T16: fetch_market_data 在不同市场状态下使用正确 TTL。

    不 mock 整个 fetch 流程，仅验证其内部调用 get_ttl("price")。
    """

    @patch("src.python.fetcher.price._fetch_with_fallback")
    @patch("src.python.fetcher.price.get_ttl")
    def test_fetch_price_calls_get_ttl(self, mock_get_ttl, mock_fetch):
        """fetch_market_data 调用 get_ttl("price")。"""
        mock_get_ttl.return_value = 30
        mock_fetch.return_value = {"price": 10.0, "name": "test"}

        from src.python.fetcher.price import fetch_market_data
        fetch_market_data("600900", "长江电力")

        mock_get_ttl.assert_called_once_with("price")
        # _fetch_with_fallback 被调用时 cache_ttl 参数为 30
        call_kwargs = mock_fetch.call_args[1]
        self.assertEqual(call_kwargs["cache_ttl"], 30)

    @patch("src.python.fetcher.price._fetch_with_fallback")
    @patch("src.python.fetcher.price.get_ttl")
    def test_get_ttl_called_with_price(self, mock_get_ttl, mock_fetch):
        """验证 get_ttl 的参数为 'price'。"""
        mock_get_ttl.return_value = 86400
        mock_fetch.return_value = {"price": 10.0}

        from src.python.fetcher.price import fetch_market_data
        fetch_market_data("003095")

        mock_get_ttl.assert_called_once_with("price")


if __name__ == "__main__":
    unittest.main()
