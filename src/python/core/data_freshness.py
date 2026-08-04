"""数据新鲜度与异常跳变检测 — 数据质量仪表盘「可信度」区块的数据源。

对每个持仓品种做两个维度的数据质量判定：

  1. 数据新鲜度（可信度分级）：
     - fresh（实时）      — 净值/行情日期等于最近交易日
     - cached（缓存）     — 净值日期等于前一交易日（正常 T-1，如 QDII/场外官方净值）
     - stale（过期）      — 净值日期早于前一交易日（数据滞后，需人工核对）
     - degraded（降级）   — 无有效行情（price<=0 或「暂无行情」）
  2. 单日异常跳变检测：
     - 仅对 fresh/cached 品种比较当前价与昨收，单日涨跌幅 ≥±20% 视为「疑似数据错误」；
     - stale/degraded 跳过跳变判定——净值日期早于前一交易日意味着期间可能跨多个
       交易日/非交易日，累计涨跌不能误判为单日异常（非交易日不误报）。

消费方：
  `report/orchestrator.prepare_report_data()` 组装为 `data_freshness`
  C19 契约注入 pipeline_data，供 18 章「数据质量仪表盘」可信度区块与
  报告头部数据异常摘要行渲染。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("invest")

# ── 新鲜度常量 ───────────────────────────────────────────────

FRESHNESS_FRESH = "fresh"
FRESHNESS_CACHED = "cached"
FRESHNESS_STALE = "stale"
FRESHNESS_DEGRADED = "degraded"

# 展示文案（语义名，避免任务代号扩散到 UI）
FRESHNESS_LABELS: dict[str, str] = {
    FRESHNESS_FRESH: "实时",
    FRESHNESS_CACHED: "缓存（T-1）",
    FRESHNESS_STALE: "过期",
    FRESHNESS_DEGRADED: "降级",
}

FRESHNESS_REASONS: dict[str, str] = {
    FRESHNESS_FRESH: "数据已更新至最近交易日",
    FRESHNESS_CACHED: "净值为前一交易日（T-1），正常",
    FRESHNESS_STALE: "净值日期滞后，可能停更或数据延迟",
    FRESHNESS_DEGRADED: "未取到有效行情，数据不可用",
}

# 需要提示的异常新鲜度集合（实时不计入）
_ABNORMAL_FRESHNESS: frozenset[str] = frozenset(
    {FRESHNESS_STALE, FRESHNESS_DEGRADED}
)

# 单日跳变阈值（默认 ±20%）
_JUMP_THRESHOLD_DEFAULT = 0.20


# ── 行情明细读取 ─────────────────────────────────────────────


def _detail_value(detail: Any, field: str, default: Any = None) -> Any:
    """从行情明细读取字段（兼容 dict 或含属性对象，如 DetailRow）。"""
    if detail is None:
        return default
    if isinstance(detail, dict):
        return detail.get(field, default)
    return getattr(detail, field, default)


def _has_effective_quote(detail: Any) -> bool:
    """判断该品种是否取到有效行情（price>0 且非「暂无行情」）。"""
    if detail is None:
        return False
    price = _detail_value(detail, "price", 0.0)
    if price is None or price <= 0:
        return False
    price_type = _detail_value(detail, "price_type", "") or ""
    if price_type == "暂无行情":
        return False
    return True


def _normalize_date(date_str: Any) -> str | None:
    """规范化日期字符串（YYYY-MM-DD），无效输入返回 None。"""
    if not date_str:
        return None
    text = str(date_str).strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    except ValueError:
        return None


# ── 单品种新鲜度分类 ─────────────────────────────────────────


def classify_freshness(
    detail: Any,
    trading_day: str,
    prev_trading_day: str,
) -> str:
    """判定单品种数据新鲜度。

    优先级：降级（无有效行情）> 实时 > 缓存 > 过期。

    Args:
        detail: 行情明细（可为 None）
        trading_day: 最近交易日 YYYY-MM-DD
        prev_trading_day: 前一交易日 YYYY-MM-DD

    Returns:
        新鲜度常量之一
    """
    if not _has_effective_quote(detail):
        return FRESHNESS_DEGRADED

    nav_date = _normalize_date(_detail_value(detail, "nav_date"))
    if nav_date is None:
        return FRESHNESS_STALE
    if nav_date == trading_day:
        return FRESHNESS_FRESH
    if nav_date == prev_trading_day:
        return FRESHNESS_CACHED
    return FRESHNESS_STALE


# ── 单日异常跳变检测 ─────────────────────────────────────────


def detect_price_jumps(
    details: list,
    trading_day: str,
    prev_trading_day: str,
    threshold: float = _JUMP_THRESHOLD_DEFAULT,
) -> list[dict]:
    """检测单日 ±threshold 异常跳变（疑似数据错误）。

    仅对 fresh/cached 品种判定（净值日期为最近交易日或其前一交易日），
    stale/degraded 跳过——跨多个交易日/非交易日的累计涨跌不视为单日异常。

    Args:
        details: 行情明细列表
        trading_day: 最近交易日 YYYY-MM-DD
        prev_trading_day: 前一交易日 YYYY-MM-DD
        threshold: 单日涨跌幅阈值（小数，默认 0.20 = ±20%）

    Returns:
        跳变事件列表，每项：:
            {"code", "name", "change_pct", "direction", "nav_date", "label"}
        change_pct 为百分比（如 25.0 表示 +25%）；无跳变返回空列表。
    """
    jumps: list[dict] = []
    for detail in details or []:
        code = _detail_value(detail, "code", "") or ""
        if not code:
            continue
        freshness = classify_freshness(detail, trading_day, prev_trading_day)
        if freshness not in (FRESHNESS_FRESH, FRESHNESS_CACHED):
            continue

        price = _detail_value(detail, "price", 0.0) or 0.0
        yesterday_close = _detail_value(detail, "yesterday_close", 0.0) or 0.0
        if not yesterday_close or abs(yesterday_close) <= 1e-10:
            continue

        change_pct = (price - yesterday_close) / yesterday_close * 100
        if abs(change_pct) < threshold * 100:
            continue

        direction = "up" if change_pct > 0 else "down"
        nav_date = _normalize_date(_detail_value(detail, "nav_date")) or ""
        jumps.append(
            {
                "code": code,
                "name": _detail_value(detail, "name", "") or "",
                "change_pct": round(change_pct, 2),
                "direction": direction,
                "nav_date": nav_date,
                "label": f"疑似数据错误（单日 {change_pct:+.2f}%）",
            }
        )
    return jumps


# ── 对外主入口：可信度摘要 ───────────────────────────────────


def build_freshness_summary(
    holdings: list,
    details: list | None = None,
    trading_day: str = "",
    prev_trading_day: str = "",
) -> dict:
    """构建可信度摘要 C19 契约（`data_freshness` 键结构）。

    逐品种标注新鲜度分类与单日跳变事件，聚合异常计数供报告头部
    数据异常摘要行与 18 章可信度区块消费。

    Args:
        holdings: Holding 列表
        details: 行情明细列表（可为 None）
        trading_day: 最近交易日 YYYY-MM-DD；为空时尝试从行情明细
            nav_date 推断最近交易日（仅用于无显式传入的兼容场景）
        prev_trading_day: 前一交易日 YYYY-MM-DD

    Returns:
        契约 dict：::
            {"available": bool, "items": list[dict], "abnormal_count": int,
             "summary": str}
        items 每项：:
            {"code", "name", "account", "freshness", "freshness_label",
             "jump", "jump_label", "change_pct"}
    """
    if not holdings:
        return {"available": False, "items": [], "abnormal_count": 0, "summary": "无持仓品种"}

    # 未显式传入交易日时，以明细中最新 nav_date 作为最近交易日近似
    t_day = trading_day or _infer_latest_nav_date(details)
    p_day = prev_trading_day

    detail_map: dict[str, Any] = {}
    for d in details or []:
        code = _detail_value(d, "code", "") or ""
        if code:
            detail_map.setdefault(code, d)

    jumps = detect_price_jumps(details or [], t_day, p_day)
    jump_by_code: dict[str, dict] = {j["code"]: j for j in jumps}

    items: list[dict] = []
    for h in holdings:
        detail = detail_map.get((h.code or "").strip())
        freshness = classify_freshness(detail, t_day, p_day)
        jump = jump_by_code.get((h.code or "").strip())
        change_pct = (
            round(
                ((_detail_value(detail, "price", 0.0) or 0.0) - (_detail_value(detail, "yesterday_close", 0.0) or 0.0))
                / (_detail_value(detail, "yesterday_close", 0.0) or 1.0)
                * 100,
                2,
            )
            if detail and (_detail_value(detail, "yesterday_close", 0.0) or 0.0) > 0
            else 0.0
        )
        items.append(
            {
                "code": h.code,
                "name": h.name,
                "account": h.account,
                "freshness": freshness,
                "freshness_label": FRESHNESS_LABELS.get(freshness, freshness),
                "reason": FRESHNESS_REASONS.get(freshness, ""),
                "jump": bool(jump),
                "jump_label": jump["label"] if jump else "",
                "change_pct": change_pct,
            }
        )

    abnormal = [i for i in items if i["freshness"] in _ABNORMAL_FRESHNESS or i["jump"]]
    summary = f"{len(items)} 个品种，{len(abnormal)} 个数据异常" if items else "无持仓品种"
    return {
        "available": True,
        "items": items,
        "abnormal_count": len(abnormal),
        "summary": summary,
    }


def _infer_latest_nav_date(details: list | None) -> str:
    """从行情明细中推断最近的净值日期（用于未显式传入交易日时的近似）。"""
    latest: str | None = None
    for d in details or []:
        nav = _normalize_date(_detail_value(d, "nav_date"))
        if nav and (latest is None or nav > latest):
            latest = nav
    return latest or datetime.now().strftime("%Y-%m-%d")
