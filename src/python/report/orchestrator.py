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
    指向相同的配置对象，写入会导致跨模块状态污染。
    """
    from concurrent.futures import ThreadPoolExecutor

    from src.python.core.code_utils import is_offsite_fund
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

    # 风格与因子分析：基金深度分析关闭时为 None（章节隐藏），
    # 开启时计算 dict（数据不足/故障时 available=False，不阻塞主报告）。
    # style_factor_data dict 主键（保留全部子键，不重复定义），
    # 内嵌 industry_beta 子键（行业 Beta 子表）。
    factor_exposure = compute_factor_exposure_data(holdings, config, reporter)
    if factor_exposure is not None:
        # 行业 Beta 子表：report_submodules.industry_beta 开关关闭时返回 None（区块隐藏）；
        # 开启但数据不足时 available=False（标题 + 占位，不阻塞本页签其余区块）
        factor_exposure["industry_beta"] = compute_industry_beta_data(holdings, details, config, reporter)
    # 持仓关系矩阵（相关性区块）：同因子暴露，基金深度分析关闭时为 None（章节隐藏）。
    # 数据契约 position_relationship_data——持仓关系矩阵一章两区块（重合度+相关性），
    # 相关性矩阵由编排层注入 pipeline_data；重合度区块为渲染期派生（§8.3）。
    correlation_data = compute_correlation_data(holdings, config, reporter)
    # 品种覆盖诊断：逐品种标注数据状态，position_status数据契约
    coverage_status = build_coverage_summary(holdings, details)
    # 可信度摘要：逐品种新鲜度分类 + 单日 ±20% 跳变检测，data_freshness数据契约
    freshness_summary = build_freshness_summary(
        holdings,
        details,
        trading_day=get_last_trading_day(),
        prev_trading_day=get_prev_trading_day(),
    )

    # 估值分位（数据契约 valuation_data）：report_submodules.valuation_percentile
    # 开启时计算（当前 PE/PB + 价格分位代理）；关闭返回 None（「资产穿透TOP10」列隐藏）
    valuation_data = compute_valuation_data(holdings, details, config, reporter)
    # 市场温度（数据契约 market_temperature_data）：report_submodules.market_temperature
    # 开启时计算（价格分位+均线偏离+波动率三因子温度计）；关闭返回 None（汇总行隐藏）
    market_temperature_data = compute_market_temperature_data(config, reporter)

    # 行动建议单一数据源：再平衡信号等纯算法产出，action_data数据契约
    # （单源计算，行动建议板块与智囊团深度复盘行动摘要共享同一对象）
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
            # 渠道上下文（场内/场外）：按账户关键词判定（is_offsite_fund），
            # 供调仓建议可行化层按渠道计算份额取整与费用（场外整数份+赎回费）；
            # getattr 兼容缺 account 的 detail 对象（测试 fixture 简化版）
            "channel": "场外" if is_offsite_fund(getattr(d, "account", "")) else "场内",
        }
        for d in details
    ]

    # 行动建议：组装 action_data（含再平衡信号；纪律/调仓/归因后续轮次填充）。
    # 此处为「中间占位构建」：组合历史峰值市值需等历史走势就绪（report 层
    # full 路径在 _prepare_full_risk_metrics 后重建），persist_silence=False
    # 使占位构建不读写纪律静默文件，保证最终构建为唯一静默写入方。
    action_data = build_action_data(holdings_details, total_mv, persist_silence=False)

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
        "news_top_count": int(config.get("news_top_count", 300)),
        # 组合风险指标（年化波动率/最大回撤/夏普比率等，需 history_data 计算后填充）
        "risk_metrics": {},
        # 风格与因子分析（数据契约 style_factor_data，内嵌 industry_beta 子键；
        # 基金深度分析关闭时为 None）
        "style_factor_data": factor_exposure,
        # 持仓关系矩阵（数据契约 position_relationship_data——相关性区块；基金深度分析关闭时为 None）
        "position_relationship_data": correlation_data,
        # 品种覆盖诊断（数据契约 position_status；品种级数据状态标注）
        "position_status": coverage_status,
        # 可信度摘要（数据契约 data_freshness；新鲜度分类 + 单日跳变检测）
        "data_freshness": freshness_summary,
        # 行动建议单一数据源（数据契约 action_data；行动建议板块 + 智囊团深度复盘行动摘要）
        "action_data": action_data,
        # 估值分位（数据契约 valuation_data；report_submodules.valuation_percentile 关闭时为 None）
        "valuation_data": valuation_data,
        # 市场温度（数据契约 market_temperature_data；report_submodules.market_temperature 关闭时为 None）
        "market_temperature_data": market_temperature_data,
    }


# ── style_factor_regression 编排（风格因子回归） ──


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
    """编排风格因子回归并返回数据契约 dict。

    流程：拉取组合 as-if 日收益（days=90）+ 因子指数 K 线 + 沪深300 基准
          → 新鲜度剔除 → 对齐 → 纯计算 OLS → dict。

    Args:
        holdings: 持仓列表（Holding 对象，含 code/name/shares）
        config: 完整配置（只读）
        reporter: 进度上报

    Returns:
        数据契约 dict；基金深度分析关闭时返回 None（章节隐藏）。
        数据不足/故障时 available=False（章节显示降级占位，不阻塞主报告，§1.4.5）。
    """
    from src.python.config import is_enable_fund_deep_analysis

    if not is_enable_fund_deep_analysis(config):
        return None

    from concurrent.futures import ThreadPoolExecutor

    from src.python.analysis.style_factor_regression import (
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
        reporter.info("正在计算风格因子回归...")
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
            reporter.ok("风格因子回归完成")
        else:
            reporter.warn(f"因子暴露数据不足（有效样本 {result.get('sample_count', 0)}）")
        return result
    except Exception:
        logger.exception("[factor] 因子暴露计算异常，章节降级")
        return unavailable_result("source_failed")


def compute_industry_beta_data(
    holdings: list,
    details: list,
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排行业 Beta 子表数据（`style_factor_data.industry_beta` 子键）。

    流程：A 股持仓行业分类（push2）→ 按市值加权行业暴露占比
          → 各行业指数 K 线（Chain + session_cache，会话级API复用/Provider Chain 必经）→ 组合 as-if 日收益
          → 纯计算逐行业一元 OLS（复用 style_factor_regression 机制）。

    Args:
        holdings: 持仓列表（Holding 对象，含 code/name/shares）
        details: market_value 计算的 DetailRow 列表（含 code/market_value）
        config: 完整配置（只读）
        reporter: 进度上报

    Returns:
        数据子契约 dict（含 available/status/exposure/betas/...）；
        report_submodules.industry_beta 关闭时返回 None（区块隐藏，不渲染）；
        push2 行业分类 / 指数 K 线不足时 available=False（标题 + 占位，§1.4.5）。
    """
    from src.python.config import is_enable_fund_deep_analysis

    if not is_enable_fund_deep_analysis(config):
        return None
    submodules = config.get("report_submodules") or {}
    if not submodules.get("industry_beta", False):
        return None

    from concurrent.futures import ThreadPoolExecutor

    from src.python.analysis.style_factor_regression import asif_portfolio_daily_returns, klines_to_returns
    from src.python.analysis.industry_beta import (
        INDUSTRY_INDEX_MAP,
        compute_industry_beta_analysis,
        compute_industry_exposure,
        unavailable_result,
    )
    from src.python.core.code_utils import is_a_share_code
    from src.python.fetcher.index import fetch_index_history
    from src.python.fetcher.industry import batch_fetch_industry_data

    _days = 90

    try:
        reporter.info("正在计算行业 Beta 子表...")

        # ── 1. A 股持仓行业分类（push2；batch 并行 + 熔断预检） ──
        a_codes = list(dict.fromkeys(d.code for d in details if is_a_share_code(d.code)))
        industry_map = batch_fetch_industry_data(a_codes) if a_codes else {}

        # ── 2. 行业市值聚合（仅取分类成功且市值 > 0 的持仓） ──
        industry_cap: dict[str, float] = {}
        for d in details:
            ind_info = industry_map.get(d.code)
            ind = (ind_info or {}).get("industry", "")
            if ind and d.market_value and d.market_value > 0:
                industry_cap[ind] = industry_cap.get(ind, 0.0) + float(d.market_value)

        exposure_result = compute_industry_exposure(industry_cap)
        if not exposure_result["available"]:
            reporter.warn("行业 Beta：行业分类（push2）不可用，写入占位")
            return unavailable_result("source_failed")

        # ── 3. 组合 as-if 日收益（并行拉取持仓 K 线） ──
        holdings_bars: dict[str, dict] = {}
        _n = len(holdings)
        with ThreadPoolExecutor(max_workers=min(6, max(1, _n)), thread_name_prefix="orch_ind") as _pool:
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
            logger.warning("[industry_beta] 组合历史收益为空，行业 Beta 数据不足")
            return unavailable_result("insufficient")

        # ── 4. 有暴露且映射行业的指数 K 线（并行） ──
        mapped_industries = sorted(i for i in exposure_result["exposure"] if i in INDUSTRY_INDEX_MAP)
        industry_klines: dict[str, list[dict]] = {}
        if mapped_industries:
            with ThreadPoolExecutor(max_workers=4, thread_name_prefix="orch_ind_idx") as _pool:
                _futs = {_pool.submit(fetch_index_history, INDUSTRY_INDEX_MAP[i], _days): i for i in mapped_industries}
                for _fut in _futs:
                    i = _futs[_fut]
                    try:
                        industry_klines[i] = _fut.result() or []
                    except Exception:
                        industry_klines[i] = []

        # ── 5. 纯计算：逐行业一元 OLS（复用 style_factor_regression 机制） ──
        industry_returns = {i: klines_to_returns(bars) for i, bars in industry_klines.items() if bars}
        result = compute_industry_beta_analysis(portfolio_returns, industry_returns)
        if not result.get("available"):
            reporter.warn("行业 Beta：指数 K 线不足，Beta 子表不渲染")
            result["exposure"] = exposure_result["exposure"]
            return result

        # ── 6. 合并暴露占比 + 指数代码 + 无映射行业 ──
        result["exposure"] = exposure_result["exposure"]
        result["index_codes"] = {i: INDUSTRY_INDEX_MAP[i] for i in result["betas"] if i in INDUSTRY_INDEX_MAP}
        result["unmapped_industries"] = sorted(i for i in exposure_result["exposure"] if i not in INDUSTRY_INDEX_MAP)
        reporter.ok("行业 Beta 子表计算完成")
        return result
    except Exception:
        logger.exception("[industry_beta] 行业 Beta 编排异常，章节子表降级")
        return unavailable_result("source_failed")


