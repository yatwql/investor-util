"""配置管理模块单元测试 — 异常场景与边界测试。

测试目标：
  - get_config — 缺失/损坏/空文件返回默认值
  - init_config — 初始化创建默认配置
  - set_config — 写入/读取/异常场景

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_config -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.python import config as cfg
from src.python.core.constants import PROJECT_ROOT
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


# 路径型配置键的预期绝对路径基准
_ABS_HOLDINGS_DIR = os.path.join(PROJECT_ROOT, "data/holdings")
_ABS_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "reports")
_ABS_LLM_KEY = os.path.join(PROJECT_ROOT, "data/config/llm_key.json")
_ABS_LLM_SETTINGS = os.path.join(PROJECT_ROOT, "data/config/llm_settings.json")

# 模板中的路径型键使用相对路径（用户友好），_DEFAULT_CONFIG 使用绝对路径，
# 值比较时需跳过这些键
_PATH_KEYS_IN_TEMPLATE = frozenset({
    "holdings_dir", "output_dir", "llm_settings_file",
    "llm_key_file", "llm_providers_file",
})



class TestGetConfig(unittest.TestCase):
    """get_config 的异常场景测试。"""

    def setUp(self):
        # 备份原始 _CONFIG_FILE，用临时目录替代
        self._orig_config = cfg._config_defaults._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._config_defaults._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        cfg._config_defaults._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    @pytest.mark.smoke
    def test_missing_file_returns_defaults(self):
        """配置文件不存在 → 返回默认值。"""
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], _ABS_HOLDINGS_DIR)
        self.assertEqual(result["holdings_filename"], "个人投资持仓信息.xlsx")
        self.assertEqual(result.get("output_dir"), _ABS_OUTPUT_DIR)
        self.assertEqual(result.get("news_top_count"), 300)
        self.assertIn("cache_ttl", result)
        self.assertIn("preferred_provider", result)

    def test_corrupted_json_returns_defaults(self):
        """配置文件损坏 → 返回默认值。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("{invalid json!!!")
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], _ABS_HOLDINGS_DIR)

    def test_empty_file_returns_defaults(self):
        """配置文件为空 → 返回默认值。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], _ABS_HOLDINGS_DIR)

    def test_partial_config_merge(self):
        """部分配置 → 未配置项用默认值补齐。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        partial = {"holdings_dir": "/custom/path"}
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(partial, f)
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "/custom/path")
        self.assertEqual(result["holdings_filename"], "个人投资持仓信息.xlsx")
        self.assertEqual(result.get("output_dir"), _ABS_OUTPUT_DIR)

    @pytest.mark.smoke
    def test_valid_config_read(self):
        """完整配置正常读取。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        data = {
            "holdings_dir": "/a",
            "holdings_filename": "b.xlsx",
            "output_dir": "/out",
            "news_top_count": 50,
            "cache_ttl": {"price": 3600},
            "preferred_provider": {},
        }
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "/a")
        self.assertEqual(result["news_top_count"], 50)


class TestInitConfig(unittest.TestCase):
    """init_config 的边界场景测试。"""

    def setUp(self):
        self._orig_config = cfg._config_defaults._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._config_defaults._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        cfg._config_defaults._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    @pytest.mark.smoke
    def test_init_creates_default_config(self):
        """初始化 → 创建包含默认值的配置文件。"""
        self.assertFalse(os.path.exists(cfg._config_defaults._CONFIG_FILE))
        cfg.init_config()
        self.assertTrue(os.path.exists(cfg._config_defaults._CONFIG_FILE))
        data = cfg.get_config()
        self.assertEqual(data["holdings_dir"], _ABS_HOLDINGS_DIR)

    def test_init_does_not_overwrite_existing(self):
        """配置文件已存在 → 不覆盖。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        existing = {"holdings_dir": "/manual"}
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f)
        cfg.init_config()
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["holdings_dir"], "/manual")

    def test_init_nonexistent_dir(self):
        """配置目录不存在 → 创建后写入。"""
        non_exist = os.path.join(self.tmp.name, "sub", "config")
        cfg._config_defaults._CONFIG_FILE = os.path.join(non_exist, "config.json")
        cfg.init_config()
        self.assertTrue(os.path.exists(cfg._config_defaults._CONFIG_FILE))


