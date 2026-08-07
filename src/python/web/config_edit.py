"""Web 配置编辑 — 完整镜像 TUI 可编辑配置全集。

- ``config_edit_whitelist``：可编辑配置项白名单（点分键 → 类型/选项 → 目标文件 → 写入原语）。
  唯一事实来源；``set_config`` 不做值校验，Web 端必须自建白名单 + 值校验。
- ``get_config_edit_surface``：读取面板全量可编辑面（GET /api/config/edit）。
- ``apply_config_edit``：应用单次编辑（POST /api/config/edit），按目标文件分派写入。
- ``config_backup_file``：写共享配置文件前的单槽 .bak 备份（mkstemp + os.replace 原子写）。

写入语义与 TUI 逐条等价（对齐 tui/handlers_config.py 编辑路径）：
  config.json 顶层标量 → ``set_config``；嵌套 dict（report_submodules /
  comparison_indices）读合并后整块写；anonymization → ``set_anonymization_mode``；
  llm_settings.json → ``write_llm_settings``（自 tui 抽取的共享原语）；
  features.json → ``save_feature_overrides``。
"""

from __future__ import annotations

import json
import logging
import os

from src.python.web.holdings_update import _atomic_copy

logger = logging.getLogger("invest")

# 匿名化枚举选项（对齐 config/anonymizer._ANONYMIZATION_MODES）
_ANON_MODES = ("off", "code_display", "full_anonymous", "summary")

# 报告章节开关（菜单 P 1~5，缺失时默认开）
_SECTION_KEYS = (
    "enable_fund_deep_analysis",
    "enable_news",
    "enable_history",
    "enable_portfolio_evolution",
    "enable_action",
)

# 报告增强子模块（菜单 P 6）
_SUBMODULE_KEYS = (
    "data_quality",
    "industry_beta",
    "candidate_compare",
    "cost_lots",
    "valuation_percentile",
    "market_temperature",
)

# LLM 分析章节可编辑开关（菜单 S 1~5；辩论三模块为隐藏项，不在白名单）
_LLM_SURFACE_KEYS = ("global_macro", "expert_review", "health_check", "penetration_deep", "news_correlation")
_LLM_HIDDEN_MODULES = ("debate_pro", "debate_con", "debate_synthesis")

# 辩论实验功能开关（菜单 S 6~8，features.json）
_DEBATE_FLAG_KEYS = ("llm_debate_procon", "llm_debate_conditional", "llm_debate_qa_concentration")


class ConfigEditError(ValueError):
    """配置编辑校验失败（未知键 / 类型不符 / 枚举不符 / action 非法）→ 400 BAD_PARAM。"""


