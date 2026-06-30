"""TUI 缓存管理命令处理器。

按职责从 tui_handlers.py 拆分而来，负责所有缓存刷新/管理相关的命令函数。
"""
from __future__ import annotations

import os
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.python.logger import setup_logger
from src.python.tui_menu import _press_any_key, _refresh_config, get_config_cache
from src.python.reader import list_xlsx_files, read_holdings
from src.python.config import set_config, get_llm_config
from src.python.tui_handlers import _select_holdings_file
logger = setup_logger()


def _read_holdings_and_clear_cache(group_name: str) -> list | None:
    """选择持仓文件 → 读取 → 清缓存。失败返回 None。

    Args:
        group_name: 缓存分组名称，传给 clear_by_group

    Returns:
        持仓列表（成功）或 None（失败）
    """
    from src.python.cache import clear_by_group

    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return None

    try:
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return None
        print(f"  [OK] 共 {len(holdings)} 条持仓记录")
        print("  [..] 清除旧缓存...")
        cleared = clear_by_group(group_name)
        if cleared:
            parts = [f"{name} {count}条" for name, count in cleared.items()]
            print(f"  [OK] {' + '.join(parts)} 已清除")
        else:
            print("  [OK] 无缓存需清除")
        return holdings
    except Exception as e:
        print(f"  [ERR] 读取持仓失败: {e}")
        _press_any_key()
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


def _refresh_profit_forecast_cache() -> int:
    """刷新盈利预测缓存。

    Returns:
        覆盖股票数（0 表示失败）
    """
    from src.python.providers.akshare_extras import _memo_clear, get_profit_forecast
    _memo_clear()
    data = get_profit_forecast()
    return len(data) if data else 0


def _refresh_sector_flow_cache() -> int:
    """刷新行业资金流向缓存。

    Returns:
        行业数（0 表示失败）
    """
    from src.python.providers.akshare_extras import get_sector_fund_flow
    data = get_sector_fund_flow()
    return len(data) if data else 0


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
            print(f"  [OK] fund_perf_{{code}}.json  ({perf_ok}/{len(funds)} 全部成功)")
        else:
            print(f"  [!] fund_perf_{{code}}.json  ({perf_ok}/{len(funds)} 成功, {perf_fail} 只失败)")
        if hold_fail == 0:
            print(f"  [OK] fund_hold_{{code}}.json  ({hold_ok}/{len(funds)} 全部成功)")
        else:
            print(f"  [!] fund_hold_{{code}}.json  ({hold_ok}/{len(funds)} 成功, {hold_fail} 只失败)")
        if bm_fail == 0:
            print(f"  [OK] fund_benchmarks.json       ({bm_ok}/{len(funds)} 全部成功)")
        else:
            print(f"  [!] fund_benchmarks.json       ({bm_ok}/{len(funds)} 成功, {bm_fail} 只未找到)")
    if pf_ok:
        print(f"  [OK] profit_forecast.json           ({pf_ok} 只股票)")
    elif funds:
        print(f"  [!] profit_forecast.json           获取失败")
    if sf_ok:
        print(f"  [OK] sector_flow.json               ({sf_ok} 个行业)")
    elif funds:
        print(f"  [!] sector_flow.json               获取失败")


def _refresh_common_caches() -> tuple[int, int]:
    """刷新不依赖基金持仓的公共缓存：盈利预测 + 行业资金流向。"""
    pf_ok = sf_ok = 0
    with ThreadPoolExecutor(max_workers=2) as _ex:
        _f1 = _ex.submit(_refresh_profit_forecast_cache)
        _f2 = _ex.submit(_refresh_sector_flow_cache)
        try:
            pf_ok = _f1.result()
            print(f"  [OK]   profit_forecast              ({pf_ok} 只股票)" if pf_ok
                  else "  [!]   profit_forecast              获取失败")
        except Exception as e:
            logger.debug("profit_forecast Future 异常: %s", e)
            print("  [!]   profit_forecast              获取失败")
        try:
            sf_ok = _f2.result()
            print(f"  [OK]   sector_flow                  ({sf_ok} 个行业)" if sf_ok
                  else "  [!]   sector_flow                  获取失败")
        except Exception as e:
            logger.debug("sector_flow Future 异常: %s", e)
            print("  [!]   sector_flow                  获取失败")
    return pf_ok, sf_ok


