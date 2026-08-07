"""报告生成管线 — 单管线/双管线的编排逻辑。

> **遗留重复文件**：本文件不再承载活代码——both/full 双路径生成的
> 编排实现在 `_report_generation.py`（聚合门面），`orchestrator.generate_report`
> 实际经其执行。请勿在本文件实施管线变更（防双份漂移）；清理本文件列为独立重构项。

职责范围：
  - 健康检查（_spawn/_collect）
  - both/full 报告管线（_generate_report_both / _generate_report_full）
  - LLM+新闻并行获取（_fetch_llm_and_news 及其辅助函数）
  - 历史+指标提取（_fetch_history_with_metrics）

数据准备函数（prepare_report_data / capture_snapshot / fetch_history_data等）
由本模块通过 ``orchestrator`` 模块内导入引用，避免循环依赖。
"""

from __future__ import annotations

from typing import Any

from src.python.report.progress import ProgressReporter

logger = __import__("logging").getLogger("invest")


# ── 健康检查（后台） ────────────────────────────────


def _spawn_health_checks(holdings: list) -> object | None:
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


# ── both 报告管线 ──────────────────────────────────


def _generate_report_both(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    fetch_history: bool = False,
    output_dir: str | None = None,
) -> Any:
    """both 报告路径：生成 HTML + Excel，不含 LLM 分析章节。

    流程：_compute_details() → capture_snapshot() → fetch_history_data()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import is_enable_fund_deep_analysis, is_enable_history, is_enable_news
    from src.python.core.perf import PerfCollector
    from src.python.core.registry import get_report_section_order
    from src.python.report.excel_generator import generate_excel_report
    from src.python.report.html_writer import write_html_report

    # ReportResult 定义于 orchestrator；数据准备函数从各自实现模块导入
    from src.python.report._report_generation import _compute_details
    from src.python.report._snapshot import capture_snapshot, fetch_history_data
    from src.python.report.orchestrator import ReportResult

    perf = PerfCollector(report_type="both", holdings=holdings)
    result = ReportResult()
    result.holdings_ok = True

    _health_fut = _spawn_health_checks(holdings)

    _enable_fund_deep_analysis = is_enable_fund_deep_analysis(config)
    _enable_news = is_enable_news(config)
    _enable_history = is_enable_history(config)
    sec_order = get_report_section_order(config)
    output = output_dir or config.get("output_dir", "reports")
    news_top_count = int(config.get("news_top_count", 300))

    # ── 1. 行情获取 ──
    perf.start("行情获取")
    details = _compute_details(holdings, reporter)
    perf.stop()

    # ── 2. 快照对比 ──
    perf.start("快照对比")
    pipeline_data = capture_snapshot(holdings, details, config, reporter)
    perf.stop()
    if pipeline_data is not None:
        assert isinstance(pipeline_data, dict), "capture_snapshot(both) pipeline_data 类型异常"
        _diff = pipeline_data.get("diff")
        if _diff is not None and not isinstance(_diff, dict):
            logger.warning("[checkpoint] pipeline_data.diff 类型异常(both): %s", type(_diff).__name__)

    # ── 3. 历史走势（条件获取） ──
    if _enable_history:
        perf.start("历史走势")
        history_data = fetch_history_data(holdings, config, reporter, fetch=fetch_history)
        perf.stop()
    else:
        history_data = None
        reporter.info("[章节配置] 历史走势已关闭，跳过")

    # ── 4. HTML 报告 ──
    _news_label = "含新闻" if _enable_news else "无新闻"
    reporter.info(f"正在生成 HTML 报告（{_news_label}）...")
    perf.start("HTML 生成")
    try:
        path = write_html_report(
            holdings,
            output_dir=output,
            news_top_count=news_top_count,
            include_news=_enable_news,
            details=details,
            section_order=sec_order,
            history_data=history_data,
            progress=reporter,
            enable_fund_deep_analysis=_enable_fund_deep_analysis,
            enable_news=_enable_news,
            enable_history=_enable_history,
            enable_llm=False,
        )
        reporter.ok(f"HTML 报告已生成: {path}")
        result.html_ok = True
    except Exception:
        reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("HTML 报告写入失败")
        result.errors.append("HTML 报告生成失败")
    perf.stop()

    # ── 5. Excel 报告 ──
    reporter.info("正在生成 Excel 报告...")
    perf.start("Excel 生成")
    try:
        generate_excel_report(
            holdings,
            include_news=_enable_news,
            output_dir=output,
            news_top_count=news_top_count,
            details=details,
            section_order=sec_order,
            pipeline_data=pipeline_data,
            history_data=history_data,
            progress=reporter,
            enable_fund_deep_analysis=_enable_fund_deep_analysis,
            enable_news=_enable_news,
            enable_history=_enable_history,
            enable_llm=False,
        )
        reporter.ok("Excel 报告已生成")
        result.excel_ok = True
    except Exception:
        reporter.add_error("Excel 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("Excel 报告生成失败")
        result.errors.append("Excel 报告生成失败")
    perf.stop()

    result.report_generated = result.html_ok or result.excel_ok
    perf.save()
    _collect_health_checks(_health_fut, "both", holdings)
    return result


# ── LLM 模块结果报告（统一计数） ────────────────────


def _report_llm_module_results(
    results: tuple,
    cached_flags: tuple[bool, bool, bool, bool],
    reporter: ProgressReporter,
) -> None:
    """统一的 LLM 模块结果报告逻辑。"""
    from src.python.llm import FAIL_REASON_DISABLED
    from src.python.llm.prompts import LLM_MODULE_FAILURE
    from src.python.core.registry import get_llm_module_name
    from src.python.report.llm_module_info import get_llm_module_failure_reason

    _MODULE_KEYS = ("global_macro", "expert_review", "health_check", "penetration_deep")

    ok_count = 0
    disabled: list[str] = []
    failed: list[str] = []

    for mk, r in zip(_MODULE_KEYS, results):
        if r is not None:
            ok_count += 1
        elif get_llm_module_failure_reason(LLM_MODULE_FAILURE, mk) == FAIL_REASON_DISABLED:
            disabled.append(get_llm_module_name(mk))
        else:
            failed.append(get_llm_module_name(mk))

    for name in disabled:
        reporter.info(f"{name}：已跳过（菜单 S 可切换）")
    for name in failed:
        reporter.add_error(f"{name}：内容生成失败（已降级使用占位文本）")
        reporter.warn(f"{name}：内容生成失败（已降级使用占位文本）")

    if ok_count > 0 and not failed:
        tag = "缓存" if all(cached_flags) else "LLM"
        reporter.ok(f"{tag} 内容生成完成")
    elif ok_count == 0 and not failed and not disabled:
        reporter.warn("LLM 均未生成（请检查 LLM 配置）")
    elif ok_count == 0 and not failed:
        reporter.info("所有 LLM 内容已跳过，未调用 LLM")


def _process_llm_future(fut, reporter) -> tuple:
    """处理 LLM future 结果，返回 (llm_content, cached, debate_info)。"""
    try:
        _result = fut.result()
        llm_content = _result[:4]
        _cached = _result[4:8]
        _report_llm_module_results(llm_content, _cached, reporter)
        debate_info = _result[8] if len(_result) > 8 else None
        return llm_content, _cached, debate_info
    except Exception:
        reporter.add_error("LLM 内容生成异常（详情请查看日志文件 logs/app.log）")
        reporter.error("LLM 内容生成异常（详情请查看日志）")
        return (None, None, None, None), (False, False, False, False), None


def _process_news_future(fut, reporter) -> tuple:
    """处理新闻 future 结果，返回 (news_data, news_llm_meta, news_ok)。"""
    try:
        news_data, news_llm_meta = fut.result()
        reporter.ok(f"新闻获取完成，共 {len(news_data)} 条")
        return news_data, news_llm_meta, bool(news_data)
    except Exception:
        reporter.add_error("新闻获取异常（详情请查看日志文件 logs/app.log）")
        reporter.warn("新闻获取异常（详情请查看日志）")
        return [], {}, False


# ── LLM + 新闻并行获取 ─────────────────────────────


def _fetch_llm_and_news(
    holdings: list,
    prep_data: dict,
    sector_flow: list | None,
    force_llm: bool,
    pipeline_data: dict | None,
    enable_news: bool,
    enable_llm: bool,
    reporter: ProgressReporter,
    *,
    history_data: dict | None = None,
    comparison_indices: dict[str, str] | None = None,
    metrics: dict | None = None,
) -> tuple[tuple, list, dict, bool, dict | None]:
    """并行获取 LLM 内容 + 新闻数据，统一处理 4 分支。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.python.llm import generate_all_llm
    from src.python.report.news_correlation import build_news_data

    llm_content: tuple = (None, None, None, None)
    news_data: list = []
    news_llm_meta: dict = {}
    news_ok: bool = False
    debate_info: dict | None = None

    if not enable_llm and not enable_news:
        reporter.info("[章节配置] 新闻和 LLM 均未开启，跳过内容生成")
        return llm_content, news_data, news_llm_meta, news_ok, debate_info

    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_llm_news")
    try:
        _news_fut = None
        _llm_fut = None

        if enable_news:
            _news_fut = pool.submit(
                build_news_data,
                holdings,
                prep_data["news_top_count"],
                prep_data["penetrated_assets"],
            )
        else:
            reporter.info("[章节配置] 市场新闻已关闭，跳过新闻获取")

        if enable_llm:
            _llm_fut = pool.submit(
                generate_all_llm,
                prep_data["a_indices"],
                prep_data["us_indices"],
                prep_data["total_mv"],
                prep_data["total_cost"],
                prep_data["total_profit"],
                prep_data["total_today_profit"],
                len(holdings),
                prep_data["categories"],
                penetrated_assets=prep_data["penetrated_assets"],
                holdings_details=prep_data["holdings_details"],
                sector_flow=sector_flow,
                force=force_llm,
                pipeline_data=pipeline_data,
                history_data=history_data,
                comparison_indices=comparison_indices,
                metrics=metrics,
            )
        else:
            reporter.info("[章节配置] LLM 分析章节已关闭，跳过 LLM 内容生成")

        if _llm_fut is not None and _news_fut is not None:
            for fut in as_completed([_news_fut, _llm_fut]):
                if fut is _llm_fut:
                    llm_content, _cached, debate_info = _process_llm_future(fut, reporter)
                else:
                    news_data, news_llm_meta, news_ok = _process_news_future(fut, reporter)
        elif _news_fut is not None:
            news_data, news_llm_meta, news_ok = _process_news_future(_news_fut, reporter)
        elif _llm_fut is not None:
            llm_content, _cached, debate_info = _process_llm_future(_llm_fut, reporter)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return llm_content, news_data, news_llm_meta, news_ok, debate_info


