"""核心配置逻辑 — 配置读写缓存 / LLM 配置合并。"""

from __future__ import annotations

import contextlib
import copy
import json
import logging
import os
import tempfile
import threading
from typing import Any

from src.python.config import _comments, _config_defaults
from src.python.config._llm_defaults import _get_default_llm_settings_template
from src.python.config._llm_providers_defaults import _get_default_llm_providers_template
from src.python.constants import PROJECT_ROOT
from src.python.registry import get_known_llm_settings_keys
from src.python.config._validation import _absolutize_paths, validate_config

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
# 配置缓存（线程安全，按 mtime 自动失效）
# ═══════════════════════════════════════════════════════════════

_config_cache: dict | None = None
_config_mtime: float = 0
_config_size: int = 0
_config_lock = threading.Lock()


def _clear_config_cache() -> None:
    """清空配置内存缓存（测试隔离用）。"""
    global _config_cache
    _config_cache = None


def get_config() -> dict:
    """
    读取配置文件并返回配置字典（带线程安全缓存）。

    缓存按文件修改时间自动失效。若配置文件不存在或内容损坏，返回默认配置。
    """
    global _config_cache, _config_mtime, _config_size

    config_path = _config_defaults.get_config_path()
    if not os.path.exists(config_path):
        _config_cache = None
        return dict(_config_defaults._DEFAULT_CONFIG)

    with _config_lock:
        try:
            current_mtime = os.path.getmtime(config_path)
            current_size = os.path.getsize(config_path)
            if _config_cache is not None and current_mtime <= _config_mtime and current_size == _config_size:
                return _config_cache
        except OSError:
            pass

        try:
            with open(config_path, encoding="utf-8-sig") as f:
                raw = f.read()
                cleaned = _comments._strip_json_comments(raw)
                config = json.loads(cleaned)
            merged = dict(_config_defaults._DEFAULT_CONFIG)
            # 过滤 null 值：不允许 config.json 中的 null 覆盖默认值
            # 嵌套 dict 合并：允许用户只覆盖部分子键（如 history.analysis）而不丢失默认值
            for key, val in config.items():
                if val is None and key in _config_defaults._DEFAULT_CONFIG:
                    continue
                if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
                    merged[key] = {**merged[key], **val}
                else:
                    merged[key] = val
            # 绝对化路径键：用户 config.json 中可使用相对路径，运行时统一转为绝对路径
            _absolutize_paths(merged)
            _config_cache = merged
            try:
                _config_mtime = os.path.getmtime(config_path)
                _config_size = os.path.getsize(config_path)
            except OSError:
                _config_mtime = 0
                _config_size = 0
            return merged
        except (OSError, json.JSONDecodeError):
            _config_cache = None
            logger.warning("配置文件 %s 读取失败，已回退到默认配置", config_path)
            return dict(_config_defaults._DEFAULT_CONFIG)


def set_config(key: str, value: Any) -> None:
    """
    更新配置项并持久化到文件。

    写入后自动失效配置缓存，确保后续 get_config() 读取最新内容。

    Args:
        key: 配置键名
        value: 配置值
    """
    global _config_cache, _config_mtime, _config_size

    config = get_config()
    config[key] = value

    config_path = _config_defaults.get_config_path()
    config_dir = os.path.dirname(config_path)

    os.makedirs(config_dir, exist_ok=True)

    # 原子写入：先写临时文件再 os.replace
    fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, config_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise

    _config_cache = None
    _config_mtime = 0
    _config_size = 0


def init_config(config_path: str | None = None) -> None:
    """初始化配置文件。

    若 config.json 不存在，则自动用默认配置创建并写入磁盘。
    若文件已存在，不做任何操作。

    Args:
        config_path: 可选配置文件路径覆写（CLI --config 使用）。
                     为 None 时使用默认路径 data/config/config.json。
    """
    global _config_cache, _config_mtime, _config_size

    if config_path is not None:
        _config_defaults.set_config_path_override(config_path)

    config_path = _config_defaults.get_config_path()
    if os.path.exists(config_path):
        config = get_config()
        validate_config(config)
        return
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    # 原子写入，复用 set_config() 模式
    fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_config_defaults._get_default_config_template())
        try:
            os.replace(tmp_path, config_path)
        except PermissionError:
            # Windows 并发场景：另一线程/进程已创建文件，清理自身临时文件后继续
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
            if os.path.exists(config_path):
                config = get_config()
                validate_config(config)
                return
            raise  # 文件确实不存在，重新抛出
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise
    _config_cache = None
    _config_mtime = 0
    _config_size = 0
    logger.info("配置文件已自动生成: %s", config_path)

    _ensure_llm_settings_file()
    _ensure_llm_providers_file()


