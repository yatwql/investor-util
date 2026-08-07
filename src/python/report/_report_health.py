"""报告管线后台健康检查子模块。

承载数据源健康检查的后台并行启动与结果收集持久化（与主管线并行，不阻塞报告生成）。

由 `_report_generation.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("invest")


# ── 健康检查（后台并行）──


def _spawn_health_checks() -> object | None:
    """在后台启动数据源健康检查，返回 Future 或 None。

    检查结果与主管线并行执行，不阻塞报告生成。
    在管线末尾调用 _collect_health_checks() 收集结果。
    """
    try:
        from concurrent.futures import ThreadPoolExecutor

        from src.python.core.check_sources import run_health_checks

        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orch_health")
        fut = pool.submit(run_health_checks)
        # 不让 pool 在函数退出时 shutdown — 让 Future 独立运行
        return fut
    except Exception:
        logger.info("[health] 启动健康检查失败（非关键，不影响报告生成）", exc_info=True)
        return None


def _collect_health_checks(
    health_future: object | None,
    report_type: str,
    holdings: list,
) -> None:
    """收集数据源健康检查结果并持久化。

    必须在管线末尾调用（所有主要阶段完成后）。
    """
    if health_future is None:
        return
    try:
        results = health_future.result(timeout=30)
        if not results:
            return
        from src.python.core.perf import save_health_check_snapshot

        save_health_check_snapshot(results, report_type=report_type, holdings_count=len(holdings))

        # 将结果注入 DegradationTracker，供 data_source_matrix 使用
        from src.python.report.data_status import get_tracker

        tracker = get_tracker()
        for r in results:
            source_key = f"health_{r['name']}"
            tracker.record(
                source_key=source_key,
                tier="T4",
                success=r["ok"],
                failure_type="unreachable" if not r["ok"] else "",
            )
    except Exception:
        logger.info("[health] 收集健康检查结果失败（非关键）", exc_info=True)
