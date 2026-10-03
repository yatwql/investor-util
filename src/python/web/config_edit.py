"""Web 配置编辑 — 可编辑面（GET）呈现 + 编辑应用（POST）委托。

编辑白名单、值校验、写入分派与写前备份的唯一实现在
``src/python/config/edit_ops.py``（Web / TUI 共用同一函数，校验强度一致）；
本模块保留 Web 面板特有的可编辑面组装（``get_config_edit_surface``），
并公开再导出共享层符号（既有引用保持可用）。
"""

from __future__ import annotations

import json
import logging
import os

from src.python.config.edit_ops import (  # noqa: F401  # 公开再导出
    ANON_MODES,
    ConfigEditError,
    apply_config_edit,
    config_backup_file,
    config_edit_whitelist,
)
from src.python.config.features import (
    GROUP_EXPERIMENTAL,
    GROUP_REPORT,
    GROUP_STANDARD,
    feature_switch_registry,
    switches_in_group,
)

logger = logging.getLogger("invest")

# LLM 分析章节可编辑开关 = 注册表可见标准模块（共享单源）；辩论三模块为隐藏项
from src.python.core.registry import LLM_HIDDEN_KEYS, visible_llm_module_names  # noqa: E402


def get_config_edit_surface() -> dict:
    """读取面板全量可编辑面（GET /api/config/edit）。

    数据来源：config.json（get_config + 章节/子模块访问器）、
    llm_settings.json（enabled_llm 直接读源文件，缺失键默认开，对齐 TUI）、
    features.json（实验性功能开关经运行时覆写读取）。
    """
    from src.python.config import (
        get_config,
        get_default,
        is_enable_action,
        is_enable_fund_deep_analysis,
        is_enable_history,
        is_enable_news,
        is_enable_portfolio_evolution,
        strip_json_comments,
    )
    from src.python.config._llm_settings import get_llm_settings_path
    from src.python.config.anonymizer import get_anonymization_mode
    from src.python.config.features import is_feature_enabled

    config = get_config()
    paths = {
        "holdings_dir": config.get("holdings_dir") or "",
        "holdings_filename": config.get("holdings_filename") or "",
        "output_dir": config.get("output_dir") or get_default("output_dir"),
    }
    sections = {
        "enable_fund_deep_analysis": is_enable_fund_deep_analysis(config),
        "enable_news": is_enable_news(config),
        "enable_history": is_enable_history(config),
        "enable_portfolio_evolution": is_enable_portfolio_evolution(config),
        "enable_action": is_enable_action(config),
    }
    # 报告章节与增强：取值与显示名皆由功能开关注册表派生（GROUP_REPORT）
    report_switches = {flag: is_feature_enabled(flag) for flag, _d in switches_in_group(GROUP_REPORT)}
    anon_mode = get_anonymization_mode()
    indices = config.get("comparison_indices") or get_default("comparison_indices")

    # LLM enabled_llm：直接读 llm_settings.json（未配置 LLM 时 get_llm_config 返回
    # None，面板独立读源文件仍可展示开关）；缺失键默认开（对齐 TUI enabled_map.get(sfx, True)）
    settings_path = get_llm_settings_path()
    enabled_map: dict = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8-sig") as f:
                raw = f.read()
            enabled_map = json.loads(strip_json_comments(raw)).get("enabled_llm") or {}
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取 llm_settings.json 失败，LLM 开关按默认展示: %s", e)
    surface_enabled = {sfx: bool(enabled_map.get(sfx, True)) for sfx in visible_llm_module_names()}
    # 功能开关：按注册表分组下发（实验组 / 常规组各一块），显示名与「是否影响报告」
    # 标记由服务端同源下发——前端不维护任何开关字典，避免与注册表漂移。
    features_surface = {
        "experimental": {flag: is_feature_enabled(flag) for flag, _d in switches_in_group(GROUP_EXPERIMENTAL)},
        "standard": {flag: is_feature_enabled(flag) for flag, _d in switches_in_group(GROUP_STANDARD)},
        "labels": {flag: d.label for flag, d in feature_switch_registry.items()},
        "report_affecting": [flag for flag, d in feature_switch_registry.items() if d.affects_report],
    }

    return {
        "paths": paths,
        "sections": sections,
        "report_switches": report_switches,
        "anonymization": {"mode": anon_mode, "options": list(ANON_MODES)},
        "comparison_indices": dict(indices),
        "comparison_indices_defaults": dict(get_default("comparison_indices") or {}),
        "llm": {
            "enabled_llm": surface_enabled,
            "hidden_modules": sorted(LLM_HIDDEN_KEYS),
        },
        "features": features_surface,
    }
