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

import datetime
import json
import logging
import os
from typing import Any

from src.python.constants import PROJECT_ROOT

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


# ── 静默期管理 ──────────────────────────────────────────────────

# 静默期持久化路径（可通过 monkeypatch.setattr 注入测试路径）
_SILENCE_FILE = os.path.join(PROJECT_ROOT, "data/state/rebalance_silence.json")


def _load_silence_state(silence_file: str | None = None) -> dict[str, str]:
    """从持久化文件加载静默期状态。

    Args:
        silence_file: 静默期文件路径。为 None 时使用 _SILENCE_FILE。

    Returns:
        {品种代码: 触发日期 (YYYY-MM-DD)}
    """
    path = silence_file or _SILENCE_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("再平衡静默期文件格式异常，将重置: %s", path)
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("再平衡静默期文件读取失败，将重置: %s", e)
        return {}


def _save_silence_state(state: dict[str, str], silence_file: str | None = None) -> None:
    """持久化静默期状态到文件。

    Args:
        state: {品种代码: 触发日期 (YYYY-MM-DD)}
        silence_file: 静默期文件路径。为 None 时使用 _SILENCE_FILE。
    """
    path = silence_file or _SILENCE_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("再平衡静默期文件写入失败: %s", e)


def _filter_silenced_signals(
    signals: list[dict[str, Any]],
    silence_days: int,
    silence_file: str | None = None,
) -> list[dict[str, Any]]:
    """过滤静默期内的再平衡信号。

    对于有 code 的信号（单品超限、品种级偏离），检查是否在静默期内。
    大类偏离信号（category）不参与静默期检查。
    静默期到期的条目自动从持久化状态中清理。

    Args:
        signals: 再平衡信号列表
        silence_days: 静默期天数
        silence_file: 静默期文件路径

    Returns:
        过滤后的信号列表（附静默信息）
    """
    if not signals or silence_days <= 0:
        return signals

    state = _load_silence_state(silence_file)
    today = datetime.date.today()
    today_str = today.isoformat()
    expired_codes: set[str] = set()
    result: list[dict[str, Any]] = []

    for sig in signals:
        code = sig.get("code", "")
        if not code or sig.get("type") in ("category", "summary"):
            # 大类偏离和汇总信号不参与静默期
            result.append(sig)
            continue

        trigger_date_str = state.get(code)
        if trigger_date_str:
            try:
                trigger_date = datetime.date.fromisoformat(trigger_date_str)
                days_passed = (today - trigger_date).days
                if days_passed < silence_days:
                    # 静默期内：跳过，添加过期标记（延迟清理）
                    remaining = silence_days - days_passed
                    logger.debug("品种 %s 在静默期内（剩余 %d 天），跳过", code, remaining)
                    continue
                else:
                    # 静默期已过：清理
                    expired_codes.add(code)
            except (ValueError, TypeError):
                # 日期格式异常，视为过期
                expired_codes.add(code)

        result.append(sig)

    # 清理过期条目
    if expired_codes:
        for c in expired_codes:
            state.pop(c, None)
        _save_silence_state(state, silence_file)

    return result


def _update_silence_state(
    signals: list[dict[str, Any]],
    silence_file: str | None = None,
) -> None:
    """将新触发的信号更新到静默期持久化状态。

    Args:
        signals: 再平衡信号列表
        silence_file: 静默期文件路径
    """
    state = _load_silence_state(silence_file)
    today_str = datetime.date.today().isoformat()
    updated = False

    for sig in signals:
        code = sig.get("code", "")
        if code and sig.get("type") not in ("category", "summary"):
            if code not in state:
                state[code] = today_str
                updated = True

    if updated:
        _save_silence_state(state, silence_file)


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


# ── 目标配置偏离度计算 ─────────────────────────────────────────


