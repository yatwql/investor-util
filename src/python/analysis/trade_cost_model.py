"""调仓交易成本模型（trade_cost_model）— 纯计算模块。

给定 What-if 变动明细（买入/卖出腿）、申赎费率表与持仓批次，估算调仓
一次性交易成本（基金申购费 + 赎回费），供「交易成本对比」面板消费；
不联网、不读盘、不 import report/（analysis 层单向依赖纪律），交易日计数
经调用方注入（唯一实现 `core/trading_calendar.py`）。

**口径（唯一依据，先决门槛②判定，设计文档 §16 记录）**：

  - **赎回费按份额持有期先进先出（FIFO）逐批判档**。批次（lots）来自本机
    持仓快照历史重放（:func:`rebuild_position_lots`：期初份额 = 期初批，
    后续份额增加 = 新批次，份额减少自最早批次起消耗）——持仓文件无买卖日期，
    逐笔批次只能由快照差分重建；期初批的建仓日 = 历史首见日，是**下界估计**
    （真实持有期可能更长、对应费率可能更低），报告须随数字标注。
  - **持有期一律以交易日计**（设计红线 / 架构约束 C25 字面口径，用户拍板）：
    调用方注入交易日计数；**档位边界数值直接按交易日解释**，来源文本中的
    「N年」标签按 `TRADING_DAYS_PER_YEAR`（250 交易日/年）折算。该口径使持有期
    数值偏短、命中更高费率档，成本估计**偏保守（偏高）**——已知且有意。
  - **金额口径 = 成本价**（份额 × 每份成本），与 What-if 全模块的成本口径一致；
    真实申购按申购金额、赎回按赎回净值计费，差额随盈亏比例变动，如实标注。
  - **申购费入账日 = 调仓生效日**（各腿 `booked_date`），与「申购费计入买入日」
    验收一致；未指定生效日时持有期计算截止日由调用方给定（`holding_end_date`）。
  - **场内品种（股票 / 场内基金）不建模**：由调用方归入 `unmodeled_codes`，
    显式标注「交易成本未建模（佣金/印花税等另计）」，不冒充 0 费率。
  - **降级不留伪精度**：费率来源缺失的腿 `rate/fee=None` 并计数
    （`unknown_legs`），`fees_complete=False`——费率未知不出成本后数字；
    来源明确为 0 的零费率是**已知 0**，照常计入（与未知严格区分）。
"""

from __future__ import annotations

import math
from typing import Any, Callable

from src.python.analysis.fee_schedule_model import (
    SRC_CONFIG,
    SRC_F10,
    SRC_TABLE_SINGLE,
    SRC_UNKNOWN,
    SRC_UNMODELED,
    TRADING_DAYS_PER_YEAR,
    build_config_fee_schedules,
    build_single_purchase_schedule,
    parse_fee_percent,
    parse_purchase_fee_schedule,
    parse_redemption_fee_schedule,
    purchase_fee,
    select_purchase_tier,
    select_redemption_tier,
)
from src.python.analysis.portfolio_evolution import _dedup_by_date

# ── 常量 ────────────────────────────────────────────────

_SHARES_EPS = 1e-3
"""份额比较容差（与 holding_change_events._SHARES_EPS 同值）。"""

#: 交易日计数注入类型：(start, end) → 经过的交易日数（YYYY-MM-DD）
TradingDayCounter = Callable[[str, str], int | None]

# 腿侧别与费率来源枚举（报告层展示与测试断言的唯一取值）
SIDE_BUY = "buy"
SIDE_SELL = "sell"
SIDE_UNMODELED = "unmodeled"

_BUY_ACTIONS = frozenset({"新增", "加仓"})
_SELL_ACTIONS = frozenset({"清仓", "减仓"})


# ── 持仓批次重放 ────────────────────────────────────────


