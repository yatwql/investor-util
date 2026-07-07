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
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.python.models import Holding


# ═══════════════════════════════════════════════════════════
# T1-T6: 市场状态组合 — get_ttl 市场时段感知
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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


@pytest.mark.scenario_datetime
@pytest.mark.scenario
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

        # v0.2.89 新增价格缓存新鲜度校验，两次调用：首次获取 + 跨日刷新
        self.assertEqual(mock_get_ttl.call_count, 2)
        mock_get_ttl.assert_any_call("price")
        # _fetch_with_fallback 第二次（刷新）调用时 cache_ttl 参数为 30
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

        # v0.2.89 新增价格缓存新鲜度校验，两次调用
        self.assertEqual(mock_get_ttl.call_count, 2)
        mock_get_ttl.assert_any_call("price")


# ═══════════════════════════════════════════════════════════
# T13: 交易时段切换缝隙 — 边界时间精度
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestT13TradingSessionSwitch(unittest.TestCase):
    """T13: 午休/收盘切换前夕的缓存/数据行为。

    验证 11:29:59 / 11:30:00 / 12:59:59 / 13:00:00 /
    14:59:59 / 15:00:00 / 15:00:01 这 7 个边界点的市场状态判断正确。

    注意：_is_market_open_fallback 使用 <= 闭合边界，
    因此 11:30 和 15:00 仍视为"交易中"（含最后 1 秒），
    而 is_midday_break() 使用 [690, 780) 半开区间。
    """

    def _is_open(self, year, month, day, hour, minute, second=0):
        """Patch market_hours.datetime 并返回 _is_market_open_fallback()。"""
        with patch("src.python.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                year, month, day, hour, minute, second,
                tzinfo=timezone(timedelta(hours=8)),
            )
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_dt.saturday = 5
            mock_dt.sunday = 6
            from src.python.market_hours import _is_market_open_fallback
            return _is_market_open_fallback(hour * 60 + minute)

    def _midday_break(self, year, month, day, hour, minute, second=0):
        """Patch market_hours.datetime 并返回 is_midday_break()。"""
        with patch("src.python.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                year, month, day, hour, minute, second,
                tzinfo=timezone(timedelta(hours=8)),
            )
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_dt.saturday = 5
            mock_dt.sunday = 6
            from src.python.market_hours import is_midday_break
            return is_midday_break()

    # ── 午休入口 ──

    def test_midday_break_112959(self):
        """11:29:59 — 仍在交易，非午休。"""
        self.assertTrue(self._is_open(2026, 7, 3, 11, 29, 59))
        self.assertFalse(self._midday_break(2026, 7, 3, 11, 29, 59))

    def test_midday_break_113000(self):
        """11:30:00 — is_midday_break=False（闭区间不含 690），
        _is_market_open_fallback 含 11:30。"""
        self.assertTrue(self._is_open(2026, 7, 3, 11, 30, 0))
        self.assertFalse(self._midday_break(2026, 7, 3, 11, 30, 0))

    def test_midday_break_125959(self):
        """12:59:59 — 仍午休。"""
        self.assertFalse(self._is_open(2026, 7, 3, 12, 59, 59))
        self.assertTrue(self._midday_break(2026, 7, 3, 12, 59, 59))

    def test_midday_break_130000(self):
        """13:00:00 — 午休结束，恢复交易。"""
        self.assertTrue(self._is_open(2026, 7, 3, 13, 0, 0))
        self.assertFalse(self._midday_break(2026, 7, 3, 13, 0, 0))

    # ── 收盘边界 ──

    def test_close_switch_145959(self):
        """14:59:59 — 仍交易。"""
        self.assertTrue(self._is_open(2026, 7, 3, 14, 59, 59))

    def test_close_switch_150000(self):
        """15:00:00 — _is_market_open_fallback 使用 <= 闭区间，仍返回 True。"""
        self.assertTrue(self._is_open(2026, 7, 3, 15, 0, 0))

    def test_close_switch_1500(self):
        """15:00（刚好 900 分钟闭区间终点）→ 含最后 1 分钟仍交易。"""
        self.assertTrue(self._is_open(2026, 7, 3, 15, 0, 0))

    def test_close_switch_1501(self):
        """15:01（901 分钟）→ 收盘。"""
        self.assertFalse(self._is_open(2026, 7, 3, 15, 1, 0))