# ═══════════════════════════════════════════════════════════════
# 白名单（唯一事实来源：点分键 → 编辑规则 → 目标文件 → 写入原语）
# ═══════════════════════════════════════════════════════════════
# 设计约束：本数据字典为模块级小写名（check-semantic-index 反向校验
# 用大小写敏感子串匹配，UPPER_SNAKE 会匹配不过）。
config_edit_whitelist = {
    # ── 1 自由文本路径（config.json 顶层标量）──
    "holdings_dir": {"kind": "str", "target": "config", "writer": "scalar"},
    "holdings_filename": {"kind": "str", "target": "config", "writer": "scalar"},
    "output_dir": {"kind": "str", "target": "config", "writer": "scalar"},
    # ── 2 报告章节开关（config.json 顶层标量）──
    "enable_fund_deep_analysis": {"kind": "bool", "target": "config", "writer": "scalar"},
    "enable_news": {"kind": "bool", "target": "config", "writer": "scalar"},
    "enable_history": {"kind": "bool", "target": "config", "writer": "scalar"},
    "enable_portfolio_evolution": {"kind": "bool", "target": "config", "writer": "scalar"},
    "enable_action": {"kind": "bool", "target": "config", "writer": "scalar"},
    # ── 3 报告增强子模块开关（config.json 嵌套 dict，读合并整块写）──
    "report_submodules.data_quality": {"kind": "bool", "target": "config", "writer": "submodule"},
    "report_submodules.industry_beta": {"kind": "bool", "target": "config", "writer": "submodule"},
    "report_submodules.candidate_compare": {"kind": "bool", "target": "config", "writer": "submodule"},
    "report_submodules.cost_lots": {"kind": "bool", "target": "config", "writer": "submodule"},
    "report_submodules.valuation_percentile": {"kind": "bool", "target": "config", "writer": "submodule"},
    "report_submodules.market_temperature": {"kind": "bool", "target": "config", "writer": "submodule"},
    # ── 4 持仓匿名化枚举（config.json 顶层 anonymization，set_anonymization_mode）──
    "anonymization.mode": {
        "kind": "enum",
        "options": _ANON_MODES,
        "target": "config",
        "writer": "anonymization",
    },
    # ── 5 对比指数池（config.json 嵌套 dict，增/删/重置）──
    "comparison_indices": {
        "kind": "action",
        "actions": ("add", "remove", "reset"),
        "target": "config",
        "writer": "comparison_indices",
    },
    # ── 6 LLM 分析章节开关（llm_settings.json enabled_llm）──
    "enabled_llm.global_macro": {"kind": "bool", "target": "llm_settings", "writer": "llm"},
    "enabled_llm.expert_review": {"kind": "bool", "target": "llm_settings", "writer": "llm"},
    "enabled_llm.health_check": {"kind": "bool", "target": "llm_settings", "writer": "llm"},
    "enabled_llm.penetration_deep": {"kind": "bool", "target": "llm_settings", "writer": "llm"},
    "enabled_llm.news_correlation": {"kind": "bool", "target": "llm_settings", "writer": "llm"},
    # ── 7 辩论实验功能开关（features.json）──
    "llm_debate_procon": {"kind": "bool", "target": "features", "writer": "features"},
    "llm_debate_conditional": {"kind": "bool", "target": "features", "writer": "features"},
    "llm_debate_qa_concentration": {"kind": "bool", "target": "features", "writer": "features"},
}


def _target_path(target: str) -> str:
    """解析目标共享配置文件的绝对路径（写前备份用）。"""
    if target == "config":
        from src.python.config._config_defaults import get_config_path

        return get_config_path()
    if target == "llm_settings":
        from src.python.config._llm_settings import get_llm_settings_path

        return get_llm_settings_path()
    if target == "features":
        from src.python.config.features import _FEATURES_FILE

        return _FEATURES_FILE
    raise ConfigEditError(f"未知配置目标文件: {target}")


def config_backup_file(path: str) -> str | None:
    """写共享配置文件前的单槽 .bak 备份（mkstemp + os.replace 原子写）。

    - 文件不存在 → 返回 None（首次写入无需备份）。
    - 存在 → 复制为 ``{path}.bak``（单槽轮转：第二次写覆盖上一版 .bak）。

    Args:
        path: 共享配置文件绝对路径。

    Returns:
        .bak 绝对路径；原文件不存在时返回 None。

    Raises:
        OSError: 备份失败（目标目录不可写等，调用方中止配置写入）。
    """
    if not os.path.isfile(path):
        return None
    bak_path = path + ".bak"
    _atomic_copy(path, bak_path)
    logger.info("[config-edit] 已备份共享配置文件: %s", bak_path)
    return bak_path


def _dispatch_write(entry: dict, key: str, value) -> None:
    """按白名单写入原语分派（与 TUI 编辑路径逐条等价）。"""
    writer = entry["writer"]
    if writer == "scalar":
        from src.python.config import set_config

        set_config(key, value)
    elif writer == "submodule":
        from src.python.config import get_config, set_config

        config = get_config()
        submodules = dict(config.get("report_submodules") or {})
        submodules[key.split(".", 1)[1]] = value
        set_config("report_submodules", submodules)
    elif writer == "anonymization":
        from src.python.config.anonymizer import set_anonymization_mode

        set_anonymization_mode(value)
    elif writer == "llm":
        _write_llm_enabled(key, value)
    elif writer == "features":
        from src.python.config.features import save_feature_overrides

        save_feature_overrides({key: value})
    else:
        raise ConfigEditError(f"未知写入原语: {writer}")


