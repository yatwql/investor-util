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
    """从 config 读取板块可见性开关，返回统一字典。"""
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


# ── capture_snapshot ──


def capture_snapshot(
    holdings: list,
    details: list,
    config: dict | None,
    reporter: ProgressReporter,
    **extra: Any,
) -> dict | None:
    """F1 持仓快照创建 + 差异计算 + 保存 + 清理。

    Args:
        holdings: 持仓列表
        details: 行情明细
        config: 配置字典
        reporter: 进度报告接口
        extra: 额外扩展字段（如 risk_metrics），透传到 pipeline_data

    Returns:
        pipeline_data 字典（含 diff），首次运行或异常时返回 None。
    """
    from src.python.fetcher.history_diff import HistoryDiff
    from src.python.report.data_status import get_tracker as _get_degradation_tracker
    from src.python.report.history_snapshot import load_latest, save
    from src.python.schemas.history import (
        AccountSnapshot,
        SnapshotData,
        SnapshotHolding,
    )

    pipeline_data: dict | None = None
    try:
        _snapshot_holdings = [
            SnapshotHolding(
                code=d.code,
                name=getattr(d, "name", ""),
                shares=0.0,
                cost_price=0.0,
                market_value=d.market_value,
                total_pnl=d.profit,
                cost_total=d.cost,
            )
            for d in details
        ]
        for h in _snapshot_holdings:
            _orig = next((x for x in holdings if x.code == h.code), None)
            if _orig:
                object.__setattr__(h, "shares", _orig.shares)
                object.__setattr__(h, "cost_price", _orig.cost_price)
        _snapshot = SnapshotData(
            accounts=(AccountSnapshot(account_name="全部", holdings=tuple(_snapshot_holdings)),),
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
            pipeline_data = {
                "diff": {
                    "is_first_check": False,
                    "total_value_diff": _diff.total_value_diff,
                    "total_value_diff_pct": _diff.total_value_diff_pct,
                    "total_pnl_diff": _diff.total_pnl_diff,
                    "days_since_last_report": _diff.days_since_last_report,
                    "added": [
                        {
                            "name": a.name,
                            "code": a.code,
                            "action": a.action,
                            "shares_diff": a.shares_diff,
                            "value_diff": a.value_diff,
                        }
                        for a in _diff.added
                    ],
                    "removed": [
                        {
                            "name": r.name,
                            "code": r.code,
                            "action": r.action,
                            "shares_diff": r.shares_diff,
                            "value_diff": r.value_diff,
                        }
                        for r in _diff.removed
                    ],
                    "increased": [
                        {
                            "name": i.name,
                            "code": i.code,
                            "action": i.action,
                            "shares_diff": i.shares_diff,
                            "value_diff": i.value_diff,
                        }
                        for i in _diff.increased
                    ],
                    "decreased": [
                        {
                            "name": d.name,
                            "code": d.code,
                            "action": d.action,
                            "shares_diff": d.shares_diff,
                            "value_diff": d.value_diff,
                        }
                        for d in _diff.decreased
                    ],
                },
                "data_degradation": _get_degradation_tracker().get_log(),
            }
            # 透传额外扩展字段（risk_metrics / portfolio_daily_returns）
            if extra:
                pipeline_data.update(extra)
        reporter.ok("环比对比数据准备完成")
    except Exception:
        logger.info("[F1] 环比数据准备跳过（首次运行或异常）", exc_info=True)
    return pipeline_data


# ── fetch_history_data ──


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
    from src.python.features import log_experimental_features

    log_experimental_features()

    if report_type == "basic":
        # basic 路径：仅生成 Excel，不调 prepare_report_data / capture_snapshot / fetch_history_data
        from src.python.registry import get_report_section_order
        from src.python.report.excel_generator import generate_excel_report

        sec_order = get_report_section_order(config)
        output = output_dir or config.get("output_dir", "reports")

        try:
            generate_excel_report(
                holdings,
                include_news=False,
                output_dir=output,
                section_order=sec_order,
                progress=reporter,
            )
            result.excel_ok = True
            result.holdings_ok = True
            result.report_generated = True
        except Exception:
            reporter.add_error("Excel 报告生成失败（详情请查看日志文件 logs/app.log）")
            logger.exception("生成 Excel 报告失败")
            result.errors.append("Excel 报告生成失败")

        return result

    if report_type == "both":
        return _generate_report_both(
            holdings,
            config,
            reporter,
            history_mode=history_mode,
            output_dir=output_dir,
        )

    if report_type == "full":
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


# ── _compute_details（轻量级行情获取，无指数/穿透/分类）──


def _compute_details(holdings: list, config: dict, reporter: ProgressReporter) -> list:
    """轻量级行情获取，供 both 路径使用。

    仅获取行情明细，不获取指数/穿透/分类数据（与 _cmd_generate_both 语义对齐）。
    """
    from src.python.report.market_value import _generate_details

    reporter.info("正在获取行情数据...")
    details = _generate_details(holdings)
    reporter.ok(f"行情数据获取完成，共 {len(details)} 条")
    return details


# ── _generate_report_both（生成 HTML+Excel，不含 LLM）──


def _generate_report_both(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    history_mode: str = "off",
    output_dir: str | None = None,
) -> ReportResult:
    """both 报告路径：生成 HTML + Excel，不含 LLM 分析章节。

    流程：_compute_details() → capture_snapshot() → fetch_history_data()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import is_enable_b_series, is_enable_history, is_enable_news
    from src.python.registry import get_report_section_order
    from src.python.report.excel_generator import generate_excel_report
    from src.python.report.html_writer import write_html_report

    result = ReportResult()
    result.holdings_ok = True

    _enable_b_series = is_enable_b_series(config)
    _enable_news = is_enable_news(config)
    _enable_history = is_enable_history(config)
    sec_order = get_report_section_order(config)
    output = output_dir or config.get("output_dir", "reports")
    news_top_count = int(config.get("news_top_count", 100))

    # ── 1. 行情获取（轻量级，无指数/穿透/分类） ──
    details = _compute_details(holdings, config, reporter)

    # ── 2. F1 快照对比（始终执行） ──
    pipeline_data = capture_snapshot(holdings, details, config, reporter)
    # [checkpoint] pipeline_data 类型断言
    if pipeline_data is not None:
        assert isinstance(pipeline_data, dict), "capture_snapshot(both) pipeline_data 类型异常"
        _diff = pipeline_data.get("diff")
        if _diff is not None and not isinstance(_diff, dict):
            logger.warning("[checkpoint] pipeline_data.diff 类型异常(both): %s", type(_diff).__name__)

    # ── 3. F2 历史走势（条件获取） ──
    if _enable_history:
        _resolved_mode = "auto" if history_mode in ("auto",) else "off"
        history_data = fetch_history_data(holdings, config, reporter, mode=_resolved_mode)
    else:
        history_data = None
        reporter.info("[板块配置] 历史走势已关闭，跳过")

    # ── 4. HTML 报告 ──
    _news_label = "含新闻" if _enable_news else "无新闻"
    reporter.info(f"正在生成 HTML 报告（{_news_label}）...")
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
            enable_b_series=_enable_b_series,
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

    # ── 5. Excel 报告 ──
    reporter.info("正在生成 Excel 报告...")
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
            enable_b_series=_enable_b_series,
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

    result.report_generated = result.html_ok or result.excel_ok
    return result


# ── _report_llm_module_results（统一的 LLM 模块结果计数/报告）──


def _report_llm_module_results(
    results: tuple,
    cached_flags: tuple[bool, bool, bool, bool],
    reporter: ProgressReporter,
) -> None:
    """统一的 LLM 模块结果报告逻辑。"""
    from src.python.llm import FAIL_REASON_DISABLED
    from src.python.llm.prompts import LLM_MODULE_FAILURE
    from src.python.registry import get_llm_module_name
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


# ── _fetch_llm_and_news（统一 4 分支）──


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

    内部管理线程池（max_workers=2，operations 池唯一存在）。
    LLM 和新闻的 ok/disabled/failed 计数统一归入此函数。

    Args:
        history_data: 组合历史走势数据，传递给 generate_all_llm。
        comparison_indices: {代码: 名称} 对比指数池，传递给 generate_all_llm。

    Returns:
        (llm_content, news_data, news_llm_meta, news_ok, debate_info)
        llm_content: (global_macro_html, expert_review_html, health_check_html, penetration_deep_html)
        debate_info: dict | None — 辩论模式启用时包含 pro_text/con_text/mode_label
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from src.python.llm import generate_all_llm
    from src.python.report.news_correlation import build_news_data

    llm_content: tuple = (None, None, None, None)
    news_data: list = []
    news_llm_meta: dict = {}
    news_ok: bool = False
    debate_info: dict | None = None

    # 分支 ④：均关闭
    if not enable_llm and not enable_news:
        reporter.info("[板块配置] 新闻和 LLM 均未开启，跳过内容生成")
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
            reporter.info("[板块配置] 新闻板块已关闭，跳过新闻获取")

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
            reporter.info("[板块配置] LLM 板块已关闭，跳过 LLM 内容生成")

        if _llm_fut is not None and _news_fut is not None:
            # 分支 ①：LLM + 新闻均开启（并行等待）
            for fut in as_completed([_news_fut, _llm_fut]):
                if fut is _llm_fut:
                    try:
                        _result = _llm_fut.result()
                        llm_content = _result[:4]
                        _cached = _result[4:8]
                        _report_llm_module_results(llm_content, _cached, reporter)
                        debate_info = _result[8] if len(_result) > 8 else None
                    except Exception:
                        reporter.add_error("LLM 内容生成异常（详情请查看日志文件 logs/app.log）")
                        reporter.error("LLM 内容生成异常（详情请查看日志）")
                else:
                    try:
                        news_data, news_llm_meta = _news_fut.result()
                        reporter.ok(f"新闻获取完成，共 {len(news_data)} 条")
                        news_ok = bool(news_data)
                    except Exception:
                        reporter.add_error("新闻获取异常（详情请查看日志文件 logs/app.log）")
                        reporter.warn("新闻获取异常（详情请查看日志）")
        elif _news_fut is not None:
            # 分支 ②：仅新闻
            try:
                news_data, news_llm_meta = _news_fut.result()
                news_ok = bool(news_data)
                reporter.ok(f"新闻获取完成，共 {len(news_data)} 条")
            except Exception:
                reporter.add_error("新闻获取异常（详情请查看日志）")
        elif _llm_fut is not None:
            # 分支 ③：仅 LLM
            try:
                _result = _llm_fut.result()
                llm_content = _result[:4]
                _cached = _result[4:8]
                _report_llm_module_results(llm_content, _cached, reporter)
                debate_info = _result[8] if len(_result) > 8 else None
            except Exception:
                reporter.add_error("LLM 内容生成异常（详情请查看日志）")
                reporter.error("LLM 内容生成异常（详情请查看日志）")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return llm_content, news_data, news_llm_meta, news_ok, debate_info


# ── _generate_report_full（HTML+Excel+LLM）──


def _generate_report_full(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    history_mode: str = "off",
    force_llm: bool = False,
    output_dir: str | None = None,
) -> ReportResult:
    """full 报告路径：生成 HTML + Excel + LLM 分析章节。

    流程：prepare_report_data() → capture_snapshot() → fetch_history_data()
          → get_sector_fund_flow() → _fetch_llm_and_news()
          → write_html_report() → generate_excel_report()
    """
    from src.python.config import is_enable_b_series, is_enable_history, is_enable_llm, is_enable_news
    from src.python.fetcher.akshare import get_sector_fund_flow
    from src.python.registry import get_report_section_order
    from src.python.report.excel_generator import generate_excel_report
    from src.python.report.html_writer import write_html_report

    result = ReportResult()
    result.holdings_ok = True

    _enable_b_series = is_enable_b_series(config)
    _enable_news = is_enable_news(config)
    _enable_history = is_enable_history(config)
    _enable_llm = is_enable_llm(config)
    sec_order = get_report_section_order(config)

    # ── 1. 完整数据准备（含指数/穿透/分类） ──
    prep = prepare_report_data(holdings, reporter, config)
    # [checkpoint] prep 类型断言
    assert isinstance(prep, dict), "prepare_report_data 返回类型异常"
    for _ck in ("total_mv", "total_cost", "total_profit", "total_today_profit", "categories",
                 "a_indices", "holdings_details", "today_str", "output_dir", "news_top_count", "risk_metrics"):
        if _ck not in prep:
            logger.warning("[checkpoint] prep 缺失必选键: %s", _ck)
        elif not isinstance(prep.get(_ck), (int, float, dict, list, str, type(None))):
            logger.warning("[checkpoint] prep.%s 类型异常: %s", _ck, type(prep.get(_ck)).__name__)

    # ── 2. F1 快照对比 ──
    pipeline_data = capture_snapshot(holdings, prep["details"], config, reporter)
    # [checkpoint] pipeline_data 类型断言
    if pipeline_data is not None:
        assert isinstance(pipeline_data, dict), "capture_snapshot pipeline_data 类型异常"
        _diff = pipeline_data.get("diff")
        if _diff is not None:
            if not isinstance(_diff, dict):
                logger.warning("[checkpoint] pipeline_data.diff 类型异常: %s", type(_diff).__name__)

    # ── 3. F2 历史走势（条件获取） ──
    if _enable_history:
        _resolved_mode = "auto" if history_mode in ("auto",) else "off"
        history_data = fetch_history_data(holdings, config, reporter, mode=_resolved_mode)
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
        _daily_returns = history_data.get("daily_returns_portfolio", [])
        if _daily_returns:
            from src.python.analysis.metrics import compute_all_metrics
            from src.python.analysis.alignment_correction import compute_alignment_factors

            _holdings_details = prep.get("holdings_details", [])
            _total_mv = prep.get("total_mv", 0)

            # 组合市值权重
            _portfolio_weights = (
                [h["market_value"] / _total_mv for h in _holdings_details
                 if _total_mv > 0 and h.get("market_value", 0) > 0]
                or None
            )

            # 全量量化指标（14 项：夏普/卡玛/HHI/胜率/换手率/Beta CI/风险贡献）
            _metrics = compute_all_metrics(
                portfolio_daily_returns=_daily_returns,
                portfolio_weights=_portfolio_weights,
                benchmark_daily_returns=None,  # 暂无可对齐的基准日收益率序列
                holdings_details=_holdings_details,
                rf_annual=0.02,
            )
            # 补充竞争语境需要但 compute_all_metrics 不产的字段
            _mdd_pct = history_data.get("max_drawdown_pct", 0)
            _metrics["annualized_volatility"] = history_data.get("annualized_volatility")
            _metrics["max_drawdown"] = -(_mdd_pct / 100) if _mdd_pct else None

            # 口径修正因子（费率估算 + 现金剥离 + TWR）
            _alignment = compute_alignment_factors(
                holdings_details=_holdings_details,
                total_mv=_total_mv,
                portfolio_daily_returns=_daily_returns,
            )
            if _alignment.get("has_any_data"):
                _metrics["alignment_summary"] = _alignment.get("summary_text", "")

            # 情景分析（基于 Beta 置信区间传播）
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
                    portfolio_volatility=history_data.get("annualized_volatility"),
                )
                if _scenario.get("has_data") and _scenario.get("scenarios"):
                    _metrics["scenario_analysis"] = _scenario
        else:
            _metrics = None
    else:
        _metrics = None
        history_data = None
        reporter.info("[板块配置] 历史走势已关闭，跳过")

    # ── 4. 行业资金流向 ──
    reporter.info("正在获取行业资金流向...")
    try:
        sector_flow = get_sector_fund_flow()
        if sector_flow:
            reporter.ok("行业资金流向获取完成")
    except Exception:
        sector_flow = None
        reporter.warn("行业资金流向获取失败，将继续生成报告")

    # ── 5. 并行获取 LLM + 新闻（4 分支统一处理） ──
    # 读取对比指数池配置（默认预设池在 _config_defaults.py 中定义）
    _comparison_indices = config.get("comparison_indices", None)
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

    # LLM 全部失败时自动降级使用占位文本
    if _enable_llm:
        from src.python.llm.fallback import build_fallback_llm_content

        llm_content = build_fallback_llm_content(llm_content)
        if all(c is not None for c in llm_content[:4]):
            result.llm_ok = True

    # ── 6. HTML 报告 ──
    _report_label = "含新闻 + LLM" if news_ok else "仅 LLM"
    reporter.info(f"正在生成 HTML 报告（{_report_label}分析章节）...")
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
            enable_b_series=_enable_b_series,
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

    # ── 8. Excel 报告 ──
    reporter.info("正在生成 Excel 报告...")
    try:
        generate_excel_report(
            holdings,
            include_news=news_ok,
            output_dir=output_dir or prep["output_dir"],
            news_top_count=prep["news_top_count"],
            include_llm=_enable_llm,
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
            enable_b_series=_enable_b_series,
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

    result.news_ok = news_ok
    result.report_generated = result.html_ok or result.excel_ok
    return result