class TestSetConfig(unittest.TestCase):
    """set_config 的异常场景测试。"""

    def setUp(self):
        self._orig_config = cfg._config_defaults._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._config_defaults._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        cfg._config_defaults._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    @pytest.mark.smoke
    def test_set_and_get(self):
        """写入 → 再次读取值与写入一致。"""
        cfg.init_config()
        cfg.set_config("holdings_dir", "/new/path")
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "/new/path")

    def test_set_preserves_other_keys(self):
        """写入单个键 → 不影响其他键。"""
        cfg.init_config()
        cfg.set_config("holdings_dir", "/new/path")
        result = cfg.get_config()
        self.assertEqual(result["holdings_filename"], "个人投资持仓信息.xlsx")
        self.assertEqual(result.get("output_dir"), _ABS_OUTPUT_DIR)

    def test_set_new_key(self):
        """写入不存在的键 → 新增。"""
        cfg.init_config()
        cfg.set_config("custom_key", "custom_value")
        result = cfg.get_config()
        self.assertEqual(result.get("custom_key"), "custom_value")

    def test_set_emits_log_on_error(self):
        """文件无写入权限时抛出 PermissionError。"""
        cfg.init_config()
        # 模拟写入失败，读取正常（让 get_config 能读出已有配置）
        _real_open = open
        def _mock_mkstemp(*args, **kwargs):
            raise PermissionError("denied")
        with patch("tempfile.mkstemp", side_effect=_mock_mkstemp):
            with self.assertRaises(PermissionError):
                cfg.set_config("key", "value")


if __name__ == "__main__":
    unittest.main()


class TestValidateConfig(unittest.TestCase):
    """validate_config 对各类配置错误的检测。"""

    def test_clean_config_returns_zero(self) -> None:
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
        n = cfg.validate_config(config)
        self.assertEqual(n, 0)

    def test_string_type_errors(self) -> None:
        """字符串配置项不是字符串类型 → 告警。"""
        config = {"holdings_dir": 123, "output_dir": None, "holdings_filename": True}
        n = cfg.validate_config(config)
        self.assertGreaterEqual(n, 2)

    def test_empty_holdings_filename(self) -> None:
        """holdings_filename 为空 → 告警。"""
        n = cfg.validate_config({"holdings_filename": ""})
        self.assertEqual(n, 1)

    def test_news_top_count_invalid(self) -> None:
        """news_top_count 无效 → 告警。"""
        n1 = cfg.validate_config({"news_top_count": -5})
        self.assertEqual(n1, 1)
        n2 = cfg.validate_config({"news_top_count": "abc"})
        self.assertEqual(n2, 1)
        n3 = cfg.validate_config({"news_top_count": 0})
        self.assertEqual(n3, 1)

    def test_cache_ttl_non_dict(self) -> None:
        """cache_ttl 不是 dict → 告警。"""
        n = cfg.validate_config({"cache_ttl": "all_good"})
        self.assertEqual(n, 1)

    def test_cache_ttl_bad_values(self) -> None:
        """cache_ttl 内负值/非数字 → 告警。"""
        n = cfg.validate_config({"cache_ttl": {"price": "abc", "news": -1, "rank": 0}})
        self.assertEqual(n, 3)

    def test_news_sources_unknown_key(self) -> None:
        """news_sources 内未知的源 → 告警。"""
        n = cfg.validate_config({"news_sources": {"my_source": True}})
        self.assertEqual(n, 1)

    def test_news_sources_non_bool(self) -> None:
        """news_sources 内非布尔值 → 告警。"""
        n = cfg.validate_config({"news_sources": {"sina": "yes"}})
        self.assertEqual(n, 1)

    def test_preferred_provider_unknown(self) -> None:
        """preferred_provider 未知类型/名称 → 告警。"""
        n = cfg.validate_config({"preferred_provider": {"stocks": "tencent", "price": "nonexistent"}})
        self.assertEqual(n, 2)

    def test_user_fund_benchmarks_not_dict(self) -> None:
        """user_fund_benchmarks 不是 dict → 告警。"""
        n = cfg.validate_config({"user_fund_benchmarks": ["600519", "沪深300"]})
        self.assertEqual(n, 1)


