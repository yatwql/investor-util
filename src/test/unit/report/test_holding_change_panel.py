"""持仓变动复盘面板（holding_change_panel）测试 — 契约装配 + 双端单源展示。

覆盖（迭代 3 验收）：
  - 契约装配：多期快照 → available/事件计数/指标/样本门槛回显/局限标注
  - 保留期读配置（history.snapshot_retention_days），缺省回退常量
  - 意图对账：决策账本事件只读注入 → aligned 计数；空账本 → 无意图记录口径
  - 展示单源：view 预格式化行携带事件值；「区间净额推断、非逐笔」标注与事件表同现
  - 双端一致：Excel 页签单元格字符串 ⊇/== view 同源行（同一次装配、同一份文本）
  - 关态：data_flag 缺省 False（Excel 显式 False，HTML data_flags 悲观 False），
    隐藏章不消耗连续编号（逐字节回退既有编号面）
  - 开关注册表：holding_change_review 已登记（实验组、默认关、影响报告）
  - 模板接线：partial 存在且被 report_template include，按 section_visible 守卫

测试隔离：conftest `_isolate_sensitive_paths` 把 HISTORY_SNAPSHOT_DIR 与
decision_ledger.jsonl 重定向到 tmp_path；快照 fixture 经 save() 构造，
不触碰真实 data/history/ 与 data/state/。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.python.analysis.holding_change_events import build_holding_change_events
from src.python.config.features import feature_switch_registry, is_feature_enabled
from src.python.core.constants import HISTORY_SNAPSHOT_RETENTION_DAYS, PROJECT_ROOT
from src.python.report.data_status import STATUS_MESSAGES
from src.python.report.holding_change_panel import (
    EVENT_HEADER,
    LIMITATIONS_NOTE,
    LLM_BLOCK_TITLE,
    build_holding_change_panel,
    build_holding_change_view,
    write_holding_change_sheet,
)
from src.python.report.history_snapshot import save
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.usefixtures("offline_external_sources")]

_TMPL_DIR = Path(PROJECT_ROOT) / "src" / "static" / "tmpl"


# ── 辅助构造（与 events 测试同构的 4 期 fixture） ──────────


def _h(code: str, shares: float, price: float) -> SnapshotHolding:
    return SnapshotHolding(
        code=code,
        name=f"{code}基金",
        shares=shares,
        cost_price=price,
        market_value=shares * price,
        daily_pnl=0.0,
        total_pnl=0.0,
        cost_total=shares * price,
    )


def _snap(ts: str, holdings: list[SnapshotHolding]) -> SnapshotData:
    return SnapshotData(
        accounts=(AccountSnapshot(account_name="全部", holdings=tuple(holdings)),),
        total_value=sum(h.market_value for h in holdings),
        total_cost=sum(h.cost_total for h in holdings),
        total_pnl=0.0,
        timestamp=ts,
    )


def _save_four_periods() -> None:
    """P1→P2 加仓；P2→P3 清仓+新增；P3→P4 减仓+清仓（共 5 个事件）。"""
    save(_snap("20260105T090000", [_h("A", 1000, 10), _h("B", 500, 20), _h("C", 200, 50)]))
    save(_snap("20260106T090000", [_h("A", 1200, 10), _h("B", 500, 20), _h("C", 200, 50)]))
    save(_snap("20260107T090000", [_h("A", 1200, 10), _h("C", 200, 50), _h("D", 300, 30)]))
    save(_snap("20260108T090000", [_h("A", 900, 10), _h("D", 300, 30)]))


_FIXED_NOW = datetime(2026, 1, 9, 12, 0, 0)


def _ledger_fixture() -> list[dict]:
    """决策账本事件：20260106 登记 A 加仓方向（落 P1→P2 区间内）→ 对账应 1 条一致。"""
    return [
        {
            "event": "decision",
            "code": "A",
            "report_date": "20260106",
            "direction": 1,
            "carrier": "7",
            "magnitude": "重仓",
        }
    ]


def _sheet_values(ws) -> tuple[list, list[tuple]]:
    """页签 → (首列值列表, 整行元组列表)。"""
    rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
    first_cols = [r[0] for r in rows if r and r[0] is not None]
    return first_cols, rows


# ── 契约装配 ─────────────────────────────────────────────


class TestBuildContract:
    """build_holding_change_panel：快照目录 → 复盘契约。"""

    def test_contract_assembles_from_multi_period_snapshots(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)

        assert contract["available"] is True
        assert contract["reason"] == ""
        assert contract["period_count"] == 4
        assert contract["event_count"] == 5  # 1 加仓 + 清仓/新增×2 + 减仓/清仓×2
        assert contract["snapshot_count"] == 4
        assert contract["metrics"] is not None
        assert contract["limitations_note"] == LIMITATIONS_NOTE
        assert contract["llm_review"] is None
        assert contract["window_start"] == "20260105T090000"
        assert contract["window_end"] == "20260108T090000"

    def test_sample_gate_echoed_and_below_recommendation(self):
        from src.python.analysis.holding_change_events import MIN_REVIEW_EVENTS, MIN_REVIEW_PERIODS

        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        sample = contract["sample"]
        assert sample["min_periods"] == MIN_REVIEW_PERIODS  # 门槛常量同源回显
        assert sample["min_events"] == MIN_REVIEW_EVENTS
        assert sample["periods_ok"] is False  # 4 < 建议 12 期
        assert sample["events_ok"] is False  # 5 < 建议 10 事件
        assert sample["sufficient"] is False

    def test_retention_days_reads_config_with_constant_fallback(self):
        _save_four_periods()
        contract = build_holding_change_panel({"history": {"snapshot_retention_days": 90}}, reference_time=_FIXED_NOW)
        assert contract["retention_days"] == 90
        contract_default = build_holding_change_panel({}, reference_time=_FIXED_NOW)
        assert contract_default["retention_days"] == HISTORY_SNAPSHOT_RETENTION_DAYS

    def test_intent_reconciliation_reads_ledger_events_readonly(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW, ledger_events=_ledger_fixture())
        intent = contract["metrics"]["intent"]
        assert intent["with_intent"] == 1
        assert intent["aligned"] == 1  # A 加仓事件 × 加仓方向 → 一致
        assert intent["divergent"] == 0

    def test_empty_ledger_falls_back_to_no_intent_caliber(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW, ledger_events=[])
        intent = contract["metrics"]["intent"]
        assert intent["with_intent"] == 0
        assert intent["ledger_available"] is False

    def test_build_never_writes_snapshot_files(self):
        _save_four_periods()
        import os

        from src.python.report.history_snapshot import _list_snapshot_files

        def _mtimes() -> dict[str, int]:
            return {f: os.path.getmtime(f) for f in _list_snapshot_files()}

        before = _mtimes()
        assert before, "fixture 快照应已落盘"
        build_holding_change_panel(None, reference_time=_FIXED_NOW)
        assert _mtimes() == before, "持仓变动复盘装配不得改写快照文件"


# ── 展示单源（view） ─────────────────────────────────────


class TestViewSingleSource:
    """build_holding_change_view：契约 → 双端共用预格式化文本。"""

    def test_event_rows_carry_formatted_event_cells(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        view = build_holding_change_view(contract)

        assert view["event_header"] == EVENT_HEADER
        assert len(view["event_rows"]) == contract["event_count"]
        # 首个事件（P1→P2 A 加仓 +200 @10 元）→ 份额 +200.00 / 市值 +2,000.00
        add_row = next(r for r in view["event_rows"] if r[4] == "加仓")
        assert add_row[0] == "01-05" and add_row[1] == "01-06"
        assert add_row[2] == "A基金" and add_row[3] == "A"
        assert add_row[5] == "+200.00"
        assert add_row[6] == "+2,000.00"

    def test_limitations_note_accompanies_event_table(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        view = build_holding_change_view(contract)
        assert view["event_rows"], "有事件才谈得上标注同现"
        assert view["limitations_note"] == LIMITATIONS_NOTE
        assert "非逐笔" in view["limitations_note"]
        assert view["hint_line"], "占位提示行必须存在（样本门槛引导）"

    def test_metrics_lines_carry_caliber_phrases(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        view = build_holding_change_view(contract)
        joined = "\n".join(view["metrics_lines"])
        assert "变动频率" in joined
        assert "结构计数" in joined
        assert "份额变动贡献" in joined and "价格变动贡献" in joined
        assert "≈ 区间市值变化" in joined  # ≈ 容差口径必须随行呈现

    def test_intent_view_summaries_for_both_ledger_states(self):
        _save_four_periods()
        with_ledger = build_holding_change_view(
            build_holding_change_panel(None, reference_time=_FIXED_NOW, ledger_events=_ledger_fixture())
        )
        assert any(r[6] == "一致" for r in with_ledger["intent_rows"])
        assert any("一致 1" in line for line in with_ledger["intent_lines"])

        without_ledger = build_holding_change_view(
            build_holding_change_panel(None, reference_time=_FIXED_NOW, ledger_events=[])
        )
        assert without_ledger["intent_rows"], "空账本仍逐条呈现（无意图记录口径）"
        assert any("无意图记录" in line for line in without_ledger["intent_lines"])
        assert any("决策账本暂无" in line for line in without_ledger["intent_lines"])

    def test_llm_paragraphs_absent_until_injected(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        view = build_holding_change_view(contract)
        assert view["llm_review_paragraphs"] is None

        contract["llm_review"] = "第一段归因。\n\n第二段归因。"
        view2 = build_holding_change_view(contract)
        assert view2["llm_review_paragraphs"] == ["第一段归因。", "第二段归因。"]


# ── Excel 端（与 view 同源） ─────────────────────────────


def _write_sheet(contract: dict | None):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    write_holding_change_sheet(ws, contract)
    return ws


class TestExcelSheetConsistency:
    """Excel 页签与 view 消费同一份预格式化字符串 → 双端逐字节同文。"""

    def test_sheet_rows_match_view_lines_cell_by_cell(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        view = build_holding_change_view(contract)
        ws = _write_sheet(contract)
        first_cols, rows = _sheet_values(ws)

        for line in view["window_lines"] + view["metrics_lines"] + view["intent_lines"]:
            assert line in first_cols, f"页签首列缺少同源行：{line[:40]}"
        assert view["limitations_note"] in first_cols, "「非逐笔」标注必须随事件表写入页签"

        sheet_event_rows = [list(r) for r in rows if r and r[0] and str(r[0]).startswith("0")]
        for cells in view["event_rows"]:
            assert cells in sheet_event_rows, f"页签缺少事件行：{cells}"

    def test_intent_table_rows_written(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW, ledger_events=_ledger_fixture())
        view = build_holding_change_view(contract)
        first_cols, _ = _sheet_values(_write_sheet(contract))
        for cells in view["intent_rows"]:
            assert cells[0] in first_cols  # 区间起落在首列（行整体写入）

    def test_llm_block_written_only_when_injected(self):
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        _, rows_off = _sheet_values(_write_sheet(contract))
        assert not any(LLM_BLOCK_TITLE in str(c) for r in rows_off for c in r if c)

        contract["llm_review"] = "归因段落。"
        first_cols, _ = _sheet_values(_write_sheet(contract))
        assert LLM_BLOCK_TITLE in first_cols


# ── 可见性关态（逐字节回退既有编号面） ─────────────────────


class TestOffStateVisibility:
    """开关关闭（契约缺席）→ 章隐藏且不消耗连续编号，两端缺省口径锁定。"""

    def test_hidden_section_consumes_no_visible_number(self):
        from src.python.core.registry import get_report_section_order
        from src.python.report.html_writer_nav import _compute_section_visibility

        order = get_report_section_order()
        kwargs = dict(
            include_news=True,
            llm_enabled_flag=True,
            holding_change_data=None,  # 开关关闭：键缺席
        )
        visible_numbers, visible_dict, _ = _compute_section_visibility(order, {}, {}, {}, {}, **kwargs)
        assert visible_dict["holding_change"] is False
        assert "holding_change" not in visible_numbers
        # 逐字节回退：隐藏章对既有编号零影响 —— 与「注册表里根本没这一章」时
        # 计算出的可见性/编号完全相等
        order_without = [s for s in order if s["key"] != "holding_change"]
        ref_numbers, _, _ = _compute_section_visibility(order_without, {}, {}, {}, {}, **kwargs)
        assert visible_numbers == ref_numbers
        assert list(visible_numbers.values()) == list(range(1, len(visible_numbers) + 1))

    def test_build_data_availability_defaults_flag_false(self):
        from src.python.report.excel_sheet_factory import build_data_availability

        avail = build_data_availability()
        assert avail["holding_change_data"] is False  # 显式 False（非缺省 True）

        avail_on = build_data_availability(holding_change_data={"available": True})
        assert avail_on["holding_change_data"] is True


# ── 开关注册表 ───────────────────────────────────────────


class TestFeatureSwitchRegistry:
    """holding_change_review 已登记且默认关、影响报告输出。"""

    def test_switch_registered_in_experimental_group_off_by_default(self):
        sw = feature_switch_registry["holding_change_review"]
        assert sw.label == "持仓变动复盘"
        assert sw.group == "experimental"
        assert sw.default is False
        assert sw.affects_report is True
        assert is_feature_enabled("holding_change_review") is False


# ── 模板接线（源码级） ───────────────────────────────────


class TestTemplateWiring:
    """partial 已建且被主模板 include，按 section_visible + view 双守卫。"""

    def test_partial_exists_and_guarded(self):
        partial = (_TMPL_DIR / "partials" / "holding_change_section.html").read_text(encoding="utf-8")
        assert 'section_visible("holding_change")' in partial
        assert "holding_change_view" in partial
        assert "limitations_note" in partial  # 标注经同源 view 渲染
        assert "sec-holding_change" in partial

    def test_main_template_includes_partial(self):
        tmpl = (_TMPL_DIR / "report_template.html").read_text(encoding="utf-8")
        assert '{% include "partials/holding_change_section.html" with context %}' in tmpl
        # include 位于组合演进与基本面快照之间（正文顺序 = 注册表顺序）
        evo_idx = tmpl.index("partials/evolution_section.html")
        hc_idx = tmpl.index("partials/holding_change_section.html")
        fs_idx = tmpl.index("partials/fundamental_snapshot_section.html")
        assert evo_idx < hc_idx < fs_idx


# ── 状态消息占位 ─────────────────────────────────────────


def test_status_message_registered():
    assert "holding_change_unavailable" in STATUS_MESSAGES
    assert build_holding_change_view(None)["reason"] == STATUS_MESSAGES["holding_change_unavailable"]


def test_events_contract_and_panel_agree_on_counts():
    """面板契约与事件层契约计数一致（同一次装配口径，防两层漂移）。"""
    _save_four_periods()
    raw = build_holding_change_events()
    contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
    assert contract["event_count"] == raw["event_count"]
    assert contract["period_count"] == raw["period_count"]
    assert contract["indeterminate_count"] == raw["indeterminate_count"]


# ── 提示词块（轨 1 契约字段）与重排标注 ──────────────────


class TestPromptBlockAndReorder:
    """契约 prompt_block（报告与 LLM 同源）+ 跨品种重排标注。"""

    def test_prompt_block_renders_view_text(self):
        """提示词块与展示视图同源：窗口行/指标行/局限标注均在块内。"""
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)

        block = contract["prompt_block"]
        assert block, "可用契约必须渲染提示词块"
        assert block.startswith("【持仓变动复盘·变动事件清单")
        assert LIMITATIONS_NOTE in block, "局限标注必须进提示词块（与报告展示同文）"
        view = build_holding_change_view(contract)
        assert view["window_lines"][0] in block, "窗口行须与展示同文（单源渲染）"
        assert view["metrics_lines"][0] in block, "指标行须与展示同文（单源渲染）"
        for row in view["event_rows"]:
            assert row[3] in block, "事件代码须出现在提示词明细中"

    def test_prompt_block_empty_when_unavailable(self):
        """契约不可用（快照不足）→ prompt_block == \"\"（附录零贡献，逐字节回退）。"""
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        assert contract["available"] is False
        assert contract["prompt_block"] == ""

    def test_reorder_detected_on_cross_product_reshuffle(self):
        """≥5 品种清仓次日同名新增 → 契约携带重排结构与标注行（账户结构变更口径）。"""
        codes = [f"C{i:04d}" for i in range(6)]
        save(_snap("20260105T090000", [_h(c, 100, 10) for c in codes]))
        save(_snap("20260106T090000", []))
        save(_snap("20260107T090000", [_h(c, 100, 10) for c in codes]))

        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        assert contract["available"] is True
        reorder = contract["reorder"]
        assert reorder is not None
        assert reorder["direction"] == "清仓→新增"
        assert reorder["date"] == "20260106"
        assert reorder["next_date"] == "20260107"
        assert "疑似账户结构重排" in contract["reorder_note"]
        assert "账户/数据结构变更解读" in contract["reorder_note"]
        view = build_holding_change_view(contract)
        assert any("疑似账户结构重排" in line for line in view["window_lines"]), "重排标注须进展示视图"
        assert "疑似账户结构重排" in contract["prompt_block"], "重排标注须进提示词块（归因框架输入）"

    def test_reorder_absent_on_normal_changes(self):
        """常规少量变动 → 无重排标注（门槛不误报）。"""
        _save_four_periods()
        contract = build_holding_change_panel(None, reference_time=_FIXED_NOW)
        assert contract["reorder"] is None
        assert contract["reorder_note"] == ""
        view = build_holding_change_view(contract)
        assert not any("疑似账户结构重排" in line for line in view["window_lines"])
        assert "疑似账户结构重排" not in contract["prompt_block"]

    def test_view_reorder_note_passthrough(self):
        """view 直读契约 reorder_note（字段增补无需改装配器即可展示）。"""
        data = {
            "available": True,
            "reorder_note": "疑似账户结构重排：10-02 → 10-03 间 6 个品种「清仓→新增」同名联动",
        }
        view = build_holding_change_view(
            {
                **data,
                "title_summary": "",
                "window_lines": ["窗口"],
                "event_header": [],
                "event_rows": [],
                "limitations_note": LIMITATIONS_NOTE,
                "metrics": {},
                "intent_header": [],
                "intent_rows": [],
                "intent_lines": [],
                "llm_review": None,
            }
        )
        assert any("疑似账户结构重排" in line for line in view["window_lines"])
