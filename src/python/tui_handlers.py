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
from src.python.registry import get_llm_module_name
from src.python.llm.pricing import _CURRENCY_SYMBOLS
from src.python.llm.prompts import _LLM_MODULE_FAILURE, FAIL_REASON_DISABLED
from src.python.report.progress import TuiProgressReporter
logger = setup_logger()

_busy: bool = False  # 防连续按键保护


def _print_llm_session_usage(usage: dict | None = None) -> None:
    """输出会话累计 LLM 用量（TUI 终端一行）。

    若 usage 为 None，自动调用 get_session_usage()。
    无调用记录时静默不输出。

    Args:
        usage: 可选的 get_session_usage() 返回值，避免重复导入
    """
    if usage is None:
        try:
            from src.python.llm import get_session_usage
            usage = get_session_usage()
        except (ImportError, TypeError, AttributeError):
            logger.debug("获取 LLM 会话用量失败（非关键）")
            return
    if not usage or usage.get("call_count", 0) == 0:
        return
    calls = usage["call_count"]
    total_tok = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    cost = usage.get("total_cost", 0.0)
    symbol = _CURRENCY_SYMBOLS.get(usage.get("currency", "CNY"), "¥")
    print(f"  [OK] 本会话 LLM 累计：{calls} 次调用，{total_tok:,} tokens，费用 {symbol}{cost:.4f}")


def _print_timing_summary() -> None:
    """输出本次运行时各模块耗时排行（委托至 TuiProgressReporter）。"""
    TuiProgressReporter().print_timing_summary()


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


def _prepare_holdings() -> list | None:
    """选择持仓文件并读取持仓记录。

    刷新配置 → 选文件 → 读持仓 → 非空检查 → 预热缓存。

    Returns:
        持仓列表；失败/取消时返回 None（已输出错误提示）
    """
    _refresh_config()
    filepath = _select_holdings_file()
    if not filepath:
        return None
    try:
        print("  [..] 正在读取持仓数据...")
        holdings = read_holdings(filepath)
        if not holdings:
            print("  [ERR] 未读取到有效的持仓数据")
            print("     请检查持仓文件中是否有数据，列名是否正确")
            print("     需要的列名：名称、代码、持仓份额、每份成本")
            _press_any_key()
            return None
        print(f"  [OK] 成功读取 {len(holdings)} 条持仓记录")
        _check_and_warm_for_new_assets(holdings)
        return holdings
    except Exception as e:
        print(f"  [ERR] 读取持仓失败: {e}")
        _press_any_key()
        return None


def _finish_report(reporter: TuiProgressReporter) -> None:
    """报告生成收尾：错误摘要 → 耗时排行 → 按任意键。"""
    reporter.print_error_summary()
    reporter.print_timing_summary()
    _press_any_key()


# ── 持仓变更检测与缓存预热 ─────────────────────────────────


def _check_and_warm_for_new_assets(holdings: list) -> None:
    """检测持仓是否变化，若有新增资产则主动预热其缓存数据。

    异常不会向外传播 — 预热是优化而非必需步骤，失败不影响后续报告生成。
    """
    try:
        from src.python.cache import check_and_refresh_caches
        from src.python.fetcher.industry import batch_fetch_industry_data
        from src.python.fetcher.fund import fetch_fund_holdings, fetch_fund_rankings
        from src.python.fetcher.price import fetch_market_data
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
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    holdings = _prepare_holdings()
    if not holdings:
        return
    try:
        _generate_excel_report(holdings, include_news=False,
                               output_dir=config.get("output_dir", "reports"),
                               progress=reporter)
    except Exception as e:
        reporter.add_error(str(e))
        logger.exception("生成 Excel 报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)


def _generate_excel_report(*args, progress=None, **kwargs):
    """生成 Excel 报告（委托给 excel_generator 模块）。"""
    from src.python.report.excel_generator import generate_excel_report
    prog = progress if progress is not None else TuiProgressReporter()
    return generate_excel_report(*args, **kwargs, progress=prog)


def _cmd_generate_html(news: bool = False) -> None:
    """生成基础的 HTML 分析报告。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    holdings = _prepare_holdings()
    if not holdings:
        return

    try:
        print("  [..] 正在获取行情数据并生成 HTML 报告...")
        from src.python.report.html_writer import write_html_report
        news_top_count = int(config.get("news_top_count", 100))
        path = write_html_report(
            holdings, output_dir=config.get("output_dir", "reports"),
            news_top_count=news_top_count, include_news=news,
            progress=reporter,
        )
        print()
        print(f"  [OK] HTML 报告已生成: {path}")
    except Exception as e:
        reporter.add_error(f"HTML 报告生成失败: {e}")
        logger.exception("生成 HTML 报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)


def _cmd_generate_both() -> None:
    """生成全系列包含新闻的报告（Excel+HTML，不含 LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    config = get_config_cache() or {}
    holdings = _prepare_holdings()
    if not holdings:
        return

    try:
        output_dir = config.get("output_dir", "reports")
        news_top_count = int(config.get("news_top_count", 100))
        today_str = datetime.now().strftime("%Y-%m-%d")

        from src.python.report.market_value import _generate_details
        reporter.info("正在获取行情数据...")
        details = _generate_details(holdings, today_str)
        _check_network_available(details)
        reporter.ok(f"行情数据获取完成，共 {len(details)} 条")

        from src.python.report.html_writer import write_html_report
        reporter.info("正在生成 HTML 报告（含新闻）...")
        try:
            path = write_html_report(
                holdings, output_dir=output_dir,
                news_top_count=news_top_count, include_news=True,
                details=details, progress=reporter,
            )
            reporter.ok(f"HTML 报告已生成: {path}")
        except Exception as e:
            reporter.add_error(f"HTML 报告生成失败: {e}")
            logger.exception("HTML 报告写入失败")
            reporter.error(f"HTML 报告生成失败: {e}")
            reporter.info("继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=output_dir,
            news_top_count=news_top_count, details=details,
            progress=reporter,
        )
    except Exception as e:
        reporter.add_error(f"全系列报告生成失败: {e}")
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)


