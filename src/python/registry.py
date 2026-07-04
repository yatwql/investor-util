"""中央注册表 — 统一管理所有数据模块的配置键名、缓存前缀、默认 TTL。

设计目标：
  - 一处注册，全局生效
  - 新增模块只需修改 registry.py，其他模块自动同步
  - 消除 config.py / cache.py / constants.py 三处分散维护的遗漏风险

用法：
  >>> from src.python.registry import get_cache_ttl_defaults
  >>> ttl_map = get_cache_ttl_defaults()
  >>> ttl_map["price"]
  86400
"""

from __future__ import annotations

from dataclasses import dataclass

from src.python.constants import CACHE_DAILY, CACHE_WEEKLY, CACHE_MONTHLY


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
    DataModuleDef("股票价格", "price",
                  cache_prefixes=("price_",), cache_ttl=CACHE_DAILY,
                  cache_groups=("preload",)),
    DataModuleDef("市场指数", "index",
                  cache_prefixes=("index_",), cache_ttl=CACHE_DAILY,
                  cache_groups=("preload",)),

    # ── 基金数据（refresh 组：主动刷新缓存）──
    DataModuleDef("基金业绩排名", "rank",
                  cache_prefixes=("fund_perf_",), cache_ttl=CACHE_DAILY,
                  cache_groups=("refresh",)),
    DataModuleDef("基金持仓", "hold",
                  cache_prefixes=("fund_hold_",), cache_ttl=CACHE_WEEKLY,
                  cache_groups=("refresh",)),

    # ── 行业分类（refresh 组）──
    DataModuleDef("行业分类", "industry",
                  cache_prefixes=("industry_",), cache_ttl=CACHE_WEEKLY,
                  cache_groups=("refresh",)),

    # ── 新闻（refresh 组）──
    DataModuleDef("新闻聚合", "news",
                  cache_prefixes=("news_",), cache_ttl=900,
                  cache_groups=("refresh",)),

    # ── LLM 智能分析模块 ──
    DataModuleDef("全球政经局势", "llm_global_macro",
                  cache_prefixes=("llm_global_macro_",),
                  cache_ttl=86400, settings_suffix="global_macro",
                  cache_groups=("preload",)),
    DataModuleDef("智囊团深度复盘", "llm_expert_review",
                  cache_prefixes=("llm_expert_review_",),
                  cache_ttl=7200, settings_suffix="expert_review",
                  cache_groups=("preload",)),
    DataModuleDef("财经新闻热点与持仓关联分析", "llm_news_correlation",
                  cache_prefixes=("llm_news_item_",),
                  cache_ttl=3600, settings_suffix="news_correlation",
                  cache_groups=("refresh",)),
    DataModuleDef("持仓体检报告", "llm_health_check",
                  cache_prefixes=("llm_health_check_",),
                  cache_ttl=86400, settings_suffix="health_check",
                  cache_groups=("preload",)),
    DataModuleDef("穿透深度分析", "llm_penetration_deep",
                  cache_prefixes=("llm_penetration_deep_",),
                  cache_ttl=86400, settings_suffix="penetration_deep",
                  cache_groups=("preload",)),

    # ── 补充数据（refresh 组）──
    DataModuleDef("机构盈利预测", "profit_forecast",
                  cache_prefixes=("profit_forecast_",), cache_ttl=CACHE_DAILY,
                  cache_groups=("refresh",)),
    DataModuleDef("行业资金流向", "sector_flow",
                  cache_prefixes=("sector_flow_",), cache_ttl=900,
                  cache_groups=("refresh",)),
    DataModuleDef("股票历史分红", "dividend",
                  cache_prefixes=("dividend_",), cache_ttl=CACHE_MONTHLY,
                  cache_groups=("refresh",)),

    # ── B 系列：基金深度分析模块 ──
    DataModuleDef("基金经理", "fund_manager",
                  cache_prefixes=("fund_manager_",),
                  exact_cache_keys=("fund_manager_snapshot",),
                  cache_ttl=CACHE_DAILY,
                  cache_groups=("refresh",)),
    DataModuleDef("持仓重合度", "fund_overlap",
                  cache_prefixes=("fund_overlap_",),
                  cache_ttl=CACHE_WEEKLY,
                  cache_groups=("refresh",)),
    DataModuleDef("基金集中度历史", "fund_concentration",
                  exact_cache_keys=("fund_concentration_snapshot",),
                  cache_ttl=CACHE_MONTHLY),
    DataModuleDef("基金风格快照", "fund_style_snapshot",
                  exact_cache_keys=("fund_style_snapshot",),
                  cache_ttl=CACHE_MONTHLY),

    # ── 精确键名缓存（基准数据/持仓跟踪/交易日历）──
    DataModuleDef("基金业绩基准", "benchmark",
                  exact_cache_keys=("fund_benchmarks",),
                  cache_ttl=CACHE_MONTHLY,
                  cache_groups=("refresh",)),
    DataModuleDef("持仓跟踪", "tracking",
                  exact_cache_keys=("holdings_tracking",),
                  cache_ttl=CACHE_MONTHLY),  # 无 cache_group，避免被手动清除

    # ── 交易日历（akshare 全年数据，极少变动，无 cache_group 避免误删）──
    DataModuleDef("交易日历", "calendar",
                  exact_cache_keys=("trading_calendar",),
                  cache_ttl=CACHE_WEEKLY * 2),  # 两周（cleanup 周期 + 读缓存均从此取值）
)


