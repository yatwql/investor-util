"""组合演进（多快照趋势聚合）纯计算测试。

覆盖：
  - 快照不足（去重后 < 3 期）→ available=False 降级
  - 同日多快照 → 按日去重（保留当日最后一份）
  - HHI 集中度计算
  - TOP 持仓占比变迁（按末期权重降序 + 跨期缺失补 0）
  - 市值为 0 的旧快照 → 回退成本口径计算权重
  - 账户配置流（市值占比 %）

测试隔离：conftest `_isolate_sensitive_paths` 已将 HISTORY_SNAPSHOT_DIR
重定向到 tmp_path，测试通过 save() 构造快照，不触碰真实数据。
"""

from __future__ import annotations

import pytest

from src.python.analysis.portfolio_evolution import (
    _compute_hhi,
    _dedup_by_date,
    _format_period_label,
    _holding_weight,
    build_evolution_data,
)
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


def _save_multi_account(
    ts: str,
    accounts: list[tuple[str, list[SnapshotHolding]]],
) -> None:
    sd = SnapshotData(
        accounts=tuple(AccountSnapshot(account_name=n, holdings=tuple(hs)) for n, hs in accounts),
        total_value=sum(h.market_value for _n, hs in accounts for h in hs),
        total_cost=sum(h.cost_total for _n, hs in accounts for h in hs),
        total_pnl=0.0,
        timestamp=ts,
    )
    save(sd)


# ── 降级 / 去重 ───────────────────────────────────────────


def test_insufficient_snapshots_returns_unavailable():
    """快照不足（去重后 < 3 期）→ available=False + reason。"""
    _save("20260701T090000", [_holding("a", "A", 100, 90)])
    _save("20260702T090000", [_holding("a", "A", 110, 90)])
    d = build_evolution_data()
    assert d["available"] is False
    assert "快照不足" in d["reason"]
    assert d["snapshot_count"] == 2


def test_dedup_by_date_keeps_latest_per_day():
    """同一自然日多份快照 → 按日去重，保留当日最后一份。"""
    _save("20260701T080000", [_holding("a", "A", 100, 90)])
    _save("20260701T120000", [_holding("a", "A", 105, 90)])
    _save("20260702T090000", [_holding("a", "A", 110, 90)])
    _save("20260703T090000", [_holding("a", "A", 120, 90)])
    d = build_evolution_data()
    assert d["available"] is True
    assert d["periods"] == ["07-01", "07-02", "07-03"]
    # 当日最后一份市值 105 生效
    assert d["total_value"] == [105.0, 110.0, 120.0]


def test_empty_snapshot_dir_unavailable():
    """无快照 → available=False。"""
    d = build_evolution_data()
    assert d["available"] is False
    assert d["snapshot_count"] == 0


# ── 指标计算 ──────────────────────────────────────────────


def test_hhi_computation():
    """HHI = Σ(权重²)；等权 2 品种 → 0.5。"""
    assert _compute_hhi([0.5, 0.5]) == 0.5
    assert _compute_hhi([0.7, 0.2, 0.1]) == pytest.approx(0.54)
    assert _compute_hhi([]) == 0.0


def test_holding_weight_priority_and_fallback():
    """权重优先市值口径，市值为 0 时回退成本口径。"""
    h = _holding("a", "A", 100, 50)
    assert _holding_weight(h, total_mv=200, total_cost=400) == pytest.approx(0.5)
    h2 = _holding("a", "A", 0, 50)
    assert _holding_weight(h2, total_mv=0, total_cost=200) == pytest.approx(0.25)
    h3 = _holding("a", "A", 0, 0)
    assert _holding_weight(h3, total_mv=0, total_cost=0) == 0.0


def test_hhi_series_and_top_holdings_ordering():
    """3 期快照 → HHI 序列 + TOP 持仓按末期权重降序 + 跨期缺失补 0。"""
    _save("20260701T090000", [_holding("a", "A", 60, 60), _holding("b", "B", 40, 40)])
    _save("20260702T090000", [_holding("a", "A", 70, 70), _holding("b", "B", 30, 30)])
    _save("20260703T090000", [_holding("a", "A", 50, 50), _holding("b", "B", 30, 30), _holding("c", "C", 20, 20)])
    d = build_evolution_data()
    assert d["available"] is True
    assert d["hhi"] == [pytest.approx(0.52), pytest.approx(0.58), pytest.approx(0.38)]
    top = d["top_holdings"]
    assert top[0]["code"] == "a"  # 末期权重 50% 最高
    assert top[0]["weights"] == [60.0, 70.0, 50.0]
    assert top[1]["code"] == "b"
    assert top[2]["code"] == "c"
    # c 只在末期出现 → 前两期权重 0，present_count = 1
    assert top[2]["present_count"] == 1
    assert top[2]["weights"] == [0.0, 0.0, 20.0]


def test_cost_fallback_for_legacy_snapshots():
    """旧快照持仓 market_value=0 → 权重回退成本口径。"""
    _save(
        "20260701T090000",
        [_holding("a", "A", 0, 60), _holding("b", "B", 0, 40)],
    )
    _save(
        "20260702T090000",
        [_holding("a", "A", 0, 70), _holding("b", "B", 0, 30)],
    )
    _save(
        "20260703T090000",
        [_holding("a", "A", 0, 80), _holding("b", "B", 0, 20)],
    )
    d = build_evolution_data()
    assert d["available"] is True
    assert d["total_value"] == [0.0, 0.0, 0.0]  # 市值口径不可用
    assert d["top_holdings"][0]["code"] == "a"
    assert d["top_holdings"][0]["weights"][0] == pytest.approx(60.0)


def test_account_flows_multi_account():
    """多账户快照 → 账户配置流（市值占比 %）。"""
    _save_multi_account(
        "20260701T090000",
        [
            ("账户A", [_holding("a", "A", 60, 60)]),
            ("账户B", [_holding("b", "B", 40, 40)]),
        ],
    )
    _save_multi_account(
        "20260702T090000",
        [
            ("账户A", [_holding("a", "A", 50, 50)]),
            ("账户B", [_holding("b", "B", 50, 50)]),
        ],
    )
    _save_multi_account(
        "20260703T090000",
        [
            ("账户A", [_holding("a", "A", 70, 70)]),
            ("账户B", [_holding("b", "B", 30, 30)]),
        ],
    )
    d = build_evolution_data()
    assert d["available"] is True
    flows = d["account_flows"]
    assert flows["账户A"] == [60.0, 50.0, 70.0]
    assert flows["账户B"] == [40.0, 50.0, 30.0]


# ── 工具函数 ──────────────────────────────────────────────


def test_format_period_label():
    """时间戳 → MM-DD 展示标签。"""
    assert _format_period_label("20260701T090000") == "07-01"
    assert _format_period_label("20261231T235959") == "12-31"
    assert _format_period_label("bad") == "bad"


def test_dedup_by_date_helper():
    """去重辅助：同一日期保留最后一份，异日期保序。"""
    from src.python.schemas.history import SnapshotData

    s1 = SnapshotData(accounts=(), total_value=1, total_cost=1, total_pnl=0, timestamp="20260701T080000")
    s2 = SnapshotData(accounts=(), total_value=2, total_cost=1, total_pnl=0, timestamp="20260701T120000")
    s3 = SnapshotData(accounts=(), total_value=3, total_cost=1, total_pnl=0, timestamp="20260702T090000")
    out = _dedup_by_date([s1, s2, s3])
    assert [x.total_value for x in out] == [2.0, 3.0]
