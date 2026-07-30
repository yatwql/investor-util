"""再平衡信号计算模块。

支持：
  - 目标配置 Schema（大类 + 品种级）
  - 权益/固收超大类偏离计算
  - 读取/计算当前大类/品种偏离度
  - 结构化输出再平衡信号

架构约束：
  ⚠️ 禁止导入 report/ 包下的任何模块。
  通过 code_utils.py 获取资产分类函数，保持与报告层的完全解耦。

目标配置 Schema（config.json → rebalance.target_allocation）：
  {
    "大类名称": {"min": 30, "max": 70, "target": 50},
    "品种代码": {"min": 0, "max": 15, "target": 10}
  }
  键为大类名称（如 "equity"）或证券代码（品种级配置）。
  配置为空 {} 时 = 不启用目标配置检查。

资产分类系统：
  大类名称        | 包含品种
  ----------------|--------------------------
  equity          | A 股、港股通、场内 ETF（股票型）
  fund_equity     | 场外股票型/混合型基金
  fixed_income    | 债券、纯债基金、短债
  money_market    | 货币基金、现金管理
  alternative     | 商品 ETF、REITs、可转债
  qdii            | QDII 基金（含隐式海外）
  others          | 未分类品种
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.code_utils import (
    is_a_share_code,
    is_bond_fund_by_name,
    is_exchange_fund_code,
    is_hk_stock_code,
    is_index_fund_by_name,
    is_money_fund_by_name,
    is_otc_fund_by_name,
    is_qdii_extended,
    is_convertible_bond_by_name,
    is_etf_by_name_or_code,
)
from src.python.config._core import get_config
from src.python.analysis._silence import (
    _SILENCE_FILE,
    _filter_silenced_signals,
    _load_silence_state,
    _save_silence_state,
    _update_silence_state,
)

logger = logging.getLogger("invest")

__all__ = [
    "classify_holding",
    "compute_target_deviation",
    "equity_fixed_income_deviation",
    "compute_rebalance_signals",
    "resolve_rebalance_config",
]

# ── 预设阈值集 ──────────────────────────────────────────────────
# key: profile 名称 → {threshold, deviation_threshold}
_REBALANCE_PROFILES: dict[str, dict[str, float]] = {
    "conservative": {"threshold": 0.10, "deviation_threshold": 0.03},
    "moderate": {"threshold": 0.15, "deviation_threshold": 0.05},
    "aggressive": {"threshold": 0.25, "deviation_threshold": 0.08},
}


def resolve_rebalance_config(rebalance_config: dict[str, Any] | None) -> dict[str, Any]:
    """解析再平衡配置，应用预设阈值集。

    当 profile 为 "conservative" / "moderate" / "aggressive" 时，
    用预设值覆盖 threshold 和 deviation_threshold（除非已在 config 中显式指定）。
    当 profile 为 "custom" 或未匹配时，使用 config 中的独立值。

    Args:
        rebalance_config: 原始 rebalance 配置段（可能为 None）

    Returns:
        解析后的配置字典（含 threshold、deviation_threshold、target_allocation 等）
    """
    if rebalance_config is None:
        config = get_config()
        rebalance_config = config.get("rebalance", {})
    result = dict(rebalance_config)

    profile = result.get("profile", "moderate")
    if profile in _REBALANCE_PROFILES:
        preset = _REBALANCE_PROFILES[profile]
        # 预设值作为默认值，用户显式指定的值优先（已在 config 中）
        result.setdefault("threshold", preset["threshold"])
        result.setdefault("deviation_threshold", preset["deviation_threshold"])
    else:
        # custom 或未知 profile → 使用独立配置值
        result.setdefault("threshold", 0.15)
        result.setdefault("deviation_threshold", 0.05)

    result.setdefault("target_allocation", {})
    result.setdefault("silence_days", 30)
    return result


# ── 误报防护 ────────────────────────────────────────────────────


def _apply_false_positive_protection(
    signals: list[dict[str, Any]],
    holdings_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对再平衡信号应用误报防护逻辑。

    三类防护：
      (1) 分红/拆股假超限：检查 shares 字段是否可用，持有量未变时标记 low_confidence
      (2) 新买入短期波动：holding_days < 20 时直接过滤
      (3) 临近行权/到期品种：标注 near_maturity 字段

    Args:
        signals: 再平衡信号列表
        holdings_details: 持仓明细列表

    Returns:
        经过误报防护处理后的信号列表
    """
    if not signals or not holdings_details:
        return signals

    # 构建 code → holding 字典
    holding_map: dict[str, dict[str, Any]] = {}
    for h in holdings_details:
        code = h.get("code", "")
        if code:
            holding_map[code] = h

    result: list[dict[str, Any]] = []
    for sig in signals:
        code = sig.get("code", "")
        if not code:
            result.append(sig)
            continue

        holding = holding_map.get(code)
        if not holding:
            result.append(sig)
            continue

        # (1) 分红/拆股假超限检查
        shares = holding.get("shares")
        if shares is not None:
            sig["shares_available"] = True
        else:
            sig["shares_available"] = False

        # (2) 新买入短期波动
        holding_days = holding.get("holding_days")
        if holding_days is not None and holding_days < 20:
            # 不足 20 个交易日 → 过滤
            sig["false_positive"] = True
            sig["false_positive_reason"] = f"持仓仅 {holding_days} 天，不足 20 个交易日，暂不触发再平衡"
            continue

        # (3) 临近行权/到期品种
        if is_convertible_bond_by_name(holding.get("name", "")):
            sig["near_maturity"] = True
            sig["action"] = sig.get("action", "") + "（可转债临近到期，建议关注转股或自然到期）"

        result.append(sig)

    return result


