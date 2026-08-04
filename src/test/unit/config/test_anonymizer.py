"""配置匿名化模块单元测试 — 4 种模式与模式解析。

测试目标：
  - _resolve_mode：未知模式回退到 'off'
  - is_anonymization_enabled：模式启用判断
  - anonymize_holdings：off / code_display / full_anonymous / summary
  - anonymize_holdings_details：明细字典匿名化
  - _num_to_label：数字转字母标签
  - _blur_value：数值模糊化
  - _categorize_*：基金/股票分类
  - get/set_anonymization_mode：配置读写

运行：
  .venv/bin/python -m pytest src/test/unit/config/test_anonymizer.py -v
"""

from __future__ import annotations

import logging
import unittest
from unittest.mock import patch

import pytest

from src.python.config.anonymizer import (
    _blur_value,
    _categorize_detail,
    _categorize_holding,
    _num_to_label,
    _resolve_mode,
    ANONYMIZATION_MODE_DESCRIPTIONS,
    anonymize_holdings,
    anonymize_holdings_details,
    get_anonymization_mode,
    is_anonymization_enabled,
    set_anonymization_mode,
)
from src.python.core.models import Holding

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


def _mk_holdings() -> list[Holding]:
    """构造最小持仓（2 个不同代码 + 1 个重复代码）。"""
    return [
        Holding(account="测试账户", name="招商银行", code="600036", shares=1000, cost_price=10.0),
        Holding(account="测试账户", name="贵州茅台", code="600519", shares=200, cost_price=500.0),
        Holding(account="测试账户", name="招商银行A", code="600036", shares=500, cost_price=12.0),
    ]


def _mk_details() -> list[dict]:
    """构造最小持仓明细字典（含 market_value/cost/profit/profit_rate_pct）。"""
    return [
        {"name": "招商银行", "code": "600036", "market_value": 216400.0, "cost": 200000.0,
         "profit": 16400.0, "profit_rate_pct": 8.2, "account": "测试账户"},
        {"name": "贵州茅台", "code": "600519", "market_value": 345000.0, "cost": 300000.0,
         "profit": 45000.0, "profit_rate_pct": 15.0, "account": "测试账户"},
    ]


class TestResolveMode(unittest.TestCase):
    """_resolve_mode 模式解析。"""

    def test_known_modes_passed_through(self):
        """合法模式原样返回。"""
        for mode in ("off", "code_display", "full_anonymous", "summary"):
            self.assertEqual(_resolve_mode(mode), mode)

    def test_unknown_mode_falls_back_off(self):
        """未知模式回退 'off' 并告警。"""
        with self.assertLogs("invest", level="WARNING") as logs:
            self.assertEqual(_resolve_mode("bogus"), "off")
        self.assertTrue(any("bogus" in msg for msg in logs.output))

    def test_none_falls_back_off(self):
        """None 视为未知 → 回退 'off'。"""
        self.assertEqual(_resolve_mode(None), "off")


class TestIsAnonymizationEnabled(unittest.TestCase):
    """is_anonymization_enabled 启用判断。"""

    def test_off_disabled(self):
        """off → False。"""
        self.assertFalse(is_anonymization_enabled("off"))

    def test_code_display_enabled(self):
        """code_display → True。"""
        self.assertTrue(is_anonymization_enabled("code_display"))

    def test_full_anonymous_enabled(self):
        """full_anonymous → True。"""
        self.assertTrue(is_anonymization_enabled("full_anonymous"))

    def test_unknown_falls_back_off_disabled(self):
        """未知模式 → 回退 off → False。"""
        self.assertFalse(is_anonymization_enabled("unknown"))


