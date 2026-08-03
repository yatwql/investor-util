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
from src.python.config import _comments
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
_PATH_KEYS_IN_TEMPLATE = frozenset(
    {
        "holdings_dir",
        "output_dir",
        "llm_settings_file",
        "llm_key_file",
        "llm_providers_file",
    }
)


class TestMergeLlmDefaults(unittest.TestCase):
    """_merge_llm_defaults 运行时补默认语义测试。

    语义（与 get_config 的 config.json 合并策略一致）：
      - 默认值打底，用户覆盖
      - 用户显式 null 不覆盖默认
      - 嵌套 dict 一层合并
      - 未知键透传
    """

    def setUp(self):
        from src.python.config._core import _merge_llm_defaults

        self._merge = _merge_llm_defaults

    def test_empty_base_returns_full_defaults(self):
        """空用户配置 → 返回完整默认配置。"""
        merged = self._merge({})
        self.assertEqual(merged["max_retries"], 2)
        self.assertEqual(merged["temperature_global_macro"], 0.3)
        self.assertIn("pricing", merged)
        self.assertIn("fact_check", merged)
        self.assertIn("debate", merged)

    def test_user_scalar_overrides_default(self):
        """用户标量覆盖默认值，其余默认保留。"""
        merged = self._merge({"max_retries": 5})
        self.assertEqual(merged["max_retries"], 5)
        self.assertEqual(merged["llm_max_concurrency"], 3)

    def test_null_does_not_override_default(self):
        """用户显式 null → 不覆盖默认值（null 不覆盖）。"""
        merged = self._merge({"max_retries": None, "temperature_global_macro": None})
        self.assertEqual(merged["max_retries"], 2)
        self.assertEqual(merged["temperature_global_macro"], 0.3)

    def test_dict_one_level_merge(self):
        """嵌套 dict 一层合并，只覆盖部分子键不丢默认。"""
        merged = self._merge({"enabled_llm": {"global_macro": False}})
        self.assertFalse(merged["enabled_llm"]["global_macro"])
        self.assertTrue(merged["enabled_llm"]["expert_review"])

        merged2 = self._merge({"pricing": {"currency": "USD"}})
        self.assertEqual(merged2["pricing"]["currency"], "USD")
        self.assertIn("claude-sonnet-4-6", merged2["pricing"])

    def test_unknown_key_passthrough(self):
        """默认中不存在的键原样透传（未知键透传）。"""
        merged = self._merge({"custom_field": "custom_value"})
        self.assertEqual(merged["custom_field"], "custom_value")

    def test_debate_defaults_preserved(self):
        """debate 段缺失 → 默认值保留（schema 校验由 _load_debate_config 兜底）。"""
        merged = self._merge({})
        self.assertEqual(merged["debate"]["max_total_tokens_per_report"], 48000)
        self.assertEqual(merged["debate"]["qa_concentration"]["threshold"], 0.20)


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

    def test_legacy_history_analysis_migrates_to_fetch_mode(self):
        """旧配置键 history.analysis → 自动迁移为 history.fetch_mode。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        legacy = {"history": {"analysis": "off"}}
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(legacy, f)
        result = cfg.get_config()
        hist = result.get("history", {})
        self.assertEqual(hist.get("fetch_mode"), "off")
        self.assertNotIn("analysis", hist)

    def test_legacy_history_analysis_kept_when_fetch_mode_present(self):
        """旧键与新键并存时，显式 fetch_mode 优先，analysis 被清理。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        mixed = {"history": {"analysis": "off", "fetch_mode": "auto"}}
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(mixed, f)
        result = cfg.get_config()
        hist = result.get("history", {})
        self.assertEqual(hist.get("fetch_mode"), "auto")
        self.assertNotIn("analysis", hist)

    def test_fetch_mode_default_is_auto(self):
        """未配置 history 时 fetch_mode 默认 auto。"""
        result = cfg.get_config()
        self.assertEqual(result.get("history", {}).get("fetch_mode"), "auto")


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

    @pytest.mark.smoke
    def test_init_template_writes_relative_paths(self):
        """首次生成 config.json → 路径型键为相对路径（全新安装可移植）。"""
        # conftest _isolate_sensitive_paths 会把 llm_settings_file / llm_key_file /
        # llm_providers_file 注入为临时路径，此处还原为项目根内路径，验证模板在
        # 真实场景下写相对路径
        _defaults = cfg._config_defaults._DEFAULT_CONFIG
        _rel_values = {
            "llm_settings_file": os.path.join(PROJECT_ROOT, "data/config/llm_settings.json"),
            "llm_key_file": os.path.join(PROJECT_ROOT, "data/config/llm_key.json"),
            "llm_providers_file": os.path.join(PROJECT_ROOT, "data/config/llm_providers.json"),
        }
        _orig = {k: _defaults[k] for k in _rel_values}
        try:
            _defaults.update(_rel_values)
            cfg.init_config()
        finally:
            _defaults.update(_orig)
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            raw = f.read()
        cleaned = _comments._strip_json_comments(raw)
        data = json.loads(cleaned)
        for key in _PATH_KEYS_IN_TEMPLATE:
            self.assertFalse(
                os.path.isabs(data[key]),
                f"{key} 被写成绝对路径: {data[key]}",
            )


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

    @pytest.mark.smoke
    def test_set_non_path_key_preserves_relative_paths(self):
        """写非路径键（如隐私提示）→ 路径型键保持相对路径，不落盘绝对路径。

        显式预写相对路径配置，隔离 conftest 对 llm_settings_file 的跨盘注入。
        """
        os.makedirs(self.tmp.name, exist_ok=True)
        relative = {
            "holdings_dir": "data/holdings",
            "holdings_filename": "个人投资持仓信息.xlsx",
            "output_dir": "reports",
            "llm_settings_file": "data/config/llm_settings.json",
            "llm_key_file": "data/config/llm_key.json",
            "llm_providers_file": "data/config/llm_providers.json",
            "enable_fund_deep_analysis": True,
            "news_top_count": 300,
        }
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(relative, f)
        # 生产环境实际触发 set_config 的入口：首次运行隐私提示标记
        cfg.set_config("_privacy_notice_shown", True)
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for key in _PATH_KEYS_IN_TEMPLATE:
            self.assertFalse(
                os.path.isabs(data[key]),
                f"{key} 被写成绝对路径: {data[key]}",
            )

    def test_set_relative_path_value_kept_relative(self):
        """写入相对路径值 → 落盘仍为相对路径，读取时被绝对化。"""
        cfg.init_config()
        cfg.set_config("holdings_dir", "data/custom")
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            data = json.loads(_comments._strip_json_comments(f.read()))
        self.assertEqual(data["holdings_dir"], "data/custom")
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], os.path.join(PROJECT_ROOT, "data/custom"))

    def test_set_external_absolute_path_kept(self):
        """写入 PROJECT_ROOT 之外的绝对路径 → 保持绝对，不被误相对化（越界保护）。"""
        cfg.init_config()
        external = os.path.join(os.path.dirname(PROJECT_ROOT), "external")
        cfg.set_config("holdings_dir", external)
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            data = json.loads(_comments._strip_json_comments(f.read()))
        self.assertEqual(data["holdings_dir"], external)


