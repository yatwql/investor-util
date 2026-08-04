"""交互图表 Feature Flag + 报告管线集成单元测试。

覆盖：
  - enable_interactive_charts Flag 默认开启（features.py 注册）
  - _build_chart_datasets_for_report：Flag 关闭 → None；开启 → 数据集 dict
  - 顶层兜底：build_chart_datasets 异常 → 返回空 dict（报告仍正常）
  - _copy_js_assets：Chart.js 本地 bundle 全部 JS 文件随报告复制
  - 调试页 test-chart.html 引擎注入列表与报告模板一致（浏览器人工验证前置载体）

运行：
  cd /lzcapp/document/working/codebase/investor-util
  .venv/bin/python -m pytest src/test/unit/report/test_feature_interactive.py -v
"""

from __future__ import annotations

import os
import re
from unittest.mock import patch

import pytest

from src.python.config.features import is_feature_enabled
from src.python.report._report_generation import _build_chart_datasets_for_report
from src.python.report.html_writer import _copy_js_assets

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_DEBUG_PAGE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "test-chart.html"),
)


def _history_ok() -> dict:
    return {
        "status": "ok",
        "bars": [{"date": "2026-01-01", "total_value": 100.0, "drawdown_pct": 0.0}],
        "benchmarks": [],
    }


class TestFeatureFlagRegistration:
    def test_flag_registered_and_default_enabled(self) -> None:
        """enable_interactive_charts 注册且默认开启。"""
        assert is_feature_enabled("enable_interactive_charts") is True

    def test_flag_disabled_via_overrides(self) -> None:
        """运行时关闭 Flag 生效。"""
        from src.python.config.features import set_feature_enabled

        try:
            set_feature_enabled("enable_interactive_charts", False)
            assert is_feature_enabled("enable_interactive_charts") is False
        finally:
            set_feature_enabled("enable_interactive_charts", True)


class TestBuildChartDatasetsForReport:
    def test_flag_off_returns_none(self) -> None:
        """Flag 关闭 → helper 返回 None（模板回退旧 Canvas）。"""
        result = _build_chart_datasets_for_report(history_data=_history_ok(), enable_interactive=False)
        assert result is None

    def test_flag_on_returns_datasets(self) -> None:
        """Flag 开启 → helper 返回数据集 dict。"""
        result = _build_chart_datasets_for_report(history_data=_history_ok(), enable_interactive=True)
        assert isinstance(result, dict)
        assert "portfolio_line" in result

    def test_top_level_fallback_returns_empty_dict(self) -> None:
        """顶层兜底：build_chart_datasets 抛异常 → 返回空 dict（报告仍正常）。"""
        # 函数内为 `from ...chart_data_builder import build_chart_datasets`，
        # 需 patch 源模块属性才会被函数内 import 取到。
        with patch(
            "src.python.report.chart_data_builder.build_chart_datasets",
            side_effect=RuntimeError("boom"),
        ):
            result = _build_chart_datasets_for_report(history_data=_history_ok(), enable_interactive=True)
        assert result == {}


class TestCopyJsAssets:
    def test_copies_all_js_files(self, tmp_path) -> None:
        """Chart.js 本地 bundle 全部 JS 文件随报告复制到输出目录。"""
        _copy_js_assets(str(tmp_path))
        for fname in (
            "chart.min.js",
            "chart-print.js",
            "chart-config.js",
            "chart-export.js",
            "chart-common.js",
            "chart-init.js",
            "toc.js",
            "theme.js",
        ):
            assert (tmp_path / fname).exists(), f"{fname} 未复制"


class TestDebugPageAssets:
    """调试页 test-chart.html 引擎注入列表与报告模板一致（浏览器人工验证前置载体）。"""

    def test_injection_list_contains_chart_common_before_init(self) -> None:
        """注入列表必须含 chart-common.js 且先于 chart-init.js（回归防护）。

        chart-init.js 依赖 window.ChartCommon（chart-common.js 提供），报告模板
        已加载它，但调试页 test-chart.html 注入列表曾漏掉该文件，导致调试页
        0/6 图全部跳过、自检无法进行。本用例保证两处注入顺序一致。
        """
        with open(_DEBUG_PAGE_PATH, encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"var scripts\s*=\s*\[(.*?)\];", content)
        assert m, "test-chart.html 应包含 scripts 引擎注入数组"
        scripts = [s.strip().strip("'\"") for s in m.group(1).split(",")]
        assert "chart.min.js" in scripts, "注入列表应包含 chart.min.js"
        assert "chart-common.js" in scripts, "注入列表应包含 chart-common.js（chart-init 依赖）"
        assert "chart-init.js" in scripts, "注入列表应包含 chart-init.js"
        assert scripts.index("chart-common.js") < scripts.index("chart-init.js"), (
            "chart-common.js 必须先于 chart-init.js 注入"
        )

    def test_offline_scenario_removes_only_engine(self) -> None:
        """离线场景仅移除 chart.min.js（引擎），chart-common.js 保留。

        与报告离线验证（删除/改名 chart.min.js）行为一致：chart-init.js 靠
        typeof Chart 守卫静默跳过，无 JS 报错。
        """
        with open(_DEBUG_PAGE_PATH, encoding="utf-8") as f:
            content = f.read()
        assert "scripts.shift();" in content, "离线场景应通过 shift() 仅移除第一个引擎文件"
        assert "if (scenario === 'offline') { scripts.shift(); }" in content, "离线场景应在注入前移除 chart.min.js"
