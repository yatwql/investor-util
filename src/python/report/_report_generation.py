"""报告生成实现 — both/full 两种路径的 HTML+Excel 生成逻辑（聚合门面）。

包含报告生成管线各工序实现。本文件为聚合门面：
  - 后台健康检查          → `_report_health.py`
  - 轻量行情/数据注入/校验 → `_report_helpers.py`
  - 全量量化指标装配       → `_full_risk_metrics.py`
  - Chart.js 数据集构建    → `_chart_dataset_factory.py`
门面保留 both/full 双路径生成编排（`_generate_report_*`）并 re-export 子模块符号。
"""

from __future__ import annotations

import logging

from src.python.report.progress import ProgressReporter

# ── 子模块 re-export ────────────────────────────────────
from src.python.report._chart_dataset_factory import _build_chart_datasets_for_report  # noqa: F401
from src.python.report._full_risk_metrics import _prepare_full_risk_metrics  # noqa: F401
from src.python.report._report_health import _collect_health_checks, _spawn_health_checks  # noqa: F401
from src.python.report._report_helpers import (  # noqa: F401
    _both_action_holdings_details,
    _compute_details,
    _inject_evolution_data,
    _inject_snapshot_diff_data,
    _validate_pipeline_snapshot,
    _validate_prep_completeness,
)

logger = __import__("logging").getLogger("invest")


