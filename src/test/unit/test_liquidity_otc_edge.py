"""流动性分析模块边缘场景测试 — 场外品种巨额赎回/极端值/异常场景。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.edge, pytest.mark.unit_providers]


class TestLiquidityOTCEdge:
    """场外流动性边缘场景。"""

    def test_large_otc_position_small_limit(self):
        """巨额场外仓位 + 小赎回上限 → 极多天数。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "000001", "name": "华夏成长混合", "market_value": 100_000_000},
        ]
        limits = {"000001": 10_000}  # 仅 1 万/日
        result = check_liquidity(holdings, 100_000_000, redemption_limits=limits)
        assert len(result) == 1
        r = result[0]
        assert r["type"] == "otc"
        assert r["liquidation_days"] > 10_000  # 需万余日
        assert "需约" in r["tag"]

    def test_multiple_otc_mixed_config(self):
        """多个 OTC 品种部分配置部分未配置。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "000001", "name": "华夏成长混合", "market_value": 1_000_000},
            {"code": "001111", "name": "华安优选混合", "market_value": 2_000_000},
            {"code": "002222", "name": "国泰金龙混合", "market_value": 500_000},
            {"code": "003333", "name": "南方绩优混合", "market_value": 3_000_000},
        ]
        limits = {"000001": 200_000, "003333": 50_000}  # 2 个配置，2 个未配
        result = check_liquidity(holdings, 6_500_000, redemption_limits=limits)
        assert len(result) == 4

        configured = [r for r in result if r["liquidation_days"] is not None]
        unconfigured = [r for r in result if r["liquidation_days"] is None]
        assert len(configured) == 2
        assert len(unconfigured) == 2
        for r in unconfigured:
            assert r["tag"] == "需手动确认赎回上限"

    def test_zero_market_value_with_limit(self):
        """零市值品种即使配置了上限也跳过。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "000001", "name": "华夏成长混合", "market_value": 0},
        ]
        limits = {"000001": 100_000}
        result = check_liquidity(holdings, 0, redemption_limits=limits)
        assert result == []
