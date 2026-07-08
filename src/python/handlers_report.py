"""TUI 报告生成命令处理器。

按职责从 tui_handlers.py 拆分而来，负责所有报告生成相关的命令函数。
"""
from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from src.python.llm import FAIL_REASON_DISABLED
from src.python.llm.prompts import _LLM_MODULE_FAILURE
from typing import Any

from src.python.logger import setup_logger
from src.python.registry import get_llm_module_name, get_report_section_order
from src.python.report.progress import TuiProgressReporter
from src.python.tui_handlers import (
    _check_network_available,
    _finish_report,
    _prepare_holdings,
    _print_error_with_hint,
    _print_llm_session_usage,
)
from src.python.tui_menu import get_config_cache

# 共享线程池 — 多处并行任务复用同一实例，避免反复创建/销毁
_POOL: ThreadPoolExecutor | None = None


def _get_pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="report")
        atexit.register(_POOL.shutdown, wait=False)
    return _POOL

logger = setup_logger()


def _generate_excel_report(*args, progress=None, **kwargs):
    """生成 Excel 报告（委托给 excel_generator 模块）。"""
    from src.python.report.excel_generator import generate_excel_report
    prog = progress if progress is not None else TuiProgressReporter()
    return generate_excel_report(*args, **kwargs, progress=prog)  # type: ignore[misc]


def _cmd_generate_excel() -> None:
    """生成 Excel 分析报告（必选内容）。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    sec_order = get_report_section_order(config)
    holdings = _prepare_holdings()
    if not holdings:
        return
    try:
        _generate_excel_report(holdings, include_news=False,
                               output_dir=config.get("output_dir", "reports"),
                               section_order=sec_order,
                               progress=reporter)
    except Exception as e:
        reporter.add_error("Excel 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("生成 Excel 报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)


def _cmd_generate_html(news: bool = False) -> None:
    """生成基础的 HTML 分析报告。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    sec_order = get_report_section_order(config)
    holdings = _prepare_holdings()
    if not holdings:
        return

    try:
        print("  [..] 正在获取行情数据并生成 HTML 报告...")
        from src.python.report.html_writer import write_html_report
        news_top_count = int(config.get("news_top_count", 100))
        path = write_html_report(
            holdings, output_dir=config.get("output_dir", "reports"),
            news_top_count=news_top_count, include_news=news,
            section_order=sec_order,
            progress=reporter,
        )
        print()
        print(f"  [OK] HTML 报告已生成: {path}")
    except Exception as e:
        reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("生成 HTML 报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    sec_order = get_report_section_order(config)
    holdings = _prepare_holdings()
    if not holdings:
        return

    try:
        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))
        today_str = datetime.now().strftime("%Y-%m-%d")

        from src.python.report.market_value import _generate_details
        reporter.info("正在获取行情数据...")
        details = _generate_details(holdings, today_str)
        _check_network_available(details)
        reporter.ok(f"行情数据获取完成，共 {len(details)} 条")

        from src.python.report.html_writer import write_html_report
        reporter.info("正在生成 HTML 报告（含新闻）...")
        try:
            path = write_html_report(
                holdings, output_dir=output_dir,
                news_top_count=news_top_count, include_news=True,
                details=details, section_order=sec_order,
                progress=reporter,
            )
            reporter.ok(f"HTML 报告已生成: {path}")
        except Exception:
            reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
            logger.exception("HTML 报告写入失败")
            reporter.error("HTML 报告生成失败（详情请查看日志）")
            reporter.info("继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=output_dir,
            news_top_count=news_top_count, details=details,
            section_order=sec_order,
            progress=reporter,
        )
    except Exception as e:
        reporter.add_error("全系列报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)


def _process_llm_news_futures(
    llm_fut, news_fut, reporter,
) -> tuple[tuple, list, dict]:
    """处理 LLM 生成 + 新闻获取的并行 Future 结果。"""
    llm_content = (None, None, None, None)
    news_data: list = []
    news_llm_meta: dict = {}

    for fut in as_completed([news_fut, llm_fut]):
        if fut is llm_fut:
            try:
                (llm_global_macro, llm_expert_review,
                 llm_health_check, llm_penetration_deep,
                 global_macro_cached, expert_review_cached,
                 health_check_cached, penetration_deep_cached) = fut.result()
                llm_content = (llm_global_macro, llm_expert_review,
                               llm_health_check, llm_penetration_deep)
                _MODULE_KEYS = ("global_macro", "expert_review",
                                "health_check", "penetration_deep")
                _MODULE_RESULTS = (llm_global_macro, llm_expert_review,
                                   llm_health_check, llm_penetration_deep)
                _CACHED_FLAGS = (global_macro_cached, expert_review_cached,
                                 health_check_cached, penetration_deep_cached)
                disabled: list[str] = []
                failed: list[str] = []
                ok_count = 0
                for mk, r in zip(_MODULE_KEYS, _MODULE_RESULTS):
                    if r is not None:
                        ok_count += 1
                    elif _LLM_MODULE_FAILURE.get(mk) == FAIL_REASON_DISABLED:
                        disabled.append(get_llm_module_name(mk))
                    else:
                        failed.append(get_llm_module_name(mk))

                for name in disabled:
                    reporter.info(f"{name}：已跳过（菜单 S 可切换）")
                for name in failed:
                    reporter.add_error(f"{name}：内容生成失败（已降级使用占位文本）")
                    reporter.warn(f"{name}：内容生成失败（已降级使用占位文本）")

                if ok_count > 0 and not failed:
                    tag = "缓存" if all(_CACHED_FLAGS) else "LLM"
                    reporter.ok(f"{tag} 内容生成完成")
                elif ok_count == 0 and not failed and not disabled:
                    reporter.warn("LLM 均未生成（请检查 LLM 配置）")
                elif ok_count == 0 and not failed:
                    reporter.info("所有 LLM 内容已跳过，未调用 LLM")
            except Exception:
                reporter.add_error("LLM 内容生成异常（详情请查看日志文件 logs/app.log）")
                reporter.error("LLM 内容生成异常（详情请查看日志）")
        else:
            try:
                news_data, news_llm_meta = fut.result()
                reporter.ok(f"新闻获取完成，共 {len(news_data)} 条")
            except Exception:
                reporter.add_error("新闻获取异常（详情请查看日志文件 logs/app.log）")
                reporter.warn("新闻获取异常（详情请查看日志）")

    return llm_content, news_data, news_llm_meta


def _prepare_report_data(holdings: list, reporter: TuiProgressReporter) -> dict:
    """获取行情、指数、穿透数据，整理持仓明细字典列表。"""
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.report.market_value import _generate_details, classify_holdings
    from src.python.report.penetration import compute_penetration_top10

    config = get_config_cache() or {}
    output_dir = config.get("output_dir", "reports")
    news_top_count = int(config.get("news_top_count", 100))
    today_str = datetime.now().strftime("%Y-%m-%d")

    reporter.info("正在获取行情数据...")
    details = _generate_details(holdings, today_str)
    _check_network_available(details)
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
        "output_dir": output_dir,
        "news_top_count": news_top_count,
    }


