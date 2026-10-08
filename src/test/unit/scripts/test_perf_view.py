"""perf-view.py 性能趋势查看测试（阶段统计合并 / 分组聚合 / 趋势报告渲染）。

覆盖 `_mean`/`_min_max` 的空输入降级、`_merge_phase_stats` 的跨记录聚合、
`_group_records` 的类型过滤 + 截尾 + 按时间排序，以及 `build_trend_report`
的空数据文案、分组表头、阶段表与「最近 5 次」明细截断。
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]


@pytest.fixture(name="mod")
def fixture_mod():
    """加载 `scripts/perf-view.py` 为可测模块。"""
    from src.test._script_loader import load_script

    return load_script("perf-view.py")


def _records(count: int = 3, version: str = "0.1.0", report_type: str = "full", start: int = 0) -> list[dict]:
    return [
        {
            "version": version,
            "report_type": report_type,
            "timestamp": f"2026-01-{start + i:02d} 10:00:00",
            "total_seconds": 10.0 + i,
            "holdings_count": 20,
            "phases": {"采集": 1.0 + i},
            "errors": [],
        }
        for i in range(count)
    ]


# ── 统计工具 ──


class TestStatsHelpers:
    """均值 / 极值的正常与空输入。"""

    def test_mean_of_values(self, mod):
        assert mod._mean([1.0, 2.0, 6.0]) == pytest.approx(3.0)

    def test_mean_of_empty_is_zero(self, mod):
        assert mod._mean([]) == 0.0

    def test_min_max(self, mod):
        assert mod._min_max([3.0, 1.0, 2.0]) == (1.0, 3.0)

    def test_min_max_of_empty_is_zero_pair(self, mod):
        assert mod._min_max([]) == (0.0, 0.0)


class TestMergePhaseStats:
    """`_merge_phase_stats` 跨记录合并。"""

    def test_merges_phase_values_across_records(self, mod):
        records = [
            {"phases": {"采集": 1.0, "渲染": 4.0}},
            {"phases": {"采集": 3.0}},
        ]
        stats = mod._merge_phase_stats(records)
        assert stats["采集"]["avg"] == pytest.approx(2.0)
        assert stats["采集"]["min"] == pytest.approx(1.0)
        assert stats["采集"]["max"] == pytest.approx(3.0)
        assert stats["采集"]["count"] == 2
        assert stats["渲染"]["count"] == 1

    def test_phase_names_sorted(self, mod):
        records = [{"phases": {"渲染": 1.0, "采集": 2.0, "LLM": 3.0}}]
        assert list(mod._merge_phase_stats(records)) == ["LLM", "渲染", "采集"]

    @pytest.mark.parametrize("phases", [{}, "not-a-dict"])
    def test_missing_or_malformed_phases_ignored(self, mod, phases):
        assert mod._merge_phase_stats([{"phases": phases}, {}]) == {}


# ── 分组聚合 ──


class TestGroupRecords:
    """`_group_records` 的过滤、截尾、排序与键。"""

    def test_groups_by_version_and_report_type(self, mod):
        records = _records(2, version="0.1.0") + _records(2, version="0.2.0", report_type="basic")
        groups = mod._group_records(records, None, None)
        assert set(groups) == {"0.1.0 / full", "0.2.0 / basic"}
        assert len(groups["0.1.0 / full"]) == 2

    def test_filters_by_report_type(self, mod):
        records = _records(2, report_type="full") + _records(3, report_type="basic")
        groups = mod._group_records(records, "basic", None)
        assert list(groups) == ["0.1.0 / basic"]
        assert len(groups["0.1.0 / basic"]) == 3

    def test_last_n_slices_before_grouping(self, mod):
        records = _records(5)
        groups = mod._group_records(records, None, 2)
        assert len(groups["0.1.0 / full"]) == 2
        assert [r["timestamp"] for r in groups["0.1.0 / full"]][-1] == records[-1]["timestamp"]

    def test_records_sorted_by_timestamp_within_group(self, mod):
        records = [
            {"version": "0.1.0", "report_type": "full", "timestamp": "2026-01-03 00:00:00"},
            {"version": "0.1.0", "report_type": "full", "timestamp": "2026-01-01 00:00:00"},
            {"version": "0.1.0", "report_type": "full", "timestamp": "2026-01-02 00:00:00"},
        ]
        groups = mod._group_records(records, None, None)
        stamps = [r["timestamp"] for r in groups["0.1.0 / full"]]
        assert stamps == sorted(stamps)

    def test_group_keys_sorted(self, mod):
        records = _records(1, version="0.9.0") + _records(1, version="0.10.0")
        assert list(mod._group_records(records, None, None)) == sorted(["0.9.0 / full", "0.10.0 / full"])

    def test_missing_fields_default_to_question_mark(self, mod):
        groups = mod._group_records([{"phases": {}}], None, None)
        assert list(groups) == ["? / ?"]


# ── 趋势报告 ──


class TestBuildTrendReport:
    """`build_trend_report` 的 Markdown 输出结构。"""

    def test_empty_records_render_placeholder(self, mod):
        text = mod.build_trend_report([])
        assert "**分组数**：0 组" in text
        assert "暂无性能历史数据" in text

    def test_header_counts_derived_from_input(self, mod):
        records = _records(4) + _records(2, report_type="basic")
        text = mod.build_trend_report(records)
        assert "**总记录数**：6 条" in text
        assert "**分组数**：2 组" in text

    def test_group_section_contains_counts_and_phase_table(self, mod):
        text = mod.build_trend_report(_records(3))
        assert "## 0.1.0 / full" in text
        assert "运行次数：**3**" in text
        assert "| 阶段 | 平均耗时 | 最短 | 最长 | 次数 |" in text
        assert "| 采集 |" in text

    def test_detail_table_capped_at_five_runs(self, mod):
        text = mod.build_trend_report(_records(8))
        assert "最近 5 次运行明细" in text
        detail_rows = [ln for ln in text.splitlines() if ln.startswith("| 2026-01-")]
        assert len(detail_rows) == 5

    def test_detail_timestamp_keeps_whole_date_and_minute(self, mod):
        """时间列取前 16 位（日期+时:分），年份首位不得被截掉。"""
        text = mod.build_trend_report(_records(2))
        cells = [ln.split("|")[1].strip() for ln in text.splitlines() if ln.startswith("| 2026-")]
        assert cells
        assert all(len(cell) == 16 for cell in cells)
        assert not any(ln.startswith("| 6-") for ln in text.splitlines())

    def test_report_type_and_last_n_applied(self, mod):
        records = _records(4, report_type="full") + _records(4, report_type="basic")
        text = mod.build_trend_report(records, report_type="basic", last_n=2)
        assert f"**总记录数**：{len(records)} 条" in text  # 头部计数是输入总量，分组按过滤后
        assert "0.1.0 / basic" in text
        assert "0.1.0 / full" not in text
        assert "运行次数：**2**" in text
