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
from src.python.report.progress import ProgressReporter
from src.python.tui_menu import _GREEN, _RESET, get_config_cache

# 共享线程池 — 多处并行任务复用同一实例，避免反复创建/销毁
_POOL: ThreadPoolExecutor | None = None


def _get_pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="report")
        atexit.register(_POOL.shutdown, wait=False)
    return _POOL

logger = setup_logger()


def _generate_excel_report(*args: Any, **kwargs: Any) -> None:
    """生成 Excel 报告（委托给 excel_generator 模块）。"""
    from src.python.report.excel_generator import generate_excel_report
    kwargs.setdefault("progress", TuiProgressReporter())
    generate_excel_report(*args, **kwargs)


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


def _capture_snapshot(holdings: list, details: list, reporter: TuiProgressReporter) -> dict | None:
    """F1 持仓快照创建 + 差异计算 + 保存 + 清理。

    提取自 _cmd_generate_both() 和 _cmd_generate_full() 的共享函数，
    消除 ~67 行重复代码。

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
        _history_cfg = (get_config_cache() or {}).get("history", {})
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


def _fetch_history_data(history_mode: str, holdings: list, reporter: TuiProgressReporter) -> dict | None:
    """F2 历史走势数据获取，消除 B/L 菜单间的重复代码。

    Args:
        history_mode: "auto" / "prompt" / "off"
        holdings: 持仓列表
        reporter: 进度报告接口

    Returns:
        history_data 字典，获取失败或不可用时返回 None。
    """
    if history_mode not in ("auto", "prompt"):
        return None
    if history_mode == "prompt":
        try:
            _resp = input("  [..] 是否获取组合历史走势数据（as-if 模拟）？(y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            _resp = "n"
    else:
        _resp = "y"
    if _resp != "y":
        return None
    reporter.info("正在获取组合历史走势数据（as-if 模拟）...")
    from src.python.report.portfolio_history import PortfolioHistoryCalculator
    _history_cfg = (get_config_cache() or {}).get("history", {})
    _coverage = _history_cfg.get("coverage_threshold", 0.8)
    _benchmark_indices = _history_cfg.get("benchmark_indices", {})
    _calc = PortfolioHistoryCalculator(
        coverage_threshold=_coverage,
        benchmark_indices=_benchmark_indices,
    )
    _holdings_tuples = [(h.code, h.name, h.shares) for h in holdings]
    try:
        history_data = _calc.get_combined_timeseries(_holdings_tuples)
        if history_data and history_data.get("status") != "unavailable":
            reporter.ok("组合历史走势数据获取完成")
        else:
            reporter.warn("组合历史走势数据获取失败（部分持仓可能不支持历史数据）")
        return history_data
    except Exception:
        logger.info("[F2] 历史走势数据获取跳过", exc_info=True)
        return None


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    sec_order = get_report_section_order(config)
    holdings = _prepare_holdings()
    if not holdings:
        return

    try:
        # ── 读取板块可见性配置 ──
        from src.python.config import is_enable_b_series, is_enable_news, is_enable_history
        _enable_b_series = is_enable_b_series(config)
        _enable_news     = is_enable_news(config)
        _enable_history  = is_enable_history(config)

        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))
        today_str = datetime.now().strftime("%Y-%m-%d")

        from src.python.report.market_value import _generate_details
        reporter.info("正在获取行情数据...")
        details = _generate_details(holdings, today_str)
        _check_network_available(details)
        reporter.ok(f"行情数据获取完成，共 {len(details)} 条")

        # ── F1 快照对比：始终执行（不受 enable_history 影响） ──
        f_context = _capture_snapshot(holdings, details, reporter)

        # ── 条件获取：F2 历史走势（board + history.analysis 双重控制） ──
        if _enable_history:
            _history_mode = config.get("history", {}).get("analysis", "off")
            history_data = _fetch_history_data(_history_mode, holdings, reporter)
        else:
            history_data = None
            reporter.info("[板块配置] 历史走势已关闭，跳过")

        from src.python.report.html_writer import write_html_report
        _news_label = "含新闻" if _enable_news else "无新闻"
        reporter.info(f"正在生成 HTML 报告（{_news_label}）...")
        try:
            path = write_html_report(
                holdings, output_dir=output_dir,
                news_top_count=news_top_count, include_news=_enable_news,
                details=details, section_order=sec_order,
                history_data=history_data, progress=reporter,
                enable_b_series=_enable_b_series,
                enable_news=_enable_news,
                enable_history=_enable_history,
                enable_llm=False,           # B 菜单：不含 LLM 分析章节
            )
            reporter.ok(f"HTML 报告已生成: {path}")
        except Exception:
            reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
            logger.exception("HTML 报告写入失败")
            reporter.error("HTML 报告生成失败（详情请查看日志）")
            reporter.info("继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=_enable_news, output_dir=output_dir,
            news_top_count=news_top_count, details=details,
            section_order=sec_order,
            f_context=f_context, history_data=history_data, progress=reporter,
            enable_b_series=_enable_b_series,
            enable_news=_enable_news,
            enable_history=_enable_history,
            enable_llm=False,           # B 菜单：不含 LLM 分析章节
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
        # ── 读取板块可见性配置 ──
        from src.python.config import is_enable_b_series, is_enable_news, is_enable_history, is_enable_llm
        config = get_config_cache() or {}
        _enable_b_series = is_enable_b_series(config)
        _enable_news     = is_enable_news(config)
        _enable_history  = is_enable_history(config)
        _enable_llm      = is_enable_llm(config)

        prep = _prepare_report_data(holdings, reporter)
        sec_order = get_report_section_order(config)

        # ── F1 快照对比：始终执行（不受 enable_history 影响） ──
        f_context = _capture_snapshot(holdings, prep["details"], reporter)

        # ── 条件获取：F2 历史走势（board + history.analysis 双重控制） ──
        if _enable_history:
            _history_mode = config.get("history", {}).get("analysis", "off")
            history_data = _fetch_history_data(_history_mode, holdings, reporter)
        else:
            history_data = None
            reporter.info("[板块配置] 历史走势已关闭，跳过")

        from src.python.llm import generate_all_llm
        from src.python.providers.akshare_extras import get_sector_fund_flow
        from src.python.report.news_correlation import build_news_data

        reporter.info("正在获取行业资金流向...")
        _sector_flow = get_sector_fund_flow()
        if _sector_flow:
            reporter.ok("行业资金流向获取完成")
        _force_llm = _prompt_force_llm(reporter)

        _llm_ex = _get_pool()
        _news_available = False
        if _enable_news:
            _news_fut = _llm_ex.submit(
                build_news_data, holdings, prep["news_top_count"], prep["penetrated_assets"],
            )
        else:
            _news_fut = None
            reporter.info("[板块配置] 新闻板块已关闭，跳过新闻获取")

        if _enable_llm:
            _llm_fut = _llm_ex.submit(
                generate_all_llm,
                prep["a_indices"], prep["us_indices"],
                prep["total_mv"], prep["total_cost"], prep["total_profit"],
                prep["total_today_profit"], len(holdings), prep["categories"],
                penetrated_assets=prep["penetrated_assets"],
                holdings_details=prep["holdings_details"],
                sector_flow=_sector_flow, force=_force_llm,
                f_context=f_context,
            )
        else:
            _llm_fut = None
            reporter.info("[板块配置] LLM 板块已关闭，跳过 LLM 内容生成")

        if _news_fut is not None and _llm_fut is not None:
            # 新闻 + LLM 均开启：并行等待结果
            llm_content, news_data, news_llm_meta = _process_llm_news_futures(
                _llm_fut, _news_fut, reporter,
            )
            _news_available = bool(news_data)
        elif _news_fut is not None:
            # 仅新闻：等待新闻结果，LLM 内容为空
            news_data, news_llm_meta = _news_fut.result()
            _news_available = bool(news_data)
            llm_content = (None, None, None, None)
        elif _llm_fut is not None:
            # 仅 LLM：等待 LLM 结果，新闻为空
            news_data = []
            news_llm_meta = {}
            _result = _llm_fut.result()     # 8-tuple from generate_all_llm
            _llm_content = _result[:4]       # (global_macro, expert_review, health_check, penetration_deep)
            _llm_cached = _result[4:]        # 4 cached booleans
            _MODULE_KEYS = ("global_macro", "expert_review",
                            "health_check", "penetration_deep")
            ok_count = sum(1 for r in _llm_content if r is not None)
            disabled: list[str] = []
            failed: list[str] = []
            for mk, r in zip(_MODULE_KEYS, _llm_content):
                if r is not None:
                    continue
                if _LLM_MODULE_FAILURE.get(mk) == FAIL_REASON_DISABLED:
                    disabled.append(get_llm_module_name(mk))
                else:
                    failed.append(get_llm_module_name(mk))
            for name in disabled:
                reporter.info(f"{name}：已跳过（菜单 S 可切换）")
            for name in failed:
                reporter.add_error(f"{name}：内容生成失败（已降级使用占位文本）")
                reporter.warn(f"{name}：内容生成失败（已降级使用占位文本）")
            if ok_count > 0 and not failed:
                tag = "缓存" if all(_llm_cached) else "LLM"
                reporter.ok(f"{tag} 内容生成完成")
            elif ok_count == 0 and not failed and not disabled:
                reporter.warn("LLM 均未生成（请检查 LLM 配置）")
            elif ok_count == 0 and not failed:
                reporter.info("所有 LLM 内容已跳过，未调用 LLM")
            llm_content = (_llm_content[0], _llm_content[1],
                           _llm_content[2], _llm_content[3])
        else:
            # 新闻 + LLM 均关闭
            news_data = []
            news_llm_meta = {}
            llm_content = (None, None, None, None)
            reporter.info("[板块配置] 新闻和 LLM 均未开启，跳过内容生成")

        _print_llm_session_usage()

        _early_warnings = _compute_early_warnings(
            holdings, prep["penetrated_assets"], _sector_flow,
            news_data, news_llm_meta, reporter,
        )

        from src.python.report.html_writer import write_html_report
        _report_label = "含新闻 + LLM" if _news_available else "仅 LLM"
        reporter.info(f"正在生成 HTML 报告（{_report_label}分析章节）...")
        try:
            path = write_html_report(
                holdings, output_dir=prep["output_dir"],
                news_top_count=prep["news_top_count"],
                include_news=_news_available,
                llm_content=llm_content, details=prep["details"],
                news_data=news_data, news_llm_meta=news_llm_meta,
                early_warnings=_early_warnings, section_order=sec_order,
                history_data=history_data, progress=reporter,
                a_indices=prep["a_indices"], us_indices=prep["us_indices"],
                enable_b_series=_enable_b_series,
                enable_news=_enable_news,
                enable_history=_enable_history,
                enable_llm=_enable_llm,         # board 层：LLM 板块是否开启
            )
            reporter.ok(f"HTML 报告已生成: {path}")
        except Exception:
            reporter.add_error("HTML 报告生成失败（详情请查看日志文件 logs/app.log）")
            logger.exception("HTML 报告写入失败")
            reporter.error("HTML 报告生成失败（详情请查看日志）")
            reporter.info("继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=_news_available,
            output_dir=prep["output_dir"],
            news_top_count=prep["news_top_count"], include_llm=_enable_llm,
            llm_content=llm_content,
            details=prep["details"], a_indices=prep["a_indices"],
            us_indices=prep["us_indices"],
            news_data=news_data,
            news_llm_meta=news_llm_meta,
            section_order=sec_order,
            early_warnings=_early_warnings, progress=reporter,
            f_context=f_context, history_data=history_data,
            enable_b_series=_enable_b_series,
            enable_news=_enable_news,
            enable_history=_enable_history,
            enable_llm=_enable_llm,
        )
    except Exception as e:
        reporter.add_error("全系列报告生成失败（详情请查看日志文件 logs/app.log）")
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)
