#!/usr/bin/env python3
"""投资分析系统 — TUI 主入口。"""

from __future__ import annotations

import os
import sys
from datetime import datetime

# 确保项目根目录在 sys.path 中，并切换工作目录
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
os.chdir(_project_root)

from typing import Callable, Optional

from src.config import get_config, get_llm_config, init_config, set_config
from src.logger import setup_logger
from src.reader import get_xlsx_info, list_xlsx_files, read_holdings
from src.tui import KEY_CTRL_C, KEY_DOWN, KEY_ENTER, KEY_UP, get_key

logger = setup_logger()

# 配置缓存（每次菜单循环读一次，配置命令后刷新）
_config_cache: dict | None = None

# ── 菜单定义 ──────────────────────────────────────────────

# 每个菜单项：(快捷键, 显示标签, 回调函数, 是否退出项)
MenuItem = tuple[str, str, Optional[Callable[[], None]], bool]

MENU_ITEMS: list[MenuItem] = [
    ("E", "生成基础版Excel分析报告", None, False),
    ("N", "生成包含新闻的Excel分析报告", None, False),
    ("H", "生成基础版HTML分析报告", None, False),
    ("B", "生成全系列包含新闻的报告(Excel+HTML)", None, False),
    ("L", "生成全系列完整版报告(Excel+HTML)", None, False),
    ("C", "配置持仓信息目录", None, False),
    ("F", "配置持仓信息文件名", None, False),
    ("R", "配置报告输出目录", None, False),
    ("1", "更新基础类缓存", None, False),
    ("2", "更新持仓类缓存", None, False),
    ("3", "清理过期缓存文件", None, False),
    ("4", "查看缓存统计信息", None, False),
    ("X", "退出", None, True),
]


# ── 运行时绑定回调 ────────────────────────────────────────


def _bind_callbacks() -> None:
    """运行时将函数引用填入 MENU_ITEMS。"""
    callbacks: dict[str, Callable[[], None]] = {
        "E": _cmd_generate_excel,
        "N": _cmd_generate_excel_with_news,
        "H": _cmd_generate_html,
        "B": _cmd_generate_both,
        "L": _cmd_generate_full,
        "C": _cmd_config_dir,
        "F": _cmd_config_filename,
        "R": _cmd_config_output_dir,
        "1": _cmd_update_basic_cache,
        "2": _cmd_update_position_cache,
        "3": _cmd_cleanup_cache,
        "4": _cmd_show_cache_stats,
    }
    for i, (key, _label, _cb, is_exit) in enumerate(MENU_ITEMS):
        MENU_ITEMS[i] = (key, _label, callbacks.get(key), is_exit)


# ── 辅助函数 ──────────────────────────────────────────────


def _print_error_with_hint(e: Exception, prefix: str = "操作失败") -> None:
    """输出带友好提示的错误信息。

    自动识别网络相关错误并给出针对性提示。
    """
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


def _press_any_key() -> None:
    """等待用户按任意键继续。支持 Ctrl+C 退出。"""
    print("  按任意键返回菜单...")
    k = get_key()
    if k == KEY_CTRL_C:
        _exit_app()


def _exit_app() -> None:
    """打印退出信息并终止程序。"""
    print()
    print("  感谢使用，再见！")
    sys.exit(0)


def _print_sep(char: str = "=", width: int = 56) -> None:
    print(char * width)


# ── 界面输出 ──────────────────────────────────────────────


def _print_header() -> None:
    """打印程序标题头（仅启动时一次）。"""
    _print_sep()
    print("           投资分析报告生成系统")
    _print_sep()


def _render_menu(sel: int) -> None:
    """打印带选择指示器的菜单。"""
    print()
    for i, (key, label, _cb, is_exit) in enumerate(MENU_ITEMS):
        if i == sel:
            print(f"  > [{key}] {label}")
        else:
            print(f"    [{key}] {label}")
    print()
    print("  方向键移动 | Enter 确认 | 字母/数字键直达 | Ctrl+C 退出")
    print()


def _refresh_config() -> dict:
    """刷新并返回配置缓存。"""
    global _config_cache
    _config_cache = get_config()
    return _config_cache


