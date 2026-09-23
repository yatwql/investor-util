"""基金重仓股 ROE 加权估算 —— 景气度框架②维「ROE 低位弹性」的基金层扩展（阶段一）。

动机：②维个股 ROE 只覆盖 A 股直接持仓；基金/ETF/联接/QDII 无个股 ROE，其权重只能
标「需核实」不计分。本模块对基金按其**前十大重仓股**的 ROE 加权，估算基金层 ROE。

口径与红线：
  - 属「按框架推演」：框架原意是选股层面的 ROE 弹性，基金层 ROE 为重仓股加权推演值，
    评分证据与持仓视角一律标注推演属性，**不得**冒充基金披露口径；
  - 阶段一仅按前十大重仓口径（`basis="top10_holdings"`），``covered_pct`` 如实披露
    重仓覆盖比例；阶段二（全量持仓口径）落地后替换取数来源，记录契约不变，
    由 ``basis`` 字段区分口径；
  - 报告期陈旧的基金持仓快照不参与估算（与穿透层共用同一时效闸门）；
  - 全部取数复用既有链路（``fetch_fund_holdings_batch`` / ``fetch_latest_indicator``），
    不新增 HTTP 通道；任一基金估算失败只缺席该基金，不拖垮诊断其余维度。
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Any

from src.python.core.code_utils import is_a_share_code

logger = logging.getLogger("invest")

#: 估算依据口径：前十大重仓股加权（阶段一）。全量持仓口径落地后新增取值，旧值保留。
ESTIMATE_BASIS_TOP10 = "top10_holdings"

#: 估算记录契约：{"roe": float, "covered_pct": float, "top_n": int,
#:                "basis": str, "report_period": str}


def weighted_roe(items: list[tuple[float, float]]) -> float | None:
    """重仓股 ROE 加权平均（纯计算）。

    Args:
        items: [(重仓占比（占基金净值 %，0~100）, 该股 ROE（小数）)]，仅含已覆盖项。

    Returns:
        加权 ROE（小数）；无有效项返回 None。
    """
    valid = [(r, roe) for r, roe in items if r > 0]
    if not valid:
        return None
    total_ratio = sum(r for r, _ in valid)
    return sum(r * roe for r, roe in valid) / total_ratio


def _fetch_stock_roe_batch(codes: list[str]) -> dict[str, float]:
    """批量取 A 股个股最新 ROE（复用财务指标链路，含缓存与降级）。

    并发数与限速口径对齐财务指标章（同为 akshare 指标取数）。
    """
    if not codes:
        return {}
    from src.python.fetcher.batch import BatchDispatcher, get_batch_worker_count
    from src.python.fetcher.financial_indicator import fetch_latest_indicator

    dispatcher = BatchDispatcher(
        max_workers=get_batch_worker_count("akshare_workers", 2),
        thread_name_prefix="batch_stock_roe",
        # 财务指标主源经 akshare 访问东方财富后端，复用其限速档
        rate_limit_provider="eastmoney",
    )
    try:
        results = dispatcher.execute([partial(fetch_latest_indicator, code) for code in codes])
    finally:
        dispatcher.shutdown()
    roe_map: dict[str, float] = {}
    for code, r in zip(codes, results):
        record = r.result if r.success else None
        roe = (record or {}).get("roe")
        if isinstance(roe, (int, float)):
            roe_map[code] = float(roe)
    return roe_map


def estimate_fund_roe_batch(
    fund_items: list[dict[str, Any]],
    *,
    known_roe: dict[str, float] | None = None,
) -> dict[str, dict[str, Any]]:
    """对若干基金按重仓股 ROE 加权，估算基金层 ROE（阶段一：前十大重仓口径）。

    Args:
        fund_items: [{"code", "name"}] 基金清单（调用方按权益类基金类型预筛）。
        known_roe: 已有股票 ROE 映射（如 `financial_indicator_data` 行），命中不再取数。

    Returns:
        {fund_code: 估算记录} 映射；持仓缺失/陈旧/无覆盖的基金不出现在结果中。
    """
    if not fund_items:
        return {}

    from src.python.fetcher.fund import fetch_fund_holdings_batch
    from src.python.report.holdings_freshness import is_stale_report, parse_report_date

    known_roe = dict(known_roe or {})
    codes = [str(f.get("code") or "") for f in fund_items]
    holdings_batch = fetch_fund_holdings_batch(codes)

    # ── 第一遍：筛出有效重仓股，收集需补取 ROE 的代码 ──
    per_fund: dict[str, list[tuple[str, float]]] = {}
    periods: dict[str, str] = {}
    for fund in fund_items:
        code = str(fund.get("code") or "")
        name = str(fund.get("name") or code)
        payload = holdings_batch.get(code)
        if not payload or not payload.get("holdings"):
            continue
        # 报告期闸门：陈旧快照与当期配置可能严重脱节，不参与估算（同穿透层口径）
        report_date = parse_report_date(payload.get("date"))
        if is_stale_report(report_date):
            logger.info("[fund_roe_estimate] 基金 %s(%s) 持仓报告期陈旧，跳过 ROE 估算", name, code)
            continue
        items = [
            (str(it.get("code") or "").strip(), float(it.get("ratio") or 0.0))
            for it in payload["holdings"]
            if 0 < float(it.get("ratio") or 0.0) <= 100
        ]
        a_items = [(c, r) for c, r in items if c and is_a_share_code(c)]
        if not a_items:
            continue
        per_fund[code] = a_items
        periods[code] = str(payload.get("date") or "")

    if not per_fund:
        return {}

    # ── 补齐缺失的股票 ROE（known_roe 命中不取数） ──
    all_codes = sorted({c for items in per_fund.values() for c, _ in items})
    missing_codes = [c for c in all_codes if c not in known_roe]
    fetched = _fetch_stock_roe_batch(missing_codes)
    roe_map = {**fetched, **known_roe}

    # ── 第二遍：逐基金加权 ──
    estimates: dict[str, dict[str, Any]] = {}
    for code, items in per_fund.items():
        covered = [(r, roe_map[c]) for c, r in items if c in roe_map]
        roe_est = weighted_roe(covered)
        if roe_est is None:
            continue
        estimates[code] = {
            "roe": round(roe_est, 4),
            "covered_pct": round(sum(r for r, _ in covered), 2),
            "top_n": len(covered),
            "basis": ESTIMATE_BASIS_TOP10,
            "report_period": periods.get(code, ""),
        }
    logger.info(
        "[fund_roe_estimate] 基金重仓 ROE 估算完成：%d/%d 只基金有估算值",
        len(estimates),
        len(fund_items),
    )
    return estimates
