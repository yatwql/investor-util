"""Jinja2 模板环境 — _ENV 实例 + 自定义过滤器 + section_visible fallback。"""

from __future__ import annotations

import os
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.python.core.code_utils import is_qdii_extended

# ── 路径 & Jinja2 环境 ─────────────────────────────────────

_TEMPLATE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tmpl"))
_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)


# ── Jinja2 自定义过滤器 ─────────────────────────────────────


def _jinja_money(value: Any) -> str:
    """格式化金额：1,234.56"""
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return "--"


def _jinja_pct(value: Any) -> str:
    """格式化比率 (0.15 → +15.00%)"""
    try:
        v = float(value)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v * 100:.2f}%"
    except (ValueError, TypeError):
        return "--"


def _jinja_price(value: Any) -> str:
    """格式化价格：四位小数"""
    try:
        return f"{float(value):.4f}"
    except (ValueError, TypeError):
        return "--"


def _jinja_shares(value: Any) -> str:
    """格式化份额：两位小数"""
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return "--"


def _jinja_change(value: Any) -> str:
    """格式化涨跌幅：百分数"""
    try:
        v = float(value)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.2f}%"
    except (ValueError, TypeError):
        return "--"


def _jinja_price_type_color(price_type: str, name: str = "") -> str:
    """取价方式颜色：蓝色代表数据时效性高/可靠。

    着色规则同 Excel 端 _apply_price_type_colors：
      - "场内收盘价(T)"、"场内午市收盘(T)"、"官方净值(T)" → var(--rating-stable)
      - QDII 基金 "官方净值(T-1)" → var(--rating-stable)
    返回 CSS 变量表达式（暗色模式（主题切换）），模板中直接用于 style="color: ..."。
    """
    if price_type in ("场内收盘价(T)", "场内午市收盘(T)", "官方净值(T)"):
        return "var(--rating-stable)"
    if price_type == "官方净值(T-1)" and name and is_qdii_extended(name):
        return "var(--rating-stable)"
    return ""


def _jinja_profit_color(value: Any) -> str:
    """盈亏颜色：盈利红 var(--profit)，亏损绿 var(--loss)（跟随主题）。"""
    try:
        v = float(value)
        if v > 0:
            return "var(--profit)"
        elif v < 0:
            return "var(--loss)"
        return ""
    except (ValueError, TypeError):
        return ""


def _jinja_thousands(value: Any) -> str:
    """格式化整数：1,234"""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def _jinja_sentiment_colorize(text: str) -> str:
    """将 [利好]/[利空] 标记着色为 HTML 内联样式，其余文本保持原样。

    [利好] → 红 var(--profit)，[利空] → 绿 var(--loss)（跟随主题）。
    返回的 HTML 已在过滤器层处理，模板中使用 ``| safe`` 避免二次转义。
    """
    if not text:
        return text
    text = text.replace("[利好]", '<span style="color:var(--profit);font-weight:bold">[利好]</span>')
    text = text.replace("[利空]", '<span style="color:var(--loss);font-weight:bold">[利空]</span>')
    return text


# ── 注册过滤器 & 全局函数 ────────────────────────────────────

_ENV.filters["money"] = _jinja_money
_ENV.filters["pct"] = _jinja_pct
_ENV.filters["price"] = _jinja_price
_ENV.filters["shares"] = _jinja_shares
_ENV.filters["change"] = _jinja_change
_ENV.filters["profit_color"] = _jinja_profit_color
_ENV.filters["price_type_color"] = _jinja_price_type_color
_ENV.filters["thousands"] = _jinja_thousands
_ENV.filters["sentiment_colorize"] = _jinja_sentiment_colorize

_ENV.globals["section_visible"] = lambda key: False  # fail-closed 默认值，生产环境由 context 变量覆盖
