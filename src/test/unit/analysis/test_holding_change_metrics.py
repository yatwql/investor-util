"""持仓变动指标纯计算（holding_change_metrics）测试 — 手算对照与恒等式。

覆盖（迭代验收）：
  - 频率：期均事件数 / 窗口交易日数 / 日均事件数（手算对照，容差 0）
  - 结构计数：五类动作计数 + 触及品种数（手算对照）
  - 贡献分解：份额变动贡献 + 价格变动贡献 逐事件手算对照（容差 0），
    且两分量之和 = 区间市值变化（恒等式断言）
  - 意图对账：一致/分歧/无意图/持平分歧逐行手算对照；settlement 事件不计入意图
  - 意图对账只读：账本事件不被改写、账本写入 API 不被触碰
  - 空事件表 → 五类计数键恒齐全、指标为零而非异常

交易日历属附带依赖（区间天数口径），模块级声明离线：日历回退「排除周六日」
口径，2026-01-05(周一)~2026-01-08(周四) 手算 = 3 个交易日。
"""

from __future__ import annotations

import copy

import pytest

from src.python.analysis.holding_change_events import extract_change_events
from src.python.analysis.holding_change_metrics import (
    ACTION_KEYS,
    ALIGN_ALIGNED,
    ALIGN_DIVERGENT,
    ALIGN_MIXED,
    ALIGN_NO_INTENT,
    build_intent_reconciliation,
    compute_holding_change_metrics,
)
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_analysis,
    pytest.mark.usefixtures("offline_external_sources"),
]


# ── 辅助构造 ──────────────────────────────────────────────


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


def _four_period_events() -> dict:
    """与手算基准同源的 4 期事件表（价格恒定，份额驱动全部变动）。"""
    seq = [
        _snap("20260105T090000", [_h("A", 1000, 10), _h("B", 500, 20), _h("C", 200, 50)]),
        _snap("20260106T090000", [_h("A", 1200, 10), _h("B", 500, 20), _h("C", 200, 50)]),
        _snap("20260107T090000", [_h("A", 1200, 10), _h("C", 200, 50), _h("D", 300, 30)]),
        _snap("20260108T090000", [_h("A", 900, 10), _h("D", 300, 30)]),
    ]
    return extract_change_events(seq)


def _ledger_fixture() -> list[dict]:
    """决策账本事件（含一条 settlement，验证其不计入意图侧）。"""
    return [
        {
            "event": "decision",
            "decision_id": "d1",
            "code": "A",
            "name": "A基金",
            "report_date": "2026-01-06",
            "direction": 1,
            "carrier": "expert_review",
            "magnitude": "high",
            "status": "pending",
        },
        {
            "event": "decision",
            "decision_id": "d2",
            "code": "B",
            "name": "B基金",
            "report_date": "2026-01-07",
            "direction": 1,
            "carrier": "rebalance",
            "magnitude": "mid",
            "status": "pending",
        },
        {
            "event": "decision",
            "decision_id": "d3",
            "code": "C",
            "name": "C基金",
            "report_date": "2026-01-08",
            "direction": 0,
            "carrier": "discipline",
            "magnitude": "low",
            "status": "pending",
        },
        {"event": "settlement", "decision_id": "d1", "settle_date": "2026-01-12", "outcome": "hit"},
    ]


def _metrics(events_data: dict, ledger: list[dict] | None = None) -> dict:
    return compute_holding_change_metrics(
        events_data["events"],
        period_count=events_data["period_count"],
        window_start=events_data["window_start"],
        window_end=events_data["window_end"],
        ledger_events=ledger,
    )


# ── 频率手算对照 ──────────────────────────────────────────


def test_frequency_hand_computed():
    """5 事件 / 4 期 = 1.25；窗口 01-05~01-08 = 3 交易日；日均 round(5/3,2)=1.67。"""
    m = _metrics(_four_period_events())
    assert m["event_count"] == 5
    assert m["period_count"] == 4
    assert m["events_per_period"] == 1.25
    assert m["trading_days"] == 3
    assert m["events_per_trading_day"] == 1.67


# ── 结构计数手算对照 ──────────────────────────────────────


def test_action_counts_and_distinct_codes_hand_computed():
    """4 期事件：新增 1 / 加仓 1 / 减仓 1 / 清仓 2 / 不可判定 0；触及品种 4。"""
    m = _metrics(_four_period_events())
    assert m["action_counts"] == {"新增": 1, "加仓": 1, "减仓": 1, "清仓": 2, "不可判定": 0}
    assert m["distinct_codes"] == 4


# ── 贡献分解手算对照 + 恒等式 ──────────────────────────────