def rebuild_position_lots(snapshots: list[Any]) -> dict[str, list[dict[str, Any]]]:
    """持仓快照序列 → 当前持仓的 FIFO 批次表（纯内存重放，零 I/O）。

    规则（与先决门槛②「快照事件 FIFO」一致）：
      - 按日去重后逐期推进；**首次出现 = 期初批**（建仓日 = 首见日，真实建仓
        可能更早 → 下界估计）；
      - 份额较上期**增加** → 追加新批次（建仓日 = 本期日期）；
      - 份额**减少** → 自最早批次起 FIFO 消耗；
      - 持仓在本期缺席 → 视为清仓（全部消耗），此后再现按新批次；
      - 份额字段缺失/非有限 → 沿用上期份额（不猜方向，批次不动）。

    Args:
        snapshots: 快照列表（乱序自动按时间戳排序；同日多份保留最后一份）

    Returns:
        ``{code: [{"start_date": "YYYY-MM-DD", "shares": float}, ...]}``
        （按建仓日升序，仅含余量 > 容差的批次；无历史 → 空 dict）
    """
    if not snapshots:
        return {}
    periods = _dedup_by_date(sorted(snapshots, key=lambda sd: sd.timestamp or ""))
    lots: dict[str, list[dict[str, Any]]] = {}
    prev: dict[str, float] = {}

    for sd in periods:
        date = _period_date(sd.timestamp)
        if not date:
            continue
        curr: dict[str, float] = {}
        invalid: set[str] = set()
        for acc in getattr(sd, "accounts", ()) or ():
            for h in getattr(acc, "holdings", ()) or ():
                code = (getattr(h, "code", "") or "").strip()
                if not code:
                    continue
                shares = getattr(h, "shares", None)
                if not _finite(shares):
                    invalid.add(code)
                    continue
                curr[code] = curr.get(code, 0.0) + float(shares)
        # 份额字段无效的代码：有上期值则沿用（不可判定 ≠ 清仓），无则不建批
        for code in invalid:
            if code in prev:
                curr[code] = prev[code]

        for code in set(prev) | set(curr):
            p = prev.get(code, 0.0)
            if code not in curr:
                _consume_fifo(lots.setdefault(code, []), p)  # 本期缺席 = 清仓
                continue
            c = curr[code]
            if code not in prev:
                if c > _SHARES_EPS:  # 首次出现（期初或期中新增）→ 新批次
                    lots.setdefault(code, []).append({"start_date": date, "shares": c})
            elif c > p + _SHARES_EPS:
                lots.setdefault(code, []).append({"start_date": date, "shares": c - p})
            elif c < p - _SHARES_EPS:
                _consume_fifo(lots.setdefault(code, []), p - c)
        prev = curr

    return {
        code: [lot for lot in code_lots if lot["shares"] > _SHARES_EPS]
        for code, code_lots in lots.items()
        if any(lot["shares"] > _SHARES_EPS for lot in code_lots)
    }


def _period_date(timestamp: str | None) -> str:
    """快照时间戳 → 日期（YYYY-MM-DD）；支持紧凑 YYYYMMDDTHHMMSS 与
    ISO YYYY-MM-DD… 两种形态；无效 → ""。"""
    ts = (timestamp or "").strip()
    if len(ts) >= 10 and ts[4] == "-" and ts[:10].replace("-", "").isdigit():
        return ts[:10]
    if len(ts) >= 8 and ts[:8].isdigit():
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
    return ""


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _consume_fifo(code_lots: list[dict[str, Any]], shares: float) -> None:
    """自最早批次起 FIFO 扣减 ``shares``（就地修改，余量 ≤ 容差的批次移除）。"""
    remain = shares
    kept: list[dict[str, Any]] = []
    for lot in code_lots:
        if remain <= _SHARES_EPS:
            kept.append(lot)
            continue
        if lot["shares"] > remain + _SHARES_EPS:
            lot["shares"] = round(lot["shares"] - remain, 6)
            kept.append(lot)
            remain = 0.0
        else:
            remain -= lot["shares"]
    # remain > 容差（消耗量超过已知批次）：保留尽力扣减结果，余缺由上层判未知
    code_lots[:] = [lot for lot in kept if lot["shares"] > _SHARES_EPS]


def consume_fifo_shares(code_lots: list[dict[str, Any]], shares: float) -> None:
    """FIFO 批次扣减公共出口（与 ``_consume_fifo`` 同源，多期回放推进模拟批次时复用）。

    语义与内部实现逐字一致：自最早批次起就地扣减，余量 ≤ 容差的批次移除。
    """
    _consume_fifo(code_lots, shares)


