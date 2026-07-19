"""功能开关注册表 — Feature Flag 体系。

提供集中管理功能开关的能力，替代分散在各模块中的条件判断。
所有开关在注册表中统一声明默认值，支持运行时启用/禁用。

用法：
  >>> from src.python.features import is_feature_enabled, FEATURE_FLAGS
  >>> if is_feature_enabled("llm_global_macro"):
  ...     generate_global_macro()

配置持久化：功能开关可通过 features.json 覆写默认值。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.python.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 路径常量 ────────────────────────────────────────────────

_FEATURES_FILE = os.path.join(PROJECT_ROOT, "data/config/features.json")

# ── 全部功能开关默认值（18 项） ──────────────────────────
# 格式：{flag_name: default_enabled}
# False = 功能默认关闭，需要用户手动启用
# True  = 功能默认开启，可在 features.json 中关闭

_FEATURE_FLAGS_DEFAULT: dict[str, bool] = {
    # ── LLM 智能分析模块（5 项） ──
    "llm_global_macro": True,
    "llm_expert_review": True,
    "llm_health_check": True,
    "llm_penetration_deep": True,
    "llm_news_correlation": True,
    # ── B 系列基金深度分析（4 项） ──
    "b_series_fund_manager": True,
    "b_series_fund_overlap": True,
    "b_series_fund_concentration": True,
    "b_series_fund_style": True,
    # ── 新闻源（5 项） ──
    "news_sina": True,
    "news_eastmoney": True,
    "news_cls": False,
    "news_wallstreetcn": True,
    "news_akshare": True,
    # ── 历史数据与回撤（2 项） ──
    "history_portfolio": True,
    "history_benchmark": True,
    # ── 功能特性（2 项） ──
    "anonymizer": False,
    "cache_daily_cleanup": True,
}

__all__ = [
    "FEATURE_FLAGS",
    "get_feature_defaults",
    "is_feature_enabled",
    "set_feature_enabled",
    "load_feature_overrides",
    "save_feature_overrides",
    "reset_feature_flags",
]

# ── 运行时状态 ──────────────────────────────────────────────
# 合并默认值 + 外部覆写后的最终生效值

FEATURE_FLAGS: dict[str, bool] = dict(_FEATURE_FLAGS_DEFAULT)


def get_feature_defaults() -> dict[str, bool]:
    """返回功能开关的出厂默认值（不受运行时覆写影响）。"""
    return dict(_FEATURE_FLAGS_DEFAULT)


def is_feature_enabled(flag_name: str) -> bool:
    """检查指定功能开关是否启用。

    Args:
        flag_name: 功能开关名称（如 "llm_global_macro"）

    Returns:
        True 表示功能启用，False 表示功能禁用
    """
    if flag_name not in FEATURE_FLAGS:
        logger.debug("[features] 未知功能开关 '%s'，视为关闭", flag_name)
        return False
    return FEATURE_FLAGS[flag_name]


def set_feature_enabled(flag_name: str, enabled: bool) -> None:
    """运行时切换功能开关状态（不持久化）。

    持久化覆写请调用 save_feature_overrides()。

    Args:
        flag_name: 功能开关名称
        enabled: True 启用 / False 禁用
    """
    if flag_name not in FEATURE_FLAGS:
        logger.warning("[features] 试图设置未知功能开关 '%s'，忽略", flag_name)
        return
    old = FEATURE_FLAGS[flag_name]
    FEATURE_FLAGS[flag_name] = enabled
    if old != enabled:
        logger.info("[features] 功能开关 '%s': %s → %s", flag_name, old, enabled)


def load_feature_overrides() -> None:
    """从 features.json 加载覆写配置，合并到 FEATURE_FLAGS。

    文件中仅需列出需要覆写的开关键值对，未列出的保持默认值。

    JSON 格式：
      {
        "llm_global_macro": false,
        "news_cls": true
      }
    """
    if not os.path.exists(_FEATURES_FILE):
        return
    try:
        with open(_FEATURES_FILE, encoding="utf-8") as f:
            overrides = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[features] 加载覆写文件失败: %s", e)
        return

    if not isinstance(overrides, dict):
        logger.warning("[features] 覆写文件格式异常（应为 JSON object），忽略")
        return

    valid_count = 0
    for flag_name, value in overrides.items():
        if isinstance(value, bool) and flag_name in FEATURE_FLAGS:
            FEATURE_FLAGS[flag_name] = value
            valid_count += 1
        elif isinstance(value, bool):
            logger.debug("[features] 覆写未知开关 '%s'，仍加载", flag_name)
            FEATURE_FLAGS[flag_name] = value
            valid_count += 1
        else:
            logger.warning("[features] 覆写 '%s' 值应为 bool，忽略", flag_name)

    if valid_count:
        logger.info("[features] 已加载 %d 项功能开关覆写", valid_count)


def save_feature_overrides(overrides: dict[str, bool], merge: bool = True) -> None:
    """保存功能开关覆写到 features.json。

    Args:
        overrides: {flag_name: enabled} 字典
        merge: True = 合并到现有覆写（覆盖同名键），False = 完全替换
    """
    existing: dict[str, Any] = {}
    if merge and os.path.exists(_FEATURES_FILE):
        try:
            with open(_FEATURES_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing.update(overrides)

    # 只保留值为 bool 的条目
    cleaned = {k: v for k, v in existing.items() if isinstance(v, bool)}

    try:
        os.makedirs(os.path.dirname(_FEATURES_FILE), exist_ok=True)
        with open(_FEATURES_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        logger.info("[features] 已保存 %d 项功能开关覆写", len(cleaned))
    except OSError as e:
        logger.warning("[features] 保存覆写失败: %s", e)

    # 同步运行时状态
    for flag_name, enabled in cleaned.items():
        FEATURE_FLAGS[flag_name] = enabled


def reset_feature_flags() -> None:
    """重置所有功能开关为默认值（运行时状态，不影响持久化文件）。"""
    FEATURE_FLAGS.clear()
    FEATURE_FLAGS.update(_FEATURE_FLAGS_DEFAULT)
    logger.debug("[features] 功能开关已重置为默认值")


# 模块导入时自动加载覆写
load_feature_overrides()
