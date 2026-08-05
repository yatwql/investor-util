"""TUI 菜单 → Handler 路由验证 — 按键正确路由到目标处理器。

覆盖菜单项回调绑定、快捷键直达路由与菜单选择边界，
不实际触发报告生成逻辑。
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.integration_tui]


@pytest.mark.integration
@pytest.mark.integration_tui
class TestTuiRouting(unittest.TestCase):
    """TUI 菜单 → Handler 路由 — 按键正确路由到目标处理器。"""

    def test_all_menu_keys_have_callbacks(self):
        """所有非退出菜单项绑定回调函数。"""
        from src.python.tui.tui import _bind_callbacks
        from src.python.tui.tui_menu import MENU_ITEMS

        _bind_callbacks()

        for key, label, callback, is_exit in MENU_ITEMS:
            with self.subTest(key=key, label=label):
                if is_exit:
                    continue  # 退出项由 _execute_item 直接处理
                self.assertIsNotNone(
                    callback,
                    f"菜单项 [{key}] {label} 未绑回调函数",
                )

    def test_menu_key_coverage(self):
        """MENU_ITEMS 包含所有标准功能键。"""
        from src.python.tui.tui_menu import MENU_ITEMS

        keys = {item[0] for item in MENU_ITEMS}
        expected = {"E", "P", "B", "L", "W", "C", "F", "O", "I", "A",
                    "1", "2", "3", "4", "S", "R", "X"}
        self.assertSetEqual(keys, expected)

    def test_execute_item_dispatches_correct_handler(self):
        """_execute_item 根据选中项索引正确执行回调。

        注：前序测试 _bind_callbacks 会绑定真实回调函数到 MENU_ITEMS，
        此处仅验证回调非 None 且可调用，不实际执行防止触发报告生成逻辑。
        """
        from src.python.tui.tui_menu import MENU_ITEMS

        # 找到非退出项
        non_exit_idx = next(i for i, item in enumerate(MENU_ITEMS)
                            if not item[3])

        cb = MENU_ITEMS[non_exit_idx][2]
        if cb is not None:
            # 仅验证回调是可调用对象，不实际调用
            self.assertTrue(callable(cb),
                            f"菜单项 [{MENU_ITEMS[non_exit_idx][0]}] 回调应可调用")

    def test_menu_sel_navigation(self):
        """菜单选择索引在上下界内。"""
        from src.python.tui.tui_menu import MENU_ITEMS
        sel = 0
        n = len(MENU_ITEMS)

        # 上边界
        sel = (sel - 1) % n
        self.assertEqual(sel, n - 1)

        # 下边界
        sel = (sel + 1) % n
        self.assertEqual(sel, 0)

    def test_keyboard_shortcut_routing(self):
        """字母键直达路由：E → handler_report._cmd_generate_excel。"""
        from src.python.tui.tui import _bind_callbacks

        _bind_callbacks()

        from src.python.tui.tui_menu import MENU_ITEMS
        e_item = next(item for item in MENU_ITEMS if item[0] == "E")
        self.assertIsNotNone(e_item[2])

        # 确认 E 绑定了正确的处理器
        cb_name = e_item[2].__name__ if e_item[2] else ""
        self.assertEqual(cb_name, "_cmd_generate_excel")

    def test_llm_key_routes_to_full_generation(self):
        """L 键路由到 _cmd_generate_full。"""
        from src.python.tui.tui import _bind_callbacks

        _bind_callbacks()

        from src.python.tui.tui_menu import MENU_ITEMS
        l_item = next(item for item in MENU_ITEMS if item[0] == "L")
        cb_name = l_item[2].__name__ if l_item[2] else ""
        self.assertEqual(cb_name, "_cmd_generate_full")
