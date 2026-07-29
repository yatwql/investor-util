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

from src.python.config import _comments, _config_defaults, _llm_providers
from src.python.config._llm_defaults import _get_default_llm_settings_template
from src.python.config._llm_providers_defaults import _get_default_llm_providers_template
from src.python.constants import PROJECT_ROOT
from src.python.registry import get_known_llm_settings_keys
from src.python.config._validation import _absolutize_paths, validate_config

# 从 _llm_providers 模块再导出（保持向后兼容，供测试导入）
from src.python.config._llm_providers import (
    _get_llm_key_path,
    _get_llm_providers_path,
    _inject_provider_chain_data,
    _load_llm_key_credentials,
    _load_llm_providers,
    _parse_providers_list,
    _validate_provider_entry,
)

logger = logging.getLogger("invest")


def _atomic_write(filepath: str, content: str) -> None:
    """原子写入文件：先写临时文件再 os.replace。

    Args:
        filepath: 目标文件路径
        content: 要写入的字符串内容
    """
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filepath), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


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


def invalidate_config_cache() -> None:
    """使 config.json 缓存失效，下次 get_config() 自动重读。"""
    global _config_cache, _config_mtime, _config_size
    with _config_lock:
        _config_cache = None
        _config_mtime = 0
        _config_size = 0


def invalidate_llm_config_cache() -> None:
    """使 LLM 配置缓存失效，下次 get_llm_config() 自动重读。"""
    global _llm_config_cache, _llm_config_mtime, _llm_config_size
    with _llm_config_lock:
        _llm_config_cache = None
        _llm_config_mtime = 0
        _llm_config_size = 0


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

    _atomic_write(config_path, json.dumps(config, ensure_ascii=False, indent=2))

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
    try:
        _atomic_write(config_path, _config_defaults._get_default_config_template())
    except PermissionError:
        # Windows 并发场景：另一线程/进程已创建文件，清理自身临时文件后继续
        if os.path.exists(config_path):
            config = get_config()
            validate_config(config)
            return
        raise  # 文件确实不存在，重新抛出
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
    缺失时返回 True（默认启用）。

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
            "llm_settings.json 中检测到 %d 个未知配置项，可能是拼写错误或无法识别的配置项: %s。请核对后删除，避免混淆。",
            len(unknown),
            ", ".join(repr(k) for k in sorted(unknown)),
        )