def _prompt_force_llm(reporter: TuiProgressReporter) -> bool:
    """询问用户是否强制刷新 LLM 缓存。"""
    try:
        _resp = input("  [..] 是否强制重新生成 LLM 内容（跳过缓存）？(y/N): ").strip().lower()
        _force = _resp == "y"
    except (EOFError, KeyboardInterrupt):
        _force = False
    if _force:
        reporter.ok("将跳过 LLM 缓存强制重新生成")
    return _force


def _compute_early_warnings(
    holdings: list, penetrated_assets: list, sector_flow: list[dict[str, Any]],
    news_data: list, news_llm_meta: dict, reporter: TuiProgressReporter,
) -> dict | None:
    """计算智能预警（行业资金流向联动 + 新闻情绪聚合）。"""
    try:
        from src.python.report.early_warning import compute_early_warnings
        _warnings = compute_early_warnings(
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


def _cmd_generate_full() -> None:
    """生成包含所有内容的全系列报告（Excel + HTML + 新闻 + LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    holdings = _prepare_holdings()
    if not holdings:
        return

    try:
        prep = _prepare_report_data(holdings, reporter)
        sec_order = get_report_section_order(get_config_cache() or {})

        from src.python.llm import generate_all_llm
        from src.python.providers.akshare_extras import get_sector_fund_flow
        from src.python.report.news_correlation import build_news_data

        reporter.info("正在获取行业资金流向...")
        _sector_flow = get_sector_fund_flow()
        if _sector_flow:
            reporter.ok("行业资金流向获取完成")
        _force_llm = _prompt_force_llm(reporter)

        _llm_ex = _get_pool()
        _news_fut = _llm_ex.submit(
            build_news_data, holdings, prep["news_top_count"], prep["penetrated_assets"],
        )
        _llm_fut = _llm_ex.submit(
            generate_all_llm,
            prep["a_indices"], prep["us_indices"],
            prep["total_mv"], prep["total_cost"], prep["total_profit"],
            prep["total_today_profit"], len(holdings), prep["categories"],
            penetrated_assets=prep["penetrated_assets"],
            holdings_details=prep["holdings_details"],
            sector_flow=_sector_flow, force=_force_llm,
        )
        llm_content, news_data, news_llm_meta = _process_llm_news_futures(
            _llm_fut, _news_fut, reporter,
        )

        _print_llm_session_usage()

        _early_warnings = _compute_early_warnings(
            holdings, prep["penetrated_assets"], _sector_flow,
            news_data, news_llm_meta, reporter,
        )

        from src.python.report.html_writer import write_html_report
        reporter.info("正在生成 HTML 报告（含新闻 + LLM 分析章节）...")
        try:
            path = write_html_report(
                holdings, output_dir=prep["output_dir"],
                news_top_count=prep["news_top_count"], include_news=True,
                llm_content=llm_content, details=prep["details"],
                news_data=news_data, news_llm_meta=news_llm_meta,
                early_warnings=_early_warnings, section_order=sec_order,
                progress=reporter,
            )
            reporter.ok(f"HTML 报告已生成: {path}")
        except Exception:
            reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
            logger.exception("HTML 报告写入失败")
            reporter.error("HTML 报告生成失败（详情请查看日志）")
            reporter.info("继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=prep["output_dir"],
            news_top_count=prep["news_top_count"], include_llm=True,
            llm_content=llm_content,
            details=prep["details"], a_indices=prep["a_indices"],
            us_indices=prep["us_indices"],
            news_data=news_data,
            news_llm_meta=news_llm_meta,
            section_order=sec_order,
            early_warnings=_early_warnings, progress=reporter,
        )
    except Exception as e:
        reporter.add_error("全系列报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)
