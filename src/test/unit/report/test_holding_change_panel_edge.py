"""持仓变动复盘面板边缘场景（holding_change_panel_edge）— 降级/截断/异常输入。

覆盖（@pytest.mark.edge）：
  - 快照不足 2 期 → available=False + 原因回显，view/页签写占位（同现）
  - 滚动保留截断：窗口起点龄期 ≥ 保留期 → truncated 标注出现（截断事实必须外显）
  - 保留期配置非法（非 int）→ 回退常量，不抛异常
  - llm_review 空串/纯空白 → 归因段落不出现（降级不产出空块）
  - window_start/end 不可解析 → 截断判定与跨度不虚构（0/不截断）
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.python.core.constants import HISTORY_SNAPSHOT_RETENTION_DAYS
from src.python.report.holding_change_panel import (
    TRUNCATION_SLACK_DAYS,
    build_holding_change_panel,
    build_holding_change_view,
    write_holding_change_sheet,
)
from src.python.report.history_snapshot import save
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_report,
    pytest.mark.edge,
    pytest.mark.usefixtures("offline_external_sources"),
]


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


class TestInsufficientSnapshots:
    """快照不足 → 双端占位同现（契约 reason == view reason == 页签文本）。"""

    def test_single_snapshot_degrades_to_placeholder(self):
        save(_snap("20260105T090000", [_h("A", 1000, 10)]))
        contract = build_holding_change_panel(None, reference_time=datetime(2026, 1, 6, 12, 0, 0))

        assert contract["available"] is False
        assert contract["reason"], "降级必须给出原因"
        assert contract["metrics"] is None

        view = build_holding_change_view(contract)
        assert view["available"] is False
        assert view["reason"] == contract["reason"]
        assert view["hint_line"]

        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        write_holding_change_sheet(ws, contract)
        cells = [str(c) for r in ws.iter_rows(values_only=True) for c in r if c]
        assert any(contract["reason"] in c for c in cells), "页签占位须回显同一 reason"

    def test_none_contract_renders_default_status_message(self):
        view = build_holding_change_view(None)
        assert view["available"] is False
        assert view["window_lines"] == [] and view["event_rows"] == []


class TestTruncationAnnotation:
    """滚动保留截断：窗口起点龄期越过保留期 → 标注必须出现（缺失即红）。"""

    def _two_periods(self):
        save(_snap("20260105T090000", [_h("A", 1000, 10)]))
        save(_snap("20260106T090000", [_h("A", 1100, 10)]))

    def test_window_beyond_retention_marks_truncated(self):
        self._two_periods()
        retention = HISTORY_SNAPSHOT_RETENTION_DAYS
        # 参考时间推到窗口起点之后 retention+10 天 → 必然越过判定线
        contract = build_holding_change_panel(
            None,
            reference_time=datetime(2026, 1, 5) + timedelta(days=retention + 10),
        )
        assert contract["truncated"] is True
        assert "保留" in contract["truncation_note"]
        view = build_holding_change_view(contract)
        assert any("保留" in line for line in view["window_lines"]), "截断标注必须进入展示行"

    def test_window_within_retention_not_truncated(self):
        self._two_periods()
        contract = build_holding_change_panel(None, reference_time=datetime(2026, 1, 8, 12, 0, 0))
        assert contract["truncated"] is False
        assert contract["truncation_note"] == ""

    def test_slack_constant_positive(self):
        assert TRUNCATION_SLACK_DAYS >= 0


class TestBadConfigAndTimestamps:
    """非法配置/时间戳 → 回退或保底，绝不抛异常、不虚构数值。"""

    def test_non_int_retention_falls_back_to_constant(self):
        save(_snap("20260105T090000", [_h("A", 1000, 10)]))
        save(_snap("20260106T090000", [_h("A", 1100, 10)]))
        contract = build_holding_change_panel(
            {"history": {"snapshot_retention_days": "not-a-number"}},
            reference_time=datetime(2026, 1, 8, 12, 0, 0),
        )
        assert contract["retention_days"] == HISTORY_SNAPSHOT_RETENTION_DAYS

    def test_unparseable_window_keeps_zero_span_without_truncation(self):
        contract = build_holding_change_panel(None, reference_time=datetime(2026, 1, 9))
        contract["available"] = True  # 仅构造展示面：窗口字段保持不可解析
        contract["window_start"] = "not-a-timestamp"
        contract["window_end"] = ""
        view = build_holding_change_view(contract)
        assert view["available"] is True  # 展示面不因窗口解析失败而整体降级
        # 截断/跨度字段保持装配期保守值
        assert contract["window_span_days"] == 0
        assert contract["truncated"] is False


class TestEmptyLlmReview:
    """llm_review 空文本 → 归因段落缺席（降级不产出空块，两分支同现判据）。"""

    def test_blank_review_produces_no_paragraphs(self):
        save(_snap("20260105T090000", [_h("A", 1000, 10)]))
        save(_snap("20260106T090000", [_h("A", 1100, 10)]))
        contract = build_holding_change_panel(None, reference_time=datetime(2026, 1, 8))
        contract["llm_review"] = "   \n\n  "
        view = build_holding_change_view(contract)
        assert view["llm_review_paragraphs"] is None
