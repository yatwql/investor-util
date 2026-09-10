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

    # 凭据分离：api_key 只能经 llm_key.json 的 credentials_ref 引用。
    # 本文件（llm_providers.json）受版本控制（.gitignore 白名单放行），
    # 内联 api_key 即「凭据随配置入库」——正是凭据分离约束禁止的泄露形态。
    # 仅在确实带了非空密钥时判定，空串/null 不产生噪音。
    api_key = entry.get("api_key")
    if isinstance(api_key, str) and api_key.strip():
        warnings.append(
            "禁止内联字段 'api_key'（凭据分离）——"
            "请将其写入 llm_key.json 的凭据块，并在本条目用 credentials_ref 引用"
        )

    # credentials_ref — 必填：凭据的唯一合法来源
    creds_ref = entry.get("credentials_ref")
    if not isinstance(creds_ref, str) or not creds_ref.strip():
        warnings.append("缺少必填字段 'credentials_ref' 或格式非法（须为非空字符串，指向 llm_key.json 中的凭据块）")

    # model / endpoint — 可选的非敏感路由字段（模板注释邀请按需修改），
    # 与凭据块同名键的关系见 llm/api._resolve_entry_credentials（entry 覆盖凭据块）。
    # 纯空白视同未设置（回落凭据块同名值），不因可选字段的空白而拒收整条——
    # 与 endpoint 的 falsy 语义保持一致。
    model = entry.get("model")
    if model is not None and not isinstance(model, str):
        warnings.append("可选字段 'model' 类型非法（须为字符串）")

    endpoint = entry.get("endpoint")
    if endpoint is not None and not isinstance(endpoint, str):
        warnings.append("可选字段 'endpoint' 类型非法（须为字符串或 null）")

    return warnings


def _parse_providers_list(raw_config: dict) -> list[dict] | None:
    """解析 llm_providers.json 中的 providers 数组，校验并补齐默认值。

    凭据边界（凭据分离）：本函数是「配置文件 → 运行期条目」的唯一入口，
    条目只携带 `credentials_ref`（凭据引用）与非敏感路由字段（model/endpoint/
    priority/…）；**api_key 不由此处传入**（内联 api_key 在校验阶段即被拒），
    运行期凭据由 `_inject_provider_chain_data` 注入的 `_llm_credentials` 解析。

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
        # 凭据唯一来源：credentials_ref → llm_key.json 凭据块（凭据分离）
        entry_dict["credentials_ref"] = entry["credentials_ref"]
        # model 为非敏感路由覆盖（模板注释邀请按需修改）；缺省时由凭据块提供。
        # 传空串会让 _resolve_entry_credentials 的 falsy 判断回落到凭据块，故仅在
        # 非空时写入。
        model = entry.get("model")
        if isinstance(model, str) and model.strip():
            entry_dict["model"] = model.strip()
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