def compute_target_deviation(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    target_allocation: dict[str, dict] | None = None,
    deviation_threshold: float = 0.05,
) -> list[dict[str, Any]]:
    """计算当前持仓与目标配置的偏离度。

    Args:
        holdings_details: 持仓明细列表
        total_mv: 持仓总市值
        target_allocation: 目标配置 Schema。
            为 None 时从 config.json 读取。
            空字典 {} = 不启用目标配置检查。
        deviation_threshold: 偏离度阈值（小数，0.05=5%）。偏离低于此值且未超限时不输出信号。

    Returns:
        偏离度信号列表：
        [
          {
            "type": "category",  # 大类偏离
            "category": "equity",
            "category_label": "权益（股票/ETF）",
            "current_weight": 55.0,   # 当前权重 %
            "target_weight": 50.0,    # 目标权重 %
            "min": 30.0,              # 目标下限
            "max": 70.0,              # 目标上限
            "deviation": 5.0,         # 偏离度（正=超配，负=低配）
            "action": "超配 5.0%，建议适当止盈权益类，增配固收类",
          },
          {
            "type": "security",  # 品种级偏离
            "code": "600519",
            "name": "贵州茅台",
            "current_weight": 18.5,
            "target_weight": 10.0,
            "deviation": 8.5,
            "action": "持有 18.5%，目标 10.0%，超配 8.5%，建议部分止盈",
          },
        ]
    """
    if not holdings_details or total_mv <= 0:
        return []

    # 读取目标配置
    if target_allocation is None:
        config = get_config()
        rebalance_cfg = config.get("rebalance", {})
        target_allocation = rebalance_cfg.get("target_allocation", {})

    if not target_allocation:
        return []

    # 分类 + 计算大类权重
    categorized = _categorize_holdings(holdings_details)
    cat_weights = _calc_category_weights(categorized, total_mv)

    signals: list[dict[str, Any]] = []

    # 1. 大类配置偏离检查
    for key, target in target_allocation.items():
        # 跳过品种级配置（键为证券代码的，在品种级检查中处理）
        if key in _CATEGORY_ORDER or key in _CATEGORY_LABELS:
            current = cat_weights.get(key, 0.0)
            t_min = target.get("min", 0)
            t_max = target.get("max", 100)
            t_target = target.get("target")

            deviation = round(current - (t_target or (t_min + t_max) / 2), 2)

            # 仅在偏离超过阈值或超出范围时输出
            threshold_pct = deviation_threshold * 100
            out_of_range = current < t_min or current > t_max
            if abs(deviation) < threshold_pct and not out_of_range:
                continue

            # 生成建议文本
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

    # 2. 品种级配置检查
    for key, target in target_allocation.items():
        # 品种级: 键为证券代码
        if key in _CATEGORY_ORDER or key in _CATEGORY_LABELS:
            continue
        # 查找该品种的当前持有
        for h in holdings_details:
            if h.get("code") == key:
                mv = h.get("market_value", 0) or 0
                current_w = round(mv / total_mv * 100, 2) if total_mv > 0 else 0.0
                t_min = target.get("min", 0)
                t_max = target.get("max", 100)
                t_target = target.get("target")

                deviation = round(current_w - (t_target or (t_min + t_max) / 2), 2)
                out_of_range = current_w < t_min or current_w > t_max
                if abs(deviation) < (deviation_threshold * 100) and not out_of_range:
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


# ── 权益/固收偏离 ────────────────────────────────────────────


