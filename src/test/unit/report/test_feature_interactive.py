"""交互图表 Feature Flag + 报告管线集成单元测试。

覆盖：
  - enable_interactive_charts Flag 默认开启（features.py 注册）
  - _build_chart_datasets_for_report：Flag 关闭 → None；开启 → 数据集 dict
  - R11 顶层兜底：build_chart_datasets 异常 → 返回空 dict（报告仍正常）
  - _copy_js_assets：Chart.js 本地 bundle 4 文件随报告复制（R21）

运行：
  cd /lzcapp/document/working/codebase/investor-util
  .venv/bin/python -m pytest src/test/unit/report/test_feature_interactive.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.config.features import is_feature_enabled
from src.python.report._report_generation import _build_chart_datasets_for_report
from src.python.report.html_writer import _copy_js_assets

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


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
        result = _build_chart_datasets_for_report(
            history_data=_history_ok(), enable_interactive=False
        )
        assert result is None

    def test_flag_on_returns_datasets(self) -> None:
        """Flag 开启 → helper 返回数据集 dict。"""
        result = _build_chart_datasets_for_report(
            history_data=_history_ok(), enable_interactive=True
        )
        assert isinstance(result, dict)
        assert "portfolio_line" in result

    def test_top_level_fallback_returns_empty_dict(self) -> None:
        """R11 顶层兜底：build_chart_datasets 抛异常 → 返回空 dict（报告仍正常）。"""
        # 函数内为 `from ...chart_data_builder import build_chart_datasets`，
        # 需 patch 源模块属性才会被函数内 import 取到。
        with patch(
            "src.python.report.chart_data_builder.build_chart_datasets",
            side_effect=RuntimeError("boom"),
        ):
            result = _build_chart_datasets_for_report(
                history_data=_history_ok(), enable_interactive=True
            )
        assert result == {}


class TestCopyJsAssets:
    def test_copies_four_js_files(self, tmp_path) -> None:
        """Chart.js 本地 bundle 4 文件随报告复制到输出目录（R21）。"""
        _copy_js_assets(str(tmp_path))
        for fname in ("chart.min.js", "chart-print.js", "chart-config.js", "chart-init.js"):
            assert (tmp_path / fname).exists(), f"{fname} 未复制"
