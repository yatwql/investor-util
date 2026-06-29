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

from src.python.tui_menu import MENU_ITEMS, _press_any_key, _refresh_config, get_config_cache
from src.python.logger import setup_logger
from src.python.reader import get_xlsx_info, list_xlsx_files, read_holdings
from src.python.config import set_config, get_llm_config

logger = setup_logger()

_busy: bool = False  # 防连续按键保护

# 报告生成过程中的错误累计（每次生成开始时清空）
_generation_errors: list[str] = []


# ── 计时器 ──────────────────────────────────────────────────

import time as _time_module

_timing_records: list[tuple[str, float]] = []


class _Timer:
    """简单计时器上下文管理器，记录各模块耗时。"""

    def __init__(self, label: str) -> None:
        self.label = label
        self.start: float = 0.0

    def __enter__(self) -> '_Timer':
        self.start = _time_module.time()
        return self

    def __exit__(self, *args) -> None:
        elapsed = _time_module.time() - self.start
        _timing_records.append((self.label, elapsed))


def _print_llm_session_usage(usage: dict | None = None) -> None:
    """输出会话累计 LLM 用量（TUI 终端一行）。

    若 usage 为 None，自动调用 get_session_usage()。
    无调用记录时静默不输出。

    Args:
        usage: 可选的 get_session_usage() 返回值，避免重复导入
    """
    if usage is None:
        try:
            from src.python.llm_client import get_session_usage
            usage = get_session_usage()
        except Exception:
            return
    if not usage or usage.get("call_count", 0) == 0:
        return
    calls = usage["call_count"]
    total_tok = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    cost = usage.get("total_cost", 0.0)
    symbol = {"CNY": "¥", "USD": "$", "EUR": "€", "GBP": "£"}.get(usage.get("currency", "CNY"), "¥")
    print(f"  [OK] 本会话 LLM 累计：{calls} 次调用，{total_tok:,} tokens，费用 {symbol}{cost:.4f}")


def _print_timing_summary() -> None:
    """输出本次运行时各模块耗时排行。"""
    if not _timing_records:
        return
    total = sum(t for _, t in _timing_records)
    print()
    print(f"  ┌{'─' * 48}┐")
    print(f"  │  ⏱ 模块耗时排行（总计 {total:.1f}s）{' ' * 17}│")
    print(f"  ├{'─' * 48}┤")
    sorted_records = sorted(_timing_records, key=lambda x: -x[1])
    for label, t in sorted_records:
        pct = t / total * 100 if total > 0 else 0
        bar_len = int(pct / 100 * 24)
        bar = "█" * bar_len + "░" * (24 - bar_len)
        print(f"  │ {label:<18s} {t:>6.1f}s {pct:>5.1f}% {bar} │")
    print(f"  └{'─' * 48}┘")
    _timing_records.clear()


def _add_error(msg: str) -> None:
    """向当前会话的错误汇总列表添加一条错误。"""
    _generation_errors.append(msg)
    logger.warning("生成异常: %s", msg)


def _call_sheet(label: str, fn, *args, **kwargs) -> bool:
    """安全调用单页写入函数，失败时记录错误并继续。

    Args:
        label: 页面名称（中文，用于日志/输出）
        fn: 要调用的写入函数（为 None 时视为模块缺失）
        args, kwargs: 传递给 fn 的参数

    Returns:
        True 表示成功，False 表示失败/未调用
    """
    if fn is None:
        _add_error(f"{label}模块缺失，跳过")
        return False
    try:
        print(f"  [..] 正在生成{label}...")
        fn(*args, **kwargs)
        print(f"  [OK] {label}生成完成")
        return True
    except Exception as e:
        _add_error(f"{label}生成失败: {e}")
        logger.exception(f"{label}写入异常")
        return False


def _clear_errors() -> None:
    """清空错误汇总。"""
    _generation_errors.clear()


