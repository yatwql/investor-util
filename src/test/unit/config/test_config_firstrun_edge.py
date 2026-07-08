"""首次运行引导测试 — 配置缺失时的引导行为。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/config/test_config_firstrun_edge.py -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_config, pytest.mark.edge]


@pytest.mark.edge
class TestFirstRunGuidance(unittest.TestCase):
    """配置缺失时的引导行为测试。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig_config = None

    def tearDown(self):
        if self._orig_config is not None:
            import src.python.config as cfg
            cfg._CONFIG_FILE = self._orig_config
        self.tmp.cleanup()

    def test_missing_config_shows_guidance(self):
        """首次启动配置不存在 → 自动初始化并提示。"""
        import src.python.config as cfg
        self._orig_config = cfg._CONFIG_FILE
        cfg._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")
        cfg._clear_config_cache()

        # 配置不存在时 get_config 返回默认值不崩溃
        result = cfg.get_config()
        self.assertEqual(result["holdings_dir"], "data/holdings")
        self.assertEqual(result["output_dir"], "reports")

    def test_missing_config_dir_auto_created(self):
        """配置目录不存在 → init_config 自动创建。"""
        import src.python.config as cfg
        nested = os.path.join(self.tmp.name, "sub", "config")
        cfg._CONFIG_FILE = os.path.join(nested, "config.json")
        self.assertFalse(os.path.exists(nested))
        cfg.init_config()
        self.assertTrue(os.path.exists(cfg._CONFIG_FILE))

    def test_friendly_warning_on_corrupted_config(self):
        """损坏的配置 → 输出警告并用默认值。"""
        import src.python.config as cfg
        self._orig_config = cfg._CONFIG_FILE
        cfg._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")
        with open(cfg._CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write("{invalid}")
        cfg._clear_config_cache()
        with patch("logging.Logger.warning") as mock_warn:
            result = cfg.get_config()
            self.assertEqual(result["holdings_dir"], "data/holdings")
            mock_warn.assert_called()
            warning_text = str(mock_warn.call_args[0][0])
            self.assertTrue(
                "配置" in warning_text or "config" in warning_text.lower(),
                f"警告消息应提及配置: {warning_text}",
            )

    def test_first_run_menu_options_available(self):
        """首次运行时菜单 [C]/[F] 配置选项应可用。"""
        import src.python.config as cfg
        self._orig_config = cfg._CONFIG_FILE
        cfg._CONFIG_FILE = os.path.join(self.tmp.name, "config.json")
        cfg._clear_config_cache()
        result = cfg.get_config()
        self.assertIsNotNone(result.get("holdings_dir"))
        self.assertIsNotNone(result.get("output_dir"))
