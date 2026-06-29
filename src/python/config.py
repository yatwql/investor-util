"""配置管理模块 — 读写 data/config/config.json。

支持：
- 基础配置（持仓目录/文件名/输出目录等）
- 缓存 TTL 自定义
- LLM 外部配置文件引用（API Key 不直接存储在 config.json 中）
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

from src.python.constants import MODEL_PRICING
from src.python.registry import get_cache_ttl_defaults, get_known_llm_settings_keys

logger = logging.getLogger("invest")

# 配置文件路径
_CONFIG_FILE = "data/config/config.json"

# 默认配置
_DEFAULT_CONFIG = {
    "holdings_dir": "data/holdings",
    "holdings_filename": "个人投资持仓信息.xlsx",
    "output_dir": "reports",
    "news_top_count": 100,
    "news_sources": {
        "sina": True,
        "eastmoney": True,
        "cls": False,
        "wallstreetcn": True,
        "akshare": True,
    },
    "preferred_provider": {},
    "cache_ttl": get_cache_ttl_defaults(),
    "user_fund_benchmarks": {},
    "llm_key_file": "data/config/llm_key.json",
    "llm_settings_file": "data/config/llm_settings.json",
}


# ── 配置缓存（线程安全，按 mtime 自动失效） ─────────────

_config_cache: dict | None = None
_config_mtime: float = 0
_config_lock = threading.Lock()


def get_config_path() -> str:
    """返回配置文件路径。"""
    return _CONFIG_FILE


def get_config() -> dict:
    """
    读取配置文件并返回配置字典（带线程安全缓存）。

    缓存按文件修改时间自动失效。若配置文件不存在或内容损坏，返回默认配置。
    """
    global _config_cache, _config_mtime

    config_path = get_config_path()
    if not os.path.exists(config_path):
        _config_cache = None
        return dict(_DEFAULT_CONFIG)

    with _config_lock:
        try:
            current_mtime = os.path.getmtime(config_path)
            if _config_cache is not None and current_mtime <= _config_mtime:
                return _config_cache
        except OSError:
            pass

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            merged = dict(_DEFAULT_CONFIG)
            # 过滤 null 值：不允许 config.json 中的 null 覆盖默认值
            for key, val in config.items():
                if val is None and key in _DEFAULT_CONFIG:
                    continue
                merged[key] = val
            _config_cache = merged
            try:
                _config_mtime = os.path.getmtime(config_path)
            except OSError:
                _config_mtime = 0
            return merged
        except (json.JSONDecodeError, IOError):
            _config_cache = None
            return dict(_DEFAULT_CONFIG)


def set_config(key: str, value: Any) -> None:
    """
    更新配置项并持久化到文件。

    写入后自动失效配置缓存，确保后续 get_config() 读取最新内容。

    Args:
        key: 配置键名
        value: 配置值
    """
    global _config_cache, _config_mtime

    config = get_config()
    config[key] = value

    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)

    # 确保父目录存在
    os.makedirs(config_dir, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # 清除缓存，使下次 get_config() 重新读取
    _config_cache = None
    _config_mtime = 0


# ── 已知的配置项枚举（用于配置校验） ──────────────────

_KNOWN_NEWS_SOURCES: set[str] = {"sina", "eastmoney", "cls", "wallstreetcn", "akshare"}

_KNOWN_PROVIDER_TYPES: set[str] = {"price", "index", "us_index", "fund_rank", "fund_hold"}

_KNOWN_PROVIDER_NAMES: set[str] = {"tencent", "eastmoney", "sina", "tiantian"}

_STRING_CONFIG_KEYS: set[str] = {"holdings_dir", "holdings_filename", "output_dir",
                                  "llm_key_file", "llm_settings_file"}


def validate_config(config: dict | None = None) -> int:
    """校验 config.json 中的常见配置错误，输出 WARNING 日志。

    Args:
        config: 已合并的配置字典。为 None 时自动调用 get_config()。

    Returns:
        发现的问题数量（方便测试断言）。
    """
    if config is None:
        config = get_config()
    issues = 0

    # ── 字符串类型检查 ──
    for key in _STRING_CONFIG_KEYS:
        val = config.get(key)
        if val is not None and not isinstance(val, str):
            logger.warning("config.json %s = %r 不是字符串类型，可能导致运行时 TypeError", key, val)
            issues += 1
    # holdings_filename 为空字符串时会导致 os.path.join 返回目录路径
    fn = config.get("holdings_filename")
    if fn is not None and not isinstance(fn, str):
        pass  # 已在上面的循环中报过
    elif isinstance(fn, str) and fn.strip() == "":
        logger.warning("config.json holdings_filename 为空字符串，将使用默认文件名")
        issues += 1

    # ── news_top_count ──
    ntc = config.get("news_top_count")
    if ntc is not None:
        try:
            n_int = int(ntc)
            if n_int <= 0:
                logger.warning("config.json news_top_count = %r 不是正数，将使用默认值 100", ntc)
                issues += 1
        except (ValueError, TypeError):
            logger.warning("config.json news_top_count = %r 不是有效整数，将使用默认值 100", ntc)
            issues += 1

    # ── cache_ttl ──
    cache_ttl = config.get("cache_ttl")
    if cache_ttl is not None and not isinstance(cache_ttl, dict):
        logger.warning("config.json cache_ttl = %r 不是对象(dict)，所有缓存 TTL 将使用默认值", cache_ttl)
        issues += 1
    elif isinstance(cache_ttl, dict):
        for k, v in cache_ttl.items():
            try:
                val = float(v)
                if val <= 0:
                    logger.warning("config.json cache_ttl.%s = %s 不是正数，将使用默认值", k, v)
                    issues += 1
            except (ValueError, TypeError):
                logger.warning("config.json cache_ttl.%s = %s 不是有效数字，将使用默认值", k, v)
                issues += 1

    # ── news_sources ──
    news_src = config.get("news_sources")
    if news_src is not None and not isinstance(news_src, dict):
        logger.warning("config.json news_sources = %r 不是对象(dict)，所有源将使用默认开关状态", news_src)
        issues += 1
    elif isinstance(news_src, dict):
        for key, val in news_src.items():
            if key not in _KNOWN_NEWS_SOURCES:
                logger.warning("config.json news_sources 中存在未知的源 %r，将被忽略", key)
                issues += 1
            if not isinstance(val, bool):
                logger.warning("config.json news_sources.%s = %r 不是布尔值，"
                               "非空字符串/数字会被当作 True 处理", key, val)
                issues += 1

    # ── preferred_provider ──
    pref = config.get("preferred_provider")
    if pref is not None and not isinstance(pref, dict):
        logger.warning("config.json preferred_provider = %r 不是对象(dict)，配置无效", pref)
        issues += 1
    elif isinstance(pref, dict):
        for data_type, provider in pref.items():
            if data_type not in _KNOWN_PROVIDER_TYPES:
                logger.warning("config.json preferred_provider 中存在未知的数据类型 %r，"
                               "有效值: %s", data_type, ", ".join(sorted(_KNOWN_PROVIDER_TYPES)))
                issues += 1
            if provider not in _KNOWN_PROVIDER_NAMES:
                logger.warning("config.json preferred_provider.%s = %r 不是已知的 provider，"
                               "有效值: %s", data_type, provider,
                               ", ".join(sorted(_KNOWN_PROVIDER_NAMES)))
                issues += 1

    # ── user_fund_benchmarks ──
    ufb = config.get("user_fund_benchmarks")
    if ufb is not None and not isinstance(ufb, dict):
        logger.warning("config.json user_fund_benchmarks = %r 不是对象(dict)，自定义基准将忽略", ufb)
        issues += 1

    if issues:
        logger.warning("config.json 共检测到 %d 个配置问题，请检查上述警告项", issues)
    return issues


def init_config() -> None:
    """初始化配置文件。

    若 config.json 不存在，则自动用默认配置创建并写入磁盘。
    若文件已存在，不做任何操作。
    """
    global _config_cache, _config_mtime

    config_path = get_config_path()
    if os.path.exists(config_path):
        config = get_config()
        validate_config(config)  # 全面校验配置
        return
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    # 清除缓存，使后续 get_config() 从新文件读取
    _config_cache = None
    _config_mtime = 0
    logger.info("配置文件已自动生成: %s", config_path)

    # 同时初始化 llm_settings.json
    _ensure_llm_settings_file()


def _ensure_llm_settings_file() -> None:
    """若 llm_settings.json 不存在，用默认值自动创建。"""
    settings_path = get_llm_settings_path()
    if os.path.exists(settings_path):
        return
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        _DEFAULT_LLM_SETTINGS = {
            "max_retries": 2,
            "temperature_global_macro": 0.3,
            "temperature_expert_review": 0.8,
            "temperature_news_correlation": 0.1,
            "temperature_health_check": 0.5,
            "temperature_penetration_deep": 0.4,
            "timeout_global_macro": 60,
            "timeout_expert_review": 120,
            "timeout_news_correlation": 60,
            "timeout_health_check": 120,
            "timeout_penetration_deep": 90,
            "cache_enabled_global_macro": True,
            "cache_enabled_expert_review": True,
            "cache_enabled_news_correlation": True,
            "cache_enabled_health_check": True,
            "cache_enabled_penetration_deep": True,
            "output_brief_global_macro": False,
            "output_brief_expert_review": False,
            "output_brief_health_check": False,
            "output_brief_penetration_deep": False,
            "max_tokens_global_macro": 1024,
            "max_tokens_expert_review": 8192,
            "max_tokens_news_correlation": 2000,
            "max_tokens_health_check": 4096,
            "max_tokens_penetration_deep": 4096,
            "model_global_macro": None,
            "model_expert_review": None,
            "model_news_correlation": None,
            "model_health_check": None,
            "model_penetration_deep": None,
            "system_prompt_global_macro": None,
            "system_prompt_expert_review": None,
            "system_prompt_news_correlation": None,
            "system_prompt_health_check": None,
            "system_prompt_penetration_deep": None,
            "enabled_llm_news_correlation": False,
            "thinking_enabled_global_macro": False,
            "thinking_enabled_expert_review": True,
            "thinking_enabled_news_correlation": False,
            "thinking_enabled_health_check": True,
            "thinking_enabled_penetration_deep": False,
            "thinking_budget_global_macro": 4000,
            "thinking_budget_expert_review": 16000,
            "thinking_budget_news_correlation": 4000,
            "thinking_budget_health_check": 12000,
            "thinking_budget_penetration_deep": 8000,
            "reasoning_effort_global_macro": "high",
            "reasoning_effort_expert_review": "high",
            "reasoning_effort_news_correlation": "high",
            "reasoning_effort_health_check": "high",
            "reasoning_effort_penetration_deep": "high",
            "pricing": {
                "currency": "CNY",
                **MODEL_PRICING,
            },
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_LLM_SETTINGS, f, ensure_ascii=False, indent=2)
        logger.info("LLM 设置文件已自动生成: %s", settings_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM 设置文件: %s", e)


# ── LLM 配置读取（外部文件） ─────────────────────────────────


def get_llm_key_path() -> str:
    """返回 LLM 密钥配置文件的路径 (llm_key.json)。

    从 data/config/config.json 中的 llm_key_file 字段读取，
    若未配置则默认返回 "data/config/llm_key.json"。
    """
    config = get_config()
    return config.get("llm_key_file", "data/config/llm_key.json")


def get_llm_settings_path() -> str:
    """返回 LLM 非敏感配置文件的路径 (llm_settings.json)。

    从 data/config/config.json 中的 llm_settings_file 字段读取，
    若未配置则默认返回 "data/config/llm_settings.json"。
    """
    config = get_config()
    return config.get("llm_settings_file", "data/config/llm_settings.json")


# ── LLM 配置缓存（按文件修改时间自动失效） ──────────────────

# 已知的 llm_settings.json 合法键名集合，用于启动时未知键名告警
# 由中央注册表 registry.py 自动派生，不再硬编码
_KNOWN_LLM_SETTINGS_KEYS: set[str] = get_known_llm_settings_keys()

# llm_key.json 中也允许出现的键名（与 llm_settings.json 重叠视为合法）
_LLM_KEY_OVERLAP_KEYS: set[str] = {"provider", "api_key", "model", "endpoint",
                                    "fallback_provider", "fallback_api_key",
                                    "fallback_endpoint", "fallback_model"}

# 已知键名合集（settings + key overlap）
_KNOWN_TOTAL_KEYS: set[str] = _KNOWN_LLM_SETTINGS_KEYS | _LLM_KEY_OVERLAP_KEYS


def _check_unknown_llm_keys(settings: dict) -> None:
    """检查 llm_settings.json 中是否存在未知键名，若有则输出 WARNING。

    Args:
        settings: 从 llm_settings.json 读取的配置字典
    """
    unknown: list[str] = []
    for key in settings:
        if key not in _KNOWN_TOTAL_KEYS:
            unknown.append(key)
    if unknown:
        logger.warning(
            "llm_settings.json 中检测到 %d 个未知配置项，可能是拼写错误或已废弃的配置: %s。"
            "请核对后删除，避免混淆。",
            len(unknown), ", ".join(repr(k) for k in sorted(unknown)),
        )

_llm_config_cache: dict | None = None
_llm_config_mtime: float = 0
_llm_config_lock = threading.Lock()


def get_llm_config() -> dict | None:
    """读取 LLM 配置（合并 llm_settings.json + llm_key.json）。

    配置优先级（高 → 低）：
      1. llm_key.json 中的字段（provider, api_key, model, endpoint）
      2. llm_settings.json 中的字段（其余所有非敏感配置）
      3. 代码内置默认值（init_llm_settings() 自动创建时写入）

    缓存按 llm_settings.json 和 llm_key.json 的修改时间联合失效。
    """
    global _llm_config_cache, _llm_config_mtime

    with _llm_config_lock:
        # ── 基础层：llm_settings.json（或向后兼容：config.json 的 llm_settings）──
        base_settings: dict = {}
        settings_mtime: float = 0
        settings_path = get_llm_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    base_settings = json.load(f)
                settings_mtime = os.path.getmtime(settings_path)
                # 首次加载时检测未知键名（仅在 cache 未初始化时告警一次）
                if _llm_config_cache is None and base_settings:
                    _check_unknown_llm_keys(base_settings)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("LLM 设置文件读取失败: %s", e)
        else:
            # 向后兼容：从 config.json 读取
            main_config = get_config()
            base_settings = dict(main_config.get("llm_settings") or {})

        # ── 覆盖层：llm_key.json ──
        key_path = get_llm_key_path()
        if not os.path.exists(key_path):
            logger.warning("LLM 密钥文件不存在: %s", key_path)
            if base_settings.get("api_key"):
                _llm_config_cache = base_settings
                _llm_config_mtime = 0
                return base_settings
            _llm_config_cache = None
            return None

        try:
            key_mtime = os.path.getmtime(key_path)
            combined_mtime = max(key_mtime, settings_mtime)

            if _llm_config_cache is not None and combined_mtime <= _llm_config_mtime:
                return _llm_config_cache

            with open(key_path, "r", encoding="utf-8") as f:
                key_config = json.load(f)

            # 校验配置
            provider = key_config.get("provider", "")
            endpoint = key_config.get("endpoint", "")
            if provider and provider not in ("claude", "openai"):
                logger.warning("llm_key.json provider = '%s' 不是有效值（应为 'claude' 或 'openai'）", provider)
            if endpoint and not endpoint.startswith("http"):
                logger.warning("llm_key.json endpoint = '%s' 不是有效 URL（应以 http 开头）", endpoint)

            # 合并：base_settings 为基础，key_config 覆盖（仅敏感字段）
            merged = dict(base_settings)
            merged.update(key_config)

            _llm_config_cache = merged
            _llm_config_mtime = combined_mtime
            return merged
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("LLM 密钥文件读取失败: %s", e)
            _llm_config_cache = None
            return None