def compute_valuation_data(
    holdings: list,
    details: list,
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排估值分位数据（`valuation_data` 数据契约）。

    流程：A 股持仓 → push2 当前 PE/PB（复用既有请求通道 + 会话缓存，
    同一代码同会话不重复请求）→ 历史 K 线价格分位（Chain + session_cache）
    → 三档刻度。PE/PB 与 K 线任一可得即计入该代码，两者皆不可得才剔除。

    Args:
        holdings: 持仓列表（Holding 对象，含 code/name/shares）
        details: market_value 计算的 DetailRow 列表（含 code/market_value）
        config: 完整配置（只读）
        reporter: 进度上报

    Returns:
        数据子契约 dict（含 available/status/by_code）；
        report_submodules.valuation_percentile 关闭时返回 None（列隐藏）；
        push2/K 线均不可用时 available=False（占位，§1.4.5）。
    """
    from src.python.config import is_enable_valuation_percentile

    if not is_enable_valuation_percentile(config):
        return None

    from concurrent.futures import ThreadPoolExecutor

    from src.python.analysis.valuation_percentile import unavailable_valuation
    from src.python.core.code_utils import is_a_share_code

    try:
        reporter.info("正在计算估值分位...")

        # ── 1. 去重 A 股持仓（code+name，供 push2/K 线路由） ──
        pairs = list(dict.fromkeys((d.code, d.name) for d in details if is_a_share_code(d.code)))

        # ── 2. 并行拉取 PE/PB + 价格分位（复用 push2 请求通道 + 会话缓存） ──
        by_code: dict[str, dict] = {}
        if pairs:
            with ThreadPoolExecutor(max_workers=min(6, max(1, len(pairs))), thread_name_prefix="orch_val") as _pool:
                _futs = {_pool.submit(_fetch_valuation_for_code, code, name): code for code, name in pairs}
                for _fut in _futs:
                    code = _futs[_fut]
                    try:
                        _val = _fut.result()
                    except Exception:
                        _val = None
                    if _val:
                        by_code[code] = _val

        if not by_code:
            reporter.warn("估值分位：push2/K 线均不可用，写入占位")
            return unavailable_valuation("source_failed")

        reporter.ok("估值分位计算完成")
        return {"available": True, "status": "ok", "by_code": by_code}
    except Exception:
        logger.exception("[valuation] 估值分位编排异常，章节降级")
        return unavailable_valuation("source_failed")


def _fetch_valuation_for_code(
    code: str,
    name: str,
    days: int = 750,
) -> dict | None:
    """拉取单只 A 股估值字段 + 价格分位（编排层内部辅助，供线程池调用）。

    Args:
        code: 6 位证券代码
        name: 证券名称（供 K 线路由）
        days: 历史 K 线回看天数（默认 750 ≈ 3 年）

    Returns:
        单代码估值子契约 dict；PE/PB 与价格分位皆不可得返回 None。
    """
    from src.python.analysis.valuation_percentile import compute_price_percentile
    from src.python.providers.eastmoney_industry import fetch_valuation_fields

    pe_pb = fetch_valuation_fields(code)
    bars = _fetch_holding_bars(code, name, days) or []
    pct = compute_price_percentile(bars)
    if not pe_pb and not pct.get("available"):
        return None
    return {
        "pe": (pe_pb or {}).get("pe"),
        "pb": (pe_pb or {}).get("pb"),
        "price_percentile": pct.get("price_percentile"),
        "tier": pct.get("tier"),
        "sample_count": pct.get("sample_count", 0),
        "percentile_available": bool(pct.get("available")),
    }


def compute_market_temperature_data(
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排市场温度数据（`market_temperature_data` 数据契约）。

    流程：沪深300 指数历史 K 线（Chain + session_cache，腾讯→新浪自动降级，
    复用既有 history_index 降级链）→ 三因子合成温度计（价格分位+均线偏离+波动率）。

    Args:
        config: 完整配置（只读）
        reporter: 进度上报

    Returns:
        数据子契约 dict（含 available/status/score/tier/disclaimer）；
        report_submodules.market_temperature 关闭时返回 None（行隐藏）；
        指数 K 线不足时 available=False（占位，§1.4.5）。
    """
    from src.python.config import is_enable_market_temperature

    if not is_enable_market_temperature(config):
        return None

    from src.python.analysis.market_temperature import (
        DEFAULT_INDEX_CODE,
        DEFAULT_INDEX_NAME,
        DEFAULT_LOOKBACK_DAYS,
        TEMPERATURE_DISCLAIMER,
        compute_temperature,
        unavailable_temperature,
    )
    from src.python.fetcher.index import fetch_index_history

    try:
        reporter.info("正在计算市场温度...")
        bars = fetch_index_history(DEFAULT_INDEX_CODE, DEFAULT_LOOKBACK_DAYS) or []
        result = compute_temperature(bars)
        if not result.get("available"):
            reporter.warn("市场温度：指数 K 线不足，写入占位")
            return unavailable_temperature("insufficient")

        result["status"] = "ok"
        result["index_code"] = DEFAULT_INDEX_CODE
        result["index_name"] = DEFAULT_INDEX_NAME
        result["disclaimer"] = TEMPERATURE_DISCLAIMER
        reporter.ok("市场温度计算完成")
        return result
    except Exception:
        logger.exception("[temperature] 市场温度编排异常，章节降级")
        return unavailable_temperature("source_failed")


def compute_correlation_data(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
) -> dict | None:
    """编排持仓相关性矩阵并返回数据契约 dict（持仓关系矩阵相关性区块）。

    流程：并行拉取各品种历史 K 线（days=90）→ 转日收益 → 纯计算相关矩阵。

    Args:
        holdings: 持仓列表（Holding 对象，含 code/name/shares）
        config: 完整配置（只读）
        reporter: 进度上报

    Returns:
        数据契约 dict；基金深度分析关闭时返回 None（章节隐藏）。
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
    from src.python.analysis.style_factor_regression import klines_to_returns

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
    transactions: list | None = None,
    dividends: list | None = None,
) -> ReportResult:
    """生成投资分析报告。

    basic: 仅 Excel（无数据准备/快照/历史）
    both:  HTML+Excel（不含 LLM）
    full:  HTML+Excel+LLM

    Args:
        fetch_history: 是否获取组合历史走势数据（as-if 模拟），仅 both/full 有效
        transactions: 交易流水记录（「交易流水」页签，无则 None）。
            成本流水子模块（report_submodules.cost_lots）开启时用于成本分档 + XIRR
        dividends: 分红流水记录（「分红流水」页签，无则 None）。
            成本流水子模块开启时用于分红累计 + XIRR
    """
    result = ReportResult()

    # 实验性功能状态日志（红色高亮）
    from src.python.config.features import log_experimental_features

    log_experimental_features()

    if report_type == "basic":
        # basic 路径：仅生成 Excel，不调 prepare_report_data / capture_snapshot / fetch_history_data
        from src.python.config import is_enable_cost_lots, is_enable_data_quality
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
                # 数据质量仪表盘子模块开关（basic 无行情数据，品种覆盖区块显示降级占位）
                enable_data_quality=is_enable_data_quality(config),
                # 成本流水子模块开关 + 交易/分红流水（汇总/市值/分类页签渲染成本分档 + XIRR + 分红累计）
                enable_cost_lots=is_enable_cost_lots(config),
                transactions=transactions,
                dividends=dividends,
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
            transactions=transactions,
            dividends=dividends,
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
            transactions=transactions,
            dividends=dividends,
        )

    result.report_generated = True
    reporter.info("generate_report: 骨架模式—未知 report_type")
    return result
