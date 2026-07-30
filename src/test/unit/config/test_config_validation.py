"""配置校验模块单元测试 — _validation.py 专用测试集。

测试目标：
  - _validation 模块可正确导入
  - 常量定义正确
  - _absolutize_paths 路径绝对化
  - _is_abs 路径判断
  - 所有 _validate_* 函数独立正确运行
  - validate_config 入口函数端到端

运行：
  python -m pytest src/test/unit/config/test_config_validation.py -v
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import pytest

from src.python.config import _validation as val
from src.python.core.constants import PROJECT_ROOT

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


class TestValidationModuleImport(unittest.TestCase):
    """验证 _validation 模块导入正确。"""

    def test_module_imported(self):
        """_validation 模块可导入。"""
        import src.python.config._validation as _v
        self.assertIsNotNone(_v)

    def test_constants_accessible(self):
        """模块常量可访问。"""
        self.assertIsInstance(val._KNOWN_NEWS_SOURCES, set)
        self.assertIsInstance(val._KNOWN_PROVIDER_TYPES, set)
        self.assertIsInstance(val._KNOWN_PROVIDER_NAMES, set)
        self.assertIsInstance(val._STRING_CONFIG_KEYS, set)
        self.assertIsInstance(val._PATH_CONFIG_KEYS, set)

    def test_known_providers_content(self):
        """已知 provider 名称包含核心值。"""
        self.assertIn("tencent", val._KNOWN_PROVIDER_NAMES)
        self.assertIn("eastmoney", val._KNOWN_PROVIDER_NAMES)
        self.assertIn("tiantian", val._KNOWN_PROVIDER_NAMES)

    def test_known_news_sources_content(self):
        """已知新闻源包含核心值。"""
        self.assertIn("sina", val._KNOWN_NEWS_SOURCES)
        self.assertIn("eastmoney", val._KNOWN_NEWS_SOURCES)


class TestIsAbs(unittest.TestCase):
    """_is_abs 路径判断测试。"""

    def test_unix_abs_path(self):
        """Unix 绝对路径识别。"""
        self.assertTrue(val._is_abs("/home/user/file"))
        self.assertTrue(val._is_abs("/"))

    def test_backslash_prefix_abs(self):
        """反斜杠开头的路径视为绝对路径。"""
        self.assertTrue(val._is_abs("\\server\\share"))
        self.assertTrue(val._is_abs("\\"))

    def test_relative_path(self):
        """相对路径返回 False。"""
        self.assertFalse(val._is_abs("data/holdings"))
        self.assertFalse(val._is_abs("./data"))
        self.assertFalse(val._is_abs(""))


class TestAbsolutizePaths(unittest.TestCase):
    """_absolutize_paths 路径绝对化测试。"""

    def test_relative_becomes_absolute(self):
        """相对路径拼接 PROJECT_ROOT。"""
        config = {"holdings_dir": "data/holdings"}
        result = val._absolutize_paths(config)
        expected = os.path.join(PROJECT_ROOT, "data/holdings")
        self.assertEqual(result["holdings_dir"], expected)

    def test_absolute_path_unchanged(self):
        """已是绝对路径的不变。"""
        config = {"holdings_dir": "/tmp/custom_holdings"}
        result = val._absolutize_paths(config)
        self.assertEqual(result["holdings_dir"], "/tmp/custom_holdings")

    def test_only_path_keys_affected(self):
        """非路径键不受影响。"""
        config = {"holdings_dir": "data", "news_top_count": 100}
        result = val._absolutize_paths(config)
        self.assertEqual(result["news_top_count"], 100)

    def test_holdings_filename_not_absolutized(self):
        """纯文件名键不受影响。"""
        config = {"holdings_filename": "持仓.xlsx"}
        result = val._absolutize_paths(config)
        self.assertEqual(result["holdings_filename"], "持仓.xlsx")

    def test_none_value_skipped(self):
        """None 值跳过。"""
        config = {"holdings_dir": None}
        result = val._absolutize_paths(config)
        self.assertIsNone(result.get("holdings_dir"))


class TestSection(unittest.TestCase):
    """_section 辅助函数测试。"""

    def test_present_and_valid_type(self):
        """配置存在且类型匹配 → 返回值正确。"""
        config = {"key": {"a": 1}}
        result, issues = val._section(config, "key", dict, "错误")
        self.assertEqual(result, {"a": 1})
        self.assertEqual(issues, 0)

    def test_missing_returns_missing(self):
        """配置缺失 → 返回 _MISSING。"""
        config = {}
        result, issues = val._section(config, "missing_key", dict, "错误")
        self.assertIs(result, val._MISSING)
        self.assertEqual(issues, 0)

    def test_wrong_type_returns_missing_plus_one(self):
        """类型不匹配 → 返回 _MISSING 且 issues+1。"""
        config = {"key": "not_a_dict"}
        result, issues = val._section(config, "key", dict, "类型错误")
        self.assertIs(result, val._MISSING)
        self.assertEqual(issues, 1)


class TestValidateStringConfigs(unittest.TestCase):
    """_validate_string_configs 测试。"""

    def test_valid_strings_no_issues(self):
        """所有字符串配置合法 → 0 问题。"""
        config = {
            "holdings_dir": "data",
            "holdings_filename": "持仓.xlsx",
            "output_dir": "reports",
            "llm_key_file": "data/config/llm_key.json",
            "llm_settings_file": "data/config/llm_settings.json",
        }
        n = val._validate_string_configs(config, 0)
        self.assertEqual(n, 0)

    def test_non_string_keys_warn(self):
        """非字符串值 → 告警（None 值跳过，不计入问题）。"""
        config = {"holdings_dir": 123, "output_dir": None}
        n = val._validate_string_configs(config, 0)
        self.assertEqual(n, 1)

    def test_empty_holdings_filename_warns(self):
        """空文件名 → 告警。"""
        config = {"holdings_filename": ""}
        n = val._validate_string_configs(config, 0)
        self.assertEqual(n, 1)


class TestValidateNewsTopCount(unittest.TestCase):
    """_validate_news_top_count 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_news_top_count({}, 0)
        self.assertEqual(n, 0)

    def test_valid_positive_no_issue(self):
        """有效正数 → 正常。"""
        n = val._validate_news_top_count({"news_top_count": 100}, 0)
        self.assertEqual(n, 0)

    def test_negative_warns(self):
        """负数 → 告警。"""
        n = val._validate_news_top_count({"news_top_count": -5}, 0)
        self.assertEqual(n, 1)

    def test_zero_warns(self):
        """零 → 告警。"""
        n = val._validate_news_top_count({"news_top_count": 0}, 0)
        self.assertEqual(n, 1)

    def test_non_integer_warns(self):
        """非整数字符串 → 告警。"""
        n = val._validate_news_top_count({"news_top_count": "abc"}, 0)
        self.assertEqual(n, 1)


