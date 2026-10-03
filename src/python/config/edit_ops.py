"""配置编辑共享层 — Web / TUI 唯一编辑通道（白名单 + 校验 + 写入 + 备份）。

- ``config_edit_whitelist``：可编辑配置项白名单（点分键 → 类型/选项 → 目标文件 → 写入原语）。
  唯一事实来源；``set_config`` 不做值校验，任何渠道必须经本模块的白名单 + 值校验。
- ``apply_config_edit``：应用单次编辑（Web POST / TUI 菜单共用），按目标文件分派写入，
  写前对目标共享文件做单槽 .bak 备份。
- ``config_backup_file``：写共享配置文件前的单槽 .bak 备份（copy_file_atomic 原子复制）。

写入语义（渠道无关，单点实现）：
  config.json 顶层标量 → ``set_config``；嵌套 dict（comparison_indices）读合并后整块写；
  anonymization → ``set_anonymization_mode``；llm_settings.json → ``write_llm_settings``；
  features.json → ``save_feature_overrides``（清单由 ``features.feature_switch_registry``
  驱动，与 TUI 菜单 S / Web 开关面板同源）。

校验规则集中于此（holdings_filename 禁路径分隔符、对比指数代码长度/字符/重复、
类型/枚举/action 合法性），两渠道强度一致——禁止在渠道层另行实现同名规则。
"""

from __future__ import annotations

import json
import logging
import os

from src.python.config import strip_json_comments
from src.python.config._config_defaults import _DEFAULT_CONFIG
from src.python.config.features import (
    feature_switch_registry,
)
from src.python.core.atomic_write import copy_file_atomic
from src.python.core.registry import visible_llm_module_names

logger = logging.getLogger("invest")

# 匿名化枚举选项（对齐 config/anonymizer._ANONYMIZATION_MODES）
ANON_MODES = ("off", "code_display", "full_anonymous", "summary")


class ConfigEditError(ValueError):
    """配置编辑校验失败（未知键 / 类型不符 / 枚举不符 / action 非法）→ 调用方映射 400。"""


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
    # ── 4 持仓匿名化枚举（config.json 顶层 anonymization，set_anonymization_mode）──
    "anonymization.mode": {
        "kind": "enum",
        "options": ANON_MODES,
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
    # ── 6 LLM 分析章节开关（llm_settings.json enabled_llm；清单 = 注册表可见标准模块）──
    **{
        f"enabled_llm.{sfx}": {"kind": "bool", "target": "llm_settings", "writer": "llm"}
        for sfx in visible_llm_module_names()
    },
    # ── 7 功能开关（features.json；清单取自 features.feature_switch_registry 全注册表，
    #      实验组与常规组同表同写入路径，分组只影响前端分块渲染）──
    **{flag: {"kind": "bool", "target": "features", "writer": "features"} for flag in feature_switch_registry},
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
        from src.python.config.features import FEATURES_FILE

        return FEATURES_FILE
    raise ConfigEditError(f"未知配置目标文件: {target}")


def config_backup_file(path: str) -> str | None:
    """写共享配置文件前的单槽 .bak 备份（原子复制）。

    - 文件不存在 → 返回 None（首次写入无需备份）。
    - 存在 → 复制为 ``{path}.bak``（单槽轮转：第二次写覆盖上一版 .bak）。

    Args:
        path: 共享配置文件绝对路径。

    Returns:
        .bak 绝对路径；原文件不存在时返回 None。

    Raises:
        OSError: 备份失败（目标目录不可写等），调用方中止配置写入。
    """
    if not os.path.isfile(path):
        return None
    bak_path = path + ".bak"
    copy_file_atomic(path, bak_path)
    logger.info("[config-edit] 已备份共享配置文件: %s", bak_path)
    return bak_path


def _dispatch_write(entry: dict, key: str, value) -> None:
    """按白名单写入原语分派（渠道无关的唯一写入路径）。"""
    writer = entry["writer"]
    if writer == "scalar":
        from src.python.config import set_config

        set_config(key, value)
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
    from src.python.config._llm_settings import get_llm_settings_path, write_llm_settings

    settings_path = get_llm_settings_path()
    settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, encoding="utf-8-sig") as f:
                raw = f.read()
            settings = json.loads(strip_json_comments(raw))
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
    """对比指数池增/删/重置（读合并 → set_config 整块写）。"""
    from src.python.config import get_config, set_config

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
    """应用单次配置编辑（Web POST / TUI 菜单共用入口）。

    按白名单校验键与值，写前对目标共享文件做单槽 .bak 备份，随后按
    目标文件分派写入原语。

    Args:
        payload: ``{"key": 点分键, "value": 值}`` 或 ``{"key": "comparison_indices",
                 "action": add/remove/reset, "code": ..., "name": ...}``.

    Returns:
        ``{"key": 点分键, "value": 新值, "backup": .bak 路径或 None}``.

    Raises:
        ConfigEditError: 键/值/action 校验失败（Web 映射 400，TUI 映射提示行）。
        OSError / Exception: 写入失败（Web 映射 500，调用方记日志）。
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
