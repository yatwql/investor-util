"""流动性分析模块测试 — 场外品种赎回天数计算。

运行：
  pytest src/test/unit/analysis/test_liquidity_otc.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

# mock 目标路径：liquidity.py 内部 from src.python.fetcher.chain import fetch_with_incremental_fallback
_MOCK_TARGET = "src.python.fetcher.chain.fetch_with_incremental_fallback"


class TestLiquidityOTCConfig:
    """场外基金赎回上限配置场景。"""

    @staticmethod
    def _otc_data() -> list[dict]:
        return [
            {"code": "000001", "name": "华夏成长混合", "market_value": 1_000_000},
            {"code": "001111", "name": "华安优选混合", "market_value": 500_000},
        ]

    def test_configured_limit_computes_days(self):
        """配置单日赎回上限后正确计算赎回天数。"""
        from src.python.analysis.liquidity import check_liquidity

        limits = {"000001": 100_000}  # 100K/日
        result = check_liquidity(self._otc_data(), 1_500_000, redemption_limits=limits)
        assert len(result) == 2

        # 000001: 1,000,000 / 100,000 = 10 日
        r1 = next(r for r in result if r["code"] == "000001")
        assert r1["type"] == "otc"
        assert r1["liquidation_days"] == 10.0
        assert r1["daily_redemption_limit"] == 100_000
        assert "需约" in r1["tag"]

        # 001111: 未配置 → 需手动确认
        r2 = next(r for r in result if r["code"] == "001111")
        assert r2["type"] == "otc"
        assert r2["liquidation_days"] is None
        assert r2["tag"] == "需手动确认赎回上限"

    def test_all_configured_low_limit(self):
        """低赎回上限导致大量天数。"""
        from src.python.analysis.liquidity import check_liquidity

        limits = {"000001": 10_000, "001111": 10_000}  # 10K/日
        result = check_liquidity(self._otc_data(), 1_500_000, redemption_limits=limits)
        assert len(result) == 2
        for r in result:
            assert r["type"] == "otc"
            assert r["liquidation_days"] == 100 or r["liquidation_days"] == 50
            assert r["daily_redemption_limit"] == 10_000

    def test_all_configured_high_limit_same_day(self):
        """单日赎回上限足够高时标记当日可赎回。"""
        from src.python.analysis.liquidity import check_liquidity

        limits = {"000001": 2_000_000, "001111": 2_000_000}
        result = check_liquidity(self._otc_data(), 1_500_000, redemption_limits=limits)
        for r in result:
            assert r["type"] == "otc"
            assert r["liquidation_days"] < 1.0
            assert r["tag"] == "当日可赎回"

    def test_no_redemption_limits_default(self):
        """不传 redemption_limits 时标记需手动确认。"""
        from src.python.analysis.liquidity import check_liquidity

        result = check_liquidity(self._otc_data(), 1_500_000)
        for r in result:
            assert r["type"] == "otc"
            assert r["liquidation_days"] is None
            assert r["tag"] == "需手动确认赎回上限"

    def test_empty_limits_dict_same_as_none(self):
        """空字典限制等价于 None。"""
        from src.python.analysis.liquidity import check_liquidity

        result = check_liquidity(self._otc_data(), 1_500_000, redemption_limits={})
        for r in result:
            assert r["type"] == "otc"
            assert r["liquidation_days"] is None
            assert r["tag"] == "需手动确认赎回上限"

    def test_no_otc_no_limit_effect(self):
        """无 OTC 品种时 limits 不生效。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [
            {"code": "600519", "name": "贵州茅台", "market_value": 10_000_000},
        ]
        with patch(_MOCK_TARGET, return_value=[]):
            result = check_liquidity(holdings, 10_000_000, redemption_limits={"600519": 999_999})
        assert result[0]["type"] == "assumed_liquid"

    def test_zero_limit_ignored(self):
        """赎回上限为 0 时视为未配置。"""
        from src.python.analysis.liquidity import check_liquidity

        limits = {"000001": 0}
        result = check_liquidity(self._otc_data(), 1_500_000, redemption_limits=limits)
        r1 = next(r for r in result if r["code"] == "000001")
        assert r1["liquidation_days"] is None
        assert r1["tag"] == "需手动确认赎回上限"