def equity_fixed_income_deviation(
    holdings_details: list[dict[str, Any]],
    total_mv: float,
    equity_fi_target: dict[str, dict] | None = None,
    deviation_threshold: float = 0.05,
) -> list[dict[str, Any]]:
    """计算权益/固收超大类偏离信号。

    将 7 个资产大类汇总为两个超大类进行偏离分析：
      - 权益类（equity）：equity + fund_equity + qdii
      - 固收类（fixed_income）：fixed_income + money_market + alternative

    对照目标配置（P3-01）计算偏离度，偏离低于阈值时不输出。
    输出示例："权益类仓位 78%，超过目标上限 70%（超配 8%），建议适当止盈权益类品种，增配固收类"

    Args:
        holdings_details: 持仓明细列表
        total_mv: 持仓总市值
        equity_fi_target: 权益/固收目标配置。
            None 时从 config.json 的 rebalance.equity_fixed_income 读取。
            空字典 {} = 不启用检查。
        deviation_threshold: 偏离度阈值（小数，0.05=5%）。偏离低于此值且未超限时不输出。

    Returns:
        权益/固收偏离信号列表：
        [
          {
            "type": "equity_fixed_income",
            "group": "equity",          # 超大类 key
            "group_label": "权益类",
            "current_weight": 78.0,     # 当前权重 %
            "target_weight": 70.0,      # 目标权重 %
            "min": 60.0,                # 目标下限
            "max": 80.0,                # 目标上限
            "deviation": 8.0,           # 偏离度（正=超配，负=低配）
            "confidence": "high",
            "action": "权益类仓位 78%，超过目标上限 80%（超配 8%），建议适当止盈权益类品种，增配固收类",
          },
        ]
    """
    if not holdings_details or total_mv <= 0:
        return []

    if equity_fi_target is None:
        config = get_config()
        rebalance_cfg = config.get("rebalance", {})
        equity_fi_target = rebalance_cfg.get("equity_fixed_income", {})

    if not equity_fi_target:
        return []

    # 分类并计算各类权重
    categorized = _categorize_holdings(holdings_details)
    cat_weights = _calc_category_weights(categorized, total_mv)

    # 汇总为权益/固收超大类权重
    group_weights: dict[str, float] = {}
    for group_key, group_info in _EQUITY_FI_GROUPS.items():
        total_w = sum(cat_weights.get(cat, 0.0) for cat in group_info["categories"])
        group_weights[group_key] = round(total_w, 2)

    signals: list[dict[str, Any]] = []
    threshold_pct = deviation_threshold * 100

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

        # 偏离低于阈值且未超限 → 不输出
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


# ── 再平衡信号入口（整合单品超限 + 目标偏离 + 权益/固收偏离） ─


def compute_rebalance_signals(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    rebalance_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """计算完整再平衡信号。

    包含三路信号：
      1. 单品超限信号
      2. 目标配置偏离信号（大类 + 品种级）
      3. 权益/固收超大类偏离信号

    配置项：
      - threshold: 单品超限阈值（默认 15%）
      - deviation_threshold: 大类/品种偏离阈值（默认 5%）
      - profile: 预设阈值集（conservative/moderate/aggressive/custom）
      - target_allocation: 目标配置 Schema
      - equity_fixed_income: 权益/固收超大类目标配置

    Args:
        holdings_details: 持仓明细列表（含 market_value / name / code）
        total_mv: 持仓总市值
        rebalance_config: 再平衡配置段。为 None 时从 config.json 读取。

    Returns:
        合并后的再平衡信号列表
    """
    if not holdings_details or total_mv <= 0:
        return []

    # 解析配置（含预设 profile 覆盖）
    resolved = resolve_rebalance_config(rebalance_config)
    threshold = resolved.get("threshold", 0.15)
    deviation_threshold = resolved.get("deviation_threshold", 0.05)
    target_allocation = resolved.get("target_allocation", {})

    signals: list[dict[str, Any]] = []

    # 1. 单品超限信号
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

    # 去重聚合：超过 3 个时汇总
    _MAX_DETAILED = 3
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

    # 2. 目标配置偏离信号
    if target_allocation:
        dev_signals = compute_target_deviation(
            holdings_details,
            total_mv,
            target_allocation,
            deviation_threshold,
        )
        signals.extend(dev_signals)

    # 3. 权益/固收超大类偏离信号
    equity_fi_target = resolved.get("equity_fixed_income", {})
    if equity_fi_target:
        ef_signals = equity_fixed_income_deviation(
            holdings_details,
            total_mv,
            equity_fi_target,
            deviation_threshold,
        )
        signals.extend(ef_signals)

    # 4. 误报防护
    signals = _apply_false_positive_protection(signals, holdings_details)

    # 5. 静默期过滤 + 更新
    silence_days = resolved.get("silence_days", 30)
    if silence_days > 0:
        silence_file = resolved.get("_silence_file")
        signals = _filter_silenced_signals(signals, silence_days, silence_file)
        _update_silence_state(signals, silence_file)

    return signals
