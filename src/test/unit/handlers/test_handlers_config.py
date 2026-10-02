"""测试 handlers_config 的 LLM 设置读写辅助函数与配置面板渲染。

面板渲染部分锁定「盒线边框四边对齐」这条不变式——补白按显示宽度而非码点数。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.python.tui.text_layout import display_width

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestReadLlmSettings:
    """_read_llm_settings: JSON 注释支持 + 文件不存在处理。"""

    @patch("src.python.config._strip_json_comments")
    @patch("src.python.tui.handlers_config.open")
    @patch("src.python.tui.handlers_config.json.loads")
    def test_normal_read(self, mock_json_loads, mock_open, mock_strip):
        """正常读取带注释的 JSON。"""
        mock_strip.return_value = '{"enabled_llm": {"news_correlation": true}}'
        mock_json_loads.return_value = {"enabled_llm": {"news_correlation": True}}
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "raw content"
        mock_open.return_value = mock_file

        from src.python.tui.handlers_config import _read_llm_settings

        result = _read_llm_settings()
        assert result is not None
        settings, path = result
        assert settings["enabled_llm"]["news_correlation"] is True
        assert "llm_settings.json" in path

    @patch("src.python.tui.handlers_config.open", side_effect=FileNotFoundError)
    @patch("src.python.tui.handlers_config.press_any_key")
    def test_file_not_found(self, mock_press, mock_open):
        """文件不存在时返回 None。"""
        from src.python.tui.handlers_config import _read_llm_settings

        result = _read_llm_settings()
        assert result is None

    @patch("src.python.config._strip_json_comments")
    @patch("src.python.tui.handlers_config.open")
    @patch("src.python.tui.handlers_config.json.loads", side_effect=json.JSONDecodeError("x", "", 1))
    @patch("src.python.tui.handlers_config.press_any_key")
    def test_json_decode_error(self, mock_press, mock_json_loads, mock_open, mock_strip):
        """JSON 解析错误时返回 None。"""
        mock_strip.return_value = "bad json"
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "bad json"
        mock_open.return_value = mock_file

        from src.python.tui.handlers_config import _read_llm_settings

        result = _read_llm_settings()
        assert result is None


class TestWriteLlmSettings:
    """_write_llm_settings: 委托共享 write_llm_settings（config 层写入原语）。"""

    @patch("src.python.config._llm_settings.write_llm_settings")
    def test_delegates_to_shared_write(self, mock_write):
        """TUI 写入委托共享 write_llm_settings，参数原样透传。"""
        from src.python.tui.handlers_config import _write_llm_settings

        settings = {"enabled_llm": {"news_correlation": True}}
        path = "/fake/path/llm_settings.json"

        _write_llm_settings(settings, path)
        mock_write.assert_called_once_with(settings, path)


# 标准 LLM 模块（菜单 S 1~5），实验性功能编号紧随其后（6~8）
_STANDARD_LLM_MODULES = {
    "global_macro": "全球政经局势",
    "expert_review": "智囊团深度复盘",
    "health_check": "持仓体检报告",
    "penetration_deep": "穿透深度分析",
    "news_correlation": "财经新闻热点与持仓关联分析",
}


class TestConfigLlmModulesExperimentalFlags:
    """_cmd_config_llm_modules: 实验块开关面板（清单取自 features 注册表实验组）。"""

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["7", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_seven_toggles_decision_reflection(
        self,
        mock_read,
        mock_names,
        mock_filter,
        mock_set_feature,
        mock_save_overrides,
        mock_input,
        mock_refresh,
        mock_press,
    ):
        """输入 7 → 切换第 2 个实验开关（决策跨期反思闭环），持久化到 features.json。

        实验块收窄为 3 项（6 正反辩论 / 7 决策跨期反思 / 8 景气度框架诊断；集中度问答
        已并入辩论流程、信号沉淀已转正为常规开关）——块内编号随注册表实验组即时重排。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"decision_reflection": True})
        mock_set_feature.assert_called_once_with("decision_reflection", True)
        mock_press.assert_called_once()

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["8", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_eight_toggles_prosperity_framework(
        self,
        mock_read,
        mock_names,
        mock_filter,
        mock_set_feature,
        mock_save_overrides,
        mock_input,
        mock_refresh,
        mock_press,
    ):
        """输入 8 → 切换实验块末项（景气度框架诊断），持久化到 features.json。"""
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"prosperity_framework": True})
        mock_set_feature.assert_called_once_with("prosperity_framework", True)
        mock_press.assert_called_once()

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["9", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_nine_toggles_promoted_standard_switch(
        self,
        mock_read,
        mock_names,
        mock_filter,
        mock_set_feature,
        mock_save_overrides,
        mock_input,
        mock_refresh,
        mock_press,
    ):
        """输入 9 → 常规块首项（确定性信号模块，转正后默认开）→ 切换即关闭。

        转正不丢入口、也不等于不可关：常规块编号自 9 起（紧随实验块：3 项辩论/反思/
        景气度框架），默认开故点一次写入 false。实验块新增开关时常规块编号整体顺延
        （编号由分组与块内顺序派生）。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"deterministic_signal": False})
        mock_set_feature.assert_called_once_with("deterministic_signal", False)
        mock_press.assert_called_once()

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["6", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_six_still_toggles_first_debate_flag(
        self,
        mock_read,
        mock_names,
        mock_filter,
        mock_set_feature,
        mock_save_overrides,
        mock_input,
        mock_refresh,
        mock_press,
    ):
        """输入 6 → 仍为第一个辩论开关（编号连续性未被新项打乱）。"""
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"llm_debate_procon": True})

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["14", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_fourteen_toggles_first_metrics_switch(
        self,
        mock_read,
        mock_names,
        mock_filter,
        mock_set_feature,
        mock_save_overrides,
        mock_input,
        mock_refresh,
        mock_press,
    ):
        """输入 14 → 量化指标首项（夏普比率），持久化到 features.json。

        常规块编号自 9 起：9 确定性信号模块 / 10 模块级质量分级 / 11 决策头结构化 /
        12 条件推理 / 13 数据源凭据就绪（转正项），14 起为量化指标七项。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"metrics_sharpe": False})
        mock_set_feature.assert_called_once_with("metrics_sharpe", False)

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["22", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_standard_block_includes_promoted_switches(
        self,
        mock_read,
        mock_names,
        mock_filter,
        mock_set_feature,
        mock_save_overrides,
        mock_input,
        mock_refresh,
        mock_press,
    ):
        """系统自检（转正项）在常规块内可切换——转正不丢入口（回归）。

        编号 22 = 5 标准模块 + 3 实验项 + 常规块序 14（doctor_check）。它此前只
        能靠手改 features.json 关闭；本用例锁定它在面板内仍可关。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"doctor_check": False})
        mock_set_feature.assert_called_once_with("doctor_check", False)


# 报告增强子模块基准配置（与 config.json 默认一致：数据质量仪表盘默认开，其余默认关）
#: 面板渲染测试用的最小配置（报告增强子模块已并入功能开关注册表，不再出现在 config）
_SUB_BASE_CONFIG: dict = {}


class TestConfigPanelsAreRectangular:
    """配置面板的盒线边框必须四边对齐。

    缺陷场景：面板行以 `len()`（码点数）手写空格补白，中文/全角字符占 2 列却
    只算 1；上下边框、分隔线、内容行又各写各的补白数，同一面板的右边框对不到
    同一列。本类逐个面板驱动一次渲染，断言打印出的盒线行显示宽度全等。
    """

    @staticmethod
    def _box_widths(captured: str) -> set[int]:
        """收集捕获输出中盒线行的显示宽度（非盒线行——如面板下方的图例——不计）。"""
        widths = set()
        for line in captured.splitlines():
            stripped = line.strip()
            if stripped.startswith(("┌", "│", "└")) and stripped.endswith(("┐", "│", "┘")):
                widths.add(display_width(line))
        return widths

    def _assert_rectangular(self, capsys, panel):
        """驱动面板函数一次（输入 0 直接返回），断言其盒线行等宽。"""
        panel()
        widths = self._box_widths(capsys.readouterr().out)
        assert widths, "未捕获到任何盒线行——面板渲染路径可能已变"
        assert len(widths) == 1, f"面板右边框未对齐，出现 {len(widths)} 种行宽：{sorted(widths)}"

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.input", side_effect=["0"])
    @patch("src.python.tui.handlers_config._read_llm_settings")
    def test_llm_modules_panel_rectangular(self, mock_read, mock_input, mock_press, capsys):
        """LLM 分析章节面板：标准模块行与实验开关行在同一右边框内。"""
        mock_read.return_value = ({"enabled_llm": {}}, "/tmp/llm_settings.json")
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        self._assert_rectangular(capsys, _cmd_config_llm_modules)

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["0"])
    @patch("src.python.tui.handlers_config.get_config_cache")
    def test_comparison_indices_panel_rectangular(self, mock_cache, mock_input, mock_refresh, mock_press, capsys):
        """对比指数池面板：指数名含中文时右边框仍对齐。"""
        mock_cache.return_value = {"comparison_indices": {"sh000905": "中证500", "sh000300": "沪深300"}}
        from src.python.tui.handlers_config import _cmd_config_comparison_indices

        self._assert_rectangular(capsys, _cmd_config_comparison_indices)

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["0"])
    @patch("src.python.config.get_config", return_value={})
    def test_report_boards_panel_rectangular(self, mock_get, mock_input, mock_refresh, mock_press, capsys):
        """报告可选章节面板：最长行（增强子模块说明）决定宽度且不撑破边框。"""
        from src.python.tui.handlers_config import _cmd_config_report_boards

        self._assert_rectangular(capsys, _cmd_config_report_boards)

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["0"])
    @patch("src.python.config.get_config", return_value=_SUB_BASE_CONFIG)
    def test_anonymization_panel_rectangular(self, mock_get, mock_input, mock_refresh, mock_press, capsys):
        """匿名化面板：带选中标记的行与普通行同宽（自成一档内区宽度）。"""
        from src.python.tui.handlers_config import _cmd_config_anonymization_mode

        self._assert_rectangular(capsys, _cmd_config_anonymization_mode)


class TestReportGroupMovedToSwitchPanel:
    """报告章节与增强子模块已并入功能开关注册表：P 面板不再另设入口，S 面板新增一块。"""

    def _source(self) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[4] / "src" / "python" / "tui" / "handlers_config.py").read_text(
            encoding="utf-8"
        )

    def test_p_subpanel_removed(self):
        src = self._source()
        assert "_cmd_config_report_submodules" not in src, "P 子面板应已删除"
        assert "REPORT_SUBMODULE_ITEMS" not in src, "面板清单常量应随子面板删除"

    def test_boards_panel_points_to_switch_menu(self):
        """基础章节面板第 6 项提示改到菜单 [S]，输入范围收为 (0-6)。"""
        src = self._source()
        assert "输入编号切换 (0-6)" in src
        assert "报告增强子模块 / LLM 分析章节 — 请在菜单 S 配置" in src

    def test_switch_panel_renders_report_group(self):
        """面板分组由注册表 GROUP_ORDER 派生（渠道层不得另写清单）。"""
        src = self._source()
        assert "GROUP_ORDER" in src
        assert "for group in GROUP_ORDER" in src
        assert "GROUP_EXPERIMENTAL, GROUP_STANDARD, GROUP_REPORT" not in src


class TestConfigDirInfoSubmenu:
    """[D] 配置目录信息子菜单：二级选项分发、返回与无效输入。"""

    @patch("builtins.input")
    @patch("src.python.tui.handlers_config._cmd_config_output_dir")
    @patch("src.python.tui.handlers_config._cmd_config_filename")
    @patch("src.python.tui.handlers_config._cmd_config_dir")
    def test_dispatches_three_sub_options_then_returns(self, mock_dir, mock_filename, mock_out, mock_input):
        """依次选 C/F/O 分别路由到三个处理器，B 返回。"""
        mock_input.side_effect = ["C", "F", "O", "B"]

        from src.python.tui.handlers_config import _cmd_config_dir_info

        _cmd_config_dir_info()

        mock_dir.assert_called_once_with()
        mock_filename.assert_called_once_with()
        mock_out.assert_called_once_with()

    @patch("builtins.input")
    @patch("src.python.tui.handlers_config._cmd_config_dir")
    def test_lowercase_choice_accepted(self, mock_dir, mock_input):
        """小写子键归一化为大写后分发。"""
        mock_input.side_effect = ["c", "B"]

        from src.python.tui.handlers_config import _cmd_config_dir_info

        _cmd_config_dir_info()

        mock_dir.assert_called_once_with()

    @patch("builtins.input")
    @patch("src.python.tui.handlers_config._cmd_config_dir")
    def test_back_returns_without_dispatch(self, mock_dir, mock_input):
        """选 B 直接返回，不触发任何处理器。"""
        mock_input.side_effect = ["B"]

        from src.python.tui.handlers_config import _cmd_config_dir_info

        _cmd_config_dir_info()

        mock_dir.assert_not_called()

    @patch("builtins.input")
    @patch("src.python.tui.handlers_config._cmd_config_dir")
    def test_unknown_choice_reprompts(self, mock_dir, mock_input, capsys):
        """无效子键提示后重新等待输入，不误触发处理器。"""
        mock_input.side_effect = ["Z", "B"]

        from src.python.tui.handlers_config import _cmd_config_dir_info

        _cmd_config_dir_info()

        mock_dir.assert_not_called()
        assert "无效选择" in capsys.readouterr().out

    @patch("src.python.tui.handlers_config._cmd_config_dir")
    @patch("builtins.input", side_effect=EOFError)
    def test_eof_returns_safely(self, mock_input, mock_dir):
        """EOF（非交互输入）不抛异常：读取一次即返回，不触发任何处理器。"""
        from src.python.tui.handlers_config import _cmd_config_dir_info

        _cmd_config_dir_info()

        mock_input.assert_called_once()
        mock_dir.assert_not_called()