def _show_config() -> None:
    """显示当前配置及 LLM 配置状态。"""
    config = _config_cache if _config_cache is not None else _refresh_config()
    holdings_path = os.path.join(config["holdings_dir"], config["holdings_filename"])
    print(f"  持仓目录: {config['holdings_dir']}")
    print(f"  持仓文件: {config['holdings_filename']}")
    print(f"  输出目录: {config.get('output_dir', 'reports')}")
    print(f"  新闻 TOP: {config.get('news_top_count', '100')} 条")
    if os.path.exists(holdings_path):
        print(f"  状态: [OK] 文件就绪")
    else:
        print(f"  状态: [!!] 文件未找到")
    # LLM 配置状态显示
    _show_llm_config_status()
    print()


def _show_llm_config_status() -> None:
    """显示 LLM 配置状态（绿色已配置 / 红色未配置）。"""
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"

    llm_config = get_llm_config()
    if llm_config and llm_config.get("api_key") and llm_config.get("provider"):
        provider = llm_config["provider"]
        model = llm_config.get("model") or "默认"
        endpoint = llm_config.get("endpoint") or "默认"
        # 截断 endpoint 显示，保留域名部分
        ep_display = endpoint.split("/")[2] if endpoint and endpoint != "默认" else endpoint
        print(f"  LLM: {GREEN}已配置{RESET}  provider={provider}  model={model}  endpoint={ep_display}")
    else:
        print(f"  LLM: {RED}未配置{RESET}（配置 data/config/llm.json 后重启生效）")


# ── 配置命令 ──────────────────────────────────────────────


def _cmd_config_dir() -> None:
    """配置持仓目录。"""
    _refresh_config()
    current = _config_cache["holdings_dir"]
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
    current = _config_cache["holdings_filename"]
    files = list_xlsx_files(_config_cache["holdings_dir"])
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
    current = _config_cache.get("output_dir", "reports")
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


# ── 持仓变更检测与缓存预热 ─────────────────────────────────


def _check_and_warm_for_new_assets(holdings: list) -> None:
    """检测持仓是否变化，若有新增资产则主动预热其缓存数据。

    当检测到持仓变更时：
      1. 清除关联的合并缓存（fund_benchmarks.json / penetration_cache.json）
      2. 对新资产主动获取行情、业绩排名、持仓明细
         填充 price_{code}.json / fund_perf_{code}.json / fund_hold_{code}.json

    Args:
        holdings: 当前持仓列表
    """
    from src.cache import check_and_refresh_caches
    from src.fetcher import fetch_fund_holdings, fetch_fund_rankings, fetch_market_data
    from src.report.fund_performance import _is_fund

    new_codes = check_and_refresh_caches(holdings)
    if not new_codes:
        return

    code_map = {h.code: h for h in holdings}
    print(f"  [..] 检测到 {len(new_codes)} 个新增资产，正在预热缓存...")

    for code in new_codes:
        h = code_map.get(code)
        name = h.name if h else code

        # 预热价格/净值缓存 → price_{code}.json
        print(f"  [..]   新增 {name} ({code}) — 获取行情...", end="")
        result = fetch_market_data(code, name)
        if result and result.get("price", 0) > 0:
            print(f" {result['price']:.4f}")
        else:
            print(" 失败")

        # 若是基金，预热业绩排名 + 持仓明细
        if h and _is_fund(h):
            # → fund_perf_{code}.json
            print(f"  [..]   新增基金 {name} ({code}) — 获取业绩排名...", end="")
            perf = fetch_fund_rankings(code)
            if perf:
                print(" OK")
            else:
                print(" 失败")

            # → fund_hold_{code}.json
            print(f"  [..]   新增基金 {name} ({code}) — 获取持仓明细...", end="")
            holds = fetch_fund_holdings(code)
            if holds and holds.get("holdings"):
                print(f" {len(holds['holdings'])} 条")
            else:
                print(" 无数据")

    print(f"  [OK] 新增资产缓存预热完成")


# ── 文件选择 ──────────────────────────────────────────────


def _select_holdings_file() -> str | None:
    """让用户选择持仓文件，返回绝对路径；未找到时返回 None。"""
    _refresh_config()
    specific_path = os.path.join(_config_cache["holdings_dir"], _config_cache["holdings_filename"])

    if os.path.exists(specific_path):
        return os.path.abspath(specific_path)

    # 配置文件中的文件不存在，尝试列出目录下所有 xlsx
    dir_path = _config_cache["holdings_dir"]
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


