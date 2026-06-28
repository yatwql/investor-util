"""TUI 命令处理器模块。

职责：
  - 所有 _cmd_* 命令处理器
  - 报告生成逻辑（_generate_excel_report）
  - 文件选择、缓存预热、网络检查等辅助函数
  - 菜单执行调度（_execute_item）
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.tui_menu import MENU_ITEMS, _press_any_key, _refresh_config, get_config_cache
from src.logger import setup_logger
from src.reader import get_xlsx_info, list_xlsx_files, read_holdings
from src.config import get_config, set_config

logger = setup_logger()

_busy: bool = False  # 防连续按键保护


# ── 辅助函数 ──────────────────────────────────────────────


def _print_error_with_hint(e: Exception, prefix: str = "操作失败") -> None:
    """输出带友好提示的错误信息。"""
    msg = str(e)
    is_network = any(kw in msg.lower() for kw in (
        "connect", "timeout", "dns", "resolve", "network",
        "connection", "read timed out", "eof", "reset",
    ))
    if is_network:
        print(f"  [ERR] {prefix}: 网络连接异常，请检查网络后重试")
        print(f"        详情: {msg}")
    elif isinstance(e, PermissionError):
        print(f"  [ERR] {prefix}: 文件写入权限不足")
        print(f"        请检查输出目录的写入权限")
    elif isinstance(e, FileNotFoundError):
        print(f"  [ERR] {prefix}: 文件未找到")
        print(f"        详情: {msg}")
    else:
        print(f"  [ERR] {prefix}: {msg}")


def _check_network_available(details: list) -> bool:
    """检查行情数据是否全部不可用（网络完全中断）。"""
    if not details:
        return False
    all_unavailable = all(
        getattr(d, 'price', 0) is None or getattr(d, 'price', 0) == 0
        for d in details
    )
    if all_unavailable:
        print("  [!!] 网络连接异常：所有行情数据均获取失败")
        print("     请检查网络连接后重试（部分报告内容可能为空）")
        return False
    return True


# ── 持仓变更检测与缓存预热 ─────────────────────────────────


def _check_and_warm_for_new_assets(holdings: list) -> None:
    """检测持仓是否变化，若有新增资产则主动预热其缓存数据。"""
    from src.cache import check_and_refresh_caches
    from src.fetcher import (
        batch_fetch_industry_data,
        fetch_fund_holdings,
        fetch_fund_rankings,
        fetch_market_data,
    )
    from src.report.fund_performance import _is_fund

    new_codes = check_and_refresh_caches(holdings)
    if not new_codes:
        return

    code_map = {h.code: h for h in holdings}
    print(f"  [..] 检测到 {len(new_codes)} 个新增资产，正在预热缓存...")

    for code in new_codes:
        h = code_map.get(code)
        name = h.name if h else code

        print(f"  [..]   新增 {name} ({code}) — 获取行情...", end="")
        result = fetch_market_data(code, name)
        if result and result.get("price", 0) > 0:
            print(f" {result['price']:.4f}")
        else:
            print(" 失败")

        if h and _is_fund(h):
            print(f"  [..]   新增基金 {name} ({code}) — 获取业绩排名...", end="")
            perf = fetch_fund_rankings(code)
            print(" OK" if perf else " 失败")

            print(f"  [..]   新增基金 {name} ({code}) — 获取持仓明细...", end="")
            holds = fetch_fund_holdings(code)
            if holds and holds.get("holdings"):
                print(f" {len(holds['holdings'])} 条")
            else:
                print(" 无数据")

        print(f"  [..]   新增 {name} ({code}) — 获取行业分类...", end="")
        _ind_map = batch_fetch_industry_data([code])
        if _ind_map and code in _ind_map:
            _idata = _ind_map[code]
            ind_name = _idata.get("industry") or "未知"
            conc_count = len(_idata.get("concepts", []))
            print(f" {ind_name} ({conc_count} 个概念)")
        else:
            print(" 无数据")

    print(f"  [OK] 新增资产缓存预热完成")


# ── 文件选择 ──────────────────────────────────────────────


def _select_holdings_file() -> str | None:
    """让用户选择持仓文件，返回绝对路径；未找到时返回 None。"""
    _refresh_config()
    config = get_config_cache() or {}
    specific_path = os.path.join(config.get("holdings_dir", ""), config.get("holdings_filename", ""))

    if os.path.exists(specific_path):
        return os.path.abspath(specific_path)

    dir_path = config.get("holdings_dir", "")
    files = list_xlsx_files(dir_path)
    if not files:
        print(f"  [ERR] 目录 '{dir_path}' 下未找到 xlsx 文件")
        print("     请先配置正确的持仓目录（菜单选项 C）")
        return None

    if len(files) == 1:
        print(f"  使用唯一找到的文件: {os.path.basename(files[0])}")
        return files[0]

    print("  找到多个持仓文件，请选择:")
    print(f"  {'':8s}{'文件名':40s}{'大小':>10s}{'修改日期':>22s}{'账户数':>8s}")
    print(f"  {'':-^8s}{'':-^40s}{'':->10s}{'':->22s}{'':->8s}")
    for i, f in enumerate(files, 1):
        basename = os.path.basename(f)
        name_disp = basename if len(basename) <= 38 else basename[:35] + "..."
        size = os.path.getsize(f)
        size_str = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
        mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M")
        info = get_xlsx_info(f)
        acct_str = f"{info.get('accounts', '?')}" if "error" not in info else "err"
        print(f"  [{i}]  {name_disp:38s} {size_str:>10s} {mtime:>22s} {acct_str:>8s}")
    try:
        choice = input("  请输入编号: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            return files[idx]
        print("  [ERR] 无效编号")
    except (ValueError, EOFError):
        print("  [ERR] 无效输入")
    return None


# ── 生成命令 ──────────────────────────────────────────────


def _cmd_generate_excel() -> None:
    """生成 Excel 分析报告（必选内容）。"""
    _refresh_config()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return
    try:
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        _check_and_warm_for_new_assets(holdings)
        _generate_excel_report(holdings, include_news=False, output_dir=config.get("output_dir", "reports"))
    except Exception as e:
        logger.exception("生成 Excel 报告失败")
        _print_error_with_hint(e, "生成失败")
    _press_any_key()


def _cmd_generate_excel_with_news() -> None:
    """生成包含新闻的 Excel 分析报告。"""
    _refresh_config()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return
    try:
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        _check_and_warm_for_new_assets(holdings)
        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))
        _generate_excel_report(holdings, include_news=True, output_dir=output_dir, news_top_count=news_top_count)
    except Exception as e:
        logger.exception("生成 Excel（新闻）报告失败")
        _print_error_with_hint(e, "生成失败")
    _press_any_key()


def _generate_excel_report(
    holdings: list, include_news: bool = False, output_dir: str = "reports",
    news_top_count: int = 100, include_llm: bool = False,
    show_llm_in_tui: bool = False, llm_content: tuple | None = None,
    details: list | None = None, a_indices: dict[str, dict[str, Any]] | None = None,
    us_indices: dict[str, dict[str, Any]] | None = None,
    news_data: list | None = None,
    llm_cached: tuple[bool, bool] = (False, False),
    news_llm_meta: dict | None = None,
) -> None:
    """生成 Excel 报告的核心逻辑。"""
    from src.fetcher import fetch_indices, fetch_us_indices
    from src.report.category import write_category_sheet
    from src.report.excel_writer import create_workbook, save_workbook
    from src.report.fund_performance import write_fund_performance_sheet
    from src.report.market_value import (
        classify_holdings,
        get_last_trading_day,
        price_update_status,
        write_market_value_sheet,
    )
    from src.report.penetration import write_penetration_sheet, compute_penetration_top10
    from src.report.summary import write_summary_sheet

    wb = create_workbook()
    wb.remove(wb.active)

    if details is not None:
        logger.info("复用外部传入的市值核算数据，共 %d 条", len(details))
        total_mv = sum(d.market_value for d in details)
        total_cost = sum(d.cost for d in details)
        total_profit = sum(d.profit for d in details)
        today_profit = sum(d.today_profit for d in details)
        ws1 = wb.create_sheet()
        write_market_value_sheet(ws1, holdings, details=details)
    else:
        logger.info("正在获取行情数据（首次耗时较长，后续使用缓存）...")
        ws1 = wb.create_sheet()
        total_mv, total_cost, total_profit, today_profit, details = \
            write_market_value_sheet(ws1, holdings)

    categories = classify_holdings(holdings)
    up_status = price_update_status(details, get_last_trading_day())

    if a_indices is None:
        logger.info("正在获取市场指数...")
        a_indices = fetch_indices()
    if us_indices is None:
        us_indices = fetch_us_indices()

    logger.info("正在生成汇总...")
    ws2 = wb.create_sheet()
    write_summary_sheet(
        ws2, total_mv, total_cost, total_profit, today_profit,
        categories=categories, update_status=up_status,
        a_indices=a_indices, us_indices=us_indices,
    )

    logger.info("正在生成分类汇总...")
    ws3 = wb.create_sheet()
    write_category_sheet(ws3, holdings, details)

    pen_result = compute_penetration_top10(holdings, details)

    logger.info("正在生成资产穿透 TOP10...")
    ws4 = wb.create_sheet()
    write_penetration_sheet(ws4, holdings, details, penetration_data=pen_result)

    logger.info("正在获取基金业绩排名...")
    ws5 = wb.create_sheet()
    write_fund_performance_sheet(ws5, holdings, details)

    if include_news:
        from src.report.news_correlation import write_news_sheet
        penetrated_assets = pen_result.get("top10", []) if pen_result else []

        if news_data is not None:
            logger.info("复用预取的新闻数据，共 %d 条", len(news_data))
            _meta = news_llm_meta or {}
        else:
            logger.info("正在获取财经新闻（含穿透资产关键词）...")
            from src.report.news_correlation import build_news_data
            news_data, _meta = build_news_data(holdings, top_n=news_top_count, penetrated_assets=penetrated_assets)
        ws6 = wb.create_sheet()
        write_news_sheet(ws6, news_data, llm_meta=_meta)

    if include_llm:
        logger.info("正在生成 LLM 增补内容...")
        try:
            from src.report.llm_content import write_llm_sheets
            macro_text, expert_text = write_llm_sheets(wb, llm_content=llm_content, llm_cached=llm_cached)
            logger.info("LLM 增补内容已生成")
        except ImportError:
            logger.warning("LLM 增补模块 (src.report.llm_content) 未就绪，跳过")
            macro_text = expert_text = ""
        except Exception as e:
            logger.exception("生成 LLM 增补内容失败")
            macro_text = expert_text = ""

        if show_llm_in_tui and (macro_text or expert_text):
            _show_llm_tui(macro_text, expert_text)

    path = save_workbook(wb, output_dir=output_dir)
    logger.info("Excel 报告已生成: %s", path)
    logger.info("总市值: %.2f元, 总成本: %.2f元, 总盈亏: %.2f元, 本日盈亏: %.2f元",
                total_mv, total_cost, total_profit, today_profit)


def _cmd_generate_html(news: bool = False) -> None:
    """生成基础的 HTML 分析报告。"""
    _refresh_config()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        print(f"  [OK] 成功读取 {len(holdings)} 条持仓记录")
        _check_and_warm_for_new_assets(holdings)

        print("  [..] 正在获取行情数据并生成 HTML 报告...")
        from src.report.html_writer import write_html_report
        news_top_count = int(config.get("news_top_count", 100))
        path = write_html_report(
            holdings, output_dir=config.get("output_dir", "reports"),
            news_top_count=news_top_count, include_news=news,
        )
        print()
        print(f"  [OK] HTML 报告已生成: {path}")
    except Exception as e:
        logger.exception("生成 HTML 报告失败")
        _print_error_with_hint(e, "生成失败")
    _press_any_key()


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 增补内容）。"""
    _refresh_config()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        _check_and_warm_for_new_assets(holdings)
        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))
        today_str = datetime.now().strftime("%Y-%m-%d")

        from src.report.market_value import _generate_details
        print("  [..] 正在获取行情数据...")
        details = _generate_details(holdings, today_str)
        _check_network_available(details)
        print(f"  [OK] 行情数据获取完成，共 {len(details)} 条")

        from src.report.html_writer import write_html_report
        print("  [..] 正在生成 HTML 报告（含新闻）...")
        path = write_html_report(
            holdings, output_dir=output_dir,
            news_top_count=news_top_count, include_news=True,
            details=details,
        )
        print(f"  [OK] HTML 报告已生成: {path}")

        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=output_dir,
            news_top_count=news_top_count, details=details,
        )
    except Exception as e:
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _press_any_key()