# ── _generate_full_html_report ─────────────────────────


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
    style_factor_data: dict | None = None,
    position_relationship_data: dict | None = None,
    evolution_data: dict | None = None,
    enable_portfolio_evolution: bool = True,
    enable_action: bool = False,
    enable_data_quality: bool = False,
    position_status: dict | None = None,
    data_freshness: dict | None = None,
    action_data: dict | None = None,
    crisis_annotation_data: dict | None = None,
    tail_risk_data: dict | None = None,
    snapshot_diff_data: dict | None = None,
    fund_flow_data: dict | None = None,
    valuation_data: dict | None = None,
    market_temperature_data: dict | None = None,
) -> bool:
    """full 路径的 HTML 报告生成，返回是否成功。

    Args:
        metrics: compute_all_metrics() 返回值（14 项全量，仅 full 路径）；
            用于构建 radar 图数据（无则从 risk_metrics/history_data 降级）。
        style_factor_data: 风格与因子分析数据契约 dict（style_factor_data 主键，
            内嵌 industry_beta 子键），基金深度分析关闭或数据不足时为 None/available=False。
        position_relationship_data: 持仓关系矩阵数据契约 dict（相关性区块数据源），
            基金深度分析关闭或数据不足时为 None/available=False。
        evolution_data: 组合演进数据契约 dict（多快照趋势聚合），
            数据不足时 available=False（模板写占位）。
        enable_portfolio_evolution: board 层 — 组合演进章节是否开启。
        enable_data_quality: 子模块 — 数据质量仪表盘（默认关，保持旧样式）。
        position_status: 品种覆盖诊断 `position_status` 契约 dict，
            品种覆盖区块数据源（开关关闭时忽略）。
        data_freshness: 可信度摘要 `data_freshness` 契约 dict，
            可信度区块 + 报告头部数据异常摘要行数据源（开关关闭时忽略）。
        enable_action: board 层 — 行动建议章节是否开启（默认关）。
        action_data: 行动建议单一数据源 `action_data` 契约 dict，
            行动建议板块 + 智囊团深度复盘行动摘要数据源（开关关闭时忽略）。
        fund_flow_data: 成本流水数据 dict
            （汇总 XIRR / 持仓分类成本分档与分红 / 市值核算资金加权成本渲染数据源，
            开关关闭或传入 None 时模板保持既有输出）。
        valuation_data: 估值分位数据契约 dict（「资产穿透TOP10」估值分位列数据源，
            开关关闭或传入 None 时模板保持既有输出）。
        market_temperature_data: 市场温度数据契约 dict
            （「投资分析汇总」市场温度刻度行数据源，开关关闭或传入 None 时保持既有输出）。
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
            enable_portfolio_evolution=enable_portfolio_evolution,
            enable_action=enable_action,
            enable_llm=enable_llm,
            debate_info=debate_info,
            chart_datasets=chart_datasets,
            enable_interactive_charts=_enable_interactive_charts,
            style_factor_data=style_factor_data,
            position_relationship_data=position_relationship_data,
            evolution_data=evolution_data,
            enable_data_quality=enable_data_quality,
            position_status=position_status,
            data_freshness=data_freshness,
            action_data=action_data,
            crisis_annotation_data=crisis_annotation_data,
            tail_risk_data=tail_risk_data,
            snapshot_diff_data=snapshot_diff_data,
            fund_flow_data=fund_flow_data,
            valuation_data=valuation_data,
            market_temperature_data=market_temperature_data,
        )
        reporter.ok(f"HTML 报告已生成: {path}")
        return True
    except Exception:
        reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("HTML 报告写入失败")
        result.errors.append("HTML 报告生成失败")
        return False


# ── _generate_full_excel_report ────────────────────────


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
    enable_portfolio_evolution: bool = True,
    enable_action: bool = False,
    enable_data_quality: bool = False,
    enable_cost_lots: bool = False,
    transactions: list | None = None,
    dividends: list | None = None,
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
            enable_portfolio_evolution=enable_portfolio_evolution,
            enable_action=enable_action,
            enable_llm=enable_llm,
            debate_info=debate_info,
            enable_data_quality=enable_data_quality,
            enable_cost_lots=enable_cost_lots,
            transactions=transactions,
            dividends=dividends,
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
    fetch_history: bool = False,
    output_dir: str | None = None,
    transactions: list | None = None,
    dividends: list | None = None,
) -> "ReportResult":
    """both 报告路径：生成 HTML + Excel，不含 LLM 分析章节。

    流程：_compute_details() → capture_snapshot() → fetch_history_data()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import (
        is_enable_action,
        is_enable_cost_lots,
        is_enable_data_quality,
        is_enable_fund_deep_analysis,
        is_enable_history,
        is_enable_news,
        is_enable_portfolio_evolution,
    )
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
    _enable_portfolio_evolution = is_enable_portfolio_evolution(config)
    _enable_action = is_enable_action(config)
    _enable_data_quality = is_enable_data_quality(config)
    _enable_cost_lots = is_enable_cost_lots(config)
    _enable_interactive_charts = is_feature_enabled("enable_interactive_charts")
    sec_order = get_report_section_order(config)
    output = output_dir or config.get("output_dir", "reports")
    news_top_count = int(config.get("news_top_count", 300))

    # ── 1. 行情获取（轻量级，无指数/穿透/分类） ──
    perf.start("行情获取")
    details = _compute_details(holdings, config, reporter)
    perf.stop()

    # 估值分位 + 市场温度（数据契约）：both 路径同样渲染「资产穿透TOP10」估值列
    # 与「投资分析汇总」温度行；开关关闭时编排函数返回 None（保持既有输出）
    from src.python.report.orchestrator import (
        compute_market_temperature_data,
        compute_valuation_data,
    )

    valuation_data = compute_valuation_data(holdings, details, config, reporter)
    market_temperature_data = compute_market_temperature_data(config, reporter)

    # ── 2. 快照对比（始终执行） ──
    perf.start("快照对比")
    pipeline_data = capture_snapshot(holdings, details, config, reporter)
    # 2b. 组合演进数据（聚合多期快照，evolution_data；开关关闭时跳过计算）
    if _enable_portfolio_evolution:
        pipeline_data = _inject_evolution_data(pipeline_data)
        # 2b1. 快照差异摘要（snapshot_diff_data）：组合演进章顶部变化摘要，
        #      与演进数据同开关（同属组合演进章节）
        pipeline_data = _inject_snapshot_diff_data(pipeline_data)
    # 2c. 品种覆盖诊断 + 可信度摘要：逐品种数据状态/新鲜度标注，注入 pipeline_data
    #    （position_status + data_freshness）
    from src.python.analysis.action_advisor import build_action_data
    from src.python.core.data_freshness import build_freshness_summary
    from src.python.core.holding_status import build_coverage_summary
    from src.python.report.market_value import get_last_trading_day, get_prev_trading_day
    from src.python.report.pipeline_data_builder import merge_pipeline_data

    pipeline_data = merge_pipeline_data(
        pipeline_data,
        position_status=build_coverage_summary(holdings, details),
        data_freshness=build_freshness_summary(
            holdings,
            details,
            trading_day=get_last_trading_day(),
            prev_trading_day=get_prev_trading_day(),
        ),
        # 估值分位 + 市场温度（数据契约）：both 路径此处组装，开关关闭时为 None
        valuation_data=valuation_data,
        market_temperature_data=market_temperature_data,
    )
    # 行动建议单一数据源（action_data）在「3. 历史走势」之后统一注入
    # （组合回撤纪律需组合历史峰值市值，见 tail_risk_data 注入点）。
    perf.stop()
    # [checkpoint] pipeline_data 类型断言
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

    # 危机区间标注（crisis_annotation_data）：基于既有 bars 重叠裁剪，不拉长 lookback
    from src.python.analysis.crisis_annotation import build_crisis_annotation

    crisis_annotation_data = build_crisis_annotation(history_data)
    if pipeline_data is not None:
        pipeline_data["crisis_annotation_data"] = crisis_annotation_data

    # 尾部风险统计（tail_risk_data）：复用历史日收益序列，样本不足时 available=False
    from src.python.analysis.tail_risk import compute_tail_risk

    tail_risk_data = compute_tail_risk((history_data or {}).get("bars"))
    if pipeline_data is not None:
        pipeline_data["tail_risk_data"] = tail_risk_data

    # 行动建议单一数据源（action_data）：行动建议板块 + 智囊团深度复盘行动摘要共享。
    # 此处为 both 路径唯一构建（历史已就绪）：组合回撤纪律以组合历史峰值市值
    # 为基准，峰值自 history_data.bars 计算；历史走势关闭时峰值取 None，
    # 回撤纪律按「峰值未知」处理（组合级回撤不激活），其余纪律不受影响。
    from src.python.analysis.action_advisor import build_action_data
    from src.python.analysis.metrics import compute_portfolio_peak_mv

    if pipeline_data is not None:
        pipeline_data["action_data"] = build_action_data(
            _both_action_holdings_details(details),
            sum(d.market_value for d in details),
            portfolio_peak_mv=compute_portfolio_peak_mv((history_data or {}).get("bars")),
        )

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
        # 成本流水数据（fund_flow_data）：复用 excel_market_data 组装逻辑，
        # 开关关闭返回 None（HTML 模板保持既有输出）。
        from src.python.report.excel_market_data import _build_flow_data

        fund_flow_data = _build_flow_data(_enable_cost_lots, transactions, dividends, holdings, details)
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
            enable_portfolio_evolution=_enable_portfolio_evolution,
            enable_action=_enable_action,
            enable_llm=False,
            chart_datasets=chart_datasets,
            enable_interactive_charts=_enable_interactive_charts,
            evolution_data=(pipeline_data or {}).get("evolution_data"),
            enable_data_quality=_enable_data_quality,
            position_status=(pipeline_data or {}).get("position_status"),
            data_freshness=(pipeline_data or {}).get("data_freshness"),
            action_data=(pipeline_data or {}).get("action_data"),
            crisis_annotation_data=crisis_annotation_data,
            tail_risk_data=tail_risk_data,
            snapshot_diff_data=(pipeline_data or {}).get("snapshot_diff_data"),
            fund_flow_data=fund_flow_data,
            valuation_data=valuation_data,
            market_temperature_data=market_temperature_data,
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
            enable_portfolio_evolution=_enable_portfolio_evolution,
            enable_action=_enable_action,
            enable_llm=False,
            enable_data_quality=_enable_data_quality,
            enable_cost_lots=_enable_cost_lots,
            transactions=transactions,
            dividends=dividends,
            valuation_data=valuation_data,
            market_temperature_data=market_temperature_data,
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


