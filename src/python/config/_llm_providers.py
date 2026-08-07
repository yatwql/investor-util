"""LLM Provider 多链配置解析。

职责范围：
  - llm_providers.json / llm_key.json 文件路径解析
  - Providers 列表加载、校验、反序列化
  - 凭据（llm_key.json）加载与格式升级
  - Provider 链数据注入函数
"""

from __future__ import annotations

import json
import logging
import os

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

_LLM_PROVIDERS_FILE_DEFAULT = os.path.join(PROJECT_ROOT, "data/config/llm_providers.json")
_LLM_KEY_FILE_DEFAULT = os.path.join(PROJECT_ROOT, "data/config/llm_key.json")

_VALID_LLM_PROVIDER_TYPES = frozenset({"claude", "openai", "gemini"})
_VALID_STRATEGIES = frozenset({"priority", "weighted", "cost_first", "fallback_only"})


def _get_llm_providers_path() -> str:
    """返回 llm_providers.json 路径（优先读取 config.json 配置）。"""
    try:
        from src.python.config import get_config

        config = get_config()
        return config.get("llm_providers_file") or _LLM_PROVIDERS_FILE_DEFAULT
    except (KeyError, TypeError, AttributeError):
        return _LLM_PROVIDERS_FILE_DEFAULT


def _get_llm_key_path() -> str:
    """返回 llm_key.json 路径（优先读取 config.json 配置）。"""
    try:
        from src.python.config import get_config

        config = get_config()
        return config.get("llm_key_file") or _LLM_KEY_FILE_DEFAULT
    except (KeyError, TypeError, AttributeError):
        return _LLM_KEY_FILE_DEFAULT


def _load_llm_providers() -> dict | None:
    """读取 data/config/llm_providers.json，不存在或格式异常返回 None。

    Returns:
        dict: 原始 JSON 解析结果，或 None（文件不存在/JSON 解析失败）
    """
    from src.python.config import _comments

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
    from src.python.config import _comments

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


def _validate_provider_entry(entry: dict) -> list[str]:
    """校验单个 provider 配置条目。

    Args:
        entry: provider dict

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
        errs = _validate_provider_entry(entry)
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
        # 凭据来源：credentials_ref 引用或内嵌 api_key/model（运行时宽容读取）
        if entry.get("credentials_ref"):
            entry_dict["credentials_ref"] = entry["credentials_ref"]
        else:
            # 保留内嵌字段供运行时直接读取（api.py 内联回退）
            logger.warning(
                "provider '%s' 内嵌 api_key，建议迁移到 llm_key.json 并使用 credentials_ref 引用",
                name,
            )
            entry_dict["api_key"] = entry["api_key"].strip()
            entry_dict["model"] = entry["model"]
        validated.append(entry_dict)

    if not validated:
        logger.warning("LLM providers 全部校验未通过，无有效 provider")
        return None
    return validated


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