def test_contribution_price_move_hand_computed_with_identity():
    """价格与份额同变的两事件：份额/价格分量逐项手算，两分量之和 = 市值变化。"""
    seq = [
        _snap("20260105T090000", [_h("A", 1000, 10), _h("B", 500, 20)]),  # A 10000, B 10000
        _snap("20260106T090000", [_h("A", 1500, 12), _h("B", 400, 18)]),  # A 18000, B 7200
    ]
    data = extract_change_events(seq)
    m = compute_holding_change_metrics(
        data["events"],
        period_count=data["period_count"],
        window_start=data["window_start"],
        window_end=data["window_end"],
    )
    # A: 份额分量 (1500-1000)×10 = 5000；价格分量 1500×(12-10) = 3000；ΔMV = 8000
    # B: 份额分量 (400-500)×20 = -2000；价格分量 400×(18-20) = -800；ΔMV = -2800
    c = m["contribution"]
    assert c["shares_part"] == 3000.0
    assert c["price_part"] == 2200.0
    assert c["market_value_change"] == 5200.0
    assert c["shares_part"] + c["price_part"] == c["market_value_change"]
    assert c["skipped_count"] == 0


def test_contribution_identity_over_full_window():
    """价格恒定的 4 期序列：全部分量落份额轴，两分量之和 = 区间市值变化（恒等式）。"""
    m = _metrics(_four_period_events())
    c = m["contribution"]
    # A: +2000 与 -3000；D: +9000；B: -10000；C: -10000 → 合计 -12000（价格轴全 0）
    assert c["shares_part"] == -12000.0
    assert c["price_part"] == 0.0
    assert c["market_value_change"] == -12000.0
    assert c["shares_part"] + c["price_part"] == c["market_value_change"]


def test_indeterminate_event_skipped_in_contribution():
    """份额不可判定事件不参与分解（计入 skipped），分量仅覆盖可判定事件。"""
    seq = [
        _snap("20260105T090000", [_h("A", 1000, 10), _h("B", 500, 20)]),
        _snap(
            "20260106T090000",
            [
                SnapshotHolding(code="A", name="A基金", shares=float("nan"), cost_price=10.0, market_value=15000.0),
                _h("B", 500, 20),
            ],
        ),
    ]
    data = extract_change_events(seq)
    m = compute_holding_change_metrics(
        data["events"],
        period_count=data["period_count"],
        window_start=data["window_start"],
        window_end=data["window_end"],
    )
    c = m["contribution"]
    assert m["action_counts"]["不可判定"] == 1
    assert c["skipped_count"] == 1
    assert c["shares_part"] == 0.0
    assert c["price_part"] == 0.0
    assert c["market_value_change"] == 0.0


# ── 意图对账手算对照 ──────────────────────────────────────


def test_intent_reconciliation_hand_computed_rows():
    """一致（A 加仓×加仓意图）/ 分歧（B 清仓×加仓意图、C 清仓×持平意图）/
    无意图（D 新增、A 减仓窗口外）逐行对照；settlement 不计入意图侧。"""
    data = _four_period_events()
    m = _metrics(data, _ledger_fixture())
    intent = m["intent"]
    assert intent["ledger_available"] is True
    assert intent["decision_count"] == 3
    assert intent["with_intent"] == 3
    assert intent["aligned"] == 1
    assert intent["divergent"] == 2

    by_key = {(r["code"], r["action"]): r for r in intent["rows"]}
    assert by_key[("A", "加仓")]["alignment"] == ALIGN_ALIGNED
    assert by_key[("A", "加仓")]["intent"] == "加仓意图"
    assert by_key[("A", "加仓")]["decisions"][0]["carrier"] == "expert_review"
    assert by_key[("B", "清仓")]["alignment"] == ALIGN_DIVERGENT
    assert by_key[("B", "清仓")]["intent"] == "加仓意图"
    assert by_key[("C", "清仓")]["alignment"] == ALIGN_DIVERGENT
    assert by_key[("C", "清仓")]["intent"] == "持平意图"
    assert by_key[("D", "新增")]["alignment"] == ALIGN_NO_INTENT
    # A 减仓区间 01-07~01-08：d1 登记于 01-06 落在窗口外 → 不构成意图
    assert by_key[("A", "减仓")]["alignment"] == ALIGN_NO_INTENT


def test_mixed_directions_unscored_as_mixed():
    """同区间多空意图并存 → 混合意图（不计一致/分歧）。"""
    events = [
        {
            "code": "A",
            "name": "A基金",
            "action": "加仓",
            "shares_diff": 100.0,
            "period_from": "20260105T090000",
            "period_to": "20260106T090000",
            "indeterminate": False,
        }
    ]
    ledger = [
        {"event": "decision", "code": "A", "report_date": "2026-01-05", "direction": 1, "carrier": "expert_review"},
        {"event": "decision", "code": "A", "report_date": "2026-01-06", "direction": -1, "carrier": "rebalance"},
    ]
    intent = build_intent_reconciliation(events, ledger)
    assert intent["rows"][0]["alignment"] == ALIGN_MIXED
    assert intent["rows"][0]["intent"] == "多空并存"
    assert intent["aligned"] == 0
    assert intent["divergent"] == 0
    assert intent["with_intent"] == 1


