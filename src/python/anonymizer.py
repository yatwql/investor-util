"""持仓匿名化模块 — 4 种匿名化模式。

用于在分享报告时隐藏真实持仓数据，保护隐私。

4 模式：
  - "off":             不处理，原样返回
  - "code_display":    名称 → "品种X"，保留代码和盈亏
  - "full_anonymous":  名称 → "品种X"，代码 → "000XXX"，盈亏模糊化
  - "summary":         仅显示大类汇总，不展示单条持仓

使用方式：
  >>> from src.python.anonymizer import anonymize_holdings
  >>> anon = anonymize_holdings(holdings, mode="code_display")
  >>> anon[0].name
  '品种A'

配置持久化：
  >>> get_anonymization_mode()
  'off'
  >>> set_anonymization_mode("code_display")
"""

from __future__ import annotations

import copy
import logging
import warnings
from typing import Any

from src.python.models import Holding

logger = logging.getLogger("invest")

# ── 模式定义 ──────────────────────────────────────────────────────

_ANONYMIZATION_MODES = frozenset({"off", "code_display", "full_anonymous", "summary"})

# 模式名别名映射（别名 → 当前命名）
_DEPRECATED_MODE_MAP: dict[str, str] = {
    "name_replace": "code_display",
    "quantity_blur": "full_anonymous",
}

# 别名提示消息模板
_DEPRECATION_WARNING_TPL = "匿名化模式 '%s' 已重命名为 '%s'，请更新配置"

__all__ = [
    "anonymize_holdings",
    "anonymize_holdings_details",
    "is_anonymization_enabled",
    "get_anonymization_mode",
    "set_anonymization_mode",
    "ANONYMIZATION_MODE_DESCRIPTIONS",
]

ANONYMIZATION_MODE_DESCRIPTIONS: dict[str, str] = {
    "off": "关闭 — 显示真实持仓名称和代码",
    "code_display": "代码显示 — 名称替换为'品种X'，保留代码和盈亏",
    "full_anonymous": "完全匿名 — 名称'品种X'，代码'000XXX'，盈亏±XX%",
    "summary": "汇总模式 — 仅显示大类汇总，不展示单条持仓",
}

# ── 模式判断 ──────────────────────────────────────────────────────


def _resolve_mode(mode: str) -> str:
    """解析模式字符串：处理废弃别名，未知时回退到 'off'。"""
    if mode in _DEPRECATED_MODE_MAP:
        new_mode = _DEPRECATED_MODE_MAP[mode]
        warnings.warn(_DEPRECATION_WARNING_TPL % (mode, new_mode), DeprecationWarning, stacklevel=3)
        logger.warning("[anonymizer] " + _DEPRECATION_WARNING_TPL, mode, new_mode)
        return new_mode
    if mode not in _ANONYMIZATION_MODES:
        logger.warning("[anonymizer] 未知匿名化模式 '%s'，使用 'off'", mode)
        return "off"
    return mode


def is_anonymization_enabled(mode: str) -> bool:
    """判断匿名化是否启用。

    Args:
        mode: 匿名化模式

    Returns:
        True 表示需执行匿名化处理
    """
    mode = _resolve_mode(mode)
    if mode == "off":
        return False
    return True


# ── 持仓列表匿名化 ────────────────────────────────────────────────


def anonymize_holdings(
    holdings: list[Holding],
    mode: str = "off",
) -> list[Holding] | dict[str, dict[str, Any]]:
    """对持仓列表执行匿名化处理。

    Args:
        holdings: 原始持仓列表
        mode: 匿名化模式

    Returns:
        - off / code_display / full_anonymous: 匿名化后的持仓列表
        - summary: 按类别汇总的字典
    """
    mode = _resolve_mode(mode)

    if mode == "off":
        return holdings

    if mode == "summary":
        return _aggregate_holdings_summary(holdings)

    result = copy.deepcopy(holdings)

    # 名称替换（所有启用非 summary 模式均执行）
    _replace_names(result, prefix="品种")

    if mode == "full_anonymous":
        _blur_shares(result)
        _mask_codes(result)

    logger.info("[anonymizer] 持仓匿名化完成（模式: %s）", mode)
    return result


