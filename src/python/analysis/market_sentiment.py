"""市场情绪与资金热点 —— 龙虎榜 / 连板梯队 × 持仓与穿透标的（纯装配）。

**用途**：把市场级情绪数据（同花顺官方：龙虎榜、连板梯队）收敛为「与我有关」的事件行——
本模块只保留**命中持仓/穿透标的代码**的条目，不做概念联想与模糊匹配（宁可少报，不可误导）：

  - ``龙虎榜``：该标的当日上榜（净买额 / 游资净买额 / 机构净买额 / 上榜原因 / 3 日榜标记）
  - ``连板梯队``：该标的出现在当日连板梯队里（板位、次日是否封板）

**为什么不按概念联想**：概念名在两侧口径不一（持仓侧来自穿透层的概念标签、市场侧来自官方
概念表），按名字匹配会产生大量假命中；且这类「概念共振」判断属推演而非数据事实，本章不做。

输入都是上游原始响应（``{"item": [...]}`` / ``{"stock_items": [...]}``），
本模块是纯函数：无网络、无缓存、不抛异常，脏值一律落下（金额单位换算为**亿元**、比率转百分数）。
"""

from __future__ import annotations

from typing import Any

from src.python.core.num_utils import safe_num

#: 连板梯队板位标签（上游键名 → 中文）
_BOARD_LABELS: dict[str, str] = {
    "two_board": "二连板",
    "three_board": "三连板",
    "four_board": "四连板",
    "five_board": "五连板",
    "six_board": "六连板",
    "seven_over": "七连板及以上",
}

#: 单条命中事件的行字段（契约稳定面）
_ROW_FIELDS: tuple[str, ...] = (
    "code",
    "name",
    "holding_kind",
    "event_type",
    "event_date",
    "net_value_yi",
    "hot_money_net_value_yi",
    "org_net_value_yi",
    "hot_rank",
    "range_days",
    "limit_reason",
    "concepts",
    "board_label",
    "board_num",
    "seal_nextday",
)


def _yi(value: Any) -> float | None:
    """元 → 亿元（保留两位）；非法值 ``None``。"""
    num = safe_num(value)
    return round(num / 1e8, 2) if num is not None else None


def _concepts(item: dict[str, Any]) -> str:
    """概念列表 → 顿号分隔的前三个（其余略）。"""
    names = [
        str(c.get("name")).strip()
        for c in (item.get("concept_list") or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    ]
    return "、".join(names[:3])


def tracked_targets(holdings: list, penetrated_assets: list | None = None) -> dict[str, dict[str, str]]:
    """跟踪标的映射：``{code: {"name": …, "holding_kind": 直接持有/穿透}}``。

    直接持仓优先（同一代码既持仓又被穿透时按「直接持有」记）。
    """
    targets: dict[str, dict[str, str]] = {}
    for h in holdings or []:
        code = str(getattr(h, "code", "") or "").strip()
        if code:
            targets[code] = {"name": str(getattr(h, "name", "") or ""), "holding_kind": "直接持有"}
    for asset in penetrated_assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        codes: list[str] = []
        if asset.get("code"):
            codes.append(str(asset["code"]))
        nested = asset.get("codes")
        if isinstance(nested, (list, set, tuple)):
            codes.extend(str(c) for c in nested)
        for code in codes:
            code = code.strip()
            if code and code not in targets:
                targets[code] = {"name": name, "holding_kind": "穿透"}
    return targets


def _dragon_tiger_rows(dragon_tiger: dict[str, Any] | None, targets: dict[str, dict[str, str]]) -> list[dict]:
    """龙虎榜命中行（按净买额降序）。"""
    trade_date = str((dragon_tiger or {}).get("trade_date") or "")
    rows: list[dict] = []
    for item in (dragon_tiger or {}).get("stock_items") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("ticker") or "").strip()
        if code not in targets:
            continue
        rows.append(
            {
                "code": code,
                "name": str(item.get("name") or targets[code]["name"]),
                "holding_kind": targets[code]["holding_kind"],
                "event_type": "龙虎榜",
                "event_date": trade_date,
                "net_value_yi": _yi(item.get("net_value")),
                "hot_money_net_value_yi": _yi(item.get("hot_money_net_value")),
                "org_net_value_yi": _yi(item.get("org_net_value")),
                "hot_rank": safe_num(item.get("hot_rank")),
                "range_days": safe_num(item.get("range_days")),
                "limit_reason": str(item.get("limit_reason") or ""),
                "concepts": _concepts(item),
                "board_label": "",
                "board_num": None,
                "seal_nextday": None,
            }
        )
    rows.sort(key=lambda r: (r["net_value_yi"] is None, -(r["net_value_yi"] or 0)))
    return rows


