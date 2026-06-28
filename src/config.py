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
        "eastmoney": False,
        "cls": False,
        "wallstreetcn": True,
        "akshare": True,
    },
    "preferred_provider": {},
    "cache_ttl": {
        "price": 86400,
        "index": 86400,
        "rank": 86400,
        "hold": 604800,
        "news": 900,
        "news_corr": 3600,
        "industry": 604800,
        "benchmark": 2592000,
        "llm": 86400,
        "llm_macro": 14400,
        "llm_expert": 7200,
    },
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
            merged.update(config)
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


def init_config() -> None:
    """初始化配置文件。

    若 config.json 不存在，则自动用默认配置创建并写入磁盘。
    若文件已存在，不做任何操作。
    """
    global _config_cache, _config_mtime

    config_path = get_config_path()
    if os.path.exists(config_path):
        config = get_config()
        # 校验 cache_ttl 配置
        cache_ttl = config.get("cache_ttl") or {}
        for k, v in cache_ttl.items():
            try:
                val = float(v)
                if val <= 0:
                    logger.warning("config.json cache_ttl.%s = %s 无效（应为正数），将使用默认值", k, v)
            except (ValueError, TypeError):
                logger.warning("config.json cache_ttl.%s = %s 不是有效数字，将使用默认值", k, v)
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
            "temperature_macro": 0.3,
            "temperature_expert": 0.8,
            "temperature_news_correlation": 0.1,
            "timeout_macro": 60,
            "timeout_expert": 120,
            "timeout_news_correlation": 60,
            "cache_enabled_macro": True,
            "cache_enabled_expert": True,
            "cache_enabled_news": True,
            "output_brief_macro": False,
            "output_brief_expert": False,
            "max_tokens_macro": 800,
            "max_tokens_expert": 8192,
            "max_tokens_news_correlation": 2000,
            "cache_ttl_macro": 14400,
            "cache_ttl_expert": 7200,
            "cache_ttl_news_correlation": 3600,
            "system_prompt_macro": None,
            "system_prompt_expert": None,
            "system_prompt_news_correlation": None,
            "llm_news_analysis": False,
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
