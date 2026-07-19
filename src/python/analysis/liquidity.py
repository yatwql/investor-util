"""流动性风险评估模块 — 场内品种变现天数计算。

使用方式::

    from src.python.analysis.liquidity import check_liquidity

    signals = check_liquidity(holdings_details, total_mv)

场内品种（股票/ETF）基于近 20 日 K 线成交量和收盘价估算日成交额，
计算全额变现所需天数。场外品种标记为 OTC 类型（由 P3-12 处理）。

降级方案：成交额数据失败时默认假设流动性充足，不告警。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("invest")

__all__ = ["check_liquidity"]

# 日均成交额计算窗口（交易日）
_LOOKBACK_DAYS = 20

# 当日可卖出阈值（变现天数 < 此值视为当日可卖出）
_SAME_DAY_THRESHOLD = 1.0


def _is_exchange_traded(code: str, name: str) -> bool:
    """判断品种是否为场内可交易（股票/ETF/场内基金）。

    优先排除场外基金：先检查 OTC 特征（含名称关键词 + 代码重叠区），
    确认非 OTC 后才判定为场内可交易。
    """
    from src.python.code_utils import is_a_share_code, is_exchange_fund_code, is_hk_stock_code

    # 场外基金（含债券基金/货基）已由 _is_otc_fund 排除，
    # 此处只做正向匹配
    return is_a_share_code(code) or is_exchange_fund_code(code)


def _is_otc_fund(name: str, code: str) -> bool:
    """判断品种是否为场外基金。

    检查顺序：债券基金/货基 → 基金名称匹配 → 代码重叠区。
    """
    from src.python.code_utils import (
        is_bond_fund_by_name,
        is_money_fund_by_name,
        is_otc_fund_by_name,
    )

    if is_bond_fund_by_name(name) or is_money_fund_by_name(name):
        return True
    # OTC 基金：检查代码重叠区+名称关键词
    if is_otc_fund_by_name(name, code):
        return True
    return False


def _compute_avg_daily_turnover(code: str) -> float | None:
    """获取近 20 日 K 线，估算日均成交额（CNY）。

    使用 K 线 volume（股）× close（收盘价）近似估算日成交额。
    数据获取失败时返回 None。

    Args:
        code: 证券代码。

    Returns:
        日均成交额（CNY），获取失败返回 None。
    """
    from src.python.fetcher.chain import fetch_with_incremental_fallback

    bars = fetch_with_incremental_fallback("history_stock", code, days=_LOOKBACK_DAYS)
    if not bars:
        return None

    # 提取收盘价和成交量，计算每日成交额 ≈ volume × close
    daily_turnovers: list[float] = []
    for bar in bars:
        close = bar.get("close")
        volume = bar.get("volume")
        if close is not None and volume is not None and close > 0 and volume > 0:
            daily_turnovers.append(volume * close)

    if not daily_turnovers:
        return None

    return sum(daily_turnovers) / len(daily_turnovers)


def check_liquidity(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
) -> list[dict[str, Any]]:
    """检查持仓流动性风险。

    对每个场内品种，基于近 20 日日均成交额计算全额变现天数。
    场外品种标记 type="otc"，不计算变现天数。
    数据获取失败的场内品种默认假设流动性充足（标记 type="assumed_liquid"）。

    Args:
        holdings_details: 持仓明细列表，每项含 code/name/market_value。
        total_mv: 组合总市值（用于权重计算，当前暂未使用）。

    Returns:
        流动性分析结果列表，每项含：
        - code: 证券代码
        - name: 证券名称
        - market_value: 持仓市值
        - type: "stock"（场内可计算）/ "otc"（场外）/ "assumed_liquid"（数据缺失，默认充足）
        - avg_daily_turnover: 日均成交额（CNY，仅 type="stock"）
        - liquidation_days: 全额变现天数（仅 type="stock"）
        - tag: "当日可卖出" / "需约 N 日卖出" / "场外基金" / "流动性充足（数据缺失）"
    """
    if not holdings_details:
        return []

    results: list[dict[str, Any]] = []
    for h in holdings_details:
        code = h.get("code", "")
        name = h.get("name", "")
        mv = h.get("market_value", 0) or 0

        if mv <= 0:
            continue

        # 场外基金 → 标记 OTC，交 P3-12
        if _is_otc_fund(name, code):
            results.append({
                "code": code,
                "name": name,
                "market_value": mv,
                "type": "otc",
                "avg_daily_turnover": None,
                "liquidation_days": None,
                "tag": "场外基金",
            })
            continue

        # 场内品种 → 计算变现天数
        if _is_exchange_traded(code, name):
            avg_turnover = _compute_avg_daily_turnover(code)
            if avg_turnover is not None and avg_turnover > 0:
                liq_days = mv / avg_turnover
                tag = "当日可卖出" if liq_days < _SAME_DAY_THRESHOLD else f"需约{liq_days:.1f}日卖出"
                results.append({
                    "code": code,
                    "name": name,
                    "market_value": mv,
                    "type": "stock",
                    "avg_daily_turnover": round(avg_turnover, 2),
                    "liquidation_days": round(liq_days, 2),
                    "tag": tag,
                })
            else:
                # 数据获取失败 → 默认充足
                logger.info("[liquidity] %s(%s) 成交额数据缺失，默认流动性充足", name, code)
                results.append({
                    "code": code,
                    "name": name,
                    "market_value": mv,
                    "type": "assumed_liquid",
                    "avg_daily_turnover": None,
                    "liquidation_days": None,
                    "tag": "流动性充足（数据缺失）",
                })
        else:
            # 港股等其他类型 → 标记为 assumed_liquid
            results.append({
                "code": code,
                "name": name,
                "market_value": mv,
                "type": "assumed_liquid",
                "avg_daily_turnover": None,
                "liquidation_days": None,
                "tag": "流动性充足（数据缺失）",
            })

    return results
