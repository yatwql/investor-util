"""快照差异摘要（自上次快照变化）纯计算测试。

覆盖：
  - 数据不足（去重后 < 2 期，无上次快照）→ available=False 降级占位
  - 两次快照差异：新增/移除品种检测
  - 集中度 HHI 变化计算（本期 - 上期）
  - 超警戒线品种检测（复用 15% 阈值）与按权重降序
  - 完全相同快照 → 摘要报告"持平"
  - summary 摘要文本覆盖所有变化点
  - 市值为 0 的旧快照 → 回退成本口径计算权重
  - 同日多快照 → 按日去重后仍可对比（保留当日最后一份）

测试隔离：conftest `_isolate_sensitive_paths` 已将 HISTORY_SNAPSHOT_DIR
重定向到 tmp_path，测试通过 save() 构造快照，不触碰真实数据。
"""

from __future__ import annotations

import pytest

from src.python.analysis.snapshot_diff import build_snapshot_diff
from src.python.report.history_snapshot import save
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


# ── 辅助构造 ──────────────────────────────────────────────


def _holding(code: str, name: str, mv: float, cost: float) -> SnapshotHolding:
    return SnapshotHolding(
        code=code,
        name=name,
        shares=0.0,
        cost_price=0.0,
        market_value=mv,
        daily_pnl=0.0,
        total_pnl=0.0,
        cost_total=cost,
    )


def _save(ts: str, holdings: list[SnapshotHolding], account: str = "全部") -> None:
    sd = SnapshotData(
        accounts=(AccountSnapshot(account_name=account, holdings=tuple(holdings)),),
        total_value=sum(h.market_value for h in holdings),
        total_cost=sum(h.cost_total for h in holdings),
        total_pnl=sum(h.total_pnl for h in holdings),
        timestamp=ts,
    )
    save(sd)


def _equal_eight() -> list[SnapshotHolding]:
    """8 个等权持仓（各 12.5% < 15% 警戒线），用于「无变化」场景。"""
    codes = [chr(ord("a") + i) for i in range(8)]
    return [_holding(c, f"{c}基金", 125.0, 100.0) for c in codes]


# ── 数据不足占位 ──────────────────────────────────────────


def test_single_snapshot_returns_unavailable_placeholder():
    """无上次快照可对比 → available=False 降级，不崩溃。"""
    _save("20260701T090000", [_holding("A", "A基金", 5000, 4000)])
    data = build_snapshot_diff()
    assert data["available"] is False
    assert "快照差异不足" in data["reason"]
    assert data["summary"] == ""
    assert data["hhi_change"] is None
    assert data["added"] == []
    assert data["removed"] == []


# ── 差异计算：新增/移除 ────────────────────────────────────


def test_two_snapshots_added_removed_detected():
    """上期 A/B → 本期 B/C：新增 C、移除 A。"""
    _save("20260701T090000", [_holding("A", "A基金", 5000, 4000), _holding("B", "B基金", 5000, 4000)])
    _save("20260702T090000", [_holding("B", "B基金", 6000, 4000), _holding("C", "C基金", 4000, 3000)])
    data = build_snapshot_diff()
    assert data["available"] is True
    assert data["added"] == [{"code": "C", "name": "C基金"}]
    assert data["removed"] == [{"code": "A", "name": "A基金"}]


# ── 集中度 HHI 变化 ───────────────────────────────────────


def test_concentration_hhi_change_computed():
    """权重 5:5 → 7:3：HHI 0.50 → 0.58，变化 +0.08。"""
    _save("20260701T090000", [_holding("A", "A基金", 5000, 4000), _holding("B", "B基金", 5000, 4000)])
    _save("20260702T090000", [_holding("A", "A基金", 7000, 4000), _holding("B", "B基金", 3000, 4000)])
    data = build_snapshot_diff()
    assert data["hhi_previous"] == pytest.approx(0.50, abs=1e-6)
    assert data["hhi_current"] == pytest.approx(0.58, abs=1e-6)
    assert data["hhi_change"] == pytest.approx(0.08, abs=1e-6)
    assert "更集中" in data["summary"]


# ── 超警戒线品种 ──────────────────────────────────────────


