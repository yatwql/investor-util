"""报告章节注册表 — 章节目录序、导航分组与页签名称派生。

（自 core/registry.py 按注册职责域下沉；门面 ``core/registry.py`` 原样再导出，
导入面与测试 patch 面不变。域内互调在本模块内解析。）

新增章节在本文件登记（key/name/number/type/data_flag/nav_group），
HTML 目录折叠导航与 Excel 页签配色两端自动同步（防漂移测试双向断言）。
"""

from __future__ import annotations

__all__ = [
    "NAV_GROUPS",
    "_LLM_SHEET_NAME_KEYS",
    "_REPORT_SECTION_DEFAULT",
    "_REPORT_SHEET_NAMES",
    "get_report_section_keys",
    "get_report_section_number",
    "get_report_section_order",
    "get_report_sheet_name",
]

# ── 报告模块注册表（序号可配置） ──────────────────────────────
# 条目字段：key / name / number / type / data_flag（单契约可见性旗标）/
# nav_group（目录导航分组，取值 ∈ NAV_GROUPS 键集：HTML 目录折叠导航与
# Excel 页签配色的分组同源，新增章节必须声明）；可选 llm_supported
# （🧠 标记：该章由 LLM 参与生成，缺省 False，与导航分组解耦）；
# 可选 data_flag_any（多契约 OR：任一契约就绪则该条目可见，供章节合并后一条目承载
# 多个区块使用；OR 采用悲观判定——未登记视为未就绪，避免契约缺省时显示空章节。
# 未声明 data_flag_any 时行为与单契约判定完全一致）。

# ── 目录导航分组注册表（六组） ────────────────────────────────
# 章节条目经 nav_group 字段挂到组；列表顺序 = 目录分组展示顺序。
# HTML 端目录折叠导航（core 消费方：report/html_writer_nav.py）与 Excel 端
# 页签 tabColor 配色（report/excel_*）同源于此——新增分组或章节在此登记，
# 两端自动同步（防漂移测试双向断言键集）。
NAV_GROUPS: list[dict] = [
    {"key": "basic", "label": "基础信息"},
    {"key": "fund_deep", "label": "基金深度分析"},
    {"key": "action", "label": "行动建议"},
    {"key": "history", "label": "历史"},
    {"key": "llm", "label": "LLM"},
    {"key": "appendix", "label": "附录"},
]