def test_empty_ledger_yields_no_intent_rows_not_errors():
    """账本空 → 全部「无意图记录」、ledger_available=False（对账列表仍呈现）。"""
    m = _metrics(_four_period_events(), [])
    intent = m["intent"]
    assert intent["ledger_available"] is False
    assert intent["decision_count"] == 0
    assert all(r["alignment"] == ALIGN_NO_INTENT for r in intent["rows"])
    assert intent["rows"][0]["decisions"] == []


# ── 意图对账只读（不回写账本） ─────────────────────────────


def test_intent_reconciliation_never_writes_ledger(monkeypatch):
    """对账全程只读：账本事件原样不动，写入 API 被触碰即失败。"""
    from src.python.core import decision_ledger

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("意图对账不得回写决策账本")

    monkeypatch.setattr(decision_ledger, "append_decision", _forbidden)
    monkeypatch.setattr(decision_ledger, "append_settlement", _forbidden)
    monkeypatch.setattr(decision_ledger, "_append_event_atomic", _forbidden)

    ledger = _ledger_fixture()
    before = copy.deepcopy(ledger)
    build_intent_reconciliation(_four_period_events()["events"], ledger)
    assert ledger == before


# ── 空事件表 ──────────────────────────────────────────────


def test_empty_events_metrics_zero_not_error():
    """空事件表 → 指标为零、五类计数键恒齐全（渲染层有稳定形状可消费）。"""
    data = extract_change_events([])
    m = compute_holding_change_metrics(
        data["events"],
        period_count=data["period_count"],
        window_start=data["window_start"] or "",
        window_end=data["window_end"] or "",
    )
    assert m["event_count"] == 0
    assert m["events_per_period"] == 0.0
    assert m["trading_days"] == 0
    assert m["events_per_trading_day"] == 0.0
    assert set(m["action_counts"]) == set(ACTION_KEYS)
    assert all(v == 0 for v in m["action_counts"].values())
    assert m["distinct_codes"] == 0
    assert m["contribution"]["skipped_count"] == 0


# ── 跨品种同日重排识别（账户/数据结构变更签名） ──────────


class TestDetectAccountReorder:
    """detect_account_reorder：两种形态 + 门槛 + 空输入。"""

    @staticmethod
    def _ev(code: str, action: str, period_to: str) -> dict:
        return {
            "code": code,
            "name": f"{code}基金",
            "action": action,
            "shares_before": 0.0,
            "shares_after": 100.0,
            "price_before": 10.0,
            "price_after": 10.0,
            "market_value_change": 0.0,
            "period_from": "20260105T090000",
            "period_to": period_to,
            "indeterminate": False,
        }

    def test_detect_clear_then_add_same_codes(self):
        """形态 ①：日 D 六品种清仓 → 次日同名新增（≥5 品种联动）→ 命中。"""
        from src.python.analysis.holding_change_metrics import detect_account_reorder

        codes = [f"00000{i}" for i in range(6)]
        events = [self._ev(c, "清仓", "20260106T090000") for c in codes]
        events += [self._ev(c, "新增", "20260107T090000") for c in codes]

        hit = detect_account_reorder(events)
        assert hit is not None
        assert hit["direction"] == "清仓→新增"
        assert hit["date"] == "20260106"
        assert hit["next_date"] == "20260107"
        assert hit["count"] == 6
        assert set(hit["codes"]) == set(codes)

    def test_detect_add_then_clear_interlude(self):
        """形态 ②：单日过桥——日 D 新增 → 次日同名清仓（无形态 ① 时命中）。"""
        from src.python.analysis.holding_change_metrics import detect_account_reorder

        codes = [f"00000{i}" for i in range(5)]
        events = [self._ev(c, "新增", "20260106T090000") for c in codes]
        events += [self._ev(c, "清仓", "20260107T090000") for c in codes]

        hit = detect_account_reorder(events)
        assert hit is not None
        assert hit["direction"] == "新增→清仓"
        assert hit["count"] == 5

    def test_below_threshold_is_not_reorder(self):
        """联动品种 < 5 → 常规调仓，不标注。"""
        from src.python.analysis.holding_change_metrics import detect_account_reorder

        codes = [f"00000{i}" for i in range(4)]
        events = [self._ev(c, "清仓", "20260106T090000") for c in codes]
        events += [self._ev(c, "新增", "20260107T090000") for c in codes]
        assert detect_account_reorder(events) is None

    def test_empty_events_returns_none(self):
        from src.python.analysis.holding_change_metrics import detect_account_reorder

        assert detect_account_reorder([]) is None

    def test_same_day_actions_not_reorder(self):
        """同日联动但无次日对应（仅清仓无新增）→ 不构成重排形态。"""
        from src.python.analysis.holding_change_metrics import detect_account_reorder

        codes = [f"00000{i}" for i in range(6)]
        events = [self._ev(c, "清仓", "20260106T090000") for c in codes]
        assert detect_account_reorder(events) is None
