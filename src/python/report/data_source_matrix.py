"""数据源可用性矩阵 — 统一聚合所有数据源状态供 Excel/HTML 渲染。

从 DegradationTracker 采集各数据源最新状态，按类别聚合为
统一的矩阵结构，消除各模块独立状态碎片。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.report.data_status import get_tracker

logger = logging.getLogger("invest")

# ── 数据源类别定义 ──────────────────────────────────────
# 每条记录包含：类别键、中文名称、source_key 前缀列表

_SOURCE_CATEGORIES: list[dict[str, Any]] = [
    {"key": "price", "name": "行情数据", "prefixes": ["price_"]},
    {"key": "fund_rank", "name": "基金排名", "prefixes": ["fund_rank_", "perf_rank"]},
    {"key": "fund_hold", "name": "基金持仓", "prefixes": ["fund_hold_"]},
    {"key": "industry", "name": "行业分类", "prefixes": ["industry_", "penetration_industry"]},
    {"key": "index", "name": "指数数据", "prefixes": ["index_a", "index_us", "index_history_"]},
    {"key": "profit_forecast", "name": "盈利预测", "prefixes": ["penetration_profit_forecast"]},
    {"key": "dividend", "name": "分红数据", "prefixes": ["penetration_dividend"]},
    {"key": "fund_flow", "name": "资金流向", "prefixes": ["ff_"]},
]


def _match_category(source_key: str) -> str | None:
    """返回 source_key 所属的类别 key，None 表示无匹配。"""
    for cat in _SOURCE_CATEGORIES:
        for prefix in cat["prefixes"]:
            if source_key == prefix or source_key.startswith(prefix):
                return cat["key"]
    return None


def build_data_source_matrix() -> list[dict[str, Any]]:
    """构建数据源可用性矩阵。

    从 DegradationTracker 事件日志聚合每条 source_key 的最新状态，
    按类别（行情/基金/行业等）归类后计算整体健康度。

    Returns:
        矩阵行列表，每行含：
            key / name / status / detail / total / ok / degraded / failed
        status 取值 "ok" / "degraded" / "failed"
    """
    events = get_tracker().get_log()
    if not events:
        return []

    # 1) 按 source_key 取最新事件
    latest: dict[str, dict[str, Any]] = {}
    for ev in events:
        key = ev["source_key"]
        ts = ev["timestamp"]
        if key not in latest or ts > latest[key]["timestamp"]:
            latest[key] = ev

    # 2) 初始化类别容器
    cat_data: dict[str, dict[str, Any]] = {}
    for cat in _SOURCE_CATEGORIES:
        cat_data[cat["key"]] = {
            "key": cat["key"],
            "name": cat["name"],
            "total": 0,
            "ok": 0,
            "degraded": 0,
            "failed": 0,
            "sample_failures": [],
        }

    unmatched: list[str] = []

    # 3) 归入类别
    for src_key, ev in latest.items():
        cat_key = _match_category(src_key)
        if cat_key is None:
            unmatched.append(src_key)
            continue
        cd = cat_data[cat_key]
        cd["total"] += 1
        if ev["success"]:
            cd["ok"] += 1
        elif ev["degraded"]:
            cd["degraded"] += 1
        else:
            cd["failed"] += 1
            if len(cd["sample_failures"]) < 3:
                cd["sample_failures"].append(
                    f"{src_key}: {ev.get('failure_type', 'unknown')}"
                )

    # 4) 计算综合状态并生成输出行
    matrix: list[dict[str, Any]] = []
    for cat in _SOURCE_CATEGORIES:
        cd = cat_data[cat["key"]]
        if cd["total"] == 0:
            continue
        if cd["failed"] == 0 and cd["degraded"] == 0:
            status = "ok"
        elif cd["failed"] > 0 and cd["ok"] == 0:
            status = "failed"
        else:
            status = "degraded"

        detail_parts: list[str] = []
        if cd["ok"] > 0:
            detail_parts.append(f"{cd['ok']} 正常")
        if cd["degraded"] > 0:
            detail_parts.append(f"{cd['degraded']} 降级")
        if cd["failed"] > 0:
            detail_parts.append(f"{cd['failed']} 失败")

        row: dict[str, Any] = {
            "key": cd["key"],
            "name": cd["name"],
            "status": status,
            "detail": "，".join(detail_parts) if detail_parts else "无数据",
            "total": cd["total"],
            "ok": cd["ok"],
            "degraded": cd["degraded"],
            "failed": cd["failed"],
            "sample_failures": cd["sample_failures"],
        }
        matrix.append(row)

    # 5) 追加未归类项（如有）
    if unmatched:
        matrix.append({
            "key": "_unmatched",
            "name": "其他数据源",
            "status": "ok",
            "detail": f"{len(unmatched)} 个未归类源（均正常）",
            "total": len(unmatched),
            "ok": len(unmatched),
            "degraded": 0,
            "failed": 0,
            "sample_failures": [],
        })

    return matrix
