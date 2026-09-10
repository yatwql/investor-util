"""确定性数值信号沉淀 — report 层抽取适配器。

从报告管线已算好的 ``pipeline_data`` 中抽取五类**确定性算法评级**，打上实时/
非实时来源标签后写入 ``core.signal_ledger``：

    市场温度  ← market_temperature_data（指数级）
    估值分位  ← valuation_data.by_code（持仓级，逐 code）
    尾部风险  ← tail_risk_data（组合级）
    风格因子  ← style_factor_data（组合级）
    再平衡超限 ← action_data.rebalance_signals（持仓级，逐 code）

设计要点：
  - **层级**：本模块属 report 层（消费 report seam 传入的 pipeline_data），
    单向依赖 ``core.signal_ledger`` 与 ``analysis`` 的**常量/枚举**（分层树
    report → analysis 合法）。评级 → 方向的映射落在本层，从而 core 层无需
    持有 analysis 的评级词汇表（见 signal_ledger 模块 docstring）。
  - **来源标签**：live/demo 判定收敛于 ``signal_ledger.resolve_data_source()``，
    本适配器只负责**供给判定事实**——逐 code 新鲜度（data_freshness.items）
    与数据源降级（data_degradation）。持仓级信号必须传该 code 的 freshness；
    组合级/指数级信号无逐品种条目，传 None（乐观缺省，理由见该函数 docstring）。
  - **不可用信号不入账**：``available=False`` 的占位无评级、非真实观测，
    入账只会污染统计；可用性叙事已由既有降级披露承担（v1 边界）。
  - 开关关闭时全链路无感（不读不写，直接返回空结果）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.analysis.style_factor_regression import FACTOR_NAMES
from src.python.analysis.valuation_percentile import (
    TIER_FAIR,
    TIER_OVERVALUED,
    TIER_UNDERVALUED,
)
from src.python.core import signal_ledger as sl
from src.python.core.decision_ledger import DIRECTION_FLAT, DIRECTION_LONG, DIRECTION_SHORT

logger = logging.getLogger("invest")

# ── 评级 → 方向（承接 decision_ledger 方向语义：+1 看多 / -1 看空 / 0 中性）──
# 低估 → 增配倾向；高估 → 减配倾向；超限 → 建议减仓（与再平衡建议同向）。
# 尾部风险与风格因子无方向语义 → FLAT（只在 value/detail 留数值事实）。
_RATING_DIRECTIONS: dict[str, int] = {
    TIER_UNDERVALUED: DIRECTION_LONG,
    TIER_FAIR: DIRECTION_FLAT,
    TIER_OVERVALUED: DIRECTION_SHORT,
    "超限": DIRECTION_SHORT,
}

# ── 尾部风险三档评级（适配器层展示词汇，供统计分组）──
# 判据是 VaR95（历史模拟，负值=单日潜在跌幅）。原始数值同时完整存于
# value/detail，回测可取精确值，不受三档粗分影响。
RATING_TAIL_ELEVATED = "尾部偏厚"
RATING_TAIL_MODERATE = "尾部中等"
RATING_TAIL_NORMAL = "尾部正常"
TAIL_RISK_ELEVATED_VAR = -3.0
TAIL_RISK_MODERATE_VAR = -2.0

# ── 样例下限：低于该样本量的信号不入账 ──
MIN_TAIL_RISK_SAMPLE = 20

# ── 组合级/指数级信号的数据源降级前缀（source_key 前缀匹配）──
# 市场温度/风格因子依赖指数历史（fetcher/index.py: index_history_{chain}_{code}）；
# 尾部风险依赖组合日收益（由逐品种 price_/fund_ 历史合成）。
_DEGRADED_PREFIX_BY_TYPE: dict[str, tuple[str, ...]] = {
    sl.SIGNAL_MARKET_TEMPERATURE: ("index_history_",),
    sl.SIGNAL_STYLE_FACTOR: ("index_history_",),
    sl.SIGNAL_TAIL_RISK: ("price_", "fund_"),
}


class _QualityContext:
    """从 pipeline_data 抽出的数据质量事实（供来源标签判定）。"""

    def __init__(self, pipeline_data: dict[str, Any]) -> None:
        self._freshness_by_code: dict[str, str] = {}
        freshness = pipeline_data.get("data_freshness")
        if isinstance(freshness, dict):
            for item in freshness.get("items") or []:
                if not isinstance(item, dict):
                    continue
                code = item.get("code")
                value = item.get("freshness")
                if code and value:
                    self._freshness_by_code[str(code)] = str(value)

        self._degraded_keys: list[str] = []
        for event in pipeline_data.get("data_degradation") or []:
            if isinstance(event, dict) and event.get("degraded") and event.get("source_key"):
                self._degraded_keys.append(str(event["source_key"]))

    def freshness_of(self, code: str) -> str | None:
        """该 code 的逐品种新鲜度；无条目返回 None（组合级/指数级乐观缺省用）。"""
        return self._freshness_by_code.get(code)

    def degraded_for(self, signal_type: str, code: str = "") -> bool:
        """该信号类型依赖的数据源本次是否降级。

        组合级/指数级按 source_key 前缀匹配；持仓级按 ``_{code}`` 后缀匹配
        （逐品种数据源 key 形如 ``price_{type}_{code}`` / ``fund_hold_{code}``）。
        """
        prefixes = _DEGRADED_PREFIX_BY_TYPE.get(signal_type)
        if prefixes:
            return any(key.startswith(prefixes) for key in self._degraded_keys)
        if not code:
            return False
        return any(key.endswith(f"_{code}") for key in self._degraded_keys)


def _direction_of(rating: str) -> int:
    return _RATING_DIRECTIONS.get(rating, DIRECTION_FLAT)


def _source_for(signal_type: str, ctx: _QualityContext, code: str = "") -> tuple[str, str]:
    """按信号层级供给判定事实（持仓级传 freshness，组合级/指数级传 None）。"""
    freshness = ctx.freshness_of(code) if code else None
    return sl.resolve_data_source(
        freshness=freshness,
        degraded=ctx.degraded_for(signal_type, code),
    )


def _tail_risk_rating(var95: float) -> str:
    if var95 <= TAIL_RISK_ELEVATED_VAR:
        return RATING_TAIL_ELEVATED
    if var95 <= TAIL_RISK_MODERATE_VAR:
        return RATING_TAIL_MODERATE
    return RATING_TAIL_NORMAL


# ── 逐信号类型抽取 ──────────────────────────────────────


def _temperature_signals(pipeline_data: dict[str, Any], report_date: str, ctx: _QualityContext) -> list[dict[str, Any]]:
    data = pipeline_data.get("market_temperature_data")
    if not isinstance(data, dict) or not data.get("available"):
        return []
    tier = data.get("tier")
    if not tier:
        return []
    signal_type = sl.SIGNAL_MARKET_TEMPERATURE
    data_source, reason = _source_for(signal_type, ctx)
    return [
        sl.build_signal(
            signal_type=signal_type,
            report_date=report_date,
            rating=str(tier),
            value=data.get("score"),
            subject=str(data.get("index_code") or ""),
            name=str(data.get("index_name") or ""),
            direction=_direction_of(str(tier)),
            data_source=data_source,
            source_reason=reason,
            detail={
                "score": data.get("score"),
                "price_percentile": data.get("price_percentile"),
                "ma_deviation": data.get("ma_deviation"),
                "volatility": data.get("volatility"),
                "sample_count": data.get("sample_count"),
            },
        )
    ]


def _valuation_signals(pipeline_data: dict[str, Any], report_date: str, ctx: _QualityContext) -> list[dict[str, Any]]:
    data = pipeline_data.get("valuation_data")
    if not isinstance(data, dict) or not data.get("available"):
        return []
    by_code = data.get("by_code")
    if not isinstance(by_code, dict):
        return []
    signals: list[dict[str, Any]] = []
    for code, item in by_code.items():
        if not isinstance(item, dict) or not item.get("percentile_available"):
            continue
        tier = item.get("tier")
        if not tier:
            continue
        signal_type = sl.SIGNAL_VALUATION
        data_source, reason = _source_for(signal_type, ctx, str(code))
        signals.append(
            sl.build_signal(
                signal_type=signal_type,
                report_date=report_date,
                rating=str(tier),
                value=item.get("price_percentile"),
                subject=str(code),
                direction=_direction_of(str(tier)),
                data_source=data_source,
                source_reason=reason,
                detail={
                    "pe": item.get("pe"),
                    "pb": item.get("pb"),
                    "sample_count": item.get("sample_count"),
                },
            )
        )
    return signals


def _tail_risk_signals(pipeline_data: dict[str, Any], report_date: str, ctx: _QualityContext) -> list[dict[str, Any]]:
    data = pipeline_data.get("tail_risk_data")
    if not isinstance(data, dict) or not data.get("available"):
        return []
    var95 = data.get("var95")
    if not isinstance(var95, (int, float)) or isinstance(var95, bool):
        return []
    sample = data.get("sample_size") or 0
    if sample < MIN_TAIL_RISK_SAMPLE:
        return []
    signal_type = sl.SIGNAL_TAIL_RISK
    data_source, reason = _source_for(signal_type, ctx)
    return [
        sl.build_signal(
            signal_type=signal_type,
            report_date=report_date,
            rating=_tail_risk_rating(float(var95)),
            value=var95,
            subject="portfolio",
            direction=DIRECTION_FLAT,
            data_source=data_source,
            source_reason=reason,
            detail={
                "var99": data.get("var99"),
                "sample_size": sample,
                "max_single_day_drop": data.get("max_single_day_drop"),
                "consecutive_down_days": data.get("consecutive_down_days"),
            },
        )
    ]


def _style_factor_signals(
    pipeline_data: dict[str, Any], report_date: str, ctx: _QualityContext
) -> list[dict[str, Any]]:
    data = pipeline_data.get("style_factor_data")
    if not isinstance(data, dict) or not data.get("available"):
        return []
    allocation = data.get("style_allocation")
    if not isinstance(allocation, dict) or not allocation:
        return []
    dominant = max(allocation, key=lambda k: allocation.get(k) or 0.0)
    signal_type = sl.SIGNAL_STYLE_FACTOR
    data_source, reason = _source_for(signal_type, ctx)
    return [
        sl.build_signal(
            signal_type=signal_type,
            report_date=report_date,
            rating=FACTOR_NAMES.get(str(dominant), str(dominant)),
            value=allocation.get(dominant),
            subject="portfolio",
            direction=DIRECTION_FLAT,
            data_source=data_source,
            source_reason=reason,
            detail={
                "alpha": data.get("alpha"),
                "window": data.get("window"),
                "sample_count": data.get("sample_count"),
                "style_allocation": allocation,
                "significant": data.get("significant"),
            },
        )
    ]


def _overflow_signals(pipeline_data: dict[str, Any], report_date: str, ctx: _QualityContext) -> list[dict[str, Any]]:
    action_data = pipeline_data.get("action_data")
    if not isinstance(action_data, dict):
        return []
    rows = action_data.get("rebalance_signals")
    if not isinstance(rows, list):
        return []
    signals: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("summary"):
            continue  # 聚合提示行（>3 条时的 summary 形态）无 code，不入账
        code = row.get("code")
        if not code:
            continue
        signal_type = sl.SIGNAL_REBALANCE_OVERFLOW
        data_source, reason = _source_for(signal_type, ctx, str(code))
        signals.append(
            sl.build_signal(
                signal_type=signal_type,
                report_date=report_date,
                rating="超限",
                value=row.get("weight"),
                subject=str(code),
                name=str(row.get("name") or ""),
                direction=DIRECTION_SHORT,
                data_source=data_source,
                source_reason=reason,
                detail={
                    "weight": row.get("weight"),
                    "threshold": row.get("threshold"),
                    "action": row.get("action"),
                },
            )
        )
    return signals


# ── 入口 ────────────────────────────────────────────────


def register_deterministic_signals(
    pipeline_data: dict[str, Any] | None,
    *,
    report_date: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """抽取本轮确定性信号并登记入账（幂等）。

    Args:
        pipeline_data: A 通道数据契约字典（含五类信号的产出键）
        report_date: 报告日期（YYYY-MM-DD），参与幂等键；None → 取当天
        path: 账本路径（测试隔离用）

    Returns:
        ``{"registered": 新增条数, "skipped": 幂等跳过条数, "by_type": {类型: 新增数}}``
    """
    if not isinstance(pipeline_data, dict) or not sl.is_active():
        return {"registered": 0, "skipped": 0, "by_type": {}}

    date_str = report_date or datetime.now().strftime("%Y-%m-%d")
    ctx = _QualityContext(pipeline_data)
    records: list[dict[str, Any]] = []
    for extractor in (
        _temperature_signals,
        _valuation_signals,
        _tail_risk_signals,
        _style_factor_signals,
        _overflow_signals,
    ):
        records.extend(extractor(pipeline_data, date_str, ctx))

    if not records:
        logger.info("[signal_ledger] 本轮无可登记的确定性信号")
        return {"registered": 0, "skipped": 0, "by_type": {}}

    appended = sl.append_signals(records, path=path)
    by_type: dict[str, int] = {}
    for record in appended:
        key = record["signal_type"]
        by_type[key] = by_type.get(key, 0) + 1
    return {
        "registered": len(appended),
        "skipped": len(records) - len(appended),
        "by_type": by_type,
    }