# ── 生成命令（占位） ──────────────────────────────────────


def _cmd_generate_excel() -> None:
    """生成 Excel 分析报告（必选内容）。"""
    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return
    try:
        holdings = read_holdings(filepath)
        _check_and_warm_for_new_assets(holdings)
        _generate_excel_report(holdings, include_news=False, output_dir=_config_cache.get("output_dir", "reports"))
    except Exception as e:
        logger.exception("生成 Excel 报告失败")
        _print_error_with_hint(e, "生成失败")
    _press_any_key()


def _cmd_generate_excel_with_news() -> None:
    """生成包含新闻的 Excel 分析报告。"""
    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return
    try:
        holdings = read_holdings(filepath)
        _check_and_warm_for_new_assets(holdings)
        output_dir = _config_cache.get("output_dir", "reports")
        news_top_count = int(_config_cache.get("news_top_count", 100))
        _generate_excel_report(holdings, include_news=True, output_dir=output_dir, news_top_count=news_top_count)
    except Exception as e:
        logger.exception("生成 Excel（新闻）报告失败")
        _print_error_with_hint(e, "生成失败")
    _press_any_key()


def _generate_excel_report(holdings: list, include_news: bool = False, output_dir: str = "reports", news_top_count: int = 100, include_llm: bool = False, force_llm: bool = False, show_llm_in_tui: bool = False, llm_content: tuple | None = None, details: list | None = None, a_indices: list | None = None, us_indices: list | None = None) -> None:
    """生成 Excel 报告的核心逻辑。

    Args:
        llm_content: 可选预生成内容 (macro_html, expert_html)，
            传入时跳过内部 LLM 调用直接使用此内容。
        details: 可选预计算市值核算明细行，传入时跳过内部行情获取。
        a_indices: 可选预获取的 A 股指数。
        us_indices: 可选预获取的美股指数。
    """
    from datetime import datetime

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

    # 第 1 页：市值核算（复用外部传入或内部生成）
    if details is not None:
        logger.info("复用外部传入的市值核算数据，共 %d 条", len(details))
        total_mv = sum(d.market_value for d in details)
        total_cost = sum(d.cost for d in details)
        total_profit = sum(d.profit for d in details)
        today_profit = sum(d.today_profit for d in details)
        # 仍需要 workbook 写市值核算行
        ws1 = wb.create_sheet()
        write_market_value_sheet(ws1, holdings, details=details)
    else:
        logger.info("正在获取行情数据（首次耗时较长，后续使用缓存）...")
        logger.info("正在生成市值核算...")
        ws1 = wb.create_sheet()
        total_mv, total_cost, total_profit, today_profit, details = \
            write_market_value_sheet(ws1, holdings)

    # 计算汇总所需数据
    categories = classify_holdings(holdings)
    up_status = price_update_status(details, get_last_trading_day())

    # 获取指数数据（复用外部传入或内部获取）
    if a_indices is None:
        logger.info("正在获取市场指数...")
        a_idx_dict = fetch_indices()
        a_indices = list(a_idx_dict.values())
    if us_indices is None:
        us_idx_dict = fetch_us_indices()
        us_indices = list(us_idx_dict.values())

    # 第 2 页：汇总
    logger.info("正在生成汇总...")
    ws2 = wb.create_sheet()
    write_summary_sheet(
        ws2, total_mv, total_cost, total_profit, today_profit,
        categories=categories,
        update_status=up_status,
        a_indices=a_indices,
        us_indices=us_indices,
    )

    # 第 3 页：分类汇总
    logger.info("正在生成分类汇总...")
    ws3 = wb.create_sheet()
    write_category_sheet(ws3, holdings, details)

    # 计算穿透 TOP10（仅一次，后续多处复用）
    pen_result = compute_penetration_top10(holdings, details)

    # 第 4 页：资产穿透 TOP10
    logger.info("正在生成资产穿透 TOP10...")
    ws4 = wb.create_sheet()
    write_penetration_sheet(ws4, holdings, details, penetration_data=pen_result)

    # 第 5 页：基金业绩分析
    logger.info("正在获取基金业绩排名...")
    ws5 = wb.create_sheet()
    write_fund_performance_sheet(ws5, holdings, details)

    # 第 6 页（可选）：财经新闻热点
    if include_news:
        logger.info("正在获取财经新闻（含穿透资产关键词）...")
        penetrated_assets = pen_result.get("top10", []) if pen_result else []

        from src.report.news_correlation import build_news_data, write_news_sheet
        news_data = build_news_data(holdings, top_n=news_top_count, penetrated_assets=penetrated_assets)
        ws6 = wb.create_sheet()
        write_news_sheet(ws6, news_data)

    # 第 7/8 页（可选）：LLM 增补内容
    if include_llm:
        logger.info("正在生成 LLM 增补内容...")
        try:
            from src.report.llm_content import write_llm_sheets
            macro_text, expert_text = write_llm_sheets(wb, holdings, details, output_dir, total_mv, total_cost, total_profit, today_profit, categories, penetration_data=pen_result, force_llm=force_llm, llm_content=llm_content, a_indices=a_indices, us_indices=us_indices)
            logger.info("LLM 增补内容已生成")
        except ImportError:
            logger.warning("LLM 增补模块 (src.report.llm_content) 未就绪，跳过")
            macro_text = expert_text = ""
        except Exception as e:
            logger.exception("生成 LLM 增补内容失败")
            macro_text = expert_text = ""

        # TUI 展示 LLM 增补内容摘要
        if show_llm_in_tui and (macro_text or expert_text):
            _show_llm_tui(macro_text, expert_text)

    # 保存
    path = save_workbook(wb, output_dir=output_dir)
    logger.info("Excel 报告已生成: %s", path)
    logger.info("总市值: %.2f元, 总成本: %.2f元, 总盈亏: %.2f元, 本日盈亏: %.2f元",
                total_mv, total_cost, total_profit, today_profit)


