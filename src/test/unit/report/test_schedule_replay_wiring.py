"""调仓纪律回放（schedule_replay_panel）接线测试 — 开关/挂载点/注册表/双端/模板。

覆盖（迭代 3 验收）：
  - 开关注册表：rebalance_schedule_replay 已登记（实验组、默认关、影响报告）
  - 挂载点：seam 开关关闭零行为、开关注入契约、下游异常只告警不外抛
  - 注册表：章节条目（type/data_flag/序号）、页签名、导航分组、两端 board 层
  - 关态回退：契约缺席 → 章隐藏且不消耗连续编号（与「注册表无此章」逐位相等）
  - 双端单源：view 预格式化行 ⊆ Excel 页签单元格；不可用时页签写占位原因
  - 引用块：可用 → 块非空（指标对照与报告同源）；不可用 → 空串（附录零贡献）
  - 模板接线：partial 存在且被 report_template include（位于事件窗之后、基本面之前）
  - 契约装配：注入取数替身 → 真实回放引擎 → available/prompt_block 落契约

测试隔离：全链 mock/注入替身，不触网、不读写真实数据。
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from src.python.config.features import feature_switch_registry, is_feature_enabled
from src.python.core.constants import PROJECT_ROOT
from src.python.core.registry import _REPORT_SECTION_DEFAULT, get_report_sheet_name
from src.python.report import _experimental_seams as seams
from src.python.report.progress import ProgressReporter
from src.python.report.schedule_replay_panel import (
    LIMITATIONS_NOTE,
    build_schedule_replay_panel,
    build_schedule_replay_view,
    write_schedule_replay_sheet,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]

_TMPL_DIR = Path(PROJECT_ROOT) / "src" / "static" / "tmpl"

_PANEL_BUILD = "src.python.report.schedule_replay_panel.build_schedule_replay_panel"
_FETCH_NAV = "src.python.report.schedule_replay_panel._fetch_nav_series"
_FEE_INDEX = "src.python.fetcher.fund_fee.fetch_fee_index"

_HOLDINGS = [
    {"code": "A", "name": "甲基金", "shares": 100.0, "cost": 1.0},
    {"code": "B", "name": "乙基金", "shares": 100.0, "cost": 1.0},
]


def _navs_long() -> dict[str, dict[str, float]]:
    """长窗口净值（约 425 个自然日、280+ 净值日）——满足默认验收下限。"""
    dates: list[str] = []
    cur = date(2024, 11, 1)
    while cur <= date(2025, 12, 31):
        if cur.weekday() < 5:
            dates.append(cur.isoformat())
        cur += timedelta(days=1)
    a_map: dict[str, float] = {}
    for i, d in enumerate(dates):
        base = 10.0 * (1.0 + 0.0005 * i)
        wiggle = 1.02 if i % 2 else 0.98
        a_map[d] = round(base * wiggle, 6)
    return {"A": a_map, "B": {d: 10.0 for d in dates}}


def _placeholder(reason: str = "历史窗口不足 12 个月（跨度 0 天 < 365 天）") -> dict:
    """不可用占位契约（与 build_schedule_replay_panel 占位态同形）。"""
    return {
        "available": False,
        "reason": reason,
        "window": None,
        "gap_pct": None,
        "cost_note": "",
        "rules": {},
        "fetch_failed": [],
        "prompt_block": "",
    }


def _build_contract(*, flag_on: bool = True) -> dict:
    """注入取数替身装配真实回放契约（全离线：净值/费率均替身）。"""
    with (
        patch("src.python.config.features.is_feature_enabled", return_value=flag_on),
        patch(_FETCH_NAV, return_value=(_navs_long(), [])),
        patch(_FEE_INDEX, return_value={}),
    ):
        return build_schedule_replay_panel(list(_HOLDINGS))


class _RecordingReporter(ProgressReporter):
    """记录各级消息的进度报告器（默认 ProgressReporter 各方法为空实现）。"""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[tuple[str, str]] = []

    def warn(self, msg: str) -> None:
        self.messages.append(("warn", msg))

    def warns(self) -> list[str]:
        return [msg for level, msg in self.messages if level == "warn"]


@pytest.fixture
def reporter() -> _RecordingReporter:
    return _RecordingReporter()


# ── 开关注册表 ───────────────────────────────────────────


class TestFeatureSwitchRegistry:
    """rebalance_schedule_replay 已登记且默认关、影响报告输出。"""

    def test_switch_registered_in_experimental_group_off_by_default(self):
        sw = feature_switch_registry["rebalance_schedule_replay"]
        assert sw.label == "调仓纪律回放"
        assert sw.group == "experimental"
        assert sw.default is False
        assert sw.affects_report is True
        assert is_feature_enabled("rebalance_schedule_replay") is False


# ── 挂载点（seam） ──────────────────────────────────────


class TestScheduleReplayMount:
    """调仓纪律回放挂载点（实验组开关，产出 ``schedule_replay_data`` 契约）。"""

    def test_flag_off_is_inert(self, reporter):
        """开关关闭 → 不装配、不注入、不告警（零导入零成本）。"""
        pipeline_data: dict = {}
        with patch("src.python.config.features.is_feature_enabled", return_value=False):
            seams.inject_schedule_replay_data(pipeline_data, reporter, holdings=list(_HOLDINGS))
        assert pipeline_data == {}
        assert reporter.warns() == []

    def test_flag_on_injects_contract(self, reporter):
        """开关打开 → 契约写入 pipeline_data，持仓清单透传。"""
        pipeline_data: dict = {}
        with (
            patch("src.python.config.features.is_feature_enabled", return_value=True),
            patch(_PANEL_BUILD, return_value={"available": True}) as build,
        ):
            seams.inject_schedule_replay_data(pipeline_data, reporter, holdings=list(_HOLDINGS))
        assert pipeline_data["schedule_replay_data"] == {"available": True}
        assert build.call_args.args[0] == _HOLDINGS

    def test_none_pipeline_data_does_not_raise(self, reporter):
        """pipeline_data=None（干跑）不得因注入而抛异常。"""
        with (
            patch("src.python.config.features.is_feature_enabled", return_value=True),
            patch(_PANEL_BUILD, return_value={"available": True}),
        ):
            seams.inject_schedule_replay_data(None, reporter, holdings=[])
        assert reporter.warns() == []

    def test_downstream_exception_warns_only(self, reporter):
        """下游异常 → 一条告警 + 契约缺席，不外抛、不中断报告。"""
        pipeline_data: dict = {}
        with (
            patch("src.python.config.features.is_feature_enabled", return_value=True),
            patch(_PANEL_BUILD, side_effect=RuntimeError("boom")),
        ):
            seams.inject_schedule_replay_data(pipeline_data, reporter, holdings=list(_HOLDINGS))
        assert pipeline_data == {}
        assert len(reporter.warns()) == 1
        assert "调仓纪律回放" in reporter.warns()[0]


# ── 注册表 / 导航 / 页签名 ──────────────────────────────


class TestRegistryWiring:
    """章节注册表条目与两端派生点（序号/类型/页签名/导航分组）。"""

    @staticmethod
    def _entry() -> dict:
        return next(s for s in _REPORT_SECTION_DEFAULT if s["key"] == "schedule_replay")

    def test_section_entry_shape(self):
        entry = self._entry()
        assert entry["type"] == "schedule_replay"
        assert entry["data_flag"] == "schedule_replay_data"
        assert entry["name"] == "调仓纪律回放"

    def test_section_number_follows_holding_change(self):
        """默认序：回放紧随持仓变动复盘，后续章顺延（号序连续由 drift 守护）。"""
        keys = [s["key"] for s in _REPORT_SECTION_DEFAULT]
        numbers = [s["number"] for s in _REPORT_SECTION_DEFAULT]
        assert keys[keys.index("holding_change") + 1] == "schedule_replay"
        assert numbers == list(range(1, len(keys) + 1))

    def test_sheet_name_registered(self):
        assert get_report_sheet_name("schedule_replay") == "调仓纪律回放"

    def test_nav_group_is_history(self):
        from src.python.report.html_writer_nav import _SECTION_NAV_GROUP_MAP

        assert _SECTION_NAV_GROUP_MAP["schedule_replay"] == "history"

    def test_board_flags_default_true_on_both_sides(self):
        """实验章 board 层恒 True（两端一致），可见性由 data 层决定。"""
        from src.python.report.excel_sheet_factory import build_data_availability
        from src.python.report.html_writer_nav import _compute_section_visibility

        _nums, visible, _ = _compute_section_visibility(
            list(_REPORT_SECTION_DEFAULT), {}, {}, {}, {}, include_news=True, llm_enabled_flag=True
        )
        assert "schedule_replay" in visible
        assert visible["schedule_replay"] is False  # data 层缺席 → 隐藏（board 层非否决）
        assert build_data_availability(schedule_replay_data={})["schedule_replay_data"] is True


# ── 关态回退：隐藏章不消耗连续编号 ───────────────────────


class TestOffStateVisibility:
    """契约缺席 → 章隐藏且不消耗连续编号，两端缺省口径锁定。"""

    def test_hidden_section_consumes_no_visible_number(self):
        from src.python.core.registry import get_report_section_order
        from src.python.report.html_writer_nav import _compute_section_visibility

        order = get_report_section_order()
        kwargs = dict(
            include_news=True,
            llm_enabled_flag=True,
            schedule_replay_data=None,  # 开关关闭：键缺席
        )
        visible_numbers, visible_dict, _ = _compute_section_visibility(order, {}, {}, {}, {}, **kwargs)
        assert visible_dict["schedule_replay"] is False
        assert "schedule_replay" not in visible_numbers
        # 逐字节回退：隐藏章对既有编号零影响 —— 与「注册表里根本没这一章」时
        # 计算出的可见性/编号完全相等
        order_without = [s for s in order if s["key"] != "schedule_replay"]
        ref_numbers, _, _ = _compute_section_visibility(order_without, {}, {}, {}, {}, **kwargs)
        assert visible_numbers == ref_numbers
        assert list(visible_numbers.values()) == list(range(1, len(visible_numbers) + 1))

    def test_build_data_availability_defaults_flag_false(self):
        from src.python.report.excel_sheet_factory import build_data_availability

        avail = build_data_availability()
        assert avail["schedule_replay_data"] is False  # 显式 False（非缺省 True）

        avail_on = build_data_availability(schedule_replay_data={"available": True})
        assert avail_on["schedule_replay_data"] is True

    def test_hidden_when_data_present_false_availability(self):
        """契约在场但 available=False → 章可见（走占位），非隐藏。"""
        from src.python.core.registry import get_report_section_order
        from src.python.report.html_writer_nav import _compute_section_visibility

        order = get_report_section_order()
        visible_numbers, visible_dict, _ = _compute_section_visibility(
            order, {}, {}, {}, {}, include_news=True, llm_enabled_flag=True, schedule_replay_data={"available": False}
        )
        assert visible_dict["schedule_replay"] is True
        assert "schedule_replay" in visible_numbers


# ── 双端单源：view ↔ Excel 页签 ─────────────────────────


class TestViewSheetSingleSource:
    """view 预格式化行与页签单元格逐字节同文；口径标注同现。"""

    def test_sheet_rows_superset_of_view_rows(self):
        from openpyxl import Workbook

        contract = _build_contract()
        assert contract["available"] is True, f"契约装配失败: {contract.get('reason')}"
        view = build_schedule_replay_view(contract)

        wb = Workbook()
        ws = wb.active
        write_schedule_replay_sheet(ws, contract)
        cells = [str(c) for row in ws.iter_rows(values_only=True) for c in row if c is not None]

        for line in view["summary_lines"]:
            assert line in cells, "口径摘要行未逐字节写入页签"
        for row in view["metric_rows"]:
            for cell in row:
                assert cell in cells, f"指标行单元格缺失: {cell}"
        for row in view["period_rows"]:
            for cell in row:
                assert cell in cells, f"逐期行单元格缺失: {cell}"
        assert view["limitations_note"] in cells, "口径标注必须与表同现（双端成对）"
        assert LIMITATIONS_NOTE in cells

    def test_placeholder_when_unavailable(self):
        from openpyxl import Workbook

        contract = _placeholder()
        view = build_schedule_replay_view(contract)
        assert view["available"] is False
        assert view["reason"] == contract["reason"]

        wb = Workbook()
        ws = wb.active
        write_schedule_replay_sheet(ws, contract)
        texts = [str(c) for row in ws.iter_rows(values_only=True) for c in row if c is not None]
        assert contract["reason"] in texts, "不可用时页签必须写占位原因"


# ── 引用块：非空同源 / 空串回退 ─────────────────────────


class TestPromptBlock:
    """prompt_block 与报告视图同源；不可用 → 空串（附录零贡献）。"""

    def test_block_renders_view_text(self):
        from src.python.report.schedule_replay_panel import _build_prompt_block

        contract = _build_contract()
        view = build_schedule_replay_view(contract)
        block = _build_prompt_block(view)
        assert block, "可用契约的引用块必须非空"
        assert block.startswith("【调仓纪律回放"), "块必须带章节标识头"
        # 指标对照表头与行与报告视图同源
        for cell in view["metric_header"]:
            assert cell in block
        for row in view["metric_rows"]:
            for cell in row:
                assert cell in block, f"指标行未进引用块: {cell}"
        assert view["limitations_note"] in block, "口径标注必须进引用块"

    def test_empty_when_unavailable(self):
        from src.python.report.schedule_replay_panel import _build_prompt_block

        assert _build_prompt_block(build_schedule_replay_view(_placeholder())) == ""


# ── 模板接线（源码级） ───────────────────────────────────


class TestTemplateWiring:
    """partial 已建且被主模板 include，按 section_visible + view 双守卫。"""

    def test_partial_exists_and_guarded(self):
        partial = (_TMPL_DIR / "partials" / "schedule_replay_section.html").read_text(encoding="utf-8")
        assert 'section_visible("schedule_replay")' in partial
        assert "schedule_replay_view" in partial
        assert "limitations_note" in partial  # 标注经同源 view 渲染
        assert "sec-schedule_replay" in partial
        assert "schedule-replay-chart-data" in partial  # 双线图数据序列化锚点
        assert "chart_schedule_replay" in partial

    def test_main_template_includes_partial(self):
        tmpl = (_TMPL_DIR / "report_template.html").read_text(encoding="utf-8")
        assert '{% include "partials/schedule_replay_section.html" with context %}' in tmpl
        # include 位于持仓变动复盘与基本面快照之间（正文顺序 = 注册表顺序）
        hc_idx = tmpl.index("partials/holding_change_section.html")
        sr_idx = tmpl.index("partials/schedule_replay_section.html")
        fs_idx = tmpl.index("partials/fundamental_snapshot_section.html")
        assert hc_idx < sr_idx < fs_idx

    def test_chart_init_registers_schedule_replay(self):
        js = (Path(PROJECT_ROOT) / "src" / "static" / "chart-init.js").read_text(encoding="utf-8")
        assert "initScheduleReplayChart" in js
        assert "schedule_replay: initScheduleReplayChart" in js


# ── 契约装配（注入替身，全离线） ─────────────────────────


class TestPanelAssembly:
    """build_schedule_replay_panel：注入取数 → 真实回放引擎 → 引用块落契约。"""

    def test_assembles_contract_with_block(self):
        contract = _build_contract()
        assert contract["available"] is True, f"契约装配失败: {contract.get('reason')}"
        assert set(contract["rules"]) == {"monthly", "threshold"}
        assert contract["window"], "回放窗口必须落契约"
        assert isinstance(contract["gap_pct"], float)
        assert isinstance(contract["cost_note"], str)
        assert contract["fetch_failed"] == []
        assert isinstance(contract["prompt_block"], str) and contract["prompt_block"]

    def test_view_carries_two_line_chart(self):
        contract = _build_contract()
        view = build_schedule_replay_view(contract)
        chart = view["chart"]
        assert chart, "可用契约必须产出双线图数据"
        assert chart["dates"], "双线图横轴非空"
        assert len(chart["replay"]) == len(chart["dates"])
        assert len(chart["buyhold"]) == len(chart["dates"])
        assert view["metric_rows"], "指标对照表必须出行"
        assert view["period_rows"], "窗口内应有逐期调仓行（月度定期）"

    def test_flag_off_yields_unavailable_placeholder(self):
        contract = _build_contract(flag_on=False)
        assert contract["available"] is False
        assert re.search(r"[一-鿿]", contract["reason"]), "占位原因必须是中文文案"
        assert contract["prompt_block"] == ""
