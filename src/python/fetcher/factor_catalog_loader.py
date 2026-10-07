"""因子目录装载（语义名 factor_catalog_loader）— 校验、备数与版本溯源。

装载 = 两件事：
  1. **目录本体**（load_factor_catalog）：validate_catalog 完整性校验（25 条 /
     五族各 5 / slug 唯一 / 字段与族名合法）+ CATALOG_VERSION 溯源——问题清单
     非空即拒载并记 ERROR 日志，调用方拿 None 走降级（不进计算、不崩报告）；
     目录随代码版本化，进程内校验一次后缓存。
  2. **计算输入**（load_factor_inputs）：为股票池经既有链路备数——日 K / 基准
     指数 / 估值字段 / 财务指标，复用缓存、熔断与降级；逐类型失败只记原因
     落入 ``unavailable``，不外抛（禁裸调 provider，一律走 chain / 网关函数）。
分层：fetcher 层；只依赖标准库与契约层（动态 import 取数网关）。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from src.python.schemas.factor_catalog import (
    BENCHMARK_INDEX,
    CATALOG,
    CATALOG_VERSION,
    FAMILIES,
    FIELD_BARS,
    FIELD_FIN,
    FIELD_INDEX,
    FIELD_TYPES,
    FIELD_VAL,
    value_present,
)

logger = logging.getLogger("invest")

__all__ = [
    "LOOKBACK_DAYS",
    "load_factor_catalog",
    "load_factor_inputs",
    "required_value_key",
    "validate_catalog",
]

LOOKBACK_DAYS = 365  # 回看窗口（自然日，K 线链路按此折算交易日）

_CATALOG_CACHE: dict[str, Any] | None = None


def load_factor_catalog() -> dict[str, Any] | None:
    """装载并校验目录；拒载返回 None（调用方降级，不进计算）。

    目录随代码版本化——进程内只校验一次，返回 {"version", "entries"}；
    信号 detail 携带 version，保证账本记录可溯源到目录版本。
    """
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE
    problems = validate_catalog(CATALOG)
    if problems:
        logger.error("[factor_catalog] 目录校验失败，拒绝装载：%s", "；".join(problems))
        return None
    _CATALOG_CACHE = {"version": CATALOG_VERSION, "entries": [dict(item) for item in CATALOG]}
    return _CATALOG_CACHE


def validate_catalog(catalog: list[dict[str, Any]]) -> list[str]:
    """目录完整性校验：25 条、五族各 5、slug 唯一、字段类型合法、族名合法。"""
    problems: list[str] = []
    if len(catalog) != 25:
        problems.append(f"目录条数 {len(catalog)} != 25")
    slugs = [item.get("slug") for item in catalog]
    if len(set(slugs)) != len(slugs):
        problems.append("slug 存在重复")
    for family in FAMILIES:
        n = sum(1 for item in catalog if item.get("family") == family)
        if n != 5:
            problems.append(f"族 {family} 条数 {n} != 5")
    for item in catalog:
        fields = item.get("fields") or []
        if not fields:
            problems.append(f"{item.get('slug')}: fields 为空")
        for field in fields:
            if field not in FIELD_TYPES:
                problems.append(f"{item.get('slug')}: 未知字段类型 {field}")
        if not item.get("label") or not item.get("formula"):
            problems.append(f"{item.get('slug')}: 缺 label/formula")
    return problems


# ── 输入备数（逐类型经既有链路，失败只记原因不外抛） ──


def probe_bars(code: str) -> list[dict]:
    """日 K 线（history_stock 链，增量合并缓存）。"""
    from src.python.fetcher.chain_incremental import fetch_with_incremental_fallback

    try:
        return fetch_with_incremental_fallback("history_stock", code, LOOKBACK_DAYS) or []
    except Exception:
        logger.warning("[factor_catalog] {code} 日K失败: {type(exc).__name__}: {exc}")
        return []


def probe_index() -> list[dict]:
    """基准指数历史（history_index 链）。"""
    from src.python.fetcher.index import fetch_index_history

    try:
        return fetch_index_history(BENCHMARK_INDEX, LOOKBACK_DAYS) or []
    except Exception:
        logger.warning("[factor_catalog] 指数历史失败: {type(exc).__name__}: {exc}")
        return []


def probe_valuation(code: str) -> dict | None:
    """当前 PE/PB/市值（push2 扩展字段，经行业数据入口）。"""
    from src.python.fetcher.industry import fetch_valuation_fields

    try:
        return fetch_valuation_fields(code)
    except Exception:
        logger.warning("[factor_catalog] {code} 估值失败: {type(exc).__name__}: {exc}")
        return None


def probe_fin_indicator(code: str) -> dict | None:
    """最新报告期财务指标（financial_indicator 链）。"""
    from src.python.fetcher.financial_indicator import fetch_latest_indicator

    try:
        return fetch_latest_indicator(code)
    except Exception:
        logger.warning("[factor_catalog] {code} 财务指标失败: {type(exc).__name__}: {exc}")
        return None


def required_value_key(catalog_item: dict[str, Any], ftype: str) -> str:
    """字段类型在具体因子上要求的值键（基本面/估值因子的可得性判定同源）。"""
    if ftype == FIELD_VAL:
        return "market_cap" if catalog_item["slug"] == "fund_size_log_cap" else "pb"
    if ftype == FIELD_FIN:
        return {"fund_roe": "roe", "fund_revenue_yoy": "revenue_yoy", "fund_gross_margin": "gross_margin"}.get(
            catalog_item["slug"], "roe"
        )
    return ftype


def load_factor_inputs(
    codes: list[str],
    probes: dict[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    """为股票池备数四类输入；逐类型失败入 ``unavailable``（带原因），不外抛。

    Args:
        codes: 池内 A 股代码列表（调用方负责穿透/直接持仓的池构造）。
        probes: 可注入取数实现（测试用）；缺省走本模块 probe_* 既有链路版本。

    Returns:
        {"bars_by_code", "index_bars", "valuation_by_code", "fin_by_code",
         "unavailable": {类型: {code或"index": 原因}}}
    """
    impl = {
        "bars": probe_bars,
        "index": probe_index,
        "valuation": probe_valuation,
        "fin": probe_fin_indicator,
        **(probes or {}),
    }
    inputs: dict[str, Any] = {
        "bars_by_code": {},
        "index_bars": [],
        "valuation_by_code": {},
        "fin_by_code": {},
        "unavailable": {},
    }

    try:
        index_bars = impl["index"]()
    except Exception as exc:  # noqa: BLE001 —— 备数阶段逐类型容错（不外抛）
        index_bars = []
        logger.warning("[factor_catalog] 指数历史取数异常: %s", exc)
    if index_bars:
        inputs["index_bars"] = index_bars
    else:
        inputs["unavailable"][FIELD_INDEX] = {"index": "基准指数不可得"}

    for code in codes:
        try:
            bars = impl["bars"](code)
        except Exception as exc:  # noqa: BLE001 —— 备数阶段逐码容错
            bars = []
            logger.warning("[factor_catalog] %s 日K取数异常: %s", code, exc)
        if bars:
            inputs["bars_by_code"][code] = bars
        else:
            inputs["unavailable"].setdefault(FIELD_BARS, {})[code] = "日K不可得"

        try:
            val = impl["valuation"](code)
        except Exception as exc:  # noqa: BLE001
            val = None
            logger.warning("[factor_catalog] %s 估值取数异常: %s", code, exc)
        if isinstance(val, dict) and any(value_present(v) for v in val.values()):
            inputs["valuation_by_code"][code] = val
        else:
            inputs["unavailable"].setdefault(FIELD_VAL, {})[code] = "估值字段不可得"

        try:
            fin = impl["fin"](code)
        except Exception as exc:  # noqa: BLE001
            fin = None
            logger.warning("[factor_catalog] %s 财务指标取数异常: %s", code, exc)
        if isinstance(fin, dict) and any(value_present(v) for v in fin.values()):
            inputs["fin_by_code"][code] = fin
        else:
            inputs["unavailable"].setdefault(FIELD_FIN, {})[code] = "财务指标不可得"
    return inputs