# ── _generate_report_full（HTML+Excel+LLM）──


def _generate_report_full(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    fetch_history: bool = False,
    force_llm: bool = False,
    output_dir: str | None = None,
    transactions: list | None = None,
    dividends: list | None = None,
) -> "ReportResult":
    """full 报告路径：生成 HTML + Excel + LLM 分析章节。

    流程：prepare_report_data() → capture_snapshot() → _prepare_full_risk_metrics()
          → get_sector_fund_flow() → _fetch_llm_and_news()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import (
        is_enable_action,
        is_enable_cost_lots,
        is_enable_data_quality,
        is_enable_fund_deep_analysis,
        is_enable_history,
        is_enable_llm,
        is_enable_news,
        is_enable_portfolio_evolution,
    )
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
    _enable_portfolio_evolution = is_enable_portfolio_evolution(config)
    _enable_action = is_enable_action(config)
    _enable_llm = is_enable_llm(config)
    _enable_data_quality = is_enable_data_quality(config)
    _enable_cost_lots = is_enable_cost_lots(config)
    sec_order = get_report_section_order(config)

    # ── 1. 完整数据准备（含指数/穿透/分类） ──
    perf.start("数据准备")
    prep = prepare_report_data(holdings, reporter, config)
    _validate_prep_completeness(prep)
    perf.stop()

    # ── 2. 快照对比 ──
    perf.start("快照对比")
    pipeline_data = capture_snapshot(holdings, prep["details"], config, reporter)
    # 风格与因子 / 持仓关系矩阵 / 品种覆盖诊断：prep 中已组装（数据契约），
    # 注入 pipeline_data 供 HTML/Excel 消费；capture_snapshot 在降级路径可能返回 None，需判空
    if pipeline_data is not None:
        pipeline_data["style_factor_data"] = prep.get("style_factor_data")
        pipeline_data["position_relationship_data"] = prep.get("position_relationship_data")
        pipeline_data["position_status"] = prep.get("position_status")
        pipeline_data["data_freshness"] = prep.get("data_freshness")
        pipeline_data["action_data"] = prep.get("action_data")
        # 估值分位 + 市场温度（数据契约，prep 中已组装；开关关闭时为 None）
        pipeline_data["valuation_data"] = prep.get("valuation_data")
        pipeline_data["market_temperature_data"] = prep.get("market_temperature_data")
    _validate_pipeline_snapshot(pipeline_data)
    # 2b. 组合演进数据（聚合多期快照，evolution_data；开关关闭时跳过计算）
    if _enable_portfolio_evolution:
        pipeline_data = _inject_evolution_data(pipeline_data)
        # 2b1. 快照差异摘要（snapshot_diff_data）：组合演进章顶部变化摘要，
        #      与演进数据同开关（同属组合演进章节）
        pipeline_data = _inject_snapshot_diff_data(pipeline_data)
    perf.stop()

    # ── 3. 历史走势 + 全量量化指标 ──
    history_data, _metrics = _prepare_full_risk_metrics(
        holdings,
        config,
        reporter,
        perf,
        fetch_history,
        _enable_history,
        prep,
        pipeline_data,
    )

    # 3.5 行动建议回填（历史走势就绪后注入组合历史峰值市值，激活回撤纪律）。
    # prepare_report_data 的 action_data 为「中间占位构建」（persist_silence=False，
    # 不读写静默文件）：彼时历史时序未就绪、峰值未知。此处用 history_data.bars
    # 计算组合历史峰值并重建 action_data（默认 persist_silence=True），作为管线
    # 中纪律静默的唯一写入方——同时保证单品信号不被占位构建抢占静默而误抑制。
    from src.python.analysis.action_advisor import build_action_data
    from src.python.analysis.metrics import compute_portfolio_peak_mv

    _peak_mv = compute_portfolio_peak_mv((history_data or {}).get("bars"))
    _action_data = build_action_data(
        prep.get("holdings_details") or [],
        prep.get("total_mv", 0),
        portfolio_peak_mv=_peak_mv,
    )
    prep["action_data"] = _action_data
    if pipeline_data is not None:
        pipeline_data["action_data"] = _action_data

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
    # 成本流水数据（fund_flow_data）：复用 excel_market_data 组装逻辑，
    # 开关关闭返回 None（HTML 模板保持既有输出）。
    from src.python.report.excel_market_data import _build_flow_data

    fund_flow_data = _build_flow_data(_enable_cost_lots, transactions, dividends, holdings, prep["details"])
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
        prep.get("style_factor_data"),
        prep.get("position_relationship_data"),
        (pipeline_data or {}).get("evolution_data"),
        _enable_portfolio_evolution,
        _enable_action,
        _enable_data_quality,
        (pipeline_data or {}).get("position_status"),
        (pipeline_data or {}).get("data_freshness"),
        (pipeline_data or {}).get("action_data"),
        (pipeline_data or {}).get("crisis_annotation_data"),
        (pipeline_data or {}).get("tail_risk_data"),
        (pipeline_data or {}).get("snapshot_diff_data"),
        fund_flow_data,
        (pipeline_data or {}).get("valuation_data"),
        (pipeline_data or {}).get("market_temperature_data"),
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
        _enable_portfolio_evolution,
        _enable_action,
        _enable_data_quality,
        _enable_cost_lots,
        transactions,
        dividends,
    )

    result.news_ok = news_ok
    result.report_generated = result.html_ok or result.excel_ok
    perf.save()
    _collect_health_checks(_health_fut, "full", holdings)
    return result
