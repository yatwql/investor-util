"""报告编排风格因子计算子模块 — 持仓 K 线路由 + 风格因子回归 + 行业 Beta。

承载数据准备族中与风格因子 / 行业 Beta 相关的编排实现：持仓历史 K 线按代码
类型路由、风格因子回归数据契约装配、行业 Beta 子表数据契约装配。

由 `orchestrator.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.python.report.progress import ProgressReporter

logger = logging.getLogger("invest")


# ── 持仓历史 K 线路由 ──


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


# ── 风格因子回归 编排 ──


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