class TestValidateCacheTtl(unittest.TestCase):
    """_validate_cache_ttl 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_cache_ttl({}, 0)
        self.assertEqual(n, 0)

    def test_non_dict_warns(self):
        """不是 dict → 告警。"""
        n = val._validate_cache_ttl({"cache_ttl": "invalid"}, 0)
        self.assertEqual(n, 1)

    def test_valid_values_no_issue(self):
        """有效值 → 正常。"""
        n = val._validate_cache_ttl({"cache_ttl": {"price": 86400, "news": 900}}, 0)
        self.assertEqual(n, 0)

    def test_bad_values_warn(self):
        """非数字/负值/零 → 告警。"""
        n = val._validate_cache_ttl({"cache_ttl": {"price": "abc", "news": -1, "rank": 0}}, 0)
        self.assertEqual(n, 3)


class TestValidateNewsSources(unittest.TestCase):
    """_validate_news_sources 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_news_sources({}, 0)
        self.assertEqual(n, 0)

    def test_unknown_source_warns(self):
        """未知源 → 告警。"""
        n = val._validate_news_sources({"news_sources": {"my_source": True}}, 0)
        self.assertEqual(n, 1)

    def test_non_bool_warns(self):
        """非布尔值 → 告警。"""
        n = val._validate_news_sources({"news_sources": {"sina": "yes"}}, 0)
        self.assertEqual(n, 1)

    def test_valid_no_issue(self):
        """有效配置 → 正常。"""
        n = val._validate_news_sources({"news_sources": {"sina": True, "cls": False}}, 0)
        self.assertEqual(n, 0)