def _cmd_update_basic_cache() -> None:
    """更新基础类缓存。"""
    holdings = _read_holdings_and_clear_cache("refresh")
    if holdings is None:
        return

    from src.python.report.fund_performance import _is_fund
    funds = [h for h in holdings if _is_fund(h)]

    if not funds:
        print("  [!!] 未检测到基金持仓，跳过基金业绩/持仓/基准缓存")
        print("  [..] 继续刷新新闻/行业分类/分红/盈利预测/行业资金流向...")
        print()
        print("  [..]   并行获取新闻/行业/分红/盈利预测/行业资金流向...")
        _refresh_common_caches()
        _press_any_key()
        return

    try:
        print()
        print("  [..]   并行获取全部缓存数据...")

        perf_ok = hold_ok = bm_ok = 0
        pf_ok = sf_ok = 0

        max_workers_val = max(3, min(len(funds) + 2, 7))
        with ThreadPoolExecutor(max_workers=max_workers_val) as executor:
            all_futures: dict = {}
            for f in funds:
                all_futures[executor.submit(_refresh_one_fund_cache, f)] = "fund"
            all_futures[executor.submit(_refresh_profit_forecast_cache)] = "other"
            all_futures[executor.submit(_refresh_sector_flow_cache)] = "other"

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
                        print(f"  [OK]   {name} ({code}) — {' | '.join(parts)}")
                    elif result[0] == "profit_forecast":
                        pf_ok = result[1]
                        print(f"  [OK]   profit_forecast              ({pf_ok} 只股票)" if pf_ok
                              else "  [!]   profit_forecast              获取失败")
                    elif result[0] == "sector_flow":
                        sf_ok = result[1]
                        print(f"  [OK]   sector_flow                  ({sf_ok} 个行业)" if sf_ok
                              else "  [!]   sector_flow                  获取失败")
                except Exception as e:
                    logger.debug("缓存刷新 Future 异常 (%s): %s", tag, e)
                    print(f"  [!]   {'基金刷新异常' if tag == 'fund' else '其他缓存刷新异常'}")

        _print_cache_refresh_report(funds, perf_ok, hold_ok, bm_ok, pf_ok, sf_ok)
    except Exception as e:
        logger.exception("更新基础缓存失败")
        print(f"  [ERR] 更新失败: {e}")
    _press_any_key()


def _fetch_prices_and_indices(holdings: list) -> tuple[int, dict, dict]:
    """并行获取持仓价格 + 市场指数并逐条输出。"""
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.fetcher.price import fetch_market_data
    from concurrent.futures import ThreadPoolExecutor, as_completed as _ac

    price_ok = 0
    a_idx: dict = {}
    us_idx: dict = {}
    with ThreadPoolExecutor(max_workers=max(3, min(len(holdings) + 2, 7))) as executor:
        fut_map: dict[Any, Any] = {}
        for h in holdings:
            fut_map[executor.submit(fetch_market_data, h.code, h.name)] = h
        idx_a_fut = executor.submit(fetch_indices)
        idx_us_fut = executor.submit(fetch_us_indices)
        fut_map[idx_a_fut] = None
        fut_map[idx_us_fut] = None

        for future in _ac(fut_map):
            h_or_none = fut_map[future]
            try:
                if h_or_none is None:
                    result = future.result()
                    if future is idx_a_fut:
                        a_idx = result or {}
                        print(f"  [OK]   A 股指数: {len(a_idx)} 个")
                    else:
                        us_idx = result or {}
                        print(f"  [OK]   美股指数: {len(us_idx)} 个")
                else:
                    h = h_or_none
                    result = future.result()
                    if result and result.get("price", 0) > 0:
                        price_ok += 1
                        print(f"  [OK]   {h.name} ({h.code}) → {result['price']:.4f}")
                    else:
                        print(f"  [!]   {h.name} ({h.code}) → 失败")
            except Exception as e:
                if h_or_none is not None:
                    print(f"  [ERR]  {h_or_none.name} ({h_or_none.code}) → {e}")

    return price_ok, a_idx, us_idx


