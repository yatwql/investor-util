"""Sheet 工厂 — 页签创建 + 可见性判定。

职责：根据注册表配置和运行时标志创建可见页签。
提取自 excel_generator.py 的 _should_create_sheet + _create_sheets。
"""

from __future__ import annotations

from typing import Any

from src.python.registry import set_sheet_title


def should_create_sheet(section: dict, enable_b_series: bool, include_news: bool, include_llm: bool) -> bool:
    """按 section.type 判断是否创建页签。

    新增模块只需在注册表标 type，无需修改此函数。
    """
    type_map = {
        "always":    True,              # summary, market_value, category, penetration, fund_performance
        "b_series":  enable_b_series,   # fund_manager, fund_overlap, fund_concentration, fund_style
        "news":      include_news,      # news_correlation, early_warning
        "llm":       include_llm,       # global_macro, expert_review, health_check, penetration_deep, llm_usage
    }
    return type_map.get(section.get("type", ""), False)


def create_sheets(
    wb: Any, section_order: list[dict],
    enable_b_series: bool = False, include_news: bool = False, include_llm: bool = False,
) -> dict[str, Any]:
    """按配置顺序创建所有可见页签，返回 {key: ws} 字典。"""
    sheets: dict[str, Any] = {}
    for sec in section_order:
        if not should_create_sheet(sec, enable_b_series, include_news, include_llm):
            continue
        ws = wb.create_sheet()
        set_sheet_title(ws, sec["key"], section_order)
        sheets[sec["key"]] = ws
    return sheets
