"""快照与历史数据 — 持仓快照创建/环比差异计算/组合历史走势。

提取自 ``report/orchestrator.py``，管理 F1 快照和 F2 历史走势两个工序。
"""

from __future__ import annotations

import logging

from src.python.report.progress import ProgressReporter

logger = __import__("logging").getLogger("invest")


def capture_snapshot(
    holdings: list,
    details: list,
    config: dict | None,
    reporter: ProgressReporter,
    **extra,
) -> dict | None:
    """F1 持仓快照创建 + 差异计算 + 保存 + 清理。

    Args:
        holdings: 持仓列表
        details: 行情明细
        config: 配置字典
        reporter: 进度报告接口
        extra: 额外扩展字段（如 risk_metrics），透传到 pipeline_data

    Returns:
        pipeline_data 字典（含 diff），首次运行或异常时返回 None。
    """
    from src.python.fetcher.history_diff import HistoryDiff
    from src.python.report.data_status import get_tracker as _get_degradation_tracker
    from src.python.report.history_snapshot import load_latest, save
    from src.python.schemas.history import (
        AccountSnapshot,
        SnapshotData,
        SnapshotHolding,
    )

    pipeline_data: dict | None = None
    try:
        _snapshot_holdings = [
            SnapshotHolding(
                code=d.code,
                name=getattr(d, "name", ""),
                shares=0.0,
                cost_price=0.0,
                market_value=d.market_value,
                total_pnl=d.profit,
                cost_total=d.cost,
            )
            for d in details
        ]
        for h in _snapshot_holdings:
            _orig = next((x for x in holdings if x.code == h.code), None)
            if _orig:
                object.__setattr__(h, "shares", _orig.shares)
                object.__setattr__(h, "cost_price", _orig.cost_price)
        from datetime import datetime

        _snapshot = SnapshotData(
            accounts=(AccountSnapshot(account_name="全部", holdings=tuple(_snapshot_holdings)),),
            total_value=sum(d.market_value for d in details),
            total_cost=sum(d.cost for d in details),
            total_pnl=sum(d.profit for d in details),
            timestamp=datetime.now().strftime("%Y%m%dT%H%M%S"),
        )
        _old = load_latest()
        _diff = HistoryDiff.compute(_snapshot, _old)
        save(_snapshot)
        from src.python.report.history_snapshot import prune as _prune_snapshots

        _history_cfg = (config or {}).get("history", {})
        _prune_snapshots(
            retention_days=_history_cfg.get("snapshot_retention_days", 60),
            max_count=_history_cfg.get("snapshot_max_count", 365),
        )
        if not _diff.is_first_check:
            pipeline_data = {
                "diff": {
                    "is_first_check": False,
                    "total_value_diff": _diff.total_value_diff,
                    "total_value_diff_pct": _diff.total_value_diff_pct,
                    "total_pnl_diff": _diff.total_pnl_diff,
                    "days_since_last_report": _diff.days_since_last_report,
                    "added": [
                        {
                            "name": a.name,
                            "code": a.code,
                            "action": a.action,
                            "shares_diff": a.shares_diff,
                            "value_diff": a.value_diff,
                        }
                        for a in _diff.added
                    ],
                    "removed": [
                        {
                            "name": r.name,
                            "code": r.code,
                            "action": r.action,
                            "shares_diff": r.shares_diff,
                            "value_diff": r.value_diff,
                        }
                        for r in _diff.removed
                    ],
                    "increased": [
                        {
                            "name": i.name,
                            "code": i.code,
                            "action": i.action,
                            "shares_diff": i.shares_diff,
                            "value_diff": i.value_diff,
                        }
                        for i in _diff.increased
                    ],
                    "decreased": [
                        {
                            "name": d.name,
                            "code": d.code,
                            "action": d.action,
                            "shares_diff": d.shares_diff,
                            "value_diff": d.value_diff,
                        }
                        for d in _diff.decreased
                    ],
                },
                "data_degradation": _get_degradation_tracker().get_log(),
            }
            # 透传额外扩展字段（risk_metrics / portfolio_daily_returns）
            if extra:
                pipeline_data.update(extra)
        reporter.ok("环比对比数据准备完成")
    except Exception:
        logger.info("[F1] 环比数据准备跳过（首次运行或异常）", exc_info=True)
    return pipeline_data


def fetch_history_data(
    holdings: list,
    config: dict | None,
    reporter: ProgressReporter,
    mode: str = "auto",
) -> dict | None:
    """获取组合历史走势数据（as-if 模拟），纯业务逻辑，不含用户交互。

    Args:
        holdings: 持仓列表
        config: 配置字典（含 history 子段）
        reporter: 进度报告接口
        mode: 模式，"auto" 执行获取，"off"/其他值直接返回 None

    Returns:
        history_data 字典，获取失败或不可用时返回 None。
    """
    if mode not in ("auto",):
        return None

    reporter.info("正在获取组合历史走势数据（as-if 模拟）...")
    from src.python.report.portfolio_history import PortfolioHistoryCalculator

    _history_cfg = (config or {}).get("history", {})

    try:
        _coverage = _history_cfg.get("coverage_threshold", 0.8)
        _benchmark_indices = _history_cfg.get("benchmark_indices", {})
        _calc = PortfolioHistoryCalculator(
            coverage_threshold=_coverage,
            benchmark_indices=_benchmark_indices,
        )
        _holdings_tuples = [(h.code, h.name, h.shares) for h in holdings]
        history_data = _calc.get_combined_timeseries(_holdings_tuples)
        if history_data and history_data.get("status") != "unavailable":
            reporter.ok("组合历史走势数据获取完成")
        else:
            reporter.warn("组合历史走势数据获取失败（部分持仓可能不支持历史数据）")
        return history_data
    except Exception:
        logger.info("[F2] 历史走势数据获取跳过", exc_info=True)
        return None