def _cmd_update_position_cache() -> None:
    """更新持仓类缓存。"""
    holdings = _read_holdings_and_clear_cache("preload")
    if holdings is None:
        return

    try:
        print()
        print(f"  [..]   并行获取持仓价格/净值 + 市场指数...")
        price_ok, a_idx, us_idx = _fetch_prices_and_indices(holdings)

        print()
        print(f"  {'=' * 40}")
        price_fail = len(holdings) - price_ok
        total_idx = len(a_idx) + len(us_idx)
        print(f"  持仓缓存更新完成 — 共 {len(holdings)} 条持仓")
        print()
        if price_fail == 0:
            print(f"  [OK] price_{{code}}.json          ({price_ok}/{len(holdings)} 全部成功)")
        else:
            print(f"  [!] price_{{code}}.json          ({price_ok}/{len(holdings)} 成功, {price_fail} 条失败)")
        print(f"  [OK] index_{{code}}.json           (A股 {len(a_idx)} 个 + 美股 {len(us_idx)} 个 = {total_idx} 个指数)")
        print(f"  [OK] LLM 关联缓存已清除（下次菜单 L 自动使用最新数据）")
    except Exception as e:
        logger.exception("更新持仓缓存失败")
        print(f"  [ERR] 更新失败: {e}")
    _press_any_key()


def _cmd_cleanup_cache() -> None:
    """清理过期缓存文件。"""
    from src.python.cache import cleanup_expired, get_cache_dir
    print("  [..] 正在扫描缓存目录...")
    removed = cleanup_expired(dry_run=False)
    cache_dir = get_cache_dir()
    if removed > 0:
        print(f"  [OK] 已删除 {removed} 个过期缓存文件 ({cache_dir})")
    else:
        print(f"  [..] 无需清理 ({cache_dir})")
    _press_any_key()


def _cmd_show_cache_stats() -> None:
    """查看缓存统计信息。"""
    from src.python.cache import cleanup_expired, get_cache_dir, get_cache_hit_rate, get_cache_stats
    cache_dir = get_cache_dir()
    stats = get_cache_stats()
    hit_rate = get_cache_hit_rate()
    print(f"  缓存目录: {cache_dir}")
    print(f"  文件总数: {stats['total_files']}")
    print(f"  总大小:   {stats['total_size_bytes'] / 1024:.0f} KB")
    if hit_rate["total"] > 0:
        pct = hit_rate["rate"] * 100
        print(f"  命中率:   {pct:.1f}% ({hit_rate['hits']} 命中 / {hit_rate['total']} 次请求)")
    print(f"  按前缀分类:")
    for prefix, count in sorted(stats.get("by_prefix", {}).items()):
        print(f"    {prefix}_*: {count} 个文件")
    print()
    top_size = stats.get("top_by_size", [])
    if top_size:
        print(f"  最大文件 TOP {len(top_size)}:")
        for key, size in top_size:
            size_kb = size / 1024
            if size_kb >= 1024:
                print(f"    {key}.json  ({size_kb / 1024:.1f} MB)")
            else:
                print(f"    {key}.json  ({size_kb:.0f} KB)")
        print()
    print("  [..] 正在检查过期文件...")
    expired = cleanup_expired(dry_run=True)
    print(f"  过期文件: {expired} 个（可通过菜单 [3] 清理）")
    _press_any_key()
