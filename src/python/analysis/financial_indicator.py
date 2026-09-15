"""财务指标派生 —— 标准指标记录 → 质量分档 / 趋势 / 当前估值。

**纯计算层**：不取数、不落盘。输入为 ``financial_indicator`` 域标准字段记录
（``analysis/financial_indicator_extract.py`` 的解析结果或 akshare 主源记录），
输出为可直接进报告契约的派生值。

## 口径与免责

- **质量分档为启发式**：按四个维度的行业通用阈值（ROE / 毛利率 / 资产负债率 /
  经营现金流对净利的覆盖）各映射 0~3 分后取均值分档（优 / 良 / 中 / 弱）。
  阈值是**通用经验值**，不区分行业（银行/地产的负债率天然偏高），故仅作横向扫视
  线索，非投资建议、非评级。
- **趋势**只比较**相邻两个年度**（年报口径）的营业收入与归母净利润，避免把季报
  累计值当年度值比较；期数不足则不给趋势（不猜）。
- **当前 PE/PB** 用现价 ÷ 该报告期每股收益/每股净资产：亏损（EPS ≤ 0）或净资产
  非正时 PE/PB 无意义，取 ``None`` 并在展示层标注。**不是历史分位**，历史分位
  属后续阶段（TTM 口径）。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger("invest")

#: 质量维度 → (标准字段, 阈值[优/良/中], 越高越好?)
_QUALITY_RULES: tuple[tuple[str, tuple[float, float, float], bool], ...] = (
    ("roe", (0.15, 0.08, 0.03), True),
    ("gross_margin", (0.40, 0.25, 0.10), True),
    ("debt_ratio", (0.40, 0.60, 0.80), False),
)

#: 均值分 → 档位（高位优先判定）
_GRADE_THRESHOLDS: tuple[tuple[float, str], ...] = ((2.5, "优"), (1.75, "良"), (1.0, "中"))

#: 现金流质量（经营现金流 / 归母净利）阈值
_CASH_QUALITY_THRESHOLDS: tuple[float, float, float] = (1.0, 0.7, 0.3)

#: 年度趋势判定阈值（±3% 内视为持平）
_TREND_EPS = 0.03

_STATEMENT_DATE_SUFFIX = "-12-31"


def _num(value: Any) -> float | None:
    """取有限数值；NaN/±inf/缺失一律 None。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _points(value: float, thresholds: tuple[float, float, float], higher_is_better: bool) -> int:
    """按阈值映射 0~3 分。"""
    if not higher_is_better:
        if value <= thresholds[0]:
            return 3
        if value <= thresholds[1]:
            return 2
        if value <= thresholds[2]:
            return 1
        return 0
    if value >= thresholds[0]:
        return 3
    if value >= thresholds[1]:
        return 2
    if value >= thresholds[2]:
        return 1
    return 0


def quality_grade(record: Mapping[str, Any] | None) -> tuple[str, float | None]:
    """质量分档：返回 ``(档位, 均值分)``；可用维度为空时 ``("", None)``。

    分档维度逐项独立：某维度缺失即不参与（不按 0 分计），避免缺数据被误判为差。
    """
    if not record:
        return "", None
    scores: list[int] = []
    for field, thresholds, higher_is_better in _QUALITY_RULES:
        value = _num(record.get(field))
        if value is None:
            continue
        scores.append(_points(value, thresholds, higher_is_better))

    cash, profit = _num(record.get("operating_cash_flow")), _num(record.get("net_profit"))
    if cash is not None and profit is not None and profit > 0:
        scores.append(_points(cash / profit, _CASH_QUALITY_THRESHOLDS, True))

    if not scores:
        return "", None
    average = round(sum(scores) / len(scores), 2)
    for threshold, grade in _GRADE_THRESHOLDS:
        if average >= threshold:
            return grade, average
    return "弱", average


def annual_records(series: Iterable[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    """取年报口径记录（报告期为 12-31），按报告期降序。"""
    annual = [r for r in (series or []) if str(r.get("report_period") or "").endswith(_STATEMENT_DATE_SUFFIX)]
    return sorted(annual, key=lambda r: str(r.get("report_period") or ""), reverse=True)


def _growth_label(new: float | None, old: float | None) -> str:
    if new is None or old is None or abs(old) < 1e-9:
        return ""
    change = (new - old) / abs(old)
    if change >= _TREND_EPS:
        return "增长"
    if change <= -_TREND_EPS:
        return "下滑"
    return "持平"


def trend_label(series: Iterable[Mapping[str, Any]] | None) -> str:
    """年度趋势标签（营收与净利同为增长 = 增长；同为下滑 = 下滑；否则波动）。

    仅比较相邻两个**年报**；年报不足两期返回空串（不给结论）。
    """
    annual = annual_records(series)
    if len(annual) < 2:
        return ""
    newest, previous = annual[0], annual[1]
    labels = [_growth_label(_num(newest.get(field)), _num(previous.get(field))) for field in ("revenue", "net_profit")]
    labels = [label for label in labels if label]
    if not labels:
        return ""
    if all(label == "增长" for label in labels):
        return "增长"
    if all(label == "下滑" for label in labels):
        return "下滑"
    if all(label == "持平" for label in labels):
        return "持平"
    return "波动"


def current_valuation(record: Mapping[str, Any] | None, price: float | None) -> tuple[float | None, float | None]:
    """当前 PE / PB（现价 ÷ 每股收益 / 每股净资产）；无意义时返回 ``(None, None)``。

    亏损（EPS ≤ 0）或净资产非正（BVPS ≤ 0）时对应倍数无意义 → ``None``。
    """
    price_num = _num(price)
    if record is None or price_num is None or price_num <= 0:
        return None, None
    eps, bvps = _num(record.get("eps")), _num(record.get("bvps"))
    pe = round(price_num / eps, 2) if eps is not None and eps > 0 else None
    pb = round(price_num / bvps, 2) if bvps is not None and bvps > 0 else None
    return pe, pb


def trend_points(series: Iterable[Mapping[str, Any]] | None, limit: int = 4) -> list[dict[str, Any]]:
    """取最近 ``limit`` 期（不限年报）的营收/净利序列，供展示趋势。"""
    points: list[dict[str, Any]] = []
    for record in list(series or [])[: max(1, int(limit))]:
        points.append(
            {
                "report_period": str(record.get("report_period") or ""),
                "doc_type": str(record.get("doc_type") or ""),
                "revenue": _num(record.get("revenue")),
                "net_profit": _num(record.get("net_profit")),
                "roe": _num(record.get("roe")),
            }
        )
    return points
