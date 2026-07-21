"""缓存操作共享层 — TUI 和 CLI 共用。

公共缓存函数（盈利预测/行业资金流向/行业/分红）+ print→reporter 替换
持仓缓存（价格+指数）+ 清理 + 统计
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import src.python.logger as _logger_mod

logger = _logger_mod.setup_logger()


# ── 数据结构 ───────────────────────────────────────────────


@dataclass
class CacheUpdateResult:
    """基础缓存更新结果。"""

    total_funds: int = 0
    perf_ok: int = 0
    hold_ok: int = 0
    bm_ok: int = 0
    pf_ok: int = 0
    sf_ok: int = 0
    ind_ok: int = 0
    div_ok: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.total_funds == 0 and self.pf_ok == 0 and self.sf_ok == 0:
            return 2
        if self.errors:
            return 1
        return 0


@dataclass
class PositionCacheResult:
    """持仓缓存更新结果。"""

    total: int = 0
    price_ok: int = 0
    a_index_count: int = 0
    us_index_count: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.total == 0:
            return 2
        if self.errors:
            return 1
        return 0


@dataclass
class CacheStats:
    """缓存统计信息。"""

    total_files: int = 0
    total_size_bytes: int = 0
    expired: int = 0
    hit_rate: float = 0.0
    hit_total: int = 0
    by_prefix: dict[str, int] = field(default_factory=dict)
    top_by_size: list[tuple[str, int]] = field(default_factory=list)
    # 快照目录
    snapshot_files: int = 0
    snapshot_size_bytes: int = 0
    # 运行时状态
    state_files: int = 0
    state_size_bytes: int = 0


# ── 内部线程池（仅 operations 内部使用）──

_POOL: ThreadPoolExecutor | None = None


def _get_pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cache_ops")
    return _POOL


# ═══════════════════════════════════════════════════════════════
# 基金刷新
# ═══════════════════════════════════════════════════════════════


def _refresh_one_fund_cache(fund) -> tuple:
    """刷新单只基金的排名、持仓和基准缓存。"""
    from src.python.fetcher.fund import fetch_fund_benchmark, fetch_fund_holdings, fetch_fund_rankings

    perf_result = fetch_fund_rankings(fund.code)
    perf_ok = bool(perf_result)
    hold_data = fetch_fund_holdings(fund.code)
    hold_ok = bool(hold_data and hold_data.get("holdings"))
    hold_count = len(hold_data["holdings"]) if hold_data and hold_data.get("holdings") else 0
    bm = fetch_fund_benchmark(fund.code)
    bm_ok = bool(bm and bm != "--")
    return ("fund", fund.code, fund.name, perf_ok, hold_ok, hold_count, bm_ok)


# ═══════════════════════════════════════════════════════════════
# 公共缓存函数
# ═══════════════════════════════════════════════════════════════


def _refresh_industry_cache(holdings: list) -> int:
    """刷新行业分类缓存。"""
    from src.python.fetcher.industry import batch_fetch_industry_data

    codes = [h.code.strip() for h in holdings if h.code and h.code.strip()]
    if not codes:
        return 0
    result = batch_fetch_industry_data(codes)
    return len(result)


def _refresh_dividend_cache(holdings: list) -> int:
    """刷新股票历史分红缓存。"""
    from src.python.fetcher.akshare import get_dividend_data

    codes = [h.code.strip() for h in holdings if h.code and h.code.strip()]
    if not codes:
        return 0
    result = get_dividend_data(codes)
    return len(result)


def _refresh_profit_forecast_cache() -> tuple[str, int]:
    """刷新盈利预测缓存。"""
    from src.python.fetcher.akshare import get_profit_forecast

    data = get_profit_forecast()
    return ("profit_forecast", len(data) if data else 0)


def _refresh_sector_flow_cache() -> tuple[str, int]:
    """刷新行业资金流向缓存。"""
    from src.python.fetcher.akshare import get_sector_fund_flow

    data = get_sector_fund_flow()
    return ("sector_flow", len(data) if data else 0)


def _sector_flow_hint() -> str:
    """根据最近一次行业资金流向失败类型返回提示文案。"""
    from src.python.fetcher.akshare import get_sector_fund_flow  # noqa: F401  # 保持 fetcher 层活跃引用
    from src.python.providers.akshare_extras import _SECTOR_FLOW_FAILURE

    if _SECTOR_FLOW_FAILURE == "connection":
        return "连接失败"
    if _SECTOR_FLOW_FAILURE == "empty":
        return "暂无数据"
    return "获取失败"


# ═══════════════════════════════════════════════════════════════
# 公共缓存并行刷新（print→reporter 替换）
# ═══════════════════════════════════════════════════════════════


def _refresh_common_caches(
    holdings: list | None,
    reporter,
) -> tuple[int, int, int, int]:
    """刷新不依赖基金持仓的公共缓存，通过 reporter.* 输出进度。

    Args:
        holdings: 可选持仓列表，提供时额外刷新行业和分红。
        reporter: 进度报告接口。

    Returns:
        (pf_ok, sf_ok, ind_ok, div_ok)
    """
    pf_ok = sf_ok = ind_ok = div_ok = 0
    pool = _get_pool()

    f1 = pool.submit(_refresh_profit_forecast_cache)
    f2 = pool.submit(_refresh_sector_flow_cache)
    futs: list[tuple[ThreadPoolExecutor, str, str]] = [
        (f1, "profit_forecast", "盈利预测"),
        (f2, "sector_flow", "行业资金流向"),
    ]
    if holdings:
        f3 = pool.submit(_refresh_industry_cache, holdings)
        f4 = pool.submit(_refresh_dividend_cache, holdings)
        futs.extend(
            [
                (f3, "industry", "行业分类"),
                (f4, "dividend", "分红数据"),
            ]
        )

    for fut, tag, label in futs:
        try:
            if tag == "profit_forecast":
                _, pf_ok = fut.result()
                if pf_ok:
                    reporter.ok(f"盈利预测 ({pf_ok} 只股票)")
                else:
                    reporter.warn("盈利预测 获取失败")
            elif tag == "sector_flow":
                sf_ok = fut.result()[1]
                if sf_ok:
                    reporter.ok(f"行业资金流向 ({sf_ok} 个行业)")
                else:
                    reporter.warn(f"行业资金流向 {_sector_flow_hint()}")
            elif tag == "industry":
                ind_ok = fut.result()
                if ind_ok:
                    reporter.ok(f"行业分类 ({ind_ok} 只证券)")
                else:
                    reporter.warn("行业分类 获取失败")
            elif tag == "dividend":
                div_ok = fut.result()
                if div_ok:
                    reporter.ok(f"分红数据 ({div_ok} 只股票)")
                else:
                    reporter.warn("分红数据 获取失败")
        except Exception as e:
            logger.debug("%s Future 异常: %s", tag, e)
            reporter.warn(f"{label} 获取失败")

    return pf_ok, sf_ok, ind_ok, div_ok


# ═══════════════════════════════════════════════════════════════
# update_basic_cache（基金 + 公共缓存）
# ═══════════════════════════════════════════════════════════════


def update_basic_cache(holdings: list, reporter) -> CacheUpdateResult:
    """更新基础类缓存（基金业绩+持仓+基准 + 公共缓存）。

    内部管理线程池，operations 池唯一存在。
    基金刷新 + 公共缓存并行获取。

    Args:
        holdings: 持仓列表
        reporter: 进度报告接口

    Returns:
        CacheUpdateResult — TUI 外壳可据此输出格式化结果
    """
    from src.python.cache import clear_by_group

    result = CacheUpdateResult()

    # 先清旧缓存（匹配 TUI 语义）
    clear_by_group("refresh")

    from src.python.report.fund_performance import is_fund

    funds = [h for h in holdings if is_fund(h)]
    result.total_funds = len(funds)

    pool = _get_pool()

    if not funds:
        # 无基金：仅刷新公共缓存
        result.pf_ok, result.sf_ok, result.ind_ok, result.div_ok = _refresh_common_caches(holdings, reporter)
        return result

    # 有基金：所有任务并行提交
    reporter.info("正在并行获取全部缓存数据...")
    all_futures: dict = {}
    for f in funds:
        all_futures[pool.submit(_refresh_one_fund_cache, f)] = ("fund", f)
    all_futures[pool.submit(_refresh_profit_forecast_cache)] = ("other", None)
    all_futures[pool.submit(_refresh_sector_flow_cache)] = ("other", None)

    for future in as_completed(all_futures):
        tag, _ = all_futures[future]
        try:
            res = future.result()
            if tag == "fund":
                _, code, name, p_ok, h_ok, h_cnt, b_ok = res
                if p_ok:
                    result.perf_ok += 1
                if h_ok:
                    result.hold_ok += 1
                if b_ok:
                    result.bm_ok += 1
                reporter.ok(
                    f"{name} ({code}) — 业绩={'OK' if p_ok else '失败'} | "
                    f"持仓={h_cnt}条 | 基准={'OK' if b_ok else '未找到'}"
                )
            elif res[0] == "profit_forecast":
                result.pf_ok = res[1]
                if result.pf_ok:
                    reporter.ok(f"盈利预测 ({result.pf_ok} 只股票)")
                else:
                    reporter.warn("盈利预测 获取失败")
            elif res[0] == "sector_flow":
                result.sf_ok = res[1]
                if result.sf_ok:
                    reporter.ok(f"行业资金流向 ({result.sf_ok} 个行业)")
                else:
                    reporter.warn(f"行业资金流向 {_sector_flow_hint()}")
        except Exception as e:
            logger.debug("缓存刷新 Future 异常: %s", e)
            result.errors.append(f"缓存刷新异常: {e}")
            reporter.warn("基金刷新异常" if tag == "fund" else "其他缓存刷新异常")

    return result


# ═══════════════════════════════════════════════════════════════
# 持仓缓存（价格+指数）
# ═══════════════════════════════════════════════════════════════


def _fetch_prices_and_indices(holdings: list, reporter) -> PositionCacheResult:
    """并行获取持仓价格 + 市场指数，通过 reporter.* 输出进度。

    内部管理线程池，operations 池唯一存在。
    """
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.fetcher.price import fetch_market_data

    result = PositionCacheResult(total=len(holdings))
    pool = _get_pool()
    fut_map: dict = {}

    for h in holdings:
        fut_map[pool.submit(fetch_market_data, h.code, h.name)] = h
    idx_a_fut = pool.submit(fetch_indices)
    idx_us_fut = pool.submit(fetch_us_indices)
    fut_map[idx_a_fut] = None
    fut_map[idx_us_fut] = None

    for future in as_completed(fut_map):
        h_or_none = fut_map[future]
        try:
            if h_or_none is None:
                idx_res = future.result() or {}
                if future is idx_a_fut:
                    result.a_index_count = len(idx_res)
                    reporter.ok(f"A 股指数: {result.a_index_count} 个")
                else:
                    result.us_index_count = len(idx_res)
                    reporter.ok(f"美股指数: {result.us_index_count} 个")
            else:
                h = h_or_none
                price_res = future.result()
                if price_res and price_res.get("price", 0) > 0:
                    result.price_ok += 1
                    reporter.ok(f"{h.name} ({h.code}) → {price_res['price']:.4f}")
                else:
                    reporter.warn(f"{h.name} ({h.code}) → 失败")
        except Exception as e:
            if h_or_none is not None:
                _msg = str(e)
                if any(kw in _msg.lower() for kw in ("connect", "timeout", "network", "reset")):
                    _hint = "网络异常"
                elif "parse" in _msg.lower() or "decode" in _msg.lower():
                    _hint = "数据解析失败"
                else:
                    _hint = "获取失败"
                reporter.error(f"{h_or_none.name} ({h_or_none.code}) → {_hint}")
                result.errors.append(f"{h_or_none.name}: {_hint}")

    return result


def update_position_cache(holdings: list, reporter) -> PositionCacheResult:
    """更新持仓类缓存（价格+指数）。

    内部管理线程池，使用 reporter.* 输出进度。
    """
    from src.python.cache import clear_by_group

    clear_by_group("preload")
    reporter.info("正在并行获取持仓价格/净值 + 市场指数...")
    return _fetch_prices_and_indices(holdings, reporter)


# ═══════════════════════════════════════════════════════════════
# 缓存清理 + 统计
# ═══════════════════════════════════════════════════════════════


def cleanup_cache(reporter) -> int:
    """清理过期缓存文件。

    Returns:
        清理的文件数量
    """
    from src.python.cache import cleanup_expired, get_cache_dir

    reporter.info("正在扫描缓存目录...")
    removed = cleanup_expired(dry_run=False)
    cache_dir = get_cache_dir()
    if removed > 0:
        reporter.ok(f"已删除 {removed} 个过期缓存文件 ({cache_dir})")
    else:
        reporter.info(f"无需清理 ({cache_dir})")
    return removed


def get_cache_stats(reporter) -> CacheStats:
    """返回缓存统计信息，无 print 格式化。

    扫描 data/cache、data/history/snapshots、data/state 三个目录。
    """
    from src.python.cache import (
        cleanup_expired,
        get_cache_dir,
        get_cache_hit_rate,
    )
    from src.python.cache import (
        get_cache_stats as _get_cache_stats,
    )
    from src.python.constants import PROJECT_ROOT

    stats = CacheStats()
    cache_dir = get_cache_dir()
    raw_stats = _get_cache_stats()
    hit_rate = get_cache_hit_rate()

    # ── 1. data/cache ──
    stats.total_files = raw_stats.get("total_files", 0)
    stats.total_size_bytes = raw_stats.get("total_size_bytes", 0)
    if hit_rate.get("total", 0) > 0:
        stats.hit_rate = hit_rate.get("rate", 0.0) * 100
        stats.hit_total = hit_rate.get("total", 0)
    stats.by_prefix = raw_stats.get("by_prefix", {})
    stats.top_by_size = raw_stats.get("top_by_size", [])

    reporter.info(f"缓存文件: {stats.total_files} 个 | 大小: {stats.total_size_bytes / 1024:.0f} KB")
    if stats.hit_total > 0:
        reporter.info(f"命中率: {stats.hit_rate:.1f}%")
    reporter.info("正在检查过期文件...")
    stats.expired = cleanup_expired(dry_run=True)
    reporter.info(f"过期文件: {stats.expired} 个")

    # ── 2. data/history/snapshots ──
    _hist_dir = os.path.join(PROJECT_ROOT, "data", "history", "snapshots")
    if os.path.isdir(_hist_dir):
        s_files = s_size = 0
        for _f in os.listdir(_hist_dir):
            _fp = os.path.join(_hist_dir, _f)
            if os.path.isfile(_fp) and _f.endswith(".json"):
                s_files += 1
                s_size += os.path.getsize(_fp)
        stats.snapshot_files = s_files
        stats.snapshot_size_bytes = s_size

    # ── 3. data/state ──
    _state_dir = os.path.join(PROJECT_ROOT, "data", "state")
    if os.path.isdir(_state_dir):
        s_files = s_size = 0
        for _f in os.listdir(_state_dir):
            _fp = os.path.join(_state_dir, _f)
            if os.path.isfile(_fp):
                s_files += 1
                s_size += os.path.getsize(_fp)
        stats.state_files = s_files
        stats.state_size_bytes = s_size

    return stats