class TestSetConfigSingleKeyPatch(unittest.TestCase):
    """set_config 单键 patch：保留注释分组、只改目标键、新键追加。

    单键 patch 基于磁盘原始文本仅替换目标键 value，保留模板的
    ``// ── X. ...`` 分组注释与行尾注释，不破坏相邻键。本类用例
    断言注释与相邻键保持完整。
    """

    def setUp(self):
        self._orig_config = cfg._config_defaults._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._config_defaults._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")
        cfg.init_config()

    def tearDown(self):
        cfg._config_defaults._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def _read_disk(self) -> str:
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            return f.read()

    def test_preserves_comment_groups_and_inline(self):
        """set_config 后分组注释与行尾注释完整保留，目标键值已更新。"""
        cfg.set_config("enable_news", False)
        raw = self._read_disk()
        # 首尾分组注释保留
        self.assertIn("// ── A. 路径与文件 ──", raw)
        self.assertIn("// ── L. 批量并行调度 ──", raw)
        # enable_news 行尾注释保留
        self.assertIn("// 市场新闻（#12）", raw)
        # 值已更新
        data = json.loads(_comments._strip_json_comments(raw))
        self.assertFalse(data["enable_news"])

    def test_patch_only_touches_target_key(self):
        """仅替换目标键值，其余键与注释保持。"""
        cfg.set_config("market_hour_ttl", 60)
        raw = self._read_disk()
        self.assertIn('"market_hour_ttl": 60,', raw)
        self.assertNotIn('"market_hour_ttl": 30', raw)
        self.assertIn("// ── C. 数据源与提供商 ──", raw)
        self.assertIn('"news_top_count": 300,', raw)
        self.assertIn("// ── I. 再平衡配置 ──", raw)

    def test_new_key_appended_at_end(self):
        """新键追加到对象末尾，已有注释与其他键不受影响。"""
        cfg.set_config("custom_extra", {"nested": [1, 2, 3]})
        raw = self._read_disk()
        data = json.loads(_comments._strip_json_comments(raw))
        self.assertEqual(data["custom_extra"], {"nested": [1, 2, 3]})
        # 新键位于文件末尾的顶层对象内
        self.assertLess(raw.rfind('"custom_extra"'), raw.rfind("}"))
        self.assertIn("// ── D. 市场时段与缓存 ──", raw)

    def test_replace_nested_value_preserves_neighbors(self):
        """替换嵌套 dict 值不破坏相邻键与注释。"""
        cfg.set_config("comparison_indices", {"sh000300": "沪深300", "sh000905": "中证500"})
        raw = self._read_disk()
        data = json.loads(_comments._strip_json_comments(raw))
        self.assertEqual(data["comparison_indices"], {"sh000300": "沪深300", "sh000905": "中证500"})
        self.assertIn("// ── F. 业绩基准与无风险利率 ──", raw)
        self.assertIsNone(data["risk_free_rate"])
        self.assertEqual(data["user_fund_benchmarks"], {})

    def test_first_creation_has_comment_groups(self):
        """文件不存在时 set_config 用模板打底 → 落盘带完整分组注释。"""
        os.remove(cfg._config_defaults._CONFIG_FILE)
        cfg.set_config("_privacy_notice_shown", True)
        raw = self._read_disk()
        self.assertIn("// ── A. 路径与文件 ──", raw)
        data = json.loads(_comments._strip_json_comments(raw))
        self.assertTrue(data["_privacy_notice_shown"])