def anonymize_holdings_details(
    details: list[dict[str, Any]],
    mode: str = "off",
) -> list[dict[str, Any]] | dict[str, dict[str, Any]]:
    """对持仓明细字典列表执行匿名化处理。

    适配 report/handlers_report.py 中 prepare_report_data 返回的
    holdings_details 格式。

    Args:
        details: 持仓明细字典列表
        mode: 匿名化模式

    Returns:
        - off / code_display / full_anonymous: 匿名化后的列表
        - summary: 按类别汇总的字典
    """
    mode = _resolve_mode(mode)

    if mode == "off":
        return details

    if mode == "summary":
        return _aggregate_details_summary(details)

    result = copy.deepcopy(details)
    _name_counter = 0
    _name_map: dict[str, str] = {}

    for d in result:
        code = d.get("code", "")
        if code and code not in _name_map:
            _name_counter += 1
            _name_map[code] = f"品种{_num_to_label(_name_counter)}"
        if code in _name_map:
            d["name"] = _name_map[code]

    if mode == "full_anonymous":
        for d in result:
            _anonymize_detail_entry(d)

    logger.info("[anonymizer] 持仓明细匿名化完成（模式: %s）", mode)
    return result


# ── 内部辅助函数 ──────────────────────────────────────────────────


def _replace_names(holdings: list[Holding], prefix: str = "品种") -> None:
    """将持仓名称替换为匿名代号。"""
    _counter = 0
    _seen_codes: dict[str, str] = {}
    for h in holdings:
        if h.code not in _seen_codes:
            _counter += 1
            _seen_codes[h.code] = f"{prefix}{_num_to_label(_counter)}"
        h.name = _seen_codes[h.code]


def _blur_shares(holdings: list[Holding]) -> None:
    """将份额四舍五入到百位（隐藏精确仓位）。"""
    for h in holdings:
        h.shares = round(h.shares / 100) * 100
        if h.shares < 100 and h.shares > 0:
            h.shares = 100  # 最小显示单位


def _mask_codes(holdings: list[Holding]) -> None:
    """将代码替换为掩码 '000XXX'。"""
    for h in holdings:
        h.code = "000XXX"


def _blur_value(value: float, precision: int = 1000) -> float:
    """将数值四舍五入到指定精度（隐藏精确金额）。"""
    if value == 0:
        return 0.0
    return round(value / precision) * precision


def _anonymize_detail_entry(d: dict[str, Any]) -> None:
    """对单条明细条目执行 full_anonymous 处理。"""
    code = d.get("code", "")
    if code:
        d["code"] = "000XXX"

    mv = d.get("market_value", 0)
    if mv:
        d["market_value"] = _blur_value(mv, 1000)

    cost = d.get("cost", 0)
    if cost:
        d["cost"] = _blur_value(cost, 1000)

    profit = d.get("profit", 0)
    if profit:
        profit_rate = d.get("profit_rate_pct", 0)
        sign = "+" if profit >= 0 else "-"
        d["profit"] = f"{sign}{abs(profit_rate):.1f}%"
    else:
        d["profit"] = "±0.0%"


def _categorize_holding(h: Holding) -> str:
    """对单条持仓进行分类。

    使用 code_utils.is_fund_holding 判断是否为基金。
    简单回退：代码以 0/3/6 开头且字段齐全按股票处理。
    """
    try:
        from src.python.code_utils import is_fund_holding

        if is_fund_holding(h.name, h.code, h.account):
            return "基金"
        return "股票/其他"
    except ImportError:
        pass

    # 回退：按代码前缀粗略判断
    code = h.code.strip()
    if code and code[0] in ("0", "3", "6"):
        return "股票/其他"
    return "基金"


