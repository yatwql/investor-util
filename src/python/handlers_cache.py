"""TUI 缓存管理命令处理器。

所有缓存刷新/管理相关的 TUI 命令处理函数（菜单 [1][2][3][4]）。
业务逻辑委托至 cache/operations.py，本模块仅保留 TUI 外壳。

本模块包含：
  - TUI 文件选择 + 持仓读取（_read_holdings_and_clear_cache）
  - TUI 结果格式化（_print_cache_refresh_report, _print_position_result）
  - TUI 命令入口（_cmd_*），委托至 cache/operations.py
"""

from __future__ import annotations

import os

from src.python.logger import setup_logger
from src.python.reader import read_holdings
from src.python.tui_handlers import print_error_with_hint, select_holdings_file
from src.python.tui_menu import GREEN, RED, RESET, YELLOW, press_any_key, refresh_config

logger = setup_logger()


# ── TUI 辅助：文件选择 + 读取 ────────────────────────────────


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


# ── TUI 结果格式化 ───────────────────────────────────────────


def _print_cache_refresh_report(result) -> None:
    """TUI 格式化输出缓存刷新结果（CacheUpdateResult → 终端颜色）。"""
    from src.python.cache.operations import _sector_flow_hint

    funds_count = result.total_funds
    perf_ok = result.perf_ok
    hold_ok = result.hold_ok
    bm_ok = result.bm_ok
    pf_ok = result.pf_ok
    sf_ok = result.sf_ok

    print()
    print(f"  {'=' * 40}")
    if funds_count:
        perf_fail = funds_count - perf_ok
        hold_fail = funds_count - hold_ok
        bm_fail = funds_count - bm_ok
        print(f"  基础缓存更新完成 — 共 {funds_count} 只基金")
        print()
        if perf_fail == 0:
            print(f"  {GREEN}[OK]{RESET} fund_perf_{{code}}.json  ({perf_ok}/{funds_count} 全部成功)")
        else:
            print(f"  {YELLOW}[!]{RESET} fund_perf_{{code}}.json  ({perf_ok}/{funds_count} 成功, {perf_fail} 只失败)")
        if hold_fail == 0:
            print(f"  {GREEN}[OK]{RESET} fund_hold_{{code}}.json  ({hold_ok}/{funds_count} 全部成功)")
        else:
            print(f"  {YELLOW}[!]{RESET} fund_hold_{{code}}.json  ({hold_ok}/{funds_count} 成功, {hold_fail} 只失败)")
        if bm_fail == 0:
            print(f"  {GREEN}[OK]{RESET} fund_benchmarks.json       ({bm_ok}/{funds_count} 全部成功)")
        else:
            print(f"  {YELLOW}[!]{RESET} fund_benchmarks.json       ({bm_ok}/{funds_count} 成功, {bm_fail} 只未找到)")
    if pf_ok:
        print(f"  {GREEN}[OK]{RESET} profit_forecast.json           ({pf_ok} 只股票)")
    elif funds_count:
        print(f"  {YELLOW}[!]{RESET} profit_forecast.json           获取失败")
    if sf_ok:
        print(f"  {GREEN}[OK]{RESET} sector_flow.json               ({sf_ok} 个行业)")
    elif funds_count:
        print(f"  {YELLOW}[!]{RESET} sector_flow.json               {_sector_flow_hint()}")


def _print_position_result(result) -> None:
    """TUI 格式化输出持仓缓存更新结果（PositionCacheResult → 终端颜色）。"""
    print()
    print(f"  {'=' * 40}")
    price_fail = result.total - result.price_ok
    total_idx = result.a_index_count + result.us_index_count
    print(f"  持仓缓存更新完成 — 共 {result.total} 条持仓")
    print()
    if price_fail == 0:
        print(f"  {GREEN}[OK]{RESET} price_{{code}}.json          ({result.price_ok}/{result.total} 全部成功)")
    else:
        print(
            f"  {YELLOW}[!]{RESET} price_{{code}}.json          ({result.price_ok}/{result.total} 成功, {price_fail} 条失败)"
        )
    print(
        f"  {GREEN}[OK]{RESET} index_{{code}}.json           (A股 {result.a_index_count} 个 + 美股 {result.us_index_count} 个 = {total_idx} 个指数)"
    )
    print(f"  {GREEN}[OK]{RESET} LLM 关联缓存已清除（下次菜单 L 自动使用最新数据）")


