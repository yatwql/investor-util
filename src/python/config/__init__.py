"""配置管理模块 — 读写 data/config/config.json。

支持：
- 基础配置（持仓目录/文件名/输出目录等）
- 缓存 TTL 自定义
- LLM 外部配置文件引用（API Key 不直接存储在 config.json 中）
- config.json / llm_settings.json / llm_key.json 支持 ``//`` 单行注释和 ``/* */`` 多行注释
  （自动剥离后解析），方便按业务场景分组管理配置项。

架构：config/ 子包（v0.3.1 拆分，原 config.py 单文件 867 行 → 3 子模块）
  _defaults.py  — 默认配置 & 模板生成
  _comments.py  — JSON 注释剥离
  _core.py      — 配置读写/缓存/校验/LLM 配置（核心逻辑）
"""

# 保留子模块引用，供测试和外部直接访问
from src.python.config import _defaults as _defaults
from src.python.config import _comments as _comments
from src.python.config import _core as _core

# ── 默认配置 ──
from src.python.config._defaults import (
    _DEFAULT_CONFIG,
    _get_default_config_template,
    _CONFIG_FILE,
    get_config_path,
)

# ── JSON 注释剥离 ──
from src.python.config._comments import _strip_json_comments

# ── 核心逻辑 ──
from src.python.config._core import (
    # 配置缓存 & 读写
    get_config,
    set_config,
    init_config,
    _clear_config_cache,
    _config_cache,
    _config_mtime,
    _config_size,
    _config_lock,
    # 配置校验
    validate_config,
    _KNOWN_NEWS_SOURCES,
    _KNOWN_PROVIDER_TYPES,
    _KNOWN_PROVIDER_NAMES,
    _STRING_CONFIG_KEYS,
    # LLM 配置
    get_llm_config,
    get_llm_key_path,
    get_llm_settings_path,
    _KNOWN_LLM_SETTINGS_KEYS,
    _llm_config_cache,
    _llm_config_mtime,
    _llm_config_size,
    _llm_config_lock,
    _get_default_llm_settings_template,
    _ensure_llm_settings_file,
    _check_unknown_llm_keys,
)

__all__ = [
    # defaults
    "_DEFAULT_CONFIG",
    "_get_default_config_template",
    "_CONFIG_FILE",
    "get_config_path",
    # comments
    "_strip_json_comments",
    # core
    "get_config",
    "set_config",
    "init_config",
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
    "get_llm_config",
    "get_llm_key_path",
    "get_llm_settings_path",
    "_KNOWN_LLM_SETTINGS_KEYS",
    "_llm_config_cache",
    "_llm_config_mtime",
    "_llm_config_size",
    "_llm_config_lock",
    "_get_default_llm_settings_template",
    "_ensure_llm_settings_file",
    "_check_unknown_llm_keys",
]