def _process_llm_news_futures(
    llm_fut, news_fut, reporter,
) -> tuple[tuple, list, dict]:
    """处理 LLM 生成 + 新闻获取的并行 Future 结果。

    Args:
        llm_fut: generate_all_llm 的 Future
        news_fut: build_news_data 的 Future
        reporter: 进度报告器

    Returns:
        (llm_content, news_data, news_llm_meta)
    """
    llm_content = (None, None, None, None)
    news_data: list = []
    news_llm_meta: dict = {}

    for fut in as_completed([news_fut, llm_fut]):
        if fut is llm_fut:
            try:
                (llm_global_macro, llm_expert_review,
                 llm_health_check, llm_penetration_deep,
                 global_macro_cached, expert_review_cached,
                 health_check_cached, penetration_deep_cached) = fut.result()
                llm_content = (llm_global_macro, llm_expert_review,
                               llm_health_check, llm_penetration_deep)
                _MODULE_KEYS = ("global_macro", "expert_review",
                                "health_check", "penetration_deep")
                _MODULE_RESULTS = (llm_global_macro, llm_expert_review,
                                   llm_health_check, llm_penetration_deep)
                _CACHED_FLAGS = (global_macro_cached, expert_review_cached,
                                 health_check_cached, penetration_deep_cached)
                disabled: list[str] = []
                failed: list[str] = []
                ok_count = 0
                for mk, r in zip(_MODULE_KEYS, _MODULE_RESULTS):
                    if r is not None:
                        ok_count += 1
                    elif _LLM_MODULE_FAILURE.get(mk) == FAIL_REASON_DISABLED:
                        disabled.append(get_llm_module_name(mk))
                    else:
                        failed.append(get_llm_module_name(mk))

                for name in disabled:
                    reporter.info(f"{name}：已跳过（菜单 S 可切换）")
                for name in failed:
                    reporter.add_error(f"{name}：内容生成失败（已降级使用占位文本）")
                    reporter.warn(f"{name}：内容生成失败（已降级使用占位文本）")

                if ok_count > 0 and not failed:
                    tag = "缓存" if all(_CACHED_FLAGS) else "LLM"
                    reporter.ok(f"{tag} 内容生成完成")
                elif ok_count == 0 and not failed and not disabled:
                    reporter.warn("LLM 均未生成（请检查 LLM 配置）")
                elif ok_count == 0 and not failed:
                    reporter.info("所有 LLM 内容已跳过，未调用 LLM")
            except Exception as e:
                reporter.add_error(f"LLM 内容生成异常: {e}")
                reporter.error(f"LLM 内容生成异常: {e}")
        else:
            try:
                news_data, news_llm_meta = fut.result()
                reporter.ok(f"新闻获取完成，共 {len(news_data)} 条")
            except Exception as e:
                reporter.add_error(f"新闻获取失败: {e}")
                reporter.warn(f"新闻获取失败: {e}")

    return llm_content, news_data, news_llm_meta


