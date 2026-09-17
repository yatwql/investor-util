"""数值/时间字段归一原语 —— 全链路防 NaN/±inf 污染与非法时间戳。

背景：``float("nan")`` 是**真值**，``float("inf")`` 更会一路穿透到聚合、
绘图与 JSON 序列化。``nan or 0.0`` 这类看似兜底的写法实际什么也没拦
（NaN 为真，``or`` 短路不生效）。本模块把散落在 providers/analysis/report
各层的十来个私有解析器收敛为一处实现，只保证一条不变量——**返回的数值一定有限**。

分层：本模块只依赖 ``core.constants``（该模块本身仅用 stdlib，故不成环），因此 ``core`` / ``providers`` /
``analysis`` / ``report`` / ``fetcher`` 任一侧均可安全导入。这是它不放在
``analysis/_math_utils.py`` 的原因——那个模块是统计专用，且 ``analysis``
已依赖 ``core``，反向导入会成环。

两个入口的取舍：

- :func:`safe_num` —— **宽容**：数值字符串会尝试解析（对接 JSON/网页脏字段）。
- :func:`strict_num` —— **严格**：只接受 ``int``/``float``，字符串一律视为非数值
  （对接序列化敏感场景，如账本落盘——字符串化数值混入会破坏类型契约）。

时间字段同理：上游（基金披露、财报元数据等）给的是**毫秒 Unix 时间戳**，
展示层与契约层要的是 ``YYYY-MM-DD`` 自然日；非法/缺失一律返回空串而不是抛异常
（:func:`ms_to_date_str`）。
"""

from __future__ import annotations

import math
from datetime import datetime

from src.python.core.constants import BEIJING_TZ
from typing import Any

__all__ = ["finite_or", "is_finite_number", "ms_to_date_str", "safe_num", "strict_num"]


def strict_num(value: Any, *, default: float | int | None = None) -> float | int | None:
    """严格数值归一：仅接受有限的 ``int``/``float``，其余返回 ``default``。

    ``bool`` 被显式排除——它是 ``int`` 的子类，混入会让 ``True`` 变成 ``1``。
    ``int`` 原样返回（不转 float），避免整数份额/ID 被改写成浮点。

    Args:
        value: 待归一的值
        default: 非数值或不有限时的返回值

    Returns:
        有限的 ``int``/``float``，否则 ``default``
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if isinstance(value, float) and not math.isfinite(value):
        return default
    return value


def safe_num(value: Any, *, default: float | int | None = None) -> float | int | None:
    """宽容数值归一：数值字符串先尝试解析，再施加有限性检查。

    解析失败的字符串（``"--"``、``""``、``"N/A"``）与非数值类型同样返回 ``default``。
    ``bool`` 仍被排除（防止 ``True`` 静默变 ``1``）。

    Args:
        value: 待归一的值（数值或数值字符串）
        default: 非数值或不有限时的返回值

    Returns:
        有限的 ``int``/``float``，否则 ``default``
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return strict_num(value, default=default)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except (ValueError, TypeError):
            return default
        return parsed if math.isfinite(parsed) else default
    return default


def finite_or(value: Any, fallback: float = 0.0) -> float:
    """``value or fallback`` 的 NaN 安全替代。

    ``float("nan")`` 为真值，故 ``nan or 0.0`` 求值仍是 NaN——本函数先归一
    再兜底，是 ````x or 0.0```` 惯用法的正确写法。始终返回 ``float``，便于
    直接参与算术。

    Args:
        value: 待归一的值
        fallback: 非有限值时的兜底数

    Returns:
        有限的 ``float``
    """
    normalized = safe_num(value, default=fallback)
    return float(normalized)  # type: ignore[arg-type]


def is_finite_number(value: Any) -> bool:
    """判定是否为有限真数值（排除 ``bool``/``None``/字符串/``NaN``/``±inf``）。

    等同于 ``strict_num(value) is not None``，但作为谓词在读起来更直观，
    也避免调用方误写 ``if not value``（``0`` 是合法数值却为假）。
    """
    return strict_num(value) is not None


def ms_to_date_str(value: Any) -> str:
    """毫秒 Unix 时间戳 → ``YYYY-MM-DD``（本地自然日）；非法/缺失返回空串。

    上游（基金披露持仓、财报元数据等）的时间字段是毫秒戳，展示层与数据契约要的是
    自然日字符串。三种非法形态统一兜底、绝不抛：非数值（``None``/``"bad"``）、
    非正值（``0`` / 负数，上游用 0 表示「无」）、超出 ``datetime`` 可表示范围。

    与 :func:`safe_num` 同一取舍：**宽容**——只保证返回可安全展示的字符串。

    时区：一律按 :data:`core.constants.BEIJING_TZ`（UTC+8 固定偏移）解释为**北京自然日**，
    不用本机时区——否则同一毫秒戳在不同运行环境会算成相邻两天（CI 跑 UTC 时实测踩过）。
    """
    num = safe_num(value)
    if num is None or num <= 0:
        return ""
    try:
        return datetime.fromtimestamp(num / 1000.0, tz=BEIJING_TZ).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return ""