_DEBATE_CONFIG_DEFAULTS: dict[str, Any] = {
    "procon": {
        "per_call_max_tokens": None,
        "synthesis_model": None,
        "synthesis_temperature": 0.5,
    },
    "conditional": {
        "scenarios": [
            {"name": "上涨", "change": 0.20, "desc": "如果未来市场上涨 20%"},
            {"name": "下跌", "change": -0.20, "desc": "如果未来市场下跌 20%"},
            {"name": "震荡", "change": 0.05, "desc": "如果未来市场窄幅震荡±5%"},
        ],
    },
    "qa_concentration": {
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

    # procon（正反辩论配置）
    raw_procon = raw_debate.get("procon")
    if isinstance(raw_procon, dict):
        if isinstance(raw_procon.get("per_call_max_tokens"), (int, float)) and raw_procon["per_call_max_tokens"] > 0:
            merged["procon"]["per_call_max_tokens"] = raw_procon["per_call_max_tokens"]
        elif raw_procon.get("per_call_max_tokens") is not None:
            logger.warning("[debate] procon.per_call_max_tokens 应为正数或 null，使用默认值 None")
        if isinstance(raw_procon.get("synthesis_model"), str) and raw_procon["synthesis_model"].strip():
            merged["procon"]["synthesis_model"] = raw_procon["synthesis_model"].strip()
        if isinstance(raw_procon.get("synthesis_temperature"), (int, float)):
            if 0.0 <= raw_procon["synthesis_temperature"] <= 2.0:
                merged["procon"]["synthesis_temperature"] = raw_procon["synthesis_temperature"]
            else:
                logger.warning("[debate] procon.synthesis_temperature 应在 [0.0, 2.0] 范围，使用默认值 0.5")

    # conditional（条件推理配置）
    raw_conditional = raw_debate.get("conditional")
    if isinstance(raw_conditional, dict):
        raw_scenarios = raw_conditional.get("scenarios")
        if isinstance(raw_scenarios, list) and raw_scenarios:
            validated: list[dict] = []
            for idx, s in enumerate(raw_scenarios):
                if isinstance(s, dict) and "name" in s and "desc" in s:
                    validated.append({"name": str(s["name"]), "change": s.get("change", 0.0), "desc": str(s["desc"])})
                else:
                    logger.warning("[debate] conditional.scenarios[%d] 格式无效，已跳过", idx)
            if validated:
                merged["conditional"]["scenarios"] = validated
            else:
                logger.warning("[debate] conditional.scenarios 全部无效，使用默认情景")

    # qa_concentration（集中度问答配置）
    raw_qa = raw_debate.get("qa_concentration")
    if isinstance(raw_qa, dict):
        raw_threshold = raw_qa.get("threshold")
        if isinstance(raw_threshold, (int, float)) and 0.0 < raw_threshold < 1.0:
            merged["qa_concentration"]["threshold"] = raw_threshold
        elif raw_threshold is not None:
            logger.warning("[debate] qa_concentration.threshold 应在 (0, 1) 范围，使用默认值 0.20")

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
        _atomic_write(settings_path, _get_default_llm_settings_template())
        logger.info("LLM 设置文件已自动生成: %s", settings_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM 设置文件: %s", e)


def _ensure_llm_providers_file() -> None:
    """若 llm_providers.json 不存在，用默认值自动创建。"""
    providers_path = _llm_providers._get_llm_providers_path()
    if os.path.exists(providers_path):
        return
    try:
        os.makedirs(os.path.dirname(providers_path), exist_ok=True)
        _atomic_write(providers_path, _get_default_llm_providers_template())
        logger.info("LLM Provider 配置文件已自动生成: %s", providers_path)
    except OSError as e:
        logger.warning("无法自动创建 LLM Provider 配置文件: %s", e)


def get_llm_settings_path() -> str:
    """返回 LLM 非敏感配置文件的路径 (llm_settings.json)。"""
    config = get_config()
    return config.get("llm_settings_file") or os.path.join(PROJECT_ROOT, "data/config/llm_settings.json")


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

        if not os.path.exists(_llm_providers._get_llm_key_path()):
            logger.warning(
                "LLM 密钥文件不存在: %s。请配置 llm_key.json 或使用 llm_providers.json 多链模式",
                _llm_providers._get_llm_key_path(),
            )
            # 检查 llm_providers.json 是否有 provider（链模式可不依赖 llm_key.json）
            raw_providers = _llm_providers._load_llm_providers()
            if raw_providers and raw_providers.get("providers"):
                base_settings["debate"] = _load_debate_config(base_settings)
                _llm_config_cache = _llm_providers._inject_provider_chain_data(base_settings)
                _llm_config_mtime = 0
                _llm_config_size = 0
                return _llm_config_cache
            _llm_config_cache = None
            return None

        try:
            key_mtime = os.path.getmtime(_llm_providers._get_llm_key_path())
            key_size = os.path.getsize(_llm_providers._get_llm_key_path())
            settings_size = os.path.getsize(settings_path) if os.path.exists(settings_path) else 0
            combined_mtime = max(key_mtime, settings_mtime)
            combined_size = key_size + settings_size

            if (
                _llm_config_cache is not None
                and combined_mtime <= _llm_config_mtime
                and combined_size == _llm_config_size
            ):
                return _llm_config_cache

            with open(_llm_providers._get_llm_key_path(), encoding="utf-8-sig") as f:
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

            _llm_providers._inject_provider_chain_data(merged)
            _llm_config_cache = merged
            _llm_config_mtime = combined_mtime
            _llm_config_size = combined_size
            return merged
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("LLM 密钥文件读取失败: %s", e)
            _llm_config_cache = None
            return None