def _prepare_report_data(holdings: list, reporter: TuiProgressReporter) -> dict:
    """获取行情、指数、穿透数据，整理持仓明细字典列表。

    Args:
        holdings: 持仓记录列表
        reporter: 进度报告器

    Returns:
        dict 含 details / total_mv / total_cost / total_profit /
             total_today_profit / categories / a_indices / us_indices /
             penetrated_assets / holdings_details / today_str / output_dir / news_top_count
    """
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.report.market_value import _generate_details, classify_holdings
    from src.python.report.penetration import compute_penetration_top10

    config = get_config_cache() or {}
    output_dir = config.get("output_dir", "reports")
    news_top_count = int(config.get("news_top_count", 100))
    today_str = datetime.now().strftime("%Y-%m-%d")

    reporter.info("正在获取行情数据...")
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
        "output_dir": output_dir,
        "news_top_count": news_top_count,
    }


def _prompt_force_llm(reporter: TuiProgressReporter) -> bool:
    """询问用户是否强制刷新 LLM 缓存。

    Returns:
        True 强制刷新，False 使用缓存
    """
    try:
        _resp = input("  [..] 是否强制重新生成 LLM 内容（跳过缓存）？(y/N): ").strip().lower()
        _force = _resp == "y"
    except (EOFError, KeyboardInterrupt):
        _force = False
    if _force:
        reporter.ok("将跳过 LLM 缓存强制重新生成")
    return _force


def _compute_early_warnings(
    holdings: list, penetrated_assets: list, sector_flow: dict,
    news_data: list, news_llm_meta: dict, reporter: TuiProgressReporter,
) -> dict | None:
    """计算智能预警（行业资金流向联动 + 新闻情绪聚合）。

    Returns:
        预警结果字典，失败时返回 None
    """
    try:
        from src.python.report.early_warning import compute_early_warnings
        _warnings = compute_early_warnings(
            holdings,
            penetration_top10=penetrated_assets,
            sector_flow=sector_flow,
            news_data=news_data,
            news_llm_meta=news_llm_meta,
        )
        if _warnings.get("has_warnings"):
            _n_sector = len(_warnings.get("sector_alerts", []))
            _n_sentiment = len(_warnings.get("sentiment_alerts", []))
            reporter.ok(f"智能预警完成: {_n_sector} 条行业预警, {_n_sentiment} 条新闻情绪")
        return _warnings
    except Exception as e:
        logger.warning("智能预警计算失败: %s", e)
        return None


def _cmd_generate_full() -> None:
    """生成包含所有内容的全系列报告（Excel + HTML + 新闻 + LLM 分析章节）。"""
    reporter = TuiProgressReporter()
    holdings = _prepare_holdings()
    if not holdings:
        return

    try:
        prep = _prepare_report_data(holdings, reporter)

        from src.python.llm import generate_all_llm
        from src.python.providers.akshare_extras import get_sector_fund_flow
        from src.python.report.news_correlation import build_news_data

        reporter.info("正在并行获取新闻 + LLM 内容...")
        _sector_flow = get_sector_fund_flow()
        _force_llm = _prompt_force_llm(reporter)

        with ThreadPoolExecutor(max_workers=2) as _llm_ex:
            _news_fut = _llm_ex.submit(
                build_news_data, holdings, prep["news_top_count"], prep["penetrated_assets"],
            )
            _llm_fut = _llm_ex.submit(
                generate_all_llm,
                prep["a_indices"], prep["us_indices"],
                prep["total_mv"], prep["total_cost"], prep["total_profit"],
                prep["total_today_profit"], len(holdings), prep["categories"],
                penetrated_assets=prep["penetrated_assets"],
                holdings_details=prep["holdings_details"],
                sector_flow=_sector_flow, force=_force_llm,
            )
            llm_content, news_data, news_llm_meta = _process_llm_news_futures(
                _llm_fut, _news_fut, reporter,
            )

        _print_llm_session_usage()

        _early_warnings = _compute_early_warnings(
            holdings, prep["penetrated_assets"], _sector_flow,
            news_data, news_llm_meta, reporter,
        )

        from src.python.report.html_writer import write_html_report
        reporter.info("正在生成 HTML 报告（含新闻 + LLM 分析章节）...")
        try:
            path = write_html_report(
                holdings, output_dir=prep["output_dir"],
                news_top_count=prep["news_top_count"], include_news=True,
                llm_content=llm_content, details=prep["details"],
                news_data=news_data, news_llm_meta=news_llm_meta,
                early_warnings=_early_warnings, progress=reporter,
            )
            reporter.ok(f"HTML 报告已生成: {path}")
        except Exception as e:
            reporter.add_error(f"HTML 报告生成失败: {e}")
            logger.exception("HTML 报告写入失败")
            reporter.error(f"HTML 报告生成失败: {e}")
            reporter.info("继续生成 Excel 报告...")

        print()
        _generate_excel_report(
            holdings, include_news=True, output_dir=prep["output_dir"],
            news_top_count=prep["news_top_count"], include_llm=True,
            llm_content=llm_content,
            details=prep["details"], a_indices=prep["a_indices"],
            us_indices=prep["us_indices"],
            news_data=news_data,
            news_llm_meta=news_llm_meta,
            early_warnings=_early_warnings, progress=reporter,
        )
    except Exception as e:
        reporter.add_error(f"全系列报告生成失败: {e}")
        logger.exception("生成全系列报告失败")
        _print_error_with_hint(e, "生成失败")
    _finish_report(reporter)


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
    """刷新单只基金的排名、持仓和基准缓存。

    Args:
        fund: 基金持仓记录

    Returns:
        ("fund", code, name, perf_ok, hold_ok, hold_count, bm_ok)
    """
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
    """刷新不依赖基金持仓的公共缓存：盈利预测 + 行业资金流向。

    缓存清除已在主流程中完成，此函数仅触发刷新操作。

    Returns:
        (pf_ok, sf_ok) — 盈利预测覆盖股票数，行业资金流向行业数
    """
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

        # 将所有任务提交到同一线程池：基金数据 + 盈利预测 + 行业资金流向
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
    """并行获取持仓价格 + 市场指数并逐条输出。

    Args:
        holdings: 持仓记录列表

    Returns:
        (price_ok_count, a_indices_dict, us_indices_dict)
    """
    from src.python.fetcher.index import fetch_indices, fetch_us_indices
    from src.python.fetcher.price import fetch_market_data
    from concurrent.futures import ThreadPoolExecutor, as_completed

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

        for future in as_completed(fut_map):
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