# ═══════════════════════════════════════════════════════════════
#  System Prompt 覆盖路径测试（pytest）
# ═══════════════════════════════════════════════════════════════
#
# 测试 generate_global_macro / generate_expert_review / etc.
# 中对 system_prompt 的处理：
#   llm_settings.json system_prompt_* 非 null → 用配置值
#   llm_settings.json system_prompt_* 为 null → 回退代码内置默认值
#   缺少 system_prompt_* 键 → 回退代码内置默认值


class TestSystemPromptOverride:
    """验证 system_prompt_* 覆盖字段的控制逻辑。"""

    def test_override_from_config(self, mocker):
        """配置中 system_prompt_global_macro 为非 null 时，应以配置值为准。"""
        import src.python.llm.generators as _gens
        mock_system = "自定义全球政经局势提示词，请分析全球经济趋势。"

        # mock get_llm_config 返回包含 system_prompt_global_macro 的配置
        mock_config = {
            "system_prompt_global_macro": mock_system,
            "cache_enabled_global_macro": False,
            "max_tokens_global_macro": 800,
            "timeout_global_macro": 60,
            # model 设为 None 以跳过实际 LLM 调用
            "model": None,
        }
        mocker.patch("src.python.llm.skeleton.get_llm_config", return_value=mock_config)
        # _generate_llm_module 位于 skeleton.py，内部调用 skeleton.get_llm_config 和
        # skeleton._generate_llm_content，因此 mock 需指向 skeleton 而非 generators
        mock_gen = mocker.patch("src.python.llm.skeleton.generate_llm_content",
                                return_value=(None, False))

        _gens.generate_global_macro(
            a_indices={}, us_indices={}, total_mv=100000,
            total_profit=5000, total_cost=0, categories={},
        )

        # 验证 _generate_llm_content 被调用，且第 4 个 positional 参数（system_prompt）等于自定义值
        # _generate_llm_content(llm_config, cache_key, cache_ttl, system_prompt, user_prompt, ...)
        call_args = mock_gen.call_args[0]  # positional args
        assert call_args[3] == mock_system, (
            f"预期 system_prompt={mock_system!r}, 实际={call_args[3]!r}"
        )

    def test_fallback_to_default(self, mocker):
        """配置中 system_prompt_global_macro 为 null 时，应使用代码内置默认值。"""
        from src.python.llm.prompts import _SYSTEM_GLOBAL_MACRO
        import src.python.llm.generators as _gens

        mock_config = {
            "system_prompt_global_macro": None,
            "cache_enabled_global_macro": False,
            "max_tokens_global_macro": 800,
            "timeout_global_macro": 60,
            "model": None,
        }
        mocker.patch("src.python.llm.skeleton.get_llm_config", return_value=mock_config)
        mock_gen = mocker.patch("src.python.llm.skeleton.generate_llm_content",
                                return_value=(None, False))

        _gens.generate_global_macro(
            a_indices={}, us_indices={}, total_mv=100000,
            total_profit=5000, total_cost=0, categories={},
        )

        call_args = mock_gen.call_args[0]
        # 应该使用代码内置默认值 _SYSTEM_GLOBAL_MACRO
        assert call_args[3] == _SYSTEM_GLOBAL_MACRO, (
            f"预期内置默认值, 实际={call_args[3][:50]!r}"
        )

    def test_missing_key_fallback(self, mocker):
        """配置中完全没有 system_prompt_global_macro 键时，应使用内置默认值。"""
        from src.python.llm.prompts import _SYSTEM_GLOBAL_MACRO
        import src.python.llm.generators as _gens

        mock_config = {
            "cache_enabled_global_macro": False,
            "max_tokens_global_macro": 800,
            "timeout_global_macro": 60,
            "model": None,
        }
        mocker.patch("src.python.llm.skeleton.get_llm_config", return_value=mock_config)
        mock_gen = mocker.patch("src.python.llm.skeleton.generate_llm_content",
                                return_value=(None, False))

        _gens.generate_global_macro(
            a_indices={}, us_indices={}, total_mv=100000,
            total_profit=5000, total_cost=0, categories={},
        )

        call_args = mock_gen.call_args[0]
        assert call_args[3] == _SYSTEM_GLOBAL_MACRO, (
            f"预期内置默认值, 实际={call_args[3][:50]!r}"
        )


