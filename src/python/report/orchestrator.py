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
    from src.python.config import (
        is_enable_fund_deep_analysis,
        is_enable_history,
        is_enable_llm,
        is_enable_news,
        is_enable_portfolio_evolution,
    )

    return {
        "fund_deep_analysis": is_enable_fund_deep_analysis(config),
        "news": is_enable_news(config),
        "history": is_enable_history(config),
        "evolution": is_enable_portfolio_evolution(config),
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

    from src.python.core.data_freshness import build_freshness_summary
    from src.python.core.holding_status import build_coverage_summary
    from src.python.analysis.action_advisor import build_action_data
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.report.market_value import (
        _generate_details,
        classify_holdings,
        get_last_trading_day,
        get_prev_trading_day,
    )
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

    # 因子暴露分析：基金深度分析关闭时为 None（章节隐藏），
    # 开启时计算 C19 dict（数据不足/故障时 available=False，不阻塞主报告）
    factor_exposure = compute_factor_exposure_data(holdings, config, reporter)
    # 持仓相关性矩阵：同因子暴露，基金深度分析关闭时为 None（章节隐藏）
    correlation_data = compute_correlation_data(holdings, config, reporter)
    # 品种覆盖诊断：逐品种标注数据状态，C19 position_status 契约
    coverage_status = build_coverage_summary(holdings, details)
    # 可信度摘要：逐品种新鲜度分类 + 单日 ±20% 跳变检测，C19 data_freshness 契约
    freshness_summary = build_freshness_summary(
        holdings,
        details,
        trading_day=get_last_trading_day(),
        prev_trading_day=get_prev_trading_day(),
    )

    # 行动建议单一数据源：再平衡信号等纯算法产出，C19 action_data 契约
    # （单源计算，20 章行动板块与 14 章行动摘要共享同一对象）
    holdings_details = [
        {
            "name": d.name,
            "code": d.code,
            "market_value": d.market_value,
            "cost": d.cost,
            "profit": d.profit,
            # profit_rate 契约为百分比（小数 ×100，如 1.8712 → 187.12），
            # 供 prompt 格式化（f"{rate:+.2f}%"）与 fact_checker 校验使用；
            # market_value 的 DetailRow.profit_rate 是小数字段，此处统一为百分。
            "profit_rate": (d.profit_rate * 100) if d.profit_rate is not None else None,
            "change_pct": (
                (d.price - d.yesterday_close) / d.yesterday_close * 100
                if d.yesterday_close and abs(d.yesterday_close) > 1e-10
                else 0.0
            ),
            "nav_date": d.nav_date,
            "source_api": d.source_api,
            # shares/price 供调仓建议可行化层计算可执行卖出份额与金额
            "shares": d.shares,
            "price": d.price,
        }
        for d in details
    ]

    # 行动建议：组装 C19 action_data（含再平衡信号；纪律/调仓/归因后续轮次填充）
    action_data = build_action_data(holdings_details, total_mv)

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
        # 因子暴露分析（C19 契约；基金深度分析关闭时为 None）
        "factor_exposure": factor_exposure,
        # 持仓相关性矩阵（C19 契约；基金深度分析关闭时为 None）
        "correlation_data": correlation_data,
        # 品种覆盖诊断（C19 契约 position_status；品种级数据状态标注）
        "position_status": coverage_status,
        # 可信度摘要（C19 契约 data_freshness；新鲜度分类 + 单日跳变检测）
        "data_freshness": freshness_summary,
        # 行动建议单一数据源（C19 契约 action_data；20 章行动板块 + 14 章行动摘要）
        "action_data": action_data,
    }


# ── factor_exposure 编排（因子暴露分析） ──


def _fetch_holding_bars(code: str, name: str, days: int) -> list[dict] | None:
    """按代码类型路由拉取单只持仓历史 K 线（路由口径同 portfolio_history）。

    Args:
        code: 证券代码
        name: 证券名称
        days: 拉取条数

    Returns:
        [{"date", "close"/"nav", ...}, ...] 按日期升序；
        不支持的类型或全链路失败返回 None。
    """
    from src.python.core.code_utils import (
        is_a_share_code,
        is_bond_fund_by_name,
        is_exchange_fund_code,
        is_hk_stock_code,
        is_otc_code_overlap,
        is_otc_fund_by_name,
        is_qdii_extended,
    )
    from src.python.fetcher.chain import fetch_with_incremental_fallback

    code = (code or "").strip()
    name = (name or "").strip()
    if is_exchange_fund_code(code) or is_a_share_code(code):
        bars = fetch_with_incremental_fallback("history_stock", code, days=days)
        # 降级：A 股/OTC 重叠区（00 开头）股票链路空时尝试基金净值链路
        if not bars and is_otc_code_overlap(code):
            bars = fetch_with_incremental_fallback("history_fund_otc", code, days=days)
    elif is_hk_stock_code(code):
        return None
    elif is_qdii_extended(name) or is_bond_fund_by_name(name) or is_otc_fund_by_name(name, code):
        bars = fetch_with_incremental_fallback("history_fund_otc", code, days=days)
    elif len(code) == 6 and code.isdigit():
        bars = fetch_with_incremental_fallback("history_fund_otc", code, days=days)
    else:
        return None
    return bars or None