class TestDelConfig(unittest.TestCase):
    """del_config 单键删除：保留注释分组、删中间键/末键、键不存在静默。"""

    def setUp(self):
        self._orig_config = cfg._config_defaults._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._config_defaults._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")
        cfg.init_config()

    def tearDown(self):
        cfg._config_defaults._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def _read_disk(self) -> str:
        with open(cfg._config_defaults._CONFIG_FILE, encoding="utf-8") as f:
            return f.read()

    def test_del_existing_key_removes(self):
        """删除已有键 → 键消失，文件仍为合法 JSON。"""
        cfg.set_config("custom_key", 123)
        cfg.del_config("custom_key")
        data = json.loads(_comments._strip_json_comments(self._read_disk()))
        self.assertNotIn("custom_key", data)

    def test_del_nonexistent_key_noop(self):
        """键不存在 → 静默返回，文件不变。"""
        raw_before = self._read_disk()
        cfg.del_config("nonexistent_key_xyz")
        self.assertEqual(self._read_disk(), raw_before)

    def test_del_preserves_comments_and_neighbors(self):
        """删除后分组注释与相邻键保持完整。"""
        cfg.set_config("custom_a", 1)
        cfg.del_config("custom_a")
        raw = self._read_disk()
        self.assertIn("// ── A. 路径与文件 ──", raw)
        data = json.loads(_comments._strip_json_comments(raw))
        self.assertEqual(data["news_top_count"], 300)

    def test_del_last_key_keeps_valid_json(self):
        """删除最后一个键（无尾随逗号）→ 清理前一成员尾逗号，JSON 合法。"""
        cfg.set_config("z_last", True)
        cfg.del_config("z_last")
        data = json.loads(_comments._strip_json_comments(self._read_disk()))
        self.assertNotIn("z_last", data)
        self.assertIn("risk_free_rate", data)

    def test_del_middle_key_keeps_neighbors(self):
        """删除中间键（值后带逗号）→ 后续键保留。"""
        cfg.set_config("m1", 1)
        cfg.set_config("m2", 2)
        cfg.del_config("m1")
        data = json.loads(_comments._strip_json_comments(self._read_disk()))
        self.assertNotIn("m1", data)
        self.assertEqual(data["m2"], 2)


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
        mock_gen = mocker.patch("src.python.llm.skeleton.generate_llm_content", return_value=(None, False))

        _gens.generate_global_macro(
            a_indices={},
            us_indices={},
            total_mv=100000,
            total_profit=5000,
            total_cost=0,
            categories={},
        )

        # 验证 _generate_llm_content 被调用，且第 4 个 positional 参数（system_prompt）等于自定义值
        # _generate_llm_content(llm_config, cache_key, cache_ttl, system_prompt, user_prompt, ...)
        call_args = mock_gen.call_args[0]  # positional args
        assert call_args[3] == mock_system, f"预期 system_prompt={mock_system!r}, 实际={call_args[3]!r}"

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
        mock_gen = mocker.patch("src.python.llm.skeleton.generate_llm_content", return_value=(None, False))

        _gens.generate_global_macro(
            a_indices={},
            us_indices={},
            total_mv=100000,
            total_profit=5000,
            total_cost=0,
            categories={},
        )

        call_args = mock_gen.call_args[0]
        # 应该使用代码内置默认值 _SYSTEM_GLOBAL_MACRO
        assert call_args[3] == _SYSTEM_GLOBAL_MACRO, f"预期内置默认值, 实际={call_args[3][:50]!r}"

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
        mock_gen = mocker.patch("src.python.llm.skeleton.generate_llm_content", return_value=(None, False))

        _gens.generate_global_macro(
            a_indices={},
            us_indices={},
            total_mv=100000,
            total_profit=5000,
            total_cost=0,
            categories={},
        )

        call_args = mock_gen.call_args[0]
        assert call_args[3] == _SYSTEM_GLOBAL_MACRO, f"预期内置默认值, 实际={call_args[3][:50]!r}"


