"""报告生成实现 — both/full 两种路径的 HTML+Excel 生成逻辑。

包含报告生成管线各工序实现。
"""

from __future__ import annotations

import logging

from src.python.report.progress import ProgressReporter

logger = __import__("logging").getLogger("invest")


# ── 健康检查（后台并行）──


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


# ── 轻量级行情获取（无指数/穿透/分类）──


def _compute_details(holdings: list, config: dict, reporter: ProgressReporter) -> list:
    """轻量级行情获取，供 both 路径使用。

    仅获取行情明细，不获取指数/穿透/分类数据（与 _cmd_generate_both 语义对齐）。
    """
    from src.python.report.market_value import _generate_details

    reporter.info("正在获取行情数据...")
    details = _generate_details(holdings)
    reporter.ok(f"行情数据获取完成，共 {len(details)} 条")
    return details


# ── 校验函数 ──


def _validate_prep_completeness(prep: dict) -> None:
    """校验 prepare_report_data 返回数据的完整性。"""
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


def _validate_pipeline_snapshot(pipeline_data: dict | None) -> None:
    """校验 capture_snapshot 返回数据的完整性。"""
    if pipeline_data is not None:
        assert isinstance(pipeline_data, dict), "capture_snapshot pipeline_data 类型异常"
        _diff = pipeline_data.get("diff")
        if _diff is not None:
            if not isinstance(_diff, dict):
                logger.warning("[checkpoint] pipeline_data.diff 类型异常: %s", type(_diff).__name__)


# ── 全量量化指标（F2 + 风险指标 + 情景分析 + 口径修正）──


def _prepare_full_risk_metrics(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    perf: object,
    history_mode: str,
    enable_history: bool,
    prep: dict,
    pipeline_data: dict | None,
) -> tuple[dict | None, dict | None]:
    """F2 历史走势获取 + 全量量化指标 + 情景分析 + 口径修正。

    返回 (history_data, metrics)，就地注入 prep 和 pipeline_data 的 risk_metrics。
    enable_history 为 False 或数据不可用时返回 (None, None)。
    """
    from src.python.analysis.alignment_correction import compute_alignment_factors
    from src.python.analysis.metrics import compute_all_metrics
    from src.python.analysis.scenario import scenario_analysis
    from src.python.report._snapshot import fetch_history_data

    if not enable_history:
        reporter.info("[章节配置] 历史走势已关闭，跳过")
        return None, None

    perf.start("历史走势")
    _resolved_mode = "auto" if history_mode in ("auto",) else "off"
    history_data = fetch_history_data(holdings, config, reporter, mode=_resolved_mode)
    perf.stop()

    # 从 history_data 提取风险指标，注入 prep 和 pipeline_data
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

    # [checkpoint] risk_metrics 完整性校验
    _injected = prep.get("risk_metrics", {})
    if not _injected.get("annualized_volatility") and _injected.get("annualized_volatility") != 0:
        logger.warning("[checkpoint] prep.risk_metrics 缺 annualized_volatility")

    # ── 全量量化指标 + 情景分析 + 口径修正 ──
    _daily_returns = history_data.get("daily_returns_portfolio", []) if history_data else None
    if _daily_returns:
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
            _scenario = scenario_analysis(
                portfolio_value=_total_mv,
                beta=_beta_val,
                beta_ci_lower=_beta_analysis.get("ci_lower"),
                beta_ci_upper=_beta_analysis.get("ci_upper"),
                beta_se=_beta_analysis.get("std_error"),
                portfolio_volatility=history_data.get("annualized_volatility"),
            )
            if _scenario.get("has_data") and _scenario.get("scenarios"):
                _metrics["scenario_analysis"] = _scenario
    else:
        _metrics = None

    return history_data, _metrics


# ── _generate_full_html_report（拆分自 _generate_report_full）──