def _print_error_summary() -> None:
    """如果存在错误，在 TUI 尾部输出汇总。"""
    if not _generation_errors:
        return
    print()
    print(f"  ╔{'═' * 48}╗")
    print(f"  ║  ⚠ 本次运行异常汇总：{len(_generation_errors)} 项             ║")
    print(f"  ╠{'═' * 48}╣")
    for i, err in enumerate(_generation_errors, 1):
        truncated = err if len(err) <= 70 else err[:67] + "..."
        print(f"  ║ {i}. {truncated:<45} ║")
    print(f"  ╚{'═' * 48}╝")
    print(f"  详细日志请查看 logs/app.log")


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
    """检测持仓是否变化，若有新增资产则主动预热其缓存数据。

    异常不会向外传播 — 预热是优化而非必需步骤，失败不影响后续报告生成。
    """
    try:
        from src.python.cache import check_and_refresh_caches
        from src.python.fetcher import (
            batch_fetch_industry_data,
            fetch_fund_holdings,
            fetch_fund_rankings,
            fetch_market_data,
        )
        from src.python.report.fund_performance import _is_fund

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
    except Exception:
        logger.warning("新资产预热过程异常，跳过（不影响后续生成）")


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
    _clear_errors()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return
    try:
        holdings = read_holdings(filepath)
        if not holdings:
            _add_error("未读取到有效的持仓数据")
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        _check_and_warm_for_new_assets(holdings)
        _generate_excel_report(holdings, include_news=False, output_dir=config.get("output_dir", "reports"))
    except Exception as e:
        _add_error(str(e))
        logger.exception("生成 Excel 报告失败")
        _print_error_with_hint(e, "生成失败")
    _print_error_summary()
    _print_timing_summary()
    _press_any_key()


def _cmd_generate_excel_with_news() -> None:
    """生成包含新闻的 Excel 分析报告。"""
    _refresh_config()
    _clear_errors()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return
    try:
        holdings = read_holdings(filepath)
        if not holdings:
            _add_error("未读取到有效的持仓数据")
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
        _add_error(str(e))
        logger.exception("生成 Excel（新闻）报告失败")
        _print_error_with_hint(e, "生成失败")
    _print_error_summary()
    _print_timing_summary()
    _press_any_key()


