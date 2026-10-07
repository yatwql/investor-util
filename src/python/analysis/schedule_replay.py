"""调仓纪律回放（schedule_replay）：规则 → 逐期调仓序列 → 逐期净值回放（纯计算零 I/O）。

分层红线（设计 docs/plan/rebalance-schedule-replay-design.md）：
  - **不新造回测引擎**：指标复用 ``metrics_returns``（sharpe/年化/回撤）与
    ``metrics_risk.turnover_rate``，LOCF/100 基点归一/日收益复用 ``whatif_backtest``
    同源公共出口，交易日计数复用 ``core.trading_calendar``；
  - **成本单源消费不复制口径**：只依赖 ``trade_cost_model.compute_trade_costs`` 的
    输入输出契约（买卖明细 + 费率表 → 成本金额），绝不并行实现第二套成本；
  - **行情经参注入**：``nav_series`` 由报告层经 Provider 链备入，本模块零 I/O。

降级契约（设计 §5）：
  - 历史窗口不足（跨度/净值日低于下限）或行情缺口 > 上限 → ``available=False``；
  - 阈值规则窗口内未触发 → notes 明示「窗口内未触发」而非空表；
  - 成本三态：费率表缺席 → ``cost_note="未计成本"``；部分腿费率未知 → 已知部分
    计入 + notes 标注未知腿数；费率全知 → ``cost_note=""``。

目标权重：``schedule.target_weights`` 缺省时按窗口末日市值归一（「当前持仓归一」）。
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Callable

from src.python.analysis.metrics_risk import turnover_rate
from src.python.analysis.metrics_returns import (
    annualized_return,
    max_drawdown_pct,
    sharpe_ratio,
)
from src.python.analysis.trade_cost_model import (
    consume_fifo_shares,
    compute_trade_costs,
)
from src.python.analysis.whatif_backtest import (
    locf_forward,
    normalize_to_basis,
    returns_from_values,
)
from src.python.core.trading_calendar import count_trading_days_elapsed
from src.python.schemas.replay_schedule import ReplaySchedule, parse_replay_schedule

logger = logging.getLogger("invest")

COST_NOTE_ABSENT = "未计成本"
#: 默认取数/验收窗口：窗口 400 自然日、跨度下限 365（≈12 个月），
#: 净值日下限 200、缺口上限 30%（设计 §5 降级判据）
DEFAULT_WINDOW_DAYS = 400
DEFAULT_MIN_SPAN_DAYS = 365
DEFAULT_MIN_POINTS = 200
DEFAULT_MAX_GAP = 0.30

_EPS = 1e-9


def _unavailable(reason: str, *, schedule: ReplaySchedule | None = None) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "schedule_version": schedule.version if schedule else None,
        "window": None,
        "gap_pct": None,
        "cost_note": "",
        "series": None,
        "metrics": None,
        "periods": [],
        "trigger": None,
        "notes": [],
    }


def _window_bounds(nav_series: dict[str, dict[str, float]], window_days: int, end_date: str) -> tuple[str, str]:
    """窗口起止：末日（end_date 或全序列最大日期）往前 window_days 个自然日。"""
    if not end_date:
        end_date = max((d for m in nav_series.values() for d in m), default="")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    start_dt = end_dt - timedelta(days=window_days)
    return start_dt.isoformat(), end_date


def _sanitize_series(nav_series: dict[str, dict[str, float]], start: str, end: str) -> dict[str, dict[str, float]]:
    """窗口过滤 + 非有限值剔除（NaN/inf 不进 LOCF）。"""
    clean: dict[str, dict[str, float]] = {}
    for code, month_map in (nav_series or {}).items():
        kept = {
            d: float(v)
            for d, v in (month_map or {}).items()
            if isinstance(d, str) and start <= d <= end and isinstance(v, (int, float)) and math.isfinite(v) and v > 0
        }
        if kept:
            clean[str(code)] = kept
    return clean


def _month_key(date_str: str, cadence: str) -> str:
    if cadence == "quarterly":
        year, month = date_str[:4], int(date_str[5:7])
        return f"{year}-Q{(month - 1) // 3 + 1}"
    return date_str[:7]


def _holdings_payload(holdings: list[dict[str, Any]], codes: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "code": str(h.get("code") or "").strip(),
            "name": str(h.get("name") or h.get("code") or ""),
            "shares": float(h.get("shares") or 0.0),
            "cost": float(h.get("cost") or 0.0),
        }
        for h in holdings
        if str(h.get("code") or "").strip() in codes and float(h.get("shares") or 0.0) > _EPS
    ]


def _resolve_target_weights(
    schedule: ReplaySchedule,
    rows: list[dict[str, Any]],
    end_navs: dict[str, float],
    notes: list[str],
) -> dict[str, float]:
    """目标权重：用户指定（持仓交集内重归一）或窗口末日市值归一。"""
    total_value = {r["code"]: r["shares"] * end_navs.get(r["code"], 0.0) for r in rows}
    total = sum(total_value.values())
    if schedule.target_weights is None:
        if total <= 0:
            return {r["code"]: 0.0 for r in rows}
        return {c: v / total for c, v in total_value.items()}

    given = schedule.target_weights
    held = {r["code"] for r in rows}
    ignored = sorted(set(given) - held)
    if ignored:
        notes.append(f"目标权重含非持仓代码已忽略：{'、'.join(ignored)}")
    missing = sorted(held - set(given))
    if missing:
        notes.append(f"目标权重未覆盖的持仓按 0（清仓）解释：{'、'.join(missing)}")
    partial = {c: given.get(c, 0.0) for c in held}
    partial_sum = sum(partial.values())
    if partial_sum <= 0:
        raise ValueError("回放规则非法：目标权重与当前持仓交集为空（总和为 0）")
    if abs(partial_sum - 1.0) > 1e-9:
        notes.append(f"目标权重在持仓交集内重归一（原交集和 {partial_sum:.6f}）")
    return {c: w / partial_sum for c, w in partial.items()}


def run_schedule_replay(
    holdings: list[dict[str, Any]],
    nav_series: dict[str, dict[str, float]],
    schedule: ReplaySchedule | dict[str, Any] | None = None,
    *,
    fee_index: dict[str, dict[str, Any]] | None = None,
    lots_by_code: dict[str, list[dict[str, Any]]] | None = None,
    unmodeled_codes: set[str] | None = None,
    cost_counter: Callable[[str, str], int | None] | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    end_date: str = "",
    min_span_days: int = DEFAULT_MIN_SPAN_DAYS,
    min_points: int = DEFAULT_MIN_POINTS,
    max_gap: float = DEFAULT_MAX_GAP,
) -> dict[str, Any]:
    """按规则回放多期调仓，返回纪律回放 vs 买入持有的净值/指标/逐期成本。

    Args:
        holdings: [{code, name, shares, cost(每份成本)}, ...] 当前持仓（回放输入快照化）。
        nav_series: {code: {date: 单位净值/收盘}}，报告层经 Provider 链备入（本函数零 I/O）。
        schedule: 回放规则（``ReplaySchedule`` / 原始映射 / None=默认月度定期）。
        fee_index: 费率索引（``fetch_fee_index`` 产物）；None → 成本不计并回显
            ``cost_note="未计成本"``（软接入两态，不并行第二套成本实现）。
        lots_by_code: 期初 FIFO 批次（快照重放产物）；None → 合成期初批（建仓日 = 窗口
            起点，持有期下界 → 赎回费率档偏高、成本偏保守，notes 明示）。
        unmodeled_codes: 场内等未建模成本品种（透传 ``compute_trade_costs``）。
        cost_counter: 交易日计数注入（None → ``count_trading_days_elapsed``）。
        window_days / end_date: 回放窗口（自然日）与末日（默认取序列最大日期）。
        min_span_days / min_points / max_gap: 验收下限——跨度不足 / 净值日不足 /
            缺口越限 → ``available=False``（章隐藏，设计 §5）。

    Returns:
        ``available=True`` 时含：``window``/``gap_pct``/``cost_note``/``series``
        （``dates`` + ``replay``/``buyhold`` 100 基点序列）/``metrics``（两侧 total、
        annualized、max_drawdown、sharpe 与 ``diff`` = replay − buyhold）/``periods``
        （逐期调仓行：date、trades、turnover、cost、cost_known）/``trigger``（触发
        汇总与 ``fired`` 列表）/``notes``；不可用时 ``available=False`` + ``reason``。

    Raises:
        ValueError: 目标权重与持仓交集为空（规则非法，契约层校验之外的运行期判定）。
    """
    if isinstance(schedule, ReplaySchedule):
        parsed = schedule
    else:
        parsed = parse_replay_schedule(schedule)
    if cost_counter is None:
        cost_counter = count_trading_days_elapsed

    # ── 取窗口与对齐轴 ──────────────────────────────────
    if not nav_series or not holdings:
        return _unavailable("无可用行情或无持仓（回放输入为空）", schedule=parsed)
    start, end = _window_bounds(nav_series, window_days, end_date)
    clean = _sanitize_series(nav_series, start, end)
    if not clean:
        return _unavailable(f"窗口 {start} ~ {end} 内无净值数据", schedule=parsed)

    rows = _holdings_payload(holdings, set(clean))
    if not rows:
        return _unavailable("持仓品种在窗口内均无行情（无可回放品种）", schedule=parsed)
    dropped = sorted({str(h.get("code") or "").strip() for h in holdings} - {r["code"] for r in rows})
    notes: list[str] = []
    if dropped:
        notes.append(f"已剔除出回放组合（窗口内无行情或无份额）：{'、'.join(dropped)}")

    union = sorted({d for code_map in clean.values() for d in code_map})
    if not union:
        return _unavailable("窗口内无净值数据", schedule=parsed)
    span = (datetime.strptime(union[-1], "%Y-%m-%d") - datetime.strptime(union[0], "%Y-%m-%d")).days
    if span < min_span_days:
        return _unavailable(f"历史窗口不足 12 个月（跨度 {span} 天 < {min_span_days} 天）", schedule=parsed)
    if len(union) < min_points:
        return _unavailable(f"净值日不足（{len(union)} < {min_points}）", schedule=parsed)

    # 逐品种覆盖率 → 整体缺口（> max_gap 判失真，章隐藏）
    coverages = [sum(1 for d in union if d in clean[r["code"]]) / len(union) for r in rows]
    gap_pct = 1.0 - (sum(coverages) / len(coverages) if coverages else 0.0)
    if gap_pct > max_gap:
        return _unavailable(f"行情缺口 {gap_pct:.0%} 超过上限 {max_gap:.0%}（回放失真风险）", schedule=parsed)

    # LOCF 矩阵；锚点 = 全品种均有值的首日（锚点前不可比，同 what-if 锚点约定）
    locf_maps = {r["code"]: locf_forward(union, clean[r["code"]]) for r in rows}
    anchor = next(
        (i for i in range(len(union)) if all(locf_maps[r["code"]][i] is not None for r in rows)),
        None,
    )
    if anchor is None:
        return _unavailable("无可对齐锚点（各品种观测区间无交集）", schedule=parsed)
    dates = union[anchor:]
    nav_at = {r["code"]: locf_maps[r["code"]][anchor:] for r in rows}

    codes = [r["code"] for r in rows]
    shares = {r["code"]: r["shares"] for r in rows}
    cost_basis = {r["code"]: r["cost"] for r in rows}
    names = {r["code"]: r["name"] for r in rows}

    end_navs = {c: float(nav_at[c][-1]) for c in codes if nav_at[c][-1] is not None}
    if len(end_navs) != len(codes):
        return _unavailable("锚点后仍有品种缺失净值（末日目标不可计算）", schedule=parsed)
    target = _resolve_target_weights(parsed, rows, end_navs, notes)

    # ── 买入持有基线（零交易）─────────────────────────────
    def day_value(shares_map: dict[str, float], idx: int, cash: float) -> float:
        total = cash
        for c in codes:
            nav = nav_at[c][idx]
            total += shares_map[c] * (nav if nav is not None else 0.0)
        return total

    buyhold_values = [day_value(shares, i, 0.0) for i in range(len(dates))]
    if buyhold_values[0] <= 0:
        return _unavailable("期初组合市值非正（无法归一）", schedule=parsed)

    # ── 纪律回放 ───────────────────────────────────────
    sim_shares = dict(shares)
    cash = 0.0
    if lots_by_code is None:
        lots = {c: [{"start_date": dates[0], "shares": sim_shares[c]}] for c in codes}
        notes.append("期初批次建仓日 = 回放窗口起点（持有期为下界估计，赎回费率档偏高、成本估计偏保守）")
    else:
        lots = {c: [dict(lot) for lot in (lots_by_code.get(c) or [])] for c in codes}
    unknown_fee_legs = 0
    unmodeled_legs = 0
    periods: list[dict[str, Any]] = []
    fired: list[str] = []
    prev_bucket: str | None = None
    threshold = parsed.threshold
    cost_enabled = fee_index is not None
    replay_values: list[float] = []

    def rebalance(idx: int) -> None:
        nonlocal cash, unknown_fee_legs, unmodeled_legs
        date = dates[idx]
        navs_d = {c: nav_at[c][idx] for c in codes}
        if any(v is None or v <= 0 for v in navs_d.values()):
            return
        value = day_value(sim_shares, idx, cash)
        if value <= 0:
            return
        before = [{"code": c, "market_value": sim_shares[c] * float(navs_d[c])} for c in codes]
        changes: list[dict[str, Any]] = []
        for c in codes:
            nav_d = float(navs_d[c])
            new_shares = round(value * target.get(c, 0.0) / nav_d, 2)
            delta = new_shares - sim_shares[c]
            if abs(delta) < 1e-6:
                continue
            base_cost = sim_shares[c] * cost_basis.get(c, 0.0)
            if sim_shares[c] <= _EPS:
                action, cand_cost = "新增", new_shares * nav_d
                cost_basis[c] = nav_d
            elif delta > 0:
                action, cand_cost = "加仓", base_cost + delta * nav_d
                cost_basis[c] = (base_cost + delta * nav_d) / new_shares
            else:
                action = "清仓" if new_shares <= _EPS else "减仓"
                cand_cost = base_cost * (new_shares / sim_shares[c]) if sim_shares[c] > 0 else 0.0
                if new_shares <= _EPS:
                    cost_basis[c] = 0.0
                else:
                    cost_basis[c] = cand_cost / new_shares
            changes.append(
                {
                    "code": c,
                    "name": names.get(c, c),
                    "action": action,
                    "base_shares": sim_shares[c],
                    "cand_shares": new_shares,
                    "base_cost": round(base_cost, 2),
                    "cand_cost": round(cand_cost, 2),
                }
            )
        turnover = turnover_rate(
            before,
            [
                {"code": c, "market_value": float(navs_d[c]) * round(value * target.get(c, 0.0) / float(navs_d[c]), 2)}
                for c in codes
            ],
        )
        period_cost = 0.0
        cost_known = True
        if changes and cost_enabled:
            result = compute_trade_costs(
                changes,
                fee_index=fee_index,
                lots_by_code=lots,
                unmodeled_codes=unmodeled_codes,
                effective_date=date,
                count_trading_days=cost_counter,
            )
            period_cost = float(result.get("total_cost") or 0.0)
            unknown_fee_legs += int(result.get("unknown_legs") or 0)
            unmodeled_legs += int(result.get("unmodeled_legs") or 0)
            cost_known = bool(result.get("fees_complete"))
            cash -= period_cost
        elif changes and not cost_enabled:
            cost_known = False
        if not changes:
            periods.append(
                {
                    "date": date,
                    "trades": 0,
                    "turnover": 0.0,
                    "cost": 0.0,
                    "cost_known": cost_known,
                }
            )
            fired.append(date)
            return
        for ch in changes:
            c = ch["code"]
            delta = float(ch["cand_shares"]) - float(ch["base_shares"])
            cash -= delta * float(navs_d[c])
            sim_shares[c] = float(ch["cand_shares"])
            if delta > 0:
                lots.setdefault(c, []).append({"start_date": date, "shares": delta})
            else:
                consume_fifo_shares(lots.setdefault(c, []), -delta)
            if sim_shares[c] <= _EPS:
                sim_shares[c] = 0.0
                lots[c] = []
        periods.append(
            {
                "date": date,
                "trades": len(changes),
                "turnover": round(float(turnover or 0.0), 6),
                "cost": round(period_cost, 2),
                "cost_known": cost_known,
            }
        )
        fired.append(date)

    for idx, date in enumerate(dates):
        if parsed.rule_type == "cadence":
            bucket = _month_key(date, parsed.cadence)
            if prev_bucket is not None and bucket != prev_bucket:
                rebalance(idx)
            prev_bucket = bucket
        else:  # threshold：逐日评估偏离，≥ 阈值全量回归
            value = day_value(sim_shares, idx, cash)
            if value > 0:
                navs_d = {c: nav_at[c][idx] for c in codes}
                if all(v is not None and v > 0 for v in navs_d.values()):
                    drift = max(abs(sim_shares[c] * float(navs_d[c]) / value - target.get(c, 0.0)) for c in codes)
                    if threshold is not None and drift >= threshold:
                        rebalance(idx)
        # 逐日记录当日收盘后净值（调仓已在当日 NAV 下完成，成本同日扣除）
        replay_values.append(day_value(sim_shares, idx, cash))

    if replay_values[0] <= 0:
        return _unavailable("回放期初市值非正（无法归一）", schedule=parsed)

    replay_norm = normalize_to_basis(replay_values, replay_values[0])
    buyhold_norm = normalize_to_basis(buyhold_values, buyhold_values[0])

    def side_metrics(norm: list[float]) -> dict[str, Any]:
        rets = returns_from_values(norm)
        return {
            "total_return": round(norm[-1] / 100.0 - 1.0, 6),
            "annualized": annualized_return(rets),
            "max_drawdown": max_drawdown_pct(rets),
            "sharpe": sharpe_ratio(rets),
        }

    replay_metrics = side_metrics(replay_norm)
    buyhold_metrics = side_metrics(buyhold_norm)
    diff = {
        key: (
            None
            if replay_metrics[key] is None or buyhold_metrics[key] is None
            else round(float(replay_metrics[key]) - float(buyhold_metrics[key]), 6)
        )
        for key in replay_metrics
    }

    # ── 触发汇总 / 成本两态回显 ───────────────────────────
    trigger: dict[str, Any] = {
        "rule_type": parsed.rule_type,
        "cadence": parsed.cadence if parsed.rule_type == "cadence" else None,
        "threshold_pp": parsed.threshold_pp,
        "count": len(fired),
        "fired": fired,
    }
    if parsed.rule_type == "threshold" and not fired:
        notes.append(f"窗口内未触发阈值（偏离始终小于 {parsed.threshold_pp}pp）——无调仓期行，回放曲线与买入持有一致")
    cost_note = "" if cost_enabled else COST_NOTE_ABSENT
    if cost_enabled and unknown_fee_legs:
        notes.append(f"{unknown_fee_legs} 条腿费率未知未计入成本合计（费率未知不出成本后数字）")
    if cost_enabled and unmodeled_legs:
        notes.append(f"{unmodeled_legs} 条腿为场内未建模品种（佣金/印花税等另计）")
    if periods and cost_enabled:
        notes.append(
            "交易成本 = 基金申赎费估算（单源消费 trade_cost_model 口径：申购按金额分档、"
            "赎回按 FIFO 批次持有期逐批判档），入账日 = 调仓生效日"
        )

    logger.info(
        "[纪律回放] %s 规则窗口 %s ~ %s：%d 个净值日、触发 %d 次、成本态=%s、缺口 %.1f%%",
        parsed.rule_type,
        dates[0],
        dates[-1],
        len(dates),
        len(fired),
        cost_note or "已计入",
        gap_pct * 100,
    )

    return {
        "available": True,
        "reason": "",
        "schedule_version": parsed.version,
        "window": {"start": dates[0], "end": dates[-1], "points": len(dates)},
        "gap_pct": round(gap_pct, 6),
        "cost_note": cost_note,
        "series": {"dates": dates, "replay": replay_norm, "buyhold": buyhold_norm},
        "metrics": {
            "replay": replay_metrics,
            "buyhold": buyhold_metrics,
            "diff": diff,
        },
        "periods": periods,
        "trigger": trigger,
        "notes": notes,
    }


__all__ = [
    "COST_NOTE_ABSENT",
    "DEFAULT_MAX_GAP",
    "DEFAULT_MIN_POINTS",
    "DEFAULT_MIN_SPAN_DAYS",
    "DEFAULT_WINDOW_DAYS",
    "run_schedule_replay",
]
