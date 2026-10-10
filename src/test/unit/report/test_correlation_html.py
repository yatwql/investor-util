"""持仓关系矩阵章节·相关性区块 HTML 呈现测试。

覆盖：
  - available=True → 汇总卡 + 相关度最高提示 + 热力矩阵 + 配对明细 + 说明
  - 强正/强负/不显著/N/A 单元格样式分支
  - 重叠样本不足品种提示行
  - available=False（数据不足 / 数据源故障）→ 降级占位
  - 相关性数据 None → 相关性区块渲染占位（章节由重合度区块驱动可见）

注意：模板在持仓关系矩阵章节内部直接调用 position_relationship_data.get()，
生产路径由 html_writer 保证重合度或相关性任一区块有数据时该章节才可见，
因此 None 场景通过「相关性区块占位」验证（重合度区块驱动章节可见）。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.test.unit.report.test_html_report_structure import (
    _REPORT_SECTION_DEFAULT,
    _build_minimal_render_data,
    _render_template,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_PR_SECTION = {"key": "position_structure", "name": "持仓结构与集中度", "number": 6}


def _order_with_relationship() -> list[dict]:
    """默认清单中将 position_structure 置为可见（其余隐藏）。"""
    return [dict(sec) for sec in _REPORT_SECTION_DEFAULT]


def _render_correlation(correlation_data) -> "BeautifulSoup":
    """渲染 position_structure 可见、其余隐藏的模板。"""
    order = _order_with_relationship()
    numbers = {sec["key"]: sec["number"] for sec in order}
    sv_dict = {sec["key"]: (sec["key"] == "position_structure") for sec in order}
    data = _build_minimal_render_data(order, numbers, sv_dict)
    data["position_relationship_data"] = correlation_data
    # 章节可见需重合度或相关性任一区块有数据：此处以相关性区块驱动（overlap 置空）
    data["overlap_matrix"] = {"fund_names": {}, "funds": [], "matrix": [], "pairs": []}
    return _render_template(data)


def _correlation_data(**extra) -> dict:
    """构造持仓关系矩阵·相关性区块数据契约 mock（2 品种，强负相关）。"""
    d = {
        "available": True,
        "status": "ok",
        "window": 60,
        "sample_count": 60,
        "codes": ["a", "b"],
        "names": {"a": "资产A", "b": "资产B"},
        "matrix": [[1.0, None], [-0.87, 1.0]],
        "p_values": [[None, None], [0.0001, None]],
        "pairs": [
            {
                "code_a": "b",
                "name_a": "资产B",
                "code_b": "a",
                "name_b": "资产A",
                "pearson": -0.87,
                "p_value": 0.0001,
                "significant": True,
                "samples": 60,
            }
        ],
        "insufficient_codes": [],
        "note": "",
    }
    d.update(extra)
    return d


class TestHtmlCorrelationSection(unittest.TestCase):
    """持仓关系矩阵章节·相关性区块 HTML 呈现测试。"""

    def _section(self, correlation_data):
        return _render_correlation(correlation_data).find(id="sec-position_structure")

    def test_full_rendering_when_available(self):
        """available=True → 汇总卡 + 相关度最高 + 热力矩阵 + 配对明细 + 说明。"""
        section = self._section(_correlation_data())
        text = section.get_text()
        self.assertIn("持仓相关性矩阵", text)
        self.assertIn("个品种", text)  # 汇总卡
        self.assertIn("相关度最高", text)  # 提示横幅
        self.assertIn("配对明细", text)  # 配对表
        self.assertIn("资产A", text)
        self.assertIn("资产B", text)
        self.assertIn("-0.87", text)  # r 值
        self.assertIn("显著", text)
        # 说明区
        self.assertIn("Pearson 相关系数", text)

    def test_matrix_cell_branches(self):
        """单元格样式分支：强负/不显著/N/A/对角线。"""
        data = _correlation_data()
        data["codes"] = ["a", "b", "c"]
        data["names"] = {"a": "资产A", "b": "资产B", "c": "资产C"}
        data["matrix"] = [
            [1.0, None, None],
            [-0.6, 1.0, None],  # b×a 强负
            [None, 0.02, 1.0],  # c×a 样本不足 N/A；c×b 不显著 0.02
        ]
        data["p_values"] = [
            [None, None, None],
            [0.001, None, None],
            [None, 0.20, None],
        ]
        data["pairs"] = [
            {
                "code_a": "b",
                "name_a": "资产B",
                "code_b": "a",
                "name_b": "资产A",
                "pearson": -0.6,
                "p_value": 0.001,
                "significant": True,
                "samples": 60,
            },
            {
                "code_a": "c",
                "name_a": "资产C",
                "code_b": "b",
                "name_b": "资产B",
                "pearson": 0.02,
                "p_value": 0.20,
                "significant": False,
                "samples": 60,
            },
        ]
        section = self._section(data)
        text = section.get_text()
        self.assertIn("强负", text)  # r=-0.6 ≤ -0.5 → 强负格
        self.assertIn("N/A", text)  # c×a 样本不足
        self.assertIn("0.02", text)  # 不显著白格显示数值
        self.assertIn("1.00", text)  # 对角线自相关

    def test_insufficient_codes_note(self):
        """重叠样本不足品种 → 灰 N/A 提示行。"""
        data = _correlation_data()
        data["insufficient_codes"] = ["a", "b"]
        data["matrix"] = [[1.0, None], [None, 1.0]]
        section = self._section(data)
        text = section.get_text()
        self.assertIn("相关性格标为 N/A", text)
        self.assertIn("a", text)

    def test_insufficient_placeholder(self):
        """available=False + status=insufficient → 数据不足占位。"""
        data = _correlation_data(available=False, status="insufficient", sample_count=20, window=60, codes=[], pairs=[])
        section = self._section(data)
        self.assertIn("持仓相关性数据不足", section.get_text())
        self.assertNotIn("配对明细", section.get_text())

    def test_source_failed_placeholder(self):
        """available=False + status=source_failed → 数据源暂不可用占位。"""
        data = _correlation_data(available=False, status="source_failed", codes=[], pairs=[])
        section = self._section(data)
        self.assertIn("数据源暂不可用", section.get_text())

    def test_correlation_none_placeholder(self):
        """相关性数据 None → 相关性区块渲染占位（重合度区块驱动章节可见）。"""
        section = self._section(None)
        text = section.get_text()
        self.assertIn("持仓相关性数据不足", text)
        self.assertNotIn("配对明细", text)


def _overlap_result(**extra) -> dict:
    """构造持仓关系矩阵·重合度区块结构（2 只基金，部分重合 50%）。"""
    d = {
        "fund_names": {"a": "基金A", "b": "基金B"},
        "funds": ["a", "b"],
        "matrix": [
            [1.0, 0.5],
            [0.5, 1.0],
        ],
        "pairs": [
            {
                "fund_a": "a",
                "fund_b": "b",
                "name_a": "基金A",
                "name_b": "基金B",
                "code_a": "a",
                "code_b": "b",
                "common_count": 2,
                "jaccard": 0.5,
                "common_stocks": [
                    {"name": "贵州茅台", "code": "600519"},
                    {"name": "五粮液", "code": "000858"},
                ],
            }
        ],
    }
    d.update(extra)
    return d


class TestHtmlMergedRelationshipSection(unittest.TestCase):
    """持仓关系矩阵章节·一章两区块（重合度 + 相关性）HTML 呈现测试。"""

    def _render_merged(self, overlap_matrix, correlation_data) -> "BeautifulSoup":
        order = _order_with_relationship()
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: (sec["key"] == "position_structure") for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["overlap_matrix"] = overlap_matrix
        data["position_relationship_data"] = correlation_data
        return _render_template(data).find(id="sec-position_structure")

    def test_both_blocks_render_in_merged_section(self):
        """重合度 + 相关性同时提供 → 同一章节内两个子区块依次呈现。"""
        section = self._render_merged(_overlap_result(), _correlation_data())
        text = section.get_text()
        self.assertIn("一、持仓重合度矩阵", text)
        self.assertIn("二、持仓相关性矩阵", text)
        # 重合度区块内容
        self.assertIn("基金A", text)
        self.assertIn("基金B", text)
        self.assertIn("50.00%", text)  # Jaccard 0.5
        # 相关性区块内容
        self.assertIn("资产A", text)
        self.assertIn("-0.87", text)
        self.assertIn("配对明细", text)

    def test_overlap_only_section_visible_correlation_placeholder(self):
        """仅重合度数据 → 章节可见，相关性区块写占位（相关性配对表不出现）。"""
        section = self._render_merged(_overlap_result(), None)
        text = section.get_text()
        self.assertIn("一、持仓重合度矩阵", text)
        self.assertIn("基金A", text)
        self.assertIn("持仓相关性数据不足", text)
        # 相关性配对表表头（品种A/相关系数 r）不应出现；重合度区块自身的配对明细合法保留
        self.assertNotIn("相关系数 r", text)


# ═══════════════════════════════════════════════════════════════
#  滚动趋势区块（HTML 呈现 + 编排接线）
# ═══════════════════════════════════════════════════════════════


def _rolling_data(**extra) -> dict:
    """构造滚动趋势契约 mock（2 窗 × 5 端点 + 1 个焦点品对）。"""
    dates = [f"2026-09-{d:02d}" for d in range(1, 6)]
    p60 = [
        {"date": "2026-09-01", "value": 0.60, "n_pairs": 1},
        {"date": "2026-09-02", "value": 0.65, "n_pairs": 2},
        {"date": "2026-09-03", "value": 0.70, "n_pairs": 2},
        {"date": "2026-09-04", "value": 0.75, "n_pairs": 2},
        {"date": "2026-09-05", "value": 0.80, "n_pairs": 2},
    ]
    p120 = [{"date": d, "value": v, "n_pairs": 2} for d, v in zip(dates, [0.55, 0.60, 0.62, 0.66, 0.70])]
    d = {
        "available": True,
        "status": "ok",
        "windows": [60, 120],
        "min_samples": 60,
        "portfolio": {"60": p60, "120": p120},
        "focus_pairs": [
            {
                "code_a": "b",
                "name_a": "资产B",
                "code_b": "a",
                "name_b": "资产A",
                "series": {
                    "60": [{"date": d2, "value": v} for d2, v in zip(dates, [0.90, 0.91, 0.93, 0.94, 0.95])],
                    "120": [{"date": d2, "value": v} for d2, v in zip(dates, [0.85] * 5)],
                },
            }
        ],
        "coverage": {
            "dates": 120,
            "first_date": "2026-04-01",
            "last_date": "2026-09-05",
            "full_window_from": {"60": "2026-07-01", "120": "2026-09-01"},
        },
        "notes": [
            "组合平均相关性 = 每个滚动端点上全部两两 Pearson r 的均值（参与对重叠样本 ≥ 60 期才计入）",
            "120 日窗完整重叠自 2026-09-01 起，此前端点按可得区间（<120 期）计算",
        ],
    }
    d.update(extra)
    return d


def _with_rolling(rolling) -> dict:
    """基础相关性数据 + rolling 键。"""
    return _correlation_data(rolling=rolling)


class TestHtmlRollingTrend(unittest.TestCase):
    """相关性区块·滚动趋势子块 HTML 呈现。"""

    def _section_html(self, correlation_data) -> str:
        return str(self._section(correlation_data))

    def _section(self, correlation_data):
        return _render_correlation(correlation_data).find(id="sec-position_structure")

    def test_rolling_block_renders_chart_table_and_notes(self):
        """滚动就绪 → 趋势标题 + 图布/绘制脚本 + 焦点品对表 + 口径句全渲染。"""
        section = self._section(_with_rolling(_rolling_data()))
        text = section.get_text()
        html = str(section)
        self.assertIn("滚动趋势", text)
        self.assertIn("corrRollingChart", html)
        self.assertIn("drawSimpleChart", html)
        self.assertIn("重点品对", text)
        # 焦点品对表：最新值与首→末趋势
        self.assertIn("0.95", text)
        self.assertIn("0.90 → 0.95", text)
        # 口径句单源（notes 原样列出）
        self.assertIn("组合平均相关性 = 每个滚动端点上全部两两 Pearson r 的均值", text)
        self.assertIn("120 日窗完整重叠自 2026-09-01 起", text)
        # 覆盖区间行
        self.assertIn("2026-04-01 ~ 2026-09-05", text)

    def test_chart_datasets_script_contains_no_null_literals(self):
        """脚本走日期映射防御：不含会污染极值轴的 null 值占位构造。"""
        html = self._section_html(_with_rolling(_rolling_data()))
        self.assertIn("baseSet", html)
        self.assertIn("window.drawSimpleChart", html)

    def test_rolling_absent_keeps_static_block_only(self):
        """无 rolling 键（既有契约）→ 静态矩阵照常、滚动子块不出现。"""
        section = self._section(_correlation_data())
        self.assertNotIn("滚动趋势", section.get_text())
        self.assertNotIn("corrRollingChart", str(section))

    def test_rolling_unavailable_omits_block(self):
        """rolling.available=False → 子块整体不渲染（静态矩阵不受影响）。"""
        section = self._section(_with_rolling(_rolling_data(available=False, status="insufficient")))
        self.assertNotIn("滚动趋势", section.get_text())
        self.assertNotIn("corrRollingChart", str(section))
        self.assertIn("配对明细", section.get_text())  # 静态块仍在

    def test_rolling_empty_portfolio_omits_block(self):
        """60 窗无端点（极端截断）→ 子块不渲染，不出现空图。"""
        empty = _rolling_data()
        empty["portfolio"] = {"60": [], "120": []}
        section = self._section(_with_rolling(empty))
        self.assertNotIn("corrRollingChart", str(section))


class TestCorrelationRollingWiring(unittest.TestCase):
    """compute_correlation_data 滚动接线：长历史拉取、降级隔离、下采样。"""

    def _holdings(self, codes=("600001", "600002", "600003")):
        from types import SimpleNamespace

        return [SimpleNamespace(code=c, name=f"品种{c[-1]}") for c in codes]

    def _bars(self, code: str, n: int = 130) -> list[dict]:
        """确定性 K 线（date/close），不同代码错相位以产生差异化相关结构。"""
        from datetime import date, timedelta

        phase = int(code[-1])
        out = []
        d = date(2026, 3, 2)
        i = 0
        while len(out) < n:
            if d.weekday() < 5:
                close = 10.0 + 0.5 * ((i + phase) % 11) + 0.05 * ((i * 7 + phase) % 5)
                out.append({"date": d.isoformat(), "close": round(close, 4)})
                i += 1
            d += timedelta(days=1)
        return out

    def test_wiring_attaches_rolling_and_fetches_rolling_history(self):
        """接线：滚动契约附带 + 拉取条数覆盖最长滚动窗（数据底座约束）。"""
        from unittest.mock import MagicMock

        from src.python.analysis.correlation import FETCH_DAYS, ROLLING_WINDOWS
        from src.python.report._report_aux_metrics import compute_correlation_data

        reporter = MagicMock()
        with patch(
            "src.python.report._report_factor_metrics._fetch_holding_bars",
            side_effect=lambda code, name, days: self._bars(code, min(days, 130)),
        ) as mock_fetch:
            result = compute_correlation_data(self._holdings(), {}, reporter)

        assert result["available"] is True
        rolling = result.get("rolling")
        assert rolling and rolling["available"] is True
        assert rolling["portfolio"]["60"], "滚动 60 窗应有端点"
        # 数据源约束：拉取条数必须覆盖最长滚动窗（否则滚动趋势恒被截断）
        assert FETCH_DAYS >= max(ROLLING_WINDOWS)
        for call in mock_fetch.call_args_list:
            assert call.args[2] == FETCH_DAYS

    def test_rolling_failure_degrades_to_static_matrix(self):
        """滚动层异常 → 静态矩阵完好、rolling=None（分层降级，不拖垮区块）。"""
        from unittest.mock import MagicMock

        from src.python.report._report_aux_metrics import compute_correlation_data

        reporter = MagicMock()
        with (
            patch(
                "src.python.report._report_factor_metrics._fetch_holding_bars",
                side_effect=lambda code, name, days: self._bars(code, 130),
            ),
            patch(
                "src.python.analysis.correlation.compute_rolling_correlations",
                side_effect=RuntimeError("滚动层爆炸"),
            ),
        ):
            result = compute_correlation_data(self._holdings(), {}, reporter)

        assert result["available"] is True
        assert result["rolling"] is None
        assert result["pairs"], "静态配对明细必须保留"

    def test_unavailable_paths_carry_rolling_none(self):
        """全链路取数失败 → 不可用契约同样携带 rolling=None（契约键恒在）。"""
        from unittest.mock import MagicMock

        from src.python.report._report_aux_metrics import compute_correlation_data

        reporter = MagicMock()
        with patch(
            "src.python.report._report_factor_metrics._fetch_holding_bars",
            return_value=None,
        ):
            result = compute_correlation_data(self._holdings(), {}, reporter)

        assert result["available"] is False
        assert result["rolling"] is None

    def test_downsample_applied_to_rolling_series(self):
        """超长滚动序列经 report/downsample 下采样（复用，不自造降采样）。"""
        from unittest.mock import MagicMock

        from src.python.report._report_aux_metrics import compute_correlation_data
        from src.python.report.downsample import DOWNSAMPLE_WEEK_THRESHOLD

        from datetime import date, timedelta

        _d = date(2025, 1, 1)
        big_dates: list[str] = []
        while len(big_dates) < 620:
            if _d.weekday() < 5:
                big_dates.append(_d.isoformat())
            _d += timedelta(days=1)
        fake_rolling = {
            "available": True,
            "status": "ok",
            "windows": [60, 120],
            "min_samples": 60,
            "portfolio": {
                "60": [{"date": d, "value": 0.5, "n_pairs": 1} for d in big_dates],
                "120": [{"date": d, "value": 0.5, "n_pairs": 1} for d in big_dates],
            },
            "focus_pairs": [
                {
                    "code_a": "600001",
                    "name_a": "品种1",
                    "code_b": "600002",
                    "name_b": "品种2",
                    "series": {
                        "60": [{"date": d, "value": 0.4} for d in big_dates],
                        "120": [{"date": d, "value": 0.4} for d in big_dates],
                    },
                }
            ],
            "coverage": {
                "dates": 620,
                "first_date": big_dates[0],
                "last_date": big_dates[-1],
                "full_window_from": {"60": big_dates[0], "120": big_dates[0]},
            },
            "notes": ["测试口径句"],
        }
        reporter = MagicMock()
        with (
            patch(
                "src.python.report._report_factor_metrics._fetch_holding_bars",
                side_effect=lambda code, name, days: self._bars(code, 130),
            ),
            patch(
                "src.python.analysis.correlation.compute_rolling_correlations",
                return_value=fake_rolling,
            ),
        ):
            result = compute_correlation_data(self._holdings(), {}, reporter)

        rolling = result["rolling"]
        assert rolling["available"] is True
        assert len(rolling["portfolio"]["60"]) <= DOWNSAMPLE_WEEK_THRESHOLD
        assert len(rolling["focus_pairs"][0]["series"]["60"]) <= DOWNSAMPLE_WEEK_THRESHOLD
        # 下采样保持端点轴同轴（周聚合取期末值，各序列同键同组）
        assert [p["date"] for p in rolling["portfolio"]["60"]] == [p["date"] for p in rolling["portfolio"]["120"]]