def _generate_excel_report(
    holdings: list, include_news: bool = False, output_dir: str = "reports",
    news_top_count: int = 100, include_llm: bool = False,
    show_llm_in_tui: bool = False, llm_content: tuple | None = None,
    details: list | None = None, a_indices: dict[str, dict[str, Any]] | None = None,
    us_indices: dict[str, dict[str, Any]] | None = None,
    news_data: list | None = None,
    llm_cached: tuple[bool, bool, bool, bool] = (False, False, False, False),
    news_llm_meta: dict | None = None,
) -> None:
    """生成 Excel 报告的核心逻辑。"""
    # ── 导入各报告模块（单独捕获，避免一处缺失拖垮整个报告） ──
    try:
        from src.python.fetcher import fetch_indices, fetch_us_indices
    except ImportError:
        fetch_indices = lambda: {}
        fetch_us_indices = lambda: {}
        _add_error("市场指数模块缺失 (fetcher)")

    try:
        from src.python.report.excel_writer import create_workbook, save_workbook
    except ImportError:
        _add_error("Excel 报告核心模块缺失 (excel_writer)，无法生成报告")
        return

    sheets_ok: dict[str, bool] = {}

    try:
        from src.python.report.summary import write_summary_sheet
    except ImportError:
        write_summary_sheet = None
        _add_error("汇总页模块缺失 (summary)")

    try:
        from src.python.report.category import write_category_sheet
    except ImportError:
        write_category_sheet = None
        _add_error("持仓分类模块缺失 (category)")

    try:
        from src.python.report.market_value import (
            classify_holdings, get_last_trading_day,
            price_update_status, write_market_value_sheet,
        )
    except ImportError:
        classify_holdings = lambda _: {}
        get_last_trading_day = lambda: ""
        price_update_status = lambda _a, _b: (0, 0, True)
        write_market_value_sheet = None
        _add_error("行情市值模块缺失 (market_value)")

    try:
        from src.python.report.penetration import write_penetration_sheet, compute_penetration_top10
    except ImportError:
        write_penetration_sheet = None
        compute_penetration_top10 = lambda _a, _b: {}
        _add_error("穿透分析模块缺失 (penetration)")

    try:
        from src.python.report.fund_performance import write_fund_performance_sheet
    except ImportError:
        write_fund_performance_sheet = None
        _add_error("基金业绩模块缺失 (fund_performance)")

    # ── 创建工作簿（必须成功） ──
    wb = create_workbook()
    wb.remove(wb.active)

    # 预创建全部页签，确保 1→10 数字顺序从左到右
    ws1 = wb.create_sheet()  # 1. 汇总
    ws2 = wb.create_sheet()  # 2. 市值核算
    ws3 = wb.create_sheet()  # 3. 持仓分类
    ws4 = wb.create_sheet()  # 4. 资产穿透TOP10
    ws5 = wb.create_sheet()  # 5. 基金业绩分析
    ws6 = wb.create_sheet() if include_news else None  # 6. 财经新闻热点

    # ── 行情市值页（返回下游所需的核心数据） ──
    if write_market_value_sheet is None:
        total_mv = total_cost = total_profit = today_profit = 0.0
        details = details or []
        categories: dict[str, int] = {}
        up_status = (0, 0, True)
        _add_error("行情市值模块缺失，跳过 Sheet 2")
    elif details is not None:
        logger.info("复用外部传入的市值核算数据，共 %d 条", len(details))
        total_mv = sum(d.market_value for d in details)
        total_cost = sum(d.cost for d in details)
        total_profit = sum(d.profit for d in details)
        today_profit = sum(d.today_profit for d in details)
        with _Timer("市值核算明细表"):
            write_market_value_sheet(ws2, holdings, details=details)
    else:
        with _Timer("行情数据获取"):
            print("  [..] 正在获取行情数据（首次耗时较长，后续使用缓存）...")
            total_mv, total_cost, total_profit, today_profit, details = \
                write_market_value_sheet(ws2, holdings)
        print("  [OK] 行情数据获取完成")

    categories = classify_holdings(holdings) if classify_holdings else {}
    up_status = price_update_status(details, get_last_trading_day()) if price_update_status else (0, 0, True)

    # ── 市场指数 ──
    if a_indices is None:
        with _Timer("市场指数"):
            print("  [..] 正在获取市场指数...")
            a_indices = fetch_indices() if fetch_indices else {}
            if us_indices is None:
                us_indices = fetch_us_indices() if fetch_us_indices else {}
            print("  [OK] 市场指数获取完成")

    # ── 各页安全写入 ──
    _llm_session = None
    with _Timer("投资分析汇总"):
        _call_sheet("投资分析汇总", write_summary_sheet,
                     ws1, total_mv, total_cost, total_profit, today_profit,
                     categories=categories, update_status=up_status,
                     a_indices=a_indices, us_indices=us_indices)

    with _Timer("持仓分类表"):
        _call_sheet("持仓分类表", write_category_sheet, ws3, holdings, details)

    with _Timer("资产穿透TOP10"):
        pen_result = compute_penetration_top10(holdings, details) if compute_penetration_top10 else {}
        print("  [OK] 资产穿透 TOP10 计算完成")
        _call_sheet("资产穿透TOP10", write_penetration_sheet,
                     ws4, holdings, details, penetration_data=pen_result)

    with _Timer("基金业绩分析"):
        _call_sheet("基金业绩分析", write_fund_performance_sheet, ws5, holdings, details)

    if include_news:
        penetrated_assets = pen_result.get("top10", []) if pen_result else []
        try:
            from src.python.report.news_correlation import write_news_sheet
        except ImportError:
            write_news_sheet = None
            _add_error("新闻页模块缺失 (news_correlation)")

        with _Timer("财经新闻热点与持仓关联分析"):
            if news_data is not None:
                logger.info("复用预取的新闻数据，共 %d 条", len(news_data))
                _meta = news_llm_meta or {}
                print(f"  [OK] 复用预取新闻数据（{len(news_data)} 条）")
            else:
                print("  [..] 正在获取财经新闻（含穿透资产关键词）...")
                try:
                    from src.python.report.news_correlation import build_news_data
                except ImportError:
                    build_news_data = None
                if build_news_data:
                    try:
                        news_data, _meta = build_news_data(holdings, top_n=news_top_count, penetrated_assets=penetrated_assets)
                    except Exception as e:
                        _add_error(f"新闻数据获取失败: {e}")
                        news_data, _meta = [], {}
                else:
                    _add_error("新闻数据模块缺失")
                    news_data, _meta = [], {}
            _call_sheet("财经新闻热点与持仓关联分析", write_news_sheet, ws6, news_data, llm_meta=_meta)

    if include_llm:
        with _Timer("LLM 分析章节"):
            print("  [..] 正在生成 LLM 分析章节...")
            try:
                from src.python.report.llm_content import write_llm_sheets
                _llm_cfg = get_llm_config() or {}
                _model_names = (
                    _llm_cfg.get("model_global_macro") or _llm_cfg.get("model", ""),
                    _llm_cfg.get("model_expert_review") or _llm_cfg.get("model", ""),
                    _llm_cfg.get("model_health_check") or _llm_cfg.get("model", ""),
                    _llm_cfg.get("model_penetration_deep") or _llm_cfg.get("model", ""),
                )
                _thinking = (
                    _llm_cfg.get("thinking_enabled_global_macro", False),
                    _llm_cfg.get("thinking_enabled_expert_review", False),
                    _llm_cfg.get("thinking_enabled_health_check", False),
                    _llm_cfg.get("thinking_enabled_penetration_deep", False),
                )
                global_macro_text, expert_review_text, health_check_text, penetration_deep_text = write_llm_sheets(
                    wb, llm_content=llm_content, llm_cached=llm_cached,
                    model_names=_model_names, thinking=_thinking,
                )
                logger.info("LLM 分析章节已生成")
                print("  [OK] LLM 分析章节生成完成")
            except ImportError:
                logger.warning("LLM 分析章节模块 (src.python.report.llm_content) 未就绪，跳过")
                _add_error("LLM 分析章节模块未就绪，跳过")
                global_macro_text = expert_review_text = health_check_text = penetration_deep_text = ""
            except Exception as e:
                logger.exception("生成 LLM 分析章节失败")
                _add_error(f"LLM 分析章节生成失败: {e}")
                global_macro_text = expert_review_text = health_check_text = penetration_deep_text = ""

        # LLM 生成完成后捕获会话用量，追加到汇总页
        try:
            from src.python.llm_client import get_session_usage
            _llm_session = get_session_usage()
        except Exception:
            _llm_session = None
        if _llm_session and _llm_session.get("call_count", 0) > 0:
            try:
                from src.python.report.summary import write_llm_usage_block
                write_llm_usage_block(ws1, _llm_session)
                from src.python.report.excel_writer import freeze_header, auto_width
                freeze_header(ws1, 2)
                auto_width(ws1)
            except Exception:
                pass

        if show_llm_in_tui and (global_macro_text or expert_review_text or health_check_text or penetration_deep_text):
            _show_llm_tui(global_macro_text, expert_review_text, health_check_text, penetration_deep_text)

        _print_llm_session_usage(_llm_session)

    with _Timer("保存文件"):
        print("  [..] 正在保存 Excel 报告...")
        path = save_workbook(wb, output_dir=output_dir)
        logger.info("Excel 报告已生成: %s", path)
        logger.info("总市值: %.2f元, 总成本: %.2f元, 总盈亏: %.2f元, 本日盈亏: %.2f元",
                    total_mv, total_cost, total_profit, today_profit)
        print(f"  [OK] Excel 报告已保存: {path}")


