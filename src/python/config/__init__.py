"""配置管理模块 — 读写 data/config/config.json。

支持：
- 基础配置（持仓目录/文件名/输出目录等）
- 缓存 TTL 自定义
- LLM 外部配置文件引用（API Key 不直接存储在 config.json 中）
- config.json / llm_settings.json / llm_key.json 支持 ``//`` 单行注释和 ``/* */`` 多行注释
  （自动剥离后解析），方便按业务场景分组管理配置项。

架构：config/ 子包
  _config_defaults.py      — config.json 默认配置 & 模板生成
  _json_patch.py           — 带注释 JSON 顶层键扫描/patch 引擎 + 字段级文本替换
  _llm_settings_defaults.py — llm_settings.json 缺省模板
  _llm_providers_defaults.py — llm_providers.json 缺省模板
  _llm_settings.py         — llm_settings.json 读取/合并/缓存与 LLM 配置入口
  _llm_providers.py        — llm_providers.json 多链解析/凭据注入
  _comments.py             — JSON 注释剥离
  _validation.py           — config.json 配置校验函数集
  _core.py                 — config.json 读写/缓存协调（解析委托 _comments/_validation，patch 引擎委托 _json_patch）
"""

# 保留子模块引用，供测试和外部直接访问
from src.python.config import _comments as _comments
from src.python.config import _config_defaults as _config_defaults
from src.python.config import _core as _core
from src.python.config import _json_patch as _json_patch
from src.python.config import _llm_settings as _llm_settings
from src.python.config import _llm_settings_defaults as _llm_settings_defaults
from src.python.config import _validation as _validation

# ── JSON 注释剥离 ──
from src.python.config._comments import _strip_json_comments

# ── 默认配置（config.json）──
from src.python.config._config_defaults import (
    _CONFIG_FILE,
    _CONFIG_PATH_OVERRIDE,
    _DEFAULT_CONFIG,
    _get_default_config_template,
    get_config_path,
    set_config_path_override,
)

# ── 配置校验 ──
from src.python.config._validation import (
    _KNOWN_NEWS_SOURCES,
    _KNOWN_PROVIDER_NAMES,
    _KNOWN_PROVIDER_TYPES,
    _STRING_CONFIG_KEYS,
    validate_config,
)

# ── 核心逻辑 ──
from src.python.config._core import (
    _clear_config_cache,
    _config_cache,
    _config_lock,
    _config_mtime,
    _config_size,
    invalidate_config_cache,
    # 配置缓存 & 读写
    get_config,
    init_config,
    # 章节可见性
    is_enable_fund_deep_analysis,
    is_enable_history,
    is_enable_news,
    is_enable_portfolio_evolution,
    is_enable_action,
    is_enable_data_quality,
    is_enable_candidate_compare,
    is_enable_cost_lots,
    is_enable_datasink,
    datasink_feature_ready,
    is_enable_financial_indicator,
    is_enable_market_sentiment,
    is_enable_financial_report_digest,
    is_enable_valuation_percentile,
    is_enable_market_temperature,
    is_enable_industry_beta,
    is_enable_fund_purchase_limit,
    get_comparison_candidates,
    set_config,
    del_config,
)

# ── LLM 设置解析（llm_settings.json）──
from src.python.config._llm_settings import (
    _KNOWN_LLM_SETTINGS_KEYS,
    _check_unknown_llm_keys,
    _ensure_llm_settings_file,
    _llm_config_cache,
    _llm_config_lock,
    _llm_config_mtime,
    _llm_config_size,
    invalidate_llm_config_cache,
    # LLM 配置
    get_llm_config,
    get_llm_settings_path,
    # 章节可见性
    is_enable_llm,
)

# ── 默认模板（llm_settings.json）──
from src.python.config._llm_settings_defaults import (
    _get_default_llm_settings_template,
)

