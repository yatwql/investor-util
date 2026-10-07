"""持仓变动指标纯计算（holding_change_metrics）— 事件表 → 结构级复盘指标。

对 `holding_change_events` 抽取的事件表做**零 I/O 纯计算**（不读盘、不联网、
不回写任何账本），产出三组结构级指标：

  1. 变动频率 —— 事件数 / 期数 / 交易日数（区间天数一律经
     `core/trading_calendar.py` 交易日计数，日历不可用时自然日回退）
  2. 结构计数 —— 新增/加仓/减仓/清仓/不可判定五类计数 + 触及品种数
  3. 区间市值贡献分解 —— 每事件按 ΔMV = 份额变动贡献 + 价格变动贡献 两分量
     分解后聚合（恒等式：两分量之和 = 区间市值变化）
  4. 意图对账 —— 变动事件 vs `core/decision_ledger` 决策登记的**只读列表对照**
     （意图 vs 成交；账本由调用方注入，本模块绝不回写）

**能力边界（诚实声明）**：全部结论限定结构级——事件为区间净额推断，非逐笔
成交；对账是列表对照而非绩效归因（不给出「意图正确率」类结论）。份额字段
缺失（None）的事件不参与贡献分解（计入 skipped，不虚构分量）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core import decision_ledger
from src.python.core.trading_calendar import count_trading_days_elapsed, elapsed_trading_days_with_natural_fallback

logger = logging.getLogger("invest")

#: 事件方向五类（前四类来自差异引擎，「不可判定」为缺字段降级补充）
ACTION_KEYS: tuple[str, ...] = ("新增", "加仓", "减仓", "清仓", "不可判定")

#: 意图对账枚举
ALIGN_ALIGNED = "一致"
ALIGN_DIVERGENT = "分歧"
ALIGN_NO_INTENT = "无意图记录"
ALIGN_MIXED = "混合意图"
ALIGN_INDETERMINATE = "不可判定"

REORDER_MIN_CODES = 5
"""跨品种同日重排识别的最小联动品种数（低于此数视为常规调仓，不标注）。"""

_INTENT_LABEL_LONG = "加仓意图"
_INTENT_LABEL_SHORT = "减仓意图"
_INTENT_LABEL_FLAT = "持平意图"
_INTENT_LABEL_NONE = "无意图记录"
_INTENT_LABEL_MIXED = "多空并存"

__all__ = [
    "ACTION_KEYS",
    "ALIGN_ALIGNED",
    "ALIGN_DIVERGENT",
    "ALIGN_INDETERMINATE",
    "ALIGN_MIXED",
    "ALIGN_NO_INTENT",
    "REORDER_MIN_CODES",
    "build_intent_reconciliation",
    "compute_holding_change_metrics",
    "detect_account_reorder",
]


def compute_holding_change_metrics(
    events: list[dict[str, Any]],
    *,
    period_count: int,
    window_start: str = "",
    window_end: str = "",
    ledger_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """事件表 → 结构级复盘指标 dict（纯函数）。

    Args:
        events: `holding_change_events` 契约中的事件列表
        period_count: 按日去重后的有效快照期数（频率分母）
        window_start: 复盘窗口起始时间戳（YYYYMMDDTHHMMSS 或 ISO）
        window_end: 复盘窗口结束时间戳
        ledger_events: 决策账本事件（`core/decision_ledger.load_events()` 注入；
            None/空 = 账本无记录，对账列表全部落「无意图记录」）

    Returns:
        指标 dict：
          - event_count / period_count: 事件数与期数
          - events_per_period: 期均变动事件数（两位小数）
          - trading_days: 窗口交易日数（自然日回退保底，恒 ≥0）
          - trading_day_mode: 交易日口径（"trading"=交易日历；"natural"=日历不可用按自然日回退）
          - events_per_trading_day: 日均变动事件数（两位小数）
          - action_counts: 五类动作计数（键恒齐全，缺类为 0）
          - distinct_codes: 触及品种数（去重）
          - contribution: {shares_part, price_part, market_value_change, skipped_count}
          - intent: 意图对账（见 `build_intent_reconciliation`）
    """
    event_count = len(events)
    action_counts = {key: 0 for key in ACTION_KEYS}
    for ev in events:
        action = ev.get("action")
        if action in action_counts:
            action_counts[action] += 1
    distinct_codes = len({ev.get("code") for ev in events if ev.get("code")})

    trading_days = _window_trading_days(window_start, window_end)
    # 口径分支标注：交易日历不可用（含起止不可解析）时 trading_days 实为自然日回退值，
    # 展示层据此如实标注口径，不把回退值谎称为交易日历口径
    trading_day_mode = "trading"
    start_date, end_date = _iso_date(window_start), _iso_date(window_end)
    if not start_date or not end_date or count_trading_days_elapsed(start_date, end_date) is None:
        trading_day_mode = "natural"
    events_per_period = round(event_count / period_count, 2) if period_count > 0 else 0.0
    events_per_trading_day = round(event_count / trading_days, 2) if trading_days > 0 else 0.0

    contribution = _contribution_breakdown(events)
    if contribution["skipped_count"]:
        logger.info(
            "[holding_change_metrics] %d 个事件缺份额字段，未参与贡献分解（只呈现可判定部分）",
            contribution["skipped_count"],
        )

    return {
        "event_count": event_count,
        "period_count": period_count,
        "events_per_period": events_per_period,
        "trading_days": trading_days,
        "trading_day_mode": trading_day_mode,
        "events_per_trading_day": events_per_trading_day,
        "action_counts": action_counts,
        "distinct_codes": distinct_codes,
        "contribution": contribution,
        "intent": build_intent_reconciliation(events, ledger_events or []),
    }


def build_intent_reconciliation(
    events: list[dict[str, Any]],
    ledger_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """变动事件 vs 决策登记的只读对账列表（纯函数，绝不回写账本）。

    对账口径：事件区间 [period_from, period_to] 内、同 code 的 `decision`
    事件构成该事件的「意图」；方向 +1 = 加仓/看多、-1 = 减仓/看空、0 = 持平。
    对照规则（列表对照，非绩效归因）：

      - 加仓/新增事件 × 加仓意图 → 一致；× 减仓意图 → 分歧
      - 减仓/清仓事件 × 减仓意图 → 一致；× 加仓意图 → 分歧
      - 同区间同时存在多空意图 → 混合意图（不计一致/分歧）
      - 仅有持平意图而发生变动 → 分歧（意图持有时实际动手）
      - 区间内无同 code 决策 → 无意图记录
      - 份额不可判定事件 → 不可判定（方向不可比，不硬对）

    Args:
        events: 事件列表（holding_change_events 契约）
        ledger_events: 决策账本全量事件（只读）

    Returns:
        {"rows": [...], "decision_count": int, "with_intent": int,
         "aligned": int, "divergent": int, "ledger_available": bool}
    """
    decisions = [ev for ev in ledger_events if ev.get("event") == decision_ledger.EVENT_DECISION]
    rows: list[dict[str, Any]] = []
    with_intent = 0
    aligned = 0
    divergent = 0

    for ev in events:
        action = ev.get("action")
        hit = [
            d
            for d in decisions
            if str(d.get("code") or "") == str(ev.get("code") or "")
            and _date_in_window(str(d.get("report_date") or ""), ev.get("period_from", ""), ev.get("period_to", ""))
        ]
        directions = {int(d.get("direction", decision_ledger.DIRECTION_FLAT)) for d in hit} if hit else set()
        intent_label, alignment = _align(action, directions)
        if directions:
            with_intent += 1
            if alignment == ALIGN_ALIGNED:
                aligned += 1
            elif alignment == ALIGN_DIVERGENT:
                divergent += 1
        rows.append(
            {
                "code": ev.get("code", ""),
                "name": ev.get("name", ""),
                "action": action,
                "shares_diff": ev.get("shares_diff"),
                "period_from": ev.get("period_from", ""),
                "period_to": ev.get("period_to", ""),
                "intent": intent_label,
                "decisions": [
                    {
                        "report_date": str(d.get("report_date") or ""),
                        "direction": int(d.get("direction", decision_ledger.DIRECTION_FLAT)),
                        "carrier": str(d.get("carrier") or ""),
                        "magnitude": str(d.get("magnitude") or ""),
                    }
                    for d in hit
                ],
                "alignment": alignment,
            }
        )

    return {
        "rows": rows,
        "decision_count": len(decisions),
        "with_intent": with_intent,
        "aligned": aligned,
        "divergent": divergent,
        "ledger_available": bool(decisions),
    }


# ── 跨品种同日重排识别（账户/数据结构变更签名） ────────────


def detect_account_reorder(
    events: list[dict[str, Any]],
    *,
    min_codes: int = REORDER_MIN_CODES,
) -> dict[str, Any] | None:
    """识别跨品种同日重排（纯函数）——账户/数据结构变更的结构性签名。

    两种形态（均非逐笔交易，归因时不得计入调仓解读）：

      ① 清仓→新增：日 D 有 ≥min_codes 个品种清仓，随后最近一期日 D′
         这些品种同名新增（典型：账户切换/份额重记后的全量回归）；
      ② 新增→清仓：日 D 有 ≥min_codes 个品种新增，随后最近一期日 D′
         同名清仓（典型：单日过桥持仓）。

    Returns:
        首个命中的 ``{"direction", "date", "next_date", "count", "codes"}``
        （日期为 YYYYMMDD；形态 ① 优先）；无命中返回 ``None``。
    """
    from collections import defaultdict

    clears: dict[str, set[str]] = defaultdict(set)
    adds: dict[str, set[str]] = defaultdict(set)
    for ev in events:
        code = str(ev.get("code") or "")
        day = _ymd(ev.get("period_to"))
        if not code or not day:
            continue
        if ev.get("action") == "清仓":
            clears[day].add(code)
        elif ev.get("action") == "新增":
            adds[day].add(code)

    for direction, src, dst in (("清仓→新增", clears, adds), ("新增→清仓", adds, clears)):
        for day in sorted(src):
            later = sorted(d for d in dst if d > day)
            if not later:
                continue
            next_day = later[0]
            overlap = src[day] & dst[next_day]
            if len(overlap) >= min_codes:
                return {
                    "direction": direction,
                    "date": day,
                    "next_date": next_day,
                    "count": len(overlap),
                    "codes": sorted(overlap),
                }
    return None


# ── 内部辅助 ─────────────────────────────────────────────


def _align(action: str | None, directions: set[int]) -> tuple[str, str]:
    """事件方向 × 意图方向 → (意图标签, 对照结论)。"""
    if action == "不可判定":
        return _INTENT_LABEL_NONE, ALIGN_INDETERMINATE
    if not directions:
        return _INTENT_LABEL_NONE, ALIGN_NO_INTENT

    has_long = decision_ledger.DIRECTION_LONG in directions
    has_short = decision_ledger.DIRECTION_SHORT in directions
    if has_long and has_short:
        return _INTENT_LABEL_MIXED, ALIGN_MIXED
    if has_long:
        intent = _INTENT_LABEL_LONG
    elif has_short:
        intent = _INTENT_LABEL_SHORT
    else:
        intent = _INTENT_LABEL_FLAT  # 仅持平意图

    wants_long = action in ("新增", "加仓")
    wants_short = action in ("减仓", "清仓")
    if wants_long and has_long:
        return intent, ALIGN_ALIGNED
    if wants_short and has_short:
        return intent, ALIGN_ALIGNED
    # 其余（方向相反，或仅有持平意图却发生变动）→ 分歧
    return intent, ALIGN_DIVERGENT


def _date_in_window(report_date: str, period_from: str, period_to: str) -> bool:
    """决策登记日是否落在事件区间内（含边界，按 YYYYMMDD 字典序比较）。"""
    day = _ymd(report_date)
    start = _ymd(period_from)
    end = _ymd(period_to)
    if not day or not start or not end:
        return False
    return start <= day <= end


def _ymd(ts: str) -> str:
    """任意时间戳形态 → YYYYMMDD（无法解析返回空串）。"""
    s = str(ts or "").strip()
    if len(s) >= 10 and s[4] == "-":
        return s[:10].replace("-", "")
    if len(s) >= 8 and s[:8].isdigit():
        return s[:8]
    return ""


def _window_trading_days(window_start: str, window_end: str) -> int:
    """复盘窗口交易日数（交易日历口径，日历/解析不可用时自然日回退）。"""
    start_date = _iso_date(window_start)
    end_date = _iso_date(window_end)
    if not start_date or not end_date:
        return 0
    return max(0, elapsed_trading_days_with_natural_fallback(start_date, end_date))


def _iso_date(ts: str) -> str:
    """时间戳 → YYYY-MM-DD（YYYYMMDDTHHMMSS / ISO / YYYY-MM-DD 三形态）。"""
    s = str(ts or "").strip()
    if len(s) >= 8 and s[:8].isdigit() and s[4] != "-":
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    return ""


def _contribution_breakdown(events: list[dict[str, Any]]) -> dict[str, Any]:
    """区间市值贡献分解：ΔMV = 份额变动贡献 + 价格变动贡献（逐事件分解后聚合）。

    分解式（恒等式，数学上精确）：
      ΔMV = (S1 - S0) * P0  +  S1 * (P1 - P0)
            └─ 份额变动贡献 ─┘   └─ 价格变动贡献 ─┘
      其中 P = 市值 / 份额。

    新增（S0=0 且 MV0=0）全部计入份额贡献；清仓（S1=0）价格分量自然为 0。
    份额字段缺失（None）或「市值 > 0 而份额 = 0」（价格轴不可判定）的事件
    不参与分解，计入 skipped_count——只呈现可判定事实，不虚构分量。
    """
    shares_total = 0.0
    price_total = 0.0
    market_value_change = 0.0
    skipped = 0

    for ev in events:
        if ev.get("indeterminate"):
            skipped += 1
            continue
        s0 = ev.get("shares_before")
        s1 = ev.get("shares_after")
        v0 = ev.get("value_before")
        v1 = ev.get("value_after")
        if s0 is None or s1 is None or v0 is None or v1 is None:
            skipped += 1
            continue
        delta = v1 - v0
        if s0 > 0:
            p0 = v0 / s0
            shares_part = (s1 - s0) * p0
            price_part = s1 * ((v1 / s1) - p0) if s1 > 0 else 0.0
        elif v0 == 0:
            # 从无到有：新增全额计入份额贡献（价格轴此前不存在）
            shares_part = delta
            price_part = 0.0
        else:
            skipped += 1  # 份额 0 而市值 > 0：价格轴不可判定，不虚构
            continue
        shares_total += shares_part
        price_total += price_part
        market_value_change += delta

    return {
        "shares_part": shares_total,
        "price_part": price_total,
        "market_value_change": market_value_change,
        "skipped_count": skipped,
    }
