"""持仓集中度监控计算模块。

计算每只基金的前 N 大持仓占比（top3/top5/top10），
与历史快照对比，输出环比变化和预警级别。

关键设计：
  - 独立快照键 fund_concentration_snapshot（固定键名，无指纹后缀）
  - 持仓指纹变化不影响快照，确保环比连续性
  - 首次运行输出"基线已记录"状态
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set

logger = logging.getLogger("invest")

_SNAPSHOT_KEY = "fund_concentration_snapshot"
_SNAPSHOT_TTL = 365 * 86400  # 接近永久

_CONCENTRATION_THRESHOLDS = [
    (3, "top3_pct"),
    (5, "top5_pct"),
    (10, "top10_pct"),
]


def _load_history_snapshot() -> dict[str, Any] | None:
    """读取历史集中度快照（固定键 fund_concentration_snapshot）。

    Returns:
        {code: {top10_pct, check_date, ...}} 或 None（首次运行/损坏）
    """
    return cache_get(_SNAPSHOT_KEY, _SNAPSHOT_TTL)


def _save_history_snapshot(current: list[dict[str, Any]]) -> None:
    """保存本次集中度数据到历史快照（覆写）。

    快照格式：
        {code: {top3_pct: float, top5_pct: float, top10_pct: float,
                check_date: str}, ...}
    """
    snapshot: dict[str, Any] = {}
    for item in current:
        code = item.get("code", "")
        if not code:
            continue
        snapshot[code] = {
            "top3_pct": item.get("top3_pct", 0.0),
            "top5_pct": item.get("top5_pct", 0.0),
            "top10_pct": item.get("top10_pct", 0.0),
            "check_date": datetime.now().strftime("%Y-%m-%d"),
        }
    if snapshot:
        cache_set(_SNAPSHOT_KEY, snapshot)


def _calc_alert_level(top10_pct: float, change_pct: float | None) -> str:
    """根据当前集中度和环比变化计算预警级别。

    Args:
        top10_pct: 当前前 10 大持仓占比（百分比，如 65.0）
        change_pct: 环比变化百分点（如 +15.0），None 表示无历史数据

    Returns:
        "紧急" / "关注" / "正常"
    """
    if change_pct is not None and change_pct > 20:
        return "紧急"
    if change_pct is not None and change_pct > 10:
        return "关注"
    if top10_pct > 80:
        return "关注"
    return "正常"


def compute_concentration(
    fund_holdings: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """计算基金的持仓集中度。

    对每只有持仓数据的基金，计算前 3/5/10 大持仓占比，
    并与历史快照对比得出环比变化和预警级别。

    Args:
        fund_holdings: {fund_code: {name, holdings: [{name, code, ratio}, ...]}, ...}
            其中 holdings 已按 ratio 降序排列（fetch_fund_holdings 默认顺序）

    Returns:
        [{code, name,
          top3_pct, top5_pct, top10_pct,
          holding_count,          # 前 N 大实际数量（不足 N 时按实际填）
          prev_top10_pct,         # 上期前 10 占比（首次运行时为 None）
          change_pct,             # 环比变化百分点（首次运行时为 None）
          alert_level,            # "紧急"/"关注"/"正常"（首次运行时为"基线已记录"）
          is_first_check: bool},  # 首次运行标记
         ...]
    """
    # 读取历史快照
    snapshot = _load_history_snapshot() or {}
    is_first_run = not bool(snapshot)

    results: list[dict[str, Any]] = []

    for code, info in fund_holdings.items():
        name = info.get("name", code)
        holdings = info.get("holdings", [])
        if not holdings:
            continue

        # 按 ratio 降序（API 默认已降序，再排一下确保）
        sorted_holdings = sorted(
            holdings,
            key=lambda x: abs(x.get("ratio", 0) or 0),
            reverse=True,
        )
        ratios = [abs(h.get("ratio", 0) or 0) for h in sorted_holdings]

        # 前 N 大占比
        def _top_n(n: int) -> float:
            return round(sum(ratios[:n]), 2)

        top3 = _top_n(3)
        top5 = _top_n(5)
        top10 = _top_n(10)
        holding_count = len(ratios)

        # 历史对比
        prev_entry = snapshot.get(code)
        prev_top10 = prev_entry.get("top10_pct") if prev_entry else None
        change_pct = round(top10 - prev_top10, 2) if prev_top10 is not None else None

        # 预警级别
        alert_level = "正常" if is_first_run else _calc_alert_level(top10, change_pct)  # 首次运行显示"基线已记录"

        results.append(
            {
                "code": code,
                "name": name,
                "top3_pct": top3,
                "top5_pct": top5,
                "top10_pct": top10,
                "holding_count": holding_count,
                "prev_top10_pct": prev_top10,
                "change_pct": change_pct,
                "alert_level": alert_level,
                "is_first_check": is_first_run,
            }
        )

    # 写入快照
    if results:
        _save_history_snapshot(results)

    return results
