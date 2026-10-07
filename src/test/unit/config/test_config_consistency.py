"""配置管理模块单元测试 — 模板与声明一致性（config.py 分片）。

测试目标：
  - LLM 设置键/模板与配置文件三方一致（llm_settings 实际路径口径）
  - 默认配置模板一致性（路径型键相对路径 + 注释保留）
  - 报告节顺序 report_section_order 校验 / 批处理 worker 键声明齐全
  - 原子写崩溃恢复（断电/写盘异常后配置文件完整性）

运行：
  pytest src/test/unit/config/test_config_consistency.py -v
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

from .test_config import _ABS_LLM_SETTINGS, _PATH_KEYS_IN_TEMPLATE

pytestmark = [pytest.mark.unit, pytest.mark.unit_config]


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
                    "position_structure": 5,
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
        n = cfg.validate_config({"report_section_order": {"summary": 1, "position_structure": 1}})
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
                    "position_structure": -3,
                }
            }
        )
        self.assertEqual(n, 3)


# ═══════════════════════════════════════════════════════════
#  batch 子键声明完整性（代码引用 ⊆ 默认值）
# ═══════════════════════════════════════════════════════════


class TestBatchWorkerKeysDeclared:
    """代码中 `get_batch_worker_count()` 引用的 batch 子键必须在 `_DEFAULT_CONFIG` 声明。

    历史缺口：`akshare_workers` 被财务指标章与基金重仓 ROE 推演引用，却未进默认值与模板——
    用户无法通过配置调整该域并发，只能吃代码兜底值，而模板一致性用例只校验「模板 ≡ 默认值」，
    对「代码引用 ⊆ 默认值」无覆盖，漏声明不会被任何用例拦住。
    """

    @pytest.mark.unit_config
    def test_referenced_worker_keys_are_declared(self):
        """扫描 src/python 下所有 get_batch_worker_count("<key>") 调用，键必须已声明。"""
        import re
        from pathlib import Path

        declared = set(cfg._config_defaults._DEFAULT_CONFIG["batch"])
        referenced: set[str] = set()
        for path in (Path(PROJECT_ROOT) / "src" / "python").rglob("*.py"):
            referenced |= set(re.findall(r'get_batch_worker_count\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))

        # 防正则失效导致空集假通过：底层至少应有基金/行业取数两处引用
        assert {"fund_workers", "industry_workers"} <= referenced
        undeclared = sorted(referenced - declared)
        assert not undeclared, f"batch 子键被代码引用但未在 _DEFAULT_CONFIG 声明（用户无法配置）: {undeclared}"


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
                    assert type(parsed["cache_ttl"][k]) is type(cfg._DEFAULT_CONFIG["cache_ttl"][k]), (
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


class TestLlmSettingsTemplateConsistency:
    """验证 _get_default_llm_settings_template() 生成的 JSON 模板与 _DEFAULT_LLM_SETTINGS 等效。

    当在 _DEFAULT_LLM_SETTINGS 中新增配置项时，必须在模板字符串中同步添加；
    反之，从模板中移除的键也应在 _DEFAULT_LLM_SETTINGS 中删除。
    本测试通过解析模板并与 _DEFAULT_LLM_SETTINGS 深度比较来检测不一致。
    """

    @pytest.mark.unit_config
    def test_template_equals_default_settings(self):
        """llm_settings 模板 JSON 解析后应与 _DEFAULT_LLM_SETTINGS 深度相等。"""
        import json

        from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS, _get_default_llm_settings_template

        template_str = _get_default_llm_settings_template()
        cleaned = cfg._strip_json_comments(template_str)
        parsed = json.loads(cleaned)

        assert parsed == _DEFAULT_LLM_SETTINGS, (
            f"llm_settings 模板与 _DEFAULT_LLM_SETTINGS 不一致\n"
            f"模板独有键: {parsed.keys() - _DEFAULT_LLM_SETTINGS.keys()}\n"
            f"默认独有键: {_DEFAULT_LLM_SETTINGS.keys() - parsed.keys()}\n"
            f"值差异: {[k for k in parsed if parsed.get(k) != _DEFAULT_LLM_SETTINGS.get(k)]}"
        )

    @pytest.mark.unit_config
    def test_module_labels_derived_from_registry(self):
        """模块显示名取自中央注册表，不得另存副本。

        历史缺陷：模板注释里的模块名是与注册表并存的第三份硬编码 —— 注册表改名
        或新增模块时它不跟着动，生成的模板注释与实际模块名静默不一致。
        """
        from src.python.config import _llm_settings_defaults as d
        from src.python.core.registry import get_llm_module_names, get_known_enabled_llm_keys

        assert d._MODULE_LABELS == get_llm_module_names(), (
            "模板模块名与注册表不一致：模板独有 "
            f"{d._MODULE_LABELS.keys() - get_llm_module_names().keys()}，"
            f"注册表独有 {get_llm_module_names().keys() - d._MODULE_LABELS.keys()}"
        )
        # enabled_llm 的每个子键都必须能在注册表里查到显示名（否则模板注释退化为裸键名）
        missing = get_known_enabled_llm_keys() - d._MODULE_LABELS.keys()
        assert not missing, f"enabled_llm 子键在注册表中无显示名: {sorted(missing)}"

    @pytest.mark.unit_config
    def test_template_module_titles_match_registry(self):
        """模板中每个「<显示名> — <模块>」区块标题的显示名须与注册表一致（渲染结果层锁定）。"""
        import re

        from src.python.config._llm_settings_defaults import _DEFAULT_LLM_SETTINGS, _get_default_llm_settings_template
        from src.python.core.registry import get_llm_module_name

        template = _get_default_llm_settings_template()
        titles = {
            module: label for label, module in re.findall(r"^\s*//\s*(.+?)\s+—\s+([a-z_]+)\s*$", template, re.MULTILINE)
        }
        assert titles, "模板中未找到任何模块区块标题，正则或模板格式已变"

        for module, label in titles.items():
            assert label == get_llm_module_name(module), (
                f"模板区块标题 {label!r} 与注册表 {get_llm_module_name(module)!r} 不一致（模块 {module}）"
            )
        # 每个 enabled_llm 子键都应有对应的配置区块
        assert _DEFAULT_LLM_SETTINGS["enabled_llm"].keys() <= titles.keys(), (
            f"以下模块在模板中缺少配置区块: {sorted(_DEFAULT_LLM_SETTINGS['enabled_llm'].keys() - titles.keys())}"
        )


class TestRepoConfigSectionOrderContract:
    """仓库自带 config 的 report_section_order 与章节注册表契约。

    测试隔离会把 config 重定向到临时目录，仓库出厂 config 的键集合漂移
    因此不会被日常用例发现——本类直接读仓库文件兜底。
    """

    def test_repo_config_keys_match_registry(self):
        """键集合双向一致（不收 llm_usage、无未知键），且各键序号与出厂序同序。"""
        from src.python.core.registry import get_report_section_keys, get_report_section_number

        path = os.path.join(PROJECT_ROOT, "data", "config", "config.json")
        with open(path, encoding="utf-8") as f:
            data = json.loads(_comments._strip_json_comments(f.read()))
        order = data.get("report_section_order") or {}
        assert set(order) == get_report_section_keys() - {"llm_usage"}
        for key, num in order.items():
            expected = get_report_section_number(key)
            assert num == expected, f"{key}={num} 偏离出厂序 {expected}（config 与注册表须同序）"


class TestReportSectionOrderAutoClean:
    """report_section_order 未知模块标识的校验期自动清理。"""

    def test_unknown_key_counted_and_removed(self):
        """未知模块标识：计 1 问题并从内存配置剔除（防残留键造成排序错位预期）。"""
        config = {"report_section_order": {"summary": 1, "nonexistent_module": 2}}
        n = cfg.validate_config(config)
        assert n == 1
        assert "nonexistent_module" not in config["report_section_order"]
        assert "summary" in config["report_section_order"]
