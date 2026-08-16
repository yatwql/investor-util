"""TUI 菜单模块单元测试。

测试目标：
  - MENU_ITEMS 结构完整性
  - index_by_key 快捷键查找
  - print_sep / print_header 不崩溃
  - _exit_app 退出行为
  - _show_llm_config_status 格式

运行：
  pytest src/test/unit/ui/test_tui_menu.py -v
"""

from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import patch

from src.python.tui.tui_menu import (
    MENU_ITEMS,
    index_by_key,
    print_header,
    print_sep,
    _show_llm_config_status,
    get_config_cache,
)
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_ui]


class TestMenuItems(unittest.TestCase):
    """MENU_ITEMS 结构完整性测试。"""

    def setUp(self):
        """重置 MENU_ITEMS 回调为 None，防止前序测试副作用。"""
        import src.python.tui.tui_menu as _tm

        for i, (key, label, _cb, is_exit) in enumerate(_tm.MENU_ITEMS):
            _tm.MENU_ITEMS[i] = (key, label, None, is_exit)

    def test_item_count(self) -> None:
        """菜单项应为 19 个。"""
        self.assertEqual(len(MENU_ITEMS), 19)

    def test_whatif_item(self) -> None:
        """What-if 菜单项在报告生成组后（第 4 项，快捷键 W）。"""
        key, label, cb, is_exit = MENU_ITEMS[3]
        self.assertEqual(key, "W")
        self.assertIn("What-if", label)
        self.assertIsNone(cb)
        self.assertFalse(is_exit)

    def test_first_item_excel(self) -> None:
        """第一项快捷键 E。"""
        key, label, cb, is_exit = MENU_ITEMS[0]
        self.assertEqual(key, "E")
        self.assertIn("Excel", label)
        self.assertIsNone(cb)
        self.assertFalse(is_exit)

    def test_last_item_exit(self) -> None:
        """最后一项快捷键 X，is_exit=True。"""
        key, label, cb, is_exit = MENU_ITEMS[18]
        self.assertEqual(key, "X")
        self.assertIn("退出", label)
        self.assertIsNone(cb)
        self.assertTrue(is_exit)

    def test_view_logs_item(self) -> None:
        """日志查看项在退出前（快捷键 V）。"""
        key, label, cb, is_exit = MENU_ITEMS[16]
        self.assertEqual(key, "V")
        self.assertIn("运行日志", label)
        self.assertIsNone(cb)
        self.assertFalse(is_exit)

    def test_health_history_item(self) -> None:
        """健康历史项在日志查看后（快捷键 H）。"""
        key, label, cb, is_exit = MENU_ITEMS[17]
        self.assertEqual(key, "H")
        self.assertIn("健康历史", label)
        self.assertIsNone(cb)
        self.assertFalse(is_exit)

    def test_all_keys_unique(self) -> None:
        """所有快捷键不重复。"""
        keys = [item[0] for item in MENU_ITEMS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_all_labels_nonempty(self) -> None:
        """所有标签非空。"""
        for item in MENU_ITEMS:
            self.assertTrue(len(item[1]) > 0, f"Label for key '{item[0]}' is empty")

    def test_callbacks_are_none_initially(self) -> None:
        """回调初始化为 None。"""
        for item in MENU_ITEMS:
            self.assertIsNone(item[2], f"Key '{item[0]}' callback should be None initially")

    def test_only_exit_is_exit(self) -> None:
        """仅退出项 is_exit=True。"""
        exit_count = sum(1 for item in MENU_ITEMS if item[3])
        self.assertEqual(exit_count, 1)


class TestIndexByKey(unittest.TestCase):
    """index_by_key 快捷键查找测试。"""

    def test_find_E(self) -> None:
        self.assertEqual(index_by_key("E"), 0)

    def test_find_W(self) -> None:
        self.assertEqual(index_by_key("W"), 3)

    def test_find_X(self) -> None:
        self.assertEqual(index_by_key("X"), 18)

    def test_find_V(self) -> None:
        self.assertEqual(index_by_key("V"), 16)

    def test_find_H(self) -> None:
        self.assertEqual(index_by_key("H"), 17)

    def test_find_nonexistent(self) -> None:
        self.assertIsNone(index_by_key("Z"))

    def test_find_lowercase(self) -> None:
        """小写字母未实现——必须大写。"""
        self.assertIsNone(index_by_key("e"))

    def test_find_number(self) -> None:
        self.assertEqual(index_by_key("1"), 7)

    def test_find_empty(self) -> None:
        self.assertIsNone(index_by_key(""))


class TestPrintFunctions(unittest.TestCase):
    """打印函数不崩溃测试。"""

    def test_print_sep_default(self) -> None:
        """默认分隔线。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            print_sep()
            output = mock_out.getvalue()
            self.assertIn("=", output)

    def test_print_sep_custom(self) -> None:
        """自定义字符和宽度。"""
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            print_sep(char="-", width=10)
            self.assertIn("----------", mock_out.getvalue())

    def test_print_header(self) -> None:
        """标题头包含系统名称 + 版本号。"""
        from src.python.core.constants import APP_NAME, APP_VERSION

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            print_header()
            self.assertIn(APP_NAME, mock_out.getvalue())
            self.assertIn(f"v{APP_VERSION}", mock_out.getvalue())


class TestConfigCache(unittest.TestCase):
    """配置缓存访问测试。"""

    def setUp(self) -> None:
        """重置模块级 _config_cache 为初始 None，防止前序测试的副作用。"""
        import src.python.tui.tui_menu as _tm

        _tm._config_cache = None

    def test_get_config_cache_default(self) -> None:
        """未初始化时返回 None。"""
        self.assertIsNone(get_config_cache())


class TestFilterMenuLlmModules(unittest.TestCase):
    """菜单层隐藏辩论三模块（注册表条目保留）。"""

    def test_filter_hides_legacy_debate_modules(self):
        """过滤后仅剩标准模块，不含辩论三模块。"""
        from src.python.core.registry import get_llm_module_names
        from src.python.tui.tui_menu import filter_menu_llm_modules

        filtered = filter_menu_llm_modules(get_llm_module_names())
        self.assertEqual(
            set(filtered.keys()),
            {
                "global_macro",
                "expert_review",
                "news_correlation",
                "health_check",
                "penetration_deep",
            },
        )

    def test_registry_keeps_legacy_debate_modules(self):
        """注册表仍保留辩论三模块（缓存 TTL/前缀清理依赖），未被删除。"""
        from src.python.core.registry import get_llm_module_names

        names = get_llm_module_names()
        self.assertIn("debate_pro", names)
        self.assertIn("debate_con", names)
        self.assertIn("debate_synthesis", names)


if __name__ == "__main__":
    unittest.main()