def _write_llm_enabled(key: str, value: bool) -> None:
    """写 llm_settings.json 的 enabled_llm.<模块>（读合并 → write_llm_settings）。"""
    from src.python.config import _strip_json_comments
    from src.python.config._llm_settings import get_llm_settings_path, write_llm_settings

    settings_path = get_llm_settings_path()
    settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8-sig") as f:
                raw = f.read()
            settings = json.loads(_strip_json_comments(raw))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取 llm_settings.json 失败，按空配置合并: %s", e)
    sub_key = key.split(".", 1)[1]
    enabled_map = dict(settings.get("enabled_llm") or {})
    enabled_map[sub_key] = value
    settings["enabled_llm"] = enabled_map
    write_llm_settings(settings, settings_path)


def _apply_plain_value(key: str, value, entry: dict):
    """标量/布尔/枚举编辑：先校验，再按 writer 分派写入。"""
    kind = entry["kind"]
    if kind == "str":
        if not isinstance(value, str) or not value.strip():
            raise ConfigEditError(f"配置项 {key} 应为非空字符串")
        value = value.strip()
        # holdings_filename 为纯文件名，拒绝含路径分隔符（防破坏文件定位）
        if key == "holdings_filename" and any(sep in value for sep in ("/", "\\")):
            raise ConfigEditError("holdings_filename 应为纯文件名，不能包含路径分隔符")
    elif kind == "bool":
        if not isinstance(value, bool):
            raise ConfigEditError(f"配置项 {key} 应为布尔值")
    elif kind == "enum":
        if value not in entry["options"]:
            raise ConfigEditError(f"配置项 {key} 取值不在允许范围内: {value}")
    else:
        raise ConfigEditError(f"配置项 {key} 不支持的值类型: {kind}")

    _dispatch_write(entry, key, value)
    return value


def _apply_comparison_action(payload: dict, entry: dict) -> dict:
    """对比指数池增/删/重置（读合并 → set_config 整块写，对齐 TUI 菜单 I）。"""
    from src.python.config import get_config, set_config
    from src.python.config._config_defaults import _DEFAULT_CONFIG

    action = payload.get("action")
    if action not in entry["actions"]:
        raise ConfigEditError(f"对比指数池 action 不合法（add/remove/reset）: {action}")
    config = get_config()
    indices = dict(config.get("comparison_indices") or _DEFAULT_CONFIG.get("comparison_indices", {}))
    if action == "add":
        code = payload.get("code")
        name = payload.get("name")
        if not isinstance(code, str) or not code.strip():
            raise ConfigEditError("对比指数代码不能为空")
        code = code.strip()
        if len(code) < 3:
            raise ConfigEditError("对比指数代码长度至少为 3")
        if any(token in code for token in ("..", "/", "\\")):
            raise ConfigEditError("对比指数代码包含非法字符")
        if code in indices:
            raise ConfigEditError(f"指数 {code} 已在对比池中")
        if not isinstance(name, str) or not name.strip():
            raise ConfigEditError("对比指数名称不能为空")
        indices[code] = name.strip()
    elif action == "remove":
        code = payload.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ConfigEditError("对比指数代码不能为空")
        code = code.strip()
        if code not in indices:
            raise ConfigEditError(f"指数 {code} 不在对比池中")
        del indices[code]
    else:  # reset → 默认预设
        indices = dict(_DEFAULT_CONFIG.get("comparison_indices", {}))
    set_config("comparison_indices", indices)
    return indices