# ── TUI 命令入口（委托至 cache/operations.py）────────────────


def _run_cache_update(group_name: str, update_fn, print_fn, action_name: str) -> None:
    """通用缓存更新命令骨架。

    Args:
        group_name: 缓存分组名称（传给 clear_by_group）
        update_fn: 执行缓存的函数，签名 (holdings, reporter) -> result
        print_fn: 结果格式化函数，签名 (result) -> None
        action_name: 操作名称（用于错误提示）
    """
    holdings = _read_holdings_and_clear_cache(group_name)
    if holdings is None:
        return

    from src.python.report.progress import TuiProgressReporter

    reporter = TuiProgressReporter()
    try:
        result = update_fn(holdings, reporter)
        print_fn(result)
    except Exception as e:
        logger.exception("更新%s失败", action_name)
        print_error_with_hint(e, f"更新{action_name}")
    press_any_key()


def _cmd_update_basic_cache() -> None:
    """更新基础类缓存。"""
    from src.python.cache.operations import update_basic_cache

    _run_cache_update("refresh", update_basic_cache, _print_cache_refresh_report, "基础缓存")


def _cmd_update_position_cache() -> None:
    """更新持仓类缓存。"""
    from src.python.cache.operations import update_position_cache

    _run_cache_update("preload", update_position_cache, _print_position_result, "持仓缓存")


def _cmd_cleanup_cache() -> None:
    """清理过期缓存文件。"""
    from src.python.cache.operations import cleanup_cache
    from src.python.report.progress import TuiProgressReporter

    reporter = TuiProgressReporter()
    cleanup_cache(reporter)
    press_any_key()


def _cmd_show_cache_stats() -> None:
    """查看缓存/状态统计信息。"""
    from src.python.cache.operations import get_cache_stats
    from src.python.report.progress import TuiProgressReporter

    reporter = TuiProgressReporter()
    stats = get_cache_stats(reporter)

    from datetime import datetime

    from src.python.cache import get_cache_dir
    from src.python.constants import PROJECT_ROOT

    cache_dir = get_cache_dir()

    # ── 1. data/cache 缓存文件 ──
    print(f"  ════════════════ data/cache ════════════════")
    print(f"  目录: {cache_dir}")
    print(f"  文件: {stats.total_files} 个 | 大小: {stats.total_size_bytes / 1024:.0f} KB")
    if stats.hit_total > 0:
        print(f"  命中率:   {stats.hit_rate:.1f}% ({stats.hit_total} 次请求)")
    if stats.top_by_size:
        print(f"  最大文件:")
        for key, size in stats.top_by_size[:3]:
            size_kb = size / 1024
            disp = f"{size_kb / 1024:.1f} MB" if size_kb >= 1024 else f"{size_kb:.0f} KB"
            print(f"    {key}.json  ({disp})")
    print("  前缀分布:")
    for prefix, count in sorted(stats.by_prefix.items()):
        print(f"    {prefix}_*: {count} 个文件")
    print()
    print(f"  过期文件: {stats.expired} 个（菜单 [3] 可清理）")

    # ── 2. data/history/snapshots 快照文件 ──
    if stats.snapshot_files > 0:
        print()
        print(f"  ════════ data/history/snapshots ════════")
        _hist_dir = os.path.join(PROJECT_ROOT, "data", "history", "snapshots")
        print(f"  目录: {os.path.abspath(_hist_dir)}")
        print(f"  文件: {stats.snapshot_files} 个 | 大小: {stats.snapshot_size_bytes / 1024:.0f} KB")
        _latest = max(
            (os.path.getmtime(os.path.join(_hist_dir, _f)) for _f in os.listdir(_hist_dir) if _f.endswith(".json")),
            default=0,
        )
        if _latest:
            print(f"  最新: {datetime.fromtimestamp(_latest).strftime('%Y-%m-%d %H:%M')}")
        print(f"  （持仓快照，超期自动删除，不随缓存清理）")

    # ── 3. data/state 运行时状态文件 ──
    if stats.state_files > 0:
        print()
        print(f"  ═══════════════ data/state ═══════════════")
        _state_dir = os.path.join(PROJECT_ROOT, "data", "state")
        print(f"  目录: {os.path.abspath(_state_dir)}")
        print(f"  文件: {stats.state_files} 个 | 大小: {stats.state_size_bytes / 1024:.1f} KB")
        print(f"  （运行时状态，跨会话持久化，不随缓存清理）")

    press_any_key()
