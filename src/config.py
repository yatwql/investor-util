"""配置管理模块 — 读写 data/config/config.json。

支持：
- 基础配置（持仓目录/文件名/输出目录等）
- 缓存 TTL 自定义
- LLM 外部配置文件引用（API Key 不直接存储在 config.json 中）
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

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
    "llm_config_file": "data/config/llm.json",
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


# ── LLM 配置读取（外部文件） ─────────────────────────────────


def get_llm_config_path() -> str:
    """返回 LLM 外部配置文件的路径。

    从 data/config/config.json 中的 llm_config_file 字段读取，
    若未配置则默认返回 "data/config/llm.json"。
    """
    config = get_config()
    return config.get("llm_config_file", "data/config/llm.json")


# ── LLM 配置内存缓存（避免重复读文件） ──────────────────

_LLM_CONFIG_CACHE: Optional[dict] = None


def get_llm_config() -> Optional[dict]:
    """读取外部 LLM 配置文件（带内存缓存）。

    仅缓存成功结果，文件不存在或损坏时不缓存 —— 下次调用会重试，
    方便运行时创建/修复 llm.json 后立即生效。

    外部文件路径由 config.json 中的 llm_config_file 字段指定（默认 data/config/llm.json）。
    API Key 仅存储在此外部文件中，config.json 不包含明文 Key。

    外部文件格式示例 (data/config/llm.json):
        {
            "provider": "claude",
            "api_key": "sk-ant-...",
            "model": "claude-sonnet-4-20250514",
            "endpoint": "https://api.anthropic.com/v1/messages",
            "max_tokens": 2500,
            "system_prompt_macro": "你是一位资深宏观经济学家。基于市场数据输出中文全球政经局势分析（500字内）。分3-4段，覆盖主要经济体政策走向、地缘风险、对持仓潜在影响。纯文本，不要使用HTML标签。",
            "system_prompt_expert": "你是投资智囊团召集人，审计用户投资组合后召集圆桌会议，严格按三阶段输出：\n\n**Phase 1 召集令**：指出组合核心矛盾，挑5位流派对立的专家...\n\n**Phase 2 圆桌会**（两轮）：第一轮提优化方向，第二轮互相反驳。\n\n**Phase 3 定音锤**：⚖ 指挥官给出量化调仓方案。\n\n约束：数据真实、引用具体持有品种的代码/占比、全 Markdown、引用北京时间。"
        }

    Returns:
        含 provider / api_key / model / endpoint / max_tokens / system_prompt_*
        等字段的字典，文件不存在或内容损坏时返回 None。
    """
    global _LLM_CONFIG_CACHE
    if _LLM_CONFIG_CACHE is not None:
        return _LLM_CONFIG_CACHE

    llm_path = get_llm_config_path()
    if not os.path.exists(llm_path):
        logger = __import__("logging").getLogger("invest")
        logger.info("LLM 配置文件不存在: %s（模块 7/8 将使用占位文本）", llm_path)
        return None

    try:
        with open(llm_path, "r", encoding="utf-8") as f:
            llm_config = json.load(f)
        api_key = (llm_config.get("api_key") or "").strip()
        provider = (llm_config.get("provider") or "").strip().lower()
        if not api_key or not provider:
            logger = __import__("logging").getLogger("invest")
            logger.warning("LLM 配置不完整: 缺少 api_key 或 provider")
            return None
        # 只返回需要的字段，不返回完整文件内容（防止日志泄露 key）
        result = {
            "provider": provider,
            "api_key": api_key,
            "model": (llm_config.get("model") or "").strip(),
            "endpoint": (llm_config.get("endpoint") or "").strip(),
            "max_tokens": int(llm_config.get("max_tokens", 2500)),
            "system_prompt_macro": (llm_config.get("system_prompt_macro") or "").strip(),
            "system_prompt_expert": (llm_config.get("system_prompt_expert") or "").strip(),
        }
        _LLM_CONFIG_CACHE = result
        return result
    except (json.JSONDecodeError, IOError) as e:
        logger = __import__("logging").getLogger("invest")
        logger.warning("LLM 配置文件读取失败: %s", e)
        return None
