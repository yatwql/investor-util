"""项目共享常量模块。

此模块不含对本项目其他任何模块的 import，保持零依赖。
供 cache.py、config.py、llm_client.py 等模块引用，
避免同一常量在多处重复维护。
"""

# ── 缓存频率常量（秒，用作代码内默认值） ──────────────────

CACHE_DAILY = 86400         # 每日（24h）
CACHE_WEEKLY = 604800       # 每周（7d）
CACHE_MONTHLY = 2592000     # 每月（30d）

# ── 缓存 TTL 默认值（按数据类型） ─────────────────────────

CACHE_TTL_DEFAULTS: dict[str, float] = {
    "price": CACHE_DAILY,
    "index": CACHE_DAILY,
    "rank": CACHE_DAILY,
    "hold": CACHE_WEEKLY,
    "news": 900,              # 新闻聚合缓存：15 分钟
    "industry": CACHE_WEEKLY, # 行业分类/概念板块：7 天
    "benchmark": CACHE_MONTHLY,
    "llm_global_macro": 86400,       # 全球政经局势：24 小时
    "llm_expert_review": 7200,       # 智囊团深度复盘：2 小时
    "llm_news_correlation": 3600,           # LLM 新闻关联分析：1 小时
    "llm_health_check": 7200,               # 持仓体检报告：2 小时
    "llm_penetration_deep": 86400,           # 穿透深度分析：24 小时
    "profit_forecast": CACHE_DAILY,   # 机构盈利预测：24h
    "sector_flow": 900,               # 行业资金流向：15分钟
    "dividend": CACHE_MONTHLY,        # 分红历史：30天
}

# ── LLM 模型定价表（每百万 token，CNY） ───────────────────

MODEL_PRICING: dict[str, dict[str, float]] = {
    # Per 1M token 定价 — 硬编码默认值（具体货币由 llm_settings.json → pricing.currency 决定）
    # 可通过 llm_settings.json 的 "pricing" 段覆盖或新增模型，
    # 文件配置优先级高于此默认表。
    # input: 标准输入（缓存未命中）
    # output: 输出
    # input_cache_hit: 缓存命中输入（可选，默认等于 input 即无折扣）
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "claude-sonnet-4-8": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "input_cache_hit": 1.50},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0, "input_cache_hit": 1.50},
    "claude-haiku-4-5": {"input": 0.25, "output": 1.25, "input_cache_hit": 0.025},
    "claude-fable-5": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "gpt-4o": {"input": 2.5, "output": 10.0, "input_cache_hit": 2.5},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "input_cache_hit": 0.15},
    "deepseek-v4-flash": {"input": 1, "output": 2, "input_cache_hit": 0.02},
    "deepseek-v4-pro": {"input": 3, "output": 6, "input_cache_hit": 0.025},
    "deepseek-chat": {"input": 1, "output": 2, "input_cache_hit": 0.02},
}
