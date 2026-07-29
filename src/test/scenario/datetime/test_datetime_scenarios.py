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
class TestGetTtlMarketAware:
    """get_ttl 市场时段感知测试 — 参数化版本。

    核心要求（T1 盘中 / T2 盘前 / T4 盘后 / T5 非交易日）：
      - 交易时段内，price/index 使用短 TTL（30s）
      - 非交易时段，price/index 使用配置的长 TTL（86400）
      - 非感知类型（rank/hold 等）不受市场状态影响
    """

    @pytest.fixture(autouse=True)
    def _setup_mocks(self):
        """自动启用的模拟环境。"""
        with patch("src.python.config.get_config") as mock_get_config:
            with patch("src.python.cache._ttl._is_market_open") as mock_is_open:
                self._mock_get_config = mock_get_config
                self._mock_is_open = mock_is_open
                yield

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

    @pytest.mark.parametrize(
        "is_open,aware,cache_ttl,mh_ttl,typ,expected",
        [
            # T1: 盘中 — short TTL for price/index
            pytest.param(True, ["price", "index"], {"price": 86400, "index": 86400}, 30, "price", 30, id="T1-price"),
            pytest.param(True, ["price", "index"], {"price": 86400, "index": 86400}, 30, "index", 30, id="T1-index"),
            pytest.param(True, ["price"], {"price": 86400}, 60, "price", 60, id="T1-custom-mh-ttl"),
            # T2/T4/T5: 非交易时段 — long TTL
            pytest.param(False, ["price", "index"], {"price": 86400, "index": 86400}, 30, "price", 86400, id="T2-pre-market"),
            pytest.param(False, ["price", "index"], {"price": 86400, "index": 86400}, 30, "index", 86400, id="T4-post-market"),
            pytest.param(False, ["price", "index"], {"price": 86400}, 30, "price", 86400, id="T5-weekend"),
            # 非感知类型不受市场状态影响
            pytest.param(True, ["price", "index"], {"rank": 7200}, 30, "rank", 7200, id="non-aware-rank"),
            pytest.param(False, ["price", "index"], {"hold": 604800}, 30, "hold", 604800, id="non-aware-hold"),
            # 边界: TTL 钳位
            pytest.param(True, ["price"], {"price": 86400}, 10, "price", 30, id="clamp-min"),
            pytest.param(True, ["price"], {"price": 86400}, 999999, "price", 86400, id="clamp-max"),
        ],
    )
    def test_ttl_scenario(self, is_open, aware, cache_ttl, mh_ttl, typ, expected):
        """参数化 TTL 场景：盘中/盘前/盘后/非交易日/钳位。"""
        self._mock_is_open.return_value = is_open
        self._setup_config(market_hour_aware=aware, cache_ttl=cache_ttl, market_hour_ttl=mh_ttl)
        from src.python.cache import get_ttl

        assert get_ttl(typ) == expected

    @pytest.mark.parametrize(
        "desc,is_open,aware,cache_ttl,typ,expected",
        [
            ("无配置 → CACHE_DAILY", False, None, None, "price", "__CACHE_DAILY__"),
            ("aware 为空 → 配置 cache_ttl", True, [], {"price": 3600}, "price", 3600),
        ],
    )
    def test_ttl_fallback(self, desc, is_open, aware, cache_ttl, typ, expected):
        """参数化回退场景：配置缺失 / aware 列表为空。"""
        self._mock_is_open.return_value = is_open
        self._setup_config(market_hour_aware=aware, cache_ttl=cache_ttl)
        if expected == "__CACHE_DAILY__":
            from src.python.constants import CACHE_DAILY

            expected = CACHE_DAILY
        from src.python.cache import get_ttl

        assert get_ttl(typ) == expected, desc


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
class TestClassifyHoldings:
    """测试 market_value.classify_holdings 产品类型分类 — 参数化版本。

    T7: 国内场外 / T8: QDII / T9: ETF / T10: 股票 / T11: 混合。
    """

    @staticmethod
    def _classify(holdings: list[Holding]) -> dict[str, list]:
        from src.python.report.market_value import classify_holdings
        return classify_holdings(holdings)

    @pytest.mark.parametrize(
        "account,name,code,expected_cat,check_otc",
        [
            # T8: QDII
            pytest.param("证券账户", "易方达纳斯达克100QDII", "01878", "QDII", True, id="T8-qdii-by-name"),
            pytest.param("证券账户", "纳斯达克qdiiETF", "51310", "QDII", False, id="T8-qdii-lowercase"),
            pytest.param("基金账户", "华夏全球QDII", "000041", "QDII", True, id="T8-qdii-precedes-channel"),
            # T7: 国内场外
            pytest.param("蚂蚁基金", "中欧医疗健康混合", "003095", "国内场外", False, id="T7-otc-fund-account"),
            pytest.param("支付宝", "天弘沪深300", "000961", "国内场外", False, id="T7-otc-alipay"),
            pytest.param("微信理财通", "易方达中小盘", "110011", "国内场外", False, id="T7-otc-wechat"),
            pytest.param("招商银行", "富国天惠", "161005", "国内场外", False, id="T7-otc-bank"),
            # T9: ETF
            pytest.param("证券账户", "电池ETF", "561910", "场内ETF", False, id="T9-etf-by-name"),
            pytest.param("证券账户", "上证50", "510050", "场内ETF", False, id="T9-etf-code-5xxx"),
            pytest.param("证券账户", "创业板ETF", "159915", "场内ETF", False, id="T9-etf-code-1xxx"),
            # T10: 股票
            pytest.param("证券账户", "长江电力", "600900", "场内股票", False, id="T10-stock-code-6xxx"),
            pytest.param("证券账户", "中兴通讯", "000063", "场内股票", False, id="T10-stock-code-0xxx"),
            pytest.param("证券账户", "宁德时代", "300750", "场内股票", False, id="T10-stock-code-3xxx"),
        ],
    )
    def test_single_holding(self, account, name, code, expected_cat, check_otc):
        """参数化单品分类测试：QDII / 场外 / ETF / 股票。"""
        h = Holding(account=account, name=name, code=code, shares=100, cost_price=1.0)
        cats = self._classify([h])
        assert len(cats[expected_cat]) == 1
        if check_otc:
            assert len(cats["国内场外"]) == 0

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
        assert len(cats["QDII"]) == 1
        assert len(cats["国内场外"]) == 1
        assert len(cats["场内ETF"]) == 1
        assert len(cats["场内股票"]) == 1

    def test_etf_precedes_stock(self):
        """ETF 判断优先于股票（代码 5xxx 但非 ETF 名称 → 仍归 ETF）。"""
        h = Holding(account="证券账户", name="某封闭基金", code="501025", shares=100, cost_price=1.0)
        cats = self._classify([h])
        assert len(cats["场内ETF"]) == 1
        assert len(cats["场内股票"]) == 0

    def test_default_to_otc(self):
        """无法识别的品种 → 默认归入国内场外。"""
        h = Holding(account="未知账户", name="某特殊产品", code="999999", shares=100, cost_price=1.0)
        cats = self._classify([h])
        assert len(cats["国内场外"]) == 1
        assert len(cats["场内股票"]) == 0
        assert len(cats["场内ETF"]) == 0
        assert len(cats["QDII"]) == 0

    def test_empty_holdings(self):
        """空持仓 → 所有分类为空列表。"""
        cats = self._classify([])
        for cat in ("场内股票", "场内ETF", "国内场外", "QDII"):
            assert len(cats[cat]) == 0


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
