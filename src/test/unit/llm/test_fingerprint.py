"""LLM 缓存指纹模块单元测试。

测试目标：
  - _extract_stable_holdings — 稳定字段提取，剔除行情波动
  - _extract_stable_penetration — 穿透资产稳定字段/全量字段
  - _build_llm_fingerprint — 指纹构建（含 full_penetration 模式）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_fingerprint.py -v
"""

from __future__ import annotations

import unittest

from src.python.llm.fingerprint import (

    _build_llm_fingerprint,
    _compute_fingerprint,
    _extract_stable_holdings,
    _extract_stable_penetration,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]



class TestExtractStableHoldings(unittest.TestCase):
    """_extract_stable_holdings — 从持仓明细剔除行情波动字段。"""

    def test_empty_returns_empty_list(self):
        """None → []。"""
        self.assertEqual(_extract_stable_holdings(None), [])

    def test_empty_list_returns_empty(self):
        """[] → []。"""
        self.assertEqual(_extract_stable_holdings([]), [])

    def test_extracts_name_code_cost_only(self):
        """只保留 name/code/cost，忽略 price/market_value 等行情字段。"""
        details = [
            {"name": "茅台", "code": "600519", "cost": 1000,
             "price": 1500, "market_value": 150000, "profit": 50000},
        ]
        result = _extract_stable_holdings(details)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], {"name": "茅台", "code": "600519", "cost": 1000})

    def test_missing_fields_default_to_zero(self):
        """缺少的字段以 0 填充。"""
        details = [{"name": "test"}]
        result = _extract_stable_holdings(details)
        self.assertEqual(result[0], {"name": "test", "code": "", "cost": 0})

    def test_multiple_holdings(self):
        """多条持仓全部保留。"""
        details = [
            {"name": "A", "code": "000001", "cost": 100},
            {"name": "B", "code": "000002", "cost": 200},
        ]
        result = _extract_stable_holdings(details)
        self.assertEqual(len(result), 2)


class TestExtractStablePenetration(unittest.TestCase):
    """_extract_stable_penetration — 穿透资产字段提取。"""

    def test_empty_returns_empty_list(self):
        """None → []。"""
        self.assertEqual(_extract_stable_penetration(None), [])

    def test_default_mode_excludes_mv_sector(self):
        """默认模式（full=False）只保留 name/codes。"""
        assets = [
            {"name": "茅台", "codes": ["600519"], "mv": 100000, "sector": "白酒", "ratio": 15.0},
        ]
        result = _extract_stable_penetration(assets)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], {"name": "茅台", "codes": ["600519"]})

    def test_full_mode_includes_mv_sector_ratio(self):
        """full=True 时包含 mv/sector/ratio。"""
        assets = [
            {"name": "茅台", "codes": ["600519"], "mv": 100000, "sector": "白酒", "ratio": 15.0},
        ]
        result = _extract_stable_penetration(assets, full=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["mv"], 100000)
        self.assertEqual(result[0]["sector"], "白酒")
        self.assertEqual(result[0]["ratio"], 15.0)

    def test_missing_codes_field(self):
        """codes 缺失时兜底为空列表。"""
        assets = [{"name": "test"}]
        result = _extract_stable_penetration(assets)
        self.assertEqual(result[0]["codes"], [])

    def test_empty_assets_list(self):
        """[] → []。"""
        self.assertEqual(_extract_stable_penetration([]), [])


class TestBuildLlmFingerprint(unittest.TestCase):
    """_build_llm_fingerprint — 统一指纹构建。"""

    def test_fingerprint_is_deterministic(self):
        """相同输入 → 相同指纹。"""
        fp1 = _build_llm_fingerprint(
            total_mv=100000, total_cost=80000, total_profit=20000,
            holdings_details=[{"name": "A", "code": "000001", "cost": 100}],
        )
        fp2 = _build_llm_fingerprint(
            total_mv=100000, total_cost=80000, total_profit=20000,
            holdings_details=[{"name": "A", "code": "000001", "cost": 100}],
        )
        self.assertEqual(fp1, fp2)

    def test_different_input_different_fingerprint(self):
        """不同输入 → 不同指纹。"""
        fp1 = _build_llm_fingerprint(total_mv=100000)
        fp2 = _build_llm_fingerprint(total_mv=200000)
        self.assertNotEqual(fp1, fp2)

    def test_full_penetration_changes_fingerprint(self):
        """full_penetration=True 时穿透数据影响指纹。"""
        assets = [{"name": "茅台", "codes": ["600519"], "mv": 100000}]
        fp_normal = _build_llm_fingerprint(penetrated_assets=assets)
        fp_full = _build_llm_fingerprint(penetrated_assets=assets, full_penetration=True)
        self.assertNotEqual(fp_normal, fp_full)

    def test_holdings_details_excludes_price(self):
        """持仓明细中的价格波动不影响指纹（与 fn:extract_stable_holdings 一致）。"""
        hp = [{"name": "A", "code": "000001", "cost": 100, "price": 9999}]
        lp = [{"name": "A", "code": "000001", "cost": 100, "price": 1}]
        self.assertEqual(
            _build_llm_fingerprint(holdings_details=hp),
            _build_llm_fingerprint(holdings_details=lp),
        )

    def test_returns_12_char_hex(self):
        """返回 12 位十六进制字符串。"""
        fp = _build_llm_fingerprint(total_mv=50000)
        self.assertEqual(len(fp), 12)
        int(fp, 16)  # 合法十六进制

    def test_all_defaults_zero(self):
        """全默认参数不报错。"""
        fp = _build_llm_fingerprint()
        self.assertEqual(len(fp), 12)
