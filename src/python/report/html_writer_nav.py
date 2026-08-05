"""HTML 报告章节可见性 + 目录分组导航子模块。

自 `html_writer.py` 拆出（超限文件拆分重构），承载报告章节的两层可见性
计算（board 层开关 × data 层数据就绪）与「基础/基金深度/风险/历史/LLM」
五组目录折叠导航构建。纯函数 + 模块常量，无外部副作用。

被 `html_writer.py`（门面）re-export，保持 `from html_writer import ...` 引用不变。
"""

from __future__ import annotations

from typing import Any


# ── HTML 目录分组导航（「基础/基金深度/风险/历史/LLM」五组，导航折叠收尾） ──

# 分组展示顺序（组名, 组 key），空组不渲染
_NAV_GROUP_LABELS: list[tuple[str, str]] = [
    ("基础", "basic"),
    ("基金深度", "fund_deep"),
    ("风险", "risk"),
    ("历史", "history"),
    ("LLM", "llm"),
]

# 章节 → 分组映射（语义分组；与报告模块注册表 key 一一对应，未知 key 回退「基础」组）
_SECTION_NAV_GROUP_MAP: dict[str, str] = {
    # 基础：汇总/明细/分类/穿透/数据源可用性
    "summary": "basic",
    "market_value": "basic",
    "category": "basic",
    "penetration": "basic",
    "data_source_status": "basic",
    # 基金深度：基金业绩 + 基金深度分析系列章节
    "fund_performance": "fund_deep",
    "fund_manager": "fund_deep",
    "position_relationship": "fund_deep",
    "fund_concentration": "fund_deep",
    "style_factor": "fund_deep",
    # 风险：行动建议（再平衡信号/交易纪律/调仓建议/收益归因）
    "action": "risk",
    # 历史：组合历史走势与回撤 + 组合演进
    "portfolio_history_drawdown": "history",
    "portfolio_evolution": "history",
    # LLM：新闻关联 + LLM 文本分析系列 + API 用量
    "news_correlation": "llm",
    "global_macro": "llm",
    "expert_review": "llm",
    "health_check": "llm",
    "penetration_deep": "llm",
    "llm_usage": "llm",
}

# LLM 支持章节：与「LLM」导航组同源派生（新闻关联 + LLM 文本分析系列 + API 用量），
# 单一数据源防漂移；目录/横向导航据此橙色加粗 + 🧠 图标标记。
_LLM_SUPPORTED_SECTIONS: frozenset[str] = frozenset(
    key for key, group in _SECTION_NAV_GROUP_MAP.items() if group == "llm"
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
    enable_action: bool = False,  # board 层：行动建议章节是否开启（默认关）
    enable_llm: bool = True,  # board 层：LLM 分析章节是否开启
    style_factor_data: dict | None = None,  # data 层：风格与因子 dict（None=无数据，章节隐藏）
    position_relationship_data: dict | None = None,  # data 层：持仓关系矩阵 dict（相关性区块数据源）
    evolution_data: dict | None = None,  # data 层：组合演进 dict（None=无数据，章节隐藏）
) -> tuple[dict[str, int], dict[str, bool], Any]:
    """计算报告模块序号 + 可见性字典 + 闭包函数。

    两层可见性模型：
      board 层：用户配置的章节开关（enable_xxx）
      data 层：各子模块返回的数据可用状态

    返回的闭包不写入 _ENV.globals。
    """
    # board 层：内联 dict（与 Excel 端结构一致）
    board_flags: dict[str, bool] = {
        "always": True,
        "fund_deep_analysis": enable_fund_deep_analysis,
        "news": enable_news,  # ← 配置字段（不是 include_news/data 层）
        "history": enable_history,
        "evolution": enable_portfolio_evolution,  # ← board 层：组合演进
        "action": enable_action,  # ← board 层：行动建议（默认关）
        "llm": enable_llm,  # ← board 层
    }
    # data 层：各模块数据就绪状态
    data_flags: dict[str, bool] = {
        "manager_data": manager_analysis is not None,
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
    }

    # 两层合并：section_visible = board_ok AND data_ok
    section_visible_dict: dict[str, bool] = {}
    for sec in order:
        board_ok = board_flags.get(sec.get("type", ""), True)
        if not board_ok:
            section_visible_dict[sec["key"]] = False
            continue
        flag_name = sec.get("data_flag")
        if not flag_name:
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
    _sv_fn = lambda key, _d=section_visible_dict: bool(_d.get(key, False))
    return visible_numbers, section_visible_dict, _sv_fn


def _build_section_nav_groups(
    order: list[dict],
    section_visible,
    section_numbers: dict,
) -> list[dict]:
    """按「基础/基金深度/风险/历史/LLM」五组构建 HTML 目录分组导航数据。

    仅收录当前可见章节；组序固定为五组顺序，组内按报告序号升序。
    返回 [{key, name, sections: [{key, number, name, llm_supported}, ...]}, ...]；
    llm_supported 标记该章节是否有 LLM 支持（与 LLM 导航组同源），模板据此加橙色/图标；
    空组（无可见章节）保留在返回列表中，模板端跳过渲染（无 `<details>`）。
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
    result: list[dict] = []
    for label, group_key in _NAV_GROUP_LABELS:
        sections = sorted(groups.get(group_key, []), key=lambda s: s["number"])
        result.append({"key": group_key, "name": label, "sections": sections})
    return result
