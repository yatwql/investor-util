"""流动性分析模块单元测试 — 正常场景。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/test_liquidity.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

_MOCK_DAILY_BARS = [
    {"date": f"2026-07-{d:02d}", "open": 10.0, "close": 10.5, "high": 10.8, "low": 9.9, "volume": 1_000_000}
    for d in range(1, 21)
]
"""20 日 K 线 mock 数据：日成交额 ≈ 10.5 × 1,000,000 = 10,500,000 元/日。"""

# mock 目标路径：liquidity.py 内部 from src.python.fetcher.chain import fetch_with_incremental_fallback
_MOCK_TARGET = "src.python.fetcher.chain.fetch_with_incremental_fallback"


class TestLiquidityEmpty:
    """空输入场景。"""

    def test_empty_holdings_returns_empty(self):
        """空持仓列表返回空。"""
        from src.python.analysis.liquidity import check_liquidity

        assert check_liquidity([], 0) == []

    def test_none_holdings_returns_empty(self):
        """None 持仓返回空。"""
        from src.python.analysis.liquidity import check_liquidity

        assert check_liquidity(None, 0) == []


class TestLiquidityOTC:
    """场外基金场景。"""

    @staticmethod
    def _otc_holdings() -> list[dict]:
        return [
            {"code": "000001", "name": "华夏成长混合", "market_value": 500_000},
            {"code": "001111", "name": "华安优选混合", "market_value": 300_000},
        ]

    def test_all_otc_marked_as_otc(self):
        """全部场外基金标记为 otc。"""
        from src.python.analysis.liquidity import check_liquidity

        result = check_liquidity(self._otc_holdings(), 800_000)
        assert len(result) == 2
        for r in result:
            assert r["type"] == "otc"
            assert r["tag"] == "需手动确认赎回上限"
            assert r["liquidation_days"] is None

    def test_otc_no_kline_call(self):
        """场外基金不触发 K 线请求。"""
        from src.python.analysis.liquidity import check_liquidity

        with patch(_MOCK_TARGET) as mock_fetch:
            check_liquidity(self._otc_holdings(), 800_000)
            mock_fetch.assert_not_called()


class TestLiquidityStock:
    """场内品种场景。"""

    def test_stock_with_kline_computes_liquidation_days(self):
        """有 K 线数据的股票计算变现天数正确。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 10_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=_MOCK_DAILY_BARS):
            result = check_liquidity(holdings, 10_000_000)
        assert len(result) == 1
        r = result[0]
        assert r["type"] == "stock"
        assert r["avg_daily_turnover"] is not None
        assert r["avg_daily_turnover"] == 10_500_000.0  # 10.5 × 1,000,000
        assert r["liquidation_days"] == pytest.approx(0.95, rel=0.1)  # 10,000,000 / 10,500,000 ≈ 0.95
        assert r["tag"] == "当日可卖出"

    def test_stock_high_market_value_requires_multiple_days(self):
        """市值远大于日均成交额时需多日卖出。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 50_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=_MOCK_DAILY_BARS):
            result = check_liquidity(holdings, 50_000_000)
        assert len(result) == 1
        r = result[0]
        assert r["liquidation_days"] > 1
        assert r["tag"].startswith("需约")

    def test_stock_missing_kline_assumed_liquid(self):
        """K 线数据缺失时假设流动性充足。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 10_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=[]):
            result = check_liquidity(holdings, 10_000_000)
        assert len(result) == 1
        r = result[0]
        assert r["type"] == "assumed_liquid"
        assert r["tag"] == "流动性充足（数据缺失）"


class TestLiquidityMixed:
    """混合持仓场景。"""

    def test_mix_of_stock_and_otc(self):
        """同时含场内和场外品种时正确标记。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 10_000_000},
            {"code": "000001", "name": "华夏成长混合", "market_value": 500_000},
            {"code": "510050", "name": "上证50ETF", "market_value": 2_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=_MOCK_DAILY_BARS):
            result = check_liquidity(holdings, 12_500_000)
        type_map = {r["code"]: r["type"] for r in result}
        assert type_map["600519"] == "stock"
        assert type_map["000001"] == "otc"
        assert type_map["510050"] == "stock"

    def test_zero_market_value_skipped(self):
        """零市值品种跳过。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 0},
        ]
        result = check_liquidity(holdings, 0)
        assert result == []
