"""报告编排共享层 — TUI 和 CLI 共用。

P1 逐步从 handlers_report.py 提取业务逻辑至此模块。

★ S1 临时依赖（S5/S6 消除）：
  - handlers_report._get_pool()   ← S6 改为内部 ThreadPoolExecutor
  - tui_menu.get_config_cache()   ← S7 改为 config 参数接收
  - tui_handlers.check_network_available() ← S5 移除（orchestrator 不调 TUI 函数）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.python.report.progress import ProgressReporter

logger = __import__("logging").getLogger("invest")


# ── 数据结构 ───────────────────────────────────────────────


@dataclass
class ReportResult:
    """报告生成结果。"""

    holdings_ok: bool = False
    excel_ok: bool = False
    html_ok: bool = False
    llm_ok: bool = True
    news_ok: bool = True
    history_ok: bool = True
    report_generated: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if not self.report_generated:
            return 2
        if self.errors:
            return 1
        return 0


def _read_section_flags(config: dict) -> dict:
    """从 config 读取板块可见性开关，返回统一字典。"""
    from src.python.config import is_enable_b_series, is_enable_news, is_enable_history, is_enable_llm
    return {
        "b_series": is_enable_b_series(config),
        "news": is_enable_news(config),
        "history": is_enable_history(config),
        "llm": is_enable_llm(config),
    }


# ── S1 移入：_prepare_report_data ──
# 原 handlers_report._prepare_report_data()
# ★ 临时依赖标注：S5 移除 check_network_available，S6 移除 _get_pool，S7 移除 get_config_cache


def prepare_report_data(holdings: list, reporter: ProgressReporter) -> dict:
    """获取行情、指数、穿透数据，整理持仓明细字典列表。"""
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.report.market_value import _generate_details, classify_holdings
    from src.python.report.penetration import compute_penetration_top10

    # ★ 临时依赖：S7 改从 config 参数接收
    from src.python.tui_menu import get_config_cache
    # ★ 临时依赖：S5 移除（TUI 专属）
    from src.python.tui_handlers import check_network_available  # noqa: F811
    # ★ 临时依赖：S6 改为内部池
    from src.python.handlers_report import _get_pool  # noqa: F811

    config = get_config_cache() or {}
    today_str = datetime.now().strftime("%Y-%m-%d")

    reporter.info("正在获取行情数据...")
    details = _generate_details(holdings, today_str)
    check_network_available(details)
    total_mv = sum(d.market_value for d in details)
    total_cost = sum(d.cost for d in details)
    total_profit = sum(d.profit for d in details)
    total_today_profit = sum(d.today_profit for d in details)
    categories = classify_holdings(holdings)

    reporter.info("正在获取指数行情...")
    _idx_ex = _get_pool()
    _a_fut = _idx_ex.submit(fetch_indices)
    _us_fut = _idx_ex.submit(fetch_us_indices)
    a_indices = _a_fut.result()
    us_indices = _us_fut.result()

    reporter.info("正在计算资产穿透 TOP10...")
    pen_result = compute_penetration_top10(holdings, details)
    penetrated_assets = (pen_result or {}).get("top10", [])

    holdings_details = [
        {
            "name": d.name, "code": d.code,
            "market_value": d.market_value, "cost": d.cost,
            "profit": d.profit, "profit_rate": d.profit_rate,
            "change_pct": (
                (d.price - d.yesterday_close) / d.yesterday_close * 100
                if d.yesterday_close and abs(d.yesterday_close) > 1e-10
                else 0.0
            ),
            "nav_date": d.nav_date,
            "source_api": d.source_api,
        }
        for d in details
    ]

    return {
        "details": details,
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_today_profit": total_today_profit,
        "categories": categories,
        "a_indices": a_indices,
        "us_indices": us_indices,
        "penetrated_assets": penetrated_assets,
        "holdings_details": holdings_details,
        "today_str": today_str,
        "output_dir": config.get("output_dir", "reports"),
        "news_top_count": int(config.get("news_top_count", 100)),
    }


# ── S2 移入：capture_snapshot + compute_early_warnings ──
# 原 handlers_report._capture_snapshot() + _compute_early_warnings()
# ★ 与 TUI 原版差异：capture_snapshot 使用 config 参数替代 get_config_cache()


def capture_snapshot(
    holdings: list, details: list,
    config: dict | None, reporter: ProgressReporter,
) -> dict | None:
    """F1 持仓快照创建 + 差异计算 + 保存 + 清理。

    接受 config 参数而非调用 get_config_cache()（★ 与 TUI 原版的核心差异）。

    Returns:
        f_context 字典（含 diff），首次运行或异常时返回 None。
    """
    from src.python.schemas.history import (
        AccountSnapshot, SnapshotData, SnapshotHolding,
    )
    from src.python.fetcher.history_diff import HistoryDiff
    from src.python.report.history_snapshot import load_latest, save

    f_context: dict | None = None
    try:
        _snapshot_holdings = [
            SnapshotHolding(
                code=d.code, name=getattr(d, "name", ""),
                shares=0.0, cost_price=0.0,
                market_value=d.market_value, total_pnl=d.profit, cost_total=d.cost,
            )
            for d in details
        ]
        for h in _snapshot_holdings:
            _orig = next((x for x in holdings if x.code == h.code), None)
            if _orig:
                object.__setattr__(h, "shares", _orig.shares)
                object.__setattr__(h, "cost_price", _orig.cost_price)
        _snapshot = SnapshotData(
            accounts=(AccountSnapshot(account_name="全部",
                                      holdings=tuple(_snapshot_holdings)),),
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
            f_context = {
                "diff": {
                    "is_first_check": False,
                    "total_value_diff": _diff.total_value_diff,
                    "total_value_diff_pct": _diff.total_value_diff_pct,
                    "total_pnl_diff": _diff.total_pnl_diff,
                    "days_since_last_report": _diff.days_since_last_report,
                    "added": [
                        {"name": a.name, "code": a.code, "action": a.action,
                         "shares_diff": a.shares_diff, "value_diff": a.value_diff}
                        for a in _diff.added
                    ],
                    "removed": [
                        {"name": r.name, "code": r.code, "action": r.action,
                         "shares_diff": r.shares_diff, "value_diff": r.value_diff}
                        for r in _diff.removed
                    ],
                    "increased": [
                        {"name": i.name, "code": i.code, "action": i.action,
                         "shares_diff": i.shares_diff, "value_diff": i.value_diff}
                        for i in _diff.increased
                    ],
                    "decreased": [
                        {"name": d.name, "code": d.code, "action": d.action,
                         "shares_diff": d.shares_diff, "value_diff": d.value_diff}
                        for d in _diff.decreased
                    ],
                },
                "diff_trimmed": _diff.trimmed,
                "days_since_last": _diff.days_since_last_report,
            }
        reporter.ok("环比对比数据准备完成")
    except Exception:
        logger.info("[F1] 环比数据准备跳过（首次运行或异常）", exc_info=True)
    return f_context


def compute_early_warnings(
    holdings: list, penetrated_assets: list, sector_flow: list[dict],
    news_data: list, news_llm_meta: dict, reporter: ProgressReporter,
) -> dict | None:
    """计算智能预警（行业资金流向联动 + 新闻情绪聚合）。"""
    try:
        from src.python.report.early_warning import compute_early_warnings as _compute_ew
        _warnings = _compute_ew(
            holdings,
            penetration_top10=penetrated_assets,
            sector_flow=sector_flow,
            news_data=news_data,
            news_llm_meta=news_llm_meta,
        )
        if _warnings.get("has_warnings"):
            _n_sector = len(_warnings.get("sector_alerts", []))
            _n_sentiment = len(_warnings.get("sentiment_alerts", []))
            reporter.ok(f"智能预警完成: {_n_sector} 条行业预警, {_n_sentiment} 条新闻情绪")
        return _warnings
    except Exception as e:
        logger.warning("智能预警计算失败: %s", e)
        return None


# ── S3 移入：fetch_history_data ──
# 原 handlers_report._fetch_history_data() 业务逻辑
# ★ 与 TUI 原版差异：接受 config 参数替代 get_config_cache()；不接受 "prompt" 模式


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


# ── S1 骨架：generate_report（S4 开始逐步填充）──


def generate_report(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    report_type: str = "basic",
    history_mode: str = "off",
    force_llm: bool = False,
    output_dir: str | None = None,
    warm_cache: bool = False,
) -> ReportResult:
    """生成投资分析报告（骨架，后续迭代逐步填充具体路径）。"""
    # S4 开始填充 basic/both/full 三条路径
    result = ReportResult()
    result.report_generated = True
    reporter.info("generate_report: 骨架模式—报告生成的模块暂未实现（S4 起逐步填充）")
    return result
