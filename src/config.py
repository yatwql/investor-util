from __future__ import annotations

import json
import os
from typing import Any

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
        "news": 86400,
        "benchmark": 2592000,
    },
}


def get_config_path() -> str:
    """返回配置文件路径。"""
    return _CONFIG_FILE


def get_config() -> dict:
    """
    读取配置文件并返回配置字典。

    如果配置文件不存在或内容损坏，返回默认配置。
    """
    config_path = get_config_path()
    if not os.path.exists(config_path):
        return dict(_DEFAULT_CONFIG)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        # 合并默认值，确保新字段不会因旧配置缺失而出错
        merged = dict(_DEFAULT_CONFIG)
        merged.update(config)
        return merged
    except (json.JSONDecodeError, IOError):
        # 配置文件损坏或无法读取时，返回默认配置
        return dict(_DEFAULT_CONFIG)


def set_config(key: str, value: Any) -> None:
    """
    更新配置项并持久化到文件。

    Args:
        key: 配置键名
        value: 配置值
    """
    config = get_config()
    config[key] = value

    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)

    # 确保父目录存在
    os.makedirs(config_dir, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def init_config() -> None:
    """初始化配置文件。

    若 config.json 不存在，则自动用默认配置创建并写入磁盘。
    若文件已存在，不做任何操作。
    """
    config_path = get_config_path()
    if os.path.exists(config_path):
        return
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    logger = __import__("logging").getLogger("invest")
    logger.info("配置文件已自动生成: %s", config_path)
