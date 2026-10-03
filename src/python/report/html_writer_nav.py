"""HTML 报告章节可见性 + 目录分组导航子模块。

承载报告章节的两层可见性计算（board 层开关 × data 层数据就绪 × LLM 章级模块禁用）
与「基础信息/基金深度分析/行动建议/历史/LLM/附录」目录折叠导航构建。纯函数 + 模块常量，
无外部副作用。

由 `html_writer.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

from typing import Any


# ── HTML 目录分组导航（「基础信息/基金深度分析/行动建议/历史/LLM」五组，导航折叠收尾） ──

# 分组展示顺序（组名, 组 key），空组不渲染
# 导航分组注册表（组名, 组 key）。渲染顺序不在这里承诺——
# `_build_section_nav_groups` 按组内最小报告号动态排序，保证目录展开序 == 正文线性序
# （号是唯一排序权威；分组只做聚合视图，不重排）。
_NAV_GROUP_LABELS: list[tuple[str, str]] = [
    ("基础信息", "basic"),
    ("基金深度分析", "fund_deep"),
    ("行动建议", "action"),
    ("历史", "history"),
    ("LLM", "llm"),
    ("附录", "appendix"),
]

# 章节 → 分组映射（语义分组；与报告模块注册表 key 一一对应，未知 key 回退「基础信息」组）。
# 默认注册序下每组成员的号段连续（basic=1..3、fund_deep=4..6、action=7、llm=8..12、
# history=13..14、appendix=15..17），目录组间按组内最小号动态排序后展开即严格 1..N，
# 与正文（flex order = 报告号）逐位一致、无跳号回跳。
_SECTION_NAV_GROUP_MAP: dict[str, str] = {
    # 基础信息：汇总/持仓明细与分类/穿透
    "summary": "basic",
    "holdings_detail": "basic",
    "penetration": "basic",
    # 基金深度分析：基金业绩 + 基金深度分析系列章节
    "fund_performance": "fund_deep",
    "position_structure": "fund_deep",
    "style_factor": "fund_deep",
    # 行动建议：再平衡信号/交易纪律/调仓建议/收益归因（决策建议，非风险章节）
    "action": "action",
    # 历史：组合历史走势与回撤 + 组合演进
    "portfolio_history_drawdown": "history",
    "portfolio_evolution": "history",
    # LLM：新闻关联 + LLM 文本分析系列（号段 8..12 连续）
    "news_correlation": "llm",
    "global_macro": "llm",
    "expert_review": "llm",
    "health_check": "llm",
    "penetration_deep": "llm",
    # 附录：收尾信息（数据源矩阵 / 持仓基本面附表 / LLM API 用量，号段尾部）
    "data_source_status": "appendix",
    "fundamental_snapshot": "appendix",
    "llm_usage": "appendix",
}

# LLM 支持章节标记（🧠）：新闻关联 + LLM 文本分析系列 + API 用量。
# 与导航分组解耦——🧠 表示「该章节由 LLM 参与生成」，导航分组只管目录位置
# （如 llm_usage 属「附录」组但仍带 🧠）；由测试断言 llm 组 ⊆ 此集合防漂移。
_LLM_SUPPORTED_SECTIONS: frozenset[str] = frozenset(
    {
        "news_correlation",
        "global_macro",
        "expert_review",
        "health_check",
        "penetration_deep",
        "llm_usage",
    }
)


def _compute_section_visibility(
    order: list[dict],
    manager_analysis: dict | None,
    overlap_matrix: dict | None,
    concentration_analysis: dict | None,
    style_analysis: dict | None,
    include_news: bool,
    llm_enabled_flag: bool,
    # ↓↓↓ board 层新增参数 ↓↓↓
    enable_news: bool = True,  # board 层：市场新闻是否开启（配置驱动，不是 include_news！）
    enable_fund_deep_analysis: bool = True,  # board 层：基金深度分析是否开启
    enable_history: bool = True,  # board 层：历史走势章节是否开启
    enable_portfolio_evolution: bool = True,  # board 层：组合演进章节是否开启
    enable_fundamental_snapshot: bool = False,  # board 层：持仓基本面章（两功能开关任一开启）
    enable_action: bool = False,  # board 层：行动建议章节是否开启（config 默认开）
    enable_llm: bool = True,  # board 层：LLM 分析章节是否开启
    llm_module_disabled: dict[str, bool] | None = None,  # 章级：enabled_llm 模块禁用的 LLM 分析章隐藏
    style_factor_data: dict | None = None,  # data 层：风格与因子 dict（None=无数据，章节隐藏）
    position_relationship_data: dict | None = None,  # data 层：持仓关系矩阵 dict（相关性区块数据源）
    evolution_data: dict | None = None,  # data 层：组合演进 dict（None=无数据，章节隐藏）
    financial_report_digest_data: dict | None = None,  # data 层：财报摘要 dict（None=无数据，章节隐藏）
    financial_indicator_data: dict | None = None,  # data 层：财务指标 dict（None=无数据，章节隐藏）
) -> tuple[dict[str, int], dict[str, bool], Any]:
    """计算报告模块序号 + 可见性字典 + 闭包函数。

    两层可见性模型 + 章级维度：
      board 层：用户配置的章节开关（enable_xxx）
      data 层：各子模块返回的数据可用状态
      章级：enabled_llm 逐模块禁用时，对应的 LLM 分析章（LLM_MODULE_GATED_SECTIONS）
            整章隐藏（目录/正文/连续重编号同步剔除），而非显示「待生成」占位

    返回的闭包不写入 _ENV.globals。
    """
    # board 层：内联 dict（与 Excel 端结构一致）
    board_flags: dict[str, bool] = {
        "always": True,
        "fund_deep_analysis": enable_fund_deep_analysis,
        "news": enable_news,  # ← 配置字段（不是 include_news/data 层）
        "history": enable_history,
        "evolution": enable_portfolio_evolution,  # ← board 层：组合演进
        "fundamental_snapshot": enable_fundamental_snapshot,  # ← board 层：持仓基本面章
        "action": enable_action,  # ← board 层：行动建议（config 默认开）
        "llm": enable_llm,  # ← board 层
    }
    # data 层：各模块数据就绪状态
    data_flags: dict[str, bool] = {
        "concentration_data": concentration_analysis is not None,
        "style_data": style_analysis is not None,
        "news_data_available": include_news,  # ← data 层（菜单类型+数据状态）
        "llm_data_available": llm_enabled_flag,  # ← data 层（LLM 生成成功？）
        # 风格与因子章可见性：风格表（渲染期派生）或因子数据（数据契约）任一就绪即可见；
        # 模板依据 available/status 在"完整内容/数据不足/数据源暂不可用"间切换（§1.4.5）
        "style_factor_data": style_factor_data is not None or style_analysis is not None,
        # 持仓关系矩阵 = 重合度区块（render 时计算）∪ 相关性区块（数据契约 数据源）：
        # 任一区块有数据即章节可见，区块各自独立降级（§1.4.5）
        "position_relationship_data": overlap_matrix is not None or position_relationship_data is not None,
        # evolution_data 同上：始终由编排层计算注入（非 None）→ 章节可见，
        # available=False 时模板写占位文本（快照不足，§1.4.5）
        "evolution_data": evolution_data is not None,
        "financial_report_digest_data": financial_report_digest_data is not None,
        "financial_indicator_data": financial_indicator_data is not None,
    }

    # 两层合并 + 章级：section_visible = board_ok AND data_ok AND module_ok
    from src.python.core.registry import LLM_MODULE_GATED_SECTIONS

    section_visible_dict: dict[str, bool] = {}
    for sec in order:
        board_ok = board_flags.get(sec.get("type", ""), True)
        if not board_ok:
            section_visible_dict[sec["key"]] = False
            continue
        if (
            llm_module_disabled
            and sec["key"] in LLM_MODULE_GATED_SECTIONS
            and llm_module_disabled.get(sec["key"], False)
        ):
            # 章级：enabled_llm.<key> = false → 该 LLM 分析章整章隐藏
            section_visible_dict[sec["key"]] = False
            continue
        flag_any = sec.get("data_flag_any")
        flag_name = sec.get("data_flag")
        if flag_any:
            # 多契约 OR（与 Excel 侧同口径，悲观判定）
            section_visible_dict[sec["key"]] = any(data_flags.get(name, False) for name in flag_any)
        elif not flag_name:
            section_visible_dict[sec["key"]] = True
        else:
            section_visible_dict[sec["key"]] = data_flags.get(flag_name, False)

    # 连续重新编号：基于可见模块分配连续序号，llm_usage 强制末位
    visible_list = [sec for sec in order if section_visible_dict.get(sec["key"], False)]
    llm_sec = [s for s in visible_list if s["key"] == "llm_usage"]
    other_secs = [s for s in visible_list if s["key"] != "llm_usage"]
    ordered_visible = other_secs + llm_sec
    visible_numbers = {sec["key"]: idx for idx, sec in enumerate(ordered_visible, start=1)}

    # 创建渲染期 section_visible 闭包（不写入 _ENV.globals）
    def _sv_fn(key: str, _d: dict[str, bool] = section_visible_dict) -> bool:
        return bool(_d.get(key, False))

    return visible_numbers, section_visible_dict, _sv_fn


def _build_section_nav_groups(
    order: list[dict],
    section_visible,
    section_numbers: dict,
) -> list[dict]:
    """构建 HTML 目录分组导航数据（分组聚合视图，报告号是唯一排序权威）。

    仅收录当前可见章节；组内按报告号升序，**组间按组内最小报告号动态排序**——
    默认注册序下展开后严格跟随正文线性序（1..N），分组只聚合不重排，
    不产生「组内尾号 → 下组头号」的跳号回跳；用户配置 report_section_order
    后组序随之自适应（C7 序号可配置兼容）。
    返回 [{key, name, sections: [{key, number, name, llm_supported}, ...]}...]；
    llm_supported 标记该章节是否由 LLM 参与生成（🧠 标记，与导航分组解耦）；
    空组（无可见章节）保留在返回列表末尾，模板端跳过渲染（无 `<details>`）。
    """
    groups: dict[str, list[dict]] = {gk: [] for _, gk in _NAV_GROUP_LABELS}
    for sec in order:
        key = sec.get("key", "")
        if not section_visible(key):
            continue
        group_key = _SECTION_NAV_GROUP_MAP.get(key, "basic")
        groups.setdefault(group_key, []).append(
            {
                "key": key,
                "number": section_numbers.get(key, 0),
                "name": sec.get("name", key),
                "llm_supported": key in _LLM_SUPPORTED_SECTIONS,
            }
        )
    built: list[dict] = []
    for label, group_key in _NAV_GROUP_LABELS:
        sections = sorted(groups.get(group_key, []), key=lambda s: s["number"])
        built.append({"key": group_key, "name": label, "sections": sections})
    # 组序动态：非空组按组内最小报告号升序（与正文序一致），空组无锚定位、排尾保留
    nonempty = [g for g in built if g["sections"]]
    empty = [g for g in built if not g["sections"]]
    nonempty.sort(key=lambda g: min(s["number"] for s in g["sections"]))
    return nonempty + empty
