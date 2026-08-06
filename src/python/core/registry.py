"""中央注册表 — 统一管理所有数据模块的配置键名、缓存前缀、默认 TTL。

设计目标：
  - 一处注册，全局生效
  - 新增模块只需修改 registry.py，其他模块自动同步
  - 消除 config.py / cache.py / constants.py 三处分散维护的遗漏风险

用法：
  >>> from src.python.core.registry import get_cache_ttl_defaults
  >>> ttl_map = get_cache_ttl_defaults()
  >>> ttl_map["price"]
  86400
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.python.core.constants import CACHE_DAILY, CACHE_MONTHLY, CACHE_TWO_WEEKS, CACHE_WEEKLY

logger = logging.getLogger("invest")


# ── 模块定义 ────────────────────────────────────────────────


@dataclass(frozen=True)
class DataModuleDef:
    """数据模块注册表条目。

    每个条目描述一个数据模块的完整配置，包括缓存行为、TTL、以及
    （对于 LLM 模块）settings 键名生成规则。

    Attributes:
        name: 人类可读的中文名称。
        data_type: 数据类型键，用于 TTL 查找和类型路由。
        cache_prefixes: 缓存文件名的前缀元组，
            用于 cleanup_expired() 从文件名推断数据类型。
        exact_cache_keys: 精确缓存键名（非前缀匹配），
            用于固定键名的特殊缓存文件。
        cache_ttl: 默认缓存过期时间（秒）。
        settings_suffix: LLM settings 键的后缀，
            设置后自动生成该模块的所有 llm_settings.json 合法键名。
            None 表示非 LLM 模块。
    """

    name: str
    data_type: str
    cache_prefixes: tuple[str, ...] = ()
    exact_cache_keys: tuple[str, ...] = ()
    cache_ttl: float = CACHE_DAILY
    settings_suffix: str | None = None
    cache_groups: tuple[str, ...] = ()

    @property
    def is_llm(self) -> bool:
        """是否为 LLM 模块（即有 settings 键名）。"""
        return self.settings_suffix is not None

    def llm_settings_keys(self) -> set[str]:
        """返回该模块的所有 llm_settings.json 合法键名。"""
        if not self.is_llm:
            return set()
        suffix = self.settings_suffix
        keys: set[str] = {
            f"model_{suffix}",
            f"temperature_{suffix}",
            f"timeout_{suffix}",
            f"cache_enabled_{suffix}",
            f"max_tokens_{suffix}",
            f"system_prompt_{suffix}",
            f"thinking_enabled_{suffix}",
            f"thinking_budget_{suffix}",
            f"reasoning_effort_{suffix}",
        }
        # output_brief 在所有 LLM 模块中生成，但 news_correlation 除外
        if suffix != "news_correlation":
            keys.add(f"output_brief_{suffix}")
        return keys


# ── 中央注册表 ──────────────────────────────────────────────
# 新增数据模块只需在此添加一行，三种派生结构自动同步。
# 注意：
#   1. cache_prefixes 中长前缀需排在短前缀之前
#      否则短前缀可能先匹配（如 "llm_" 会误匹配 "llm_global_macro"）
#      但此处所有 LLM 模块均使用完整长前缀，无歧义
#   2. exact_cache_keys 对应无前缀的精确缓存键名
#   3. settings_suffix 设置后自动加入 llm_settings 键名校验

_MODULE_REGISTRY: tuple[DataModuleDef, ...] = (
    # ── 基础行情（preload 组：换持仓后重取）──
    DataModuleDef("股票价格", "price", cache_prefixes=("price_",), cache_ttl=CACHE_DAILY, cache_groups=("preload",)),
    DataModuleDef("市场指数", "index", cache_prefixes=("index_",), cache_ttl=CACHE_DAILY, cache_groups=("preload",)),
    # ── 基金数据（refresh 组：主动刷新缓存）──
    DataModuleDef(
        "基金业绩排名", "rank", cache_prefixes=("fund_perf_",), cache_ttl=CACHE_DAILY, cache_groups=("refresh",)
    ),
    DataModuleDef(
        "基金持仓", "hold", cache_prefixes=("fund_hold_",), cache_ttl=CACHE_WEEKLY, cache_groups=("refresh",)
    ),
    # ── 行业分类（refresh 组）──
    DataModuleDef(
        "行业分类", "industry", cache_prefixes=("industry_",), cache_ttl=CACHE_TWO_WEEKS, cache_groups=("refresh",)
    ),
    # ── 新闻（refresh 组）──
    DataModuleDef("新闻聚合", "news", cache_prefixes=("news_",), cache_ttl=900, cache_groups=("refresh",)),
    # ── LLM 智能分析模块 ──
    DataModuleDef(
        "全球政经局势",
        "llm_global_macro",
        cache_prefixes=("llm_global_macro_",),
        cache_ttl=86400,
        settings_suffix="global_macro",
        cache_groups=("preload",),
    ),
    DataModuleDef(
        "智囊团深度复盘",
        "llm_expert_review",
        cache_prefixes=("llm_expert_review_",),
        cache_ttl=7200,
        settings_suffix="expert_review",
        cache_groups=("preload",),
    ),
    DataModuleDef(
        "财经新闻热点与持仓关联分析",
        "llm_news_correlation",
        cache_prefixes=("llm_news_item_",),
        cache_ttl=3600,
        settings_suffix="news_correlation",
        cache_groups=("refresh",),
    ),
    DataModuleDef(
        "持仓体检报告",
        "llm_health_check",
        cache_prefixes=("llm_health_check_",),
        cache_ttl=86400,
        settings_suffix="health_check",
        cache_groups=("preload",),
    ),
    DataModuleDef(
        "穿透深度分析",
        "llm_penetration_deep",
        cache_prefixes=("llm_penetration_deep_",),
        cache_ttl=86400,
        settings_suffix="penetration_deep",
        cache_groups=("preload",),
    ),
    # ── 辩论模式（preload 组，实验功能）──
    DataModuleDef(
        "辩论白脸",
        "llm_debate_pro",
        cache_prefixes=("llm_debate_pro_",),
        cache_ttl=86400,
        settings_suffix="debate_pro",
        cache_groups=("preload",),
    ),
    DataModuleDef(
        "辩论黑脸",
        "llm_debate_con",
        cache_prefixes=("llm_debate_con_",),
        cache_ttl=86400,
        settings_suffix="debate_con",
        cache_groups=("preload",),
    ),
    DataModuleDef(
        "辩论综合",
        "llm_debate_synthesis",
        cache_prefixes=("llm_debate_synthesis_",),
        cache_ttl=86400,
        settings_suffix="debate_synthesis",
        cache_groups=("preload",),
    ),
    # ── 补充数据（refresh 组）──
    DataModuleDef(
        "机构盈利预测",
        "profit_forecast",
        cache_prefixes=("profit_forecast_",),
        cache_ttl=CACHE_DAILY,
        cache_groups=("refresh",),
    ),
    DataModuleDef(
        "行业资金流向", "sector_flow", cache_prefixes=("sector_flow_",), cache_ttl=900, cache_groups=("refresh",)
    ),
    DataModuleDef(
        "股票历史分红", "dividend", cache_prefixes=("dividend_",), cache_ttl=CACHE_MONTHLY, cache_groups=("refresh",)
    ),
    # ── 基金深度分析模块 ──
    DataModuleDef(
        "基金经理",
        "fund_manager",
        cache_prefixes=("fund_manager_",),
        exact_cache_keys=("fund_manager_snapshot",),
        cache_ttl=CACHE_DAILY,
        cache_groups=("refresh",),
    ),
    DataModuleDef(
        "基金集中度历史",
        "fund_concentration",
        exact_cache_keys=("fund_concentration_snapshot",),
        cache_ttl=CACHE_MONTHLY,
    ),
    DataModuleDef(
        "基金风格快照", "fund_style_snapshot", exact_cache_keys=("fund_style_snapshot",), cache_ttl=CACHE_MONTHLY
    ),
    DataModuleDef(
        "基金风格扩展数据（市值/PE）",
        "extended",
        cache_prefixes=("extended_",),
        cache_ttl=CACHE_DAILY,
        cache_groups=("refresh",),
    ),
    # ── 精确键名缓存（基准数据/持仓跟踪/交易日历）──
    DataModuleDef(
        "基金业绩基准",
        "benchmark",
        exact_cache_keys=("fund_benchmarks",),
        cache_ttl=CACHE_MONTHLY,
        cache_groups=("refresh",),
    ),
    DataModuleDef(
        "持仓跟踪", "tracking", exact_cache_keys=("holdings_tracking",), cache_ttl=CACHE_MONTHLY
    ),  # 无 cache_group，避免被手动清除
    # ── 组合历史走势（无 cache_group — per-code 缓存，不因切换持仓文件而清除）──
    DataModuleDef("历史股票日线", "history_stock", cache_prefixes=("history_stock_",), cache_ttl=CACHE_WEEKLY),
    DataModuleDef("历史基金净值", "history_fund_otc", cache_prefixes=("history_fund_otc_",), cache_ttl=CACHE_MONTHLY),
    DataModuleDef("指数历史日线", "history_index", cache_prefixes=("history_index_",), cache_ttl=CACHE_MONTHLY),
    # ── 交易日历（akshare 全年数据，极少变动，无 cache_group 避免误删）──
    DataModuleDef(
        "交易日历", "calendar", exact_cache_keys=("trading_calendar",), cache_ttl=CACHE_WEEKLY * 2
    ),  # 两周（cleanup 周期 + 读缓存均从此取值）
    # ── 无风险利率（bond_zh_us_rate + 手动兜底）──
    DataModuleDef(
        "无风险利率",
        "bond_yield",
        exact_cache_keys=("bond_yield_rf",),
        cache_ttl=CACHE_DAILY,
        cache_groups=("refresh",),
    ),
)


# ── 派生产出 ────────────────────────────────────────────────
# 以下函数从 _MODULE_REGISTRY 动态生成，供 config.py / cache.py 使用


def get_registry() -> tuple[DataModuleDef, ...]:
    """返回完整的注册表副本（用于遍历和测试）。"""
    return _MODULE_REGISTRY


def get_cache_ttl_defaults() -> dict[str, float]:
    """按数据类型返回默认 TTL 映射。

    未注册的类型回退到 CACHE_DAILY。
    """
    return {m.data_type: m.cache_ttl for m in _MODULE_REGISTRY}


def get_prefix_type_map() -> dict[str, str]:
    """缓存文件名前缀 → 数据类型映射。

    用于 cleanup_expired() 从文件名前缀推断数据类型。
    """
    result: dict[str, str] = {}
    for m in _MODULE_REGISTRY:
        for prefix in m.cache_prefixes:
            result[prefix] = m.data_type
    return result


def get_exact_type_map() -> dict[str, str]:
    """精确缓存键名 → 数据类型映射。

    用于固定键名（无通配前缀）的缓存文件清理。
    """
    return {key: m.data_type for m in _MODULE_REGISTRY for key in m.exact_cache_keys}


def get_known_llm_settings_keys() -> set[str]:
    """返回 llm_settings.json 的所有合法键名。

    由每个 LLM 模块的 settings_suffix 自动派生。
    外加全局键名（max_retries, enabled_llm, pricing）。
    """
    keys: set[str] = set()
    for m in _MODULE_REGISTRY:
        if m.is_llm:
            keys |= m.llm_settings_keys()
    # 全局键名
    keys |= {
        "max_retries",
        "enabled_llm",
        "pricing",
        "llm_max_concurrency",
        "news_correlation_top_n",
        "debate",
        "fact_check",
    }
    return keys


def get_registered_data_types() -> set[str]:
    """返回所有已注册的数据类型集合。"""
    return {m.data_type for m in _MODULE_REGISTRY}


def get_known_enabled_llm_keys() -> set[str]:
    """返回 enabled_llm 字典的所有合法子键（即所有 LLM 模块的 settings_suffix）。"""
    return {m.settings_suffix for m in _MODULE_REGISTRY if m.is_llm and m.settings_suffix is not None}


def get_llm_module_name(settings_suffix: str) -> str:
    """根据 settings_suffix 返回 LLM 模块的中文名称。

    Args:
        settings_suffix: 模块后缀，如 "global_macro"、"expert_review"

    Returns:
        中文名称；未找到时返回 settings_suffix 本身

    Usage:
        >>> get_llm_module_name("global_macro")
        '全球政经局势'
    """
    for m in _MODULE_REGISTRY:
        if m.settings_suffix == settings_suffix:
            return m.name
    return settings_suffix


def get_llm_module_names() -> dict[str, str]:
    """返回所有 LLM 模块的 settings_suffix → 中文名称 映射。

    替代各模块内部硬编码的 _label_map / _MODULE_DISPLAY 等字典。

    Returns:
        {suffix: name, ...}，如 {"global_macro": "全球政经局势", ...}

    Usage:
        >>> names = get_llm_module_names()
        >>> names["global_macro"]
        '全球政经局势'
    """
    return {m.settings_suffix: m.name for m in _MODULE_REGISTRY if m.is_llm and m.settings_suffix is not None}


# ── 非 LLM 报表页签名称 ──────────────────────────────────
# 对应 Excel 报告的各功能页签中文标题。
# LLM 模块页签（global_macro/expert_review/health_check/penetration_deep）
# 以及 news_correlation 已通过 get_llm_module_name() 注册，无需再列于此。

_REPORT_SHEET_NAMES: dict[str, str] = {
    "summary": "投资分析汇总",
    "market_value": "市值核算明细表",
    "category": "持仓分类表",
    "penetration": "资产穿透TOP10",
    "fund_performance": "基金业绩分析",
    "fund_manager": "基金经理变更监控",
    "position_relationship": "持仓关系矩阵",
    "fund_concentration": "持仓集中度监控",
    "style_factor": "风格与因子分析",
    "portfolio_history_drawdown": "组合历史走势与回撤",
    "portfolio_evolution": "组合演进",
    "action": "行动建议",
}


def get_report_sheet_name(sheet_key: str) -> str:
    """根据 sheet 键名返回非 LLM 报表页签的中文标题。

    Args:
        sheet_key: 页签键名，如 "summary"、"market_value"

    Returns:
        中文标题；未找到时返回 sheet_key 本身
    """
    return _REPORT_SHEET_NAMES.get(sheet_key, sheet_key)


# ── 计算模块注册表（_COMPUTATION_REGISTRY） ──────────────────
# 计算模块不能反向导入 report/，此注册表确保分析模块与报表层的
# 单向依赖关系（analysis 层隔离约束）得以维持。


@dataclass(frozen=True)
class ComputModuleDef:
    """计算模块注册表条目。

    记录所有计算/分析模块的元信息，
    用于运行时发现、依赖管理和指标级断路的注册基础。

    Attributes:
        name: 模块中文名称。
        module_key: 模块键名，如 "analytics_metrics"、"analytics_liquidity"。
        label: 短标签（用于日志/提示）。
        dependencies: 前置数据模块键名列表（如 "bond_yield"、"history"）。
        description: 模块功能说明，用于文档生成。
        status: 实现状态（planned / implemented）。
    """

    name: str
    module_key: str
    label: str = ""
    dependencies: tuple[str, ...] = ()
    description: str = ""
    status: str = "planned"


_COMPUTATION_REGISTRY: tuple[ComputModuleDef, ...] = (
    ComputModuleDef(
        name="量化指标计算",
        module_key="analytics_metrics",
        label="指标",
        dependencies=("bond_yield", "history"),
        description="夏普比率、卡玛比率、HHI 集中度、组合 Beta、持仓胜率、换手率、波动率、最大回撤等指标",
        status="implemented",
    ),
    ComputModuleDef(
        name="流动性分析",
        module_key="analytics_liquidity",
        label="流动性",
        dependencies=(),
        description="场内/场外比例、停牌风险、基金封闭期分析",
        status="implemented",
    ),
    ComputModuleDef(
        name="外汇敞口分析",
        module_key="analytics_fx_exposure",
        label="外汇",
        dependencies=(),
        description="A股/港股/美股 国别分布与外汇风险敞口判断",
        status="implemented",
    ),
    ComputModuleDef(
        name="情景分析",
        module_key="analytics_scenario",
        label="情景",
        dependencies=("history",),
        description="市场上涨/下跌的情景模拟与影响评估（±10%/±20%/±30% 六情景，含置信区间传播）",
        status="implemented",
    ),
    ComputModuleDef(
        name="组合校准分析",
        module_key="analytics_alignment",
        label="校准",
        dependencies=(),
        description="组合校准修正因子：费率估算、现金剥离、时间加权收益率（TWR）",
        status="implemented",
    ),
    ComputModuleDef(
        name="用户画像推断",
        module_key="analytics_inferrer",
        label="画像",
        dependencies=(),
        description="从持仓结构推断用户风险偏好与投资风格",
        status="planned",
    ),
    ComputModuleDef(
        name="事实锚定校验器",
        module_key="analytics_fact_checker",
        label="事实校验",
        dependencies=(),
        description="LLM 输出的事实锚定校验：数值一致性、品种存在性、排名正确性（纯算法层）",
        status="implemented",
    ),
)


def get_computation_registry() -> tuple[ComputModuleDef, ...]:
    """返回完整的计算模块注册表副本。"""
    return _COMPUTATION_REGISTRY


def get_computation_module(module_key: str) -> ComputModuleDef | None:
    """根据 module_key 查找计算模块定义。

    Args:
        module_key: 模块键名，如 "analytics_metrics"

    Returns:
        ComputModuleDef 或 None（未找到）
    """
    for m in _COMPUTATION_REGISTRY:
        if m.module_key == module_key:
            return m
    return None


# ── 报告模块注册表（序号可配置） ──────────────────────────────

_REPORT_SECTION_DEFAULT: list[dict] = [
    # ── always 类型（始终显示，无 data_flag 依赖） ──
    {"key": "summary", "name": "投资分析汇总", "number": 1, "type": "always", "data_flag": None},
    {"key": "market_value", "name": "市值核算明细表", "number": 2, "type": "always", "data_flag": None},
    {"key": "category", "name": "持仓分类表", "number": 3, "type": "always", "data_flag": None},
    {"key": "penetration", "name": "资产穿透TOP10", "number": 4, "type": "always", "data_flag": None},
    {"key": "fund_performance", "name": "基金业绩分析", "number": 5, "type": "always", "data_flag": None},
    # ── 基金深度分析 类型（有数据才显示） ──
    {
        "key": "fund_manager",
        "name": "基金经理变更监控",
        "number": 6,
        "type": "fund_deep_analysis",
        "data_flag": "manager_data",
    },
    {
        "key": "position_relationship",
        "name": "持仓关系矩阵",
        "number": 7,
        "type": "fund_deep_analysis",
        "data_flag": "position_relationship_data",
    },
    {
        "key": "fund_concentration",
        "name": "持仓集中度监控",
        "number": 8,
        "type": "fund_deep_analysis",
        "data_flag": "concentration_data",
    },
    # ── 风格与因子分析（「基金风格表 + 风格因子回归」两区块 + 行业 Beta 子表） ──
    # 区块一：基金风格表（渲染期派生）· 区块二：风格因子回归（style_factor_data 子键）
    # · 区块三：行业 Beta 子表（style_factor_data.industry_beta，report_submodules.industry_beta 开关默认关）
    {
        "key": "style_factor",
        "name": "风格与因子分析",
        "number": 9,
        "type": "fund_deep_analysis",
        "data_flag": "style_factor_data",
    },
    # ── news 类型（需启用新闻功能） ──
    {
        "key": "news_correlation",
        "name": "财经新闻热点与持仓关联分析",
        "number": 10,
        "type": "news",
        "data_flag": "news_data_available",
    },
    # ── llm 类型（需启用 LLM 功能） ──
    {"key": "global_macro", "name": "全球政经局势", "number": 11, "type": "llm", "data_flag": "llm_data_available"},
    {"key": "expert_review", "name": "智囊团深度复盘", "number": 12, "type": "llm", "data_flag": "llm_data_available"},
    {"key": "health_check", "name": "持仓体检报告", "number": 13, "type": "llm", "data_flag": "llm_data_available"},
    {"key": "penetration_deep", "name": "穿透深度分析", "number": 14, "type": "llm", "data_flag": "llm_data_available"},
    # ── history 类型（始终显示，数据不可用时显示占位文本） ──
    # 组合历史走势与回撤：一章分「走势表 + 回撤矩阵」两区块 + 危机区间标注（2015/2018/2020/2022）
    {
        "key": "portfolio_history_drawdown",
        "name": "组合历史走势与回撤",
        "number": 15,
        "type": "history",
        "data_flag": None,
    },
    # ── evolution 类型（独立开关 enable_portfolio_evolution 控制） ──
    # 组合演进：聚合本地多期快照，data_flag 控制章节可见性，
    # available=False 时模板/页签写占位（与持仓关系矩阵的降级模式一致）
    {
        "key": "portfolio_evolution",
        "name": "组合演进",
        "number": 16,
        "type": "evolution",
        "data_flag": "evolution_data",
    },
    # ── action 类型（独立顶层开关 enable_action 控制，默认开，菜单 P 可切换） ──
    # 行动建议：再平衡信号 + 交易纪律 + 调仓建议 + 收益归因（纯算法，basic/both/full 均可见）
    {
        "key": "action",
        "name": "行动建议",
        "number": 17,
        "type": "action",
        "data_flag": None,
    },
    # ── always 类型（始终显示） ──
    {"key": "data_source_status", "name": "数据源可用性矩阵", "number": 18, "type": "always", "data_flag": None},
    # ── llm_usage 强制末位（技术约束） ──
    {"key": "llm_usage", "name": "LLM API 用量", "number": 19, "type": "llm", "data_flag": "llm_data_available"},
]


def get_report_section_keys() -> set[str]:
    """返回所有有效的报告模块标识集合，供 config 校验使用。

    Returns:
        {"summary", "market_value", "category", ..., "portfolio_history_drawdown"}
    """
    return {sec["key"] for sec in _REPORT_SECTION_DEFAULT}


def get_report_section_number(key: str, config: dict | None = None) -> int:
    """根据模块键名返回当前配置下的序号。

    优先读取用户配置（config.json 的 report_section_order），
    未配置时返回默认注册表中的序号。

    Args:
        key: 模块键名，如 "fund_manager"
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
