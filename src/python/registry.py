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
    # ── 基础行情 ──
    DataModuleDef("股票价格", "price",
                  cache_prefixes=("price_",), cache_ttl=CACHE_DAILY),
    DataModuleDef("市场指数", "index",
                  cache_prefixes=("index_",), cache_ttl=CACHE_DAILY),

    # ── 基金数据 ──
    DataModuleDef("基金业绩排名", "rank",
                  cache_prefixes=("fund_perf_",), cache_ttl=CACHE_DAILY),
    DataModuleDef("基金持仓", "hold",
                  cache_prefixes=("fund_hold_",), cache_ttl=CACHE_WEEKLY),

    # ── 行业分类 ──
    DataModuleDef("行业分类", "industry",
                  cache_prefixes=("industry_",), cache_ttl=CACHE_WEEKLY),

    # ── 新闻 ──
    DataModuleDef("新闻聚合", "news",
                  cache_prefixes=("news_",), cache_ttl=900),

    # ── LLM 智能分析模块 ──
    DataModuleDef("全球政经局势", "llm_global_macro",
                  cache_prefixes=("llm_global_macro_",),
                  cache_ttl=86400, settings_suffix="global_macro"),
    DataModuleDef("智囊团深度复盘", "llm_expert_review",
                  cache_prefixes=("llm_expert_review_",),
                  cache_ttl=7200, settings_suffix="expert_review"),
    DataModuleDef("LLM新闻关联分析", "llm_news_correlation",
                  cache_prefixes=("llm_news_correlation_", "llm_news_item_"),
                  cache_ttl=3600, settings_suffix="news_correlation"),
    DataModuleDef("持仓体检报告", "llm_health_check",
                  cache_prefixes=("llm_health_check_",),
                  cache_ttl=7200, settings_suffix="health_check"),
    DataModuleDef("穿透深度分析", "llm_penetration_deep",
                  cache_prefixes=("llm_penetration_deep_",),
                  cache_ttl=86400, settings_suffix="penetration_deep"),

    # ── 补充数据 ──
    DataModuleDef("机构盈利预测", "profit_forecast",
                  cache_prefixes=("profit_forecast_",), cache_ttl=CACHE_DAILY),
    DataModuleDef("行业资金流向", "sector_flow",
                  cache_prefixes=("sector_flow_",), cache_ttl=900),
    DataModuleDef("股票历史分红", "dividend",
                  cache_prefixes=("dividend_",), cache_ttl=CACHE_MONTHLY),

    # ── 精确键名缓存（基准数据/持仓跟踪）──
    DataModuleDef("基金业绩基准", "benchmark",
                  exact_cache_keys=("fund_benchmarks", "holdings_tracking"),
                  cache_ttl=CACHE_MONTHLY),
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
    # enabled_llm_news_correlation 是 v0.2.35 之前的旧键名，作为已知的已弃用键保留
    keys |= {"max_retries", "enabled_llm", "enabled_llm_news_correlation", "pricing"}
    return keys


def get_registered_data_types() -> set[str]:
    """返回所有已注册的数据类型集合。"""
    return {m.data_type for m in _MODULE_REGISTRY}