def _show_llm_tui(macro_text: str, expert_text: str) -> None:
    """在 TUI 终端中展示 LLM 增补内容摘要。"""
    W = 72

    def _trim(text: str, max_len: int = 280) -> str:
        if len(text) <= max_len:
            return text
        cut = text[:max_len]
        last_period = cut.rfind("。")
        if last_period > max_len // 2:
            return cut[:last_period + 1]
        return cut + "…"

    def _print_box(title: str, body: str) -> None:
        border = "─" * (W - 2)
        print(f"  ┌{border}┐")
        print(f"  │ {title:<{W - 3}}│")
        print(f"  ├{border}┤")
        for line in body.split("\n"):
            for chunk in [line[i:i + W - 4] for i in range(0, max(len(line), 1), W - 4)]:
                print(f"  │ {chunk:<{W - 3}}│")
        print(f"  └{border}┘")

    if macro_text:
        _print_box("全球政经局势", _trim(macro_text.strip(), 200))
        print()

    if expert_text:
        phase3 = ""
        for kw in ("定音锤", "Phase 3", "⚖"):
            idx = expert_text.find(kw)
            if idx >= 0:
                phase3 = expert_text[idx:]
                break
        phase1 = ""
        for kw in ("召集令", "Phase 1", "🕵"):
            idx = expert_text.find(kw)
            if idx >= 0:
                end = expert_text.find("Phase 2", idx)
                if end < 0:
                    end = expert_text.find("**Phase 2", idx)
                if end < 0:
                    end = expert_text.find("圆桌", idx)
                if end < 0:
                    end = idx + 400
                phase1 = expert_text[idx:end]
                break

        parts = [p for p in [phase1, phase3] if p]
        body = _trim("\n".join(parts) if parts else expert_text.strip(), 500)
        _print_box("智囊团核心观点", body)
    print()