def _compute_confidence(
    signal_type: str,
    deviation: float | None,
    threshold: float | None = None,
    deviation_threshold_pct: float = 5.0,
) -> str:
    """计算再平衡信号置信度。

    规则：
      - single_overflow: weight 超过 2× threshold → high，否则 medium
      - category/security: abs(deviation) > 2× threshold → high，
        abs(deviation) > threshold → medium，否则 low

    Args:
        signal_type: 信号类型
        deviation: 偏离值（百分比，已有正负号）
        threshold: 单品超限阈值（小数，如 0.15）
        deviation_threshold_pct: 配置偏离阈值（百分比，如 5.0）

    Returns:
        "high" / "medium" / "low"
    """
    if signal_type == "single_overflow":
        # 单品超限：基于 weight 是否超过 2× threshold
        if threshold and deviation and deviation > threshold * 100 * 2:
            return "high"
        return "medium"

    # category / security 偏离
    abs_dev = abs(deviation) if deviation is not None else 0
    if abs_dev > deviation_threshold_pct * 2:
        return "high"
    if abs_dev > deviation_threshold_pct:
        return "medium"
    return "low"


# ── 资产分类 —──────────────────────────────────────────────────


def classify_holding(name: str, code: str) -> str:
    """对单个持仓进行资产大类分类。

    Args:
        name: 持仓名称
        code: 证券代码

    Returns:
        大类名称: equity / fund_equity / fixed_income / money_market /
                  alternative / qdii / others
    """
    # 可转债优先于 ETF/LOF 判定（代码以 1 开头，与 ETF 同区间）
    if is_convertible_bond_by_name(name):
        return "alternative"

    # QDII 判定（含隐式海外基金）
    if is_qdii_extended(name):
        return "qdii"

    # 货币基金
    if is_money_fund_by_name(name):
        return "money_market"

    # 债券基金（需在 QDII 之后，因为部分 QDII 债券基金含 "债" 字但不属纯债）
    if is_bond_fund_by_name(name):
        return "fixed_income"

    # 场内 ETF/LOF → 按代码细分（优先于 A 股判断）
    if is_exchange_fund_code(code):
        if is_etf_by_name_or_code(name, code):
            # 债券 ETF → 固收；货币 ETF → 货币；其余 → 权益
            if is_bond_fund_by_name(name):
                return "fixed_income"
            if is_money_fund_by_name(name):
                return "money_market"
            return "equity"
        return "alternative"  # LOF/Reits 等归入 alternative

    # 场外基金（名称匹配 + 00 代码重叠区判断，放在 A 股检查前）
    if is_otc_fund_by_name(name, code) or is_index_fund_by_name(name):
        if is_bond_fund_by_name(name):
            return "fixed_income"
        return "fund_equity"

    # A 股 / 港股通 → 权益
    if is_a_share_code(code) or is_hk_stock_code(code):
        return "equity"

    # 默认归入权益类基金
    return "fund_equity"


_CATEGORY_ORDER: list[str] = [
    "equity",
    "fund_equity",
    "fixed_income",
    "money_market",
    "alternative",
    "qdii",
    "others",
]

_CATEGORY_LABELS: dict[str, str] = {
    "equity": "权益（股票/ETF）",
    "fund_equity": "权益类基金",
    "fixed_income": "固收（债券/纯债基金）",
    "money_market": "货币基金",
    "alternative": "另类（商品/REITs/可转债）",
    "qdii": "QDII 海外",
    "others": "其他",
}