def _ladder_rows(ladder: dict[str, Any] | None, targets: dict[str, dict[str, str]]) -> list[dict]:
    """连板梯队命中行（最新交易日；板位由高到低）。"""
    items = [i for i in ((ladder or {}).get("item") or []) if isinstance(i, dict)]
    if not items:
        return []
    # item 按日期倒序给出（实测首项为最新交易日），取首项即可
    latest = items[0]
    event_date = str(latest.get("date") or "")
    rows: list[dict] = []
    for board_key, members in (latest.get("boards") or {}).items():
        for member in members or []:
            if not isinstance(member, dict):
                continue
            code = str(member.get("ticker") or "").strip()
            if code not in targets:
                continue
            rows.append(
                {
                    "code": code,
                    "name": str(member.get("name") or targets[code]["name"]),
                    "holding_kind": targets[code]["holding_kind"],
                    "event_type": "连板梯队",
                    "event_date": event_date,
                    "net_value_yi": None,
                    "hot_money_net_value_yi": None,
                    "org_net_value_yi": None,
                    "hot_rank": None,
                    "range_days": None,
                    "limit_reason": "",
                    "concepts": "",
                    "board_label": _BOARD_LABELS.get(str(board_key), str(board_key)),
                    "board_num": safe_num(member.get("board_num")),
                    "seal_nextday": bool(member.get("seal_nextday"))
                    if member.get("seal_nextday") is not None
                    else None,
                }
            )
    rows.sort(key=lambda r: (-(r["board_num"] or 0), r["code"]))
    return rows


def build_market_sentiment(
    dragon_tiger: dict[str, Any] | None,
    ladder: dict[str, Any] | None,
    targets: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """两份上游响应 + 跟踪标的 → 市场情绪契约。

    Returns:
        ``{available, reason, trade_date, summary, rows, failures, entry_count}``；两份数据都没有
        可用条目时 ``available=False``（由展示层写占位，不阻断主链路）。
    """
    failures: list[dict[str, str]] = []
    if not dragon_tiger:
        failures.append({"source": "龙虎榜", "reason": "未取到数据（源不可用或未配置凭据）"})
    if not ladder:
        failures.append({"source": "连板梯队", "reason": "未取到数据（源不可用或未配置凭据）"})

    rows = _dragon_tiger_rows(dragon_tiger, targets) + _ladder_rows(ladder, targets)
    # 两源皆不可用 → 降级（写占位）；只要有一源可用就出契约——**即使零命中**也要给市场概览，
    # 否则价值型组合（常年不涨停/不上榜）会让整块恒空，读者既看不到市场情绪、也不知道是空还是坏
    if not (dragon_tiger or ladder):
        return {
            "available": False,
            "reason": "情绪面数据不可用",
            "trade_date": "",
            "summary": {},
            "rows": [],
            "failures": failures,
            "entry_count": 0,
        }

    board_caps = ((ladder or {}).get("window") or {}).get("board_caps") or {}
    return {
        "available": True,
        "reason": "" if rows else "当日无持仓/穿透标的命中龙虎榜或连板梯队",
        "trade_date": str((dragon_tiger or {}).get("trade_date") or ""),
        "summary": {
            "board_caps": {_BOARD_LABELS.get(k, k): safe_num(v) for k, v in board_caps.items()},
            "lhb_stock_count": safe_num((dragon_tiger or {}).get("stock_count")),
            "ladder_date": str(((_ladder_latest_date(ladder)) or "")),
        },
        "rows": rows,
        "failures": failures,
        "entry_count": len(rows),
    }


def _ladder_latest_date(ladder: dict[str, Any] | None) -> str:
    """连板梯队最新交易日（取 ``window.date_list`` 首项，缺失回退 item 首项）。"""
    window = (ladder or {}).get("window") or {}
    dates = [str(d) for d in (window.get("date_list") or []) if str(d or "").strip()]
    if dates:
        return dates[0]
    items = [i for i in ((ladder or {}).get("item") or []) if isinstance(i, dict)]
    return str(items[0].get("date") or "") if items else ""


__all__ = ["build_market_sentiment", "tracked_targets"]
