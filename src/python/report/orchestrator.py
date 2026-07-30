"""报告编排共享层 — TUI 和 CLI 共用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

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
    """从 config 读取章节可见性开关，返回统一字典。"""
    from src.python.config import is_enable_b_series, is_enable_history, is_enable_llm, is_enable_news

    return {
        "b_series": is_enable_b_series(config),
        "news": is_enable_news(config),
        "history": is_enable_history(config),
        "llm": is_enable_llm(config),
    }


# ── prepare_report_data ──
# ★ config 参数已为必传


def prepare_report_data(
    holdings: list,
    reporter: ProgressReporter,
    config: dict,
) -> dict:
    """获取行情、指数、穿透数据，整理持仓明细字典列表。

    使用内部 ThreadPoolExecutor。
    注意：config 参数传入后必须只读使用，不得 mutate。调用方持有的 dict 引用
    指向相同的配置对象，写入会导致跨模块状态污染（C14 约束）。
    """
    from concurrent.futures import ThreadPoolExecutor

    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.report.market_value import _generate_details, classify_holdings
    from src.python.report.penetration import compute_penetration_top10

    today_str = datetime.now().strftime("%Y-%m-%d")

    reporter.info("正在获取行情数据...")
    details = _generate_details(holdings, today_str)
    total_mv = sum(d.market_value for d in details)
    total_cost = sum(d.cost for d in details)
    total_profit = sum(d.profit for d in details)
    total_today_profit = sum(d.today_profit for d in details)
    categories = classify_holdings(holdings)

    reporter.info("正在获取指数行情...")
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_prep")
    try:
        _a_fut = pool.submit(fetch_indices)
        _us_fut = pool.submit(fetch_us_indices)
        a_indices = _a_fut.result()
        us_indices = _us_fut.result()
    finally:
        pool.shutdown(wait=False)

    reporter.info("正在计算资产穿透 TOP10...")
    pen_result = compute_penetration_top10(holdings, details)
    penetrated_assets = (pen_result or {}).get("top10", [])

    holdings_details = [
        {
            "name": d.name,
            "code": d.code,
            "market_value": d.market_value,
            "cost": d.cost,
            "profit": d.profit,
            "profit_rate": d.profit_rate,
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
        # 组合风险指标（年化波动率/最大回撤/夏普比率等，需 history_data 计算后填充）
        "risk_metrics": {},
    }


# ── generate_report ──


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
    """生成投资分析报告。

    basic: 仅 Excel（无数据准备/快照/历史）
    both:  HTML+Excel（不含 LLM）
    full:  HTML+Excel+LLM
    """
    result = ReportResult()

    # 实验性功能状态日志（红色高亮）
    from src.python.config.features import log_experimental_features

    log_experimental_features()

    if report_type == "basic":
        # basic 路径：仅生成 Excel，不调 prepare_report_data / capture_snapshot / fetch_history_data
        from src.python.core.perf import PerfCollector
        from src.python.core.registry import get_report_section_order
        from src.python.report._report_generation import _collect_health_checks, _spawn_health_checks
        from src.python.report.excel_generator import generate_excel_report

        perf = PerfCollector(report_type="basic", holdings=holdings)
        sec_order = get_report_section_order(config)
        output = output_dir or config.get("output_dir", "reports")

        # 后台启动健康检查（与 Excel 生成并行）
        _health_fut = _spawn_health_checks(holdings)

        try:
            perf.start("Excel 生成")
            generate_excel_report(
                holdings,
                include_news=False,
                output_dir=output,
                section_order=sec_order,
                progress=reporter,
            )
            perf.stop()
            result.excel_ok = True
            result.holdings_ok = True
            result.report_generated = True
        except Exception:
            perf.add_error("Excel 报告生成失败")
            reporter.add_error("Excel 报告生成失败（详情请查看日志文件 logs/app.log）")
            logger.exception("生成 Excel 报告失败")
            result.errors.append("Excel 报告生成失败")

        perf.save()
        _collect_health_checks(_health_fut, "basic", holdings)
        return result

    if report_type == "both":
        from src.python.report._report_generation import _generate_report_both

        return _generate_report_both(
            holdings,
            config,
            reporter,
            history_mode=history_mode,
            output_dir=output_dir,
        )

    if report_type == "full":
        from src.python.report._report_generation import _generate_report_full

        return _generate_report_full(
            holdings,
            config,
            reporter,
            history_mode=history_mode,
            force_llm=force_llm,
            output_dir=output_dir,
        )

    result.report_generated = True
    reporter.info("generate_report: 骨架模式—未知 report_type")
    return result


# bridge imports — 保持向后兼容
from src.python.report._snapshot import capture_snapshot, fetch_history_data  # noqa: E402, F401
from src.python.report._llm_news import (  # noqa: E402, F401
    _fetch_llm_and_news,
    _report_llm_module_results,
    _submit_llm_future,
    _submit_news_future,
    _collect_llm_future_result,
    _collect_news_future_result,
)
from src.python.report._report_generation import (  # noqa: E402, F401
    _compute_details,
    _generate_report_both,
    _generate_report_full,
    _prepare_full_risk_metrics,
    _generate_full_html_report,
    _generate_full_excel_report,
    _spawn_health_checks,
    _collect_health_checks,
    _validate_prep_completeness,
    _validate_pipeline_snapshot,
)