# ═══════════════════════════════════════════════════════════════
# 章节可见性读取函数
# ═══════════════════════════════════════════════════════════════


def is_enable_b_series(config: dict | None = None) -> bool:
    """基金深度分析章节（#6~9）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_b_series")
    if val is None:
        logger.debug("config.json 缺少 enable_b_series，使用默认值 true")
        return True
    return bool(val)


def is_enable_news(config: dict | None = None) -> bool:
    """市场新闻（#10）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_news")
    if val is None:
        logger.debug("config.json 缺少 enable_news，使用默认值 true")
        return True
    return bool(val)


def is_enable_history(config: dict | None = None) -> bool:
    """组合历史走势+回撤分析（#16~17）是否启用。缺失时返回 True。"""
    if config is None:
        config = get_config()
    val = config.get("enable_history")
    if val is None:
        logger.debug("config.json 缺少 enable_history，使用默认值 true")
        return True
    return bool(val)


# ── LLM 分析章节可见性（来自 llm_settings.json enabled_llm） ────

_REPORT_LLM_MODULES = frozenset(
    {
        "global_macro",
        "expert_review",
        "health_check",
        "penetration_deep",
    }
)


def is_enable_llm(config: dict | None = None) -> bool:
    """LLM 分析章节是否启用。

    检查 llm_settings.json 中 4 个 LLM 报告模块（global_macro /
    expert_review / health_check / penetration_deep）是否有任一启用。
    缺失时返回 True（向后兼容）。

    注意：news_correlation 仅用于新闻关联分析，不影响 LLM 分析章节整体可见性。
    """
    llm_config = get_llm_config()
    enabled_map = (llm_config or {}).get("enabled_llm", {})
    if not enabled_map:
        return True  # 缺失时默认启用
    return any(enabled_map.get(k, False) for k in _REPORT_LLM_MODULES)


# ═══════════════════════════════════════════════════════════════
# LLM 配置
# ═══════════════════════════════════════════════════════════════

_KNOWN_LLM_SETTINGS_KEYS: set[str] = get_known_llm_settings_keys()
_llm_config_cache: dict | None = None
_llm_config_mtime: float = 0
_llm_config_size: int = 0
_llm_config_lock = threading.Lock()


def _check_unknown_llm_keys(settings: dict) -> None:
    """检查 llm_settings.json 中是否存在未知键名。"""
    unknown = [key for key in settings if key not in _KNOWN_LLM_SETTINGS_KEYS]
    if unknown:
        logger.warning(
            "llm_settings.json 中检测到 %d 个未知配置项，可能是拼写错误或已废弃的配置: %s。请核对后删除，避免混淆。",
            len(unknown),
            ", ".join(repr(k) for k in sorted(unknown)),
        )


_DEBATE_CONFIG_DEFAULTS: dict[str, Any] = {
    "mode_1_procon": {
        "per_call_max_tokens": None,
        "synthesis_model": None,
        "synthesis_temperature": 0.5,
    },
    "mode_2_conditional": {
        "scenarios": [
            {"name": "上涨", "change": 0.20, "desc": "如果未来市场上涨 20%"},
            {"name": "下跌", "change": -0.20, "desc": "如果未来市场下跌 20%"},
            {"name": "震荡", "change": 0.05, "desc": "如果未来市场窄幅震荡±5%"},
        ],
    },
    "mode_3_qa_concentration": {
        "threshold": 0.20,
    },
    "max_total_tokens_per_report": 16000,
    "per_call_timeout_override": 90,
}


