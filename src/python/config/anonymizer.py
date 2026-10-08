"""持仓匿名化模块 — 4 种匿名化模式。

用于在分享报告时隐藏真实持仓数据，保护隐私。

4 模式：
  - "off":             不处理，原样返回
  - "code_display":    名称 → "品种X"，保留代码和盈亏
  - "full_anonymous":  名称 → "品种X"，代码 → "000XXX"，盈亏模糊化
  - "summary":         仅显示大类汇总，不展示单条持仓

使用方式：
  >>> from src.python.config.anonymizer import anonymize_holdings
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
import re
from typing import Any

from src.python.core.code_utils import is_fund_holding
from src.python.core.models import Holding

#: 代码显示掩码：匿名模式下持仓代码在「展示面」的统一显示值。
CODE_DISPLAY_MASK = "000XXX"

#: 会把持仓代码折叠掉的模式（真码不出现在任何展示面）。
CODE_MASKING_MODES = frozenset({"full_anonymous", "summary"})


def is_code_masked_mode(mode: str | None) -> bool:
    """给定匿名化模式，判断持仓代码是否应折叠为显示掩码。

    Args:
        mode: 匿名化模式名（"off"/"code_display"/"full_anonymous"/"summary"）。

    Returns:
        True 表示代码需掩码（full_anonymous / summary），False 表示保留真码
        （off 原样 / code_display 契约保留代码）。
    """
    return (mode or "") in CODE_MASKING_MODES


logger = logging.getLogger("invest")

# ── 模式定义 ──────────────────────────────────────────────────────

_ANONYMIZATION_MODES = frozenset({"off", "code_display", "full_anonymous", "summary"})

__all__ = [
    "anonymize_holdings",
    "anonymize_holdings_details",
    "build_report_alias_map",
    "fold_details_summary",
    "mask_display_text",
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
    """解析模式字符串：未知模式回退到 'off'。"""
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
    """将代码替换为掩码 CODE_DISPLAY_MASK。"""
    for h in holdings:
        h.code = CODE_DISPLAY_MASK


def _blur_value(value: float, precision: int = 1000) -> float:
    """将数值四舍五入到指定精度（隐藏精确金额）；返回 float 保持字段类型契约。"""
    if value == 0:
        return 0.0
    return round(value / precision, 0) * precision


def _anonymize_detail_entry(d: dict[str, Any]) -> None:
    """对单条明细条目执行 full_anonymous 处理（数值字段层）。

    - 数值保持**数值型**（下游合计/图表/格式化契约）：市值与成本按千位模糊，
      盈亏与收益率由模糊值**派生**，保证行内恒等（盈亏 = 市值 − 成本）；
      收益率沿用百分比契约，避免模糊前精度反推。
    - **代码字段保留真值**：code 是再平衡静默、决策账本、申购状态等键控
      链路的键，掩码会跨品种碰撞；「000XXX」的显示由明细渲染层与
      产物文本清扫兜底（report 层匿名化接线）。
    """
    mv = d.get("market_value", 0) or 0
    if mv:
        mv = _blur_value(mv, 1000)
        d["market_value"] = mv

    cost = d.get("cost", 0) or 0
    if cost:
        cost = _blur_value(cost, 1000)
        d["cost"] = cost

    d["profit"] = round(mv - cost, 2)
    d["profit_rate"] = round((mv - cost) / cost * 100, 1) if cost else 0.0
    if "profit_rate_pct" in d:  # 旧键兼容：同步为派生值，避免残留原精度
        d["profit_rate_pct"] = d["profit_rate"]


def _categorize_holding(h: Holding) -> str:
    """对单条持仓进行分类（基金 / 股票及其他）。

    类型判定统一委托 ``code_utils.is_fund_holding``（代码类型判定中心化），
    本模块不自建前缀回退——自建前缀表既与中心判定漂移，
    也把「0/3/6 开头即股票」这一错误知识散落到匿名化层。
    """
    if is_fund_holding(h.name, h.code, h.account):
        return "基金"
    return "股票/其他"


def _categorize_detail(d: dict[str, Any]) -> str:
    """对单条持仓明细进行分类。"""
    code = d.get("code", "")
    name = d.get("name", "")
    account = d.get("account", "")
    if is_fund_holding(name, code, account):
        return "基金"
    return "股票/其他"


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


# ── 报告管线匿名化公共入口（字段层映射 / 文本掩码 / 大类折叠） ──────


def _entry_value(item: Any, key: str, default: str = "") -> str:
    """按 dict / 对象两种形态取字段值（明细字典、DetailRow、Holding 通用）。"""
    if isinstance(item, dict):
        return item.get(key, default) or default
    return getattr(item, key, default) or default


def build_report_alias_map(details: list[Any], mode: str = "off", *, include_codes: bool = True) -> dict[str, str]:
    """构建真值 → 展示值映射（字段层与产物清扫共用，保证代号编号一致）。

    编号规则与 ``anonymize_holdings_details`` 一致（code 首次见序 → 字母序），
    使字段层替换与产物文本清扫的「品种X」指向同一持仓。

    Args:
        details: 明细/持仓序列（dict、DetailRow、Holding 均可）
        mode: 匿名化模式；off → 空映射
        include_codes: 是否把真码纳入映射。HTML 自由文本清扫必须传 False——
            代码是纯数字串，全文子串替换会误伤金额与 JSON 数值；代码面改由
            渲染点结构化掩码（build_code_display_map）与 mask_code_text 负责。
            Excel 侧只动字符串单元格、金额是数值单元格，可保持 True。

    Returns:
        {真名: "品种X", ...}；full_anonymous 且 include_codes 时追加 {真码: 掩码}
    """
    mode = _resolve_mode(mode)
    if mode == "off":
        return {}

    code_label: dict[str, str] = {}
    name_map: dict[str, str] = {}
    counter = 0
    for item in details:
        code = _entry_value(item, "code")
        name = _entry_value(item, "name")
        if code and code not in code_label:
            counter += 1
            code_label[code] = f"品种{_num_to_label(counter)}"
        if name and name not in name_map and code in code_label:
            name_map[name] = code_label[code]

    alias_map = dict(name_map)
    if mode == "full_anonymous" and include_codes:
        alias_map.update({code: CODE_DISPLAY_MASK for code in code_label})
    return alias_map


def build_code_display_map(details: list[Any], mode: str = "off") -> dict[str, str]:
    """构建 {真码: 代码显示掩码} 映射（渲染点结构化替换用，精确键控命中）。

    与 :func:`build_report_alias_map` 的区别：只含代码、不含名称，且覆盖
    full_anonymous 与 summary 两种折叠代码面的模式（code_display 契约保留真码、
    off 原样，均返回空映射）。键是实际持仓代码，指数/基准等非持仓代码天然
    不在映射内、不会被误掩。

    Args:
        details: 明细/持仓序列（dict、DetailRow、Holding 均可）
        mode: 匿名化模式；off → 空映射

    Returns:
        {真码: CODE_DISPLAY_MASK}；无需折叠代码面时返回空映射
    """
    if not is_code_masked_mode(mode):
        return {}
    return {_entry_value(item, "code"): CODE_DISPLAY_MASK for item in details if _entry_value(item, "code")}


def code_masking_enabled(mode: str | None = None) -> bool:
    """当前（或指定）匿名化模式是否折叠持仓代码面。

    Args:
        mode: 匿名化模式；None → 读取当前配置模式。

    Returns:
        True 表示代码面应折叠为显示掩码（full_anonymous / summary）
    """
    if mode is None:
        mode = get_anonymization_mode()
    return is_code_masked_mode(mode)


def mask_holding_code(code: str, mode: str | None = None) -> str:
    """把持仓代码折为展示层显示值（提示词组装点等单点展示替换）。

    Args:
        code: 持仓代码原文。
        mode: 匿名化模式；None → 读取当前配置模式。

    Returns:
        折叠模式返回 :data:`CODE_DISPLAY_MASK`，否则原样返回；空值原样返回
    """
    if not code:
        return code
    if mode is None:
        mode = get_anonymization_mode()
    return CODE_DISPLAY_MASK if is_code_masked_mode(mode) else code


_MASKED_CODE_PATTERNS: dict[str, re.Pattern[str]] = {}


def mask_code_text(text: str | None, code_map: dict[str, str] | None) -> str | None:
    """在自由文本中按 {真码: 显示掩码} 做**边界安全**的精确键替换。

    代码是数字串，无条件子串替换会误伤金额与 JSON 数值（``1600519.0`` 内含
    ``600519``）。这里要求真码两侧都不是数字/小数点/冒号才认定它是独立代码：

      - ``<td>600519</td>``、``"code":"600519"``、``、600519、`` → 命中
      - ``1600519.0``、``600519.0``、``{"mv":600519}``、``12.600519%`` → 不命中

    Args:
        text: 待掩码文本（None/空串原样返回）。
        code_map: {真码: 显示掩码}，来自 :func:`build_code_display_map`。

    Returns:
        替换后的文本；无映射或无命中时原样返回
    """
    if not text or not code_map:
        return text
    for code, masked in code_map.items():
        if not code or code not in text:
            continue
        pattern = _MASKED_CODE_PATTERNS.get(code)
        if pattern is None:
            pattern = re.compile(rf"(?<![\d.:]){re.escape(code)}(?![\d.])")
            _MASKED_CODE_PATTERNS[code] = pattern
        text = pattern.sub(masked, text)
    return text


def mask_display_text(text: str, alias_map: dict[str, str]) -> str:
    """按映射替换文本中的真值（键按长度降序，先长后短避免子串截断）。

    用于约束块、新闻关键词标签、HTML 产物等自由文本面的匿名化清扫。
    """
    if not text or not alias_map:
        return text
    for real in sorted((k for k in alias_map if k), key=len, reverse=True):
        if real in text:
            text = text.replace(real, alias_map[real])
    return text


_CATEGORY_ROW_LABELS = {"基金": "基金汇总", "股票/其他": "股票汇总"}


def fold_details_summary(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """summary 模式：明细字典按大类折叠为同构聚合行（保持 list[dict] 形态）。

    聚合行携带与单条明细一致的键（缺失键补默认值），下游渲染、小计、
    LLM 提示词与图表数据集零改动消费；不携带 holding_days（观察期按
    「未知」处理，由行动建议层既有缺省防护承接）。
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    for d in details:
        buckets.setdefault(_categorize_detail(d), []).append(d)

    rows: list[dict[str, Any]] = []
    for cat, items in buckets.items():
        mv = sum(i.get("market_value", 0) or 0 for i in items)
        cost = sum(i.get("cost", 0) or 0 for i in items)
        profit = sum(i.get("profit", 0) or 0 for i in items)
        rows.append(
            {
                "name": _CATEGORY_ROW_LABELS.get(cat, f"{cat}汇总"),
                "code": "",
                "market_value": mv,
                "cost": cost,
                "profit": profit,
                "profit_rate": round(profit / cost * 100, 2) if cost else 0.0,
                "change_pct": 0.0,
                "nav_date": "",
                "source_api": "",
                "shares": sum(i.get("shares", 0) or 0 for i in items),
                "price": 0.0,
                "channel": "",
            }
        )
    return rows


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
    if mode not in _ANONYMIZATION_MODES:
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