# ═══════════════════════════════════════════════════════════
# 净值数据空窗期
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestNavDataGap(unittest.TestCase):
    """净值数据空窗期：基金净值未发布（15:00 前）时的降级行为。

    验证 nav_date ≠ T → today_profit = 0；
    价格日期描述为旧日期。
    """

    def _compute_row(self, nav_date: str, trading_day: str = "2026-07-03"):
        """调用 _compute_detail_row 并返回 DetailRow。"""
        from src.python.report.market_value import _compute_detail_row
        from src.python.models import Holding

        h = Holding(account="证券", name="测试基金", code="003095",
                    shares=1000.0, cost_price=1.5)
        mkt = {
            "price": 1.6, "yesterday_close": 1.55,
            "price_date": nav_date, "source_api": "eastmoney",
            "name": "测试基金", "code": "003095",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value=trading_day):
            return _compute_detail_row(h, mkt)

    def test_nav_date_t_equal_today_profit_calculated(self):
        """nav_date == T → 计算本日盈亏。"""
        row = self._compute_row("2026-07-03")
        self.assertGreater(row.today_profit, 0)

    def test_nav_date_t_minus_1_today_profit_zero(self):
        """nav_date == T-1（15:00 前空窗期）→ today_profit = 0。"""
        row = self._compute_row("2026-07-02")
        self.assertEqual(row.today_profit, 0.0)

    def test_nav_date_none_today_profit_zero(self):
        """nav_date 为空 → today_profit = 0。"""
        row = self._compute_row("")
        self.assertEqual(row.today_profit, 0.0)

    def test_nav_date_t_minus_1_price_type_official_prev(self):
        """nav_date == T-1 → 价格类型显示 "官方净值(T-1)"。"""
        from src.python.report.market_value import _determine_price_type

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-07-02"),
        ):
            ptype = _determine_price_type(
                "eastmoney", "2026-07-02", "2026-07-03",
            )
            self.assertEqual(ptype, "官方净值(T-1)")


# ═══════════════════════════════════════════════════════════
# 多时区 QDII 净值一致性
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestQdiiDateConsistency(unittest.TestCase):
    """多时区 QDII 净值一致性：不同交易时区 QDII 净值的日期标注。

    QDII 基金因时差净值延迟一天发布（T-1），
    在 price_update_status 中应视为"已更新"。
    """

    @staticmethod
    def _make_detail(name: str, nav_date: str, source_api: str = "eastmoney"):
        """构造 DetailRow。"""
        from src.python.report.market_value import DetailRow
        return DetailRow(
            account="证券", name=name, code="003095",
            shares=100.0, cost=100.0,
            price=1.2, yesterday_close=1.15,
            nav_date=nav_date, source_api=source_api,
            today_profit=0.0, profit=20.0,
            profit_rate=0.0, premium="--",
            market_value=120.0,
        )

    def _update_status(self, details: list) -> tuple:
        """调用 price_update_status 返回更新状态。"""
        from src.python.report.market_value import price_update_status

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-07-02"),
        ):
            return price_update_status(details, "2026-07-03")

    def test_qdii_nav_date_t_updated(self):
        """QDII + nav_date == T → 更新完成。"""
        d = self._make_detail("标普500QDII", "2026-07-03")
        updated, total, all_updated = self._update_status([d])
        self.assertEqual(updated, 1)
        self.assertEqual(total, 1)
        self.assertTrue(all_updated)

    def test_qdii_nav_date_t_minus_1_updated(self):
        """QDII + nav_date == T-1 → 视为更新完成（时差延迟一天）。"""
        d = self._make_detail("标普500QDII", "2026-07-02")
        updated, total, all_updated = self._update_status([d])
        self.assertEqual(updated, 1)
        self.assertEqual(total, 1)
        self.assertTrue(all_updated)

    def test_non_qdii_nav_date_t_minus_1_not_updated(self):
        """非 QDII + nav_date == T-1 → 未更新。"""
        d = self._make_detail("易方达蓝筹", "2026-07-02")
        updated, total, all_updated = self._update_status([d])
        self.assertEqual(updated, 0)
        self.assertEqual(total, 1)
        self.assertFalse(all_updated)

    def test_qdii_nav_date_t_minus_2_not_updated(self):
        """QDII + nav_date == T-2（延迟超过 1 天）→ 未更新。"""
        d = self._make_detail("标普500QDII", "2026-07-01")
        updated, total, all_updated = self._update_status([d])
        self.assertEqual(updated, 0)
        self.assertEqual(total, 1)
        self.assertFalse(all_updated)

    def test_tencent_nav_date_t_updated(self):
        """场内（tencent）+ nav_date == T → 更新完成。"""
        d = self._make_detail("贵州茅台", "2026-07-03", source_api="tencent")
        updated, total, all_updated = self._update_status([d])
        self.assertEqual(updated, 1)
        self.assertTrue(all_updated)

    def test_tencent_nav_date_t_minus_1_not_updated(self):
        """场内（tencent）+ nav_date == T-1 → 未更新。"""
        d = self._make_detail("贵州茅台", "2026-07-02", source_api="tencent")
        updated, total, all_updated = self._update_status([d])
        self.assertEqual(updated, 0)
        self.assertFalse(all_updated)


