"""配置管理模块单元测试 — 异常场景与边界测试。

测试目标：
  - get_config — 缺失/损坏/空文件返回默认值
  - init_config — 初始化创建默认配置
  - set_config — 写入/读取/异常场景（含单键补丁）
  - 合并 LLM 默认值 / del_config / validate_config

兄弟分片：test_config_consistency.py（模板与声明一致性：LLM 设置键/批处理键/报告节顺序/原子写崩溃恢复）、
test_config_feature_gates.py（板层与功能开关访问器：组合进化/候选比较/动作开关/数据沉降/报告组开关）。

运行：
  pytest src/test/unit/config/test_config.py -v
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
        from src.python.config._llm_settings import _merge_llm_defaults

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
        self.assertEqual(merged["debate"]["max_total_tokens_per_report"], 72000)
        self.assertEqual(merged["debate"]["concentration_qa"]["threshold"], 0.20)


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

    def test_legacy_history_analysis_ignored(self):
        """旧配置键 history.analysis 不再迁移，fetch_mode 取默认值。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        legacy = {"history": {"analysis": "off"}}
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(legacy, f)
        result = cfg.get_config()
        hist = result.get("history", {})
        self.assertEqual(hist.get("fetch_mode"), "auto")  # 默认值，不再读取旧键

    def test_fetch_mode_default_is_auto(self):
        """未配置 history 时 fetch_mode 默认 auto。"""
        result = cfg.get_config()
        self.assertEqual(result.get("history", {}).get("fetch_mode"), "auto")

    def test_lookback_days_default_is_90(self):
        """未配置 history 时 lookback_days 默认 90（≥ 回撤分析 MIN_SPAN 60）。"""
        result = cfg.get_config()
        self.assertEqual(result.get("history", {}).get("lookback_days"), 90)

    def test_lookback_days_merge_user_value(self):
        """用户显式配置 history.lookback_days 覆盖默认值。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        user = {"history": {"lookback_days": 120}}
        with open(cfg._config_defaults._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(user, f)
        result = cfg.get_config()
        hist = result.get("history", {})
        self.assertEqual(hist.get("lookback_days"), 120)
        # 覆盖后其余 history 子键默认值仍保留（浅合并不丢默认）
        self.assertEqual(hist.get("fetch_mode"), "auto")


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
        self.assertIn("// 市场新闻", raw)
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