def test_over_limit_holdings_detected_and_sorted_desc():
    """18% / 82% / 0%：B(82%)、A(18%) 超 15% 警戒线，按权重降序。"""
    _save(
        "20260701T090000",
        [_holding("A", "A基金", 5000, 4000), _holding("B", "B基金", 5000, 4000)],
    )
    _save(
        "20260702T090000",
        [
            _holding("A", "A基金", 1800, 1000),
            _holding("B", "B基金", 8200, 1000),
            _holding("C", "C基金", 0, 0),  # 市值/成本均 0 → 权重 0，不超限
        ],
    )
    data = build_snapshot_diff()
    over = data["over_limit"]
    assert [o["code"] for o in over] == ["B", "A"]
    assert over[0]["weight_pct"] == 82.0
    assert over[0]["threshold_pct"] == 15.0
    assert over[1]["weight_pct"] == 18.0


# ── 无变化场景 ────────────────────────────────────────────


def test_identical_snapshots_report_flat():
    """两期完全相同的 8 等权持仓：无新增/移除/超限，HHI 持平。"""
    _save("20260701T090000", _equal_eight())
    _save("20260702T090000", _equal_eight())
    data = build_snapshot_diff()
    assert data["added"] == []
    assert data["removed"] == []
    assert data["over_limit"] == []
    assert data["hhi_previous"] == pytest.approx(0.125, abs=1e-6)
    assert data["hhi_change"] == pytest.approx(0.0, abs=1e-6)
    assert "持平" in data["summary"]


# ── summary 覆盖所有变化点 ────────────────────────────────


def test_summary_lists_all_change_points():
    """一次快照覆盖新增/移除/HHI/超限全部变化点，摘要逐项列出。"""
    _save("20260701T090000", [_holding("A", "A基金", 5000, 4000), _holding("B", "B基金", 5000, 4000)])
    _save(
        "20260702T090000",
        [
            _holding("B", "B基金", 3000, 2000),
            _holding("C", "C基金", 6000, 2000),
            _holding("D", "D基金", 1000, 2000),
        ],
    )
    data = build_snapshot_diff()
    summary = data["summary"]
    assert "新增 2 个品种" in summary and "C基金" in summary and "D基金" in summary
    assert "移除 1 个品种" in summary and "A基金" in summary
    assert "集中度 HHI" in summary
    assert "超 15% 警戒线品种 2 个" in summary
    assert data["hhi_current"] == pytest.approx(0.46, abs=1e-6)


# ── 成本口径回退 ──────────────────────────────────────────


def test_cost_fallback_when_market_value_zero():
    """市值为 0 的旧快照 → 回退成本口径计算 HHI 与超限项。"""
    _save(
        "20260701T090000",
        [_holding("A", "A基金", 0, 4000), _holding("B", "B基金", 0, 6000)],
    )
    _save(
        "20260702T090000",
        [_holding("A", "A基金", 0, 2000), _holding("B", "B基金", 0, 8000)],
    )
    data = build_snapshot_diff()
    assert data["hhi_previous"] == pytest.approx(0.52, abs=1e-6)
    assert data["hhi_current"] == pytest.approx(0.68, abs=1e-6)
    assert [o["code"] for o in data["over_limit"]] == ["B", "A"]


# ── 同日去重 ──────────────────────────────────────────────


def test_same_date_multiple_snapshots_dedup_keeps_last():
    """同日两份快照按日去重保留最后一份，跨日对比仍可用。"""
    _save("20260701T080000", [_holding("A", "A基金", 5000, 4000), _holding("B", "B基金", 5000, 4000)])
    _save("20260701T120000", [_holding("A", "A基金", 7000, 4000), _holding("B", "B基金", 3000, 4000)])
    _save("20260702T090000", [_holding("A", "A基金", 8000, 4000), _holding("B", "B基金", 2000, 4000)])
    data = build_snapshot_diff()
    assert data["snapshot_count"] == 3  # 原始文件数
    assert data["previous_date"] == "07-01"
    assert data["current_date"] == "07-02"
    # 上期为 07-01 最后一份（HHI 0.58），而非当日第一份（0.50）
    assert data["hhi_previous"] == pytest.approx(0.58, abs=1e-6)
    assert data["hhi_current"] == pytest.approx(0.68, abs=1e-6)