class TestAnonymizeHoldings(unittest.TestCase):
    """anonymize_holdings 持仓列表匿名化。"""

    def test_off_returns_original(self):
        """off → 原列表（同一对象）。"""
        holdings = _mk_holdings()
        result = anonymize_holdings(holdings, "off")
        self.assertIs(result, holdings)
        self.assertEqual(result[0].name, "招商银行")

    def test_code_display_replaces_names_keeps_code(self):
        """code_display → 名称替换为'品种X'，保留代码与盈亏。"""
        result = anonymize_holdings(_mk_holdings(), "code_display")
        self.assertIsInstance(result, list)
        names = [h.name for h in result]
        # 同代码复用同一代号，不同代码递增
        self.assertEqual(names[0], names[2])  # 600036 两次 → 同代号
        self.assertNotEqual(names[0], names[1])  # 600036 vs 600519
        self.assertEqual(result[0].code, "600036")  # 代码保留
        self.assertEqual(result[0].shares, 1000)  # 份额保留

    def test_code_display_does_not_mutate_original(self):
        """code_display 返回深拷贝，不改动原持仓。"""
        holdings = _mk_holdings()
        anonymize_holdings(holdings, "code_display")
        self.assertEqual(holdings[0].name, "招商银行")

    def test_full_anonymous_masks_code_and_blurs_shares(self):
        """full_anonymous → 代码 '000XXX'，份额按百位取整。"""
        result = anonymize_holdings(_mk_holdings(), "full_anonymous")
        self.assertIsInstance(result, list)
        for h in result:
            self.assertEqual(h.code, "000XXX")
        # 1000 → 1000；200 → 200（round(2)*100=200）；500 → 500
        self.assertEqual(result[0].shares, 1000)
        self.assertEqual(result[1].shares, 200)
        # 小数份额按百位进位：55 → round(55/100)=round(0.55)=1 → 100
        small = [Holding(account="a", name="x", code="000001", shares=55, cost_price=10.0)]
        r = anonymize_holdings(small, "full_anonymous")
        self.assertEqual(r[0].shares, 100)

    def test_summary_aggregates_by_category(self):
        """summary → 按类别汇总字典。"""
        holdings = [Holding(account="a", name="招商银行", code="600036", shares=1000, cost_price=10.0)]
        result = anonymize_holdings(holdings, "summary")
        self.assertIsInstance(result, dict)
        self.assertIn("股票/其他", result)
        summary = result["股票/其他"]
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["shares"], 1000.0)
        self.assertEqual(summary["cost"], 10000.0)  # shares × cost_price = 1000 × 10.0

    def test_unknown_mode_falls_back_off(self):
        """未知模式 → 回退 off → 原样返回。"""
        holdings = _mk_holdings()
        with self.assertLogs("invest", level="WARNING"):
            result = anonymize_holdings(holdings, "not_a_mode")
        self.assertIs(result, holdings)


class TestAnonymizeHoldingsDetails(unittest.TestCase):
    """anonymize_holdings_details 明细字典匿名化。"""

    def test_off_returns_original(self):
        """off → 原列表。"""
        details = _mk_details()
        result = anonymize_holdings_details(details, "off")
        self.assertIs(result, details)

    def test_code_display_replaces_names(self):
        """code_display → 名称替换，代码/数值保留。"""
        result = anonymize_holdings_details(_mk_details(), "code_display")
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["code"], "600036")
        self.assertEqual(result[0]["market_value"], 216400.0)
        self.assertEqual(result[0]["name"], "品种A")
        self.assertEqual(result[1]["name"], "品种B")

    def test_full_anonymous_masks_value(self):
        """full_anonymous → 代码掩码 + 金额模糊 + 盈亏文本。"""
        result = anonymize_holdings_details(_mk_details(), "full_anonymous")
        self.assertIsInstance(result, list)
        entry = result[0]
        self.assertEqual(entry["code"], "000XXX")
        self.assertEqual(entry["market_value"], 216000.0)  # round(216400/1000)*1000
        self.assertEqual(entry["cost"], 200000.0)  # round(200000/1000)*1000
        self.assertIsInstance(entry["profit"], str)
        self.assertIn("%", entry["profit"])

    def test_full_anonymous_zero_profit(self):
        """full_anonymous + profit=0 → 盈亏文本 '±0.0%'。"""
        d = {"name": "招商银行", "code": "600036", "market_value": 216400.0, "cost": 216400.0,
             "profit": 0, "profit_rate_pct": 0.0, "account": "测试账户"}
        result = anonymize_holdings_details([d], "full_anonymous")
        self.assertEqual(result[0]["profit"], "±0.0%")

    def test_summary_aggregates_details(self):
        """summary → 含 market_value/cost/profit 汇总。"""
        result = anonymize_holdings_details(_mk_details(), "summary")
        self.assertIsInstance(result, dict)
        cat = "股票/其他"
        self.assertIn(cat, result)
        data = result[cat]
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["market_value"], 561400.0)  # 216400 + 345000
        self.assertEqual(data["profit"], 61400.0)  # 16400 + 45000


class TestNumToLabel(unittest.TestCase):
    """_num_to_label 数字转字母。"""

    def test_single_letter(self):
        """1→A, 2→B, ..., 26→Z。"""
        self.assertEqual(_num_to_label(1), "A")
        self.assertEqual(_num_to_label(2), "B")
        self.assertEqual(_num_to_label(26), "Z")

    def test_multi_letter(self):
        """27→AA, 28→AB。"""
        self.assertEqual(_num_to_label(27), "AA")
        self.assertEqual(_num_to_label(28), "AB")

    def test_zero_returns_A(self):
        """0 → 'A'（兜底）。"""
        self.assertEqual(_num_to_label(0), "A")


