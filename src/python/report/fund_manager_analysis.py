"""基金经理变更检测引擎 — 报告第 13 页数据。

职责：
  1. 调用 fetch_fund_manager 获取每只基金的当前经理信息
  2. 从 fund_manager_snapshot 读取历史快照，检测经理变更
  3. 判定变更时段（1月/3月/6月）和预警级别
  4. 首次运行时输出"首检"状态 + 引导文案

关键设计：
  - 快照使用固定键名 fund_manager_snapshot（无指纹后缀），属 refresh 缓存组，菜单 [1] 可清除
  - 持仓指纹变化不会影响快照数据，确保变更检测独立于持仓变化
  - 每次分析后覆写快照，记录 {code: {manager_name, check_date}}
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.fetcher.fund_manager import fetch_fund_manager
from src.python.models import Holding
from src.python.report.fund_performance import is_fund

logger = logging.getLogger("invest")

_SNAPSHOT_KEY = "fund_manager_snapshot"
_SNAPSHOT_TTL = 365 * 86400  # 接近永久（快照手动管理，不由 TTL 驱动）

# ── 快照读写 ────────────────────────────────────────────────────


def _load_snapshot() -> dict[str, Any] | None:
    """读取基金经理快照（固定键 fund_manager_snapshot）。

    Returns:
        {code: {manager_name, check_date, ...}} 或 None（首次运行/损坏）
    """
    return cache_get(_SNAPSHOT_KEY, _SNAPSHOT_TTL)


def _update_snapshot(current: dict[str, Any]) -> None:
    """更新基金经理快照（覆写）。

    快照格式：
        {code: {manager_name: str, check_date: str}, ...}

    注意：此快照使用固定键名，不受持仓指纹影响。
    持仓变化不会导致快照清除，经理变更检测完全独立于持仓变化。
    """
    cache_set(_SNAPSHOT_KEY, current)


# ── 变更检测核心逻辑 ──────────────────────────────────────────


def _calc_alert_level(changed_1m: bool, changed_3m: bool, changed_6m: bool) -> str:
    """根据变更时段计算预警级别。"""
    if changed_1m:
        return "紧急"
    elif changed_3m or changed_6m:
        return "关注"
    return "正常"


def detect_manager_changes(holdings: list[Holding]) -> list[dict[str, Any]]:
    """检测持仓中所有基金的基金经理变更。

    对每只基金：
      1. 获取当前基金经理信息（fetch_fund_manager，优先读缓存）
      2. 从 fund_manager_snapshot 读取上次快照
      3. 比较快照中的 manager_name vs 当前 manager_name
         - 不同 → 判定为变更（根据 start_date 判断变更时段）
         - 相同 → 无变更
      4. 更新快照

    Args:
        holdings: 持仓列表（仅处理基金类型）

    Returns:
        每只基金一条记录：
        [{code, name, current_manager, start_date, tenure_days,
          changed_1m: bool, changed_3m: bool, changed_6m: bool,
          alert_level: str, is_first_check: bool}]
        仅含基金（非股票/现金），无基金时返回空列表。
    """
    # 筛选基金持仓
    fund_holdings = [h for h in holdings if is_fund(h)]
    if not fund_holdings:
        return []

    # 读取历史快照
    snapshot = _load_snapshot() or {}
    is_first_run = not bool(snapshot)

    results: list[dict[str, Any]] = []
    new_snapshot: dict[str, Any] = {}

    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    for h in fund_holdings:
        manager_info = fetch_fund_manager(h.code)

        current_manager = ""
        start_date = ""
        tenure_days = 0

        if manager_info:
            current_manager = manager_info.get("manager_name", "")
            start_date = manager_info.get("start_date", "")
            tenure_days = manager_info.get("tenure_days", 0)

        # ── 变更检测 ──
        prev_entry = snapshot.get(h.code)
        changed_1m = False
        changed_3m = False
        changed_6m = False

        if prev_entry and current_manager:
            prev_manager = prev_entry.get("manager_name", "")
            if prev_manager and prev_manager != current_manager:
                # 经理变更 → 根据 start_date 判定变更时段
                if start_date:
                    try:
                        change_date = datetime.strptime(start_date, "%Y-%m-%d")
                        days_since = (today - change_date).days
                        changed_1m = days_since <= 30
                        changed_3m = days_since <= 90
                        changed_6m = days_since <= 180
                    except (ValueError, TypeError):
                        # 日期无法解析，保守处理
                        changed_1m = True
                        changed_3m = True
                        changed_6m = True
                else:
                    # 无 start_date 但经理名不同 → 标记为变更
                    changed_3m = True
                    changed_6m = True
        elif not prev_entry and current_manager:
            # 首次运行或新基金 → 无历史对比
            # 根据 start_date 判断是否为近期变更
            if start_date:
                try:
                    start = datetime.strptime(start_date, "%Y-%m-%d")
                    days_since = (today - start).days
                    changed_1m = days_since <= 30
                    changed_3m = days_since <= 90
                    changed_6m = days_since <= 180
                except (ValueError, TypeError):
                    pass

        alert_level = _calc_alert_level(changed_1m, changed_3m, changed_6m)

        # 首次运行特殊标注
        if is_first_run:
            alert_level = "首检"

        results.append(
            {
                "code": h.code,
                "name": h.name,
                "current_manager": current_manager or "--",
                "start_date": start_date or "--",
                "tenure_days": tenure_days,
                "changed_1m": changed_1m,
                "changed_3m": changed_3m,
                "changed_6m": changed_6m,
                "alert_level": alert_level,
                "is_first_check": is_first_run,
            }
        )

        # ── 更新快照（只要有经理数据就更新）──
        if current_manager:
            new_snapshot[h.code] = {
                "manager_name": current_manager,
                "check_date": today_str,
            }

    # 写入快照
    if new_snapshot:
        _update_snapshot(new_snapshot)

    return results


def build_first_check_summary(results: list[dict]) -> str:
    """生成首次运行引导文案。

    Args:
        results: detect_manager_changes 的返回结果

    Returns:
        引导文案字符串（不含换行）
    """
    total = len(results)
    managed = sum(1 for r in results if r.get("current_manager") and r["current_manager"] != "--")
    return f"此为首次运行，基金经理变更自下次报告起跟踪。当前监控 {total} 只基金，其中 {managed} 只由当前经理管理。"