def _generate_full_html_report(
    holdings: list,
    prep: dict,
    output_dir: str | None,
    sec_order: list,
    llm_content: tuple,
    news_data: list,
    news_llm_meta: dict,
    news_ok: bool,
    history_data: dict | None,
    reporter: ProgressReporter,
    enable_fund_deep_analysis: bool,
    enable_news: bool,
    enable_history: bool,
    enable_llm: bool,
    debate_info: dict | None,
    result,
    metrics: dict | None = None,
    factor_exposure: dict | None = None,
) -> bool:
    """full 路径的 HTML 报告生成，返回是否成功。

    Args:
        metrics: compute_all_metrics() 返回值（14 项全量，仅 full 路径）；
            用于构建 radar 图数据（无则从 risk_metrics/history_data 降级）。
        factor_exposure: 因子暴露分析 C19 契约 dict，
            基金深度分析关闭或数据不足时为 None/available=False。
    """
    from src.python.config.features import is_feature_enabled
    from src.python.report.html_writer import write_html_report

    _report_label = "含新闻 + LLM" if news_ok else "仅 LLM"
    reporter.info(f"正在生成 HTML 报告（{_report_label}分析章节）...")
    try:
        _enable_interactive_charts = is_feature_enabled("enable_interactive_charts")
        chart_datasets = _build_chart_datasets_for_report(
            history_data=history_data,
            details=prep.get("details"),
            risk_metrics=prep.get("risk_metrics"),
            all_metrics=metrics,
            enable_interactive=_enable_interactive_charts,
        )
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
            enable_fund_deep_analysis=enable_fund_deep_analysis,
            enable_news=enable_news,
            enable_history=enable_history,
            enable_llm=enable_llm,
            debate_info=debate_info,
            chart_datasets=chart_datasets,
            enable_interactive_charts=_enable_interactive_charts,
            factor_exposure=factor_exposure,
        )
        reporter.ok(f"HTML 报告已生成: {path}")
        return True
    except Exception:
        reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("HTML 报告写入失败")
        result.errors.append("HTML 报告生成失败")
        return False


# ── _generate_full_excel_report（拆分自 _generate_report_full）──


