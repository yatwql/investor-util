"""LLM/新闻并行获取 — 线程池提交/收集/报告。

统一管理 LLM 内容和新闻数据的并行获取。
"""

from __future__ import annotations

import logging

from src.python.report.progress import ProgressReporter

logger = __import__("logging").getLogger("invest")


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


def _submit_llm_future(
    pool,
    holdings: list,
    prep_data: dict,
    sector_flow: list | None,
    force_llm: bool,
    pipeline_data: dict | None,
    enable_llm: bool,
    *,
    history_data: dict | None = None,
    comparison_indices: dict[str, str] | None = None,
    metrics: dict | None = None,
) -> object | None:
    """向线程池提交 LLM 生成任务，返回 Future 或 None。"""
    if not enable_llm:
        return None
    from src.python.llm import generate_all_llm

    return pool.submit(
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


def _submit_news_future(
    pool,
    holdings: list,
    prep_data: dict,
    enable_news: bool,
) -> object | None:
    """向线程池提交新闻获取任务，返回 Future 或 None。"""
    if not enable_news:
        return None
    from src.python.report.news_correlation import build_news_data

    return pool.submit(
        build_news_data,
        holdings,
        prep_data["news_top_count"],
        prep_data["penetrated_assets"],
    )


def _collect_llm_future_result(fut, reporter) -> tuple:
    """收集 LLM 生成结果，返回 (llm_content, debate_info)。"""
    try:
        _result = fut.result()
        llm_content = _result[:4]
        _cached = _result[4:8]
        _report_llm_module_results(llm_content, _cached, reporter)
        debate_info = _result[8] if len(_result) > 8 else None
        return llm_content, debate_info
    except Exception:
        reporter.add_error("LLM 内容生成异常（详情请查看日志文件 logs/app.log）")
        reporter.error("LLM 内容生成异常（详情请查看日志）")
        return (None, None, None, None), None


def _collect_news_future_result(fut, reporter) -> tuple:
    """收集新闻获取结果，返回 (news_data, news_llm_meta, news_ok)。"""
    try:
        news_data, news_llm_meta = fut.result()
        news_ok = bool(news_data)
        reporter.ok(f"新闻获取完成，共 {len(news_data)} 条")
        return news_data, news_llm_meta, news_ok
    except Exception:
        reporter.add_error("新闻获取异常（详情请查看日志文件 logs/app.log）")
        reporter.warn("新闻获取异常（详情请查看日志）")
        return [], {}, False


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
) -> tuple[tuple, list, dict, bool]:
    """并行获取 LLM 内容 + 新闻数据，统一处理 4 分支。

    内部管理线程池（max_workers=2）。
    LLM 和新闻的 ok/disabled/failed 计数统一归入此函数。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    llm_content: tuple = (None, None, None, None)
    news_data: list = []
    news_llm_meta: dict = {}
    news_ok: bool = False
    debate_info: dict | None = None

    # 分支 ④：均关闭
    if not enable_llm and not enable_news:
        reporter.info("[章节配置] 新闻和 LLM 均未开启，跳过内容生成")
        return llm_content, news_data, news_llm_meta, news_ok, debate_info

    if not enable_news:
        reporter.info("[章节配置] 市场新闻已关闭，跳过新闻获取")
    if not enable_llm:
        reporter.info("[章节配置] LLM 分析章节已关闭，跳过 LLM 内容生成")

    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_llm_news")
    try:
        _news_fut = _submit_news_future(pool, holdings, prep_data, enable_news)
        _llm_fut = _submit_llm_future(
            pool,
            holdings,
            prep_data,
            sector_flow,
            force_llm,
            pipeline_data,
            enable_llm,
            history_data=history_data,
            comparison_indices=comparison_indices,
            metrics=metrics,
        )

        if _llm_fut is not None and _news_fut is not None:
            # 分支 ①：LLM + 新闻均开启（并行等待）
            for fut in as_completed([_news_fut, _llm_fut]):
                if fut is _llm_fut:
                    llm_content, debate_info = _collect_llm_future_result(fut, reporter)
                else:
                    news_data, news_llm_meta, news_ok = _collect_news_future_result(fut, reporter)
        elif _news_fut is not None:
            # 分支 ②：仅新闻
            news_data, news_llm_meta, news_ok = _collect_news_future_result(_news_fut, reporter)
        elif _llm_fut is not None:
            # 分支 ③：仅 LLM
            llm_content, debate_info = _collect_llm_future_result(_llm_fut, reporter)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return llm_content, news_data, news_llm_meta, news_ok, debate_info