_REPORT_SECTION_DEFAULT: list[dict] = [
    # ── always 类型（始终显示，无 data_flag 依赖） ──
    {"key": "summary", "name": "投资分析汇总", "number": 1, "type": "always", "data_flag": None, "nav_group": "basic"},
    {
        "key": "holdings_detail",
        "name": "持仓明细与分类",
        "number": 2,
        "type": "always",
        "nav_group": "basic",
        "data_flag": None,
    },
    {
        "key": "penetration",
        "name": "资产穿透TOP10",
        "number": 3,
        "type": "always",
        "data_flag": None,
        "nav_group": "basic",
    },
    {
        "key": "fund_performance",
        "name": "基金业绩分析",
        "number": 4,
        "type": "always",
        "nav_group": "fund_deep",
        "data_flag": None,
    },
    # ── 基金深度分析 类型（有数据才显示） ──
    {
        "key": "position_structure",
        "name": "持仓结构与集中度",
        "number": 5,
        "type": "fund_deep_analysis",
        "nav_group": "fund_deep",
        "data_flag": None,
        "data_flag_any": ("position_relationship_data", "concentration_data"),
    },
    # ── 风格与因子分析（「基金风格表 + 风格因子回归」两区块 + 行业 Beta 子表） ──
    # 区块一：基金风格表（渲染期派生）· 区块二：风格因子回归（style_factor_data 子键）
    # · 区块三：行业 Beta 子表（style_factor_data.industry_beta，功能开关 industry_beta 默认关）
    # · 区块四：因子目录（factor_catalog_data 主键，实验开关 factor_catalog 默认关）
    {
        "key": "style_factor",
        "name": "风格与因子分析",
        "number": 6,
        "type": "fund_deep_analysis",
        "nav_group": "fund_deep",
        "data_flag": "style_factor_data",
    },
    # ── action 类型（独立顶层开关 enable_action 控制，默认开，菜单 P 可切换） ──
    # 行动建议：再平衡信号 + 交易纪律 + 调仓建议 + 收益归因（纯算法，basic/both/full 均可见）
    # 出厂序号 7，与仓库 config.json 的 report_section_order 取值相同——该配置清空为 {}
    # 时即回到本默认顺序，故两者必须同序，改动其一须同步另一处
    {
        "key": "action",
        "name": "行动建议",
        "number": 7,
        "type": "action",
        "nav_group": "action",
        "data_flag": None,
    },
    # ── news 类型（需启用新闻功能） ──
    {
        "key": "news_correlation",
        "name": "财经新闻热点与持仓关联分析",
        "number": 8,
        "type": "news",
        "nav_group": "llm",
        "llm_supported": True,
        "data_flag": "news_data_available",
    },
    # ── llm 类型（需启用 LLM 功能） ──
    {
        "key": "global_macro",
        "name": "全球政经局势",
        "number": 9,
        "type": "llm",
        "nav_group": "llm",
        "llm_supported": True,
        "data_flag": "llm_data_available",
    },
    {
        "key": "expert_review",
        "name": "智囊团深度复盘",
        "number": 10,
        "type": "llm",
        "nav_group": "llm",
        "llm_supported": True,
        "data_flag": "llm_data_available",
    },
    {
        "key": "health_check",
        "name": "持仓体检报告",
        "number": 11,
        "type": "llm",
        "nav_group": "llm",
        "llm_supported": True,
        "data_flag": "llm_data_available",
    },
    {
        "key": "penetration_deep",
        "name": "穿透深度分析",
        "number": 12,
        "type": "llm",
        "nav_group": "llm",
        "llm_supported": True,
        "data_flag": "llm_data_available",
    },
    # ── history 类型（始终显示，数据不可用时显示占位文本） ──
    # 组合历史走势与回撤：一章分「走势表 + 回撤矩阵」两区块 + 危机区间标注（2015/2018/2020/2022）
    {
        "key": "portfolio_history_drawdown",
        "name": "组合历史走势与回撤",
        "number": 13,
        "type": "history",
        "nav_group": "history",
        "data_flag": None,
    },
    # ── evolution 类型（独立开关 enable_portfolio_evolution 控制） ──
    # 组合演进：聚合本地多期快照，data_flag 控制章节可见性，
    # available=False 时模板/页签写占位（与持仓关系矩阵的降级模式一致）
    {
        "key": "portfolio_evolution",
        "name": "组合演进",
        "number": 14,
        "type": "evolution",
        "nav_group": "history",
        "data_flag": "evolution_data",
    },
    # ── holding_change 类型（报告章节与增强开关 holding_change_review 控制，经实验挂载点注入） ──
    # 持仓变动复盘：快照差分事件级操作侧复盘（事件清单/频率/结构演变/意图对账 +
    # LLM 归因块）。data_flag 控制双端可见性：开关关闭（默认）时
    # pipeline_data 键缺席 → 标志 False → 整章隐藏，两条输出路径保持既有输出；
    # 开关注入但数据不足时双端写占位
    {
        "key": "holding_change",
        "name": "持仓变动复盘",
        "number": 15,
        "type": "holding_change",
        "nav_group": "history",
        "data_flag": "holding_change_data",
    },
    # 事件窗量化对照：并入「财经新闻热点与持仓关联分析」章内区块（partial 在新闻章内以
    # block-title 渲染，可见性由契约 event_impact_view 决定），不占独立注册表条目、不消耗
    # 连续编号；报告章节与增强开关 event_window_impact 经实验挂载点注入 pipeline_data["event_impact_data"]。
    # ── schedule_replay 类型（实验开关 rebalance_schedule_replay 控制，经实验挂载点注入）：调仓纪律回放——月度定期/阈值偏离纪律多期回放 vs 买入持有；data_flag 控制双端可见性（关态键缺席隐藏 / 开启但数据不足双端占位） ──
    {
        "key": "schedule_replay",
        "name": "调仓纪律回放",
        "number": 16,
        "type": "schedule_replay",
        "nav_group": "history",
        "data_flag": "schedule_replay_data",
    },
    # ── always 类型（始终显示） ──
    {
        "key": "data_source_status",
        "name": "数据源可用性矩阵",
        "number": 17,
        "type": "always",
        "nav_group": "appendix",
        "data_flag": None,
    },
    # ── fundamental_snapshot 类型（两功能开关各控一块，默认关）──
    # 持仓基本面 = 财务指标（financial_indicator）+ 持仓个股财报摘要（financial_report_digest）；
    # 两契约 OR 决定章节可见性（任一块就绪即显示，块级开关各控各的渲染）
    {
        "key": "fundamental_snapshot",
        "name": "持仓基本面",
        "number": 18,
        "type": "fundamental_snapshot",
        "nav_group": "appendix",
        "data_flag": None,
        "data_flag_any": ("financial_indicator_data", "financial_report_digest_data"),
    },
    # ── llm_usage 强制末位（技术约束） ──
    {
        "key": "llm_usage",
        "name": "LLM API 用量",
        "number": 19,
        "type": "llm",
        "nav_group": "appendix",
        "llm_supported": True,
        "data_flag": "llm_data_available",
    },
]


