"""流动性分析模块边缘场景测试 — 极端值/异常场景。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]

# mock 目标路径：liquidity.py 内部 from src.python.fetcher.chain import fetch_with_incremental_fallback
_MOCK_TARGET = "src.python.fetcher.chain.fetch_with_incremental_fallback"


def _extreme_market_value_bars() -> list[dict]:
    """极高市值品种：成交额巨大但相对持仓仍很小。"""
    return [
        {"date": f"2026-07-{d:02d}", "open": 100.0, "close": 102.0,
         "high": 105.0, "low": 99.0, "volume": 500_000}
        for d in range(1, 21)
    ]


def _low_liquidity_bars() -> list[dict]:
    """极低流动性品种：日均成交额不到市值的 0.1%。"""
    return [
        {"date": f"2026-07-{d:02d}", "open": 50.0, "close": 50.5,
         "high": 51.0, "low": 49.5, "volume": 100}
        for d in range(1, 21)
    ]


class TestLiquidityEdge:
    """流动性边缘场景。"""

    def test_large_position(self):
        """大持仓品种变现天数合理。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 200_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=_extreme_market_value_bars()):
            result = check_liquidity(holdings, 200_000_000)
        assert len(result) == 1
        r = result[0]
        assert r["type"] == "stock"
        assert r["liquidation_days"] > 3  # 日均成交额 ~51M，200M 需约 4 日
        assert "需约" in r["tag"]

    def test_extremely_low_liquidity(self):
        """极低流动性品种（日均成交额极低）。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600000", "name": "浦发银行", "market_value": 10_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=_low_liquidity_bars()):
            result = check_liquidity(holdings, 10_000_000)
        assert len(result) == 1
        r = result[0]
        assert r["type"] == "stock"
        assert r["liquidation_days"] > 100  # 日均成交额 ~5050，极度不流动
        assert "需约" in r["tag"]

    def test_kline_with_zero_volume(self):
        """K 线中全部成交量为零时返回 assumed_liquid。"""
        from src.python.analysis.liquidity import check_liquidity

        zero_volume_bars = [
            {"date": f"2026-07-{d:02d}", "open": 10.0, "close": 10.5,
             "high": 10.8, "low": 9.9, "volume": 0}
            for d in range(1, 21)
        ]
        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 10_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=zero_volume_bars):
            result = check_liquidity(holdings, 10_000_000)
        assert result[0]["type"] == "assumed_liquid"
