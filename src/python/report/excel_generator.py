"""Excel 报告生成核心函数。

从 tui_handlers.py 提取，通过 callbacks 参数与 TUI 交互。
"""

from __future__ import annotations

import time as _time_module
from datetime import datetime
from typing import Any

from src.python.config import get_llm_config
from src.python.logger import setup_logger
from src.python.registry import get_llm_module_name, get_report_sheet_name

logger = setup_logger()

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


def generate_excel_report(
    holdings: list, include_news: bool = False, output_dir: str = "reports",
    news_top_count: int = 100, include_llm: bool = False,
    show_llm_in_tui: bool = False, llm_content: tuple | None = None,
    details: list | None = None, a_indices: dict[str, dict[str, Any]] | None = None,
    us_indices: dict[str, dict[str, Any]] | None = None,
    news_data: list | None = None,
    llm_cached: tuple[bool, bool, bool, bool] = (False, False, False, False),
    news_llm_meta: dict | None = None,
    early_warnings: dict | None = None,
    callbacks: dict | None = None,
) -> None:
    """生成 Excel 报告的核心逻辑。

    Args:
        holdings: 持仓列表
        include_news: 是否包含新闻页签
        output_dir: 输出目录
        news_top_count: 新闻条数上限
        include_llm: 是否包含 LLM 分析章节
        show_llm_in_tui: 是否在 TUI 中展示 LLM 摘要
        llm_content: 预生成的 LLM 内容元组
        details: 预获取的市值核算明细
        a_indices: A 股指数数据
        us_indices: 美股指数数据
        news_data: 预获取的新闻数据
        llm_cached: 各 LLM 章节是否来自缓存
        news_llm_meta: 新闻 LLM 元数据
        early_warnings: 智能预警数据
        callbacks: TUI 交互回调字典，支持 key:
            - add_error(msg)
            - call_sheet(label, fn, *args, **kwargs)
            - show_llm_tui(global_macro, expert_review, health_check, penetration_deep)
            - print_llm_session_usage(usage)
    """
    cb = callbacks or {}
    _add_error = cb.get("add_error", lambda _: None)
    _call_sheet = cb.get("call_sheet", lambda _label, _fn, *a, **kw: None)
    _show_llm_tui = cb.get("show_llm_tui", lambda *a: None)
    _print_llm_session_usage = cb.get("print_llm_session_usage", lambda *a: None)

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
        _add_error(f"{get_llm_module_name('penetration_deep')}模块缺失 (penetration)")

    try:
        from src.python.report.fund_performance import write_fund_performance_sheet
    except ImportError:
        write_fund_performance_sheet = None
        _add_error("基金业绩模块缺失 (fund_performance)")

    # ── 创建工作簿（必须成功） ──
    wb = create_workbook()
    wb.remove(wb.active)

    # 预创建全部页签，确保 1→12 数字顺序从左到右
    ws1 = wb.create_sheet()  # 1. 汇总
    ws2 = wb.create_sheet()  # 2. 市值核算
    ws3 = wb.create_sheet()  # 3. 持仓分类
    ws4 = wb.create_sheet()  # 4. 资产穿透TOP10
    ws5 = wb.create_sheet()  # 5. 基金业绩分析
    ws6 = wb.create_sheet() if include_news else None  # 6. 财经新闻热点与持仓关联分析
    ws7 = wb.create_sheet() if include_news else None  # 7. 智能预警（仅在有新闻时生成）

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
        with _Timer(get_report_sheet_name('market_value')):
            write_market_value_sheet(ws2, holdings, details=details)
    else:
        with _Timer("行情数据获取 (" + get_report_sheet_name('market_value') + ")"):
            print("  [..] 正在获取行情数据（首次耗时较长，后续使用缓存）...")
            total_mv, total_cost, total_profit, today_profit, details = \
                write_market_value_sheet(ws2, holdings)
        print("  [OK] 行情数据获取完成")

    categories = classify_holdings(holdings) if classify_holdings else {}
    up_status = price_update_status(details, get_last_trading_day()) if price_update_status else (0, 0, True)

    # ── 市场指数 ──
    if a_indices is None:
        with _Timer("市场指数 (" + get_report_sheet_name('summary') + ")"):
            print("  [..] 正在获取市场指数...")
            a_indices = fetch_indices() if fetch_indices else {}
            if us_indices is None:
                us_indices = fetch_us_indices() if fetch_us_indices else {}
            print("  [OK] 市场指数获取完成")

    # ── 各页安全写入 ──
    _llm_session = None
    with _Timer(get_report_sheet_name('summary')):
        _call_sheet(get_report_sheet_name('summary'), write_summary_sheet,
                     ws1, total_mv, total_cost, total_profit, today_profit,
                     categories=categories, update_status=up_status,
                     a_indices=a_indices, us_indices=us_indices)

    with _Timer(get_report_sheet_name('category')):
        _call_sheet(get_report_sheet_name('category'), write_category_sheet, ws3, holdings, details)

    with _Timer(get_report_sheet_name('penetration')):
        pen_result = compute_penetration_top10(holdings, details) if compute_penetration_top10 else {}
        print("  [OK] 资产穿透TOP10 计算完成")
        _call_sheet(get_report_sheet_name('penetration'), write_penetration_sheet,
                     ws4, holdings, details, penetration_data=pen_result)

    with _Timer(get_report_sheet_name('fund_performance')):
        _call_sheet(get_report_sheet_name('fund_performance'), write_fund_performance_sheet, ws5, holdings, details)

    if include_news:
        penetrated_assets = pen_result.get("top10", []) if pen_result else []
        try:
            from src.python.report.news_correlation import write_news_sheet
        except ImportError:
            write_news_sheet = None
            _add_error(f"{get_llm_module_name('news_correlation')}模块缺失 (news_correlation)")

        with _Timer(get_llm_module_name('news_correlation')):
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
                    _add_error(f"{get_llm_module_name('news_correlation')}数据模块缺失")
                    news_data, _meta = [], {}
            _call_sheet(get_llm_module_name('news_correlation'), write_news_sheet, ws6, news_data, llm_meta=_meta)

        # 智能预警页签（依赖新闻 + 穿透数据）
        if include_news and ws7 is not None:
            if early_warnings is None:
                _early_warnings = {"sector_alerts": [], "sentiment_alerts": [],
                                   "has_warnings": False, "has_sector_data": False, "has_llm_news": False}
            else:
                _early_warnings = early_warnings
            try:
                from src.python.report.early_warning import write_early_warning_sheet
                _call_sheet(get_report_sheet_name('early_warning'), write_early_warning_sheet, ws7, _early_warnings)
            except ImportError as _ew_err:
                _add_error(f"智能预警模块缺失: {_ew_err}")

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
            from src.python.llm import get_session_usage
            _llm_session = get_session_usage()
        except (ImportError, TypeError, AttributeError):
            logger.debug("获取 LLM 会话用量失败（非关键，不展示用量信息）")
            _llm_session = None
        if _llm_session and _llm_session.get("call_count", 0) > 0:
            try:
                from src.python.report.summary import write_llm_usage_block
                write_llm_usage_block(ws1, _llm_session)
                from src.python.report.excel_writer import freeze_header, auto_width
                freeze_header(ws1, 2)
                auto_width(ws1)
            except (OSError, TypeError, AttributeError):
                logger.debug("写入 LLM 用量或格式化 worksheet 失败（非关键）")

        if show_llm_in_tui and (global_macro_text or expert_review_text or health_check_text or penetration_deep_text):
            _show_llm_tui(global_macro_text, expert_review_text, health_check_text, penetration_deep_text)

        _print_llm_session_usage(_llm_session)

    with _Timer("保存 Excel/HTML 文件"):
        print("  [..] 正在保存 Excel 报告...")
        path = save_workbook(wb, output_dir=output_dir)
        logger.info("Excel 报告已生成: %s", path)
        logger.info("总市值: %.2f元, 总成本: %.2f元, 总盈亏: %.2f元, 本日盈亏: %.2f元",
                    total_mv, total_cost, total_profit, today_profit)
        print(f"  [OK] Excel 报告已保存: {path}")
