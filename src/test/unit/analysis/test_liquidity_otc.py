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

        # 001111: 未配置 → 类型默认档（混合基金 T+3，非实测）
        r2 = next(r for r in result if r["code"] == "001111")
        assert r2["type"] == "otc"
        assert r2["liquidation_days"] == 3.0
        assert r2["estimate_basis"] == "type_default"
        assert "类型默认档" in r2["tag"] and "非实测" in r2["tag"]

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
        """不传 redemption_limits 时按类型默认档估算（混合基金 T+3，标非实测）。"""
        from src.python.analysis.liquidity import check_liquidity

        result = check_liquidity(self._otc_data(), 1_500_000)
        for r in result:
            assert r["type"] == "otc"
            assert r["liquidation_days"] == 3.0
            assert r["estimate_basis"] == "type_default"
            assert "非实测" in r["tag"]

    def test_empty_limits_dict_same_as_none(self):
        """空字典限制等价于 None（同样走类型默认档）。"""
        from src.python.analysis.liquidity import check_liquidity

        result = check_liquidity(self._otc_data(), 1_500_000, redemption_limits={})
        for r in result:
            assert r["type"] == "otc"
            assert r["liquidation_days"] == 3.0
            assert r["estimate_basis"] == "type_default"

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
        """赎回上限为 0 时视为未配置（落类型默认档）。"""
        from src.python.analysis.liquidity import check_liquidity

        limits = {"000001": 0}
        result = check_liquidity(self._otc_data(), 1_500_000, redemption_limits=limits)
        r1 = next(r for r in result if r["code"] == "000001")
        assert r1["liquidation_days"] == 3.0
        assert r1["estimate_basis"] == "type_default"


class TestLiquidityOtcTypeDefaultTier:
    """场外基金赎回天数类型默认档（非实测口径）。"""

    def test_money_fund_t1(self):
        """货币基金 → T+1。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [{"code": "000198", "name": "天弘余额宝货币", "market_value": 100_000}]
        result = check_liquidity(holdings, 100_000)
        assert result[0]["liquidation_days"] == 1.0
        assert result[0]["estimate_basis"] == "type_default"

    def test_short_bond_t1(self):
        """短债基金 → T+1（先于纯债档命中）。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [{"code": "000012", "name": "某某短债债券A", "market_value": 100_000}]
        result = check_liquidity(holdings, 100_000)
        assert result[0]["liquidation_days"] == 1.0

    def test_pure_bond_t2(self):
        """纯债基金 → T+2。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [{"code": "000013", "name": "某某纯债债券A", "market_value": 100_000}]
        result = check_liquidity(holdings, 100_000)
        assert result[0]["liquidation_days"] == 2.0

    def test_qdii_t7(self):
        """QDII 基金 → T+7（保守上沿）。"""
        from src.python.analysis.liquidity import check_liquidity

        holdings = [{"code": "000041", "name": "某某纳斯达克100指数QDII", "market_value": 100_000}]
        result = check_liquidity(holdings, 100_000)
        assert result[0]["liquidation_days"] == 7.0
        assert "非实测" in result[0]["tag"]
