"""Sheet 工厂 — 页签创建 + 可见性判定。

职责：根据注册表配置和运行时标志创建可见页签。
"""

from __future__ import annotations

from typing import Any


def should_create_sheet(section: dict, data_availability: dict[str, bool] | None = None) -> bool:
    """纯 data 层：按注册表的 data_flag 判断模块数据是否就绪。

    无 data_flag 的模块（always、history）始终创建；data_flag
    未出现在 data_availability 中时视为已就绪（如基金深度分析的
    数据在页签创建后才写入，由下游函数自行兜底）。
    """
    flag_name = section.get("data_flag")
    if not flag_name:
        return True
    avail = data_availability or {}
    return avail.get(flag_name, True)


def create_sheets(
    wb: Any,
    section_order: list[dict],
    enable_fund_deep_analysis: bool = False,
    enable_news: bool = True,  # board 层
    enable_history: bool = True,  # board 层
    enable_portfolio_evolution: bool = True,  # board 层：组合演进
    enable_action: bool = False,  # board 层：行动建议（config 默认开）
    enable_llm: bool = True,  # board 层
    data_availability: dict[str, bool] | None = None,  # data 层
) -> dict[str, Any]:
    """按配置顺序创建所有可见页签，返回 {key: ws} 字典。

    两层可见性模型：
      board 层：用户配置的章节开关（enable_xxx）
      data 层：运行时数据可用性标志（data_availability dict）

    Args:
        wb: openpyxl Workbook
        section_order: 注册表模块顺序列表
        enable_fund_deep_analysis: board 层 — 基金深度分析是否开启（配置驱动）
        enable_news: board 层 — 市场新闻是否开启（配置驱动）
        enable_history: board 层 — 历史走势章节是否开启
        enable_action: board 层 — 行动建议章节是否开启（config 默认开）
        enable_llm: board 层 — LLM 分析章节是否开启
        data_availability: data 层 — 各模块 data_flag 的就绪状态
    """
    # 内联 board_flags dict（与 HTML 端结构一致，行为一致性由集成测试保证）
    board_flags = {
        "always": True,
        "fund_deep_analysis": enable_fund_deep_analysis,
        "news": enable_news,  # ← 配置驱动的 board 层值
        "history": enable_history,
        "evolution": enable_portfolio_evolution,
        "action": enable_action,
        "llm": enable_llm,
    }

    # should_create_sheet 查 data_availability dict
    sheets: dict[str, Any] = {}
    have_llm_usage = False
    llm_usage_name = ""
    visible_count = 0
    _data_avail = data_availability or {}

    for sec in section_order:
        # 第 1 层：board 层预过滤
        if not board_flags.get(sec.get("type", ""), True):
            continue

        # 第 2 层：data 层判断（查注册表的 data_flag）
        if not should_create_sheet(sec, _data_avail):
            continue

        # llm_usage 强制末位，先标记稍后创建
        if sec["key"] == "llm_usage":
            have_llm_usage = True
            llm_usage_name = sec["name"]
            continue

        visible_count += 1
        ws = wb.create_sheet()
        ws.title = f"{visible_count}.{sec['name']}"
        sheets[sec["key"]] = ws

    # llm_usage 始终在最后
    if have_llm_usage:
        visible_count += 1
        ws = wb.create_sheet()
        ws.title = f"{visible_count}.{llm_usage_name}"
        sheets["llm_usage"] = ws

    return sheets