class TestBlurValue(unittest.TestCase):
    """_blur_value 数值模糊化。"""

    def test_zero_returns_zero(self):
        """0 → 0.0。"""
        self.assertEqual(_blur_value(0), 0.0)

    def test_rounds_to_thousand(self):
        """默认精度 1000。"""
        self.assertEqual(_blur_value(216400), 216000.0)
        self.assertEqual(_blur_value(216600), 217000.0)

    def test_custom_precision(self):
        """自定义精度。"""
        self.assertEqual(_blur_value(55, precision=100), 100.0)


class TestCategorize(unittest.TestCase):
    """_categorize_holding / _categorize_detail 分类。"""

    def test_stock_categorized_stock(self):
        """A 股代码（600 开头，名称不含 ETF，非场外账户）→ 股票/其他。"""
        h = Holding(account="账户A", name="招商银行", code="600036", shares=1000, cost_price=10.0)
        self.assertEqual(_categorize_holding(h), "股票/其他")
        self.assertEqual(_categorize_detail({"name": "招商银行", "code": "600036", "account": "账户A"}), "股票/其他")

    def test_fund_categorized_fund(self):
        """场外基金（00 前缀 + 名称含基金特征词）→ 基金。"""
        h = Holding(account="账户A", name="易方达蓝筹精选混合", code="005827", shares=1000, cost_price=1.0)
        self.assertEqual(_categorize_holding(h), "基金")
        self.assertEqual(_categorize_detail({"name": "易方达蓝筹精选混合", "code": "005827", "account": "账户A"}), "基金")

    def test_import_error_falls_back_to_prefix(self):
        """code_utils 导入失败 → 按代码前缀粗略分类。"""
        with patch.dict("sys.modules", {"src.python.core.code_utils": None}):
            stock = Holding(account="账户A", name="招商银行", code="600036", shares=1000, cost_price=10.0)
            self.assertEqual(_categorize_holding(stock), "股票/其他")
            fund = Holding(account="账户A", name="某指数基金", code="161725", shares=1000, cost_price=1.0)
            self.assertEqual(_categorize_holding(fund), "基金")
            self.assertEqual(_categorize_detail({"name": "招商银行", "code": "600036", "account": "账户A"}), "股票/其他")
            self.assertEqual(_categorize_detail({"name": "某指数基金", "code": "161725", "account": "账户A"}), "基金")


class TestGetSetMode(unittest.TestCase):
    """get/set_anonymization_mode 配置读写。"""

    # 注意：get/set_anonymization_mode 内部是 `from src.python.config import get_config`，
    # 故 patch 目标是 src.python.config 模块命名空间，而非 anonymizer 模块属性。

    @patch("src.python.config.get_config")
    def test_get_default_off(self, mock_get):
        """无配置 → 默认 off。"""
        mock_get.return_value = {}
        self.assertEqual(get_anonymization_mode(), "off")

    @patch("src.python.config.get_config")
    def test_get_reads_mode(self, mock_get):
        """读取配置中的模式。"""
        mock_get.return_value = {"anonymization": {"mode": "code_display"}}
        self.assertEqual(get_anonymization_mode(), "code_display")

    @patch("src.python.config.get_config")
    def test_get_invalid_mode_warns_off(self, mock_get):
        """配置中模式无效 → 回退 off + 告警。"""
        mock_get.return_value = {"anonymization": {"mode": "invalid"}}
        with self.assertLogs("invest", level="WARNING"):
            self.assertEqual(get_anonymization_mode(), "off")

    @patch("src.python.config.get_config")
    @patch("src.python.config.set_config")
    def test_set_valid_mode_persists(self, mock_set, mock_get):
        """合法模式写入配置。"""
        mock_get.return_value = {"anonymization": {"mode": "off"}}
        set_anonymization_mode("full_anonymous")
        mock_set.assert_called_once()
        args = mock_set.call_args[0]
        self.assertEqual(args[0], "anonymization")
        self.assertEqual(args[1], {"mode": "full_anonymous"})

    @patch("src.python.config.get_config")
    @patch("src.python.config.set_config")
    def test_set_invalid_mode_raises(self, mock_get, mock_set):
        """非法模式抛 ValueError，不写入。"""
        mock_get.return_value = {"anonymization": {"mode": "off"}}
        with self.assertRaises(ValueError):
            set_anonymization_mode("bogus")
        mock_set.assert_not_called()


class TestModeDescriptions(unittest.TestCase):
    """ANONYMIZATION_MODE_DESCRIPTIONS 完整性。"""

    def test_all_modes_described(self):
        """4 种模式均有描述。"""
        self.assertEqual(set(ANONYMIZATION_MODE_DESCRIPTIONS.keys()), {"off", "code_display", "full_anonymous", "summary"})
        for desc in ANONYMIZATION_MODE_DESCRIPTIONS.values():
            self.assertTrue(desc)


if __name__ == "__main__":
    unittest.main()