# ── 配置支持LLM的报告模块 ──────────────────────────────────


def _read_llm_settings() -> tuple[dict, str] | None:
    """读取 llm_settings.json 配置（支持 JSON 注释）。

    Returns:
        (settings_dict, path) 成功时；失败时返回 None（已输出错误提示）
    """
    import json
    from src.python.config import _strip_json_comments
    path = "data/config/llm_settings.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        settings = json.loads(_strip_json_comments(raw))
        return settings, path
    except (FileNotFoundError, json.JSONDecodeError):
        print("  [ERR] 无法读取 llm_settings.json")
        _press_any_key()
        return None


def _write_llm_settings(settings: dict, path: str) -> None:
    """写入 llm_settings.json 并刷新 LLM 配置缓存。"""
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    from src.python.config import get_llm_config
    get_llm_config()


def _cmd_config_llm_modules() -> None:
    """配置各 LLM 报告的启用/停用（编辑 llm_settings.json 的 enabled_llm）。"""
    from src.python.registry import get_llm_module_names

    result = _read_llm_settings()
    if result is None:
        return
    settings, settings_path = result

    enabled_map = settings.get("enabled_llm", {})
    module_names = get_llm_module_names()

    while True:
        print()
        print("  ┌── 配置支持LLM的报告模块 ──────────────────┐")
        items = []
        for i, (sfx, name) in enumerate(module_names.items(), 1):
            status = enabled_map.get(sfx, True)
            status_str = f"\033[92m开启\033[0m" if status else f"\033[91m关闭\033[0m"
            items.append((i, sfx, name, status))
            print(f"  │ {i}. {name:<14s} [{status_str}]\033[0m{' ' * 4}│")
        print(f"  │ 0. 返回主菜单{' ' * 27}│")
        print(f"  └{'─' * 42}┘")
        print()
        choice = input("  输入编号切换 (0-5): ").strip()

        if choice == "0":
            break

        try:
            idx = int(choice)
            matched = [it for it in items if it[0] == idx]
            if matched:
                _, sfx, name, curr = matched[0]
                enabled_map[sfx] = not curr
                settings["enabled_llm"] = enabled_map
                _write_llm_settings(settings, settings_path)
                print(f"  [OK] {name} 已{'开启' if not curr else '关闭'}")
            else:
                print("  [!] 无效编号")
        except (ValueError, TypeError):
            print("  [!] 请输入有效编号")

    _press_any_key()


# ── 刷新配置 ─────────────────────────────────────────────


def _cmd_refresh_config() -> None:
    """重新加载所有配置（config.json + llm_settings.json + llm_key.json）。"""
    from src.python.config import get_config, get_llm_config
    from src.python.llm.pricing import _reload_pricing

    # 破坏内部缓存强制重新读取
    import src.python.config as _cfg_mod
    _cfg_mod._config_cache = None
    _cfg_mod._config_mtime = 0
    _cfg_mod._llm_config_cache = None
    _cfg_mod._llm_config_mtime = 0

    config = get_config()
    llm_config = get_llm_config()
    _reload_pricing()

    # 刷新 tui_menu 配置缓存
    _refresh_config()

    if config:
        print("  [OK] config.json 已重新加载")
    if llm_config:
        print("  [OK] llm_settings.json + llm_key.json 已重新加载")
    else:
        print("  [!] LLM 未配置（llm_key.json 缺失或无效）")
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