def _categorize_detail(d: dict[str, Any]) -> str:
    """对单条持仓明细进行分类。"""
    code = d.get("code", "")
    name = d.get("name", "")
    account = d.get("account", "")
    try:
        from src.python.code_utils import is_fund_holding

        if is_fund_holding(name, code, account):
            return "基金"
        return "股票/其他"
    except ImportError:
        pass

    code_str = str(code).strip()
    if code_str and code_str[0] in ("0", "3", "6"):
        return "股票/其他"
    return "基金"


def _aggregate_holdings_summary(holdings: list[Holding]) -> dict[str, dict[str, Any]]:
    """将持仓按类别汇总。

    Args:
        holdings: 原始持仓列表

    Returns:
        {category: {count, cost, shares}} 形式的汇总字典
        注意：Holding 不含市场价，故 market_value / profit 需在
        上层（anonymize_holdings_details 级别）计算。
    """
    summary: dict[str, dict[str, Any]] = {}

    for h in holdings:
        cat = _categorize_holding(h)
        if cat not in summary:
            summary[cat] = {"count": 0, "cost": 0.0, "shares": 0.0}
        summary[cat]["count"] += 1
        summary[cat]["cost"] += h.shares * h.cost_price
        summary[cat]["shares"] += h.shares

    return summary


def _aggregate_details_summary(details: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """将持仓明细按类别汇总，包含完整的财务指标。

    Args:
        details: 持仓明细字典列表

    Returns:
        {category: {count, market_value, cost, profit, profit_rate_pct}} 汇总字典
    """
    summary: dict[str, dict[str, Any]] = {}

    for d in details:
        cat = _categorize_detail(d)
        if cat not in summary:
            summary[cat] = {"count": 0, "market_value": 0.0, "cost": 0.0, "profit": 0.0, "profit_rate_pct": 0.0}

        summary[cat]["count"] += 1
        summary[cat]["market_value"] += d.get("market_value", 0) or 0
        summary[cat]["cost"] += d.get("cost", 0) or 0
        summary[cat]["profit"] += d.get("profit", 0) or 0
        summary[cat]["profit_rate_pct"] += d.get("profit_rate_pct", 0) or 0

    # 计算平均值 profit_rate_pct
    for cat_data in summary.values():
        if cat_data["count"] > 0 and cat_data["profit_rate_pct"] != 0:
            cat_data["profit_rate_pct"] = round(cat_data["profit_rate_pct"] / cat_data["count"], 2)

    return summary


# ── 工具函数 ──────────────────────────────────────────────────────


def _num_to_label(n: int) -> str:
    """数字转字母标签：1→A, 2→B, ..., 26→Z, 27→AA, 28→AB..."""
    label = ""
    while n > 0:
        n -= 1
        label = chr(ord("A") + n % 26) + label
        n //= 26
    return label or "A"


# ── 配置读写 ──────────────────────────────────────────────────────


def get_anonymization_mode() -> str:
    """从配置中读取匿名化模式。

    Returns:
        当前模式字符串，默认为 "off"
    """
    from src.python.config import get_config

    config = get_config()
    anon_config = config.get("anonymization", {})
    mode = anon_config.get("mode", "off")
    if mode not in _ANONYMIZATION_MODES and mode not in _DEPRECATED_MODE_MAP:
        logger.warning("[anonymizer] 配置中的匿名化模式 '%s' 无效，使用 'off'", mode)
        mode = "off"
    return mode


def set_anonymization_mode(mode: str) -> None:
    """将匿名化模式持久化到配置。

    Args:
        mode: 新模式（必须在 _ANONYMIZATION_MODES 中）

    Raises:
        ValueError: mode 不在合法模式集合中
    """
    if mode not in _ANONYMIZATION_MODES:
        valid = ", ".join(sorted(_ANONYMIZATION_MODES))
        raise ValueError(f"无效匿名化模式 '{mode}'，有效值: {valid}")

    from src.python.config import get_config, set_config

    config = get_config()
    anon_config = dict(config.get("anonymization", {}))
    anon_config["mode"] = mode
    set_config("anonymization", anon_config)
    logger.info("[anonymizer] 匿名化模式已更新为 '%s'", mode)