__all__ = [
    # config 默认配置
    "_DEFAULT_CONFIG",
    "_get_default_config_template",
    "_CONFIG_FILE",
    "_CONFIG_PATH_OVERRIDE",
    "get_config_path",
    # llm 默认模板
    "_get_default_llm_settings_template",
    # 注释剥离
    "_strip_json_comments",
    # 核心逻辑
    "get_config",
    "set_config",
    "del_config",
    "init_config",
    "set_config_path_override",
    "invalidate_config_cache",
    "invalidate_llm_config_cache",
    "_clear_config_cache",
    "_config_cache",
    "_config_mtime",
    "_config_size",
    "_config_lock",
    "validate_config",
    "_KNOWN_NEWS_SOURCES",
    "_KNOWN_PROVIDER_TYPES",
    "_KNOWN_PROVIDER_NAMES",
    "_STRING_CONFIG_KEYS",
    # 章节可见性
    "is_enable_fund_deep_analysis",
    "is_enable_news",
    "is_enable_history",
    "is_enable_llm",
    "is_enable_portfolio_evolution",
    "is_enable_action",
    "is_enable_data_quality",
    "is_enable_candidate_compare",
    "is_enable_cost_lots",
    "is_enable_datasink",
    "datasink_feature_ready",
    "is_enable_financial_indicator",
    "is_enable_market_sentiment",
    "is_enable_financial_report_digest",
    "is_enable_valuation_percentile",
    "is_enable_market_temperature",
    "is_enable_industry_beta",
    "is_enable_fund_purchase_limit",
    "get_comparison_candidates",
    # LLM 配置
    "get_llm_config",
    "get_llm_settings_path",
    # 渠道共享：默认值 / 持仓路径 / 本地状态 / 注释解析（公开 API）
    "get_default",
    "resolve_holdings_path",
    "get_local_flag",
    "strip_json_comments",
    "_KNOWN_LLM_SETTINGS_KEYS",
    "_llm_config_cache",
    "_llm_config_mtime",
    "_llm_config_size",
    "_llm_config_lock",
    "_ensure_llm_settings_file",
    "_check_unknown_llm_keys",
]


# ── 渠道共享：默认值与持仓路径解析（单一事实来源，渠道层禁止字面量回退） ──


def get_default(key: str):
    """返回配置默认值表中的默认值（``_DEFAULT_CONFIG`` 单一来源）。"""
    return _DEFAULT_CONFIG.get(key)


def resolve_holdings_path(config: dict | None = None) -> str:
    """解析持仓文件路径：``holdings_dir`` + ``holdings_filename``（未配置项回退默认值表）。

    三渠道（CLI/TUI/Web）持仓定位的唯一入口——渠道层不得自行拼接或字面量回退。

    Args:
        config: 可选显式配置（渠道上下文传入其缓存配置）；不传时读全局配置。
    """
    import os

    if config is None:
        config = get_config()
    holdings_dir = config.get("holdings_dir") or _DEFAULT_CONFIG.get("holdings_dir", "")
    holdings_filename = config.get("holdings_filename") or _DEFAULT_CONFIG.get("holdings_filename", "")
    return os.path.join(holdings_dir, holdings_filename)


def is_formal_holdings_source(config: dict | None = None) -> bool:
    """持仓源是否为正式持仓目录（``data/holdings/``）下的持仓文件。

    持仓快照是用户的长期历史状态（快照对比/组合演进/持仓变动复盘的数据底座），
    只应由正式持仓源写入与比对。demo/试算/临时持仓（路径不在正式目录下，含
    ``data/holdings/uploads/`` 上传暂存区）判定为非正式源——调用方据此跳过快照
    捕获与历史对比，防止幻影持仓污染真实快照历史（症状：未持有品种被报成清仓）。

    解析异常按非正式源处理（fail-closed：宁可少写、不误写用户历史）。

    Args:
        config: 配置字典；None 时读全局配置（与 ``resolve_holdings_path`` 同源解析）。
    """
    import os

    from src.python.core.constants import PROJECT_ROOT

    try:
        source = os.path.abspath(resolve_holdings_path(config))
        formal_dir = os.path.abspath(os.path.join(PROJECT_ROOT, "data", "holdings"))
        if source != formal_dir and not source.startswith(formal_dir + os.sep):
            return False
        # 上传暂存区虽在正式目录下，但内容为外部上传的试算/覆盖文件，非正式存量
        uploads_dir = os.path.abspath(os.path.join(formal_dir, "uploads"))
        return source != uploads_dir and not source.startswith(uploads_dir + os.sep)
    except Exception:
        return False


def get_local_flag(key: str) -> bool:
    """读取机器本地状态标记（公开 API，替代 ``config._local_state`` 私有模块直引）。"""
    from src.python.config._local_state import get_flag

    return get_flag(key)


# 评论解析公开别名（原私有名保留供包内既有引用）
strip_json_comments = _strip_json_comments