def _generate_full_excel_report(
    holdings: list,
    prep: dict,
    output_dir: str | None,
    news_ok: bool,
    llm_content: tuple,
    news_data: list,
    news_llm_meta: dict,
    sec_order: list,
    pipeline_data: dict | None,
    history_data: dict | None,
    reporter: ProgressReporter,
    enable_fund_deep_analysis: bool,
    enable_news: bool,
    enable_history: bool,
    enable_llm: bool,
    debate_info: dict | None,
    result,
) -> bool:
    """full 路径的 Excel 报告生成，返回是否成功。"""
    from src.python.report.excel_generator import generate_excel_report

    reporter.info("正在生成 Excel 报告...")
    try:
        generate_excel_report(
            holdings,
            include_news=news_ok,
            output_dir=output_dir or prep["output_dir"],
            news_top_count=prep["news_top_count"],
            include_llm=enable_llm,
            llm_content=llm_content,
            details=prep["details"],
            a_indices=prep["a_indices"],
            us_indices=prep["us_indices"],
            news_data=news_data,
            news_llm_meta=news_llm_meta,
            section_order=sec_order,
            progress=reporter,
            pipeline_data=pipeline_data,
            history_data=history_data,
            enable_fund_deep_analysis=enable_fund_deep_analysis,
            enable_news=enable_news,
            enable_history=enable_history,
            enable_llm=enable_llm,
            debate_info=debate_info,
        )
        reporter.ok("Excel 报告已生成")
        return True
    except Exception:
        reporter.add_error("Excel 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("Excel 报告生成失败")
        result.errors.append("Excel 报告生成失败")
        return False


# ── _generate_report_both（生成 HTML+Excel，不含 LLM）──


def _generate_report_both(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    history_mode: str = "off",
    output_dir: str | None = None,
) -> "ReportResult":
    """both 报告路径：生成 HTML + Excel，不含 LLM 分析章节。

    流程：_compute_details() → capture_snapshot() → fetch_history_data()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import is_enable_fund_deep_analysis, is_enable_history, is_enable_news
    from src.python.config.features import is_feature_enabled
    from src.python.core.perf import PerfCollector
    from src.python.core.registry import get_report_section_order
    from src.python.report._snapshot import capture_snapshot, fetch_history_data
    from src.python.report.excel_generator import generate_excel_report
    from src.python.report.html_writer import write_html_report
    from src.python.report.orchestrator import ReportResult

    perf = PerfCollector(report_type="both", holdings=holdings)
    result = ReportResult()
    result.holdings_ok = True

    # 后台启动健康检查（与数据获取并行）
    _health_fut = _spawn_health_checks(holdings)

    _enable_fund_deep_analysis = is_enable_fund_deep_analysis(config)
    _enable_news = is_enable_news(config)
    _enable_history = is_enable_history(config)
    _enable_interactive_charts = is_feature_enabled("enable_interactive_charts")
    sec_order = get_report_section_order(config)
    output = output_dir or config.get("output_dir", "reports")
    news_top_count = int(config.get("news_top_count", 100))

    # ── 1. 行情获取（轻量级，无指数/穿透/分类） ──
    perf.start("行情获取")
    details = _compute_details(holdings, config, reporter)
    perf.stop()

    # ── 2. F1 快照对比（始终执行） ──
    perf.start("快照对比")
    pipeline_data = capture_snapshot(holdings, details, config, reporter)
    perf.stop()
    # [checkpoint] pipeline_data 类型断言
    if pipeline_data is not None:
        assert isinstance(pipeline_data, dict), "capture_snapshot(both) pipeline_data 类型异常"
        _diff = pipeline_data.get("diff")
        if _diff is not None and not isinstance(_diff, dict):
            logger.warning("[checkpoint] pipeline_data.diff 类型异常(both): %s", type(_diff).__name__)

    # ── 3. F2 历史走势（条件获取） ──
    if _enable_history:
        _resolved_mode = "auto" if history_mode in ("auto",) else "off"
        perf.start("历史走势")
        history_data = fetch_history_data(holdings, config, reporter, mode=_resolved_mode)
        perf.stop()
    else:
        history_data = None
        reporter.info("[章节配置] 历史走势已关闭，跳过")

    # ── 4. HTML 报告 ──
    _news_label = "含新闻" if _enable_news else "无新闻"
    reporter.info(f"正在生成 HTML 报告（{_news_label}）...")
    perf.start("HTML 生成")
    try:
        chart_datasets = _build_chart_datasets_for_report(
            history_data=history_data,
            details=details,
            enable_interactive=_enable_interactive_charts,
        )
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
            chart_datasets=chart_datasets,
            enable_interactive_charts=_enable_interactive_charts,
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


# ── Chart.js 数据集构建辅助 ───────────────────────────────


def _build_chart_datasets_for_report(
    *,
    history_data: dict | None,
    details: list | None = None,
    risk_metrics: dict | None = None,
    all_metrics: dict | None = None,
    enable_interactive: bool = True,
) -> dict | None:
    """构建 Chart.js 数据集（Flag 关闭或数据缺失时返回 None/空 dict）。

    - Flag 关闭 → None（模板不渲染 Chart.js，回退旧 Canvas）
    - Flag 开启 → build_chart_datasets()（内部对单图失败独立 try/except，R11）

    metrics_* Flag（§6.6 F1）：收集雷达子开关值传给预处理器，
    关闭的指标在 radar 数据集输出 "N/A"。注：metrics_risk_contribution
    是指标级熔断开关（circuit_breaker_wrapper 消费），非雷达轴，不在此收集。
    """
    if not enable_interactive:
        return None
    try:
        from src.python.config.features import is_feature_enabled
        from src.python.report.chart_data_builder import build_chart_datasets

        _metric_flag_names = (
            "metrics_sharpe",
            "metrics_calmar",
            "metrics_hhi",
            "metrics_winrate",
            "metrics_turnover",
            "metrics_beta",
        )
        metric_flags = {n: is_feature_enabled(n) for n in _metric_flag_names}

        return build_chart_datasets(
            history_data=history_data,
            details=details,
            risk_metrics=risk_metrics,
            all_metrics=all_metrics,
            metric_flags=metric_flags,
        )
    except Exception:
        # 预处理器顶层兜底（R11）：任何异常 → 返回空 dict（报告仍有表格/占位）
        logger.warning("[chart] 数据集构建失败，图表整体跳过（报告仍正常）", exc_info=True)
        return {}


# ── _generate_report_full（HTML+Excel+LLM）──


def _generate_report_full(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    history_mode: str = "off",
    force_llm: bool = False,
    output_dir: str | None = None,
) -> "ReportResult":
    """full 报告路径：生成 HTML + Excel + LLM 分析章节。

    流程：prepare_report_data() → capture_snapshot() → _prepare_full_risk_metrics()
          → get_sector_fund_flow() → _fetch_llm_and_news()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import is_enable_fund_deep_analysis, is_enable_history, is_enable_llm, is_enable_news
    from src.python.config.features import is_feature_enabled
    from src.python.fetcher.akshare import get_sector_fund_flow
    from src.python.core.perf import PerfCollector
    from src.python.core.registry import get_report_section_order
    from src.python.report._llm_news import _fetch_llm_and_news
    from src.python.report._snapshot import capture_snapshot
    from src.python.report.orchestrator import ReportResult, prepare_report_data

    perf = PerfCollector(report_type="full", holdings=holdings)
    result = ReportResult()
    result.holdings_ok = True
    _health_fut = _spawn_health_checks(holdings)

    _enable_fund_deep_analysis = is_enable_fund_deep_analysis(config)
    _enable_news = is_enable_news(config)
    _enable_history = is_enable_history(config)
    _enable_llm = is_enable_llm(config)
    sec_order = get_report_section_order(config)

    # ── 1. 完整数据准备（含指数/穿透/分类） ──
    perf.start("数据准备")
    prep = prepare_report_data(holdings, reporter, config)
    _validate_prep_completeness(prep)
    perf.stop()

    # ── 2. F1 快照对比 ──
    perf.start("快照对比")
    pipeline_data = capture_snapshot(holdings, prep["details"], config, reporter)
    # 因子暴露：prep 中已组装（C19 契约），注入 pipeline_data 供 HTML/Excel 消费；
    # capture_snapshot 在降级路径可能返回 None，需判空
    if pipeline_data is not None:
        pipeline_data["factor_exposure"] = prep.get("factor_exposure")
    _validate_pipeline_snapshot(pipeline_data)
    perf.stop()

    # ── 3. F2 历史走势 + 全量量化指标 ──
    history_data, _metrics = _prepare_full_risk_metrics(
        holdings,
        config,
        reporter,
        perf,
        history_mode,
        _enable_history,
        prep,
        pipeline_data,
    )

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

    # ── 5. 并行获取 LLM + 新闻 ──
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
    result.html_ok = _generate_full_html_report(
        holdings,
        prep,
        output_dir,
        sec_order,
        llm_content,
        news_data,
        news_llm_meta,
        news_ok,
        history_data,
        reporter,
        _enable_fund_deep_analysis,
        _enable_news,
        _enable_history,
        _enable_llm,
        debate_info,
        result,
        _metrics,
        prep.get("factor_exposure"),
    )

    # ── 7. Excel 报告 ──
    result.excel_ok = _generate_full_excel_report(
        holdings,
        prep,
        output_dir,
        news_ok,
        llm_content,
        news_data,
        news_llm_meta,
        sec_order,
        pipeline_data,
        history_data,
        reporter,
        _enable_fund_deep_analysis,
        _enable_news,
        _enable_history,
        _enable_llm,
        debate_info,
        result,
    )

    result.news_ok = news_ok
    result.report_generated = result.html_ok or result.excel_ok
    perf.save()
    _collect_health_checks(_health_fut, "full", holdings)
    return result
