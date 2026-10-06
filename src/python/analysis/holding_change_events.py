"""持仓变动事件抽取（holding_change_events）— 快照序列 → 变动事件表。

把去重后的持仓快照序列**逐对差分**展开为区间净额变动事件序列（零手工、
零新数据源），为「持仓变动复盘」章（holding_change_review）提供事件契约
`holding_change_data.events`。事件方向分类**复用差异引擎**
`fetcher/history_diff.HistoryDiff.compute`（新增/加仓/减仓/清仓四类），
按日去重**复用** `analysis/portfolio_evolution._dedup_by_date`——不自写
第二套 diff/去重（与报告环比两套口径互相矛盾即技术债）。

**能力边界（诚实声明，与 `analysis/snapshot_diff.py` 同一设计边界先例）**：

  - 事件是**区间净额推断**，非逐笔成交——快照不含成交日期/单价/费用/出场价，
    一律不派生（不虚构）；报告须随事件表标注「区间净额推断、非逐笔」。
  - 同一持仓区间内多笔买卖折叠为一条净额事件；净额 ≈ 0 的对敲不可见；
    分红再投/份额折算也会改份额、混入事件（已知局限，结论限定结构级）。
  - 份额字段缺失/非有限值（NaN/Inf）时事件标 `action="不可判定"`、份额字段
    置 None，只按市值差呈现事实，不倒推份额方向。

先决门槛常量（go/no-go 判据，随报告回显供监测）：`MIN_REVIEW_PERIODS` /
`MIN_REVIEW_EVENTS`。数据不足（去重后有效快照 < 2 期）返回
`available=False` 占位（同 `snapshot_diff` 降级形态），不中断报告。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from src.python.analysis.portfolio_evolution import _dedup_by_date
from src.python.fetcher.history_diff import HistoryDiff
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

logger = logging.getLogger("invest")

#: 先决门槛①：有效快照（按日去重后）期数下限
MIN_REVIEW_PERIODS = 12
#: 先决门槛①：累计变动事件数下限
MIN_REVIEW_EVENTS = 10
#: 有效期数下限：去重后不足 2 期无从差分（占位降级）
_DEFAULT_MIN_PERIODS = 2
#: 份额差绝对值低于该值视为「不变」（与 HistoryDiff 分类阈值一致）
_SHARES_EPS = 0.001

# 事件方向枚举（分类复用 HistoryDiff；「不可判定」为本模块缺字段降级补充）
ACTION_NEW = "新增"
ACTION_INCREASE = "加仓"
ACTION_DECREASE = "减仓"
ACTION_EXIT = "清仓"
ACTION_INDETERMINATE = "不可判定"

__all__ = [
    "ACTION_DECREASE",
    "ACTION_EXIT",
    "ACTION_INCREASE",
    "ACTION_INDETERMINATE",
    "ACTION_NEW",
    "MIN_REVIEW_EVENTS",
    "MIN_REVIEW_PERIODS",
    "build_holding_change_events",
    "extract_change_events",
]


def extract_change_events(
    snapshots: list[SnapshotData],
    *,
    min_periods: int = _DEFAULT_MIN_PERIODS,
) -> dict[str, Any]:
    """快照序列 → 变动事件表契约 dict（纯函数：不读盘、不联网、不回写）。

    Args:
        snapshots: 快照列表（乱序输入自动按 timestamp 升序排序）
        min_periods: 有效期数下限（默认 2），不足时返回 available=False 占位

    Returns:
        holding_change_events 契约 dict：
          - available: 数据是否充足（去重后有效快照 >= min_periods）
          - snapshot_count: 输入快照数（去重前）
          - period_count: 按日去重后有效快照期数
          - period_timestamps: 各期时间戳（YYYYMMDDTHHMMSS，升序）
          - window_start / window_end: 复盘窗口起止时间戳（首/末期；不足 1 期为 None）
          - events: 事件列表（逐对差分展开，见模块 docstring 字段契约）
          - event_count / indeterminate_count: 事件数 / 缺份额字段不可判定事件数
          - reason: available=False 时的降级原因
    """
    ordered = sorted(snapshots, key=lambda sd: sd.timestamp or "")
    periods = _dedup_by_date(ordered)
    period_count = len(periods)

    if period_count < min_periods:
        reason = f"持仓变动复盘快照不足：有效快照 {period_count} < 下限 {min_periods} 期，变动事件待积累"
        logger.info("[holding_change_events] %s", reason)
        return {
            "available": False,
            "snapshot_count": len(snapshots),
            "period_count": period_count,
            "period_timestamps": [sd.timestamp for sd in periods],
            "window_start": periods[0].timestamp if periods else None,
            "window_end": periods[-1].timestamp if periods else None,
            "events": [],
            "event_count": 0,
            "indeterminate_count": 0,
            "reason": reason,
        }

    events: list[dict[str, Any]] = []
    indeterminate_count = 0
    for prev_sd, curr_sd in zip(periods, periods[1:]):
        pair_events, pair_indeterminate = _diff_pair(prev_sd, curr_sd)
        events.extend(pair_events)
        indeterminate_count += pair_indeterminate

    if indeterminate_count:
        logger.warning(
            "[holding_change_events] %d 个事件缺份额字段，已标「不可判定」（只按市值差呈现）",
            indeterminate_count,
        )

    return {
        "available": True,
        "snapshot_count": len(snapshots),
        "period_count": period_count,
        "period_timestamps": [sd.timestamp for sd in periods],
        "window_start": periods[0].timestamp if periods else None,
        "window_end": periods[-1].timestamp if periods else None,
        "events": events,
        "event_count": len(events),
        "indeterminate_count": indeterminate_count,
        "reason": "",
    }


def build_holding_change_events(
    *,
    snapshot_namespace: str | None = None,
    min_periods: int = _DEFAULT_MIN_PERIODS,
) -> dict[str, Any]:
    """从快照目录加载全部快照并抽取事件表（消费入口，读本地快照零网络）。

    Args:
        snapshot_namespace: 快照隔离域（None=共享主目录；如 "web"=web 试算域）
        min_periods: 有效期数下限（默认 2）

    Returns:
        同 `extract_change_events` 契约
    """
    from src.python.report.history_snapshot import load_all

    return extract_change_events(load_all(snapshot_namespace), min_periods=min_periods)


# ── 内部辅助 ─────────────────────────────────────────────


def _diff_pair(
    prev_sd: SnapshotData,
    curr_sd: SnapshotData,
) -> tuple[list[dict[str, Any]], int]:
    """一对相邻快照 → 事件列表与不可判定事件数。

    份额字段全部有效的持仓走 HistoryDiff 分类（四类动作）；份额缺失/非有限
    的持仓先从两侧快照中剔除（防 NaN 污染差异引擎的方向判定），再按市值差
    单独判定——有市值变化则出「不可判定」事件，无变化则不出事件。
    """
    prev_idx = HistoryDiff._index_holdings(prev_sd)
    curr_idx = HistoryDiff._index_holdings(curr_sd)
    invalid = {code for code, h in prev_idx.items() if not _shares_valid(h)}
    invalid |= {code for code, h in curr_idx.items() if not _shares_valid(h)}

    diff = HistoryDiff.compute(
        _drop_codes(curr_sd, invalid),
        _drop_codes(prev_sd, invalid),
    )

    period_from = prev_sd.timestamp or ""
    period_to = curr_sd.timestamp or ""
    events: list[dict[str, Any]] = []
    for group in (diff.added, diff.increased, diff.decreased, diff.removed):
        for d in group:
            h0 = prev_idx.get(d.code)
            h1 = curr_idx.get(d.code)
            events.append(
                {
                    "code": d.code,
                    "name": d.name,
                    "action": d.action,
                    "shares_diff": d.shares_diff,
                    "value_diff": d.value_diff,
                    "shares_before": _shares_of(h0),
                    "shares_after": _shares_of(h1),
                    "value_before": _value_of(h0),
                    "value_after": _value_of(h1),
                    "period_from": period_from,
                    "period_to": period_to,
                    "indeterminate": False,
                }
            )

    # 缺份额字段的持仓：只按市值差呈现事实（方向不可判定，不倒推）
    indeterminate = 0
    for code in sorted(invalid):
        h0 = prev_idx.get(code)
        h1 = curr_idx.get(code)
        v0 = _value_of(h0)
        v1 = _value_of(h1)
        if v0 is None or v1 is None or math.isclose(v1, v0, abs_tol=1e-9):
            continue  # 市值同样不可知或无变化 → 无可判定事实，不出事件
        base = h1 or h0
        events.append(
            {
                "code": code,
                "name": getattr(base, "name", "") or code,
                "action": ACTION_INDETERMINATE,
                "shares_diff": None,
                "value_diff": round(v1 - v0, 2),
                "shares_before": _shares_of(h0),
                "shares_after": _shares_of(h1),
                "value_before": v0,
                "value_after": v1,
                "period_from": period_from,
                "period_to": period_to,
                "indeterminate": True,
            }
        )
        indeterminate += 1

    return events, indeterminate


def _drop_codes(sd: SnapshotData, drop: set[str]) -> SnapshotData:
    """返回剔除指定 code 后的快照副本（纯内存，不改动原快照）。"""
    if not drop:
        return sd
    accounts = tuple(
        AccountSnapshot(
            account_name=acc.account_name,
            holdings=tuple(h for h in acc.holdings if h.code not in drop),
        )
        for acc in sd.accounts
    )
    return SnapshotData(
        accounts=accounts,
        total_value=sd.total_value,
        total_cost=sd.total_cost,
        total_pnl=sd.total_pnl,
        total_pnl_pct=sd.total_pnl_pct,
        timestamp=sd.timestamp,
        fingerprint=sd.fingerprint,
        llm_summary=sd.llm_summary,
    )


def _shares_valid(h: SnapshotHolding) -> bool:
    """份额字段是否可用于方向判定（存在且为有限数值）。"""
    return _is_finite(getattr(h, "shares", None))


def _shares_of(h: SnapshotHolding | None) -> float | None:
    """份额字段：缺席侧 = 未持有（0，事实非虚构）；字段非有限 → None。"""
    if h is None:
        return 0.0
    value = getattr(h, "shares", None)
    return float(value) if _is_finite(value) else None


def _value_of(h: SnapshotHolding | None) -> float | None:
    """市值字段：缺席侧 = 未持有（0，事实非虚构）；字段非有限 → None。"""
    if h is None:
        return 0.0
    value = getattr(h, "market_value", None)
    return float(value) if _is_finite(value) else None


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
