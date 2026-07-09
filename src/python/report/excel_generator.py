"""Excel 报告生成核心函数。

通过 ProgressReporter 接口输出进度，不依赖 TUI。
"""

from __future__ import annotations

from typing import Any

from src.python.logger import setup_logger
from src.python.registry import get_report_section_order
from src.python.report.excel_module_loader import load_report_modules
from src.python.report.excel_content_sheets import write_content_sheets
from src.python.report.excel_market_data import resolve_market_data, resolve_indices
from src.python.report.excel_news_warning import write_news_and_early_warning
from src.python.report.excel_sheet_factory import create_sheets
from src.python.report.progress import ProgressReporter, SilentProgressReporter, _Timer

logger = setup_logger()


def _write_b_series_sheets(
    sheets: dict[str, Any], holdings: list,
    enable_b_series: bool, data: dict[str, Any],
    modules: dict[str, Any],
    prog: ProgressReporter,
) -> None:
    """写入基金深度分析页签（B 系列）。"""
    if not enable_b_series:
        return
    # 基金经理变更监控
    detect = modules.get("detect_manager_changes", lambda _h: [])
    ws13 = sheets.get("fund_manager")
    if ws13 is not None:
        prog.info("正在分析基金经理变更...")
        try:
            manager_data = detect(holdings)
        except Exception as e:
            logger.warning("基金经理变更监控数据获取失败: %s", e)
            prog.add_error("基金经理变更监控数据获取失败")
            manager_data = None

        write_fund_mgr = modules.get("write_fund_manager_sheet")
        if write_fund_mgr:
            try:
                write_fund_mgr(ws13, manager_data or [])
                prog.ok("基金经理变更监控页签写入完成")
            except Exception as e:
                logger.warning("基金经理变更监控页签写入失败: %s", e)
                prog.add_error("基金经理变更监控页签写入失败")

    # 14. 持仓重合度矩阵
    compute_overlap = modules.get("compute_overlap_matrix")
    write_overlap = modules.get("write_overlap_matrix_sheet")
    ws14 = sheets.get("fund_overlap")
    if ws14 is not None and compute_overlap is not None and write_overlap is not None:
        prog.info("正在计算持仓重合度矩阵...")
        fund_names: dict[str, str] = {}
        overlap_result = None
        try:
            from src.python.fetcher.fund import fetch_fund_holdings
            from src.python.report.fund_performance import _is_fund

            # 筛选基金持仓，获取每只基金的持仓数据 + 市值
            fund_codes = list(dict.fromkeys(
                h.code for h in holdings if _is_fund(h)
            ))
            if len(fund_codes) < 2:
                logger.info("持仓重合度矩阵：基金数 < 2（%d），跳过", len(fund_codes))
            else:
                # 构建 fund_holdings（复用缓存，0 额外 HTTP）
                fund_holdings: dict[str, list[dict]] = {}
                for code in fund_codes:
                    fh = fetch_fund_holdings(code)
                    if fh and fh.get("holdings"):
                        fund_holdings[code] = fh["holdings"]
                        fund_names[code] = fh.get("name", code)

                if len(fund_holdings) >= 2:
                    # 构建 fund_mv_map（从市值核算明细中提取）
                    details = data.get("details", [])
                    fund_mv_map: dict[str, float] = {}
                    for d in details:
                        if d.code in fund_codes:
                            fund_mv_map[d.code] = fund_mv_map.get(d.code, 0.0) + d.market_value

                    overlap_result = compute_overlap(
                        fund_holdings,
                        fund_mv_map=fund_mv_map if fund_mv_map else None,
                    )
                    if overlap_result:
                        overlap_result["fund_names"] = fund_names
                else:
                    logger.info("持仓重合度矩阵：无可用的基金持仓数据")
        except Exception as e:
            logger.warning("持仓重合度矩阵数据获取/计算失败: %s", e)
            prog.add_error("持仓重合度矩阵数据获取失败")

        try:
            write_overlap(ws14, overlap_result or {}, fund_names=fund_names)
            prog.ok("持仓重合度矩阵页签写入完成")
        except Exception as e:
            logger.warning("持仓重合度矩阵页签写入失败: %s", e)
            prog.add_error("持仓重合度矩阵页签写入失败")

    # 15. 持仓集中度监控
    compute_conc = modules.get("compute_concentration")
    write_conc = modules.get("write_concentration_sheet")
    ws15 = sheets.get("fund_concentration")
    if ws15 is not None and compute_conc is not None and write_conc is not None:
        prog.info("正在计算持仓集中度...")
        conc_data = None
        try:
            from src.python.fetcher.fund import fetch_fund_holdings
            from src.python.report.fund_performance import _is_fund

            fund_codes = list(dict.fromkeys(
                h.code for h in holdings if _is_fund(h)
            ))
            conc_fund_holdings: dict[str, dict] = {}
            for code in fund_codes:
                fh = fetch_fund_holdings(code)
                if fh and fh.get("holdings"):
                    conc_fund_holdings[code] = {
                        "name": fh.get("name", code),
                        "holdings": fh["holdings"],
                    }

            if conc_fund_holdings:
                conc_data = compute_conc(conc_fund_holdings)
                if conc_data:
                    prog.ok("持仓集中度计算完成")
                else:
                    logger.info("持仓集中度监控：无持仓数据")
            else:
                logger.info("持仓集中度监控：无基金持仓数据")
        except Exception as e:
            logger.warning("持仓集中度数据获取/计算失败: %s", e)
            prog.add_error("持仓集中度数据获取失败")

        try:
            write_conc(ws15, conc_data or [])
            prog.ok("持仓集中度监控页签写入完成")
        except Exception as e:
            logger.warning("持仓集中度监控页签写入失败: %s", e)
            prog.add_error("持仓集中度监控页签写入失败")

    # 16. 基金风格分析
    analyze_style = modules.get("analyze_style_for_all_funds")
    write_style = modules.get("write_style_sheet")
    ws16 = sheets.get("fund_style")
    if ws16 is not None and analyze_style is not None and write_style is not None:
        prog.info("正在分析基金风格漂移...")
        style_result = None
        try:
            from src.python.fetcher.fund import fetch_fund_holdings
            from src.python.report.fund_performance import _is_fund

            fund_codes = list(dict.fromkeys(
                h.code for h in holdings if _is_fund(h)
            ))
            style_fund_holdings: dict[str, dict] = {}
            for code in fund_codes:
                fh = fetch_fund_holdings(code)
                if fh and fh.get("holdings"):
                    style_fund_holdings[code] = {
                        "name": fh.get("name", code),
                        "holdings": fh["holdings"],
                    }

            if style_fund_holdings:
                style_result = analyze_style(style_fund_holdings)
                if style_result.get("results"):
                    prog.ok("基金风格分析计算完成")
                else:
                    logger.info("基金风格分析：无结果")
            else:
                logger.info("基金风格分析：无基金持仓数据")
        except Exception as e:
            logger.warning("基金风格分析数据获取/计算失败: %s", e)
            prog.add_error("基金风格分析数据获取失败")

        try:
            write_style(ws16, (style_result or {}).get("results", []))
            prog.ok("基金风格分析页签写入完成")
        except Exception as e:
            logger.warning("基金风格分析页签写入失败: %s", e)
            prog.add_error("基金风格分析页签写入失败")