class TestLlmSettingsKeyConsistency:
    """验证 llm_settings.json 的键名与 _KNOWN_LLM_SETTINGS_KEYS 一致。"""

    def test_all_keys_tracked(self):
        """llm_settings.json 中不应有未在 _KNOWN_LLM_SETTINGS_KEYS 中登记的键。"""
        import json
        from src.python.config import _KNOWN_LLM_SETTINGS_KEYS, _strip_json_comments, get_llm_settings_path


        with open(get_llm_settings_path(), encoding="utf-8") as f:
            raw = f.read()
            llm = json.loads(_strip_json_comments(raw))

        file_keys = set(llm.keys())
        untracked = file_keys - _KNOWN_LLM_SETTINGS_KEYS
        assert not untracked, (
            f"llm_settings.json 中发现 {len(untracked)} 个未登记键名: {sorted(untracked)}"
        )


# ═══════════════════════════════════════════════════════════════
#  config 原子写入断电恢复回归测试
# ═══════════════════════════════════════════════════════════════


class TestAtomicWriteCrashRecovery(unittest.TestCase):
    """验证 config.set_config 在写入过程中崩溃不会导致配置文件损坏。

    模拟场景：
      1. 写入时 os.replace 抛出异常 → 配置保持原内容
      2. 写入时 tempfile.mkstemp 成功但后续崩溃 → 临时文件被清理
      3. 半写文件残留（模拟断电后重启）→ get_config 仍能返回默认值
    """

    def setUp(self):
        self._orig_config = cfg._config_defaults._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._config_defaults._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")
        cfg.init_config()

    def tearDown(self):
        cfg._config_defaults._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def test_replace_crash_preserves_original(self):
        """os.replace 抛出异常 → 原配置文件内容不变。"""
        # 先写入一个已知值
        cfg.set_config("holdings_dir", "/original/path")
        original_content = open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8").read()

        # 模拟 os.replace 崩溃
        with patch("src.python.config._core.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cfg.set_config("holdings_dir", "/new/path")

        # 文件内容应保持原样
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            self.assertEqual(f.read(), original_content)

    def test_replace_crash_tmp_file_cleaned(self):
        """os.replace 崩溃后临时文件被清理。"""
        cfg.set_config("holdings_dir", "/original")
        config_dir = os.path.dirname(cfg._config_defaults._CONFIG_FILE)
        tmp_files_before = [f for f in os.listdir(config_dir) if f.endswith(".tmp")]

        with patch("src.python.config._core.os.replace", side_effect=OSError("crash")):
            try:
                cfg.set_config("holdings_dir", "/new")
            except OSError:
                pass

        tmp_files_after = [f for f in os.listdir(config_dir) if f.endswith(".tmp")]
        self.assertEqual(len(tmp_files_after), len(tmp_files_before))

    def test_crash_before_replace_config_intact(self):
        """模拟写入过程中途崩溃（异常抛出前）/ 配置文件可读。"""
        cfg.set_config("output_dir", "/reports/original")

        def _crash_before_replace(tmp_path, final_path):
            # 模拟写入 tmp 成功后、replace 前崩溃
            raise RuntimeError("power failure")

        with patch("src.python.config._core.os.replace", side_effect=_crash_before_replace):
            with self.assertRaises(RuntimeError):
                cfg.set_config("output_dir", "/reports/crashed")

        # 直接读取文件内容验证（内存缓存可能已被 crash 污染）
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload.get("output_dir"), "/reports/original")

    def test_simulate_power_failure_then_recovery(self):
        """模拟断电后重启：残留临时文件不影响正常读取。"""
        cfg.set_config("holdings_dir", "/before/crash")

        # 模拟断电：手动创建临时文件但不执行 replace
        config_dir = os.path.dirname(cfg._config_defaults._CONFIG_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"holdings_dir": "/crash/data"}, f)

        # 模拟重启后 get_config → 应返回旧配置（临时文件被忽略）
        result = cfg.get_config()
        self.assertEqual(result.get("holdings_dir"), "/before/crash")

    def test_partial_write_after_crash_old_file_readable(self):
        """模拟 os.replace 前崩溃导致 tempfile 残留，旧配置仍可用。"""
        cfg.set_config("holdings_dir", "/safe/value")

        # 模拟磁盘写中途崩溃
        original_replace = os.replace
        call_count = [0]

        def _crash_mid_write(tmp_path, final_path):
            call_count[0] += 1
            if call_count[0] == 1:
                # 第一次调用：写入临时文件后崩溃
                raise OSError("disk full")
            # 后续调用正常
            return original_replace(tmp_path, final_path)

        # 多次 set_config 即使部分失败也不影响整体
        with patch("src.python.config._core.os.replace", side_effect=_crash_mid_write):
            with self.assertRaises(OSError):
                cfg.set_config("holdings_dir", "/unsafe")

        # 旧值依然可用（直接读文件避免内存缓存污染）
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload.get("holdings_dir"), "/safe/value")