# ── 历史走势 + 全量指标提取 ────────────────────────


def _fetch_history_with_metrics(
    holdings: list,
    config: dict,
    reporter,
    fetch_history: bool,
    prep: dict,
    pipeline_data: dict | None,
) -> tuple:
    """获取历史走势 + 全量量化指标 + 情景分析 + 口径修正。

    Returns:
        (history_data, metrics) — 关闭时均为 None
    """
    from src.python.config import is_enable_history
    from src.python.report._snapshot import fetch_history_data

    if not is_enable_history(config):
        reporter.info("[章节配置] 历史走势已关闭，跳过")
        return None, None

    history_data = fetch_history_data(holdings, config, reporter, fetch=fetch_history)

    if history_data and history_data.get("status") not in ("unavailable",):
        _risk = {
            "annualized_volatility": history_data.get("annualized_volatility", 0),
            "max_drawdown_pct": history_data.get("max_drawdown_pct", 0),
            "total_return_pct": history_data.get("total_return_pct", 0),
            "data_start": history_data.get("data_start", ""),
            "data_end": history_data.get("data_end", ""),
        }
        prep["risk_metrics"] = _risk
        if pipeline_data is not None:
            pipeline_data["risk_metrics"] = _risk
            pipeline_data["portfolio_daily_returns"] = history_data.get("daily_returns_portfolio", [])

    _injected = prep.get("risk_metrics", {})
    if not _injected.get("annualized_volatility") and _injected.get("annualized_volatility") != 0:
        logger.warning("[checkpoint] prep.risk_metrics 缺 annualized_volatility")

    if history_data:
        _daily_returns = history_data.get("daily_returns_portfolio", [])
    else:
        _daily_returns = None

    if not _daily_returns:
        return history_data, None

    from src.python.analysis.alignment_correction import compute_alignment_factors
    from src.python.analysis.metrics import compute_all_metrics

    _holdings_details = prep.get("holdings_details", [])
    _total_mv = prep.get("total_mv", 0)

    _portfolio_weights = [
        h["market_value"] / _total_mv for h in _holdings_details if _total_mv > 0 and h.get("market_value", 0) > 0
    ] or None

    _metrics = compute_all_metrics(
        portfolio_daily_returns=_daily_returns,
        portfolio_weights=_portfolio_weights,
        benchmark_daily_returns=None,
        holdings_details=_holdings_details,
        rf_annual=0.02,
    )
    _mdd_pct = history_data.get("max_drawdown_pct", 0)
    _metrics["annualized_volatility"] = history_data.get("annualized_volatility")
    _metrics["max_drawdown"] = -(_mdd_pct / 100) if _mdd_pct else None

    _alignment = compute_alignment_factors(
        holdings_details=_holdings_details,
        total_mv=_total_mv,
        portfolio_daily_returns=_daily_returns,
    )
    if _alignment.get("has_any_data"):
        _metrics["alignment_summary"] = _alignment.get("summary_text", "")

    _beta_analysis = _metrics.get("beta_analysis")
    _beta_val = _metrics.get("portfolio_beta")
    if isinstance(_beta_analysis, dict) and _beta_val is not None:
        from src.python.analysis.scenario import scenario_analysis

        _scenario = scenario_analysis(
            portfolio_value=_total_mv,
            beta=_beta_val,
            beta_ci_lower=_beta_analysis.get("ci_lower"),
            beta_ci_upper=_beta_analysis.get("ci_upper"),
            beta_se=_beta_analysis.get("std_error"),
        )
        if _scenario.get("has_data") and _scenario.get("scenarios"):
            _metrics["scenario_analysis"] = _scenario

    return history_data, _metrics