def _load_debate_config(settings: dict) -> dict:
    """解析 debate 配置段，Schema 校验失败时回退默认值。

    Args:
        settings: 从 llm_settings.json 解析的原始配置字典。

    Returns:
        合并用户值与缺省值的完整 debate 配置字典。
    """
    raw_debate = settings.get("debate")
    if not isinstance(raw_debate, dict):
        return copy.deepcopy(_DEBATE_CONFIG_DEFAULTS)

    merged = copy.deepcopy(_DEBATE_CONFIG_DEFAULTS)

    # mode_1_procon
    raw_m1 = raw_debate.get("mode_1_procon")
    if isinstance(raw_m1, dict):
        if isinstance(raw_m1.get("per_call_max_tokens"), (int, float)) and raw_m1["per_call_max_tokens"] > 0:
            merged["mode_1_procon"]["per_call_max_tokens"] = raw_m1["per_call_max_tokens"]
        elif raw_m1.get("per_call_max_tokens") is not None:
            logger.warning("[debate] mode_1_procon.per_call_max_tokens 应为正数或 null，使用默认值 None")
        if isinstance(raw_m1.get("synthesis_model"), str) and raw_m1["synthesis_model"].strip():
            merged["mode_1_procon"]["synthesis_model"] = raw_m1["synthesis_model"].strip()
        if isinstance(raw_m1.get("synthesis_temperature"), (int, float)):
            if 0.0 <= raw_m1["synthesis_temperature"] <= 2.0:
                merged["mode_1_procon"]["synthesis_temperature"] = raw_m1["synthesis_temperature"]
            else:
                logger.warning("[debate] mode_1_procon.synthesis_temperature 应在 [0.0, 2.0] 范围，使用默认值 0.5")

    # mode_2_conditional
    raw_m2 = raw_debate.get("mode_2_conditional")
    if isinstance(raw_m2, dict):
        raw_scenarios = raw_m2.get("scenarios")
        if isinstance(raw_scenarios, list) and raw_scenarios:
            validated: list[dict] = []
            for idx, s in enumerate(raw_scenarios):
                if isinstance(s, dict) and "name" in s and "desc" in s:
                    validated.append({"name": str(s["name"]), "change": s.get("change", 0.0), "desc": str(s["desc"])})
                else:
                    logger.warning("[debate] mode_2_conditional.scenarios[%d] 格式无效，已跳过", idx)
            if validated:
                merged["mode_2_conditional"]["scenarios"] = validated
            else:
                logger.warning("[debate] mode_2_conditional.scenarios 全部无效，使用默认情景")

    # mode_3_qa_concentration
    raw_m3 = raw_debate.get("mode_3_qa_concentration")
    if isinstance(raw_m3, dict):
        raw_threshold = raw_m3.get("threshold")
        if isinstance(raw_threshold, (int, float)) and 0.0 < raw_threshold < 1.0:
            merged["mode_3_qa_concentration"]["threshold"] = raw_threshold
        elif raw_threshold is not None:
            logger.warning("[debate] mode_3_qa_concentration.threshold 应在 (0, 1) 范围，使用默认值 0.20")

    # 顶层标量
    raw_total = raw_debate.get("max_total_tokens_per_report")
    if isinstance(raw_total, (int, float)) and raw_total > 0:
        merged["max_total_tokens_per_report"] = int(raw_total)

    raw_timeout = raw_debate.get("per_call_timeout_override")
    if isinstance(raw_timeout, (int, float)) and raw_timeout > 0:
        merged["per_call_timeout_override"] = int(raw_timeout)

    return merged