# ═══════════════════════════════════════════════════════════
# T17: 跨月/跨年报告 — get_last_trading_day 跨年行为
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestCrossYearReport(unittest.TestCase):
    """T17: 跨月/跨年报告 — get_last_trading_day / get_prev_trading_day 跨年行为。

    验证 12 月 31 日和 1 月 2 日生成的跨年行情数据连续性。
    """

    _CROSS_YEAR_CALENDAR = {
        "2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31",
        "2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07",
    }

    @staticmethod
    def _is_trading_side_effect(d):
        return d.strftime("%Y-%m-%d") in TestCrossYearReport._CROSS_YEAR_CALENDAR

    def _run_get_last_trading_day(self, dt):
        with (
            patch("src.python.report.market_value.datetime") as mock_dt,
            patch("src.python.report.market_value._is_trading_day") as mock_td,
        ):
            mock_dt.now.return_value = dt
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_td.side_effect = self._is_trading_side_effect
            from src.python.report.market_value import get_last_trading_day
            return get_last_trading_day()

    def test_dec31_intraday_returns_dec31(self):
        """12月31日盘中 → 返回 2026-12-31。"""
        dt = datetime(2026, 12, 31, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(self._run_get_last_trading_day(dt), "2026-12-31")

    def test_jan1_holiday_returns_dec31(self):
        """1月1日（元旦假期）→ 返回 2026-12-31（跨年回退）。"""
        dt = datetime(2027, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(self._run_get_last_trading_day(dt), "2026-12-31")

    def test_jan4_intraday_returns_jan4(self):
        """1月4日盘中（节后首个交易日）→ 返回 2027-01-04。"""
        dt = datetime(2027, 1, 4, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(self._run_get_last_trading_day(dt), "2027-01-04")

    def test_jan4_pre_market_returns_dec31(self):
        """1月4日盘前（9:00）→ 先退回1月3日（非交易日）→ 最终回退到2026-12-31。"""
        dt = datetime(2027, 1, 4, 9, 0, tzinfo=timezone(timedelta(hours=8)))
        self.assertEqual(self._run_get_last_trading_day(dt), "2026-12-31")

    def test_prev_trading_day_cross_year(self):
        """get_prev_trading_day('2027-01-04') → '2026-12-31'（跨年查找）。"""
        with patch("src.python.report.market_value._is_trading_day") as mock_td:
            mock_td.side_effect = self._is_trading_side_effect
            from src.python.report.market_value import get_prev_trading_day
            self.assertEqual(get_prev_trading_day("2027-01-04"), "2026-12-31")


# ═══════════════════════════════════════════════════════════
# T18: 季末/年末效应 — 基金调仓前后净值跳变
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestQuarterEndEffect(unittest.TestCase):
    """T18: 季末/年末效应 — 基金季末调仓日前后净值跳变。

    验证大额净值变动时 today_profit 计算正确、profit_rate 无除零异常。
    """

    def _compute(self, nav_date: str, price: float, yclose: float,
                 trading_day: str = "2026-09-30") -> "DetailRow":
        from src.python.report.market_value import DetailRow, _compute_detail_row
        h = Holding(account="证券", name="测试基金", code="003095",
                    shares=1000.0, cost_price=1.5)
        mkt = {
            "price": price, "yesterday_close": yclose,
            "price_date": nav_date, "source_api": "eastmoney",
            "name": "测试基金", "code": "003095",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value=trading_day):
            return _compute_detail_row(h, mkt)

    def test_quarter_end_large_positive_jump(self):
        """季末调仓日净值大幅上涨（+10%）→ today_profit 正确。"""
        row = self._compute("2026-09-30", 1.65, 1.50)
        self.assertEqual(row.today_profit, 150.0)  # (1.65-1.50)*1000

    def test_quarter_end_large_negative_jump(self):
        """季末调仓日净值大幅下跌（-5%）→ 本日亏损。"""
        row = self._compute("2026-09-30", 1.425, 1.50)
        self.assertEqual(row.today_profit, -75.0)  # (1.425-1.50)*1000

    def test_quarter_end_t_minus_1_nav_not_updated(self):
        """调仓次日（T-1 净值）→ today_profit = 0（净值未更新）。"""
        row = self._compute("2026-09-29", 1.65, 1.50, trading_day="2026-09-30")
        self.assertEqual(row.today_profit, 0.0)

    def test_quarter_end_extreme_20pct_jump_no_overflow(self):
        """季末极端调仓 +20% → 计算正确无溢出。"""
        row = self._compute("2026-09-30", 1.80, 1.50)
        self.assertEqual(row.today_profit, 300.0)
        self.assertAlmostEqual(row.profit_rate, 0.20)

    def test_quarter_end_price_update_status_during_rebalance(self):
        """季末调仓日 → price_update_status 正确识别已更新资产。"""
        from src.python.report.market_value import DetailRow, price_update_status

        # 季末前最后交易日：调仓完成，净值已更新
        rebalanced = DetailRow(account="证券", name="调仓基金", code="003095",
            shares=1000, cost=1500, price=1.65, yesterday_close=1.50,
            nav_date="2026-09-30", source_api="eastmoney",
            today_profit=0.0, profit=150.0, profit_rate=0.0, premium="--",
            market_value=1650.0)
        # 场外基金净值 T-1（尚未更新）
        pending = DetailRow(account="证券", name="场外基金", code="000961",
            shares=1000, cost=1200, price=1.25, yesterday_close=1.24,
            nav_date="2026-09-29", source_api="eastmoney",
            today_profit=0.0, profit=50.0, profit_rate=0.0, premium="--",
            market_value=1250.0)

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-09-30"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-09-29"),
        ):
            updated, total, all_updated = price_update_status(
                [rebalanced, pending], "2026-09-30")
            self.assertEqual(updated, 1)
            self.assertEqual(total, 2)
            self.assertFalse(all_updated)


# ═══════════════════════════════════════════════════════════
# T19: 汇率中间价故障 — QDII 取价降级
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestExchangeRateFailure(unittest.TestCase):
    """T19: 汇率中间价故障 — 美元/港币汇率数据暂不可用时的 QDII 降级。

    当汇率数据故障导致 QDII 净值获取失败或延迟时，验证系统降级行为。
    """

    def test_qdii_market_data_none_graceful(self):
        """QDII + 行情数据为空 → 返回零值 DetailRow，不崩溃。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding(account="证券", name="标普500QDII", code="159941",
                    shares=100.0, cost_price=2.0)
        row = _compute_detail_row(h, None)
        self.assertEqual(row.market_value, 0.0)
        self.assertEqual(row.price, 0.0)
        self.assertEqual(row.today_profit, 0.0)
        self.assertEqual(row.code, "159941")
        # cost 应正确计算
        self.assertEqual(row.cost, 200.0)

    def test_qdii_stale_nav_t_minus_3(self):
        """汇率故障导致 QDII 净值延迟到 T-3 → 价格类型标注为"官方净值(T-3)"，today_profit=0。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding(account="证券", name="标普500QDII", code="159941",
                    shares=100.0, cost_price=2.0)
        mkt = {
            "price": 1.8, "yesterday_close": 1.85,
            "price_date": "2026-06-30",  # T-3
            "source_api": "eastmoney",
            "name": "标普500QDII", "code": "159941",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-07-02"),
            patch("src.python.report.market_value._count_trading_days_back",
                  return_value=3),
        ):
            row = _compute_detail_row(h, mkt)
            self.assertEqual(row.today_profit, 0.0)
            self.assertIn("T-3", row.price_type)

    def test_qdii_stale_not_updated_in_status(self):
        """汇率故障导致 QDII 净值延迟超过 1 天 → price_update_status 标记为未更新。"""
        from src.python.report.market_value import DetailRow, price_update_status

        qdii_t = DetailRow(account="证券", name="标普500QDII-A", code="159941",
            shares=100, cost=200, price=1.82, yesterday_close=1.85,
            nav_date="2026-07-03", source_api="eastmoney",
            today_profit=0.0, profit=-18.0, profit_rate=0.0, premium="--",
            market_value=182.0)
        qdii_stale = DetailRow(account="证券", name="标普500QDII-B", code="016055",
            shares=100, cost=200, price=1.80, yesterday_close=1.85,
            nav_date="2026-06-30", source_api="eastmoney",  # T-3, too stale
            today_profit=0.0, profit=-20.0, profit_rate=0.0, premium="--",
            market_value=180.0)

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-07-03"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-07-02"),
        ):
            updated, total, all_updated = price_update_status(
                [qdii_t, qdii_stale], "2026-07-03")
            self.assertEqual(updated, 1)  # T 的 QDII 已更新
            self.assertEqual(total, 2)
            self.assertFalse(all_updated)