# 权益/固收超大类分组定义
# 将 7 个资产大类汇总为两个超大类用于权益/固收偏离检查
_EQUITY_FI_GROUPS: dict[str, dict[str, Any]] = {
    "equity": {
        "categories": ["equity", "fund_equity", "qdii"],
        "label": "权益类",
    },
    "fixed_income": {
        "categories": ["fixed_income", "money_market", "alternative"],
        "label": "固收类",
    },
}


def _categorize_holdings(
    holdings_details: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """按大类分类持仓列表。

    Args:
        holdings_details: 持仓明细列表（含 name / code / market_value）

    Returns:
        {大类名称: [持仓条目, ...]}
    """
    categorized: dict[str, list[dict[str, Any]]] = {cat: [] for cat in _CATEGORY_ORDER}
    for h in holdings_details:
        name = h.get("name", "")
        code = h.get("code", "")
        cat = classify_holding(name, code)
        if cat not in categorized:
            cat = "others"
        categorized[cat].append(h)
    return categorized


def _calc_category_weights(
    categorized: dict[str, list[dict[str, Any]]],
    total_mv: float,
) -> dict[str, float]:
    """计算各资产大类的市值权重百分比。

    Args:
        categorized: _categorize_holdings() 返回的分类字典
        total_mv: 持仓总市值

    Returns:
        {大类名称: 权重百分比（如 45.5 表示 45.5%）}
    """
    weights: dict[str, float] = {}
    for cat in _CATEGORY_ORDER:
        items = categorized.get(cat, [])
        mv = sum(h.get("market_value", 0) or 0 for h in items)
        weights[cat] = round(mv / total_mv * 100, 2) if total_mv > 0 else 0.0
    return weights


def _calc_group_weights(cat_weights: dict[str, float]) -> dict[str, float]:
    """汇总各大类权重为权益/固收超大类权重。

    Args:
        cat_weights: _calc_category_weights() 的返回

    Returns:
        {超大类key: 权重百分比}
    """
    group_weights: dict[str, float] = {}
    for group_key, group_info in _EQUITY_FI_GROUPS.items():
        total_w = sum(cat_weights.get(cat, 0.0) for cat in group_info["categories"])
        group_weights[group_key] = round(total_w, 2)
    return group_weights


def _build_category_deviation_signals(
    cat_weights: dict[str, float],
    target_allocation: dict[str, dict],
    deviation_threshold: float,
) -> list[dict[str, Any]]:
    """大类配置偏离检查：遍历 target_allocation 中属于大类的条目，生成偏离信号。"""
    signals: list[dict[str, Any]] = []
    threshold_pct = deviation_threshold * 100
    for key, target in target_allocation.items():
        if key not in _CATEGORY_ORDER and key not in _CATEGORY_LABELS:
            continue
        current = cat_weights.get(key, 0.0)
        t_min = target.get("min", 0)
        t_max = target.get("max", 100)
        t_target = target.get("target")

        deviation = round(current - (t_target or (t_min + t_max) / 2), 2)
        out_of_range = current < t_min or current > t_max
        if abs(deviation) < threshold_pct and not out_of_range:
            continue

        if current > t_max:
            action = (
                f"权益占比 {current}%，超过目标上限 {t_max}%，超配 {deviation:.1f}%，建议适当止盈权益类，增配固收类"
            )
        elif current < t_min:
            action = f"权益占比 {current}%，低于目标下限 {t_min}%，低配 {-deviation:.1f}%，建议适当增配权益类"
        else:
            action = f"权益占比 {current}%，在目标范围 {t_min}%-{t_max}% 内，无需调整"

        label = _CATEGORY_LABELS.get(key, key)
        confidence = _compute_confidence(
            "category",
            deviation=deviation,
            deviation_threshold_pct=deviation_threshold * 100,
        )
        signals.append(
            {
                "type": "category",
                "category": key,
                "category_label": label,
                "current_weight": current,
                "target_weight": t_target or (t_min + t_max) / 2,
                "min": t_min,
                "max": t_max,
                "deviation": deviation,
                "confidence": confidence,
                "action": action,
            }
        )
    return signals


def _build_security_deviation_signals(
    holdings_details: list[dict[str, Any]],
    total_mv: float,
    target_allocation: dict[str, dict],
    deviation_threshold: float,
) -> list[dict[str, Any]]:
    """品种级配置偏离检查：遍历 target_allocation 中属于证券代码的条目，生成偏离信号。"""
    signals: list[dict[str, Any]] = []
    threshold_pct = deviation_threshold * 100
    for key, target in target_allocation.items():
        if key in _CATEGORY_ORDER or key in _CATEGORY_LABELS:
            continue
        for h in holdings_details:
            if h.get("code") == key:
                mv = h.get("market_value", 0) or 0
                current_w = round(mv / total_mv * 100, 2) if total_mv > 0 else 0.0
                t_min = target.get("min", 0)
                t_max = target.get("max", 100)
                t_target = target.get("target")

                deviation = round(current_w - (t_target or (t_min + t_max) / 2), 2)
                out_of_range = current_w < t_min or current_w > t_max
                if abs(deviation) < threshold_pct and not out_of_range:
                    continue

                if current_w > t_max:
                    act = f"持有 {current_w}%，目标 {t_target or t_max}%，超配 {deviation:.1f}%，建议部分止盈"
                elif current_w < t_min:
                    act = f"持有 {current_w}%，低于目标下限 {t_min}%，低配 {-deviation:.1f}%，建议适当增持"
                else:
                    act = f"持有 {current_w}%，在目标范围 {t_min}%-{t_max}% 内"
                sec_confidence = _compute_confidence(
                    "security",
                    deviation=deviation,
                    deviation_threshold_pct=deviation_threshold * 100,
                )
                signals.append(
                    {
                        "type": "security",
                        "code": key,
                        "name": h.get("name", ""),
                        "current_weight": current_w,
                        "target_weight": t_target or (t_min + t_max) / 2,
                        "deviation": deviation,
                        "confidence": sec_confidence,
                        "action": act,
                    }
                )
                break
    return signals


# ── 目标配置偏离度计算 ─────────────────────────────────────────


def compute_target_deviation(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    target_allocation: dict[str, dict] | None = None,
    deviation_threshold: float = 0.05,
) -> list[dict[str, Any]]:
    """计算当前持仓与目标配置的偏离度。

    编排 _build_category_deviation_signals 和 _build_security_deviation_signals，
    分别计算大类偏离和品种级偏离信号。
    """
    if not holdings_details or total_mv <= 0:
        return []

    if target_allocation is None:
        config = get_config()
        rebalance_cfg = config.get("rebalance", {})
        target_allocation = rebalance_cfg.get("target_allocation", {})

    if not target_allocation:
        return []

    categorized = _categorize_holdings(holdings_details)
    cat_weights = _calc_category_weights(categorized, total_mv)

    signals: list[dict[str, Any]] = []
    signals.extend(_build_category_deviation_signals(cat_weights, target_allocation, deviation_threshold))
    signals.extend(
        _build_security_deviation_signals(holdings_details, total_mv, target_allocation, deviation_threshold)
    )
    return signals


# ── 权益/固收偏离 ────────────────────────────────────────────


def _build_equity_fi_signals(
    group_weights: dict[str, float],
    equity_fi_target: dict[str, dict],
    threshold_pct: float,
    deviation_threshold: float,
) -> list[dict[str, Any]]:
    """构建权益/固收超大类偏离信号。"""
    signals: list[dict[str, Any]] = []
    for group_key, target in equity_fi_target.items():
        if group_key not in _EQUITY_FI_GROUPS:
            logger.warning("equity_fixed_income_deviation: 未知超大类 %r，跳过", group_key)
            continue

        current = group_weights.get(group_key, 0.0)
        t_min = target.get("min", 0)
        t_max = target.get("max", 100)
        t_target = target.get("target")

        deviation = round(current - (t_target or (t_min + t_max) / 2), 2)
        out_of_range = current < t_min or current > t_max

        if abs(deviation) < threshold_pct and not out_of_range:
            continue

        group_label = _EQUITY_FI_GROUPS[group_key]["label"]

        if current > t_max:
            action = (
                f"{group_label}仓位 {current}%，超过目标上限 {t_max}%，"
                f"超配 {deviation:.1f}%，建议适当降低{group_label}配置"
            )
        elif current < t_min:
            action = (
                f"{group_label}仓位 {current}%，低于目标下限 {t_min}%，"
                f"低配 {-deviation:.1f}%，建议适当增加{group_label}配置"
            )
        else:
            action = f"{group_label}仓位 {current}%，在目标范围 {t_min}%-{t_max}% 内，无需调整"

        confidence = _compute_confidence(
            "category",
            deviation=deviation,
            deviation_threshold_pct=deviation_threshold * 100,
        )

        signals.append(
            {
                "type": "equity_fixed_income",
                "group": group_key,
                "group_label": group_label,
                "current_weight": current,
                "target_weight": t_target or (t_min + t_max) / 2,
                "min": t_min,
                "max": t_max,
                "deviation": deviation,
                "confidence": confidence,
                "action": action,
            }
        )

    return signals


def equity_fixed_income_deviation(
    holdings_details: list[dict[str, Any]],
    total_mv: float,
    equity_fi_target: dict[str, dict] | None = None,
    deviation_threshold: float = 0.05,
) -> list[dict[str, Any]]:
    """计算权益/固收超大类偏离信号。

    将 7 个资产大类汇总为权益类和固收类超大类，
    委托 _calc_group_weights / _build_equity_fi_signals 计算偏离信号。
    """
    if not holdings_details or total_mv <= 0:
        return []

    if equity_fi_target is None:
        config = get_config()
        rebalance_cfg = config.get("rebalance", {})
        equity_fi_target = rebalance_cfg.get("equity_fixed_income", {})

    if not equity_fi_target:
        return []

    categorized = _categorize_holdings(holdings_details)
    cat_weights = _calc_category_weights(categorized, total_mv)
    group_weights = _calc_group_weights(cat_weights)
    threshold_pct = deviation_threshold * 100

    return _build_equity_fi_signals(group_weights, equity_fi_target, threshold_pct, deviation_threshold)


# ── 再平衡信号入口（整合单品超限 + 目标偏离 + 权益/固收偏离） ─


def _compute_single_overflow_signals(
    holdings_details: list[dict[str, Any]],
    total_mv: float,
    threshold: float,
) -> list[dict[str, Any]]:
    """单品超限信号：检查每个品种是否超过单项配置上限，超过 3 个时汇总。"""
    _MAX_DETAILED = 3
    single_signals: list[dict[str, Any]] = []
    for h in holdings_details:
        mv = h.get("market_value", 0) or 0
        weight = mv / total_mv
        if weight > threshold:
            weight_pct = round(weight * 100, 2)
            confidence = _compute_confidence(
                "single_overflow",
                deviation=weight_pct,
                threshold=threshold,
            )
            single_signals.append(
                {
                    "type": "single_overflow",
                    "code": h.get("code", ""),
                    "name": h.get("name", ""),
                    "weight": weight_pct,
                    "threshold": threshold * 100,
                    "confidence": confidence,
                    "action": f"持仓 {weight * 100:.1f}%，超出建议上限 {threshold * 100:.0f}%，建议部分止盈至 {threshold * 50:.0f}-{threshold * 100:.0f}% 区间",
                }
            )

    signals: list[dict[str, Any]] = []
    if len(single_signals) > _MAX_DETAILED:
        signals.append(
            {
                "type": "summary",
                "summary": True,
                "count": len(single_signals),
                "message": (
                    f"您的组合集中度较高，有 {len(single_signals)} 个品种超过 "
                    f"{threshold * 100:.0f}% 警戒线，建议整体考虑适度分散"
                ),
            }
        )
    else:
        single_signals.sort(key=lambda x: -x["weight"])
        signals.extend(single_signals[:_MAX_DETAILED])

    return signals


def compute_rebalance_signals(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    rebalance_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """计算完整再平衡信号。

    编排五步流程：
      1. 单品超限信号（_compute_single_overflow_signals）
      2. 目标配置偏离信号（compute_target_deviation）
      3. 权益/固收超大类偏离信号（equity_fixed_income_deviation）
      4. 误报防护（_apply_false_positive_protection）
      5. 静默期过滤（_filter_silenced_signals）
    """
    if not holdings_details or total_mv <= 0:
        return []

    resolved = resolve_rebalance_config(rebalance_config)
    threshold = resolved.get("threshold", 0.15)
    deviation_threshold = resolved.get("deviation_threshold", 0.05)
    target_allocation = resolved.get("target_allocation", {})
    equity_fi_target = resolved.get("equity_fixed_income", {})

    signals: list[dict[str, Any]] = []

    # 1. 单品超限信号
    signals.extend(_compute_single_overflow_signals(holdings_details, total_mv, threshold))

    # 2. 目标配置偏离信号
    if target_allocation:
        signals.extend(compute_target_deviation(holdings_details, total_mv, target_allocation, deviation_threshold))

    # 3. 权益/固收超大类偏离信号
    if equity_fi_target:
        signals.extend(equity_fixed_income_deviation(holdings_details, total_mv, equity_fi_target, deviation_threshold))

    # 4. 误报防护
    signals = _apply_false_positive_protection(signals, holdings_details)

    # 5. 静默期过滤 + 更新
    silence_days = resolved.get("silence_days", 30)
    if silence_days > 0:
        silence_file = resolved.get("_silence_file")
        signals = _filter_silenced_signals(signals, silence_days, silence_file)
        _update_silence_state(signals, silence_file)

    return signals
