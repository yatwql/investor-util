"""基金深度分析页签写入模块。

职责：基金经理变更监控、持仓关系矩阵、持仓集中度监控、风格与因子分析。

注：三个模块（重合度/集中度/风格）共享相同的数据准备模板，
通过 _process_fund_deep_analysis_module 辅助函数消除重复代码。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.python.core.logger import setup_logger
from src.python.fetcher.fund import fetch_fund_holdings_cached
from src.python.report.fund_performance import is_fund
from src.python.report.progress import ProgressReporter

logger = setup_logger()


def _process_fund_deep_analysis_module(
    holdings: list,
    process_fn: Callable,
    prog: ProgressReporter,
) -> tuple[list[str], dict[str, dict]]:
    """基金深度分析模块通用数据准备模板。

    每个调用方自行封装 try/except，此函数不捕获异常。
    返回 (fund_codes, fund_holdings_map)，其中 fund_holdings_map
    的键是基金代码，值是 {"name": ..., "holdings": [...]}。
    """
    fund_codes = list(dict.fromkeys(h.code for h in holdings if is_fund(h)))
    fund_holdings_map: dict[str, dict] = {}
    for code in fund_codes:
        fh = fetch_fund_holdings_cached(code)
        if fh and fh.get("holdings"):
            fund_holdings_map[code] = {
                "name": fh.get("name", code),
                "holdings": fh["holdings"],
            }

    return fund_codes, fund_holdings_map


def write_fund_deep_analysis_sheets(
    sheets: dict[str, Any],
    holdings: list,
    enable_fund_deep_analysis: bool,
    data: dict[str, Any],
    modules: dict[str, Any],
    prog: ProgressReporter,
    style_factor_data: dict[str, Any] | None = None,
    position_relationship_data: dict[str, Any] | None = None,
) -> None:
    """写入基金深度分析页签。

    Args:
        style_factor_data: 风格与因子分析数据契约 dict，来自 pipeline_data
            （style_factor_data 主键，内嵌 industry_beta 子键）；
            未提供或 available=False 时因子回归区块写入占位（§1.4.5 降级治理）。
        position_relationship_data: 持仓关系矩阵数据契约 dict（相关性区块数据源），
            来自 pipeline_data；未提供或 available=False 时相关性区块写入占位（§1.4.5 降级治理）。
    """
    if not enable_fund_deep_analysis:
        return

    # ── 基金经理变更监控（独立逻辑，无 fetch_fund_holdings 依赖） ──
    detect = modules.get("detect_manager_changes", lambda _h: [])
    ws_mgr = sheets.get("fund_manager")
    if ws_mgr is not None:
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
                write_fund_mgr(ws_mgr, manager_data or [])
                prog.ok("基金经理变更监控页签写入完成")
            except Exception as e:
                logger.warning("基金经理变更监控页签写入失败: %s", e)
                prog.add_error("基金经理变更监控页签写入失败")

    # ── 持仓关系矩阵（一章两区块：持仓重合度 + 持仓相关性） ──
    compute_overlap = modules.get("compute_overlap_matrix")
    write_pr = modules.get("write_position_relationship_sheet")
    ws_pr = sheets.get("position_relationship")
    if ws_pr is not None and compute_overlap is not None and write_pr is not None:
        prog.info("正在计算持仓重合度矩阵...")
        overlap_result = None
        fund_names: dict[str, str] = {}
        try:
            fund_codes, fund_holdings_map = _process_fund_deep_analysis_module(holdings, compute_overlap, prog)
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
            write_pr(
                ws_pr,
                overlap_result,
                fund_names=fund_names,
                correlation_data=position_relationship_data,
            )
            prog.ok("持仓关系矩阵页签写入完成")
        except Exception as e:
            logger.warning("持仓关系矩阵页签写入失败: %s", e)
            prog.add_error("持仓关系矩阵页签写入失败")

    # ── 持仓集中度监控 ──
    compute_conc = modules.get("compute_concentration")
    write_conc = modules.get("write_concentration_sheet")
    ws_conc = sheets.get("fund_concentration")
    if ws_conc is not None and compute_conc is not None and write_conc is not None:
        prog.info("正在计算持仓集中度...")
        conc_data = None
        try:
            _, conc_fund_holdings = _process_fund_deep_analysis_module(holdings, compute_conc, prog)
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
            write_conc(ws_conc, conc_data or [])
            prog.ok("持仓集中度监控页签写入完成")
        except Exception as e:
            logger.warning("持仓集中度监控页签写入失败: %s", e)
            prog.add_error("持仓集中度监控页签写入失败")

    # ── 风格与因子分析（一章三区块：基金风格表 + 风格因子回归 + 行业 Beta 子表） ──
    # style_factor_data 来自编排层 pipeline_data（style_factor_data 主键，
    # 内嵌 industry_beta 子键）；风格表 results 为渲染期派生（不进数据契约）。
    # 三区块独立降级（§1.4.5）：风格表空/因子空/行业 Beta 关均不影响其余区块。
    analyze_style = modules.get("analyze_style_for_all_funds")
    write_sf = modules.get("write_style_factor_sheet")
    ws_sf = sheets.get("style_factor")
    if ws_sf is not None and write_sf is not None:
        prog.info("正在写入风格与因子分析页签...")
        style_result = None
        if analyze_style is not None:
            try:
                _, sf_fund_holdings = _process_fund_deep_analysis_module(holdings, analyze_style, prog)
                if sf_fund_holdings:
                    style_result = analyze_style(sf_fund_holdings)
                    if (style_result or {}).get("results"):
                        prog.ok("风格与因子分析计算完成")
                    else:
                        logger.info("风格与因子分析：无结果")
                else:
                    logger.info("风格与因子分析：无基金持仓数据")
            except Exception as e:
                logger.warning("风格与因子分析数据获取/计算失败: %s", e)
                prog.add_error("风格与因子分析数据获取失败")

        _factor_names = None
        if style_factor_data:
            try:
                from src.python.analysis.style_factor_regression import FACTOR_NAMES

                _factor_names = FACTOR_NAMES
            except Exception:
                _factor_names = None
        try:
            write_sf(
                ws_sf,
                style_data=(style_result or {}).get("results", []),
                factor_exposure=style_factor_data,
                factor_names=_factor_names,
                industry_beta=(style_factor_data or {}).get("industry_beta"),
            )
            prog.ok("风格与因子分析页签写入完成")
        except Exception as e:
            logger.warning("风格与因子分析页签写入失败: %s", e)
            prog.add_error("风格与因子分析页签写入失败")