# ── 派生产出 ────────────────────────────────────────────────
# 以下函数从 _MODULE_REGISTRY 动态生成，供 config.py / cache.py 使用


def get_registry() -> tuple[DataModuleDef, ...]:
    """返回完整的注册表副本（用于遍历和测试）。"""
    return _MODULE_REGISTRY


def get_cache_ttl_defaults() -> dict[str, float]:
    """按数据类型返回默认 TTL 映射。

    对应原 constants.py 中 CACHE_TTL_DEFAULTS 的功能。
    未注册的类型回退到 CACHE_DAILY。
    """
    return {m.data_type: m.cache_ttl for m in _MODULE_REGISTRY}


def get_prefix_type_map() -> dict[str, str]:
    """缓存文件名前缀 → 数据类型映射。

    用于 cleanup_expired() 从文件名前缀推断数据类型。
    对应原 cache.py 中 prefix_type_map 的功能。
    """
    result: dict[str, str] = {}
    for m in _MODULE_REGISTRY:
        for prefix in m.cache_prefixes:
            result[prefix] = m.data_type
    return result


def get_exact_type_map() -> dict[str, str]:
    """精确缓存键名 → 数据类型映射。

    用于固定键名（无通配前缀）的缓存文件清理。
    对应原 cache.py 中 exact_map 的功能。
    """
    return {key: m.data_type for m in _MODULE_REGISTRY for key in m.exact_cache_keys}


def get_known_llm_settings_keys() -> set[str]:
    """返回 llm_settings.json 的所有合法键名。

    由每个 LLM 模块的 settings_suffix 自动派生。
    外加全局键名（max_retries, enabled_llm, pricing）。
    对应原 config.py 中 _KNOWN_LLM_SETTINGS_KEYS 的功能。
    """
    keys: set[str] = set()
    for m in _MODULE_REGISTRY:
        if m.is_llm:
            keys |= m.llm_settings_keys()
    # 全局键名
    keys |= {"max_retries", "enabled_llm", "pricing"}
    return keys


def get_registered_data_types() -> set[str]:
    """返回所有已注册的数据类型集合。"""
    return {m.data_type for m in _MODULE_REGISTRY}


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
    return {
        m.settings_suffix: m.name
        for m in _MODULE_REGISTRY
        if m.is_llm
    }


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
    "early_warning": "智能预警",
    "fund_manager": "基金经理变更监控",
    "fund_overlap": "持仓重合度矩阵",
    "fund_concentration": "持仓集中度监控",
    "fund_style": "基金风格分析",
}


def get_report_sheet_name(sheet_key: str) -> str:
    """根据 sheet 键名返回非 LLM 报表页签的中文标题。

    Args:
        sheet_key: 页签键名，如 "summary"、"market_value"

    Returns:
        中文标题；未找到时返回 sheet_key 本身
    """
    return _REPORT_SHEET_NAMES.get(sheet_key, sheet_key)