def _write_llm_section_and_usage(
    sheets: dict[str, Any], include_llm: bool, llm_content: tuple[str | None, str | None, str | None, str | None] | None,
    prog: ProgressReporter, section_order: list[dict] | None = None,
) -> None:
    """写入 LLM 分析章节页签和 LLM API 用量页签。"""
    if not include_llm:
        return

    with _Timer("LLM 分析章节"):
        prog.info("正在生成 LLM 分析章节...")
        try:
            from src.python.report.llm_content import write_llm_sheets
            write_llm_sheets(sheets, llm_content=llm_content or (None, None, None, None), section_order=section_order)
            logger.info("LLM 分析章节已生成")
            prog.ok("LLM 分析章节生成完成")
        except ImportError:
            logger.warning("LLM 分析章节模块 (src.python.report.llm_content) 未就绪，跳过")
            prog.add_error("LLM 分析章节模块未就绪，跳过")
        except Exception:
            logger.exception("生成 LLM 分析章节失败")
            prog.add_error("LLM 分析章节生成失败（详情请查看日志）")

    _build_llm_usage_sheet(sheets, prog)


def _build_llm_usage_sheet(sheets: dict[str, Any], _prog: ProgressReporter) -> None:
    """构建并写入 LLM API 用量页签。"""
    try:
        from src.python.llm import (
            FAIL_REASON_DISABLED,
            format_session_usage,
            get_session_usage,
        )
        from src.python.llm.prompts import _LLM_MODULE_FAILURE
        from src.python.registry import get_llm_module_names
        from src.python.report.summary import write_llm_usage_sheet
    except (ImportError, AttributeError) as e:
        logger.debug("LLM 用量页签模块未就绪（非关键）: %s", e)
        return

    raw_session = get_session_usage()
    formatted = format_session_usage(raw_session)
    if not formatted:
        return

    # 从原始会话数据获取 per_module（raw_session 始终有该键，而 formatted
    # 在 has_usage=False 时可能不含 per_module），确保缓存场景等所有路径都能拿到数据
    per_module = raw_session.get("per_module", {}) or {}
    if not per_module:
        logger.debug("LLM 会话数据中 per_module 为空，尝试从 formatted 获取")
        per_module = formatted.get("per_module", {}) or {}
    all_failure = dict(_LLM_MODULE_FAILURE)
    names_map = get_llm_module_names()

    MODULE_KEYS = ["global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation"]
    DISPLAY_REASON = {
        "not_configured": "LLM 未配置",
        "api_error": "LLM API 调用失败",
        "network_error": "LLM API 网络连接失败",
        "timeout": "LLM API 请求超时",
        "circuit_open": "LLM API 暂时不可用（熔断冷却中）",
    }

    excel_module_info: list[dict] = []
    for mk in MODULE_KEYS:
        entry: dict = {"key": mk, "name": names_map.get(mk, mk)}
        reason = all_failure.get(mk)
        pm = per_module.get(mk)
        if reason == FAIL_REASON_DISABLED:
            entry.update({"status": "disabled", "status_label": "已禁用",
                          "model": "", "input_tokens": 0, "output_tokens": 0,
                          "total_tokens": 0, "cache_hit_tokens": 0,
                          "cost": 0.0, "cached": False, "thinking": False, "endpoint": ""})
        elif reason:
            reason_text = DISPLAY_REASON.get(str(reason).lower(), str(reason))
            entry.update({"status": "failed", "status_label": reason_text,
                          "model": "", "input_tokens": 0, "output_tokens": 0,
                          "total_tokens": 0, "cache_hit_tokens": 0,
                          "cost": 0.0, "cached": False, "thinking": False, "endpoint": ""})
        elif pm:
            inp = pm.get("input_tokens", 0)
            out = pm.get("output_tokens", 0)
            entry.update({
                "status": "cached" if pm.get("cached") else "success",
                "status_label": "缓存" if pm.get("cached") else "成功",
                "model": pm.get("model", ""),
                "input_tokens": inp, "output_tokens": out,
                "total_tokens": inp + out,
                "cache_hit_tokens": pm.get("cache_hit_tokens", 0),
                "cost": pm.get("cost", 0.0),
                "cached": pm.get("cached", False),
                "thinking": pm.get("thinking", False),
                "endpoint": pm.get("endpoint", ""),
            })
        else:
            continue  # 无状态的模块不加入明细
        if entry.get("status_label"):
            excel_module_info.append(entry)

    if not excel_module_info:
        return

    ws = sheets.get("llm_usage")
    if ws is None:
        logger.debug("llm_usage 页签未被创建，跳过 API 用量写入")
        return
    glb_endpoint = next((mi["endpoint"] for mi in excel_module_info if mi.get("endpoint")), "")
    try:
        write_llm_usage_sheet(ws, formatted, excel_module_info, llm_endpoint=glb_endpoint)
    except Exception as e:
        logger.debug("创建 LLM API 用量页签失败（非关键）: %s", e)