# ── full 报告管线（HTML + Excel + LLM） ─────────────


def _generate_report_full(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    fetch_history: bool = False,
    force_llm: bool = False,
    output_dir: str | None = None,
) -> Any:
    """full 报告路径：生成 HTML + Excel + LLM 分析章节。

    流程：prepare_report_data() → capture_snapshot() → fetch_history_data()
          → get_sector_fund_flow() → _fetch_llm_and_news()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import is_enable_fund_deep_analysis, is_enable_llm, is_enable_news
    from src.python.fetcher.akshare import get_sector_fund_flow
    from src.python.core.perf import PerfCollector
    from src.python.core.registry import get_report_section_order
    from src.python.report.excel_generator import generate_excel_report
    from src.python.report.html_writer import write_html_report

    # ReportResult/prepare_report_data 定义于 orchestrator；快照函数从 _snapshot 导入
    from src.python.report._snapshot import capture_snapshot
    from src.python.report.orchestrator import ReportResult, prepare_report_data

    perf = PerfCollector(report_type="full", holdings=holdings)
    result = ReportResult()
    result.holdings_ok = True

    _health_fut = _spawn_health_checks(holdings)

    _enable_fund_deep_analysis = is_enable_fund_deep_analysis(config)
    _enable_news = is_enable_news(config)
    _enable_llm = is_enable_llm(config)
    sec_order = get_report_section_order(config)

    # ── 1. 完整数据准备（含指数/穿透/分类） ──
    perf.start("数据准备")
    prep = prepare_report_data(holdings, reporter, config)
    assert isinstance(prep, dict), "prepare_report_data 返回类型异常"
    for _ck in (
        "total_mv",
        "total_cost",
        "total_profit",
        "total_today_profit",
        "categories",
        "a_indices",
        "holdings_details",
        "today_str",
        "output_dir",
        "news_top_count",
        "risk_metrics",
    ):
        if _ck not in prep:
            logger.warning("[checkpoint] prep 缺失必选键: %s", _ck)
        elif not isinstance(prep.get(_ck), (int, float, dict, list, str, type(None))):
            logger.warning("[checkpoint] prep.%s 类型异常: %s", _ck, type(prep.get(_ck)).__name__)

    perf.stop()

    # ── 2. 快照对比 ──
    perf.start("快照对比")
    pipeline_data = capture_snapshot(holdings, prep["details"], config, reporter)
    if pipeline_data is not None:
        assert isinstance(pipeline_data, dict), "capture_snapshot pipeline_data 类型异常"
        _diff = pipeline_data.get("diff")
        if _diff is not None and not isinstance(_diff, dict):
            logger.warning("[checkpoint] pipeline_data.diff 类型异常: %s", type(_diff).__name__)

    perf.stop()

    # ── 3. 历史走势 + 全量量化指标 + 情景分析 + 口径修正 ──
    perf.start("历史走势")
    history_data, _metrics = _fetch_history_with_metrics(
        holdings,
        config,
        reporter,
        fetch_history,
        prep,
        pipeline_data,
    )
    perf.stop()

    # ── 4. 行业资金流向 ──
    reporter.info("正在获取行业资金流向...")
    perf.start("行业资金流向")
    try:
        sector_flow = get_sector_fund_flow()
        if sector_flow:
            reporter.ok("行业资金流向获取完成")
    except Exception:
        sector_flow = None
        reporter.warn("行业资金流向获取失败，将继续生成报告")
    perf.stop()

    # ── 5. 并行获取 LLM + 新闻（4 分支统一处理） ──
    _comparison_indices = config.get("comparison_indices", None)
    perf.start("LLM+新闻")
    llm_content, news_data, news_llm_meta, news_ok, debate_info = _fetch_llm_and_news(
        holdings,
        prep,
        sector_flow,
        force_llm,
        pipeline_data,
        _enable_news,
        _enable_llm,
        reporter,
        history_data=history_data,
        comparison_indices=_comparison_indices,
        metrics=_metrics,
    )

    if _enable_llm:
        from src.python.llm.fallback import build_fallback_llm_content

        llm_content = build_fallback_llm_content(llm_content)
        if all(c is not None for c in llm_content[:4]):
            result.llm_ok = True
    perf.stop()

    # ── 6. HTML 报告 ──
    _report_label = "含新闻 + LLM" if news_ok else "仅 LLM"
    reporter.info(f"正在生成 HTML 报告（{_report_label}分析章节）...")
    perf.start("HTML 生成")
    try:
        path = write_html_report(
            holdings,
            output_dir=output_dir or prep["output_dir"],
            news_top_count=prep["news_top_count"],
            include_news=news_ok,
            llm_content=llm_content,
            details=prep["details"],
            news_data=news_data,
            news_llm_meta=news_llm_meta,
            section_order=sec_order,
            history_data=history_data,
            progress=reporter,
            a_indices=prep["a_indices"],
            us_indices=prep["us_indices"],
            enable_fund_deep_analysis=_enable_fund_deep_analysis,
            enable_news=_enable_news,
            enable_history=_enable_history,
            enable_llm=_enable_llm,
            debate_info=debate_info,
        )
        reporter.ok(f"HTML 报告已生成: {path}")
        result.html_ok = True
    except Exception:
        reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("HTML 报告写入失败")
        result.errors.append("HTML 报告生成失败")
    perf.stop()

    # ── 7. Excel 报告 ──
    reporter.info("正在生成 Excel 报告...")
    perf.start("Excel 生成")
    try:
        generate_excel_report(
            holdings,
            include_news=news_ok,
            output_dir=output_dir or prep["output_dir"],
            news_top_count=prep["news_top_count"],
            include_llm=_enable_llm,
            llm_content=llm_content,
            details=prep["details"],
            news_data=news_data,
            news_llm_meta=news_llm_meta,
            section_order=sec_order,
            pipeline_data=pipeline_data,
            history_data=history_data,
            progress=reporter,
            a_indices=prep["a_indices"],
            us_indices=prep["us_indices"],
            enable_fund_deep_analysis=_enable_fund_deep_analysis,
            enable_news=_enable_news,
            enable_history=_enable_history,
            enable_llm=_enable_llm,
            debate_info=debate_info,
        )
        reporter.ok("Excel 报告已生成")
        result.excel_ok = True
    except Exception:
        reporter.add_error("Excel 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("Excel 报告生成失败")
        result.errors.append("Excel 报告生成失败")
    perf.stop()

    result.report_generated = result.html_ok or result.excel_ok
    result.history_ok = history_data is not None
    perf.save()
    _collect_health_checks(_health_fut, "full", holdings)
    return result
