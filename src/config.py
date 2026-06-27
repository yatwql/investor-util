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
from typing import Any, Optional

logger = logging.getLogger("invest")

# 配置文件路径
_CONFIG_FILE = "data/config/config.json"

# 默认配置
_DEFAULT_CONFIG = {
    "holdings_dir": "data/holdings",
    "holdings_filename": "个人投资持仓信息.xlsx",
    "output_dir": "reports",
    "news_top_count": 100,
    "preferred_provider": {},
    "cache_ttl": {
        "price": 86400,
        "index": 86400,
        "rank": 86400,
        "hold": 604800,
        "news": 900,
        "benchmark": 2592000,
    },
    "llm_config_file": "data/config/llm.json",
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


# ── LLM 配置读取（外部文件） ─────────────────────────────────


def get_llm_config_path() -> str:
    """返回 LLM 外部配置文件的路径。

    从 data/config/config.json 中的 llm_config_file 字段读取，
    若未配置则默认返回 "data/config/llm.json"。
    """
    config = get_config()
    return config.get("llm_config_file", "data/config/llm.json")


# ── LLM 配置缓存（按文件修改时间自动失效） ──────────────────

_llm_config_cache: dict | None = None
_llm_config_mtime: float = 0
_llm_config_lock = threading.Lock()


def get_llm_config() -> dict | None:
    """读取 LLM 配置文件（带缓存，文件修改后自动刷新）。"""
    global _llm_config_cache, _llm_config_mtime

    with _llm_config_lock:
        llm_path = get_llm_config_path()
        if not os.path.exists(llm_path):
            logger.warning("LLM 配置文件不存在: %s", llm_path)
            _llm_config_cache = None
            return None

        try:
            current_mtime = os.path.getmtime(llm_path)
            if _llm_config_cache is not None and current_mtime <= _llm_config_mtime:
                return _llm_config_cache

            with open(llm_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # 校验配置
            provider = config.get("provider", "")
            endpoint = config.get("endpoint", "")
            if provider and provider not in ("claude", "openai"):
                logger.warning("llm.json provider = '%s' 不是有效值（应为 'claude' 或 'openai'）", provider)
            if endpoint and not endpoint.startswith("http"):
                logger.warning("llm.json endpoint = '%s' 不是有效 URL（应以 http 开头）", endpoint)

            _llm_config_cache = config
            _llm_config_mtime = current_mtime
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("LLM 配置文件读取失败: %s", e)
            _llm_config_cache = None
            return None