def _consume_lots(
    code_lots: list[dict[str, Any]],
    shares: float,
) -> tuple[list[tuple[dict[str, Any], float]], bool]:
    """FIFO 模拟消耗（只读）：返回 ``[(批次, 消耗份额)]`` 与是否足额覆盖。

    不修改输入批次（真实扣减仅发生在 :func:`rebuild_position_lots` 重放期）。
    """
    consumed: list[tuple[dict[str, Any], float]] = []
    remain = shares
    for lot in code_lots:
        if remain <= _SHARES_EPS:
            break
        take = min(lot["shares"], remain)
        if take > _SHARES_EPS:
            consumed.append((lot, take))
            remain -= take
    return consumed, remain <= _SHARES_EPS


# ── 成本聚合 ────────────────────────────────────────────


def compute_trade_costs(
    changes: list[dict[str, Any]],
    *,
    fee_index: dict[str, dict[str, Any]] | None = None,
    lots_by_code: dict[str, list[dict[str, Any]]] | None = None,
    count_trading_days: TradingDayCounter | None = None,
    effective_date: str = "",
    holding_end_date: str = "",
    unmodeled_codes: set[str] | None = None,
) -> dict[str, Any]:
    """变动明细 → 交易成本估算契约（纯计算：注入费率表/批次/交易日计数）。

    腿划分（按 ``action``，与 What-if 变动契约同源）：
      - 买入腿（新增/加仓）：金额 = 目标成本增量，费率按金额分档；
      - 卖出腿（清仓/减仓）：金额 = 基准成本减量，赎回费率按 FIFO 消耗批次的
        交易日持有期逐批判档后**加权**；
      - 场内品种（``unmodeled_codes``）：不建模，显式计数与标注；
      - 不变 → 无腿；费率来源缺失 → 未知腿（rate/fee=None，不冒充 0）。

    Args:
        changes: What-if ``changes`` 列表（code/name/action/base_shares/
            cand_shares/base_cost/cand_cost 等）
        fee_index: ``{code: {"purchase": 费率表, "redemption": 费率表}}``
            （各费率表自带 ``source`` 字段，两侧可不同源）
        lots_by_code: :func:`rebuild_position_lots` 输出（卖出腿批次来源）
        count_trading_days: 交易日计数注入 ``(start, end) -> int | None``
            （生产 = ``core.trading_calendar.count_trading_days_elapsed``）；
            缺失或返回 None → 卖出腿持有期未知 → 费率未知
        effective_date: 调仓生效日（成本入账日；空 = 未指定）
        holding_end_date: 持有期计算截止日（未指定生效日时由调用方给定，
            常为最近交易日；空且无生效日 → 卖出腿持有期未知）
        unmodeled_codes: 场内品种代码集（股票/场内基金）

    Returns:
        trade_cost 契约 dict：
          - available: 是否有可呈现的交易腿（无调仓 → False）
          - legs: 每腿 {code, name, action, side, shares, amount, rate, fee,
            flat_fee, rate_source, booked_date, holding_days}
          - purchase_total / redemption_total / total_cost（元，已知费用合计）
          - unknown_legs / unmodeled_legs / leg_count
          - fees_complete: 基金腿费率是否全部已知（False → 不出成本后数字）
          - notes: 口径与局限标注（面板两端同源常驻）
          - reason: available=False 时的原因
    """
    fee_index = fee_index or {}
    lots_by_code = lots_by_code or {}
    unmodeled_codes = unmodeled_codes or set()
    hold_end = effective_date or holding_end_date

    legs: list[dict[str, Any]] = []
    for c in changes or []:
        code = str(c.get("code") or "").strip()
        action = c.get("action")
        if not code or action not in (_BUY_ACTIONS | _SELL_ACTIONS):
            continue
        base_shares = float(c.get("base_shares") or 0.0)
        cand_shares = float(c.get("cand_shares") or 0.0)
        base_cost = float(c.get("base_cost") or 0.0)
        cand_cost = float(c.get("cand_cost") or 0.0)
        name = str(c.get("name") or code)

        if code in unmodeled_codes:
            legs.append(
                _leg(
                    code=code,
                    name=name,
                    action=action,
                    side=SIDE_UNMODELED,
                    shares=abs(cand_shares - base_shares),
                    amount=abs(cand_cost - base_cost),
                    source=SRC_UNMODELED,
                    booked_date=effective_date,
                )
            )
            continue

        entry = fee_index.get(code) or {}
        if action in _BUY_ACTIONS:
            amount = max(cand_cost - base_cost, 0.0)
            shares = max(cand_shares - base_shares, 0.0)
            schedule = entry.get("purchase")
            fee, tier = purchase_fee(amount, schedule)
            legs.append(
                _leg(
                    code=code,
                    name=name,
                    action=action,
                    side=SIDE_BUY,
                    shares=shares,
                    amount=amount,
                    rate=(tier or {}).get("rate") if fee is not None else None,
                    fee=fee,
                    flat_fee=(tier or {}).get("flat_fee") if fee is not None else None,
                    source=_fee_source(schedule, fee is not None),
                    booked_date=effective_date,
                )
            )
        else:
            amount = max(base_cost - cand_cost, 0.0)
            shares = max(base_shares - cand_shares, 0.0)
            fee, rate, holding_days, source = _redemption_cost(
                sell_shares=shares,
                amount=amount,
                schedule=entry.get("redemption"),
                lots=lots_by_code.get(code) or [],
                count_trading_days=count_trading_days,
                hold_end=hold_end,
            )
            legs.append(
                _leg(
                    code=code,
                    name=name,
                    action=action,
                    side=SIDE_SELL,
                    shares=shares,
                    amount=amount,
                    rate=rate,
                    fee=fee,
                    source=source,
                    booked_date=effective_date,
                    holding_days=holding_days,
                )
            )

    if not legs:
        return _empty_result(reason="无调仓变动（无新增/加仓/清仓/减仓腿），无交易成本")

    purchase_total = round(sum(leg["fee"] for leg in legs if leg["side"] == SIDE_BUY and leg["fee"] is not None), 2)
    redemption_total = round(sum(leg["fee"] for leg in legs if leg["side"] == SIDE_SELL and leg["fee"] is not None), 2)
    unknown = sum(1 for leg in legs if leg["side"] != SIDE_UNMODELED and leg["fee"] is None)
    unmodeled = sum(1 for leg in legs if leg["side"] == SIDE_UNMODELED)

    return {
        "available": True,
        "legs": legs,
        "purchase_total": purchase_total,
        "redemption_total": redemption_total,
        "total_cost": round(purchase_total + redemption_total, 2),
        "unknown_legs": unknown,
        "unmodeled_legs": unmodeled,
        "leg_count": len(legs),
        "fees_complete": unknown == 0,
        "notes": _build_notes(
            legs=legs,
            unknown=unknown,
            unmodeled=unmodeled,
            effective_date=effective_date,
            hold_end=hold_end,
            lots_used=bool(lots_by_code),
        ),
        "reason": "",
    }