class TestLlmSettingsKeyConsistency:
    """验证 llm_settings.json 的键名与 _KNOWN_LLM_SETTINGS_KEYS 一致。"""

    def test_all_keys_tracked(self):
        """llm_settings.json 中不应有未在 _KNOWN_LLM_SETTINGS_KEYS 中登记的键。

        使用 _ABS_LLM_SETTINGS（PROJECT_ROOT 硬路径）绕过 _isolate_sensitive_paths
        的路径重定向，因为本测试是只读的代码-配置文件一致性校验，不依赖运行时配置。
        """
        import json
        from src.python.config import _KNOWN_LLM_SETTINGS_KEYS, _strip_json_comments

        _path = _ABS_LLM_SETTINGS
        if not os.path.exists(_path):
            return  # 无真实配置文件时跳过（CI/裸环境）

        with open(_path, encoding="utf-8") as f:
            raw = f.read()
            llm = json.loads(_strip_json_comments(raw))

        file_keys = set(llm.keys())
        untracked = file_keys - _KNOWN_LLM_SETTINGS_KEYS
        assert not untracked, f"llm_settings.json 中发现 {len(untracked)} 个未登记键名: {sorted(untracked)}"


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
            payload = json.loads(_comments._strip_json_comments(f.read()))
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
            payload = json.loads(_comments._strip_json_comments(f.read()))
        self.assertEqual(payload.get("holdings_dir"), "/safe/value")


