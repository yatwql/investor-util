"""HTML 报告章节可见性 + 目录分组导航子模块。

承载报告章节的两层可见性计算（board 层开关 × data 层数据就绪 × LLM 章级模块禁用）
与「基础信息/基金深度分析/行动建议/历史/LLM/附录」目录折叠导航构建。纯函数 + 模块常量，
无外部副作用。分组与 🧠 标记均自 core/registry.py 的章节注册表派生（NAV_GROUPS /
条目 nav_group / llm_supported 字段），本模块不自持第二份分组事实源。

由 `html_writer.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

from typing import Any

from src.python.core.registry import NAV_GROUPS, _REPORT_SECTION_DEFAULT

# ── HTML 目录分组导航（「基础信息/基金深度分析/行动建议/历史/LLM/附录」六组，导航折叠收尾） ──

# 导航分组视图（组名, 组 key），空组不渲染。渲染顺序不在这里承诺——
# `_build_section_nav_groups` 按报告号线性序扫描、同组连续段聚块，
# 保证目录展开序 == 正文线性序（号是唯一排序权威；分组只做聚合视图，不重排）。
# 组定义（key / label / 顺序）单源于 registry.NAV_GROUPS（Excel 页签配色同源），
# 此处仅投影为 (label, key) 元组视图供既有消费方使用。
_NAV_GROUP_LABELS: list[tuple[str, str]] = [(g["label"], g["key"]) for g in NAV_GROUPS]

# 章节 → 分组由注册表条目 nav_group 字段派生（未知 key 仅可能来自测试构造的最小
# 条目，回退「基础信息」组；注册表条目漏配由 test_registry 的 nav_group 完整性
# 用例拦截，不在渲染层静默容错）。默认注册序下每组成员的号段连续
# （basic=1..3、fund_deep=4..6、action=7、llm=8..12、history=13..16、
# appendix=17..19），一块即一组、展开即严格 1..N；用户跨组插号
# （report_section_order）时组在号序断点处拆块（同组可出现多块），
# 展开恒等于正文线性序，与正文（flex order = 报告号）逐位一致。

# LLM 支持章节标记（🧠）：由注册表条目 llm_supported 字段派生——新闻关联 +
# LLM 文本分析系列 + API 用量。与导航分组解耦——🧠 表示「该章节由 LLM 参与生成」，
# 导航分组只管目录位置（如 llm_usage 属「附录」组但仍带 🧠）；
# 由测试断言 llm 组 ⊆ 此集合防漂移。
_LLM_SUPPORTED_SECTIONS: frozenset[str] = frozenset(
    sec["key"] for sec in _REPORT_SECTION_DEFAULT if sec.get("llm_supported")
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
    holding_change_data: dict | None = None,  # data 层：持仓变动复盘 dict（None=开关关闭/无数据，整章隐藏）
    schedule_replay_data: dict | None = None,  # data 层：调仓纪律回放 dict（None=开关关闭/无数据，整章隐藏）
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
        # 持仓变动复盘：实验章无 board 层开关（恒 True），可见性由 data 层
        # data_flag（holding_change_data，seam 注入）控制——与 Excel 端同口径
        "holding_change": True,
        # 调仓纪律回放：同持仓变动复盘（实验章无 board 层开关，data 层控制）
        "schedule_replay": True,
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
        # 持仓变动复盘：实验开关 holding_change_review 经 seam 注入（缺席=None）→
        # 整章隐藏；注入但 available=False 时模板写占位（双端同口径）
        "holding_change_data": holding_change_data is not None,
        # 调仓纪律回放：实验开关 rebalance_schedule_replay 经 seam 注入（缺席=None）→
        # 整章隐藏；注入但 available=False 时模板写占位（双端同口径）
        "schedule_replay_data": schedule_replay_data is not None,
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

    按报告号**线性序扫描**，同组连续段聚为一块——默认注册序下每组号段连续、
    一块即一组，展开后严格 1..N 与正文逐位一致；用户配置 report_section_order
    跨组插号时（如附录章插入号段中间），组在号序断点处自然拆块、同组可出现
    多块，如实反映线性序，展开恒等于正文线性序（无跳号回跳，序号可配置兼容）。
    仅收录当前可见章节；空组保留在返回列表末尾，模板端跳过渲染（无 `<details>`）。
    返回 [{key, name, sections: [{key, number, name, llm_supported}, ...]}...]；
    llm_supported 标记该章节是否由 LLM 参与生成（🧠 标记，与导航分组解耦）；
    同 key 块可能多于一个（仅跨组交错场景），消费方聚合时勿假设 key 唯一。
    """
    labels = {gk: lb for lb, gk in _NAV_GROUP_LABELS}
    visible: list[dict] = []
    for sec in order:
        key = sec.get("key", "")
        if not section_visible(key):
            continue
        visible.append(
            {
                "key": key,
                "number": section_numbers.get(key, 0),
                "name": sec.get("name", key),
                "llm_supported": key in _LLM_SUPPORTED_SECTIONS,
                "group": sec.get("nav_group", "basic"),
            }
        )
    # 号是唯一排序权威：先按号排成正文线性序，再按同组连续段分块
    visible.sort(key=lambda s: s["number"])
    blocks: list[dict] = []
    for sec in visible:
        group_key = sec.pop("group")
        if blocks and blocks[-1]["key"] == group_key:
            blocks[-1]["sections"].append(sec)
        else:
            blocks.append({"key": group_key, "name": labels.get(group_key, group_key), "sections": [sec]})
    # 空组（无可见章节）排尾保留，模板端跳过渲染（无 <details>）
    appeared = {b["key"] for b in blocks}
    empty = [{"key": gk, "name": lb, "sections": []} for lb, gk in _NAV_GROUP_LABELS if gk not in appeared]
    return blocks + empty
