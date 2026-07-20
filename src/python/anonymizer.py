"""持仓匿名化模块 — 名称替换/数量模糊/关闭三种模式。

用于在分享报告时隐藏真实持仓数据，保护隐私。

使用方式：
  >>> from src.python.anonymizer import anonymize_holdings
  >>> anon = anonymize_holdings(holdings, mode="name_replace")
  >>> anon[0].name
  '持仓A'

三模式：
  - "off":      不处理，原样返回
  - "name_replace": 名称替换为"持仓A/B/C..."，保留代码和份额
  - "quantity_blur": 名称替换 + 份额四舍五入到百位（隐藏精确仓位）
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from src.python.models import Holding

logger = logging.getLogger("invest")

_ANONYMIZATION_MODES = frozenset({"off", "name_replace", "quantity_blur"})

__all__ = [
    "anonymize_holdings",
    "anonymize_holdings_details",
    "is_anonymization_enabled",
]


def is_anonymization_enabled(mode: str) -> bool:
    """判断匿名化是否启用。

    Args:
        mode: 匿名化模式

    Returns:
        True 表示需执行匿名化处理
    """
    return mode in ("name_replace", "quantity_blur")


def anonymize_holdings(
    holdings: list[Holding],
    mode: str = "off",
) -> list[Holding]:
    """对持仓列表执行匿名化处理。

    Args:
        holdings: 原始持仓列表
        mode: 匿名化模式

    Returns:
        匿名化后的持仓列表（仅在启用时创建副本）
    """
    if mode not in _ANONYMIZATION_MODES:
        logger.warning("[anonymizer] 未知匿名化模式 '%s'，使用 'off'", mode)
        mode = "off"

    if mode == "off":
        return holdings

    result = copy.deepcopy(holdings)

    # 名称替换（所有启用模式均执行）
    _replace_names(result)

    # 数量模糊
    if mode == "quantity_blur":
        _blur_shares(result)

    logger.info("[anonymizer] 持仓匿名化完成（模式: %s）", mode)
    return result


def anonymize_holdings_details(
    details: list[dict[str, Any]],
    mode: str = "off",
) -> list[dict[str, Any]]:
    """对持仓明细字典列表执行匿名化处理。

    适配 report/handlers_report.py 中 prepare_report_data 返回的
    holdings_details 格式。

    Args:
        details: 持仓明细字典列表
        mode: 匿名化模式

    Returns:
        匿名化后的列表
    """
    if mode not in _ANONYMIZATION_MODES:
        mode = "off"

    if mode == "off":
        return details

    result = copy.deepcopy(details)
    _name_counter = 0
    _name_map: dict[str, str] = {}

    for d in result:
        code = d.get("code", "")
        if code and code not in _name_map:
            _name_counter += 1
            _name_map[code] = f"持仓{_num_to_label(_name_counter)}"
        if code in _name_map:
            d["name"] = _name_map[code]

    if mode == "quantity_blur":
        for d in result:
            mv = d.get("market_value", 0)
            if mv:
                d["market_value"] = _blur_value(mv)

    return result


def _replace_names(holdings: list[Holding]) -> None:
    """将持仓名称替换为匿名代号。"""
    _counter = 0
    _seen_codes: dict[str, str] = {}
    for h in holdings:
        if h.code not in _seen_codes:
            _counter += 1
            _seen_codes[h.code] = f"持仓{_num_to_label(_counter)}"
        h.name = _seen_codes[h.code]


def _blur_shares(holdings: list[Holding]) -> None:
    """将份额四舍五入到百位（隐藏精确仓位）。"""
    for h in holdings:
        h.shares = round(h.shares / 100) * 100
        if h.shares < 100 and h.shares > 0:
            h.shares = 100  # 最小显示单位


def _blur_value(value: float) -> float:
    """将数值四舍五入到千位（隐藏精确金额）。"""
    return round(value / 1000) * 1000


def _num_to_label(n: int) -> str:
    """数字转字母标签：1→A, 2→B, ..., 26→Z, 27→AA, 28→AB..."""
    label = ""
    while n > 0:
        n -= 1
        label = chr(ord("A") + n % 26) + label
        n //= 26
    return label or "A"
