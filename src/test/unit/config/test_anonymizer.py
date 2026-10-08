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
    build_code_display_map,
    build_report_alias_map,
    fold_details_summary,
    get_anonymization_mode,
    is_anonymization_enabled,
    is_code_masked_mode,
    mask_code_text,
    mask_display_text,
    mask_holding_code,
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
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 216400.0,
            "cost": 200000.0,
            "profit": 16400.0,
            "profit_rate_pct": 8.2,
            "account": "测试账户",
        },
        {
            "name": "贵州茅台",
            "code": "600519",
            "market_value": 345000.0,
            "cost": 300000.0,
            "profit": 45000.0,
            "profit_rate_pct": 15.0,
            "account": "测试账户",
        },
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

    def test_full_anonymous_blurs_values_and_keeps_code(self):
        """full_anonymous → 代码保留（键控链路）+ 金额千位模糊 + 盈亏数值派生。"""
        result = anonymize_holdings_details(_mk_details(), "full_anonymous")
        self.assertIsInstance(result, list)
        entry = result[0]
        # 代码保留真值：再平衡静默/决策账本/申购状态等键控链路不跨品种碰撞；
        # 「000XXX」显示由明细渲染层与产物清扫兑底
        self.assertEqual(entry["code"], "600036")
        self.assertEqual(entry["market_value"], 216000.0)  # round(216400/1000)*1000
        self.assertEqual(entry["cost"], 200000.0)  # round(200000/1000)*1000
        # 盈亏保持数值型且行内恒等（盈亏 = 市值 − 成本），下游合计/格式化不崩
        self.assertIsInstance(entry["profit"], float)
        self.assertEqual(entry["profit"], 16000.0)
        # 收益率由模糊值派生（百分比契约），不残留模糊前精度
        self.assertEqual(entry["profit_rate"], 8.0)
        self.assertEqual(entry["profit_rate_pct"], 8.0)

    def test_full_anonymous_zero_profit(self):
        """full_anonymous + 盈亏为 0 → 派生盈亏/收益率为数值 0。"""
        d = {
            "name": "招商银行",
            "code": "600036",
            "market_value": 216400.0,
            "cost": 216400.0,
            "profit": 0,
            "profit_rate_pct": 0.0,
            "account": "测试账户",
        }
        result = anonymize_holdings_details([d], "full_anonymous")
        self.assertEqual(result[0]["profit"], 0.0)
        self.assertEqual(result[0]["profit_rate"], 0.0)

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
        self.assertEqual(
            _categorize_detail({"name": "易方达蓝筹精选混合", "code": "005827", "account": "账户A"}), "基金"
        )

    def test_delegates_to_central_judgment(self):
        """分类结果无条件跟随 `code_utils.is_fund_holding`（不自建前缀回退）。

        分类只认中心判定，不另立前缀回退表——两套判定并存必然漂移，故此处
        无内联回退。以「中心判定说基金、代码前缀暗示股票」的持仓验证分类确实
        听中心判定：mock 直接改写中心函数返回值即可翻转结论。
        """
        from src.python.config import anonymizer

        stock = Holding(account="账户A", name="招商银行", code="600036", shares=1000, cost_price=10.0)
        with patch.object(anonymizer, "is_fund_holding", return_value=True):
            self.assertEqual(_categorize_holding(stock), "基金")
        with patch.object(anonymizer, "is_fund_holding", return_value=False):
            self.assertEqual(_categorize_holding(stock), "股票/其他")
            self.assertEqual(
                _categorize_detail({"name": "招商银行", "code": "600036", "account": "账户A"}), "股票/其他"
            )

    def test_beijing_exchange_stock_not_misclassified_as_fund(self):
        """北交所（8 开头）股票 → 股票/其他（不自建前缀判断）。"""
        h = Holding(account="账户A", name="某北交所股票", code="830799", shares=1000, cost_price=10.0)
        self.assertEqual(_categorize_holding(h), "股票/其他")
        self.assertEqual(
            _categorize_detail({"name": "某北交所股票", "code": "830799", "account": "账户A"}), "股票/其他"
        )


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


