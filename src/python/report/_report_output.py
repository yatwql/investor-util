"""报告输出包装层 —— full 路径的 Excel 生成入口（从 _report_generation 拆出）。

职责：把「契约 → Excel 渲染层调用」的参数拼装集中此处（章节顺序、开关透传、实验/常规开关分流），
使 `_report_generation.py` 只负责编排与落盘结论。纯转发（无状态、无 IO 决策），由编排模块导入使用。

拆分动因：`_report_generation.py` 超过 800 行硬上限，按「编排 vs 输出包装」轴拆开。
"""

from __future__ import annotations

import logging

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
