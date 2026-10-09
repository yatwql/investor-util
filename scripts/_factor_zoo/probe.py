"""股票池与字段可得性探测（穿透池只读复用 + 经既有链路逐因子探测）。"""

from __future__ import annotations

from typing import Any
from typing import Callable
import time

from _factor_zoo.catalog import (
    BENCHMARK_INDEX,
    FIELD_BARS,
    FIELD_FIN,
    FIELD_INDEX,
    FIELD_VAL,
    LOOKBACK_DAYS,
    TYPE_COVERAGE,
)


def build_stock_pool(holdings_path: str) -> dict[str, Any]:
    """穿透持仓股票池（只读复用穿透模块输出 + 直接持仓 A 股）。

    返回 {"codes": [...升序唯一...], "holdings_file", "direct_stocks",
          "penetration_stocks", "built_at"}；穿透失败时回退直接持仓并记录原因。
    """
    from src.python.core.code_utils import is_a_share_stock
    from src.python.core.reader import read_holdings
    from src.python.report.market_value import DetailRow
    from src.python.report.penetration import compute_penetration_top10

    holdings = read_holdings(holdings_path)
    # 名称 + 代码双维判定（排除 00 前缀重叠区场外基金，如 002943）
    direct = sorted({h.code for h in holdings if is_a_share_stock(h.name, h.code)})
    details = [
        DetailRow(
            name=h.name,
            code=h.code,
            market_value=h.shares * h.cost_price,
            cost=h.shares * h.cost_price,
            profit=0.0,
            account=h.account,
        )
        for h in holdings
    ]
    penetration: list[str] = []
    note = ""
    try:
        result = compute_penetration_top10(holdings, details)
        penetration = _extract_share_codes(result.get("top10") or [])
    except Exception as exc:  # 穿透失败回退直接持仓（池缩小会在判定书如实记录）
        note = f"穿透失败回退直接持仓: {type(exc).__name__}: {exc}"
    codes = sorted(set(direct) | set(penetration))
    return {
        "codes": codes,
        "holdings_file": str(holdings_path),
        "direct_stocks": direct,
        "penetration_stocks": sorted(set(penetration)),
        "penetration_note": note,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _extract_share_codes(nodes: Any) -> list[str]:
    """从穿透 top10 结构中递归收集 A 股代码（code 标量 / codes 列表两种形状）。"""
    from src.python.core.code_utils import is_a_share_code

    found: set[str] = set()
    if isinstance(nodes, dict):
        code = nodes.get("code")
        if isinstance(code, str) and is_a_share_code(code):
            found.add(code)
        codes = nodes.get("codes")
        if isinstance(codes, (list, tuple)):
            for item in codes:
                if isinstance(item, str) and is_a_share_code(item):
                    found.add(item)
        for value in nodes.values():
            found.update(_extract_share_codes(value))
    elif isinstance(nodes, (list, tuple)):
        for item in nodes:
            found.update(_extract_share_codes(item))
    return sorted(found)


def probe_bars(code: str) -> list[dict]:
    """日 K 线（history_stock 链，增量合并缓存）。"""
    from src.python.fetcher.chain_incremental import fetch_with_incremental_fallback

    try:
        return fetch_with_incremental_fallback("history_stock", code, LOOKBACK_DAYS) or []
    except Exception as exc:
        print(f"    [!] {code} 日K失败: {type(exc).__name__}: {exc}")
        return []


def probe_index() -> list[dict]:
    """基准指数历史（history_index 链）。"""
    from src.python.fetcher.index import fetch_index_history

    try:
        return fetch_index_history(BENCHMARK_INDEX, LOOKBACK_DAYS) or []
    except Exception as exc:
        print(f"    [!] 指数历史失败: {type(exc).__name__}: {exc}")
        return []


def probe_valuation(code: str) -> dict | None:
    """当前 PE/PB/市值（push2 扩展字段，经行业数据入口）。"""
    from src.python.fetcher.industry import fetch_valuation_fields

    try:
        return fetch_valuation_fields(code)
    except Exception as exc:
        print(f"    [!] {code} 估值失败: {type(exc).__name__}: {exc}")
        return None


def probe_fin_indicator(code: str) -> dict | None:
    """最新报告期财务指标（financial_indicator 链）。"""
    from src.python.fetcher.financial_indicator import fetch_latest_indicator

    try:
        return fetch_latest_indicator(code)
    except Exception as exc:
        print(f"    [!] {code} 财务指标失败: {type(exc).__name__}: {exc}")
        return None


def _value_present(value: Any) -> bool:
    return value is not None and not (isinstance(value, float) and value != value)


def probe_fields(
    catalog: list[dict[str, Any]], pool: dict[str, Any], probes: dict[str, Callable[..., Any]] | None = None
) -> dict[str, Any]:
    """逐字段类型探测池内可得性（每类型记录耗时；因子可得性在 metric_a 判定）。

    probes: 可注入替身（测试用）；默认走真实链路。
    返回 {"field_results": {type: {"per_code": {...}, "index_ok": bool},
          "timings": {type: seconds}, "pool_size": N, "cache_warm_bars": K}}
    """
    probes = probes or {
        FIELD_BARS: probe_bars,
        FIELD_INDEX: lambda *_: probe_index(),
        FIELD_VAL: probe_valuation,
        FIELD_FIN: probe_fin_indicator,
    }
    codes: list[str] = list(pool.get("codes") or [])
    field_results: dict[str, Any] = {"per_code": {}, "index_ok": False}
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    bars_by_code: dict[str, list[dict]] = {}
    for code in codes:
        bars = probes[FIELD_BARS](code)
        bars_by_code[code] = bars
    timings[FIELD_BARS] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    index_bars = probes[FIELD_INDEX]()
    timings[FIELD_INDEX] = round(time.perf_counter() - t0, 3)
    field_results["index_ok"] = bool(index_bars)

    for ftype in (FIELD_VAL, FIELD_FIN):
        t0 = time.perf_counter()
        per_code: dict[str, Any] = {}
        for code in codes:
            per_code[code] = probes[ftype](code)
        timings[ftype] = round(time.perf_counter() - t0, 3)
        field_results["per_code"][ftype] = per_code

    field_results["bars_by_code"] = bars_by_code
    field_results["index_bars"] = index_bars
    return {
        "field_results": field_results,
        "timings": timings,
        "pool_size": len(codes),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ═══════════════════════════════════════════════════════════════
#  指标 A：字段可得率（纯计算，测试可注入）
# ═══════════════════════════════════════════════════════════════


def _required_value_key(catalog_item: dict[str, Any], ftype: str) -> str:
    """字段类型在具体因子上要求的值键（覆盖率与信号提取同源）。"""
    if ftype == FIELD_VAL:
        return "market_cap" if catalog_item["slug"] == "fund_size_log_cap" else "pb"
    if ftype == FIELD_FIN:
        return {"fund_roe": "roe", "fund_revenue_yoy": "revenue_yoy", "fund_gross_margin": "gross_margin"}.get(
            catalog_item["slug"], "roe"
        )
    return ""


def _field_coverage(catalog_item: dict[str, Any], field_results: dict[str, Any]) -> dict[str, Any]:
    """单因子的逐字段覆盖率：bars 按 min_bars 条数、其余按值有效性。"""
    codes = list(field_results.get("codes") or [])
    total = len(codes)
    detail: dict[str, Any] = {}
    for ftype in catalog_item.get("fields", []):
        if ftype == FIELD_BARS:
            bars_by_code = field_results.get("bars_by_code") or {}
            min_bars = int(catalog_item.get("min_bars") or 0)
            ok_codes = [c for c in codes if len(bars_by_code.get(c) or []) >= min_bars]
        elif ftype == FIELD_INDEX:
            ok_codes = codes if field_results.get("index_ok") else []
        else:
            per_code = (field_results.get("per_code") or {}).get(ftype) or {}
            key = _required_value_key(catalog_item, ftype)
            ok_codes = []
            for c in codes:
                value = per_code.get(c)
                if isinstance(value, dict):
                    ok_codes += [c] if _value_present(value.get(key)) else []
                else:
                    ok_codes += [c] if _value_present(value) else []
        coverage = (len(ok_codes) / total) if total else 0.0
        detail[ftype] = {
            "ok": coverage >= TYPE_COVERAGE,
            "coverage": round(coverage, 4),
            "ok_codes": len(ok_codes),
            "total": total,
        }
    return detail