class TestValidatePreferredProvider(unittest.TestCase):
    """_validate_preferred_provider 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_preferred_provider({}, 0)
        self.assertEqual(n, 0)

    def test_unknown_type_and_name_warn(self):
        """未知类型 + 未知名称 → 2 告警。"""
        n = val._validate_preferred_provider({"preferred_provider": {"stocks": "tencent", "price": "nonexistent"}}, 0)
        self.assertEqual(n, 2)

    def test_valid_no_issue(self):
        """有效配置 → 正常。"""
        n = val._validate_preferred_provider({"preferred_provider": {"price": "tencent", "fund_rank": "tiantian"}}, 0)
        self.assertEqual(n, 0)


class TestValidateUserFundBenchmarks(unittest.TestCase):
    """_validate_user_fund_benchmarks 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_user_fund_benchmarks({}, 0)
        self.assertEqual(n, 0)

    def test_not_dict_warns(self):
        """不是 dict → 告警。"""
        n = val._validate_user_fund_benchmarks({"user_fund_benchmarks": ["600519", "沪深300"]}, 0)
        self.assertEqual(n, 1)

    def test_invalid_code_warns(self):
        """无效代码 → 告警。"""
        n = val._validate_user_fund_benchmarks({"user_fund_benchmarks": {"": "沪深300"}}, 0)
        self.assertEqual(n, 1)

    def test_invalid_benchmark_warns(self):
        """无效基准 → 告警。"""
        n = val._validate_user_fund_benchmarks({"user_fund_benchmarks": {"000001": 12345}}, 0)
        self.assertEqual(n, 1)


class TestValidateEnableBoards(unittest.TestCase):
    """_validate_enable_boards 测试。"""

    def test_missing_all_no_issue(self):
        """全部缺失 → 正常（默认启用）。"""
        n = val._validate_enable_boards({}, 0)
        self.assertEqual(n, 0)

    def test_valid_bools_no_issue(self):
        """有效布尔值 → 正常。"""
        n = val._validate_enable_boards({"enable_b_series": True, "enable_news": False}, 0)
        self.assertEqual(n, 0)

    def test_non_bool_warns(self):
        """非布尔值 → 告警。"""
        n = val._validate_enable_boards({"enable_b_series": "yes"}, 0)
        self.assertEqual(n, 1)


class TestValidateMarketHours(unittest.TestCase):
    """_validate_market_hours 测试。"""

    def test_missing_all_no_issue(self):
        """全部缺失 → 正常。"""
        n = val._validate_market_hours({}, 0)
        self.assertEqual(n, 0)

    def test_invalid_market_hour_aware_warns(self):
        """market_hour_aware 不是字符串列表 → 告警。"""
        n = val._validate_market_hours({"market_hour_aware": "not_a_list"}, 0)
        self.assertEqual(n, 1)

    def test_market_hour_ttl_too_small_warns(self):
        """market_hour_ttl < 30 → 告警。"""
        n = val._validate_market_hours({"market_hour_ttl": 10}, 0)
        self.assertEqual(n, 1)

    def test_market_hour_ttl_invalid_type_warns(self):
        """market_hour_ttl 不是整数 → 告警。"""
        n = val._validate_market_hours({"market_hour_ttl": "abc"}, 0)
        self.assertEqual(n, 1)

    def test_market_hours_not_dict_warns(self):
        """market_hours 不是 dict → 告警。"""
        n = val._validate_market_hours({"market_hours": "invalid"}, 0)
        self.assertEqual(n, 1)


class TestValidateBenchmarkIndices(unittest.TestCase):
    """_validate_benchmark_indices 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_benchmark_indices({}, 0)
        self.assertEqual(n, 0)

    def test_not_dict_warns(self):
        """不是 dict → 告警。"""
        n = val._validate_benchmark_indices({"history": {"benchmark_indices": "invalid"}}, 0)
        self.assertEqual(n, 1)

    def test_invalid_key_warns(self):
        """无效键 → 告警。"""
        n = val._validate_benchmark_indices({"history": {"benchmark_indices": {"ab": "沪深300"}}}, 0)
        self.assertGreaterEqual(n, 1)

    def test_non_string_value_warns(self):
        """非字符串值 → 告警。"""
        n = val._validate_benchmark_indices({"history": {"benchmark_indices": {"000001": 12345}}}, 0)
        self.assertGreaterEqual(n, 1)


class TestValidateComparisonIndices(unittest.TestCase):
    """_validate_comparison_indices 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_comparison_indices({}, 0)
        self.assertEqual(n, 0)

    def test_not_dict_warns(self):
        """不是 dict → 告警。"""
        n = val._validate_comparison_indices({"comparison_indices": "invalid"}, 0)
        self.assertEqual(n, 1)