def _ensure_llm_settings_file() -> None:
    """若 llm_settings.json 不存在，用默认值自动创建。"""
    config = get_config()
    settings_path = config.get("llm_settings_file") or os.path.join(PROJECT_ROOT, "data/config/llm_settings.json")
    if os.path.exists(settings_path):
        return
    try:
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        # 原子写入，复用 set_config() 模式
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(settings_path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_get_default_llm_settings_template())
            os.replace(tmp_path, settings_path)
        except Exception:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
            raise
        logger.info("LLM 设置文件已自动生成: %s", settings_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM 设置文件: %s", e)


def _ensure_llm_providers_file() -> None:
    """若 llm_providers.json 不存在，用默认值自动创建。"""
    providers_path = _get_llm_providers_path()
    if os.path.exists(providers_path):
        return
    try:
        os.makedirs(os.path.dirname(providers_path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(providers_path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_get_default_llm_providers_template())
            os.replace(tmp_path, providers_path)
        except Exception:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
            raise
        logger.info("LLM Provider 配置文件已自动生成: %s", providers_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM Provider 配置文件: %s", e)


def get_llm_settings_path() -> str:
    """返回 LLM 非敏感配置文件的路径 (llm_settings.json)。"""
    config = get_config()
    return config.get("llm_settings_file") or os.path.join(PROJECT_ROOT, "data/config/llm_settings.json")


# ── LLM Provider 多链配置解析 ──────────────────────────────────

_LLM_PROVIDERS_FILE_DEFAULT = os.path.join(PROJECT_ROOT, "data/config/llm_providers.json")
_LLM_KEY_FILE_DEFAULT = os.path.join(PROJECT_ROOT, "data/config/llm_key.json")


def _get_llm_providers_path() -> str:
    """返回 llm_providers.json 路径（优先读取 config.json 配置）。"""
    try:
        from src.python.config import get_config

        config = get_config()
        return config.get("llm_providers_file") or _LLM_PROVIDERS_FILE_DEFAULT
    except Exception:
        return _LLM_PROVIDERS_FILE_DEFAULT


def _get_llm_key_path() -> str:
    """返回 llm_key.json 路径（优先读取 config.json 配置）。"""
    try:
        from src.python.config import get_config

        config = get_config()
        return config.get("llm_key_file") or _LLM_KEY_FILE_DEFAULT
    except Exception:
        return _LLM_KEY_FILE_DEFAULT


_VALID_LLM_PROVIDER_TYPES = frozenset({"claude", "openai", "gemini"})
_VALID_STRATEGIES = frozenset({"priority", "weighted", "cost_first", "fallback_only"})


def _load_llm_providers() -> dict | None:
    """读取 data/config/llm_providers.json，不存在或格式异常返回 None。

    Returns:
        dict: 原始 JSON 解析结果，或 None（文件不存在/JSON 解析失败）
    """
    if not os.path.exists(_get_llm_providers_path()):
        return None
    try:
        with open(_get_llm_providers_path(), encoding="utf-8-sig") as f:
            config = json.loads(_comments._strip_json_comments(f.read()))
        if not isinstance(config, dict):
            logger.warning("LLM providers 文件根元素不是 JSON 对象，已忽略")
            return None
        return config
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("LLM providers 文件读取失败: %s", e)
        return None


def _load_llm_key_credentials() -> dict[str, dict] | None:
    """读取 llm_key.json 为多键凭据字典。

    多凭据格式：
      {"claude-main": {"api_key": "sk-...", "model": "..."}, "openai-fb": {"api_key": "..."}}

    单凭据格式（自动升级）：
      {"api_key": "sk-...", "model": "claude-sonnet-4-..."}
      → 自动包裹为 {"_default": {"api_key": "...", "model": "..."}}

    Returns:
        {ref_name: {api_key, model?, endpoint?}} 或 None（文件不存在/解析失败）
    """
    if not os.path.exists(_get_llm_key_path()):
        return None
    try:
        with open(_get_llm_key_path(), encoding="utf-8-sig") as f:
            raw = json.loads(_comments._strip_json_comments(f.read()))
        if not isinstance(raw, dict):
            logger.warning("llm_key.json 根元素不是 JSON 对象，已忽略")
            return None
        # 格式检测：顶层有 "api_key" 字符串键 → 单凭据格式
        if isinstance(raw.get("api_key"), str):
            return {"_default": raw}
        # 多凭据格式：校验每项是 dict
        for ref_name, creds in raw.items():
            if not isinstance(creds, dict):
                logger.warning("llm_key.json 中 '%s' 的值不是 JSON 对象，已忽略", ref_name)
        return raw
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("llm_key.json 读取失败: %s", e)
        return None


def _parse_providers_list(raw_config: dict) -> list[dict] | None:
    """解析 llm_providers.json 中的 providers 数组，校验并补齐默认值。

    Args:
        raw_config: _load_llm_providers() 返回的原始 dict

    Returns:
        校验通过且补齐默认值后的 provider dict 列表，或 None（无有效 provider）
    """
    providers = raw_config.get("providers")
    if not providers or not isinstance(providers, list):
        logger.warning("LLM providers 配置中 providers 字段缺失或不是数组")
        return None
    if len(providers) == 0:
        logger.warning("LLM providers 配置中 providers 数组为空")
        return None

    validated: list[dict] = []
    seen_names: set[str] = set()
    for i, entry in enumerate(providers):
        if not isinstance(entry, dict):
            logger.warning("LLM providers[%d] 不是字典对象，已跳过", i)
            continue
        errs = _validate_provider_entry(entry, i)
        if errs:
            for e in errs:
                logger.warning("LLM providers[%d] 校验不通过: %s", i, e)
            continue
        name = entry["name"]
        if name in seen_names:
            logger.warning("LLM providers 中存在重复 name '%s'，后者覆盖前者", name)
        seen_names.add(name)
        entry_dict: dict = {
            "name": name,
            "provider": entry["provider"],
            "endpoint": entry.get("endpoint"),
            "priority": entry.get("priority", 99),
            "weight": entry.get("weight", 1),
            "timeout": float(entry.get("timeout", 60.0)),
            "proxy_preferred": entry.get("proxy_preferred", False),
        }
        # 凭据来源：credentials_ref 或内嵌 api_key/model
        if entry.get("credentials_ref"):
            entry_dict["credentials_ref"] = entry["credentials_ref"]
        else:
            entry_dict["api_key"] = entry["api_key"].strip()
            entry_dict["model"] = entry["model"]
        validated.append(entry_dict)

    if not validated:
        logger.warning("LLM providers 全部校验未通过，无有效 provider")
        return None
    return validated


def _validate_provider_entry(entry: dict, index: int) -> list[str]:
    """校验单个 provider 配置条目。

    Args:
        entry: provider dict
        index: 在 providers 数组中的索引（用于错误消息）

    Returns:
        WARNING 消息列表，空列表表示完全通过
    """
    warnings: list[str] = []

    # name
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        warnings.append("缺少必填字段 'name' 或格式非法（须为非空字符串）")

    # provider type
    provider_type = entry.get("provider")
    if provider_type not in _VALID_LLM_PROVIDER_TYPES:
        warnings.append(f"provider 类型 '{provider_type}' 无效（有效值: claude/openai/gemini）")

    has_creds_ref = bool(entry.get("credentials_ref"))

    # api_key — 无 credentials_ref 时必填
    api_key = entry.get("api_key")
    if not has_creds_ref:
        if not isinstance(api_key, str) or not api_key.strip():
            warnings.append("缺少必填字段 'api_key' 或格式非法（须为非空字符串）")

    # model — 无 credentials_ref 时必填
    model = entry.get("model")
    if not has_creds_ref:
        if not isinstance(model, str) or not model.strip():
            warnings.append("缺少必填字段 'model' 或格式非法（须为非空字符串）")

    # credentials_ref 格式检查
    if has_creds_ref:
        if not isinstance(entry["credentials_ref"], str) or not entry["credentials_ref"].strip():
            warnings.append("'credentials_ref' 须为非空字符串")

    # optional: endpoint
    endpoint = entry.get("endpoint")
    if endpoint is not None and not isinstance(endpoint, str):
        warnings.append("可选字段 'endpoint' 类型非法（须为字符串或 null）")

    return warnings


def _inject_provider_chain_data(config: dict) -> dict:
    """向 LLM config dict 中注入多 Provider 链数据：_provider_list / _strategy / _preferred_providers。

    校验：
      - strategy 值在 {"priority","weighted","cost_first","fallback_only"} 中
      - preferred_providers 中的 name 必须在 provider_list 中存在

    注意：此函数修改传入的 dict 并返回之。
    """
    raw_providers = _load_llm_providers()
    if raw_providers is None:
        config["_provider_list"] = None
        config["_strategy"] = "priority"
        config["_preferred_providers"] = {}
        return config

    provider_list = _parse_providers_list(raw_providers)
    config["_provider_list"] = provider_list

    # strategy
    strategy = raw_providers.get("strategy", "priority")
    if strategy not in _VALID_STRATEGIES:
        logger.warning(
            "LLM providers strategy '%s' 无效，回退到 'priority'（有效值: %s）",
            strategy,
            "/".join(sorted(_VALID_STRATEGIES)),
        )
        strategy = "priority"
    config["_strategy"] = strategy

    # preferred_providers
    preferred = raw_providers.get("preferred_providers", {})
    if not isinstance(preferred, dict):
        logger.warning("LLM providers preferred_providers 不是 dict，已忽略")
        preferred = {}
    elif provider_list is not None:
        valid_names = {p["name"] for p in provider_list}
        for module_key, name in list(preferred.items()):
            if name not in valid_names:
                logger.warning(
                    "LLM providers preferred_providers['%s']='%s' 不在 provider 列表中，已忽略", module_key, name
                )
                preferred.pop(module_key, None)
    config["_preferred_providers"] = preferred

    # ── 凭据引用注入 _llm_credentials ──
    credentials = _load_llm_key_credentials()
    if credentials:
        config["_llm_credentials"] = credentials
        # 检查 provider_list 中 credentials_ref 的可解析性
        provider_list = config.get("_provider_list")
        if provider_list:
            for entry in provider_list:
                ref = entry.get("credentials_ref")
                if ref and ref not in credentials:
                    logger.warning(
                        "provider '%s' 引用凭据 '%s' 在 llm_key.json 中不存在",
                        entry["name"],
                        ref,
                    )

    return config


def get_llm_config() -> dict | None:
    """读取 LLM 配置（合并 llm_settings.json + llm_key.json + llm_providers.json）。"""
    global _llm_config_cache, _llm_config_mtime, _llm_config_size

    with _llm_config_lock:
        base_settings: dict = {}
        settings_mtime: float = 0
        settings_path = get_llm_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, encoding="utf-8-sig") as f:
                    raw = f.read()
                    cleaned = _comments._strip_json_comments(raw)
                    base_settings = json.loads(cleaned)
                settings_mtime = os.path.getmtime(settings_path)
                if _llm_config_cache is None and base_settings:
                    _check_unknown_llm_keys(base_settings)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("LLM 设置文件读取失败: %s", e)

        if not os.path.exists(_get_llm_key_path()):
            logger.warning("LLM 密钥文件不存在: %s", _get_llm_key_path())
            if base_settings.get("api_key"):
                base_settings["api_key"] = base_settings["api_key"].strip()
                base_settings["debate"] = _load_debate_config(base_settings)
                _llm_config_cache = _inject_provider_chain_data(base_settings)
                _llm_config_mtime = 0
                _llm_config_size = 0
                return _llm_config_cache
            # 检查 llm_providers.json 是否有 provider（链模式可不依赖 llm_key.json）
            raw_providers = _load_llm_providers()
            if raw_providers and raw_providers.get("providers"):
                base_settings["debate"] = _load_debate_config(base_settings)
                _llm_config_cache = _inject_provider_chain_data(base_settings)
                _llm_config_mtime = 0
                _llm_config_size = 0
                return _llm_config_cache
            _llm_config_cache = None
            return None

        try:
            key_mtime = os.path.getmtime(_get_llm_key_path())
            key_size = os.path.getsize(_get_llm_key_path())
            settings_size = os.path.getsize(settings_path) if os.path.exists(settings_path) else 0
            combined_mtime = max(key_mtime, settings_mtime)
            combined_size = key_size + settings_size

            if (
                _llm_config_cache is not None
                and combined_mtime <= _llm_config_mtime
                and combined_size == _llm_config_size
            ):
                return _llm_config_cache

            with open(_get_llm_key_path(), encoding="utf-8-sig") as f:
                key_raw = f.read()
                key_config = json.loads(_comments._strip_json_comments(key_raw))

            provider = key_config.get("provider", "")
            endpoint = key_config.get("endpoint", "")
            if provider and provider not in ("claude", "openai", "gemini"):
                logger.warning("llm_key.json provider = '%s' 不是有效值（claude/openai/gemini）", provider)
            if endpoint and not endpoint.startswith("http"):
                logger.warning("llm_key.json endpoint = '%s' 不是有效 URL", endpoint)

            merged = dict(base_settings)
            merged.update(key_config)
            merged["debate"] = _load_debate_config(merged)
            if merged.get("api_key"):
                merged["api_key"] = merged["api_key"].strip()

            _inject_provider_chain_data(merged)
            _llm_config_cache = merged
            _llm_config_mtime = combined_mtime
            _llm_config_size = combined_size
            return merged
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("LLM 密钥文件读取失败: %s", e)
            _llm_config_cache = None
            return None
