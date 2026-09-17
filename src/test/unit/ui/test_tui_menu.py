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
        """菜单项应为 20 个（含受开关约束的 [D] 系统自检）。"""
        self.assertEqual(len(MENU_ITEMS), 20)

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
        key, label, cb, is_exit = MENU_ITEMS[19]
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

    def test_doctor_item(self) -> None:
        """系统自检项在健康历史后、退出前（快捷键 D）。"""
        key, label, cb, is_exit = MENU_ITEMS[18]
        self.assertEqual(key, "D")
        self.assertIn("系统自检", label)
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
        self.assertEqual(index_by_key("X"), 19)

    def test_find_D(self) -> None:
        self.assertEqual(index_by_key("D"), 18)

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


@pytest.mark.unit
@pytest.mark.unit_ui
class TestFeatureGatedMenuItems:
    """受功能开关约束的菜单项（[D] 系统自检）。

    `_apply_feature_gates` 就裁剪 `MENU_ITEMS`，故每个用例前后都必须快照/还原——
    否则会污染同进程内其它测试对菜单项数量的断言。
    """

    @pytest.fixture(autouse=True)
    def _restore_menu(self):
        import src.python.tui.tui_menu as tm

        snapshot = list(tm.MENU_ITEMS)
        yield
        tm.MENU_ITEMS[:] = snapshot

    def _apply(self, enabled: bool):
        import src.python.tui.tui_menu as tm

        with patch("src.python.config.features.is_feature_enabled", return_value=enabled):
            tm._apply_feature_gates()

    def test_gated_keys_are_registered_in_menu(self):
        """门控表里的键必须真实存在于菜单——否则开关写了也没人看得见。"""
        import src.python.tui.tui_menu as tm

        keys = {item[0] for item in tm.MENU_ITEMS}
        assert set(tm.FEATURE_GATED_ITEMS) <= keys

    def test_gated_flag_is_registered_feature(self):
        """门控开关必须是注册表中已声明的功能开关（防拼写错误静默失效）。"""
        import src.python.tui.tui_menu as tm
        from src.python.config.features import FEATURE_FLAGS

        for flag in tm.FEATURE_GATED_ITEMS.values():
            assert flag in FEATURE_FLAGS

    def test_doctor_item_hidden_when_flag_off(self):
        import src.python.tui.tui_menu as tm

        self._apply(enabled=False)
        assert "D" not in {item[0] for item in tm.MENU_ITEMS}

    def test_doctor_item_visible_when_flag_on(self):
        import src.python.tui.tui_menu as tm

        self._apply(enabled=True)
        assert "D" in {item[0] for item in tm.MENU_ITEMS}

    def test_doctor_item_visible_under_defaults(self):
        """默认配置下 [D] 即在菜单里（系统自检已转正为默认开启）。

        上面两条都用 patch 覆盖取值，测不出默认值本身——默认值若改回关闭，
        它们仍全绿，而用户打开的菜单里会少一项。
        """
        import src.python.tui.tui_menu as tm

        tm._apply_feature_gates()

        assert "D" in {item[0] for item in tm.MENU_ITEMS}

    def test_callback_binding_survives_gating(self):
        """裁剪后其余项的回调绑定不受影响（索引与渲染一致）。"""
        import src.python.tui.tui_menu as tm

        self._apply(enabled=False)
        keys = [item[0] for item in tm.MENU_ITEMS]
        assert keys[-1] == "X"
        assert len(keys) == len(set(keys))

    def test_gating_is_idempotent(self):
        import src.python.tui.tui_menu as tm

        self._apply(enabled=False)
        first = list(tm.MENU_ITEMS)
        self._apply(enabled=False)
        assert tm.MENU_ITEMS == first


if __name__ == "__main__":
    unittest.main()