class TestValidateRebalanceConfig(unittest.TestCase):
    """_validate_rebalance_config 测试。"""

    def test_missing_no_issue(self):
        """缺失 → 正常。"""
        n = val._validate_rebalance_config({}, 0)
        self.assertEqual(n, 0)

    def test_not_dict_warns(self):
        """不是 dict → 告警。"""
        n = val._validate_rebalance_config({"rebalance": "invalid"}, 0)
        self.assertEqual(n, 1)

    def test_invalid_threshold_warns(self):
        """threshold 超出范围 → 告警。"""
        n = val._validate_rebalance_config({"rebalance": {"threshold": 5}}, 0)
        self.assertEqual(n, 1)

    def test_valid_threshold_no_issue(self):
        """有效 threshold → 正常。"""
        n = val._validate_rebalance_config({"rebalance": {"threshold": 0.15}}, 0)
        self.assertEqual(n, 0)

    def test_invalid_profile_warns(self):
        """无效 profile → 告警。"""
        n = val._validate_rebalance_config({"rebalance": {"profile": "extreme"}}, 0)
        self.assertEqual(n, 1)

    def test_invalid_silence_days_warns(self):
        """负数的 silence_days → 告警。"""
        n = val._validate_rebalance_config({"rebalance": {"silence_days": -1}}, 0)
        self.assertEqual(n, 1)

    def test_target_allocation_not_dict_warns(self):
        """target_allocation 不是 dict → 告警。"""
        n = val._validate_rebalance_config({"rebalance": {"target_allocation": "invalid"}}, 0)
        self.assertEqual(n, 1)


class TestValidateConfigEntryPoint(unittest.TestCase):
    """validate_config 入口函数测试。"""

    def test_clean_config_returns_zero(self):
        """有效配置 → 0 问题。"""
        config = {
            "holdings_dir": "data/holdings",
            "holdings_filename": "持仓.xlsx",
            "output_dir": "reports",
            "llm_key_file": "data/config/llm_key.json",
            "llm_settings_file": "data/config/llm_settings.json",
            "news_top_count": 100,
            "cache_ttl": {"price": 86400, "news": 900},
            "news_sources": {"sina": True, "cls": False},
            "preferred_provider": {"price": "tencent"},
            "user_fund_benchmarks": {"000001": "沪深300"},
        }
        n = val.validate_config(config)
        self.assertEqual(n, 0)

    def test_none_config_fallsback(self):
        """config=None 时调用 get_config() 获取配置。"""
        with patch("src.python.config._core.get_config") as mock_get:
            mock_get.return_value = {}
            n = val.validate_config(None)
            mock_get.assert_called()
            # 空配置会有多个问题
            self.assertGreaterEqual(n, 0)

    def test_multiple_issues_accumulate(self):
        """多个问题累加计数。"""
        n = val.validate_config({
            "holdings_filename": "",
            "news_top_count": -5,
            "cache_ttl": "invalid",
        })
        self.assertEqual(n, 3)

    def test_validate_enable_llm_warns_on_unknown_key(self):
        """_validate_enable_llm 对 llm_settings.json 中未知模块告警。"""
        mock_llm_config = {"enabled_llm": {"nonexistent_module": True}}
        with patch("src.python.config._core.get_llm_config", return_value=mock_llm_config):
            n = val._validate_enable_llm(0)
            self.assertEqual(n, 1)

    def test_validate_enable_llm_non_dict_warns(self):
        """enabled_llm 不是 dict → 告警。"""
        mock_llm_config = {"enabled_llm": "not_a_dict"}
        with patch("src.python.config._core.get_llm_config", return_value=mock_llm_config):
            n = val._validate_enable_llm(0)
            self.assertEqual(n, 1)
