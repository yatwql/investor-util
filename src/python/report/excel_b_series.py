"""B 系列基金深度分析页签写入模块。

职责：基金经理变更监控、持仓重合度矩阵、持仓集中度监控、基金风格漂移分析。
提取自 excel_generator.py 的 _write_b_series_sheets。

注：三个模块（重合度/集中度/风格）共享相同的数据准备模板，
通过 _process_b_module 辅助函数消除重复代码。
"""

from __future__ import annotations

from typing import Any, Callable

from src.python.fetcher.fund import fetch_fund_holdings
from src.python.logger import setup_logger
from src.python.provider_registry import NOT_FOUND, get_registry
from src.python.report.fund_performance import is_fund
from src.python.report.progress import ProgressReporter

logger = setup_logger()


def _fetch_fund_holdings_cached(code: str) -> dict | None:
    """基金持仓获取（含会话缓存），同一报告生成中同基金只获取一次。"""
    registry = get_registry()
    cached = registry.session_cache_get("fund_hold", code)
    if cached is not NOT_FOUND:
        return cached
    result = fetch_fund_holdings(code)
    registry.session_cache_set("fund_hold", code, result, source="api")
    return result


def _process_b_module(
    holdings: list,
    process_fn: Callable,
    prog: ProgressReporter,
) -> tuple[list[str], dict[str, dict]]:
    """B 系列模块通用数据准备模板。

    每个调用方自行封装 try/except，此函数不捕获异常。
    返回 (fund_codes, fund_holdings_map)，其中 fund_holdings_map
    的键是基金代码，值是 {"name": ..., "holdings": [...]}。
    """
    fund_codes = list(dict.fromkeys(
        h.code for h in holdings if is_fund(h)
    ))
    fund_holdings_map: dict[str, dict] = {}
    for code in fund_codes:
        fh = _fetch_fund_holdings_cached(code)
        if fh and fh.get("holdings"):
            fund_holdings_map[code] = {
                "name": fh.get("name", code),
                "holdings": fh["holdings"],
            }

    return fund_codes, fund_holdings_map


def write_b_series_sheets(
    sheets: dict[str, Any], holdings: list,
    enable_b_series: bool, data: dict[str, Any],
    modules: dict[str, Any],
    prog: ProgressReporter,
) -> None:
    """写入基金深度分析页签（B 系列）。"""
    if not enable_b_series:
        return

    # ── 基金经理变更监控（独立逻辑，无 fetch_fund_holdings 依赖） ──
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

    # ── 14. 持仓重合度矩阵 ──
    compute_overlap = modules.get("compute_overlap_matrix")
    write_overlap = modules.get("write_overlap_matrix_sheet")
    ws14 = sheets.get("fund_overlap")
    if ws14 is not None and compute_overlap is not None and write_overlap is not None:
        prog.info("正在计算持仓重合度矩阵...")
        overlap_result = None
        fund_names: dict[str, str] = {}
        try:
            fund_codes, fund_holdings_map = _process_b_module(holdings, compute_overlap, prog)
            if len(fund_codes) < 2:
                logger.info("持仓重合度矩阵：基金数 < 2（%d），跳过", len(fund_codes))
            elif len(fund_holdings_map) >= 2:
                fund_holdings_raw: dict[str, list[dict]] = {}
                for code, v in fund_holdings_map.items():
                    fund_holdings_raw[code] = v["holdings"]
                    fund_names[code] = v["name"]

                details = data.get("details", [])
                fund_mv_map: dict[str, float] = {}
                for d in details:
                    if d.code in fund_codes:
                        fund_mv_map[d.code] = fund_mv_map.get(d.code, 0.0) + d.market_value

                overlap_result = compute_overlap(
                    fund_holdings_raw,
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

    # ── 15. 持仓集中度监控 ──
    compute_conc = modules.get("compute_concentration")
    write_conc = modules.get("write_concentration_sheet")
    ws15 = sheets.get("fund_concentration")
    if ws15 is not None and compute_conc is not None and write_conc is not None:
        prog.info("正在计算持仓集中度...")
        conc_data = None
        try:
            _, conc_fund_holdings = _process_b_module(holdings, compute_conc, prog)
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

    # ── 16. 基金风格分析 ──
    analyze_style = modules.get("analyze_style_for_all_funds")
    write_style = modules.get("write_style_sheet")
    ws16 = sheets.get("fund_style")
    if ws16 is not None and analyze_style is not None and write_style is not None:
        prog.info("正在分析基金风格漂移...")
        style_result = None
        try:
            _, style_fund_holdings = _process_b_module(holdings, analyze_style, prog)
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