def _cmd_generate_full() -> None:
    """生成包含所有内容的全系列报告（Excel + HTML + 新闻 + LLM 增补内容）。"""
    _refresh_config()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        _check_and_warm_for_new_assets(holdings)
        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))

        from src.fetcher import fetch_indices, fetch_us_indices
        from src.report.market_value import _generate_details, classify_holdings
        from src.report.penetration import compute_penetration_top10

        today_str = datetime.now().strftime("%Y-%m-%d")
        details = _generate_details(holdings, today_str)
        _check_network_available(details)
        total_mv = sum(d.market_value for d in details)
        total_cost = sum(d.cost for d in details)
        total_profit = sum(d.profit for d in details)
        total_today_profit = sum(d.today_profit for d in details)
        categories = classify_holdings(holdings)

        with ThreadPoolExecutor(max_workers=2) as _idx_ex:
            _a_fut = _idx_ex.submit(fetch_indices)
            _us_fut = _idx_ex.submit(fetch_us_indices)
            a_indices = _a_fut.result()
            us_indices = _us_fut.result()
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
            }
            for d in details
        ]

        from src.llm_client import generate_all_llm
        from src.providers.akshare_extras import get_sector_fund_flow
        from src.report.news_correlation import build_news_data

        print("  [..] 正在并行获取新闻 + LLM 内容...")

        _sector_flow = get_sector_fund_flow()

        news_data: list = []
        news_llm_meta: dict = {}
        llm_content = (None, None)
        llm_cached = (False, False)

        with ThreadPoolExecutor(max_workers=2) as _llm_ex:

            def _run_llm():
                return generate_all_llm(
                    a_indices, us_indices, total_mv, total_cost, total_profit,
                    total_today_profit, len(holdings), categories,
                    penetrated_assets=penetrated_assets,
                    holdings_details=holdings_details,
                    sector_flow=_sector_flow, force=False,
                )

            _news_fut = _llm_ex.submit(
                build_news_data, holdings, news_top_count, penetrated_assets,
            )
            _llm_fut = _llm_ex.submit(_run_llm)

            for fut in as_completed([_news_fut, _llm_fut]):
                if fut is _llm_fut:
                    llm_macro, llm_expert, macro_cached, expert_cached = fut.result()
                    llm_content = (llm_macro, llm_expert)
                    llm_cached = (macro_cached, expert_cached)
                    tag = "缓存" if macro_cached and expert_cached else "LLM"
                    print(f"  [OK] {tag} 内容生成完成")
                else:
                    news_data, news_llm_meta = fut.result()
                    print(f"  [OK] 新闻获取完成，共 {len(news_data)} 条")

        from src.report.html_writer import write_html_report
        print("  [..] 正在生成 HTML 报告（含新闻 + LLM 增补内容）...")
        try:
            path = write_html_report(
                holdings, output_dir=output_dir,
                news_top_count=news_top_count, include_news=True,
                llm_content=llm_content, details=details,
                news_data=news_data, news_llm_meta=news_llm_meta,
            )
            print(f"  [OK] HTML 报告已生成: {path}")
        except Exception as e:
            logger.exception("HTML 报告写入失败")
            print(f"  [ERR] HTML 报告生成失败: {e}")
            print("  [..] 继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=output_dir,
            news_top_count=news_top_count, include_llm=True,
            llm_content=llm_content, show_llm_in_tui=True,
            details=details, a_indices=a_indices, us_indices=us_indices,
            news_data=news_data, llm_cached=llm_cached,
            news_llm_meta=news_llm_meta,
        )
    except Exception as e:
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _press_any_key()