class TestValidateReportSectionOrder(unittest.TestCase):
    """_validate_report_section_order 配置校验测试。"""

    def test_no_order_returns_zero(self):
        """report_section_order 未配置 → 0 问题。"""
        n = cfg.validate_config({"holdings_dir": "data"})
        self.assertEqual(n, 0)

    def test_valid_order_returns_zero(self):
        """有效配置 → 0 问题。"""
        n = cfg.validate_config({
            "report_section_order": {
                "summary": 1,
                "fund_manager": 6,
                "global_macro": 12,
            }
        })
        self.assertEqual(n, 0)

    def test_non_dict_order_warns(self):
        """report_section_order 不是 dict → 1 问题。"""
        n = cfg.validate_config({"report_section_order": "invalid"})
        self.assertEqual(n, 1)

    def test_unknown_key_warns(self):
        """未知模块标识 → 1 问题。"""
        n = cfg.validate_config({
            "report_section_order": {"nonexistent_module": 1}
        })
        self.assertEqual(n, 1)

    def test_non_integer_value_warns(self):
        """配置值不是整数 → 1 问题。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": "abc"}
        })
        self.assertEqual(n, 1)

    def test_negative_value_warns(self):
        """负值序号 → 1 问题。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": -5}
        })
        self.assertEqual(n, 1)

    def test_zero_value_warns(self):
        """零值序号 → 1 问题。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": 0}
        })
        self.assertEqual(n, 1)

    def test_duplicate_number_warns(self):
        """重复序号 → 1 问题（仅第二次出现时告警）。"""
        n = cfg.validate_config({
            "report_section_order": {"summary": 1, "fund_manager": 1}
        })
        self.assertEqual(n, 1)

    def test_llm_usage_in_config_warns(self):
        """llm_usage 出现在配置中 → 1 问题。"""
        n = cfg.validate_config({
            "report_section_order": {"llm_usage": 1}
        })
        self.assertEqual(n, 1)

    def test_multiple_issues_accumulate(self):
        """多个问题累加计数。"""
        n = cfg.validate_config({
            "report_section_order": {
                "unknown_key": 1,
                "summary": "abc",
                "fund_manager": -3,
            }
        })
        self.assertEqual(n, 3)


# ═══════════════════════════════════════════════════════════════
#  _get_default_config_template() 与 _DEFAULT_CONFIG 一致性
# ═══════════════════════════════════════════════════════════════


class TestDefaultConfigTemplateConsistency:
    """验证 _get_default_config_template() 生成的 JSON 模板与 _DEFAULT_CONFIG 等效。

    当在 _DEFAULT_CONFIG 中新增配置项时，必须在模板字符串中同步添加；
    反之，从模板中移除的键也应在 _DEFAULT_CONFIG 中删除。
    本测试通过解析模板并与 _DEFAULT_CONFIG 深度比较来检测不一致。
    """

    @pytest.mark.unit_config
    def test_template_equals_default_config(self):
        """模板 JSON 解析后应与 _DEFAULT_CONFIG 深度相等。"""
        import json

        template_str = cfg._get_default_config_template()
        cleaned = cfg._strip_json_comments(template_str)
        parsed = json.loads(cleaned)

        # 深度比较：排除可能因运行时环境动态变化的 cache_ttl
        # （由 get_cache_ttl_defaults() 生成，模板和 _DEFAULT_CONFIG 均引用同一函数，
        #  但 registry 可能在不同测试间被修改）
        assert parsed.keys() == cfg._DEFAULT_CONFIG.keys(), (
            f"模板与 _DEFAULT_CONFIG 键集不一致\n"
            f"模板独有: {parsed.keys() - cfg._DEFAULT_CONFIG.keys()}\n"
            f"配置独有: {cfg._DEFAULT_CONFIG.keys() - parsed.keys()}"
        )

        for key in parsed:
            if key == "cache_ttl":
                # cache_ttl 动态生成，兜底比较键集与值类型
                assert parsed["cache_ttl"].keys() == cfg._DEFAULT_CONFIG["cache_ttl"].keys(), (
                    f"cache_ttl 键集不一致: {parsed['cache_ttl'].keys() ^ cfg._DEFAULT_CONFIG['cache_ttl'].keys()}"
                )
                for k in parsed["cache_ttl"]:
                    assert type(parsed["cache_ttl"][k]) == type(cfg._DEFAULT_CONFIG["cache_ttl"][k]), (
                        f"cache_ttl.{k} 类型不匹配: {type(parsed['cache_ttl'][k])} vs {type(cfg._DEFAULT_CONFIG['cache_ttl'][k])}"
                    )
            if key in _PATH_KEYS_IN_TEMPLATE:
                # 路径键：模板保留相对路径便于用户编辑，_DEFAULT_CONFIG 使用绝对路径，
                # 检查模板值是否为相对路径即可，不做值相等性断言
                assert not os.path.isabs(parsed[key]), (
                    f"模板中的路径键 {key!r} 应为相对路径，"
                    f"实际为绝对路径: {parsed[key]!r}"
                )
                assert os.path.isabs(cfg._DEFAULT_CONFIG[key]), (
                    f"_DEFAULT_CONFIG 中的路径键 {key!r} 应为绝对路径，"
                    f"实际为相对路径: {cfg._DEFAULT_CONFIG[key]!r}"
                )
            else:
                assert parsed[key] == cfg._DEFAULT_CONFIG[key], (
                    f"键 {key!r} 值不匹配:\n"
                    f"  模板: {parsed[key]!r}\n"
                    f"  配置: {cfg._DEFAULT_CONFIG[key]!r}"
                )
