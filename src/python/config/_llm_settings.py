"""LLM 设置解析 — llm_settings.json 读取/合并/校验与 LLM 配置缓存。

职责范围：
  - llm_settings.json 路径解析、读取、未知键校验
  - 与 llm_key.json / llm_providers.json 合并为完整 LLM 配置（get_llm_config）
  - debate 配置段解析（_load_debate_config）
  - LLM 配置内存缓存与失效（get_llm_config / invalidate_llm_config_cache）
  - LLM 分析章节可见性（is_enable_llm）

与 _llm_providers.py 分工：providers 多链解析与凭据注入在 _llm_providers.py，
本模块负责 llm_settings.json 侧的合并入口，并在运行时调用 providers 注入。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from typing import Any

from src.python.config import _comments, _llm_providers
from src.python.config._llm_defaults import _DEFAULT_LLM_SETTINGS, _get_default_llm_settings_template
from src.python.core.constants import PROJECT_ROOT
from src.python.core.registry import get_known_llm_settings_keys

logger = logging.getLogger("invest")

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
    "max_total_tokens_per_report": 48000,
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


def _merge_llm_defaults(base: dict) -> dict:
    """默认值打底 + 用户覆盖合并；null 不覆盖；dict 键一层合并；未知键透传。

    与 get_config 的 config.json 合并策略一致：
      - 用户显式写 null 时不覆盖默认值（null 不覆盖）
      - 嵌套 dict（enabled_llm / fact_check / pricing 等）一层合并，
        允许用户只覆盖部分子键而不丢失默认值
      - 默认中不存在的键原样透传（未知键透传，供消费端自定义字段使用）

    debate 段保留默认值作为合并底（_load_debate_config 会对每个子键做
    schema 校验并以 _DEBATE_CONFIG_DEFAULTS 兜底），此处不特殊处理。

    Args:
        base: 从 llm_settings.json 解析的用户配置字典。

    Returns:
        合并默认值后的完整配置字典（含全部默认键，消费端 .get() 可直接取值）。
    """
    merged = copy.deepcopy(_DEFAULT_LLM_SETTINGS)
    for key, val in base.items():
        if val is None and key in merged:
            continue
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = {**merged[key], **val}
        else:
            merged[key] = val
    return merged


def _ensure_llm_settings_file() -> None:
    """若 llm_settings.json 不存在，用默认值自动创建。"""
    from src.python.config._core import _atomic_write, get_config

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


def get_llm_settings_path() -> str:
    """返回 LLM 非敏感配置文件的路径 (llm_settings.json)。"""
    from src.python.config._core import get_config

    config = get_config()
    return config.get("llm_settings_file") or os.path.join(PROJECT_ROOT, "data/config/llm_settings.json")


def invalidate_llm_config_cache() -> None:
    """使 LLM 配置缓存失效，下次 get_llm_config() 自动重读。"""
    global _llm_config_cache, _llm_config_mtime, _llm_config_size
    with _llm_config_lock:
        _llm_config_cache = None
        _llm_config_mtime = 0
        _llm_config_size = 0


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
                # 运行时补默认：llm_settings.json 缺失的键按 _DEFAULT_LLM_SETTINGS 兜底，
                # 消除消费端 .get() 硬编码兜底与模板默认值之间的两套默认值漂移。
                if base_settings:
                    base_settings = _merge_llm_defaults(base_settings)
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