# ── 非 LLM 报表页签名称（章节注册表派生视图） ──────────────
# 页签中文标题与章节显示名同源（单一真值 = 条目 name），改名只需改注册表；
# LLM 模块页签（global_macro/expert_review/health_check/penetration_deep）
# 以及 news_correlation 的页签标题走 get_llm_module_name() 路径，
# 差集在此显式声明——注册表新增章须归入其一（派生关系由测试锁定）。
_LLM_SHEET_NAME_KEYS: frozenset[str] = frozenset(
    {"global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation"}
)

_REPORT_SHEET_NAMES: dict[str, str] = {
    sec["key"]: sec["name"] for sec in _REPORT_SECTION_DEFAULT if sec["key"] not in _LLM_SHEET_NAME_KEYS
}


def get_report_sheet_name(sheet_key: str) -> str:
    """根据 sheet 键名返回非 LLM 报表页签的中文标题。

    Args:
        sheet_key: 页签键名，如 "summary"、"holdings_detail"

    Returns:
        中文标题；未找到时返回 sheet_key 本身
    """
    return _REPORT_SHEET_NAMES.get(sheet_key, sheet_key)


def get_report_section_keys() -> set[str]:
    """返回所有有效的报告模块标识集合，供 config 校验使用。

    Returns:
        {"summary", "holdings_detail", ..., "portfolio_history_drawdown"}
    """
    return {sec["key"] for sec in _REPORT_SECTION_DEFAULT}


def get_report_section_number(key: str, config: dict | None = None) -> int:
    """根据模块键名返回当前配置下的序号。

    优先读取用户配置（config.json 的 report_section_order），
    未配置时返回默认注册表中的序号。

    Args:
        key: 模块键名，如 "position_structure"
        config: 完整配置字典，为 None 时使用默认注册表序号

    Returns:
        序号整数，未找到时返回 0
    """
    order = get_report_section_order(config)
    for sec in order:
        if sec["key"] == key:
            return sec["number"]
    return 0


def get_report_section_order(config: dict | None = None) -> list[dict]:
    """合并用户配置与默认顺序，返回排序后的报告模块列表。

    处理逻辑：
      1. 无配置或配置为空 → 返回完整 19 项默认顺序（与当前硬编码一致）
      2. 用户配置的模块使用配置序号，其余保持默认序号
      3. 已配置模块排在前（按序号升序），未配置模块按默认顺序排后
      4. llm_usage 始终固定在最后一位

    Args:
        config: 完整配置字典（含 report_section_order 键），
                为 None 时返回 _REPORT_SECTION_DEFAULT 深拷贝

    Returns:
        [{key, name, number, type, data_flag}, ...] 共 19 项
    """
    if config is None:
        return [dict(sec) for sec in _REPORT_SECTION_DEFAULT]

    user_order = config.get("report_section_order", {})
    if not user_order or not isinstance(user_order, dict):
        return [dict(sec) for sec in _REPORT_SECTION_DEFAULT]

    configured_keys = set(user_order.keys())

    # 分离已配置和未配置模块
    configured: list[dict] = []
    unconfigured: list[dict] = []

    for sec in _REPORT_SECTION_DEFAULT:
        entry = dict(sec)
        if entry["key"] in configured_keys and entry["key"] != "llm_usage":
            try:
                entry["number"] = int(user_order[entry["key"]])
            except (ValueError, TypeError):
                entry["number"] = sec["number"]  # 配置无效时回退默认
            configured.append(entry)
        else:
            unconfigured.append(entry)

    # 已配置模块按序号升序
    configured.sort(key=lambda x: x["number"])

    # 合并：已配置在前，未配置在后（保持默认相对顺序）
    result = configured + unconfigured

    # llm_usage 强制末位（先查找再移除，避免迭代中删除）
    llm_entry: dict | None = None
    for sec in result:
        if sec["key"] == "llm_usage":
            llm_entry = sec
            break
    if llm_entry:
        result.remove(llm_entry)
        result.append(llm_entry)

    return result
