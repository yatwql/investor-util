"""数据模块注册表 — 数据模块的配置键名、缓存前缀、默认 TTL 与 LLM 设置键派生。

（自 core/registry.py 按注册职责域下沉；门面 ``core/registry.py`` 原样再导出，
导入面与测试 patch 面不变。域内互调在本模块内解析。）

设计目标：
  - 一处注册，全局生效
  - 新增数据模块只需修改本文件，config/cache/常量三处自动同步
  - 消除 config.py / cache.py / constants.py 三处分散维护的遗漏风险

用法：
  >>> from src.python.core.registry import get_cache_ttl_defaults
  >>> ttl_map = get_cache_ttl_defaults()
  >>> ttl_map["price"]
  86400
"""

from __future__ import annotations

from dataclasses import dataclass

from src.python.core.constants import CACHE_DAILY, CACHE_MONTHLY, CACHE_TWO_WEEKS, CACHE_WEEKLY

__all__ = [
    "DataModuleDef",
    "LLM_HIDDEN_KEYS",
    "LLM_MODULE_GATED_SECTIONS",
    "_MODULE_REGISTRY",
    "get_cache_ttl_defaults",
    "get_exact_type_map",
    "get_known_enabled_llm_keys",
    "get_known_llm_settings_keys",
    "get_llm_module_name",
    "get_llm_module_names",
    "get_prefix_type_map",
    "get_registered_data_types",
    "get_registry",
    "visible_llm_module_names",
]

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
    # ── 市场情绪（同花顺官方：龙虎榜 + 连板梯队；盘中变化 → 短 TTL）──
    DataModuleDef("市场情绪", "sentiment", cache_prefixes=("sentiment_",), cache_ttl=3600.0, cache_groups=("refresh",)),
    # ── 全文本财报（DataSinking 主源 + 巨潮备源；索引与正文分级 TTL）──
    # 索引/章节清单 TTL 与正文同档（月度）：财报披露是低频事件（年报/半年报/季报），
    # 索引两周过期会频繁重取 DataSinking（免费档日配额 8191 篇、还受 3 请求/秒限制），
    # 正是「连接失败」高发的一类场景；月度窗口不损失语义（新报告期出现时按报告期排序
    # 自然优先，且正文取数另走正文级 TTL）。
    DataModuleDef(
        "财报索引",
        "report",
        cache_prefixes=(
            "report_datasink_index_",
            "report_datasink_sections_",
            "report_cninfo_index_",
            "report_cninfo_orgid_",
            "report_cninfo_text_",
        ),
        cache_ttl=CACHE_MONTHLY,
        cache_groups=("refresh",),
    ),
    DataModuleDef(
        "财报正文",
        "report_doc",
        cache_prefixes=("report_datasink_doc_",),
        cache_ttl=CACHE_MONTHLY,
        cache_groups=("refresh",),
    ),
    # ── 结构化财务指标（akshare 主源） ──
    DataModuleDef(
        "财务指标",
        "fin_indicator",
        cache_prefixes=("fin_indicator_",),
        cache_ttl=CACHE_MONTHLY,
        cache_groups=("refresh",),
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
    # ── 生成后自检（实验能力，出厂默认关；生成后一遍执行，不属并行调度模块）──
    # 登记于此的目的：显示名/缓存前缀/TTL/用量统计/失败原因载体全部复用既有机制。
    # **刻意不进 generators_orchestrator._MODULE_FNS**：其输入是其余模块的产出，
    # 必须串行在它们之后，不属线程池并行调度（见 llm/self_review.py 模块说明）。
    DataModuleDef(
        "生成后自检",
        "llm_self_review",
        cache_prefixes=("llm_self_review_",),
        cache_ttl=7200,
        settings_suffix="self_review",
        cache_groups=("preload",),
    ),
    # ── 持仓变动复盘归因（实验能力，章本体由 feature holding_change_review 控制；
    #    章内 LLM 归因块，串行后置执行）──
    # 登记目的同生成后自检：显示名/缓存前缀/TTL/用量统计/失败原因载体复用既有机制。
    # **刻意不进 generators_orchestrator._MODULE_FNS**：输入是报告 seam 注入的契约
    # （holding_change_data），必须在报告管线内串行取用，不属线程池并行调度
    # （见 llm/holding_change_review.py 模块说明）。
    DataModuleDef(
        "持仓变动复盘归因",
        "llm_holding_change",
        cache_prefixes=("llm_holding_change_",),
        cache_ttl=7200,
        settings_suffix="holding_change",
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
    DataModuleDef(
        "基金申购状态总表",
        "fund_purchase",
        exact_cache_keys=("fund_purchase_status_table",),
        cache_ttl=CACHE_DAILY,  # 与官方净值（price 数据类型）同档，显式声明而非回退巧合
    ),  # 无 cache_group：大表不随菜单刷新强抓，仅按 TTL 过期
    DataModuleDef(
        "基金申赎费率",
        "fund_fee",
        cache_prefixes=("fund_fee_",),
        cache_ttl=CACHE_WEEKLY,  # 费率低频变动，周档 + TTL 抖动防同批过期
        cache_groups=("refresh",),  # per-code 缓存，随菜单刷新按持仓代码更新（同基金持仓组）
    ),
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
        "llm_max_thinking_concurrency",
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


# 面板隐藏的 LLM 模块集合（单一事实来源）：辩论三模块保留在注册表
# （缓存 TTL/前缀清理仍依赖），但不入状态面板/配置面板/编辑白名单。
# TUI 菜单过滤、Web 状态面与配置编辑白名单均由此派生，禁止渠道自持副本。
LLM_HIDDEN_KEYS: frozenset[str] = frozenset({"debate_pro", "debate_con", "debate_synthesis"})

# 报告章级开关集合（单一事实来源）：这些 LLM 分析章由 llm_settings.json →
# enabled_llm.<key> 逐模块独立控制，禁用时**整章隐藏**（目录/正文/Excel 页签与
# 连续重编号同步剔除），而非显示「待生成」占位；HTML/Excel 两端可见性判定同由此派生，
# 禁止两端自持副本。
# 不在集合内的 LLM 相关章：news_correlation（LLM 仅二次增强，关键词模式仍可用，
# 章不随模块隐藏）、llm_usage（用量统计随 board 总开关）。
LLM_MODULE_GATED_SECTIONS: frozenset[str] = frozenset(
    {"global_macro", "expert_review", "health_check", "penetration_deep"}
)


def visible_llm_module_names() -> dict[str, str]:
    """面板可见的 LLM 标准模块映射（settings_suffix → 中文名，已剔除隐藏模块）。"""
    return {k: v for k, v in get_llm_module_names().items() if k not in LLM_HIDDEN_KEYS}
