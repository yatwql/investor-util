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

import json
import os
import tempfile
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.python.tui.status_line import build_status_line, reset_status_memo
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
        """菜单项应为 18 个（含受开关约束的 [T] 系统自检；[C]/[F]/[O] 已聚合到 [D] 子菜单）。"""
        self.assertEqual(len(MENU_ITEMS), 18)

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
        key, label, cb, is_exit = MENU_ITEMS[17]
        self.assertEqual(key, "X")
        self.assertIn("退出", label)
        self.assertIsNone(cb)
        self.assertTrue(is_exit)

    def test_view_logs_item(self) -> None:
        """日志查看项在退出前（快捷键 V）。"""
        key, label, cb, is_exit = MENU_ITEMS[14]
        self.assertEqual(key, "V")
        self.assertIn("运行日志", label)
        self.assertIsNone(cb)
        self.assertFalse(is_exit)

    def test_health_history_item(self) -> None:
        """健康历史项在日志查看后（快捷键 H）。"""
        key, label, cb, is_exit = MENU_ITEMS[15]
        self.assertEqual(key, "H")
        self.assertIn("健康历史", label)
        self.assertIsNone(cb)
        self.assertFalse(is_exit)

    def test_config_dir_info_item(self) -> None:
        """配置目录信息项在 What-if 后（第 5 项，快捷键 D）。"""
        key, label, cb, is_exit = MENU_ITEMS[4]
        self.assertEqual(key, "D")
        self.assertIn("配置目录信息", label)
        self.assertIsNone(cb)
        self.assertFalse(is_exit)

    def test_doctor_item(self) -> None:
        """系统自检项在健康历史后、退出前（快捷键 T）。"""
        key, label, cb, is_exit = MENU_ITEMS[16]
        self.assertEqual(key, "T")
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
        self.assertEqual(index_by_key("X"), 17)

    def test_find_D(self) -> None:
        self.assertEqual(index_by_key("D"), 4)

    def test_find_T(self) -> None:
        self.assertEqual(index_by_key("T"), 16)

    def test_find_V(self) -> None:
        self.assertEqual(index_by_key("V"), 14)

    def test_find_H(self) -> None:
        self.assertEqual(index_by_key("H"), 15)

    def test_find_nonexistent(self) -> None:
        self.assertIsNone(index_by_key("Z"))

    def test_find_lowercase(self) -> None:
        """小写字母未实现——必须大写。"""
        self.assertIsNone(index_by_key("e"))

    def test_find_number(self) -> None:
        self.assertEqual(index_by_key("1"), 5)

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
        """过滤后仅剩标准模块，不含辩论三模块。

        期望集合由「注册表全集 ⊖ 菜单隐藏集」结构导出（不写死逐条清单）：
        新增模块时本用例不需改，仅当**隐藏集**变化才应重审。
        """
        from src.python.core.registry import get_llm_module_names
        from src.python.tui.tui_menu import LLM_MENU_HIDDEN_KEYS, filter_menu_llm_modules

        module_names = get_llm_module_names()
        filtered = filter_menu_llm_modules(module_names)
        self.assertEqual(set(filtered.keys()), set(module_names) - set(LLM_MENU_HIDDEN_KEYS))
        for hidden in LLM_MENU_HIDDEN_KEYS:
            self.assertNotIn(hidden, filtered)
            self.assertIn(hidden, module_names, "隐藏集成员必须仍在注册表内（缓存 TTL 依赖）")

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
    """受功能开关约束的菜单项（[T] 系统自检）。

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
        assert "T" not in {item[0] for item in tm.MENU_ITEMS}

    def test_doctor_item_visible_when_flag_on(self):
        import src.python.tui.tui_menu as tm

        self._apply(enabled=True)
        assert "T" in {item[0] for item in tm.MENU_ITEMS}

    def test_doctor_item_visible_under_defaults(self):
        """默认配置下 [T] 即在菜单里（系统自检已转正为默认开启）。

        上面两条都用 patch 覆盖取值，测不出默认值本身——默认值若改回关闭，
        它们仍全绿，而用户打开的菜单里会少一项。
        """
        import src.python.tui.tui_menu as tm

        tm._apply_feature_gates()

        assert "T" in {item[0] for item in tm.MENU_ITEMS}

    def test_config_dir_info_unaffected_by_doctor_gate(self):
        """开关关闭只裁剪 [T] 自检，[D] 配置目录信息（无门控）仍在菜单中。"""
        import src.python.tui.tui_menu as tm

        self._apply(enabled=False)
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


class TestLlmStatusRendering:
    """_show_llm_config_status — 消费 llm_status 单源的三态终端渲染。"""

    @staticmethod
    def _render() -> str:
        import src.python.tui.tui_menu as tm

        buf = StringIO()
        with patch("sys.stdout", buf):
            tm._show_llm_config_status()
        return buf.getvalue()

    def test_unconfigured_line(self):
        with patch("src.python.config.get_llm_config", return_value=None):
            assert "未配置" in self._render()

    def test_flat_configured_line(self):
        with patch("src.python.config.get_llm_config", return_value={"api_key": "k", "provider": "claude"}):
            out = self._render()
        assert "已配置" in out
        assert "provider=claude" in out
        assert "模型路由" in out

    def test_multi_chain_render(self):
        cfg = {"_provider_list": [{"name": "alpha", "provider": "claude", "priority": 10}]}
        with patch("src.python.config.get_llm_config", return_value=cfg):
            out = self._render()
        assert "多链服务 (1 provider)" in out
        assert "alpha" in out


class TestStatusLine(unittest.TestCase):
    """页头状态行：五项取数、逐项降级、TTL 记忆化与页头接线。"""

    def setUp(self) -> None:
        reset_status_memo()

    def tearDown(self) -> None:
        reset_status_memo()

    # ── 分项取数 ──

    def test_last_report_formats_timestamp(self) -> None:
        """perf 历史末条时间戳 → MM-DD HH:MM。"""
        with patch(
            "src.python.core.perf.load_history",
            return_value=[{"timestamp": "2026-10-07T09:55:00"}],
        ):
            from src.python.tui.status_line import _last_report_part

            self.assertEqual(_last_report_part(), "上次报告 10-07 09:55")

    def test_last_report_interrupted_marker(self) -> None:
        """末条 status=interrupted → 时间戳带「（已中断）」，下次启动不误判为成功。"""
        with patch(
            "src.python.core.perf.load_history",
            return_value=[{"timestamp": "2026-10-07T09:55:00", "status": "interrupted"}],
        ):
            from src.python.tui.status_line import _last_report_part

            self.assertEqual(_last_report_part(), "上次报告 10-07 09:55（已中断）")

    def test_last_report_empty_and_broken(self) -> None:
        """无历史 / 读取异常 → 逐项降级为 —。"""
        from src.python.tui.status_line import _last_report_part

        with patch("src.python.core.perf.load_history", return_value=[]):
            self.assertEqual(_last_report_part(), "上次报告 —")
        with patch("src.python.core.perf.load_history", side_effect=OSError("损坏")):
            self.assertEqual(_last_report_part(), "上次报告 —")

    def test_cache_expired_from_stats(self) -> None:
        """缓存统计 expired 计数；异常降级为 —。"""
        from src.python.tui.status_line import _cache_expired_part

        with patch(
            "src.python.cache.operations.get_cache_stats",
            return_value=SimpleNamespace(expired=3),
        ):
            self.assertEqual(_cache_expired_part(), "缓存过期 3")
        with patch(
            "src.python.cache.operations.get_cache_stats",
            side_effect=OSError("目录不可读"),
        ):
            self.assertEqual(_cache_expired_part(), "缓存过期 —")

    def test_freshness_latest_from_price_cache(self) -> None:
        """最新价格缓存的 price_date → 数据日期 + 自然日龄（纯本地，不触交易日历）。"""
        from datetime import datetime

        today = datetime.now().date()
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "price_demo_v1.json"), "w", encoding="utf-8") as f:
                json.dump({"_data": {"price": 1.23, "price_date": today.isoformat()}}, f)
            with (
                patch("src.python.cache.get_cache_dir", return_value=tmp),
                patch(
                    "src.python.cache.get",
                    return_value={"price": 1.23, "price_date": today.isoformat()},
                ),
            ):
                from src.python.tui.status_line import _freshness_part

                self.assertEqual(_freshness_part(), f"新鲜度 {today:%m-%d}（0天）")

    def test_freshness_no_price_cache(self) -> None:
        """无价格缓存 → 新鲜度 —。"""
        with tempfile.TemporaryDirectory() as tmp:
            with patch("src.python.cache.get_cache_dir", return_value=tmp):
                from src.python.tui.status_line import _freshness_part

                self.assertEqual(_freshness_part(), "新鲜度 —")

    def test_freshness_source_failure(self) -> None:
        """取数异常 → 逐项降级为 —。"""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "price_demo_v1.json"), "w", encoding="utf-8") as f:
                json.dump({"_data": {"price": 1.23, "price_date": "2026-10-07"}}, f)
            with (
                patch("src.python.cache.get_cache_dir", return_value=tmp),
                patch("src.python.cache.get", side_effect=OSError("读档失败")),
            ):
                from src.python.tui.status_line import _freshness_part

                self.assertEqual(_freshness_part(), "新鲜度 —")

    def test_degraded_count_from_health_history(self) -> None:
        """健康历史末条 fail_count → 降级源数；无记录 → —。"""
        from src.python.tui.status_line import _degraded_part

        with patch(
            "src.python.core.perf.summarize_health_history",
            return_value=[{"fail_count": 2}],
        ):
            self.assertEqual(_degraded_part(), "降级源 2")
        with patch("src.python.core.perf.summarize_health_history", return_value=[]):
            self.assertEqual(_degraded_part(), "降级源 —")
        with patch(
            "src.python.core.perf.summarize_health_history",
            side_effect=OSError("读档失败"),
        ):
            self.assertEqual(_degraded_part(), "降级源 —")

    def test_llm_status_dot(self) -> None:
        """LLM 状态点：已配置 ● / 未配置 ○ / 异常 —。"""
        from src.python.tui.status_line import _llm_part

        with patch(
            "src.python.core.system_info.llm_status",
            return_value={"configured": True},
        ):
            self.assertEqual(_llm_part(), "LLM ●")
        with patch(
            "src.python.core.system_info.llm_status",
            return_value={"configured": False},
        ):
            self.assertEqual(_llm_part(), "LLM ○")
        with patch(
            "src.python.core.system_info.llm_status",
            side_effect=RuntimeError("配置故障"),
        ):
            self.assertEqual(_llm_part(), "LLM —")

    # ── 整行组装 ──

    def test_full_line_format_with_menu_hint(self) -> None:
        """五项拼接为单行并携带详情菜单指引。"""
        with (
            patch("src.python.core.perf.load_history", return_value=[]),
            patch(
                "src.python.cache.operations.get_cache_stats",
                return_value=SimpleNamespace(expired=5),
            ),
            patch("src.python.core.perf.summarize_health_history", return_value=[]),
            patch(
                "src.python.core.system_info.llm_status",
                return_value={"configured": True},
            ),
            tempfile.TemporaryDirectory() as tmp,
            patch("src.python.cache.get_cache_dir", return_value=tmp),
        ):
            line = build_status_line()
        self.assertTrue(line.startswith("状态 │ "))
        self.assertIn("上次报告 —", line)
        self.assertIn("缓存过期 5", line)
        self.assertIn("新鲜度 —", line)
        self.assertIn("降级源 —", line)
        self.assertIn("LLM ●", line)
        self.assertIn("〔详情 [4][H][S]〕", line)

    def test_all_sources_fail_degrades_per_item(self) -> None:
        """五路取数全挂 → 逐项显示 —，不向调用方抛出。"""
        boom = side_effect = RuntimeError("全挂")
        with (
            patch("src.python.core.perf.load_history", side_effect=boom),
            patch("src.python.cache.operations.get_cache_stats", side_effect=side_effect),
            patch("src.python.cache.get_cache_dir", side_effect=side_effect),
            patch("src.python.core.perf.summarize_health_history", side_effect=side_effect),
            patch("src.python.core.system_info.llm_status", side_effect=side_effect),
        ):
            line = build_status_line()
        for label in ("上次报告", "缓存过期", "新鲜度", "降级源", "LLM"):
            self.assertIn(f"{label} —", line)

    def test_memo_ttl_reuses_then_refreshes(self) -> None:
        """TTL 内复用记忆（重活不重取），过期后重新取数。"""
        mock_stats = MagicMock(return_value=SimpleNamespace(expired=1))
        with patch("src.python.cache.operations.get_cache_stats", mock_stats):
            build_status_line(now=1_000.0)
            build_status_line(now=1_020.0)  # TTL 内 → 复用
            self.assertEqual(mock_stats.call_count, 1)
            build_status_line(now=1_100.0)  # 超过 45s → 重取
            self.assertEqual(mock_stats.call_count, 2)

    def test_print_header_renders_status_line(self) -> None:
        """print_header 输出常驻状态行（页头接线）。"""
        with patch(
            "src.python.tui.status_line.build_status_line",
            return_value="状态 │ 单测行",
        ):
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                print_header()
                out = mock_out.getvalue()
        self.assertIn("状态 │ 单测行", out)


if __name__ == "__main__":
    unittest.main()