# ── 配置命令 ──────────────────────────────────────────────


def _cmd_config_dir() -> None:
    """配置持仓目录。"""
    _refresh_config()
    config = get_config_cache() or {}
    current = config.get("holdings_dir", "")
    print(f"  当前目录: {current}")
    print("  请输入新目录路径（留空则不修改）:")
    try:
        new_dir = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if new_dir:
        set_config("holdings_dir", new_dir)
        _refresh_config()
        print(f"  [OK] 目录已更新为: {new_dir}")
    else:
        print("  未修改")


def _cmd_config_filename() -> None:
    """配置持仓文件名。"""
    _refresh_config()
    config = get_config_cache() or {}
    current = config.get("holdings_filename", "")
    files = list_xlsx_files(config.get("holdings_dir", ""))
    if files:
        print("  当前目录中的 xlsx 文件:")
        for i, f in enumerate(files, 1):
            print(f"    [{i}] {os.path.basename(f)}")
        print()
    print(f"  当前文件名: {current}")
    print("  请输入文件名（留空则不修改）:")
    try:
        new_name = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if new_name:
        set_config("holdings_filename", new_name)
        _refresh_config()
        print(f"  [OK] 文件名已更新为: {new_name}")
    else:
        print("  未修改")


def _cmd_config_output_dir() -> None:
    """配置报告输出目录。"""
    _refresh_config()
    config = get_config_cache() or {}
    current = config.get("output_dir", "reports")
    print(f"  当前输出目录: {current}")
    print("  请输入新的报告输出目录路径（留空则不修改）:")
    try:
        new_dir = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if new_dir:
        set_config("output_dir", new_dir)
        _refresh_config()
        print(f"  [OK] 输出目录已更新为: {new_dir}")
    else:
        print("  未修改")