class TestReportAliasMaskFold(unittest.TestCase):
    """build_report_alias_map / mask_display_text / fold_details_summary（报告管线接入面）。"""

    def test_off_mode_yields_empty_map(self):
        """off → 空映射（清扫/掩码恒等）。"""
        self.assertEqual(build_report_alias_map(_mk_details(), "off"), {})

    def test_alias_numbering_matches_details_anonymization(self):
        """映射编号与 anonymize_holdings_details 的 code 首次见序一致（代号同源）。"""
        details = _mk_details()
        mapping = build_report_alias_map(details, "code_display")
        anon = anonymize_holdings_details([dict(d) for d in details], "code_display")
        for src, out in zip(details, anon, strict=True):
            self.assertEqual(mapping[src["name"]], out["name"])
        self.assertEqual(mapping["招商银行"], "品种A")
        self.assertEqual(mapping["贵州茅台"], "品种B")
        # code_display 不映射代码
        self.assertNotIn("600036", mapping)

    def test_full_map_includes_codes(self):
        """full → 映射含真码 → 000XXX。"""
        mapping = build_report_alias_map(_mk_details(), "full_anonymous")
        self.assertEqual(mapping["600036"], "000XXX")
        self.assertEqual(mapping["招商银行"], "品种A")

    def test_mask_display_text_long_key_first(self):
        """长键优先替换；空映射恒等。"""
        mapping = {"招商银行": "品种A", "600036": "000XXX"}
        text = "招商银行(600036) 限购 100 份"
        self.assertEqual(mask_display_text(text, mapping), "品种A(000XXX) 限购 100 份")
        self.assertEqual(mask_display_text(text, {}), text)

    def test_fold_details_summary_rows_schema(self):
        """折叠行保持明细 dict 同构键 + 大类聚合值。"""
        rows = fold_details_summary(_mk_details())
        self.assertEqual(len(rows), 1)  # 两条均股票/其他
        row = rows[0]
        self.assertEqual(row["name"], "股票汇总")
        self.assertEqual(row["market_value"], 561400.0)
        self.assertEqual(row["cost"], 500000.0)
        self.assertEqual(row["profit"], 61400.0)
        self.assertEqual(row["code"], "")
        # 同构键：下游渲染/小计/LLM 零改动消费
        for key in ("profit_rate", "shares", "change_pct", "nav_date", "source_api", "price", "channel"):
            self.assertIn(key, row)
        self.assertEqual(row["profit_rate"], 12.28)  # 61400/500000*100

    def test_fold_keeps_first_seen_order_and_fund_label(self):
        """类别按首见序；含基金时生成「基金汇总」行。"""
        details = _mk_details() + [
            {
                "name": "沪深300ETF",
                "code": "510300",
                "market_value": 10000.0,
                "cost": 9000.0,
                "profit": 1000.0,
                "profit_rate_pct": 11.1,
                "account": "测试账户",
            }
        ]
        rows = fold_details_summary(details)
        labels = [r["name"] for r in rows]
        self.assertEqual(labels[0], "股票汇总")
        self.assertIn("基金汇总", labels)


