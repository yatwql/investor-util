"""申购可行性判定 — 受限标的可行性纯函数（what-if 目标持仓面的判定入口）。

判定所需数据以纯形参下传（受限索引 ``restricted_index``，字段值由 report 层
契约单源渲染）——本模块不 import report、不做数值格式化、零 I/O 零日志
（架构分层：report → analysis 单向，不新增反向依赖）。

设计文档 ``docs/plan/fund-purchase-limit-advice-design.md`` §3.2 判定矩阵：
宁缺毋错——金额或限额任一未知只提示限购、不给天数估算。
"""

from __future__ import annotations

import math
from typing import Any

#: 可行性天数阈值（交易日）：估算天数超过该值判定路径不可行
FEASIBILITY_MAX_DAYS = 60


def evaluate_purchase_feasibility(
    code: str,
    amount: float | None,
    restricted_index: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """受限标的申购可行性判定（纯函数，零 I/O）。

    Args:
        code: 标的代码（场外基金代码；场内/查无此码 → 索引不含 → None）
        amount: 建议买入/需合并金额（未知 → None，不估天数；<=0 视为未知）
        restricted_index: 受限标的预格式化索引（契约字段；None/空 → 无判定）

    Returns:
        ``None``：未受限/索引空/查无此码 —— 无判定即现网行为（零回归）。
        受限时 ``dict``（字段全部来自索引与纯算术）：

        - ``kind="limited"``（限大额）：``days = ceil(amount / limit)``
          （交易日估算）；金额或限额任一未知 → ``days=None``、``feasible=None``
        - ``kind="suspended"``（暂停申购）：``next_open_text`` 提示下一开放日
        - ``feasible``：``days <= FEASIBILITY_MAX_DAYS``；days 未知 → None
    """
    if not restricted_index:
        return None
    entry = restricted_index.get(str(code))
    if not isinstance(entry, dict):
        return None
    status = str(entry.get("status") or "")
    base: dict[str, Any] = {
        "code": str(code),
        "status": status,
        "limit_text": str(entry.get("limit_text") or ""),
        "next_open_text": str(entry.get("next_open_text") or ""),
    }
    if status == "暂停申购":
        return {**base, "kind": "suspended", "amount": None, "days": None, "feasible": None}
    if status != "限大额":
        # 索引准入只收限大额/暂停申购；其他状态（防御分支）无判定
        return None
    limit = entry.get("limit")
    amount_ok = isinstance(amount, (int, float)) and math.isfinite(amount) and amount > 0
    limit_ok = isinstance(limit, (int, float)) and math.isfinite(limit) and limit > 0
    if not (amount_ok and limit_ok):
        # 金额/限额任一未知（含 0 元限额，解析层已单点转 None）→ 不给天数
        return {**base, "kind": "limited", "amount": None, "days": None, "feasible": None}
    days = math.ceil(amount / limit)
    return {
        **base,
        "kind": "limited",
        "amount": float(amount),
        "days": days,
        "feasible": days <= FEASIBILITY_MAX_DAYS,
    }


def describe_feasibility(note: dict[str, Any]) -> str:
    """受限提示话术（静态模板 + 索引字段值；Excel/HTML 两侧渲染共用，单源）。

    Args:
        note: :func:`evaluate_purchase_feasibility` 返回的判定 dict（或含同名字段的提示条目）

    Returns:
        提示文案（含「估算·以渠道显示为准」口径，不作成交承诺）。
    """
    if note.get("kind") == "suspended":
        text = "暂停申购"
        next_open = str(note.get("next_open_text") or "")
        if next_open:
            text += f"，下一开放日 {next_open}"
        return f"{text}，请待开放后再执行"
    limit_text = str(note.get("limit_text") or "")
    if limit_text and limit_text != "限额未知":
        text = f"限大额，日限 {limit_text} 元"
    else:
        text = "限大额，限额未知"
    days = note.get("days")
    if not isinstance(days, int):
        return f"{text}，按当前额度无法估算可执行天数（以渠道显示为准）"
    if note.get("feasible"):
        return f"{text}，预计需 {days} 个交易日（估算·以渠道显示为准）"
    return f"{text}，预计需 {days} 个交易日（> {FEASIBILITY_MAX_DAYS}）路径不可行（估算·以渠道显示为准）"