# ── 缓存刷新命令 ─────────────────────────────────────────


def _cmd_update_basic_cache() -> None:
    """更新基础类缓存。"""
    from src.cache import clear, clear_by_prefix
    from src.fetcher import fetch_fund_benchmark, fetch_fund_holdings, fetch_fund_rankings
    from src.report.fund_performance import _is_fund

    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        print(f"  [OK] 共 {len(holdings)} 条持仓记录")

        funds = [h for h in holdings if _is_fund(h)]
        if not funds:
            print("  [!!] 未检测到基金持仓，无需更新基础缓存")
            _press_any_key()
            return

        print()
        print("  [..] 清除旧缓存...")
        clear_by_prefix("fund_perf_")
        clear_by_prefix("fund_hold_")
        clear("fund_benchmarks")
        clear_by_prefix("news_")
        clear_by_prefix("llm_news_corr_")
        clear_by_prefix("industry_")
        clear_by_prefix("dividend_")
        clear_by_prefix("profit_forecast_")
        clear_by_prefix("sector_flow_")
        print("  [OK] 旧缓存已清除（含 news_ + llm_news_corr_ + industry_ +"
              " dividend_ + profit_forecast_ + sector_flow_ 缓存）")

        print()
        from concurrent.futures import ThreadPoolExecutor, as_completed
        print(f"  [..]   并行获取 {len(funds)} 只基金的数据（最多 3 路并发）...")

        def _refresh_one_fund(fund):
            perf_result = fetch_fund_rankings(fund.code)
            perf_ok = bool(perf_result)
            hold_data = fetch_fund_holdings(fund.code)
            hold_ok = bool(hold_data and hold_data.get("holdings"))
            hold_count = len(hold_data["holdings"]) if hold_data and hold_data.get("holdings") else 0
            bm = fetch_fund_benchmark(fund.code)
            bm_ok = bool(bm and bm != "--")
            return (fund.code, fund.name, perf_ok, hold_ok, hold_count, bm_ok, bm if bm_ok else "")

        perf_ok = hold_ok = bm_ok = 0
        with ThreadPoolExecutor(max_workers=3) as executor:
            fut_to_fund = {executor.submit(_refresh_one_fund, f): f for f in funds}
            for future in as_completed(fut_to_fund):
                code, name, p_ok, h_ok, h_cnt, b_ok, bm_str = future.result()
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

        print()
        print(f"  {'=' * 40}")
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

        # ── 盈利预测 + 行业资金流向 ──
        print()
        print("  [..]   刷新全量盈利预测和行业资金流向...")
        from src.providers.akshare_extras import (
            _memo_clear, get_profit_forecast, get_sector_fund_flow,
        )
        _memo_clear()
        pf_ok = sf_ok = 0
        with ThreadPoolExecutor(max_workers=2) as _pool:
            _pf_fut = _pool.submit(get_profit_forecast)
            _sf_fut = _pool.submit(get_sector_fund_flow)
            pf_data = _pf_fut.result()
            sf_data = _sf_fut.result()
            if pf_data:
                pf_ok = len(pf_data)
            if sf_data:
                sf_ok = len(sf_data)
        if pf_ok:
            print(f"  [OK]   profit_forecast              ({pf_ok} 只股票)")
        else:
            print("  [!]   profit_forecast              获取失败")
        if sf_ok:
            print(f"  [OK]   sector_flow                  ({sf_ok} 个行业)")
        else:
            print("  [!]   sector_flow                  获取失败")
    except Exception as e:
        logger.exception("更新基础缓存失败")
        print(f"  [ERR] 更新失败: {e}")
    _press_any_key()


