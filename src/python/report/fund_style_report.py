"""基金风格判定 — 漂移检测与全基金分析入口。

对所有基金进行风格判定后，结合历史快照检测风格漂移，
输出含漂移等级的分析结果。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.report.fund_style_base import (
    _SIZE_ORDER,
    _STYLE_ORDER,
    _load_snapshot,
    _update_snapshot,
)
from src.python.report.fund_style_classify import classify_fund_style

logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════
#  漂移检测
# ═══════════════════════════════════════════════════════════


def _grid_distance(style_a: str, style_b: str) -> int:
    """计算两种风格在六宫格网格上的距离。

    距离定义：size 差 + style 差的绝对值。
    例：大盘成长→小盘成长 = 2（size差2格，style差0格）
        大盘成长→中盘价值 = 2（size差1格，style差1格）
        大盘成长→小盘价值 = 4（size差2格，style差2格）

    Returns:
        0-4 的网格距离（0=相同，4=完全相反）
    """
    if style_a == style_b or style_a == "--" or style_b == "--":
        return 0

    size_a = style_a[:2] if len(style_a) >= 2 else ""
    size_b = style_b[:2] if len(style_b) >= 2 else ""
    style_type_a = style_a[2:] if len(style_a) > 2 else ""
    style_type_b = style_b[2:] if len(style_b) > 2 else ""

    size_dist = (
        abs(_SIZE_ORDER.index(size_a) - _SIZE_ORDER.index(size_b))
        if size_a in _SIZE_ORDER and size_b in _SIZE_ORDER
        else 0
    )
    style_dist = (
        abs(_STYLE_ORDER.index(style_type_a) - _STYLE_ORDER.index(style_type_b))
        if style_type_a in _STYLE_ORDER and style_type_b in _STYLE_ORDER
        else 0
    )

    return size_dist + style_dist


def _drift_level(distance: int) -> str:
    """根据网格距离返回漂移等级。"""
    if distance >= 3:
        return "严重"
    elif distance >= 2:
        return "中度"
    elif distance >= 1:
        return "轻度"
    return "无"


def analyze_style_for_all_funds(
    fund_holdings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """对所有基金进行风格判定和漂移检测。

    Args:
        fund_holdings: {fund_code: {name, holdings: [{name, code, ratio}, ...]}, ...}

    Returns:
        {"results": [{code, name, current_style, prev_style, drift_level,
                      drift_score, is_estimated, is_first_check, ...}, ...],
         "snapshot_updated": bool}
    """
    snapshot = _load_snapshot() or {}
    is_first_run = not bool(snapshot)
    new_snapshot: dict[str, Any] = {}
    results: list[dict[str, Any]] = []

    _total = len(fund_holdings)
    for idx, (code, info) in enumerate(fund_holdings.items(), 1):
        name = info.get("name", code)
        holdings = info.get("holdings", [])
        logger.info("基金风格分析 [%d/%d]: %s (%s)", idx, _total, name, code)
        if not holdings:
            continue

        # 风格判定
        style_result = classify_fund_style(code, holdings)
        current_style = style_result.get("style", "--")
        is_estimated = style_result.get("is_estimated", False)

        # 漂移检测
        prev_entry = snapshot.get(code)
        prev_style = prev_entry.get("style") if prev_entry else None
        is_first_check = is_first_run or prev_style is None

        # 生成备注
        remark_parts = []
        if is_first_check:
            remark = "基准确立中"
        else:
            if is_estimated:
                remark_parts.append("估算风格")
            remark = "；".join(remark_parts) if remark_parts else ""

        if is_first_check:
            drift_level = "基准确立中" if current_style != "--" else "--"
            drift_score = None
        else:
            distance = _grid_distance(str(prev_style), current_style)
            drift_level = _drift_level(distance)
            drift_score = distance

        results.append(
            {
                "code": code,
                "name": name,
                "current_style": current_style,
                "prev_style": prev_style or "--",
                "drift_level": drift_level,
                "drift_score": drift_score,
                "is_estimated": is_estimated,
                "is_first_check": is_first_check,
                "remark": remark,
                "details": style_result.get("details", []),
            }
        )

        if current_style != "--":
            new_snapshot[code] = {
                "style": current_style,
                "is_estimated": is_estimated,
                "check_date": datetime.now().strftime("%Y-%m-%d"),
            }

    if new_snapshot:
        _update_snapshot(new_snapshot)

    return {"results": results, "snapshot_updated": bool(new_snapshot)}
