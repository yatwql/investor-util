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


# 标准 LLM 模块（菜单 S 1~5），实验性功能编号紧随其后（6~9）
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
    @patch("src.python.tui.handlers_config.input", side_effect=["8", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_eight_toggles_decision_reflection(
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
        """输入 8 → 切换第 3 个实验开关（决策跨期反思闭环），持久化到 features.json。

        转正后实验块收窄为 4 项（6 正反辩论 / 7 集中度问答 / 8 决策跨期反思 /
        9 确定性信号沉淀）——块内编号随注册表实验组即时重排。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"decision_reflection": True})
        mock_set_feature.assert_called_once_with("decision_reflection", True)
        mock_press.assert_called_once()

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["9", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_nine_toggles_signal_ledger(
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
        """输入 9 → 切换实验块末项（确定性信号沉淀），持久化到 features.json。"""
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"signal_ledger": True})
        mock_set_feature.assert_called_once_with("signal_ledger", True)
        mock_press.assert_called_once()

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["10", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_ten_toggles_promoted_standard_switch(
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
        """输入 10 → 常规块首项（信号预消化，转正后默认开）→ 切换即关闭。

        转正不丢入口、也不等于不可关：常规块编号自 10 起（紧随收窄后的实验块），
        默认开故点一次写入 false。此前实验组 9 项时编号 10 落在实验块尾部。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"signal_pre_digest": False})
        mock_set_feature.assert_called_once_with("signal_pre_digest", False)
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
    @patch("src.python.tui.handlers_config.input", side_effect=["15", "0"])
    @patch("src.python.config.features.save_feature_overrides")
    @patch("src.python.config.features.set_feature_enabled")
    @patch("src.python.tui.handlers_config.filter_menu_llm_modules", return_value=_STANDARD_LLM_MODULES)
    @patch("src.python.core.registry.get_llm_module_names")
    @patch("src.python.tui.handlers_config._read_llm_settings", return_value=({}, "/fake/llm_settings.json"))
    def test_menu_number_fifteen_toggles_first_metrics_switch(
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
        """输入 15 → 量化指标首项（夏普比率），持久化到 features.json。

        常规块编号自 10 起：10 信号预消化 / 11 模块级质量分级 / 12 决策头结构化 /
        13 条件推理 / 14 数据源凭据就绪（转正项），15 起为量化指标七项。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"metrics_sharpe": False})
        mock_set_feature.assert_called_once_with("metrics_sharpe", False)

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["23", "0"])
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

        编号 23 = 5 标准模块 + 4 实验项 + 常规块序 14（doctor_check）。它此前只
        能靠手改 features.json 关闭；本用例锁定它在面板内仍可关。
        """
        from src.python.tui.handlers_config import _cmd_config_llm_modules

        _cmd_config_llm_modules()

        mock_save_overrides.assert_called_once_with({"doctor_check": False})
        mock_set_feature.assert_called_once_with("doctor_check", False)


# 报告增强子模块基准配置（与 config.json 默认一致：数据质量仪表盘默认开，其余默认关）
_SUB_BASE_CONFIG = {
    "report_submodules": {
        "data_quality": True,
        "industry_beta": False,
        "candidate_compare": False,
        "cost_lots": False,
        "valuation_percentile": False,
        "market_temperature": False,
    }
}


class TestConfigReportSubmodules:
    """_cmd_config_report_submodules: 报告增强子模块开关切换（mock 输入与配置读写）。"""

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["1", "0"])
    @patch("src.python.config.set_config")
    @patch("src.python.config.get_config", return_value=_SUB_BASE_CONFIG)
    def test_toggle_data_quality_off(self, mock_get, mock_set, mock_input, mock_refresh, mock_press):
        """输入 1 → 关闭数据质量仪表盘（默认开启），整体写回 report_submodules。"""
        from src.python.tui.handlers_config import _cmd_config_report_submodules

        _cmd_config_report_submodules()

        expected = dict(_SUB_BASE_CONFIG["report_submodules"])
        expected["data_quality"] = False
        mock_set.assert_called_once_with("report_submodules", expected)
        mock_press.assert_called_once()

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["2", "0"])
    @patch("src.python.config.set_config")
    @patch("src.python.config.get_config", return_value=_SUB_BASE_CONFIG)
    def test_toggle_industry_beta_on(self, mock_get, mock_set, mock_input, mock_refresh, mock_press):
        """输入 2 → 开启行业Beta子表，其余子模块保持关闭。"""
        from src.python.tui.handlers_config import _cmd_config_report_submodules

        _cmd_config_report_submodules()

        expected = dict(_SUB_BASE_CONFIG["report_submodules"])
        expected["industry_beta"] = True
        mock_set.assert_called_once_with("report_submodules", expected)

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["9", "0"])
    @patch("src.python.config.set_config")
    @patch("src.python.config.get_config", return_value=_SUB_BASE_CONFIG)
    def test_invalid_number_then_return(self, mock_get, mock_set, mock_input, mock_refresh, mock_press):
        """无效编号不写配置，随后 0 正常返回。"""
        from src.python.tui.handlers_config import _cmd_config_report_submodules

        _cmd_config_report_submodules()

        mock_set.assert_not_called()

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.refresh_config")
    @patch("src.python.tui.handlers_config.input", side_effect=["0"])
    @patch("src.python.config.set_config")
    @patch("src.python.config.get_config", return_value=_SUB_BASE_CONFIG)
    def test_zero_returns_without_change(self, mock_get, mock_set, mock_input, mock_refresh, mock_press):
        """直接 0 返回，不触发任何写配置。"""
        from src.python.tui.handlers_config import _cmd_config_report_submodules

        _cmd_config_report_submodules()

        mock_set.assert_not_called()


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
    def test_report_submodules_panel_rectangular(self, mock_get, mock_input, mock_refresh, mock_press, capsys):
        """报告增强子模块面板：各子模块名长短不一，状态方括号仍对齐。"""
        from src.python.tui.handlers_config import _cmd_config_report_submodules

        self._assert_rectangular(capsys, _cmd_config_report_submodules)

    @patch("src.python.tui.handlers_config.press_any_key")
    @patch("src.python.tui.handlers_config.input", side_effect=["0"])
    @patch("src.python.config.anonymizer.get_anonymization_mode", return_value="full_anonymous")
    def test_anonymization_panel_rectangular(self, mock_mode, mock_input, mock_press, capsys):
        """匿名化面板：带选中标记的行与普通行同宽（自成一档内区宽度）。"""
        from src.python.tui.handlers_config import _cmd_config_anonymization_mode

        self._assert_rectangular(capsys, _cmd_config_anonymization_mode)