def apply_config_edit(payload: dict) -> dict:
    """应用单次配置编辑（POST /api/config/edit）。

    按白名单校验键与值，写前对目标共享文件做单槽 .bak 备份，随后按
    目标文件分派写入原语（与 TUI 编辑路径逐条等价）。

    Args:
        payload: ``{"key": 点分键, "value": 值}`` 或 ``{"key": "comparison_indices",
                 "action": add/remove/reset, "code": ..., "name": ...}``。

    Returns:
        ``{"key": 点分键, "value": 新值, "backup": .bak 路径或 None}``。

    Raises:
        ConfigEditError: 键/值/action 校验失败（400 BAD_PARAM）。
        OSError / Exception: 写入失败（500 CONFIG_WRITE_FAILED，调用方记日志）。
    """
    key = payload.get("key")
    entry = config_edit_whitelist.get(key)
    if entry is None:
        raise ConfigEditError(f"配置键不在白名单: {key}")

    backup_path = config_backup_file(_target_path(entry["target"]))

    if entry["writer"] == "comparison_indices":
        new_value = _apply_comparison_action(payload, entry)
    else:
        new_value = _apply_plain_value(key, payload.get("value"), entry)
    return {"key": key, "value": new_value, "backup": backup_path}


def get_config_edit_surface() -> dict:
    """读取面板全量可编辑面（GET /api/config/edit）。

    数据来源：config.json（get_config + 章节/子模块访问器）、
    llm_settings.json（enabled_llm 直接读源文件，缺失键默认开，对齐 TUI）、
    features.json（辩论实验开关经运行时覆写读取）。
    """
    from src.python.config import (
        get_config,
        is_enable_action,
        is_enable_candidate_compare,
        is_enable_cost_lots,
        is_enable_data_quality,
        is_enable_fund_deep_analysis,
        is_enable_history,
        is_enable_industry_beta,
        is_enable_market_temperature,
        is_enable_news,
        is_enable_portfolio_evolution,
        is_enable_valuation_percentile,
    )
    from src.python.config import _strip_json_comments
    from src.python.config._config_defaults import _DEFAULT_CONFIG
    from src.python.config._llm_settings import get_llm_settings_path
    from src.python.config.anonymizer import get_anonymization_mode
    from src.python.config.features import is_feature_enabled

    config = get_config()
    paths = {
        "holdings_dir": config.get("holdings_dir") or "",
        "holdings_filename": config.get("holdings_filename") or "",
        "output_dir": config.get("output_dir") or "reports",
    }
    sections = {
        "enable_fund_deep_analysis": is_enable_fund_deep_analysis(config),
        "enable_news": is_enable_news(config),
        "enable_history": is_enable_history(config),
        "enable_portfolio_evolution": is_enable_portfolio_evolution(config),
        "enable_action": is_enable_action(config),
    }
    submodules = {
        "data_quality": is_enable_data_quality(config),
        "industry_beta": is_enable_industry_beta(config),
        "candidate_compare": is_enable_candidate_compare(config),
        "cost_lots": is_enable_cost_lots(config),
        "valuation_percentile": is_enable_valuation_percentile(config),
        "market_temperature": is_enable_market_temperature(config),
    }
    anon_mode = get_anonymization_mode()
    indices = config.get("comparison_indices") or _DEFAULT_CONFIG.get("comparison_indices", {})

    # LLM enabled_llm：直接读 llm_settings.json（未配置 LLM 时 get_llm_config 返回
    # None，面板独立读源文件仍可展示开关）；缺失键默认开（对齐 TUI enabled_map.get(sfx, True)）
    settings_path = get_llm_settings_path()
    enabled_map: dict = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8-sig") as f:
                raw = f.read()
            enabled_map = json.loads(_strip_json_comments(raw)).get("enabled_llm") or {}
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取 llm_settings.json 失败，LLM 开关按默认展示: %s", e)
    surface_enabled = {k: bool(enabled_map.get(k, True)) for k in _LLM_SURFACE_KEYS}
    debate = {flag: is_feature_enabled(flag) for flag in _DEBATE_FLAG_KEYS}

    return {
        "paths": paths,
        "sections": sections,
        "submodules": submodules,
        "anonymization": {"mode": anon_mode, "options": list(_ANON_MODES)},
        "comparison_indices": dict(indices),
        "comparison_indices_defaults": dict(_DEFAULT_CONFIG.get("comparison_indices", {})),
        "llm": {
            "enabled_llm": surface_enabled,
            "hidden_modules": list(_LLM_HIDDEN_MODULES),
            "debate": debate,
        },
    }