class TestValidateReportSectionOrder(unittest.TestCase):
    """_validate_report_section_order 配置校验测试。"""

    def test_no_order_returns_zero(self):
        """report_section_order 未配置 → 0 问题。"""
        n = cfg.validate_config({"holdings_dir": "data"})
        self.assertEqual(n, 0)

    def test_valid_order_returns_zero(self):
        """有效配置 → 0 问题。"""
        n = cfg.validate_config(
            {
                "report_section_order": {
                    "summary": 1,
                    "fund_manager": 6,
                    "global_macro": 12,
                }
            }
        )
        self.assertEqual(n, 0)

    def test_non_dict_order_warns(self):
        """report_section_order 不是 dict → 1 问题。"""
        n = cfg.validate_config({"report_section_order": "invalid"})
        self.assertEqual(n, 1)

    def test_unknown_key_warns(self):
        """未知模块标识 → 1 问题。"""
        n = cfg.validate_config({"report_section_order": {"nonexistent_module": 1}})
        self.assertEqual(n, 1)

    def test_non_integer_value_warns(self):
        """配置值不是整数 → 1 问题。"""
        n = cfg.validate_config({"report_section_order": {"summary": "abc"}})
        self.assertEqual(n, 1)

    def test_negative_value_warns(self):
        """负值序号 → 1 问题。"""
        n = cfg.validate_config({"report_section_order": {"summary": -5}})
        self.assertEqual(n, 1)

    def test_zero_value_warns(self):
        """零值序号 → 1 问题。"""
        n = cfg.validate_config({"report_section_order": {"summary": 0}})
        self.assertEqual(n, 1)

    def test_duplicate_number_warns(self):
        """重复序号 → 1 问题（仅第二次出现时告警）。"""
        n = cfg.validate_config({"report_section_order": {"summary": 1, "fund_manager": 1}})
        self.assertEqual(n, 1)

    def test_llm_usage_in_config_warns(self):
        """llm_usage 出现在配置中 → 1 问题。"""
        n = cfg.validate_config({"report_section_order": {"llm_usage": 1}})
        self.assertEqual(n, 1)

    def test_multiple_issues_accumulate(self):
        """多个问题累加计数。"""
        n = cfg.validate_config(
            {
                "report_section_order": {
                    "unknown_key": 1,
                    "summary": "abc",
                    "fund_manager": -3,
                }
            }
        )
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
                # 路径键：模板与 _DEFAULT_CONFIG 均使用绝对路径（CWD 无关安全），
                # 但测试 fixture（_isolate_sensitive_paths）可能覆写 _DEFAULT_CONFIG
                # 的某个路径键指向 tmp_path，此时模板与 _DEFAULT_CONFIG 值不相等属正常。
                # 只验证两者都是非空字符串即可。
                assert parsed[key], f"模板中的路径键 {key!r} 为空"
                assert isinstance(parsed[key], str), f"模板中的路径键 {key!r} 非字符串"
            else:
                assert parsed[key] == cfg._DEFAULT_CONFIG[key], (
                    f"键 {key!r} 值不匹配:\n  模板: {parsed[key]!r}\n  配置: {cfg._DEFAULT_CONFIG[key]!r}"
                )


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
