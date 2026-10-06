"""配置管理模块单元测试 — 功能开关与访问器（config.py 分片）。

测试目标：
  - 组合进化 / 动作生成 / 数据沉降等板层开关访问器
  - comparison_candidates 候选比较访问器校验
  - 报告组开关（cost_lots 等）与报告节顺序模板 ↔ 注册表对齐

运行：
  pytest src/test/unit/config/test_config_feature_gates.py -v
"""

from __future__ import annotations
import json
import unittest
from src.python import config as cfg
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


class TestIsEnablePortfolioEvolution(unittest.TestCase):
    """is_enable_portfolio_evolution 访问器测试（组合演进章节开关）。"""

    def test_default_true_when_missing(self):
        """配置缺省 → 返回 True（默认启用）。"""
        self.assertTrue(cfg.is_enable_portfolio_evolution({}))
        self.assertTrue(cfg.is_enable_portfolio_evolution({"enable_fund_deep_analysis": False}))

    def test_false_when_disabled(self):
        """显式 false → 返回 False。"""
        self.assertFalse(cfg.is_enable_portfolio_evolution({"enable_portfolio_evolution": False}))

    def test_true_when_enabled(self):
        """显式 true → 返回 True。"""
        self.assertTrue(cfg.is_enable_portfolio_evolution({"enable_portfolio_evolution": True}))

    def test_independent_from_fund_deep_analysis(self):
        """组合演进开关独立于基金深度分析开关。"""
        self.assertTrue(cfg.is_enable_portfolio_evolution({"enable_fund_deep_analysis": False}))
        self.assertFalse(
            cfg.is_enable_portfolio_evolution({"enable_fund_deep_analysis": True, "enable_portfolio_evolution": False})
        )


class TestGetComparisonCandidates(unittest.TestCase):
    """get_comparison_candidates 候选代码列表访问器。"""

    def test_missing_returns_empty(self):
        """config 缺失 comparison_candidates → 空列表。"""
        self.assertEqual(cfg.get_comparison_candidates({}), [])

    def test_non_list_returns_empty(self):
        """comparison_candidates 非列表 → 空列表（安全降级）。"""
        self.assertEqual(cfg.get_comparison_candidates({"comparison_candidates": "000001"}), [])
        self.assertEqual(cfg.get_comparison_candidates({"comparison_candidates": None}), [])

    def test_strings_normalized(self):
        """字符串项剥空白返回。"""
        self.assertEqual(
            cfg.get_comparison_candidates({"comparison_candidates": [" 000001 ", "110022"]}),
            ["000001", "110022"],
        )

    def test_numeric_normalized_to_six_digit(self):
        """数值项归一化为 6 位代码（如 110022 → '110022'、1 → '000001'）。"""
        self.assertEqual(
            cfg.get_comparison_candidates({"comparison_candidates": [110022, 1]}),
            ["110022", "000001"],
        )

    def test_invalid_items_skipped(self):
        """非法项忽略。"""
        self.assertEqual(
            cfg.get_comparison_candidates({"comparison_candidates": ["000001", {"code": "x"}]}),
            ["000001"],
        )


class TestIsEnableAction(unittest.TestCase):
    """is_enable_action 访问器测试（行动建议独立章开关，默认开）。"""

    def test_default_true_when_missing(self):
        """config 缺失 enable_action → 返回 True（默认开）。"""
        self.assertTrue(cfg.is_enable_action({}))
        self.assertTrue(cfg.is_enable_action({"enable_fund_deep_analysis": True}))

    def test_default_config_says_enabled(self):
        """默认配置模板 enable_action=True（默认开启的事实来源）。"""
        self.assertTrue(cfg._config_defaults._DEFAULT_CONFIG["enable_action"])

    def test_false_when_disabled(self):
        """显式 false → 返回 False。"""
        self.assertFalse(cfg.is_enable_action({"enable_action": False}))

    def test_true_when_enabled(self):
        """显式 true → 返回 True。"""
        self.assertTrue(cfg.is_enable_action({"enable_action": True}))

    def test_independent_from_portfolio_evolution(self):
        """行动建议开关独立于组合演进开关。"""
        self.assertTrue(cfg.is_enable_action({"enable_portfolio_evolution": True}))
        self.assertTrue(cfg.is_enable_action({"enable_portfolio_evolution": False, "enable_action": True}))


