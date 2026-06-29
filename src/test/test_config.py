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


class TestGetConfig(unittest.TestCase):
    """get_config 的异常场景测试。"""

    def setUp(self):
        # 备份原始 _CONFIG_FILE，用临时目录替代
        self._orig_config = cfg._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        cfg._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def test_missing_file_returns_defaults(self):
        """配置文件不存在 → 返回默认值。"""
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "data/holdings")
        self.assertEqual(result["holdings_filename"], "个人投资持仓信息.xlsx")
        self.assertEqual(result.get("output_dir"), "reports")
        self.assertEqual(result.get("news_top_count"), 100)
        self.assertIn("cache_ttl", result)
        self.assertIn("preferred_provider", result)

    def test_corrupted_json_returns_defaults(self):
        """配置文件损坏 → 返回默认值。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        with open(cfg._CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("{invalid json!!!")
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "data/holdings")

    def test_empty_file_returns_defaults(self):
        """配置文件为空 → 返回默认值。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        with open(cfg._CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("")
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "data/holdings")

    def test_partial_config_merge(self):
        """部分配置 → 未配置项用默认值补齐。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        partial = {"holdings_dir": "/custom/path"}
        with open(cfg._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(partial, f)
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "/custom/path")
        self.assertEqual(result["holdings_filename"], "个人投资持仓信息.xlsx")
        self.assertEqual(result.get("output_dir"), "reports")

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
        with open(cfg._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "/a")
        self.assertEqual(result["news_top_count"], 50)


class TestInitConfig(unittest.TestCase):
    """init_config 的边界场景测试。"""

    def setUp(self):
        self._orig_config = cfg._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        cfg._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def test_init_creates_default_config(self):
        """初始化 → 创建包含默认值的配置文件。"""
        self.assertFalse(os.path.exists(cfg._CONFIG_FILE))
        cfg.init_config()
        self.assertTrue(os.path.exists(cfg._CONFIG_FILE))
        with open(cfg._CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["holdings_dir"], "data/holdings")

    def test_init_does_not_overwrite_existing(self):
        """配置文件已存在 → 不覆盖。"""
        os.makedirs(self.tmp.name, exist_ok=True)
        existing = {"holdings_dir": "/manual"}
        with open(cfg._CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f)
        cfg.init_config()
        with open(cfg._CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["holdings_dir"], "/manual")

    def test_init_nonexistent_dir(self):
        """配置目录不存在 → 创建后写入。"""
        non_exist = os.path.join(self.tmp.name, "sub", "config")
        cfg._CONFIG_FILE = os.path.join(non_exist, "config.json")
        cfg.init_config()
        self.assertTrue(os.path.exists(cfg._CONFIG_FILE))


class TestSetConfig(unittest.TestCase):
    """set_config 的异常场景测试。"""

    def setUp(self):
        self._orig_config = cfg._CONFIG_FILE
        self.tmp = tempfile.TemporaryDirectory()
        cfg._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")

    def tearDown(self):
        cfg._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

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
        self.assertEqual(result.get("output_dir"), "reports")

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
        def _mock_open(*args, **kwargs):
            mode = args[1] if len(args) > 1 else kwargs.get("mode", "r")
            if "w" in mode or "a" in mode:
                raise PermissionError("denied")
            return _real_open(*args, **kwargs)
        with patch("builtins.open", side_effect=_mock_open):
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