def _cmd_generate_html(news: bool = False) -> None:
    """生成 基础的 HTML 分析报告（不含 LLM 增补内容）。"""
    _refresh_config()

    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        print(f"  [OK] 成功读取 {len(holdings)} 条持仓记录")
        _check_and_warm_for_new_assets(holdings)

        print("  [..] 正在获取行情数据并生成 HTML 报告...")

        from src.report.html_writer import write_html_report
        news_top_count = int(_config_cache.get("news_top_count", 100))
        path = write_html_report(holdings, output_dir=_config_cache.get("output_dir", "reports"), news_top_count=news_top_count, include_news=news)

        print()
        print(f"  [OK] HTML 报告已生成: {path}")

    except Exception as e:
        logger.exception("生成 HTML 报告失败")
        _print_error_with_hint(e, "生成失败")

    _press_any_key()


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 增补内容）。

    预计算市值核算一次，HTML 和 Excel 两处复用，避免重复行情 HTTP 请求。
    """
    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        from datetime import datetime

        holdings = read_holdings(filepath)
        _check_and_warm_for_new_assets(holdings)
        output_dir = _config_cache.get("output_dir", "reports")
        news_top_count = int(_config_cache.get("news_top_count", 100))
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 预计算市值核算明细（仅一次）
        from src.report.market_value import _generate_details
        print("  [..] 正在获取行情数据...")
        details = _generate_details(holdings, today_str)
        print(f"  [OK] 行情数据获取完成，共 {len(details)} 条")

        # HTML 报告
        from src.report.html_writer import write_html_report
        print("  [..] 正在生成 HTML 报告（含新闻）...")
        path = write_html_report(
            holdings, output_dir=output_dir,
            news_top_count=news_top_count, include_news=True,
            details=details,
        )
        print(f"  [OK] HTML 报告已生成: {path}")

        # Excel 报告
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
    """在 TUI 终端中展示 LLM 增补内容摘要。

    从 LLM 文本中提取关键段落，用彩色框展示。
    全球政经局势显示前 200 字，智囊团复盘抽取 Phase 1/3 核心观点。
    """
    W = 72  # 框宽度

    def _trim(text: str, max_len: int = 280) -> str:
        """截断文本到指定长度，保留最后一个完整句号。"""
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

    # 全球政经局势 — 前 200 字
    if macro_text:
        macro_trimmed = _trim(macro_text.strip(), 200)
        _print_box("全球政经局势", macro_trimmed)
        print()

    # 智囊团深度复盘 — 提取定音锤段落 + 核心观点
    if expert_text:
        # 尝试提取 Phase 3（定音锤）
        phase3 = ""
        for kw in ("定音锤", "Phase 3", "⚖"):
            idx = expert_text.find(kw)
            if idx >= 0:
                phase3 = expert_text[idx:]
                break
        # 再尝试提取 Phase 1（矛盾）
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

        # 拼接展示
        parts = [p for p in [phase1, phase3] if p]
        if parts:
            body = _trim("\n".join(parts), 500)
        else:
            body = _trim(expert_text.strip(), 500)
        _print_box("智囊团核心观点", body)

    print()


def _cmd_generate_full() -> None:
    """生成包含所有内容的全系列报告（Excel + HTML + 新闻 + LLM 增补内容）。

    LLM 内容预先生成一次，传递给 Excel 和 HTML 两个 writer 复用，
    避免重复调用 API 浪费 token 和时间。
    """
    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        from datetime import datetime

        holdings = read_holdings(filepath)
        _check_and_warm_for_new_assets(holdings)
        output_dir = _config_cache.get("output_dir", "reports")
        news_top_count = int(_config_cache.get("news_top_count", 100))

        # ── 预计算 LLM 所需数据（一次调用，两处复用）────────
        from src.fetcher import fetch_indices, fetch_us_indices
        from src.report.market_value import _generate_details, classify_holdings
        from src.report.penetration import compute_penetration_top10

        today_str = datetime.now().strftime("%Y-%m-%d")
        details = _generate_details(holdings, today_str)
        total_mv = sum(d.market_value for d in details)
        total_cost = sum(d.cost for d in details)
        total_profit = sum(d.profit for d in details)
        total_today_profit = sum(d.today_profit for d in details)
        categories = classify_holdings(holdings)
        a_idx_dict = fetch_indices()
        us_idx_dict = fetch_us_indices()
        a_indices = list(a_idx_dict.values())
        us_indices = list(us_idx_dict.values())
        pen_result = compute_penetration_top10(holdings, details)
        penetrated_assets = (pen_result or {}).get("top10", [])

        # 构建持仓明细（供 LLM 引用具体品种，防止虚构代码）
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

        # ── LLM 生成（仅一次，缓存指纹避免重复）────────────────
        from src.cache import compute_holdings_fingerprint, get as cache_get, set as cache_set
        from src.llm_client import generate_all_llm

        fp = compute_holdings_fingerprint(holdings)
        prev_fp = cache_get("llm_holdings_fp", 86400)
        force_llm = (prev_fp is None or prev_fp != fp)
        if force_llm:
            cache_set("llm_holdings_fp", fp)

        llm_macro, llm_expert = generate_all_llm(
            a_indices, us_indices, total_mv, total_cost, total_profit,
            total_today_profit, len(holdings), categories,
            penetrated_assets=penetrated_assets,
            holdings_details=holdings_details, force=force_llm,
        )
        llm_content = (llm_macro, llm_expert)

        # ── HTML 报告 ──────────────────────────────────────────
        from src.report.html_writer import write_html_report
        print("  [..] 正在生成 HTML 报告（含新闻 + LLM 增补内容）...")
        path = write_html_report(
            holdings, output_dir=output_dir,
            news_top_count=news_top_count, include_news=True,
            llm_content=llm_content, details=details,
        )
        print(f"  [OK] HTML 报告已生成: {path}")

        # ── Excel 报告 ─────────────────────────────────────────
        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=output_dir,
            news_top_count=news_top_count, include_llm=True,
            llm_content=llm_content, show_llm_in_tui=True,
            details=details, a_indices=a_indices, us_indices=us_indices,
        )

    except Exception as e:
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")

    _press_any_key()


# ── 缓存刷新命令 ─────────────────────────────────────────


def _cmd_update_basic_cache() -> None:
    """更新基础类缓存 — 清除旧缓存 → 重新获取基金业绩/持仓/基准。

    缓存文件：
      fund_perf_{code}.json        → 基金业绩评价+同类排名（单条，由 fetch_fund_rankings 自动写入）
      fund_hold_{code}.json        → 各基金底层持仓权重（单条，由 fetch_fund_holdings 自动写入）
      fund_benchmarks.json         → 业绩比较基准
    """
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
        print(f"  [OK] 共 {len(holdings)} 条持仓记录")

        # 筛选基金
        funds = [h for h in holdings if _is_fund(h)]
        if not funds:
            print("  [!!] 未检测到基金持仓，无需更新基础缓存")
            _press_any_key()
            return

        # 1) 清除旧缓存
        print()
        print("  [..] 清除旧缓存...")
        clear_by_prefix("fund_hold_")
        clear("fund_benchmarks")
        print("  [OK] 旧缓存已清除")

        # 2) 获取基金业绩排名 + 持仓 + 基准
        print()
        print(f"  [..] 获取 {len(funds)} 只基金的业绩排名、持仓数据和业绩基准...")
        perf_ok = hold_ok = bm_ok = 0
        for idx, fund in enumerate(funds, 1):
            # 业绩排名（fetch_fund_rankings 自动写入 fund_perf_{code}.json）
            print(f"  [..]   [{idx}/{len(funds)}] {fund.name} ({fund.code}) — 业绩排名...", end="")
            result = fetch_fund_rankings(fund.code)
            if result:
                perf_ok += 1
                print(" OK")
            else:
                print(" 失败")

            # 持仓（fetch_fund_holdings 自动写入 fund_hold_{code}.json）
            print(f"  [..]   [{idx}/{len(funds)}] {fund.name} ({fund.code}) — 持仓...", end="")
            holdings_data = fetch_fund_holdings(fund.code)
            if holdings_data and holdings_data.get("holdings"):
                hold_ok += 1
                print(f" {len(holdings_data['holdings'])} 条")
            else:
                print(" 无数据")

            # 业绩基准（fetch_fund_benchmark 自动写入 fund_benchmarks.json）
            print(f"  [..]   [{idx}/{len(funds)}] {fund.name} ({fund.code}) — 业绩基准...", end="")
            bm = fetch_fund_benchmark(fund.code)
            if bm and bm != "--":
                bm_ok += 1
                print(f" {bm}")
            else:
                print(" 未找到")

        # 汇总
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

    except Exception as e:
        logger.exception("更新基础缓存失败")
        print(f"  [ERR] 更新失败: {e}")

    _press_any_key()


def _cmd_update_position_cache() -> None:
    """更新持仓类缓存 — 清除旧缓存 → 重新获取价格/指数/穿透数据。

    缓存文件：
      price_{code}.json         → 单条持仓价格/净值（由 fetch_market_data 自动写入）
      portfolio_latest.json    → 持仓主数据
      penetration_cache.json   → 穿透 TOP10 计算结果
      智囊团深度复盘缓存        → 持仓变化时 LLM 专家复盘自动失效
    """
    from src.cache import clear, clear_by_prefix, set as cache_set
    from src.fetcher import fetch_indices, fetch_market_data, fetch_us_indices
    from src.report.market_value import DetailRow, classify_holdings
    from src.report.penetration import compute_penetration_top10

    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        print(f"  [OK] 共 {len(holdings)} 条持仓记录")

        # 1) 清除旧缓存
        print()
        print("  [..] 清除旧缓存...")
        price_count = clear_by_prefix("price_")
        index_count = clear_by_prefix("index_")
        clear("portfolio_latest")
        clear("penetration_cache")
        expert_count = clear_by_prefix("llm_expert")
        print(f"  [OK] 价格缓存 {price_count} 条 + 指数缓存 {index_count} 条 + "
              f"穿透缓存 + 持仓主数据 + 智囊团复盘 {expert_count} 条 已清除")

        # 2) 获取所有持仓的最新价格/净值
        print()
        print(f"  [..] 获取 {len(holdings)} 条持仓的最新价格/净值...")
        price_ok = 0
        portfolio_items = []
        for idx, h in enumerate(holdings, 1):
            print(f"  [..]   [{idx}/{len(holdings)}] {h.name} ({h.code})...", end="")
            result = fetch_market_data(h.code, h.name)
            if result and result.get("price", 0) > 0:
                price_ok += 1
                price = result["price"]
                mv = round(price * h.shares, 2)
                portfolio_items.append({
                    "name": h.name, "code": h.code,
                    "account": h.account, "shares": h.shares,
                    "cost_price": h.cost_price,
                    "price": price,
                    "yesterday_close": result.get("yesterday_close", 0),
                    "price_date": result.get("price_date", ""),
                    "source": result.get("source", ""),
                    "market_value": mv,
                })
                print(f" {price:.4f}")
            else:
                print(" 失败")

        # 3) 获取指数行情
        print()
        print("  [..] 获取市场指数...")
        print("  [..]   获取 A 股指数...", end="")
        a_idx = fetch_indices()
        print(f" {len(a_idx)} 个指数")
        print("  [..]   获取美股指数...", end="")
        us_idx = fetch_us_indices()
        print(f" {len(us_idx)} 个指数")

        # 写入组合主数据缓存
        categories = classify_holdings(holdings)
        portfolio_data = {
            "update_time": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_holdings": len(holdings),
            "items": portfolio_items,
            "categories": {k: len(v) for k, v in categories.items()},
        }
        cache_set("portfolio_latest", portfolio_data)
        print("  [OK]   持仓主数据 (portfolio_latest) 已缓存")

        # 5) 计算并缓存穿透 TOP10
        print()
        print("  [..]   计算资产穿透 TOP10...")

        # 先构建假的 DetailRow（因为 compute_penetration_top10 需要细节行）
        detail_rows = []
        for item in portfolio_items:
            dr = DetailRow(
                account=item["account"],
                name=item["name"],
                code=item["code"],
                price=item["price"],
                shares=item["shares"],
                market_value=item["market_value"],
                cost=round(item["cost_price"] * item["shares"], 2),
            )
            detail_rows.append(dr)

        pen_result = compute_penetration_top10(holdings, detail_rows)
        cache_set("penetration_cache", pen_result)

        top10_count = len(pen_result["top10"])
        merged_count = pen_result["summary"]["merged_count"]
        print(f"  [OK]   穿透 TOP10 已缓存 — 合并 {merged_count} 个标的，TOP10 {top10_count} 条")

        # 汇总
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
        if price_fail == 0:
            print(f"  [OK] portfolio_latest.json         (全量数据完整)")
        else:
            print(f"  [!] portfolio_latest.json         (已写入，但有 {price_fail} 条持仓缺价格)")
        if len(pen_result["top10"]) > 0:
            print(f"  [OK] penetration_cache.json        ({merged_count} 个合并标的, TOP10 {top10_count} 条)")
        else:
            print(f"  [!] penetration_cache.json        (穿透计算TOP10为空)")
        print(f"  ---")
        print(f"  缓存文件已写入 data/cache/ 目录")

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


# ── 从快捷键查找菜单索引 ──────────────────────────────────


def _index_by_key(key: str) -> int | None:
    """返回快捷键对应的菜单索引，未找到则返回 None。"""
    for i, (k, _label, _cb, _is_exit) in enumerate(MENU_ITEMS):
        if k == key:
            return i
    return None


# ── 执行菜单项 ─────────────────────────────────────────────


def _execute_item(sel: int) -> None:
    """执行第 sel 项菜单的回调或退出。"""
    _, _label, callback, is_exit = MENU_ITEMS[sel]
    if is_exit:
        _exit_app()
    if callback is not None:
        try:
            callback()
        except KeyboardInterrupt:
            print()
            print("  操作已取消")
            _press_any_key()


# ── 主循环 ──────────────────────────────────────────────


def main() -> None:
    """TUI 主循环。支持方向键导航 + Enter 确认 + 字母快捷键 + Ctrl+C。"""
    init_config()
    _bind_callbacks()

    # 启动时自动清理过期缓存（静默后台执行，仅日志记录）
    try:
        from src.cache import cleanup_expired
        removed = cleanup_expired(dry_run=False)
        if removed > 0:
            logger.info("启动时自动清理了 %d 个过期缓存文件", removed)
    except Exception:
        pass

    _print_header()
    sel: int = 0  # 当前选中项，默认第一项

    while True:
        _show_config()
        _render_menu(sel)

        key = get_key()

        if key == KEY_UP:
            sel = (sel - 1) % len(MENU_ITEMS)
        elif key == KEY_DOWN:
            sel = (sel + 1) % len(MENU_ITEMS)
        elif key == KEY_ENTER:
            _execute_item(sel)
        elif key == KEY_CTRL_C:
            _exit_app()
        elif len(key) == 1 and ("A" <= key <= "Z" or "a" <= key <= "z" or "0" <= key <= "9"):
            # 统一转为大写匹配菜单快捷键
            idx = _index_by_key(key.upper())
            if idx is not None:
                sel = idx
                _execute_item(idx)
            # else: 非菜单字母 -> 忽略


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("  感谢使用，再见！")
        sys.exit(0)