def _leg(
    *,
    code: str,
    name: str,
    action: str,
    side: str,
    shares: float,
    amount: float,
    source: str,
    booked_date: str,
    rate: float | None = None,
    fee: float | None = None,
    flat_fee: float | None = None,
    holding_days: float | None = None,
) -> dict[str, Any]:
    """构造单腿条目（字段全量在场，未知即 None，契约稳定）。"""
    return {
        "code": code,
        "name": name,
        "action": action,
        "side": side,
        "shares": round(shares, 2),
        "amount": round(amount, 2),
        "rate": rate,
        "fee": fee,
        "flat_fee": flat_fee,
        "rate_source": source,
        "booked_date": booked_date,
        "holding_days": holding_days,
    }


def _redemption_cost(
    *,
    sell_shares: float,
    amount: float,
    schedule: dict[str, Any] | None,
    lots: list[dict[str, Any]],
    count_trading_days: TradingDayCounter | None,
    hold_end: str,
) -> tuple[float | None, float | None, float | None, str]:
    """卖出腿赎回费：FIFO 消耗批次 → 逐批交易日持有期选档 → 加权费率。

    Returns:
        (fee, weighted_rate, weighted_holding_days, rate_source)；
        任一环节不可判定（无费率表 / 无批次 / 批次不足 / 持有期未知 / 档位
        无命中）→ ``(None, None, None, "unknown")``。
    """
    if not schedule or sell_shares <= 0:
        return None, None, None, _fee_source(schedule, False)
    if not lots or count_trading_days is None or not hold_end:
        return None, None, None, SRC_UNKNOWN

    consumed, covered = _consume_lots(lots, sell_shares)
    if not consumed or not covered:
        return None, None, None, SRC_UNKNOWN  # 批次不足以覆盖卖出份额 → 不猜

    weighted_rate = 0.0
    weighted_days = 0.0
    for lot, take in consumed:
        days = count_trading_days(str(lot.get("start_date") or ""), hold_end)
        tier = select_redemption_tier(schedule, days)
        if days is None or tier is None:
            return None, None, None, SRC_UNKNOWN
        weighted_rate += take * float(tier["rate"])
        weighted_days += take * float(days)

    rate = round(weighted_rate / sell_shares, 6)
    days_avg = round(weighted_days / sell_shares, 1)
    return round(max(amount, 0.0) * rate, 2), rate, days_avg, _fee_source(schedule, True)