def generate_excel_report(
    holdings: list, include_news: bool = False, output_dir: str = "reports",
    news_top_count: int = 100, include_llm: bool = False,
    llm_content: tuple[str | None, str | None, str | None, str | None] | None = None,
    details: list | None = None, a_indices: dict[str, dict[str, Any]] | None = None,
    us_indices: dict[str, dict[str, Any]] | None = None,
    news_data: list | None = None,
    news_llm_meta: dict | None = None,
    early_warnings: dict | None = None,
    include_b_series: bool | None = None,  # renamed from include_fund_deep
    progress: ProgressReporter | None = None,
    section_order: list[dict] | None = None,
) -> None:
    """生成 Excel 报告的核心逻辑。

    Args:
        holdings: 持仓列表
        include_news: 是否包含新闻页签
        output_dir: 输出目录
        news_top_count: 新闻条数上限
        include_llm: 是否包含 LLM 分析章节
        llm_content: 预生成的 LLM 内容元组
        details: 预获取的市值核算明细
        a_indices: A 股指数数据
        us_indices: 美股指数数据
        news_data: 预获取的新闻数据
        news_llm_meta: 新闻 LLM 元数据
        early_warnings: 智能预警数据
        include_b_series: 是否包含 B 系列页签（基金深度分析）。
            None 时跟随 include_news（B/L 含，E/H 不含）。已从 include_fund_deep 重命名。
        progress: 进度报告接口（默认 SilentProgressReporter，不输出）
        section_order: 可选的自定义报告模块顺序，来自 get_report_section_order(config)
    """
    prog = progress if progress is not None else SilentProgressReporter()

    # B 系列跟随 include_news（B/L 菜单含新闻 = 含 B 系列）
    enable_b_series = include_news if include_b_series is None else include_b_series

    modules = load_report_modules(prog)
    if not modules:
        return  # excel_writer 缺失，无法继续

    create_workbook = modules["create_workbook"]
    save_workbook = modules["save_workbook"]

    # ── 创建工作簿，按需创建全部页签 ──
    wb = create_workbook()
    wb.remove(wb.active)
    order = section_order or get_report_section_order()  # 内部名 order，避免影子覆盖参数
    sheets = create_sheets(wb, order,
                            enable_b_series=enable_b_series,
                            include_news=include_news,
                            include_llm=include_llm)

    # ── 行情市值 + 指数 ──
    data = resolve_market_data(holdings, details, modules, sheets["market_value"], prog)
    a_idx, us_idx = resolve_indices(a_indices, us_indices, modules, prog)

    # ── 各页签写入 ──
    pen_result = write_content_sheets(sheets, holdings, data, a_idx, us_idx, modules, prog)
    write_news_and_early_warning(sheets, holdings, pen_result, include_news,
                                  news_data, news_llm_meta, news_top_count,
                                  early_warnings, prog)
    _write_b_series_sheets(sheets, holdings, enable_b_series, data, modules, prog)
    _write_llm_section_and_usage(sheets, include_llm, llm_content, prog, section_order=order)

    # ── 保存 ──
    with _Timer("保存 Excel/HTML 文件"):
        prog.info("正在保存 Excel 报告...")
        path = save_workbook(wb, output_dir=output_dir)
        logger.info("Excel 报告已生成: %s", path)
        logger.info("总市值: %.2f元, 总成本: %.2f元, 总盈亏: %.2f元, 本日盈亏: %.2f元",
                    data["total_mv"], data["total_cost"],
                    data["total_profit"], data["today_profit"])
        prog.ok(f"Excel 报告已保存: {path}")
