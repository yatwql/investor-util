"""实验功能使用统计 — 为「转正 / 撤销」决策提供客观数据（语义名 experiment_stats）。

每次报告生成时，若启用了实验性功能（``features.log_experimental_features`` 的
唯一调用时机），按开关记录累计启用次数与最近启用日期。长期无人启用的实验功能
是撤销候选；高频启用的则是转正候选——本模块让这两类决策有据可依，而非靠代码
行数与账本行数推测。

设计约束（对齐 core 层账本模块 decision_ledger / signal_ledger 的纪律）：
    分层约束  — 本模块属 core 层，只依赖 stdlib + 同层 core（atomic_write / constants），
                禁止 import report/llm/analysis/config 下的任何模块——统计的**写入**
                触发点位于 config.features（report 入口侧），读取侧为 core.doctor，
                本模块自身保持纯 core 依赖。
    持久化    — data/state/experiment_stats.json，整体读改写 + 原子写入
                （委托 core/atomic_write.write_json_atomic）
    无单例    — 无状态函数集，读档 → 合并 → 原子写回；不设全局注册器，避免跨测试状态泄漏
    尽力而为  — 读写失败只记 WARNING，绝不影响报告主链路（调用方 config.features
                已包一层兜底，本模块内部仍保持「失败不外抛」的自 containment）
    时间口径  — 最近启用日期取报告生成的本地日历日（YYYY-MM-DD），跨日多次
                生成只刷新日期、累计次数照常 +1

数据流：
    record_experiment_usage()  按开关累计次数并刷新最近启用日期（report 入口调用）
    load_experiment_usage()    读全量统计（doctor 只读视图调用；损坏时容错返回空）
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.python.core.atomic_write import write_json_atomic
from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

__all__ = [
    "EXPERIMENT_STATS_FILE",
    "load_experiment_usage",
    "record_experiment_usage",
]

# ── 持久化路径 ──────────────────────────────────────────
# module-level 变量，测试时可通过 monkeypatch.setattr 重定向（测试隔离模式）。
# data/state 而非 data/cache：避开 cache.cleanup_expired() 清扫（理由同
# src/python/core/decision_ledger._DECISION_LEDGER_FILE）。
EXPERIMENT_STATS_FILE = os.path.join(PROJECT_ROOT, "data", "state", "experiment_stats.json")

#: 单条统计记录的形状：{"enabled_count": int >= 0, "last_enabled_date": "YYYY-MM-DD"}


def _today_str() -> str:
    """返回本地日历日（YYYY-MM-DD），作为「最近启用日期」的时间口径。"""
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d")


def load_experiment_usage(path: str | None = None) -> dict[str, dict[str, Any]]:
    """读取实验功能使用统计（损坏/缺失时容错返回空 dict，绝不外抛）。

    Args:
        path: 可选自定义路径（测试注入）；缺省用 ``EXPERIMENT_STATS_FILE``。

    Returns:
        ``{开关名: {"enabled_count": int, "last_enabled_date": str}}``；
        文件缺失/JSON 损坏/形状异常时返回 ``{}``。
    """
    import json

    target = path or EXPERIMENT_STATS_FILE
    if not os.path.exists(target):
        return {}
    try:
        with open(target, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[experiment_stats] 读取统计文件失败，按空统计处理: %s", e)
        return {}
    if not isinstance(raw, dict):
        logger.warning("[experiment_stats] 统计文件形状异常（应为 JSON object），按空统计处理")
        return {}

    cleaned: dict[str, dict[str, Any]] = {}
    for flag, entry in raw.items():
        if not isinstance(flag, str) or not isinstance(entry, dict):
            continue
        count = entry.get("enabled_count")
        date = entry.get("last_enabled_date")
        if isinstance(count, int) and count >= 0 and isinstance(date, str):
            cleaned[flag] = {"enabled_count": count, "last_enabled_date": date}
    return cleaned


def record_experiment_usage(enabled_flags: list[str], path: str | None = None) -> None:
    """按开关累计启用次数并刷新最近启用日期（幂等调用方语义：一次报告 = 一次记录）。

    读档 → 逐开关 +1 / 刷新日期 → 原子写回。失败只记 WARNING，绝不外抛——
    统计是观测设施，不是报告生成的前置条件。无启用项时不写盘（无统计无需落空文件）。

    Args:
        enabled_flags: 本次报告启用的实验功能开关名列表（可含重复，内部去重）
        path: 可选自定义路径（测试注入）；缺省用 ``EXPERIMENT_STATS_FILE``
    """
    if not enabled_flags:
        return
    target = path or EXPERIMENT_STATS_FILE
    today = _today_str()
    stats = load_experiment_usage(target)
    for flag in sorted(set(enabled_flags)):
        entry = stats.get(flag) or {}
        count = entry.get("enabled_count", 0)
        stats[flag] = {
            "enabled_count": (count if isinstance(count, int) and count >= 0 else 0) + 1,
            "last_enabled_date": today,
        }

    if not write_json_atomic(
        target,
        stats,
        prefix=".experiment_stats_",
        log_tag="experiment_stats",
        noun="实验功能使用统计",
    ):
        logger.warning("[experiment_stats] 使用统计落盘失败（本次统计不生效，不影响报告）")
