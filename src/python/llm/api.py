"""LLM API 调用模块 — 核心请求、重试、Provider 路由、截断检测。"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Optional
import httpx

from src.python.llm.circuit_breaker import (
    _cb_endpoint,
    _cb_is_open,
    _cb_record_failure,
    _cb_record_success,
)
from src.python.llm.pricing import _estimate_cost
from src.python.llm.session import _track_session_usage

logger = logging.getLogger("invest")

__all__ = [
    "_LLM_TIMEOUT", "_RETRY_DELAYS", "_TRUNCATION_MARKER", "_AUTO_INCREASE_FACTOR",
    "_CONTENT_FILTER_RECOVERY", "_TOKEN_LINE_RE", "_CACHE_LINE_HTML", "_CACHE_LINE_MODEL_TPL",
    "_MODEL_LINE_RE", "_THINKING_SUPPORTED_PREFIXES", "_THINKING_EFFORT_MODEL_PREFIXES",
    "_supports_extended_thinking", "_is_effort_model", "_truncation_warning",
    "_check_claude_truncation", "_check_openai_truncation", "_extract_content",
    "_strip_token_line", "_extract_model_from_cached", "_log_token_usage",
    "_get_retry_max", "_sanitize_endpoint",
    "_call_llm_with_retry", "_call_single_provider", "_call_llm", "_call_claude", "_call_openai",
]

# ── 默认超时 ─────────────────────────────────────────────────

_LLM_TIMEOUT = 120.0

# ── 重试配置 ─────────────────────────────────────────────────

_RETRY_DELAYS = [1.0, 3.0, 5.0, 10.0, 15.0]  # 指数退避：第 1~5 次依次等待

# ── 输出截断自适应重试 ────────────────────────────────

_TRUNCATION_MARKER = "【⚠ 输出已被截断"
"""截断警告中的唯一标记，用于检测输出是否被 max_tokens 截断。"""

_AUTO_INCREASE_FACTOR = 1.5
"""截断时自动增大的倍数。"""

# ── 内容过滤安抚重试 ────────────────────────────────

_CONTENT_FILTER_RECOVERY = (
    "\n\n注意：请确保你的回答包含实质性的分析内容。"
    "如果前一版本未输出任何内容，请提供完整的分析结果。"
    "所有数据均基于公开市场信息，请客观分析即可。"
)
"""当 API 返回空内容（可能被内容过滤机制拦截）时，
追加到 system prompt 尾部重新请求。"""


# ── 缓存行定义 ────────────────────────────────────

_TOKEN_LINE_RE = re.compile(
    r'<p style="color:#888;font-size:12px">[^<]*Token 用量[^<]*</p>'
)
"""匹配旧版和新版 Token 用量行。"""

_CACHE_LINE_HTML = (
    '<p style="color:#888;font-size:12px">'
    "本次使用LLM缓存，未直接使用LLM服务能力"
    "</p>"
)
"""缓存命中的 HTML 提示行。"""

_CACHE_LINE_MODEL_TPL = (
    '<p style="color:#888;font-size:12px">'
    "本次使用LLM缓存（原始模型：{model}）"
    "</p>"
)
"""含原始模型名称的缓存提示行模板。"""

_MODEL_LINE_RE = re.compile(r'模型[：:]\s*([^|<\s][^|]*)')
"""从 token 行中提取模型名称的正则。"""


# ── Extended Thinking 模型兼容性名单 ──

_THINKING_SUPPORTED_PREFIXES = ("claude-sonnet-4", "claude-opus-4", "deepseek-v4-", "deepseek-chat")

# 使用 output_config.effort（而非 thinking.budget_tokens）控制思考深度的模型。
_THINKING_EFFORT_MODEL_PREFIXES = ("deepseek-v4-", "deepseek-chat")


def _supports_extended_thinking(model: str) -> bool:
    """检查模型是否支持 Extended Thinking。"""
    return any(model.lower().startswith(p) for p in _THINKING_SUPPORTED_PREFIXES)


def _is_effort_model(model: str) -> bool:
    """检查模型是否使用 effort（而非 budget_tokens）控制思考深度。"""
    return any(model.lower().startswith(p) for p in _THINKING_EFFORT_MODEL_PREFIXES)


def _truncation_warning(config_field: str) -> str:
    """生成截断警告，指明 llm_settings.json 中需要增大的具体配置项。"""
    return (
        f"\n\n{_TRUNCATION_MARKER}！{config_field} 上限不足，内容不完整。"
        f"请在 data/config/llm_settings.json 中增大 {config_field} 后重新生成。】"
    )


def _check_claude_truncation(data: dict, max_tokens: int, label: str, config_field: str = "max_tokens") -> bool:
    """检查 Claude Messages API 响应是否被 max_tokens 截断。

    若 stop_reason 为 "max_tokens"，说明输出达到 token 上限被截断，
    记录 ERROR 日志。由调用方决定是否在内容后附加警告。
    """
    stop_reason = data.get("stop_reason")
    if stop_reason == "max_tokens":
        out_tokens = (data.get("usage") or {}).get("output_tokens", 0)
        logger.error(
            "LLM 输出被截断 [%s]: %s=%d, 实际输出=%d tokens。"
            "内容不完整，请在 llm_settings.json 中增大 %s",
            label, config_field, max_tokens, out_tokens, config_field,
        )
        return True
    return False


def _check_openai_truncation(data: dict, max_tokens: int, label: str, config_field: str = "max_tokens") -> bool:
    """检查 OpenAI Chat Completions 响应是否被 max_tokens 截断。

    finish_reason 为 "length" 表示达到 token 上限被截断。
    """
    try:
        finish_reason = data["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError):
        return False
    if finish_reason == "length":
        out_tokens = (data.get("usage") or {}).get("completion_tokens", 0)
        logger.error(
            "LLM 输出被截断 [%s]: %s=%d, 实际输出=%d tokens。"
            "内容不完整，请在 llm_settings.json 中增大 %s",
            label, config_field, max_tokens, out_tokens, config_field,
        )
        return True
    return False


def _extract_content(data: dict) -> str | None:
    """从 Anthropic Messages API 兼容响应中提取文本内容。

    兼容标准 Claude 格式及 DeepSeek Anthropic 兼容端点等多种格式变体。
    会遍历 content 列表中所有 text block 并拼接返回。

    Returns:
        str: 提取的文本内容
        None: 响应格式异常或内容被过滤
    """
    # API 返回了错误信息
    if data and "error" in data:
        logger.warning("LLM API 返回错误: %s", data["error"])
        return None

    try:
        content_field = data.get("content")
    except (AttributeError, TypeError):
        return None

    # content 为字符串（部分兼容实现）
    if isinstance(content_field, str):
        return content_field

    # content 为列表：提取所有 text block 并拼接
    if isinstance(content_field, list):
        texts = []
        for block in content_field:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    texts.append(text)
                elif block.get("type") == "text" and block.get("text"):
                    texts.append(str(block["text"]))
        if texts:
            return "\n".join(texts)
        # content 列表为空或只有 non-text block（如 thinking / redacted_thinking）
        # 可能是内容被过滤，返回空字符串而非 None 以便上层做针对性处理
        if not texts and content_field:
            return ""
        return ""  # 空列表也视为空内容而非格式异常

    return None


def _strip_token_line(html: str) -> str:
    """从缓存的 HTML 中剥离旧的 Token 用量行。"""
    return _TOKEN_LINE_RE.sub("", html).strip()


def _extract_model_from_cached(html: str) -> str:
    """从缓存的 HTML 中提取原始模型名称。"""
    m = _MODEL_LINE_RE.search(html)
    return m.group(1).strip() if m else ""


def _log_token_usage(provider: str, usage: dict | None, label: str, model_name: str = "") -> None:
    """记录 LLM API 调用的 token 使用量，可选估算费用。

    Args:
        provider: "claude" 或 "openai"
        usage: API 响应中的 usage 字典
        label: 调用标签（如 "全球政经局势"）
        model_name: 模型名称（用于费用估算，可空）
    """
    if not usage:
        return
    if provider == "claude":
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        cache_hit = usage.get("cache_read_input_tokens", 0)
    else:
        inp = usage.get("prompt_tokens", 0)
        out = usage.get("completion_tokens", 0)
        cache_hit = 0
    total = inp + out
    msg = f"  [LLM] {label}: 输入 {inp:,} + 输出 {out:,} = {total:,} tokens"
    if cache_hit:
        msg += f" (缓存命中 {cache_hit:,})"
    if model_name:
        _cost = _estimate_cost(model_name, inp, out, cache_hit_input_tokens=cache_hit)
        if _cost != "-":
            msg += f" | 估算费用: {_cost}"
    print(msg)


def _get_retry_max(llm_config: dict) -> int:
    """从 llm_config 中读取最大重试次数，兜底返回 2。"""
    try:
        val = int(llm_config.get("max_retries", 2))
        return max(0, val)
    except (TypeError, ValueError):
        return 2


def _sanitize_endpoint(endpoint: str) -> str:
    """从 endpoint URL 中提取纯域名，避免路径/参数泄露到日志。"""
    try:
        return endpoint.split("/")[2] if endpoint else "unknown"
    except (IndexError, TypeError, AttributeError):
        return "unknown"


def _call_llm_with_retry(
    label: str,
    client: httpx.Client,
    url: str,
    headers: dict,
    payload: dict,
    timeout: float,
    max_retries: int,
    max_tokens: int,
    config_field: str,
    extract_fn: Callable[[dict], str | None],
    check_truncation_fn: Callable[[dict, int], bool],
    provider: str,
    model_name: str = "",
) -> tuple[Optional[str], Optional[dict]]:
    """LLM API 调用通用重试骨架。

    合并 _call_claude 和 _call_openai 中完全相同的重试/超时/错误处理逻辑。
    API 特有的部分（payload 构造、响应提取、截断检测）通过回调参数注入。

    Args:
        label: 显示名称（"Claude" / "OpenAI"），用于日志
        client: httpx 客户端实例
        url: API 端点 URL
        headers: HTTP 请求头
        payload: JSON 请求体
        timeout: 请求超时秒数
        max_retries: 最大重试次数
        max_tokens: 最大输出 token 数（用于截断日志）
        config_field: llm_settings.json 中的配置字段名（截断时提示用户）
        extract_fn: 从响应 dict 中提取文本内容的回调
        check_truncation_fn: 检查是否被截断的回调
        provider: 日志中的 provider 标识（"claude" / "openai"）
        model_name: 模型名称（用于费用估算，可空）

    Returns:
        (content, usage) — content 为文本，usage 为 API 用量字典，失败时均为 None
    """
    # ── 熔断器检查 ──
    if _cb_is_open(url):
        logger.warning("%s API 熔断中 (%s)，跳过本次请求", label, _cb_endpoint(url))
        print(f"  [!] {label} API 暂时不可用（熔断冷却中），跳过请求")
        return (None, None)

    for attempt in range(max_retries + 1):
        try:
            resp = client.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in (429, 503) and attempt < max_retries:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "%s API %d (尝试 %d/%d)，%.1fs 后重试...",
                    label, resp.status_code, attempt + 1, max_retries + 1, delay,
                )
                print(f"  [..] {label} API {resp.status_code} (第{attempt + 1}次重试, {delay:.0f}s后)...")
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            _cb_record_success(url)
        except httpx.TimeoutException:
            if attempt < max_retries:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "%s API 超时 (尝试 %d/%d)，%.1fs 后重试...",
                    label, attempt + 1, max_retries + 1, delay,
                )
                print(f"  [..] {label} API 超时 (第{attempt + 1}次重试, {delay:.0f}s后)...")
                time.sleep(delay)
                continue
            logger.warning("%s API 超时（已重试 %d 次）", label, max_retries)
            _cb_record_failure(url)
            return (None, None)
        except httpx.RequestError:
            host = _sanitize_endpoint(url)
            if attempt < max_retries:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "%s API 请求失败 (%s) (尝试 %d/%d)，%.1fs 后重试...",
                    label, host, attempt + 1, max_retries + 1, delay,
                )
                print(f"  [..] {label} API 网络错误 ({host}) (第{attempt + 1}次重试, {delay:.0f}s后)...")
                time.sleep(delay)
                continue
            logger.warning("%s API 请求失败 (%s)（已重试 %d 次）", label, host, max_retries)
            _cb_record_failure(url)
            return (None, None)
        except (ValueError, KeyError) as e:
            logger.warning("%s API 响应解析失败: %s", label, e)
            _cb_record_failure(url)
            return (None, None)

        content = extract_fn(data)
        if content is None:
            logger.warning("%s API 响应格式异常", label)
            _cb_record_failure(url)
            return (None, None)
        if not content.strip():
            logger.warning("%s API 返回空内容（可能被内容过滤机制拦截）", label)
            # 不记为熔断失败 — 保留 usage 信息供上层做安抚重试
            return ("", data.get("usage"))

        truncated = check_truncation_fn(data, max_tokens)
        usage = data.get("usage")
        _log_token_usage(provider, usage, label, model_name=model_name)
        _track_session_usage(provider, usage, model_name=model_name)

        content = content.strip()
        if truncated:
            content += _truncation_warning(config_field)

        return (content, usage)

    _cb_record_failure(url)
    return (None, None)


def _call_single_provider(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    resolved_model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float,
    max_retries: int,
    http_client: httpx.Client | None,
    config_field: str,
    temperature: float | None,
    llm_config: dict | None,
) -> tuple[Optional[str], Optional[dict]]:
    """调用单个 LLM provider。"""
    # 使用 lazy import 通过 llm_client 获取函数引用，
    # 确保 unittest.mock.patch("src.python.llm_client.XXX") 对测试生效
    import src.python.llm_client as _lm  # noqa: F811
    if provider == "claude":
        return _lm._call_claude(system_prompt, user_prompt, api_key, resolved_model, endpoint,
                                max_tokens, timeout, max_retries=max_retries,
                                http_client=http_client, config_field=config_field,
                                temperature=temperature, llm_config=llm_config)
    elif provider == "openai":
        return _lm._call_openai(system_prompt, user_prompt, api_key, resolved_model, endpoint,
                                max_tokens, timeout, max_retries=max_retries,
                                http_client=http_client, config_field=config_field,
                                temperature=temperature)
    else:
        logger.warning("不支持的 LLM provider: %s", provider)
        return (None, None)


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    llm_config: dict,
    timeout: float = 60.0,
    http_client: httpx.Client | None = None,
    max_tokens: int | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
    model: str | None = None,
) -> tuple[Optional[str], Optional[dict]]:
    """调用 LLM API 生成文本。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        llm_config: LLM 配置字典
        timeout: API 超时秒数，默认 60s
        http_client: 可选的 httpx.Client 实例
        max_tokens: 可选覆盖值，优先级高于 llm_config 中的对应字段
        config_field: llm_settings.json 中的配置字段名，截断时在日志中提示用户增大该字段
        temperature: 可选覆盖值，优先级高于 llm_config 中的对应字段，None 表示使用 API 默认值
        model: 可选模型覆盖，优先级高于 llm_config 中的 model 字段（用于 per-module 路由）

    Returns:
        (content, usage) — content 为文本，usage 为 API 用量字典，失败时均为 None
    """
    provider = llm_config.get("provider", "")
    api_key = llm_config.get("api_key", "")
    resolved_model = model or llm_config.get("model", "")
    endpoint = llm_config.get("endpoint", "")
    max_tokens = max_tokens or 2500
    max_retries = _get_retry_max(llm_config)

    # 使用 lazy import 通过 llm_client 获取 _call_single_provider，
    # 确保 unittest.mock.patch("src.python.llm_client._call_single_provider") 对测试生效
    import src.python.llm_client as _lm  # noqa: F811

    # ── 主 provider ──
    result, usage = _lm._call_single_provider(
        provider, system_prompt, user_prompt, api_key, resolved_model, endpoint,
        max_tokens, timeout, max_retries, http_client, config_field, temperature, llm_config,
    )
    if result is not None:
        if result != "":
            return result, usage
        # result == "" → 内容过滤导致空返回，尝试安抚重试
        logger.warning("%s API 返回空内容，追加安抚指令重试一次", provider)
        print(f"  [..] {provider} API 返回空内容，追加安抚指令重试...")
        calmed_system = system_prompt + _CONTENT_FILTER_RECOVERY
        result2, usage2 = _lm._call_single_provider(
            provider, calmed_system, user_prompt, api_key, resolved_model, endpoint,
            max_tokens, timeout, max_retries, http_client, config_field, temperature, llm_config,
        )
        if result2 and result2.strip():
            print(f"  [OK] 安抚重试成功")
            return result2, usage2
        logger.warning("安抚重试后仍返回空内容，继续尝试回退 provider")

    # ── 主 provider 失败 → 尝试回退 provider（若已配置） ──
    fallback_provider = llm_config.get("fallback_provider", "")
    if fallback_provider and fallback_provider != provider:
        fb_api_key = llm_config.get("fallback_api_key", api_key)
        fb_endpoint = llm_config.get("fallback_endpoint", endpoint)
        fb_model = llm_config.get("fallback_model", resolved_model)
        logger.warning("主 provider (%s) 已失败，回退到 %s", provider, fallback_provider)
        print(f"  [..] LLM 主 provider ({provider}) 失败，正在回退到 {fallback_provider}...")
        result, usage = _lm._call_single_provider(
            fallback_provider, system_prompt, user_prompt, fb_api_key, fb_model, fb_endpoint,
            max_tokens, timeout, max_retries, http_client, config_field, temperature, llm_config,
        )
        if result is not None:
            return result, usage
        logger.warning("回退 provider (%s) 同样失败", fallback_provider)

    return (None, None)


def _call_claude(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
    max_retries: int = 2,
    http_client: httpx.Client | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
    llm_config: dict | None = None,
) -> tuple[Optional[str], Optional[dict]]:
    """调用 Claude API (Messages API)，带重试 + 用量日志。

    实际 HTTP 重试逻辑委托给 _call_llm_with_retry。
    system prompt 使用数组格式 + cache_control 以支持 Anthropic Prompt Caching
    （同一 system prompt 在 5 分钟内多次调用时节省输入 token）。

    支持 Extended Thinking（thinking 参数），通过 llm_settings.json 中
    thinking_enabled_{模块} / thinking_budget_{模块} 配置开启。
    推荐仅在智囊团深度复盘（expert_review）场景开启，全球政经局势和新闻关联分析收益有限。
    若模型不支持 Extended Thinking（如 claude-sonnet-3-5），自动降级跳过。

    Args:
        max_retries: 最大重试次数，从 llm_config 读取
        temperature: 若不为 None，覆盖 payload 中的 temperature 字段
        llm_config: LLM 合并配置，用于读取 thinking 配置项

    Returns:
        (content, usage) — usage 为 API 返回的用量字典，失败时均为 None
    """
    url = endpoint or "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    # 数组格式 + cache_control 支持 Prompt Caching
    payload = {
        "model": model or "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }
    # ── Extended Thinking（根据模型类型 + 模块配置） ──
    if llm_config:
        _module_suffix = config_field.replace("max_tokens_", "")
        _thinking_key = f"thinking_enabled_{_module_suffix}"
        if llm_config.get(_thinking_key, False):
            _resolved_model = model or "claude-sonnet-4-20250514"
            if not _supports_extended_thinking(_resolved_model):
                logger.warning(
                    "模型 %s 不支持 Extended Thinking，已自动降级跳过 [%s]",
                    _resolved_model, _module_suffix,
                )
            else:
                payload["thinking"] = {"type": "enabled"}
                payload.pop("temperature", None)  # Extended Thinking 与 temperature 互斥
                if _is_effort_model(_resolved_model):
                    # DeepSeek 等：用 effort（high/max）控制思考深度
                    _effort_key = f"reasoning_effort_{_module_suffix}"
                    _effort = llm_config.get(_effort_key, "high")
                    payload["output_config"] = {"effort": _effort}
                    logger.info("Extended Thinking 已开启 [%s]: effort=%s", _module_suffix, _effort)
                else:
                    # Anthropic Claude：用 budget_tokens 控制
                    _budget_key = f"thinking_budget_{_module_suffix}"
                    _budget = llm_config.get(_budget_key)
                    if not _budget or _budget < max_tokens + 1024:
                        _budget = max_tokens + 4096  # 自动兜底
                    payload["thinking"]["budget_tokens"] = _budget
                    logger.info("Extended Thinking 已开启 [%s]: budget=%d", _module_suffix, _budget)
    if temperature is not None and "thinking" not in payload:
        payload["temperature"] = temperature
    client = http_client

    import src.python.llm_client as _lm  # noqa: F811
    return _lm._call_llm_with_retry(
        label="Claude", client=client, url=url, headers=headers,
        payload=payload, timeout=timeout, max_retries=max_retries,
        max_tokens=max_tokens, config_field=config_field,
        extract_fn=_extract_content,
        check_truncation_fn=lambda d, mt: _check_claude_truncation(d, mt, "Claude", config_field),
        provider="claude", model_name=model,
    )


def _call_openai(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
    max_retries: int = 2,
    http_client: httpx.Client | None = None,
    config_field: str = "max_tokens",
    temperature: float | None = None,
) -> tuple[Optional[str], Optional[dict]]:
    """调用 OpenAI API (Chat Completions)，带重试 + 用量日志。

    实际 HTTP 重试逻辑委托给 _call_llm_with_retry。

    Args:
        max_retries: 最大重试次数，从 llm_config 读取
        temperature: 若不为 None，覆盖 payload 中的 temperature 字段

    Returns:
        (content, usage) — usage 为 API 返回的用量字典，失败时均为 None
    """
    url = endpoint or "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model or "gpt-4o",
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    client = http_client

    def _extract_openai(data: dict) -> str | None:
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

    import src.python.llm_client as _lm  # noqa: F811
    return _lm._call_llm_with_retry(
        label="OpenAI", client=client, url=url, headers=headers,
        payload=payload, timeout=timeout, max_retries=max_retries,
        max_tokens=max_tokens, config_field=config_field,
        extract_fn=_extract_openai,
        check_truncation_fn=lambda d, mt: _check_openai_truncation(d, mt, "OpenAI", config_field),
        provider="openai", model_name=model,
    )
