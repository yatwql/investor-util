"""报告产物落盘包装层 —— full 路径的 HTML/Excel 生成入口（从 _report_generation 拆出）。

职责：把「契约 → 渲染层调用」的参数拼装与落盘 try/except 集中此处（章节顺序、开关透传、
实验/常规开关分流、失败登记与 `result` 标志位回填），使 `_report_generation.py` 只负责
管线编排。由编排模块导入使用（`_generate_report_full` 经门面命名空间解析，可被 mock patch）。

拆分动因：`_report_generation.py` 逼近 800 行硬上限（rf-582），按「编排 vs 输出包装」轴
把 full 路径 HTML 落盘 `_generate_full_html_report` 一并收入，与 `_generate_full_excel_report` 同居。
"""

from __future__ import annotations

import logging

from src.python.report._chart_dataset_factory import _build_chart_datasets_for_report
from src.python.report.progress import ProgressReporter

logger = logging.getLogger("invest")


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
    enable_fundamental_snapshot: bool = False,
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
            enable_fundamental_snapshot=enable_fundamental_snapshot,
            financial_report_digest_data=(pipeline_data or {}).get("financial_report_digest_data"),
            financial_indicator_data=(pipeline_data or {}).get("financial_indicator_data"),
        )
        reporter.ok("Excel 报告已生成")
        return True
    except Exception:
        reporter.add_error("Excel 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("Excel 报告生成失败")
        result.errors.append("Excel 报告生成失败")
        return False


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
    factor_catalog_data: dict | None = None,
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
    decision_review_data: dict | None = None,
    prosperity_framework_data: dict | None = None,
    enable_fundamental_snapshot: bool = False,
    financial_report_digest_data: dict | None = None,
    financial_indicator_data: dict | None = None,
    market_sentiment_data: dict | None = None,
    purchase_status_data: dict | None = None,
    holding_change_data: dict | None = None,
    event_impact_data: dict | None = None,
    schedule_replay_data: dict | None = None,
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
        enable_action: board 层 — 行动建议章节是否开启（config 默认开）。
        action_data: 行动建议单一数据源 `action_data` 契约 dict，
            行动建议板块 + 智囊团深度复盘行动摘要数据源（开关关闭时忽略）。
        fund_flow_data: 成本流水数据 dict
            （汇总 XIRR / 持仓分类成本分档与分红 / 市值核算资金加权成本渲染数据源，
            开关关闭或传入 None 时模板保持既有输出）。
        valuation_data: 估值分位数据契约 dict（「资产穿透TOP10」估值分位列数据源，
            开关关闭或传入 None 时模板保持既有输出）。
        market_temperature_data: 市场温度数据契约 dict
            （「投资分析汇总」市场温度刻度行数据源，开关关闭或传入 None 时保持既有输出）。
        market_sentiment_data: 市场情绪与持仓热点契约 dict（报告增强开关 `market_sentiment`，
            行动建议章内嵌区块数据源，开关关闭或传入 None 时保持既有输出）。
            与 Excel 侧同源，由编排层 `_generate_report_full` 注入——须在写 HTML 之前完成
            取数，否则本类别既不出现在矩阵、说明表也记「未使用」（与 Excel 自相矛盾）。
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
            factor_catalog_data=factor_catalog_data,
            position_relationship_data=position_relationship_data,
            evolution_data=evolution_data,
            enable_data_quality=enable_data_quality,
            position_status=position_status,
            data_freshness=data_freshness,
            action_data=action_data,
            prosperity_framework_data=prosperity_framework_data,
            crisis_annotation_data=crisis_annotation_data,
            tail_risk_data=tail_risk_data,
            snapshot_diff_data=snapshot_diff_data,
            fund_flow_data=fund_flow_data,
            valuation_data=valuation_data,
            market_temperature_data=market_temperature_data,
            decision_review_data=decision_review_data,
            market_sentiment_data=market_sentiment_data,
            enable_fundamental_snapshot=enable_fundamental_snapshot,
            financial_report_digest_data=financial_report_digest_data,
            financial_indicator_data=financial_indicator_data,
            purchase_status_data=purchase_status_data,
            holding_change_data=holding_change_data,
            event_impact_data=event_impact_data,
            schedule_replay_data=schedule_replay_data,
        )
        reporter.ok(f"HTML 报告已生成: {path}")
        return True
    except Exception:
        reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("HTML 报告写入失败")
        result.errors.append("HTML 报告生成失败")
        return False
