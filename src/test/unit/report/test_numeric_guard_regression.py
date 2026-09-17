"""数值归一回归测试 —— 报告层不得让 NaN/±inf 进入市值与盈亏。

缺陷背景：``price = mkt.get("price", 0.0) or 0.0`` 看似兜底，实际对 NaN 无效
（NaN 为真值），脏价格会直入市值/盈亏/溢价全链；昨收为 NaN 时更会把「全天涨幅」
算成 ``price × shares``，凭空造出当日盈亏。
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from src.python.core.models import Holding
from src.python.report.market_value import _compute_detail_row

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _row(price, yclose, *, shares=100, cost=10.0, source_api="tencent"):
    h = Holding("证券", "测试资产", "000001", shares, cost)
    mkt = {
        "price": price,
        "yesterday_close": yclose,
        "price_date": "2026-07-01",
        "source": "腾讯财经",
        "source_api": source_api,
    }
    with (
        patch("src.python.report.market_value.get_last_trading_day", return_value="2026-07-01"),
        patch("src.python.report.market_value.is_market_open", return_value=False),
    ):
        return _compute_detail_row(h, mkt)


@pytest.mark.unit
@pytest.mark.unit_report
class TestNanPriceDoesNotPolluteMarketValue:
    """NaN 价格 → 市值/盈亏全链不产 NaN。"""

    def test_nan_price_yields_finite_market_value(self):
        detail = _row(float("nan"), 10.0)
        assert math.isfinite(detail.market_value)
        assert detail.market_value == 0.0

    def test_nan_price_yields_finite_profit(self):
        detail = _row(float("nan"), 10.0)
        assert math.isfinite(detail.profit)
        assert detail.profit == -1000.0  # 0 市值 - 100×10 成本

    def test_nan_price_yields_finite_today_profit(self):
        detail = _row(float("nan"), 10.0)
        assert math.isfinite(detail.today_profit)

    def test_positive_inf_price_yields_finite_market_value(self):
        """+inf 是有限性之外的漏网路径（原 ``or 0.0`` 同样拦不住）。"""
        detail = _row(float("inf"), 10.0)
        assert math.isfinite(detail.market_value)
        assert detail.market_value == 0.0


@pytest.mark.unit
@pytest.mark.unit_report
class TestNanYesterdayCloseDoesNotFabricateProfit:
    """昨日收盘 NaN → 当日盈亏记「未知」而非凭空造出 price×shares。"""

    def test_nan_yclose_gives_zero_today_profit(self):
        detail = _row(10.0, float("nan"))
        assert detail.today_profit == 0.0, "昨收未知时不得把全天涨幅算成 price×shares"

    def test_inf_yclose_gives_zero_today_profit(self):
        detail = _row(10.0, float("inf"))
        assert detail.today_profit == 0.0

    def test_missing_yclose_gives_zero_today_profit(self):
        h = Holding("证券", "测试资产", "000001", 100, 10.0)
        mkt = {"price": 10.0, "price_date": "2026-07-01", "source": "腾讯财经", "source_api": "tencent"}
        with (
            patch("src.python.report.market_value.get_last_trading_day", return_value="2026-07-01"),
            patch("src.python.report.market_value.is_market_open", return_value=False),
        ):
            detail = _compute_detail_row(h, mkt)
        assert detail.today_profit == 0.0

    def test_legitimate_yclose_still_computed(self):
        """合法昨收行为逐字不变（不变量）。"""
        detail = _row(11.0, 10.0)
        assert detail.today_profit == 100.0

    def test_finite_negative_yclose_still_computed(self):
        """负的**有限**昨收属既有容忍口径，不在本次修复范围。"""
        detail = _row(5.0, -5.0)
        assert detail.today_profit == 1000.0