def _cmd_update_position_cache() -> None:
    """更新持仓类缓存。"""
    from src.cache import clear_by_prefix
    from src.fetcher import fetch_indices, fetch_market_data, fetch_us_indices
    from concurrent.futures import ThreadPoolExecutor, as_completed

    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        print(f"  [OK] 共 {len(holdings)} 条持仓记录")

        print()
        print("  [..] 清除旧缓存...")
        price_count = clear_by_prefix("price_")
        index_count = clear_by_prefix("index_")
        expert_count = clear_by_prefix("llm_expert_review_")
        macro_count = clear_by_prefix("llm_global_macro_")
        print(f"  [OK] 价格缓存 {price_count} 条 + 指数缓存 {index_count} 条 + "
              f"智囊团复盘 {expert_count} 条 + 全球政经 {macro_count} 条 已清除")

        print()
        print(f"  [..]   并行获取 {len(holdings)} 条持仓的价格/净值（最多 5 路并发）...")
        price_ok = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            fut_to_h = {executor.submit(fetch_market_data, h.code, h.name): h for h in holdings}
            for future in as_completed(fut_to_h):
                h = fut_to_h[future]
                try:
                    result = future.result()
                    if result and result.get("price", 0) > 0:
                        price_ok += 1
                        print(f"  [OK]   {h.name} ({h.code}) → {result['price']:.4f}")
                    else:
                        print(f"  [!]   {h.name} ({h.code}) → 失败")
                except Exception as e:
                    print(f"  [ERR]  {h.name} ({h.code}) → {e}")

        print()
        print("  [..] 获取市场指数...")
        a_idx = fetch_indices()
        print(f"  [OK] A 股指数: {len(a_idx)} 个")
        us_idx = fetch_us_indices()
        print(f"  [OK] 美股指数: {len(us_idx)} 个")

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
    from src.cache import cleanup_expired, get_cache_dir
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
    from src.cache import cleanup_expired, get_cache_dir, get_cache_stats
    cache_dir = get_cache_dir()
    stats = get_cache_stats()
    print(f"  缓存目录: {cache_dir}")
    print(f"  文件总数: {stats['total_files']}")
    print(f"  总大小:   {stats['total_size_bytes'] / 1024:.0f} KB")
    print(f"  按前缀分类:")
    for prefix, count in sorted(stats.get("by_prefix", {}).items()):
        print(f"    {prefix}_*: {count} 个文件")
    print()
    print("  [..] 正在检查过期文件...")
    expired = cleanup_expired(dry_run=True)
    print(f"  过期文件: {expired} 个（可通过菜单 [3] 清理）")
    _press_any_key()


# ── 执行菜单项 ─────────────────────────────────────────────


def _execute_item(sel: int) -> None:
    """执行第 sel 项菜单的回调或退出。"""
    global _busy
    _, _label, callback, is_exit = MENU_ITEMS[sel]
    if is_exit:
        from src.tui_menu import _exit_app
        _exit_app()
    if callback is not None:
        if _busy:
            return
        _busy = True
        try:
            callback()
        except KeyboardInterrupt:
            print()
            print("  操作已取消")
            _press_any_key()
        finally:
            _busy = False
