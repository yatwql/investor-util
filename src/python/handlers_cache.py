"""TUI 缓存管理命令处理器。

按职责从 tui_handlers.py 拆分而来，负责所有缓存刷新/管理相关的命令函数。
"""
from __future__ import annotations

import atexit
import os
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

from src.python.logger import setup_logger
from src.python.reader import read_holdings
from src.python.tui_handlers import print_error_with_hint, select_holdings_file
from src.python.tui_menu import GREEN, RED, YELLOW, RESET
from src.python.tui_menu import press_any_key, refresh_config

logger = setup_logger()

# 共享线程池 — handlers_cache 内多处并发任务复用同一实例
_POOL: ThreadPoolExecutor | None = None


def _get_pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cache")
        atexit.register(_POOL.shutdown, wait=False)
    return _POOL


def _read_holdings_and_clear_cache(group_name: str) -> list | None:
    """选择持仓文件 → 读取 → 清缓存。失败返回 None。

    Args:
        group_name: 缓存分组名称，传给 clear_by_group

    Returns:
        持仓列表（成功）或 None（失败）
    """
    from src.python.cache import clear_by_group

    refresh_config()
    filepath = select_holdings_file()
    if not filepath:
        return None

    try:
        holdings = read_holdings(filepath)
        if not holdings:
            print(f"  {RED}[ERR]{RESET} 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            press_any_key()
            return None
        print(f"  {GREEN}[OK]{RESET} 共 {len(holdings)} 条持仓记录")
        print("  [..] 清除旧缓存...")
        cleared = clear_by_group(group_name)
        if cleared:
            parts = [f"{name} {count}条" for name, count in cleared.items()]
            print(f"  {GREEN}[OK]{RESET} {' + '.join(parts)} 已清除")
        else:
            print(f"  {GREEN}[OK]{RESET} 无缓存需清除")
        return holdings
    except Exception as e:
        print_error_with_hint(e, "读取持仓失败")
        press_any_key()
        return None


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


def _refresh_industry_cache(holdings: list) -> int:
    """刷新行业分类缓存。

    提取持仓中所有 A 股代码，调用 batch_fetch_industry_data 重拉并写入缓存。

    Returns:
        成功获取的证券数量
    """
    from src.python.fetcher.industry import batch_fetch_industry_data

    codes = [h.code.strip() for h in holdings if h.code and h.code.strip()]
    if not codes:
        return 0
    result = batch_fetch_industry_data(codes)
    return len(result)


def _refresh_dividend_cache(holdings: list) -> int:
    """刷新股票历史分红缓存。

    提取持仓中所有代码，调用 get_dividend_data 重拉并写入缓存。
    get_dividend_data 内部自动过滤非 A 股代码。

    Returns:
        成功获取的股票数量
    """
    from src.python.providers.akshare_extras import get_dividend_data

    codes = [h.code.strip() for h in holdings if h.code and h.code.strip()]
    if not codes:
        return 0
    result = get_dividend_data(codes)
    return len(result)


def _refresh_profit_forecast_cache() -> tuple[str, int]:
    """刷新盈利预测缓存。

    Returns:
        ("profit_forecast", 覆盖股票数) — 0 表示失败
    """
    from src.python.providers.akshare_extras import _memo_clear, get_profit_forecast
    _memo_clear()
    data = get_profit_forecast()
    return ("profit_forecast", len(data) if data else 0)


def _refresh_sector_flow_cache() -> tuple[str, int]:
    """刷新行业资金流向缓存。

    Returns:
        ("sector_flow", 行业数) — 0 表示失败
    """
    from src.python.providers.akshare_extras import get_sector_fund_flow
    data = get_sector_fund_flow()
    return ("sector_flow", len(data) if data else 0)


def _sector_flow_hint() -> str:
    """根据最近一次行业资金流向失败类型返回提示文案。"""
    from src.python.providers.akshare_extras import _SECTOR_FLOW_FAILURE
    if _SECTOR_FLOW_FAILURE == "connection":
        return "连接失败"
    if _SECTOR_FLOW_FAILURE == "empty":
        return "暂无数据"
    return "获取失败"


def _print_cache_refresh_report(
    funds: list, perf_ok: int, hold_ok: int, bm_ok: int,
    pf_ok: int = 0, sf_ok: int = 0,
) -> None:
    """输出基础缓存刷新结果汇总。"""
    print()
    print(f"  {'=' * 40}")
    if funds:
        perf_fail = len(funds) - perf_ok
        hold_fail = len(funds) - hold_ok
        bm_fail = len(funds) - bm_ok
        print(f"  基础缓存更新完成 — 共 {len(funds)} 只基金")
        print()
        if perf_fail == 0:
            print(f"  {GREEN}[OK]{RESET} fund_perf_{{code}}.json  ({perf_ok}/{len(funds)} 全部成功)")
        else:
            print(f"  {YELLOW}[!]{RESET} fund_perf_{{code}}.json  ({perf_ok}/{len(funds)} 成功, {perf_fail} 只失败)")
        if hold_fail == 0:
            print(f"  {GREEN}[OK]{RESET} fund_hold_{{code}}.json  ({hold_ok}/{len(funds)} 全部成功)")
        else:
            print(f"  {YELLOW}[!]{RESET} fund_hold_{{code}}.json  ({hold_ok}/{len(funds)} 成功, {hold_fail} 只失败)")
        if bm_fail == 0:
            print(f"  {GREEN}[OK]{RESET} fund_benchmarks.json       ({bm_ok}/{len(funds)} 全部成功)")
        else:
            print(f"  {YELLOW}[!]{RESET} fund_benchmarks.json       ({bm_ok}/{len(funds)} 成功, {bm_fail} 只未找到)")
    if pf_ok:
        print(f"  {GREEN}[OK]{RESET} profit_forecast.json           ({pf_ok} 只股票)")
    elif funds:
        print(f"  {YELLOW}[!]{RESET} profit_forecast.json           获取失败")
    if sf_ok:
        print(f"  {GREEN}[OK]{RESET} sector_flow.json               ({sf_ok} 个行业)")
    elif funds:
        print(f"  {YELLOW}[!]{RESET} sector_flow.json               {_sector_flow_hint()}")


def _refresh_common_caches(holdings: list | None = None) -> tuple[int, int, int, int]:
    """刷新不依赖基金持仓的公共缓存：盈利预测 + 行业资金流向。

    Args:
        holdings: 可选持仓列表，提供时额外刷新行业分类和分红缓存。

    Returns:
        (pf_ok, sf_ok, ind_ok, div_ok)
    """
    pf_ok = sf_ok = ind_ok = div_ok = 0
    _ex = _get_pool()
    _f1 = _ex.submit(_refresh_profit_forecast_cache)
    _f2 = _ex.submit(_refresh_sector_flow_cache)
    futures: list[tuple[Future[Any], str]] = [(_f1, "profit_forecast"), (_f2, "sector_flow")]
    if holdings:
        _f3 = _ex.submit(_refresh_industry_cache, holdings)
        _f4 = _ex.submit(_refresh_dividend_cache, holdings)
        futures.extend([(_f3, "industry"), (_f4, "dividend")])

        for fut, tag in futures:
            try:
                if tag == "profit_forecast":
                    _, pf_ok = fut.result()
                    print(f"  {GREEN}[OK]{RESET}   profit_forecast              ({pf_ok} 只股票)" if pf_ok else f"  {YELLOW}[!]{RESET}   profit_forecast              获取失败")
                elif tag == "sector_flow":
                    sf_ok = fut.result()[1]
                    print(f"  {GREEN}[OK]{RESET}   sector_flow                  ({sf_ok} 个行业)" if sf_ok
                          else f"  {YELLOW}[!]{RESET}   sector_flow                  {_sector_flow_hint()}")
                elif tag == "industry":
                    ind_ok = fut.result()
                    print(f"  {GREEN}[OK]{RESET}   industry                     ({ind_ok} 只证券)" if ind_ok else f"  {YELLOW}[!]{RESET}   industry                     获取失败")
                elif tag == "dividend":
                    div_ok = fut.result()
                    print(f"  {GREEN}[OK]{RESET}   dividend                     ({div_ok} 只股票)" if div_ok else f"  {YELLOW}[!]{RESET}   dividend                     获取失败")
            except Exception as e:  # noqa: PERF203
                logger.debug("%s Future 异常: %s", tag, e)
                print(f"  {YELLOW}[!]{RESET}   {tag:<30}获取失败")
    return pf_ok, sf_ok, ind_ok, div_ok


def _cmd_update_basic_cache() -> None:
    """更新基础类缓存。"""
    holdings = _read_holdings_and_clear_cache("refresh")
    if holdings is None:
        return

    from src.python.report.fund_performance import is_fund
    funds = [h for h in holdings if is_fund(h)]

    if not funds:
        print("  [!!] 未检测到基金持仓，跳过基金业绩/持仓/基准缓存")
        print("  [..] 继续刷新行业分类/分红/盈利预测/行业资金流向...")
        print()
        print("  [..]   并行获取行业/分红/盈利预测/资金流向...")
        _refresh_common_caches(holdings)
        press_any_key()
        return

    try:
        print()
        print("  [..]   并行获取全部缓存数据...")

        perf_ok = hold_ok = bm_ok = 0
        pf_ok = sf_ok = 0

        _ex = _get_pool()
        all_futures: dict = {}
        for f in funds:
            all_futures[_ex.submit(_refresh_one_fund_cache, f)] = "fund"
        all_futures[_ex.submit(_refresh_profit_forecast_cache)] = "other"
        all_futures[_ex.submit(_refresh_sector_flow_cache)] = "other"

        for future in as_completed(all_futures):
            tag = all_futures[future]
            try:
                result = future.result()
                if result[0] == "fund":
                    _, code, name, p_ok, h_ok, h_cnt, b_ok = result
                    if p_ok: perf_ok += 1
                    if h_ok: hold_ok += 1
                    if b_ok: bm_ok += 1
                    parts = [f"业绩={'OK' if p_ok else '失败'}"]
                    if h_ok:
                        parts.append(f"持仓={h_cnt}条")
                    else:
                        parts.append("持仓=无数据")
                    parts.append(f"基准={'OK' if b_ok else '未找到'}")
                    print(f"  {GREEN}[OK]{RESET}   {name} ({code}) — {' | '.join(parts)}")
                elif result[0] == "profit_forecast":
                    pf_ok = result[1]
                    print(f"  {GREEN}[OK]{RESET}   profit_forecast              ({pf_ok} 只股票)" if pf_ok else f"  {YELLOW}[!]{RESET}   profit_forecast              获取失败")
                elif result[0] == "sector_flow":
                    sf_ok = result[1]
                    print(f"  {GREEN}[OK]{RESET}   sector_flow                  ({sf_ok} 个行业)" if sf_ok
                          else f"  {YELLOW}[!]{RESET}   sector_flow                  {_sector_flow_hint()}")
            except Exception as e:
                logger.debug("缓存刷新 Future 异常 (%s): %s", tag, e)
                print(f"  {YELLOW}[!]{RESET}   {'基金刷新异常' if tag == 'fund' else '其他缓存刷新异常'}")

        _print_cache_refresh_report(funds, perf_ok, hold_ok, bm_ok, pf_ok, sf_ok)
    except Exception as e:
        logger.exception("更新基础缓存失败")
        print_error_with_hint(e, "更新基础缓存")
    press_any_key()


def _fetch_prices_and_indices(holdings: list) -> tuple[int, dict, dict]:
    """并行获取持仓价格 + 市场指数并逐条输出。"""
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.fetcher.price import fetch_market_data

    price_ok = 0
    a_idx: dict = {}
    us_idx: dict = {}
    _ex = _get_pool()
    fut_map: dict[Any, Any] = {}
    for h in holdings:
        fut_map[_ex.submit(fetch_market_data, h.code, h.name)] = h
    idx_a_fut = _ex.submit(fetch_indices)
    idx_us_fut = _ex.submit(fetch_us_indices)
    fut_map[idx_a_fut] = None
    fut_map[idx_us_fut] = None

    for future in as_completed(fut_map):
        h_or_none = fut_map[future]
        try:
            if h_or_none is None:
                result = future.result()
                if future is idx_a_fut:
                    a_idx = result or {}
                    print(f"  {GREEN}[OK]{RESET}   A 股指数: {len(a_idx)} 个")
                else:
                    us_idx = result or {}
                    print(f"  {GREEN}[OK]{RESET}   美股指数: {len(us_idx)} 个")
            else:
                h = h_or_none
                result = future.result()
                if result and result.get("price", 0) > 0:
                    price_ok += 1
                    print(f"  {GREEN}[OK]{RESET}   {h.name} ({h.code}) → {result['price']:.4f}")
                else:
                    print(f"  {YELLOW}[!]{RESET}   {h.name} ({h.code}) → 失败")
        except Exception as e:
            if h_or_none is not None:
                _msg = str(e)
                if any(kw in _msg.lower() for kw in ("connect", "timeout", "network", "reset")):
                    _hint = "网络异常"
                elif "parse" in _msg.lower() or "decode" in _msg.lower():
                    _hint = "数据解析失败"
                else:
                    _hint = "获取失败"
                print(f"  {RED}[ERR]{RESET}  {h_or_none.name} ({h_or_none.code}) → {_hint}")

    return price_ok, a_idx, us_idx


def _cmd_update_position_cache() -> None:
    """更新持仓类缓存。"""
    holdings = _read_holdings_and_clear_cache("preload")
    if holdings is None:
        return

    try:
        print()
        print("  [..]   并行获取持仓价格/净值 + 市场指数...")
        price_ok, a_idx, us_idx = _fetch_prices_and_indices(holdings)

        print()
        print(f"  {'=' * 40}")
        price_fail = len(holdings) - price_ok
        total_idx = len(a_idx) + len(us_idx)
        print(f"  持仓缓存更新完成 — 共 {len(holdings)} 条持仓")
        print()
        if price_fail == 0:
            print(f"  {GREEN}[OK]{RESET} price_{{code}}.json          ({price_ok}/{len(holdings)} 全部成功)")
        else:
            print(f"  {YELLOW}[!]{RESET} price_{{code}}.json          ({price_ok}/{len(holdings)} 成功, {price_fail} 条失败)")
        print(f"  {GREEN}[OK]{RESET} index_{{code}}.json           (A股 {len(a_idx)} 个 + 美股 {len(us_idx)} 个 = {total_idx} 个指数)")
        print(f"  {GREEN}[OK]{RESET} LLM 关联缓存已清除（下次菜单 L 自动使用最新数据）")
    except Exception as e:
        logger.exception("更新持仓缓存失败")
        print_error_with_hint(e, "更新持仓缓存")
    press_any_key()


def _cmd_cleanup_cache() -> None:
    """清理过期缓存文件。"""
    from src.python.cache import cleanup_expired, get_cache_dir
    print("  [..] 正在扫描缓存目录...")
    removed = cleanup_expired(dry_run=False)
    cache_dir = get_cache_dir()
    if removed > 0:
        print(f"  {GREEN}[OK]{RESET} 已删除 {removed} 个过期缓存文件 ({cache_dir})")
    else:
        print(f"  [..] 无需清理 ({cache_dir})")
    press_any_key()


def _cmd_show_cache_stats() -> None:
    """查看缓存/状态统计信息。"""
    from src.python.cache import cleanup_expired, get_cache_dir, get_cache_hit_rate, get_cache_stats
    from src.python.constants import PROJECT_ROOT
    cache_dir = get_cache_dir()
    stats = get_cache_stats()
    hit_rate = get_cache_hit_rate()

    # ── 1. data/cache 缓存文件 ──
    print(f"  ════════════════ data/cache ════════════════")
    print(f"  目录: {cache_dir}")
    print(f"  文件: {stats['total_files']} 个 | 大小: {stats['total_size_bytes'] / 1024:.0f} KB")
    if hit_rate["total"] > 0:
        pct = hit_rate["rate"] * 100
        print(f"  命中率:   {pct:.1f}% ({hit_rate['hits']} 命中 / {hit_rate['total']} 次请求)")
    top_size = stats.get("top_by_size", [])
    if top_size:
        print(f"  最大文件:")
        for key, size in top_size[:3]:
            size_kb = size / 1024
            disp = f"{size_kb / 1024:.1f} MB" if size_kb >= 1024 else f"{size_kb:.0f} KB"
            print(f"    {key}.json  ({disp})")
    print("  前缀分布:")
    for prefix, count in sorted(stats.get("by_prefix", {}).items()):
        print(f"    {prefix}_*: {count} 个文件")
    print()
    print("  [..] 正在检查过期文件...")
    expired = cleanup_expired(dry_run=True)
    print(f"  过期文件: {expired} 个（菜单 [3] 可清理）")

    # ── 2. data/history/snapshots 快照文件 ──
    _hist_dir = os.path.join(PROJECT_ROOT, "data", "history", "snapshots")
    if os.path.isdir(_hist_dir):
        _h_files = _h_size = 0
        for _f in os.listdir(_hist_dir):
            _fp = os.path.join(_hist_dir, _f)
            if os.path.isfile(_fp) and _f.endswith(".json"):
                _h_files += 1
                _h_size += os.path.getsize(_fp)
        if _h_files > 0:
            print()
            print(f"  ════════ data/history/snapshots ════════")
            print(f"  目录: {os.path.abspath(_hist_dir)}")
            print(f"  文件: {_h_files} 个 | 大小: {_h_size / 1024:.0f} KB")
            _latest = max(
                (os.path.getmtime(os.path.join(_hist_dir, _f))
                 for _f in os.listdir(_hist_dir) if _f.endswith(".json")),
                default=0,
            )
            if _latest:
                from datetime import datetime
                print(f"  最新: {datetime.fromtimestamp(_latest).strftime('%Y-%m-%d %H:%M')}")
            print(f"  （持仓快照，超期自动删除，不随缓存清理）")

    # ── 3. data/state 运行时状态文件 ──
    _state_dir = os.path.join(PROJECT_ROOT, "data", "state")
    if os.path.isdir(_state_dir):
        _s_files = _s_size = 0
        for _f in os.listdir(_state_dir):
            _fp = os.path.join(_state_dir, _f)
            if os.path.isfile(_fp):
                _s_files += 1
                _s_size += os.path.getsize(_fp)
        if _s_files > 0:
            print()
            print(f"  ═══════════════ data/state ═══════════════")
            print(f"  目录: {os.path.abspath(_state_dir)}")
            print(f"  文件: {_s_files} 个 | 大小: {_s_size / 1024:.1f} KB")
            print(f"  （运行时状态，跨会话持久化，不随缓存清理）")

    press_any_key()
