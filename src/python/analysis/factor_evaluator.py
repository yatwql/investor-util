"""因子目录计算编排（语义名 factor_evaluator）— 备数 → 逐因子横截面 → 摘要。

输入 = factor_catalog_loader.load_factor_inputs 的四类备数（测试可注入纯数据，
不发起网络）；输出 = 逐因子「最新横截面值 / 可算性 / 中性相对」+ 每日单条快照的
rating 摘要，供 signal_record 入账与风格与因子分析区「因子目录」区块渲染。

降级（逐因子降级不截断整表，全链 fail-soft）：
  - 横截面 = 池内各码「最新有效因子值」的均值，有效码数 < MIN_CODES_PER_DAY 当期不出值；
  - 单因子数据不足 → 该因子记不可算并给出原因（基准指数不可得 / 估值字段不可得 /
    财务指标不可得 / 日K不可得 / 有效码数不足）；
  - 目录拒载 / 池空 / 四类输入全不可用 → 返回 available=False 占位（不抛异常、不崩报告）。

口径与门槛判定书（冻结清单版本见 factor_catalog.CATALOG_VERSION）一致：
基本面族（估值/财务字段）按码级标量直取，技术族用日K（+基准指数）逐因子计算。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis._factor_formulas import compute_factor_values
from src.python.fetcher.factor_catalog_loader import (
    load_factor_catalog,
    load_factor_inputs,
    required_value_key,
)
from src.python.schemas.factor_catalog import (
    CATALOG,
    CATALOG_VERSION,
    FAMILY_LABELS,
    FIELD_BARS,
    FIELD_FIN,
    FIELD_INDEX,
    FIELD_VAL,
    MIN_CODES_PER_DAY,
    NEUTRAL_POINTS,
    value_present,
)

logger = logging.getLogger("invest")

__all__ = ["build_factor_catalog_data", "derive_factor_pool", "evaluate_factor_catalog"]


def derive_factor_pool(details: Any, penetrated_assets: Any) -> dict[str, Any]:
    """池构造（纯函数）：直接持仓 A 股（名称+代码双维）∪ 穿透 top10 A 股代码。

    Args:
        details: 行情明细（DetailRow 列表或含 name/code 的字典列表，两者皆可）。
        penetrated_assets: 穿透资产结构（code 标量 / codes 列表两种形状递归收集）。

    Returns:
        {"codes": 升序唯一池, "direct_stocks": 直接持仓, "penetration_stocks": 穿透}.
    """
    from src.python.core.code_utils import is_a_share_code, is_a_share_stock

    direct: set[str] = set()
    for row in details or []:
        if isinstance(row, dict):
            name, code = str(row.get("name") or ""), str(row.get("code") or "")
        else:
            name = str(getattr(row, "name", "") or "")
            code = str(getattr(row, "code", "") or "")
        if code and is_a_share_stock(name, code):
            direct.add(code)

    found: set[str] = set()

    def _walk(nodes: Any) -> None:
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
                _walk(value)
        elif isinstance(nodes, (list, tuple)):
            for item in nodes:
                _walk(item)

    _walk(penetrated_assets)
    return {
        "codes": sorted(set(direct) | found),
        "direct_stocks": sorted(direct),
        "penetration_stocks": sorted(found),
    }


def _placeholder(reason: str, version: str, catalog_size: int) -> dict[str, Any]:
    """占位契约（available=False，factors 为空 → 区块/信号全链无感）。"""
    return {
        "available": False,
        "reason": reason,
        "version": version,
        "catalog_size": catalog_size,
        "computed": 0,
        "neutral_above": 0,
        "neutral_total": 0,
        "rating": "",
        "pool_size": 0,
        "factors": [],
        "unavailable": {},
    }


def _apply_scalar(
    row: dict[str, Any],
    item: dict[str, Any],
    source: dict[str, Any],
    field_kind: str,
    codes_all: list[str],
) -> None:
    """基本面族：按码级标量（估值/财务字段）取值并算横截面均值。"""
    key = required_value_key(item, field_kind)
    values: list[float] = []
    for code in codes_all:
        value = (source.get(code) or {}).get(key)
        if value_present(value):
            values.append(float(value))
    row["codes_ok"] = len(values)
    if len(values) >= MIN_CODES_PER_DAY:
        row["value"] = sum(values) / len(values)
        row["computable"] = True
    elif values:
        row["reason"] = f"有效码数不足({len(values)}<{MIN_CODES_PER_DAY})"
    else:
        row["reason"] = "估值字段不可得" if field_kind == FIELD_VAL else "财务指标不可得"


def _apply_bars(
    row: dict[str, Any],
    item: dict[str, Any],
    bars_by_code: dict[str, Any],
    index_bars: list[Any],
) -> None:
    """技术族：逐码用日K（+基准指数）算因子序列，取最新有效值的横截面均值。"""
    slug = str(item["slug"])
    min_bars = int(item.get("min_bars") or 0)
    values: list[float] = []
    for code, bars in bars_by_code.items():
        if not bars or len(bars) < min_bars:
            continue
        series = compute_factor_values(slug, bars, index_bars)
        latest = next((v for v in reversed(series) if value_present(v)), None)
        if latest is not None:
            values.append(float(latest))
    row["codes_ok"] = len(values)
    if len(values) >= MIN_CODES_PER_DAY:
        row["value"] = sum(values) / len(values)
        row["computable"] = True
    elif values:
        row["reason"] = f"有效码数不足({len(values)}<{MIN_CODES_PER_DAY})"
    else:
        row["reason"] = "日K不可得"


def evaluate_factor_catalog(
    inputs: dict[str, Any],
    *,
    entries: list[dict[str, Any]] | None = None,
    version: str = CATALOG_VERSION,
) -> dict[str, Any]:
    """逐因子横截面评估（纯函数，inputs 可注入；不发起网络）。

    Args:
        inputs: load_factor_inputs 形状的四类备数（bars_by_code/index_bars/
            valuation_by_code/fin_by_code/unavailable），空/非 dict → 占位。
        entries: 目录条目列表（缺省用冻结 CATALOG；测试可注入子集）。
        version: 目录版本号（透传进契约，便于报告自述与对账）。

    Returns:
        因子目录契约（available/computed/rating/factors 等，见模块 docstring）。
    """
    factor_entries = list(CATALOG if entries is None else entries)
    if not isinstance(inputs, dict) or not inputs:
        return _placeholder("输入为空", version, len(factor_entries))

    unavailable = dict(inputs.get("unavailable") or {})
    bars_by_code = inputs.get("bars_by_code") or {}
    index_bars = inputs.get("index_bars") or []
    valuation = inputs.get("valuation_by_code") or {}
    fin = inputs.get("fin_by_code") or {}
    codes_all = sorted(set(bars_by_code) | set(valuation) | set(fin))

    factors: list[dict[str, Any]] = []
    computed = 0
    neutral_above = 0
    neutral_total = 0

    for item in factor_entries:
        slug = str(item.get("slug") or "")
        fields = set(item.get("fields") or [])
        neutral = NEUTRAL_POINTS.get(slug)
        row: dict[str, Any] = {
            "slug": slug,
            "family": item.get("family", ""),
            "family_label": FAMILY_LABELS.get(str(item.get("family", "")), str(item.get("family", ""))),
            "label": item.get("label", slug),
            "value": None,
            "neutral": neutral,
            "above": None,
            "codes_ok": 0,
            "computable": False,
            "reason": None,
        }

        if FIELD_INDEX in fields and not index_bars:
            row["reason"] = "基准指数不可得"
        elif FIELD_VAL in fields and FIELD_BARS not in fields:
            _apply_scalar(row, item, valuation, FIELD_VAL, codes_all)
        elif FIELD_FIN in fields and FIELD_BARS not in fields:
            _apply_scalar(row, item, fin, FIELD_FIN, codes_all)
        elif FIELD_BARS in fields:
            _apply_bars(row, item, bars_by_code, index_bars)
        else:
            row["reason"] = "字段需求未知"

        if row["computable"] and row["value"] is not None:
            computed += 1
            if neutral is not None:
                neutral_total += 1
                row["above"] = bool(row["value"] >= neutral)
                if row["above"]:
                    neutral_above += 1
        factors.append(row)

    if neutral_total:
        rating = f"{neutral_above}/{neutral_total} 中性上方"
    elif computed:
        rating = f"{computed}/{len(factor_entries)} 可算"
    else:
        rating = ""

    return {
        "available": computed > 0,
        "reason": None if computed > 0 else "池内无可算因子",
        "version": version,
        "catalog_size": len(factor_entries),
        "computed": computed,
        "neutral_above": neutral_above,
        "neutral_total": neutral_total,
        "rating": rating,
        "pool_size": len(codes_all),
        "factors": factors,
        "unavailable": unavailable,
    }


def build_factor_catalog_data(codes: list[str]) -> dict[str, Any]:
    """编排入口：目录装载 → 四类备数（带探针短路）→ 横截面评估。

    Args:
        codes: 股票池代码（derive_factor_pool 产物；空池 → 占位不备数）。

    Returns:
        因子目录契约；任何环节异常/拒载均降级为 available=False 占位。
    """
    catalog = load_factor_catalog()
    if not catalog:
        return _placeholder("目录校验失败", CATALOG_VERSION, len(CATALOG))
    entries, version = catalog["entries"], str(catalog["version"])
    if not codes:
        return _placeholder("股票池为空", version, len(entries))
    try:
        inputs = load_factor_inputs(codes)
    except Exception as exc:  # fail-soft：备数异常不崩报告
        logger.error("[factor_catalog] 因子目录备数异常，降级为不可用占位: %s", exc)
        return _placeholder(f"备数异常: {type(exc).__name__}", version, len(entries))
    return evaluate_factor_catalog(inputs, entries=entries, version=version)