class TestCodeDisplayMaskFold(unittest.TestCase):
    """build_code_display_map / mask_holding_code / mask_code_text（代码面渲染点掩码）。"""

    def test_code_map_covers_only_code_masking_modes(self):
        """full/summary → {真码: 掩码}；code_display/off → 空（契约保留真码）。"""
        details = _mk_details()
        expected = {"600036": "000XXX", "600519": "000XXX"}
        self.assertEqual(build_code_display_map(details, "full_anonymous"), expected)
        self.assertEqual(build_code_display_map(details, "summary"), expected)
        self.assertEqual(build_code_display_map(details, "code_display"), {})
        self.assertEqual(build_code_display_map(details, "off"), {})

    def test_code_map_excludes_non_holding_codes(self):
        """映射只含实际持仓代码——指数/基准代码天然不在其中、不会被误掩。"""
        mapping = build_code_display_map(_mk_details(), "full_anonymous")
        self.assertNotIn("000300", mapping)
        self.assertNotIn("510300", mapping)

    def test_alias_map_exclude_codes_is_names_only(self):
        """include_codes=False → 仅名称（HTML 自由文本清扫用，杜绝数字替换金额）。"""
        details = _mk_details()
        names_only = build_report_alias_map(details, "full_anonymous", include_codes=False)
        self.assertEqual(names_only["招商银行"], "品种A")
        self.assertNotIn("600036", names_only)
        self.assertNotIn("600519", names_only)
        # 默认仍含代码（Excel 字符串单元格清扫等键控面行为不变）
        self.assertIn("600036", build_report_alias_map(details, "full_anonymous"))

    def test_mask_holding_code_per_mode(self):
        """full/summary → 掩码；code_display/off → 原样；空值原样返回。"""
        self.assertEqual(mask_holding_code("600036", "full_anonymous"), "000XXX")
        self.assertEqual(mask_holding_code("600036", "summary"), "000XXX")
        self.assertEqual(mask_holding_code("600036", "code_display"), "600036")
        self.assertEqual(mask_holding_code("600036", "off"), "600036")
        self.assertEqual(mask_holding_code("", "full_anonymous"), "")

    def test_is_code_masked_mode(self):
        """is_code_masked_mode：full/summary → True；off/code_display/None → False。"""
        self.assertTrue(is_code_masked_mode("full_anonymous"))
        self.assertTrue(is_code_masked_mode("summary"))
        self.assertFalse(is_code_masked_mode("off"))
        self.assertFalse(is_code_masked_mode("code_display"))
        self.assertFalse(is_code_masked_mode(None))

    def test_mask_code_text_replaces_standalone_tokens(self):
        """独立代码 token（HTML 单元格 / JSON 字符串 / 枚举列表）→ 折叠。"""
        mapping = {"600036": "000XXX"}
        self.assertEqual(mask_code_text("<td>600036</td>", mapping), "<td>000XXX</td>")
        self.assertEqual(mask_code_text('{"code":"600036"}', mapping), '{"code":"000XXX"}')
        self.assertEqual(mask_code_text("600036、999999", mapping), "000XXX、999999")
        both = {"600036": "000XXX", "600519": "000XXX"}
        self.assertEqual(mask_code_text("600036,600519", both), "000XXX,000XXX")

    def test_mask_code_text_skips_numeric_substrings(self):
        """金额 / JSON 数值 / 相邻数字中的同数字片段不被替换（数字子串误伤防护）。"""
        mapping = {"600036": "000XXX"}
        for text in ("金额 1600036.00", "600036.0", '{"mv":600036}', "12.600036%", "06000360", "1,600,036.00"):
            self.assertEqual(mask_code_text(text, mapping), text, text)

    def test_mask_code_text_empty_inputs_identity(self):
        """None / 空文本 / 空映射 → 恒等。"""
        self.assertIsNone(mask_code_text(None, {"600036": "000XXX"}))
        self.assertEqual(mask_code_text("", {"600036": "000XXX"}), "")
        self.assertEqual(mask_code_text("600036", None), "600036")
        self.assertEqual(mask_code_text("600036", {}), "600036")


class TestModeDescriptions(unittest.TestCase):
    """ANONYMIZATION_MODE_DESCRIPTIONS 完整性。"""

    def test_all_modes_described(self):
        """4 种模式均有描述。"""
        self.assertEqual(
            set(ANONYMIZATION_MODE_DESCRIPTIONS.keys()), {"off", "code_display", "full_anonymous", "summary"}
        )
        for desc in ANONYMIZATION_MODE_DESCRIPTIONS.values():
            self.assertTrue(desc)


if __name__ == "__main__":
    unittest.main()