class TestDatasinkFeatureGate:
    """DataSinking 数据底座门禁：配置位 + 凭据双条件（纯本地判定）。"""

    def test_enabled_flag_default_true_when_section_missing(self):
        from src.python.config import is_enable_datasink

        assert is_enable_datasink({}) is True
        assert is_enable_datasink({"datasink": {}}) is True
        assert is_enable_datasink({"datasink": {"enabled": True}}) is True
        assert is_enable_datasink({"datasink": {"enabled": False}}) is False

    def test_feature_ready_requires_enabled_and_credential(self, monkeypatch):
        import src.python.core.datasource_credential as cred
        from src.python.config import datasink_feature_ready

        monkeypatch.setattr(cred, "missing_credential", lambda _sid: None)
        assert datasink_feature_ready({"datasink": {"enabled": True}}) is True
        assert datasink_feature_ready({"datasink": {"enabled": False}}) is False

        monkeypatch.setattr(cred, "missing_credential", lambda _sid: object())
        assert datasink_feature_ready({"datasink": {"enabled": True}}) is False

    def test_default_config_has_enabled_true(self):
        from src.python.config._config_defaults import _DEFAULT_CONFIG

        assert _DEFAULT_CONFIG["datasink"]["enabled"] is True


class TestReportGroupSwitches:
    """报告章节与增强开关：功能开关注册表为唯一真源（GROUP_REPORT）。"""

    KEYS = (
        "data_quality",
        "industry_beta",
        "candidate_compare",
        "cost_lots",
        "valuation_percentile",
        "market_temperature",
        "financial_report_digest",
        "market_sentiment",
        "financial_indicator",
    )

    def test_known_report_keys_stay_in_group(self):
        """已知报告组开关不得静默移出分组（子集断言：新增报告开关不要求改本清单）。"""
        from src.python.config.features import GROUP_REPORT, switches_in_group

        flags = {flag for flag, _d in switches_in_group(GROUP_REPORT)}
        assert set(self.KEYS) <= flags

    def test_accessor_matches_registry_default(self):
        """注册表报告组**每个**开关都有访问器，且访问器取值 == 注册表默认值（缺键回落由注册表统一表达）。"""
        from src.python.config import _core
        from src.python.config.features import (
            GROUP_REPORT,
            feature_switch_registry,
            switches_in_group,
        )

        for flag, _d in switches_in_group(GROUP_REPORT):
            accessor = getattr(_core, f"is_enable_{flag}")
            assert accessor() is bool(feature_switch_registry[flag].default), flag

    def test_accessor_follows_runtime_override(self):
        """运行时覆盖（features.json / --feature）即时反映到访问器。"""
        from src.python.config import is_enable_financial_indicator
        from src.python.config.features import set_feature_enabled

        assert is_enable_financial_indicator() is False
        set_feature_enabled("financial_indicator", True)
        assert is_enable_financial_indicator() is True

    def test_config_json_no_longer_carries_report_submodules(self):
        from src.python.config import get_config

        assert "report_submodules" not in get_config()

    def test_config_argument_is_ignored(self):
        """config 形参仅为兼容签名保留，不再参与取值。"""
        from src.python.config import is_enable_market_temperature

        assert is_enable_market_temperature({}) is True
        assert is_enable_market_temperature({"report_submodules": {"market_temperature": False}}) is True


class TestReportSectionOrderTemplateMatchesRegistry:
    """配置模板的 report_section_order 与注册表出厂默认同序（章节合并后一致性锁定）。"""

    @pytest.mark.unit_config
    def test_template_section_order_matches_registry_defaults(self):
        """模板/默认配置的 report_section_order（若有）必须与注册表默认序号一致。"""
        import re

        from src.python.config import _config_defaults as d
        from src.python.core.registry import _REPORT_SECTION_DEFAULT, get_report_section_keys

        template = d._get_default_config_template()
        m = re.search(r'"report_section_order":\s*(\{.*?\})', template, re.S)
        assert m, "模板未包含 report_section_order"
        order = json.loads(m.group(1))
        if not order:  # 空 {} = 使用默认顺序，天然一致
            return
        defaults = {s["key"]: s["number"] for s in _REPORT_SECTION_DEFAULT}
        assert set(order) <= get_report_section_keys(), f"模板含未知模块: {set(order) - get_report_section_keys()}"
        for key, num in order.items():
            assert defaults[key] == num, f"{key} 模板序号 {num} != 注册表默认 {defaults[key]}"