# ═══════════════════════════════════════════════════════════
# T20: 节假日调休 — 调休工作日/放假日的交易日判断
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestHolidayMakeupWorkday(unittest.TestCase):
    """T20: 节假日调休 — 调休工作日（周日上班）vs 调休放假（周六休息）的交易日判断。

    交易日历包含调休规则时，_is_trading_day 应正确识别。
    """

    _MAKEUP_CALENDAR = {
        "2026-07-01", "2026-07-02", "2026-07-03",  # Wed-Fri 正常
        "2026-07-04",  # Saturday 调休上班（在日历中）
        "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10",  # Mon-Fri
        # 7月11日（周六）正常休息 —— 不在日历中
        # 7月12日（周日）正常休息 —— 不在日历中
    }

    def test_saturday_makeup_workday_is_trading(self):
        """周六调休上班（在交易日历中）→ _is_trading_day 返回 True。"""
        from src.python.report.market_value import _is_trading_day
        with patch("src.python.report.market_value._get_trading_calendar",
                   return_value=self._MAKEUP_CALENDAR):
            self.assertTrue(_is_trading_day(datetime(2026, 7, 4)))  # Saturday

    def test_saturday_holiday_not_in_calendar(self):
        """周六调休放假（不在交易日历中）→ _is_trading_day 返回 False。"""
        from src.python.report.market_value import _is_trading_day
        with patch("src.python.report.market_value._get_trading_calendar",
                   return_value=self._MAKEUP_CALENDAR):
            self.assertFalse(_is_trading_day(datetime(2026, 7, 11)))  # Saturday

    def test_fallback_weekend_not_trading(self):
        """无交易日历回退 → 周六日均返回 False。"""
        from src.python.report.market_value import _is_trading_day
        with patch("src.python.report.market_value._get_trading_calendar",
                   return_value=set()):
            self.assertFalse(_is_trading_day(datetime(2026, 7, 4)))   # Saturday
            self.assertFalse(_is_trading_day(datetime(2026, 7, 5)))   # Sunday

    def test_makeup_workday_market_open_still_false(self):
        """调休工作日（周六）→ is_market_open 因 weekday>=5 返回 False（已知局限）。

        is_market_open 各层都查 weekday() >= 5 快速短路，
        这是已知的局限性——调休上班日虽然 _is_trading_day 返回 True，
        但 is_market_open 返回 False。不影响缓存 TTL 等核心功能。
        """
        config_patcher = patch("src.python.config.get_config",
                               return_value={})
        config_patcher.start()
        try:
            with patch("src.python.market_hours.datetime") as mock_dt:
                mock_dt.now.return_value = datetime(
                    2026, 7, 4, 10, 0,  # Saturday makeup workday
                    tzinfo=timezone(timedelta(hours=8)),
                )
                mock_dt.timezone = timezone
                mock_dt.timedelta = timedelta
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                mock_dt.saturday = 5
                mock_dt.sunday = 6
                from src.python.market_hours import is_market_open
                self.assertFalse(is_market_open())
        finally:
            config_patcher.stop()

    def test_get_last_trading_day_via_holiday_calendar(self):
        """调休放假期间 get_last_trading_day 正确回退到最近交易日。"""
        holiday_calendar = {
            "2026-09-28", "2026-09-29", "2026-09-30",
            "2026-10-10",  # Saturday makeup workday
            "2026-10-12", "2026-10-13",
        }
        dt = datetime(2026, 10, 5, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        with (
            patch("src.python.report.market_value.datetime") as mock_dt,
            patch("src.python.report.market_value._is_trading_day") as mock_td,
        ):
            mock_dt.now.return_value = dt
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            mock_td.side_effect = lambda d: d.strftime("%Y-%m-%d") in holiday_calendar
            from src.python.report.market_value import get_last_trading_day
            # 10月5日盘中 → 非交易日（国庆假期）→ 前找 → 9月30日
            self.assertEqual(get_last_trading_day(), "2026-09-30")


# ═══════════════════════════════════════════════════════════
# T21: 港股通假期差异 — A 股开市但港股通关闭
# ═══════════════════════════════════════════════════════════


@pytest.mark.scenario_datetime
@pytest.mark.scenario
class TestHKConnectHoliday(unittest.TestCase):
    """T21: 港股通假期差异 — A 股开市但港股通关闭时的取价降级。

    A 股交易日但港股通因香港假期（如佛诞日）关闭时，QDII 净值
    延迟到 T-1，系统应正确标记 price_type 并计算 today_profit。
    """

    def test_qdii_hk_nav_t_minus_1_during_a_share_trading(self):
        """A 股盘中 + QDII 净值 T-1（港股通假期滞后）→ today_profit=0，price_type 正确。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding(account="证券", name="港股通QDII", code="016055",
                    shares=100.0, cost_price=1.0)
        mkt = {
            "price": 1.05, "yesterday_close": 1.04,
            "price_date": "2026-09-29",  # T-1（港股通假期，净值未更新）
            "source_api": "eastmoney",
            "name": "港股通QDII", "code": "016055",
        }
        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-09-30"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-09-29"),
        ):
            row = _compute_detail_row(h, mkt)
            self.assertEqual(row.today_profit, 0.0)
            self.assertEqual(row.price_type, "官方净值(T-1)")

    def test_qdii_hk_nav_t_during_a_share_trading(self):
        """A 股盘中 + QDII 净值 T（港股通正常）→ 计算本日盈亏。"""
        from src.python.report.market_value import _compute_detail_row
        h = Holding(account="证券", name="港股通QDII", code="016055",
                    shares=100.0, cost_price=1.0)
        mkt = {
            "price": 1.06, "yesterday_close": 1.04,
            "price_date": "2026-09-30",  # T（正常更新）
            "source_api": "eastmoney",
            "name": "港股通QDII", "code": "016055",
        }
        with patch("src.python.report.market_value.get_last_trading_day",
                   return_value="2026-09-30"):
            row = _compute_detail_row(h, mkt)
            self.assertGreater(row.today_profit, 0.0)

    def test_price_update_status_hk_connect_closed(self):
        """港股通假期 → QDII 净值 T-1 视为已更新（时差容忍），T-2 视为未更新。"""
        from src.python.report.market_value import DetailRow, price_update_status

        qdii_t_minus_1 = DetailRow(account="证券", name="港股通QDII-A", code="016055",
            shares=100, cost=100, price=1.05, yesterday_close=1.04,
            nav_date="2026-09-29", source_api="eastmoney",
            today_profit=0.0, profit=5.0, profit_rate=0.0, premium="--",
            market_value=105.0)
        qdii_t_minus_2 = DetailRow(account="证券", name="港股通QDII-B", code="017730",
            shares=100, cost=100, price=1.03, yesterday_close=1.05,
            nav_date="2026-09-28", source_api="eastmoney",
            today_profit=0.0, profit=3.0, profit_rate=0.0, premium="--",
            market_value=103.0)

        with (
            patch("src.python.report.market_value.get_last_trading_day",
                  return_value="2026-09-30"),
            patch("src.python.report.market_value.get_prev_trading_day",
                  return_value="2026-09-29"),
        ):
            updated, total, all_updated = price_update_status(
                [qdii_t_minus_1, qdii_t_minus_2], "2026-09-30")
            self.assertEqual(updated, 1)  # T-1 视为已更新
            self.assertEqual(total, 2)
            self.assertFalse(all_updated)


if __name__ == "__main__":
    unittest.main()
