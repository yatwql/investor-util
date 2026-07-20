"""汇率敞口分析模块单元测试。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/test_fx_exposure.py -v
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class TestFxExposureNormal:
    """正常场景测试。"""

    def test_all_cny(self):
        """全人民币持仓返回 100% CNY。"""
        from src.python.analysis.fx_exposure import fx_exposure

        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 100_000},
            {"name": "招商银行", "code": "600036", "market_value": 50_000},
        ]
        result = fx_exposure(holdings)
        assert result["has_foreign"] is False
        assert len(result["exposures"]) == 1
        assert result["exposures"][0]["currency"] == "CNY"
        assert result["exposures"][0]["pct"] == 100.0

    def test_hkd_holdings(self):
        """港股通持仓识别为 HKD。"""
        from src.python.analysis.fx_exposure import fx_exposure

        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 100_000},
            {"name": "腾讯控股", "code": "00700", "market_value": 100_000},
        ]
        result = fx_exposure(holdings)
        assert result["has_foreign"] is True
        assert result["hkd_suffix"] != ""
        cny = next(e for e in result["exposures"] if e["currency"] == "CNY")
        hkd = next(e for e in result["exposures"] if e["currency"] == "HKD")
        assert cny["pct"] == 50.0
        assert hkd["pct"] == 50.0

    def test_usd_qdii(self):
        """QDII 基金识别为 USD。"""
        from src.python.analysis.fx_exposure import fx_exposure

        holdings = [
            {"name": "易方达纳斯达克100ETF联接", "code": "161130", "market_value": 80_000},
            {"name": "招商银行", "code": "600036", "market_value": 20_000},
        ]
        result = fx_exposure(holdings)
        assert result["has_foreign"] is True
        usd = next(e for e in result["exposures"] if e["currency"] == "USD")
        assert usd["pct"] == 80.0

    def test_mixed_currencies(self):
        """多币种混合持仓。"""
        from src.python.analysis.fx_exposure import fx_exposure

        holdings = [
            {"name": "沪深300ETF", "code": "510300", "market_value": 50_000},
            {"name": "腾讯控股", "code": "00700", "market_value": 30_000},
            {"name": "标普500ETF", "code": "513500", "market_value": 20_000},
        ]
        result = fx_exposure(holdings)
        assert len(result["exposures"]) == 3
        assert result["has_foreign"] is True

    def test_summary_format(self):
        """摘要格式化文本。"""
        from src.python.analysis.fx_exposure import fx_exposure

        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 70_000},
            {"name": "腾讯控股", "code": "00700", "market_value": 30_000},
        ]
        result = fx_exposure(holdings)
        assert "人民币" in result["summary"]
        assert "港币" in result["summary"]
        assert "70.0%" in result["summary"]
        assert "30.0%" in result["summary"]


class TestFxExposureEdge:
    """边缘场景测试。"""

    def test_empty_holdings(self):
        """空持仓列表返回空结果。"""
        from src.python.analysis.fx_exposure import fx_exposure

        result = fx_exposure([])
        assert result["exposures"] == []
        assert result["summary"] == ""
        assert result["has_foreign"] is False

    def test_none_holdings(self):
        """None 持仓返回空结果。"""
        from src.python.analysis.fx_exposure import fx_exposure

        result = fx_exposure(None)
        assert result["exposures"] == []
        assert result["summary"] == ""

    def test_zero_market_value(self):
        """市值为零的品种被跳过。"""
        from src.python.analysis.fx_exposure import fx_exposure

        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 0},
        ]
        result = fx_exposure(holdings)
        assert result["exposures"] == []
        assert result["total_mv"] == 0.0

    def test_single_holding(self):
        """单品种持仓。"""
        from src.python.analysis.fx_exposure import fx_exposure

        holdings = [
            {"name": "腾讯控股", "code": "00700", "market_value": 200_000},
        ]
        result = fx_exposure(holdings)
        assert len(result["exposures"]) == 1
        assert result["exposures"][0]["currency"] == "HKD"
        assert result["exposures"][0]["pct"] == 100.0
        assert result["has_foreign"] is True


class TestBuildFxExposureBlock:
    """_build_fx_exposure_block prompt 构建测试。"""

    def test_normal_block(self):
        """正常数据生成格式化块。"""
        from src.python.llm.prompts_tables import _build_fx_exposure_block

        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 70_000},
            {"name": "腾讯控股", "code": "00700", "market_value": 30_000},
        ]
        block = _build_fx_exposure_block(holdings)
        assert "【币种敞口分布】" in block
        assert "人民币" in block
        assert "港币" in block
        assert "非人民币资产合计占比" in block

    def test_empty_block(self):
        """空持仓返回空字符串。"""
        from src.python.llm.prompts_tables import _build_fx_exposure_block

        assert _build_fx_exposure_block([]) == ""
        assert _build_fx_exposure_block(None) == ""

    def test_no_foreign_block(self):
        """全人民币不显示非人民币风险提示。"""
        from src.python.llm.prompts_tables import _build_fx_exposure_block

        holdings = [
            {"name": "贵州茅台", "code": "600519", "market_value": 100_000},
        ]
        block = _build_fx_exposure_block(holdings)
        assert "非人民币资产合计占比" not in block