def _cmd_generate_html(news: bool = False) -> None:
    """生成基础的 HTML 分析报告。"""
    _refresh_config()
    _clear_errors()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        if not holdings:
            _add_error("未读取到有效的持仓数据")
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        print(f"  [OK] 成功读取 {len(holdings)} 条持仓记录")
        _check_and_warm_for_new_assets(holdings)

        print("  [..] 正在获取行情数据并生成 HTML 报告...")
        from src.python.report.html_writer import write_html_report
        news_top_count = int(config.get("news_top_count", 100))
        path = write_html_report(
            holdings, output_dir=config.get("output_dir", "reports"),
            news_top_count=news_top_count, include_news=news,
        )
        print()
        print(f"  [OK] HTML 报告已生成: {path}")
    except Exception as e:
        _add_error(f"HTML 报告生成失败: {e}")
        logger.exception("生成 HTML 报告失败")
        _print_error_with_hint(e, "生成失败")
    _print_error_summary()
    _print_timing_summary()
    _press_any_key()


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 分析章节）。"""
    _refresh_config()
    _clear_errors()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        holdings = read_holdings(filepath)
        if not holdings:
            _add_error("未读取到有效的持仓数据")
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        _check_and_warm_for_new_assets(holdings)
        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))
        today_str = datetime.now().strftime("%Y-%m-%d")

        from src.python.report.market_value import _generate_details
        print("  [..] 正在获取行情数据...")
        details = _generate_details(holdings, today_str)
        _check_network_available(details)
        print(f"  [OK] 行情数据获取完成，共 {len(details)} 条")

        from src.python.report.html_writer import write_html_report
        print("  [..] 正在生成 HTML 报告（含新闻）...")
        try:
            path = write_html_report(
                holdings, output_dir=output_dir,
                news_top_count=news_top_count, include_news=True,
                details=details,
            )
            print(f"  [OK] HTML 报告已生成: {path}")
        except Exception as e:
            _add_error(f"HTML 报告生成失败: {e}")
            logger.exception("HTML 报告写入失败")
            print(f"  [ERR] HTML 报告生成失败: {e}")
            print("  [..] 继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=output_dir,
            news_top_count=news_top_count, details=details,
        )
    except Exception as e:
        _add_error(f"全系列报告生成失败: {e}")
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _print_error_summary()
    _print_timing_summary()
    _press_any_key()


def _show_llm_tui(global_macro_text: str, expert_review_text: str, health_check_text: str = "", penetration_deep_text: str = "") -> None:
    """在 TUI 终端中展示 LLM 分析章节摘要。"""
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

    if global_macro_text:
        _print_box("全球政经局势", _trim(global_macro_text.strip(), 200))
        print()

    if expert_review_text:
        phase3 = ""
        for kw in ("定音锤", "Phase 3", "⚖"):
            idx = expert_review_text.find(kw)
            if idx >= 0:
                phase3 = expert_review_text[idx:]
                break
        phase1 = ""
        for kw in ("召集令", "Phase 1", "🕵"):
            idx = expert_review_text.find(kw)
            if idx >= 0:
                end = expert_review_text.find("Phase 2", idx)
                if end < 0:
                    end = expert_review_text.find("**Phase 2", idx)
                if end < 0:
                    end = expert_review_text.find("圆桌", idx)
                if end < 0:
                    end = idx + 400
                phase1 = expert_review_text[idx:end]
                break

        parts = [p for p in [phase1, phase3] if p]
        body = _trim("\n".join(parts) if parts else expert_review_text.strip(), 500)
        _print_box("智囊团深度复盘", body)
    print()

    if health_check_text:
        # 提取综合评分和评级供 TUI 展示
        lines = health_check_text.split("\n")
        score_line = ""
        for line in lines:
            if "总分" in line or "综合评分" in line:
                score_line = line.strip()[:120]
                break
        body = score_line if score_line else _trim(health_check_text.strip(), 200)
        _print_box("持仓体检报告摘要", body)
    print()

    if penetration_deep_text:
        # 提取穿透深度分析概要
        lines = penetration_deep_text.split("\n")
        summary_line = ""
        for line in lines:
            if "集中度" in line or "行业" in line or "国家" in line or "货币" in line:
                summary_line = line.strip()[:120]
                break
        body = summary_line if summary_line else _trim(penetration_deep_text.strip(), 200)
        _print_box("穿透深度分析概要", body)
    print()


def _cmd_generate_full() -> None:
    """生成包含所有内容的全系列报告（Excel + HTML + 新闻 + LLM 分析章节）。"""
    _refresh_config()
    _clear_errors()
    config = get_config_cache() or {}
    filepath = _select_holdings_file()
    if not filepath:
        return

    try:
        holdings = read_holdings(filepath)
        if not holdings:
            _add_error("未读取到有效的持仓数据")
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return
        _check_and_warm_for_new_assets(holdings)
        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))

        from src.python.fetcher import fetch_indices, fetch_us_indices
        from src.python.report.market_value import _generate_details, classify_holdings
        from src.python.report.penetration import compute_penetration_top10

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
                "nav_date": d.nav_date,
                "source_api": d.source_api,
            }
            for d in details
        ]

        from src.python.llm_client import generate_all_llm
        from src.python.providers.akshare_extras import get_sector_fund_flow
        from src.python.report.news_correlation import build_news_data

        print("  [..] 正在并行获取新闻 + LLM 内容...")

        _sector_flow = get_sector_fund_flow()

        news_data: list = []
        news_llm_meta: dict = {}
        llm_content = (None, None, None, None)
        llm_cached = (False, False, False, False)

        # 是否强制刷新 LLM 缓存
        _force_llm = False
        try:
            _resp = input("  [..] 是否强制重新生成 LLM 内容（跳过缓存）？(y/N): ").strip().lower()
            _force_llm = _resp == "y"
        except (EOFError, KeyboardInterrupt):
            _force_llm = False
        if _force_llm:
            print("  [OK] 将跳过 LLM 缓存强制重新生成")

        with ThreadPoolExecutor(max_workers=2) as _llm_ex:

            def _run_llm():
                return generate_all_llm(
                    a_indices, us_indices, total_mv, total_cost, total_profit,
                    total_today_profit, len(holdings), categories,
                    penetrated_assets=penetrated_assets,
                    holdings_details=holdings_details,
                    sector_flow=_sector_flow, force=_force_llm,
                )

            _news_fut = _llm_ex.submit(
                build_news_data, holdings, news_top_count, penetrated_assets,
            )
            _llm_fut = _llm_ex.submit(_run_llm)

            for fut in as_completed([_news_fut, _llm_fut]):
                if fut is _llm_fut:
                    try:
                        llm_global_macro, llm_expert_review, llm_health_check, llm_penetration_deep, global_macro_cached, expert_review_cached, health_check_cached, penetration_deep_cached = fut.result()
                        llm_content = (llm_global_macro, llm_expert_review, llm_health_check, llm_penetration_deep)
                        llm_cached = (global_macro_cached, expert_review_cached, health_check_cached, penetration_deep_cached)
                        if not any(c is None for c in (llm_global_macro, llm_expert_review, llm_health_check, llm_penetration_deep)):
                            tag = "缓存" if global_macro_cached and expert_review_cached else "LLM"
                            print(f"  [OK] {tag} 内容生成完成")
                        else:
                            _add_error("部分 LLM 内容生成失败（已降级使用占位文本）")
                            print("  [!] 部分 LLM 内容生成失败（已降级使用占位文本）")
                    except Exception as e:
                        _add_error(f"LLM 内容生成异常: {e}")
                        print(f"  [ERR] LLM 内容生成异常: {e}")
                else:
                    try:
                        news_data, news_llm_meta = fut.result()
                        print(f"  [OK] 新闻获取完成，共 {len(news_data)} 条")
                    except Exception as e:
                        _add_error(f"新闻获取失败: {e}")
                        print(f"  [!] 新闻获取失败: {e}")

        _print_llm_session_usage()

        from src.python.report.html_writer import write_html_report
        print("  [..] 正在生成 HTML 报告（含新闻 + LLM 分析章节）...")
        try:
            path = write_html_report(
                holdings, output_dir=output_dir,
                news_top_count=news_top_count, include_news=True,
                llm_content=llm_content, details=details,
                news_data=news_data, news_llm_meta=news_llm_meta,
            )
            print(f"  [OK] HTML 报告已生成: {path}")
        except Exception as e:
            _add_error(f"HTML 报告生成失败: {e}")
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
        _add_error(f"全系列报告生成失败: {e}")
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _print_error_summary()
    _print_timing_summary()
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


def _refresh_common_caches() -> None:
    """刷新不依赖基金持仓的公共缓存：盈利预测 + 行业资金流向。

    缓存清除已在主流程中完成，此函数仅触发刷新操作。
    """
    pf_ok = sf_ok = 0
    with ThreadPoolExecutor(max_workers=2) as _ex:
        def _job1():
            from src.python.providers.akshare_extras import _memo_clear, get_profit_forecast
            _memo_clear()
            data = get_profit_forecast()
            return len(data) if data else 0
        def _job2():
            from src.python.providers.akshare_extras import get_sector_fund_flow
            data = get_sector_fund_flow()
            return len(data) if data else 0
        _f1 = _ex.submit(_job1)
        _f2 = _ex.submit(_job2)
        try:
            pf_ok = _f1.result()
            print(f"  [OK]   profit_forecast              ({pf_ok} 只股票)" if pf_ok
                  else "  [!]   profit_forecast              获取失败")
        except Exception:
            print("  [!]   profit_forecast              获取失败")
        try:
            sf_ok = _f2.result()
            print(f"  [OK]   sector_flow                  ({sf_ok} 个行业)" if sf_ok
                  else "  [!]   sector_flow                  获取失败")
        except Exception:
            print("  [!]   sector_flow                  获取失败")


def _cmd_update_basic_cache() -> None:
    """更新基础类缓存。"""
    from src.python.cache import clear, clear_by_prefix
    from src.python.fetcher import fetch_fund_benchmark, fetch_fund_holdings, fetch_fund_rankings
    from src.python.report.fund_performance import _is_fund

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
        has_non_fundable_data = True  # news/industry/dividend/profit_forecast/sector_flow 不依赖基金

        if not funds:
            print("  [!!] 未检测到基金持仓，跳过基金业绩/持仓/基准缓存")
            print("  [..] 继续刷新新闻/行业分类/分红/盈利预测/行业资金流向...")

        print()
        print("  [..] 清除旧缓存...")
        clear_by_prefix("fund_perf_")
        clear_by_prefix("fund_hold_")
        clear("fund_benchmarks")
        clear_by_prefix("news_")
        clear_by_prefix("llm_news_item_")
        clear_by_prefix("industry_")
        clear_by_prefix("dividend_")
        clear_by_prefix("profit_forecast_")
        clear_by_prefix("sector_flow_")
        print("  [OK] 旧缓存已清除（含 fund_perf_ + fund_hold_ + fund_benchmarks + news_ +"
              " llm_news_item_ + industry_ +"
              " dividend_ + profit_forecast_ + sector_flow_ 缓存）")

        if not funds:
            # 无基金：只刷新非基金类缓存
            print()
            print(f"  [..]   并行获取新闻/行业/分红/盈利预测/行业资金流向...")
            _refresh_common_caches()
            _press_any_key()
            return

        print()
        print(f"  [..]   并行获取全部缓存数据...")

        # 基金级刷新
        def _refresh_one_fund(fund):
            perf_result = fetch_fund_rankings(fund.code)
            perf_ok = bool(perf_result)
            hold_data = fetch_fund_holdings(fund.code)
            hold_ok = bool(hold_data and hold_data.get("holdings"))
            hold_count = len(hold_data["holdings"]) if hold_data and hold_data.get("holdings") else 0
            bm = fetch_fund_benchmark(fund.code)
            bm_ok = bool(bm and bm != "--")
            return ("fund", fund.code, fund.name, perf_ok, hold_ok, hold_count, bm_ok)

        def _refresh_profit_forecast():
            from src.python.providers.akshare_extras import _memo_clear, get_profit_forecast
            _memo_clear()
            data = get_profit_forecast()
            ok = len(data) if data else 0
            return ("profit_forecast", ok)

        def _refresh_sector_flow():
            from src.python.providers.akshare_extras import get_sector_fund_flow
            data = get_sector_fund_flow()
            ok = len(data) if data else 0
            return ("sector_flow", ok)

        perf_ok = hold_ok = bm_ok = 0
        pf_ok = sf_ok = 0

        # 将所有任务提交到同一线程池：基金数据 + 盈利预测 + 行业资金流向
        max_workers_val = max(3, min(len(funds) + 2, 7))
        with ThreadPoolExecutor(max_workers=max_workers_val) as executor:
            all_futures = {}
            for f in funds:
                all_futures[executor.submit(_refresh_one_fund, f)] = "fund"
            all_futures[executor.submit(_refresh_profit_forecast)] = "other"
            all_futures[executor.submit(_refresh_sector_flow)] = "other"

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
                        if pf_ok:
                            print(f"  [OK]   profit_forecast              ({pf_ok} 只股票)")
                        else:
                            print("  [!]   profit_forecast              获取失败")
                    elif result[0] == "sector_flow":
                        sf_ok = result[1]
                        if sf_ok:
                            print(f"  [OK]   sector_flow                  ({sf_ok} 个行业)")
                        else:
                            print("  [!]   sector_flow                  获取失败")
                except Exception:
                    if tag == "fund":
                        print(f"  [!]   基金刷新异常")
                    else:
                        print(f"  [!]   其他缓存刷新异常")

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
        if pf_ok:
            print(f"  [OK] profit_forecast.json           ({pf_ok} 只股票)")
        else:
            print(f"  [!] profit_forecast.json           获取失败")
        if sf_ok:
            print(f"  [OK] sector_flow.json               ({sf_ok} 个行业)")
        else:
            print(f"  [!] sector_flow.json               获取失败")
    except Exception as e:
        logger.exception("更新基础缓存失败")
        print(f"  [ERR] 更新失败: {e}")
    _press_any_key()


def _cmd_update_position_cache() -> None:
    """更新持仓类缓存。"""
    from src.python.cache import clear_by_prefix
    from src.python.fetcher import fetch_indices, fetch_market_data, fetch_us_indices
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
        expert_review_count = clear_by_prefix("llm_expert_review_")
        global_macro_count = clear_by_prefix("llm_global_macro_")
        health_check_count = clear_by_prefix("llm_health_check_")
        penetration_deep_count = clear_by_prefix("llm_penetration_deep_")
        print(f"  [OK] 价格缓存 {price_count} 条 + 指数缓存 {index_count} 条 + "
              f"智囊团深度复盘 {expert_review_count} 条 + 全球政经局势 {global_macro_count} 条 + "
              f"持仓体检报告 {health_check_count} 条 + 穿透深度分析 {penetration_deep_count} 条 已清除")

        print()
        print(f"  [..]   并行获取持仓价格/净值 + 市场指数...")
        price_ok = 0
        a_idx: dict = {}
        us_idx: dict = {}
        with ThreadPoolExecutor(max_workers=max(3, min(len(holdings) + 2, 7))) as executor:
            fut_map: dict[Any, str | None] = {}
            for h in holdings:
                fut_map[executor.submit(fetch_market_data, h.code, h.name)] = h
            idx_a_fut = executor.submit(fetch_indices)
            idx_us_fut = executor.submit(fetch_us_indices)
            fut_map[idx_a_fut] = None
            fut_map[idx_us_fut] = None

            for future in as_completed(fut_map):
                h_or_none = fut_map[future]
                try:
                    if h_or_none is None:
                        # 指数请求
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
    from src.python.cache import cleanup_expired, get_cache_dir, get_cache_stats
    cache_dir = get_cache_dir()
    stats = get_cache_stats()
    print(f"  缓存目录: {cache_dir}")
    print(f"  文件总数: {stats['total_files']}")
    print(f"  总大小:   {stats['total_size_bytes'] / 1024:.0f} KB")
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


# ── 执行菜单项 ─────────────────────────────────────────────


def _execute_item(sel: int) -> None:
    """执行第 sel 项菜单的回调或退出。"""
    global _busy
    _, _label, callback, is_exit = MENU_ITEMS[sel]
    if is_exit:
        from src.python.tui_menu import _exit_app
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