def _fee_source(schedule: dict[str, Any] | None, fee_known: bool) -> str:
    """腿的费率来源标记：未知一律 unknown，已知取费率表自带 source（缺省 f10_tier）。"""
    if not fee_known or not schedule:
        return SRC_UNKNOWN
    source = str(schedule.get("source") or "")
    if source in (SRC_F10, SRC_TABLE_SINGLE, SRC_CONFIG):
        return source
    return SRC_F10


def _build_notes(
    *,
    legs: list[dict[str, Any]],
    unknown: int,
    unmodeled: int,
    effective_date: str,
    hold_end: str,
    lots_used: bool,
) -> list[str]:
    """口径与局限标注（随成本块两端常驻；按内容条件追加）。"""
    buy_sources = {leg["rate_source"] for leg in legs if leg["side"] == SIDE_BUY}
    if buy_sources <= {SRC_TABLE_SINGLE} and buy_sources:
        purchase_desc = "申购费按全量表单档优惠费率估算（无金额分档，按首档近似）"
    else:
        purchase_desc = "申购费按买入金额分档（天天基金优惠费率）"
    notes = [
        f"交易成本 = 基金申赎费估算：{purchase_desc}，入账日 = 调仓生效日"
        + (f"（{effective_date}）" if effective_date else "（未指定生效日）"),
        "金额按成本价口径（与 What-if 成本口径一致；真实申购按申购金额、赎回按赎回净值计费）",
    ]
    if any(leg["side"] == SIDE_SELL for leg in legs):
        notes.append(
            "赎回费按份额持有期先进先出逐批判档，持有期以交易日计、档位边界按交易日解释"
            "（「N年」按 250 交易日/年折算）；该口径下持有期偏短、费率档偏高，成本估计偏保守"
        )
        if lots_used:
            notes.append(
                "批次由本机持仓快照历史重放重建，期初批建仓日为历史首见日（下界估计）"
                "——实际持有期可能更长、对应费率可能更低"
            )
        if not hold_end:
            notes.append("未指定生效日且无持有期截止日，卖出腿费率不可判定")
    if unknown:
        notes.append(f"{unknown} 条腿费率来源缺失，未计入合计（费率未知不出成本后数字）")
    if unmodeled:
        notes.append(f"{unmodeled} 条腿为场内品种（股票/场内基金），交易成本未建模（佣金/印花税等另计）")
    return notes


def _empty_result(reason: str) -> dict[str, Any]:
    """空成本契约（字段全量在场，降级态契约稳定）。"""
    return {
        "available": False,
        "legs": [],
        "purchase_total": 0.0,
        "redemption_total": 0.0,
        "total_cost": 0.0,
        "unknown_legs": 0,
        "unmodeled_legs": 0,
        "leg_count": 0,
        "fees_complete": True,
        "notes": [],
        "reason": reason,
    }


__all__ = [
    "SIDE_BUY",
    "SIDE_SELL",
    "SIDE_UNMODELED",
    "SRC_CONFIG",
    "SRC_F10",
    "SRC_TABLE_SINGLE",
    "SRC_UNMODELED",
    "SRC_UNKNOWN",
    "TRADING_DAYS_PER_YEAR",
    "TradingDayCounter",
    "build_single_purchase_schedule",
    "build_config_fee_schedules",
    "compute_trade_costs",
    "parse_fee_percent",
    "parse_purchase_fee_schedule",
    "parse_redemption_fee_schedule",
    "purchase_fee",
    "rebuild_position_lots",
    "select_purchase_tier",
    "select_redemption_tier",
]