def compute_factor_exposure_data(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排因子暴露分析并返回 C19 契约 dict。

    流程：拉取组合 as-if 日收益（days=90）+ 因子指数 K 线 + 沪深300 基准
          → 新鲜度剔除 → 对齐 → 纯计算 OLS → C19 dict。

    Args:
        holdings: 持仓列表（Holding 对象，含 code/name/shares）
        config: 完整配置（只读，C14 约束）
        reporter: 进度上报

    Returns:
        C19 契约 dict；基金深度分析关闭时返回 None（章节隐藏）。
        数据不足/故障时 available=False（章节显示降级占位，不阻塞主报告，§1.4.5）。
    """
    from src.python.config import is_enable_fund_deep_analysis

    if not is_enable_fund_deep_analysis(config):
        return None

    from concurrent.futures import ThreadPoolExecutor

    from src.python.analysis.factor_exposure import (
        BASELINE_INDEX,
        DEFAULT_WINDOW,
        FACTOR_INDICES,
        MIN_FACTORS,
        MIN_SAMPLES,
        asif_portfolio_daily_returns,
        compute_factor_exposure,
        filter_stale_factor_klines,
        klines_to_returns,
        unavailable_result,
    )
    from src.python.fetcher.index import fetch_index_history

    today_str = datetime.now().strftime("%Y-%m-%d")
    # 90 条历史：预留对齐/dropna 头部损耗，保证 ≥window(60) 期有效样本
    _days = 90

    try:
        # ── 1. 拉取组合 as-if 日收益（并行） ──
        reporter.info("正在计算因子暴露分析...")
        holdings_bars: dict[str, dict] = {}
        _n = len(holdings)
        with ThreadPoolExecutor(max_workers=min(6, max(1, _n)), thread_name_prefix="orch_factor") as _pool:
            _futs = {_pool.submit(_fetch_holding_bars, h.code, h.name, _days): h for h in holdings}
            for _fut in _futs:
                h = _futs[_fut]
                try:
                    _bars = _fut.result()
                except Exception:
                    _bars = None
                if _bars:
                    holdings_bars[h.code] = {"shares": float(h.shares), "bars": _bars}
        portfolio_returns = asif_portfolio_daily_returns(holdings_bars)
        if not portfolio_returns:
            logger.warning("[factor] 组合历史收益为空，因子暴露数据不足")
            return unavailable_result("insufficient")

        # ── 2. 拉取因子指数 K 线（并行；fetch_index_history 内置 T2 降级记录） ──
        factor_klines: dict[str, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="orch_factor_idx") as _pool:
            _futs = {_pool.submit(fetch_index_history, code, _days): f for f, code in FACTOR_INDICES.items()}
            for _fut in _futs:
                f = _futs[_fut]
                try:
                    factor_klines[f] = _fut.result() or []
                except Exception:
                    factor_klines[f] = []

        # 数据源故障：全部因子拉取为空（区别于数据不足，§1.4.5 ②）
        if all(not bars for bars in factor_klines.values()):
            logger.warning("[factor] 全部因子指数 K 线获取失败，章节降级为数据源暂不可用")
            return unavailable_result("source_failed")

        # ── 3. 新鲜度剔除（停更）+ 空拉取剔除 ──
        empty_factors = [f for f, bars in factor_klines.items() if not bars]
        fresh, stale = filter_stale_factor_klines({f: bars for f, bars in factor_klines.items() if bars}, today_str)
        excluded = sorted(set(empty_factors + stale))
        if len(fresh) < MIN_FACTORS:
            logger.warning("[factor] 有效因子不足 %d（剔除 %s），数据不足", MIN_FACTORS, excluded)
            return unavailable_result("insufficient", stale_factors=excluded)

        # ── 4. 因子收益序列 + 沪深300 基准 ──
        factor_returns = {f: klines_to_returns(fresh[f]) for f in fresh}
        baseline_returns = klines_to_returns(fetch_index_history(BASELINE_INDEX, _days) or [])

        # ── 5. 纯计算 OLS ──
        result = compute_factor_exposure(
            portfolio_returns,
            factor_returns,
            baseline_returns=baseline_returns or None,
            window=DEFAULT_WINDOW,
            min_samples=MIN_SAMPLES,
        )
        if excluded:
            result["stale_factors"] = excluded
        if result.get("available"):
            reporter.ok("因子暴露分析完成")
        else:
            reporter.warn(f"因子暴露数据不足（有效样本 {result.get('sample_count', 0)}）")
        return result
    except Exception:
        logger.exception("[factor] 因子暴露计算异常，章节降级")
        return unavailable_result("source_failed")


def compute_correlation_data(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排持仓相关性矩阵并返回 C19 契约 dict。

    流程：并行拉取各品种历史 K 线（days=90）→ 转日收益 → 纯计算相关矩阵。

    Args:
        holdings: 持仓列表（Holding 对象，含 code/name/shares）
        config: 完整配置（只读，C14 约束）
        reporter: 进度上报

    Returns:
        C19 契约 dict；基金深度分析关闭时返回 None（章节隐藏）。
        数据不足/故障时 available=False（章节显示降级占位，不阻塞主报告，§1.4.5）。
    """
    from src.python.config import is_enable_fund_deep_analysis

    if not is_enable_fund_deep_analysis(config):
        return None

    from concurrent.futures import ThreadPoolExecutor

    from src.python.analysis.correlation import (
        DEFAULT_WINDOW,
        FETCH_DAYS,
        MIN_HOLDINGS,
        MIN_SAMPLES,
        compute_correlation_matrix,
        unavailable_result,
    )
    from src.python.analysis.factor_exposure import klines_to_returns

    try:
        reporter.info("正在计算持仓相关性矩阵...")
        returns_by_code: dict[str, list[dict]] = {}
        _n = len(holdings)
        with ThreadPoolExecutor(max_workers=min(6, max(1, _n)), thread_name_prefix="orch_corr") as _pool:
            _futs = {_pool.submit(_fetch_holding_bars, h.code, h.name, FETCH_DAYS): h for h in holdings}
            for _fut in _futs:
                h = _futs[_fut]
                try:
                    _bars = _fut.result()
                except Exception:
                    _bars = None
                if _bars:
                    _rets = klines_to_returns(_bars)
                    if _rets:
                        returns_by_code[h.code] = _rets

        if len(returns_by_code) < MIN_HOLDINGS:
            logger.warning(
                "[correlation] 有效持仓不足 %d（%d 只），数据不足",
                MIN_HOLDINGS,
                len(returns_by_code),
            )
            return unavailable_result(
                "insufficient",
                sample_count=0,
                insufficient_codes=sorted(returns_by_code.keys()),
            )

        names_by_code = {h.code: h.name for h in holdings}
        result = compute_correlation_matrix(
            returns_by_code,
            names_by_code,
            window=DEFAULT_WINDOW,
            min_samples=MIN_SAMPLES,
        )
        if result.get("available"):
            reporter.ok("持仓相关性矩阵计算完成")
        else:
            reporter.warn(f"持仓相关性数据不足（有效样本 {result.get('sample_count', 0)}）")
        return result
    except Exception:
        logger.exception("[correlation] 相关性矩阵计算异常，章节降级")
        return unavailable_result("source_failed")


# ── generate_report ──


def generate_report(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    report_type: str = "basic",
    fetch_history: bool = False,
    force_llm: bool = False,
    output_dir: str | None = None,
    warm_cache: bool = False,
) -> ReportResult:
    """生成投资分析报告。

    basic: 仅 Excel（无数据准备/快照/历史）
    both:  HTML+Excel（不含 LLM）
    full:  HTML+Excel+LLM

    Args:
        fetch_history: 是否获取组合历史走势数据（as-if 模拟），仅 both/full 有效
    """
    result = ReportResult()

    # 实验性功能状态日志（红色高亮）
    from src.python.config.features import log_experimental_features

    log_experimental_features()

    if report_type == "basic":
        # basic 路径：仅生成 Excel，不调 prepare_report_data / capture_snapshot / fetch_history_data
        from src.python.config import is_enable_data_quality
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
                # 18 章数据质量仪表盘子模块开关（basic 无行情数据，品种覆盖区块显示降级占位）
                enable_data_quality=is_enable_data_quality(config),
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
            fetch_history=fetch_history,
            output_dir=output_dir,
        )

    if report_type == "full":
        from src.python.report._report_generation import _generate_report_full

        return _generate_report_full(
            holdings,
            config,
            reporter,
            fetch_history=fetch_history,
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
