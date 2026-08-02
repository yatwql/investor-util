"""LLM API 基础模块 — 共享的常量、检测函数、失败追踪与重试骨架。

基础设施层（被 api.py / skeleton.py / generators 系列共用）。
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.python.llm.circuit_breaker import (
    _cb_endpoint,
    _cb_is_open,
    _cb_record_failure,
    _cb_record_success,
)
from src.python.llm.pricing import estimate_cost
from src.python.llm.prompts import (
    FAIL_REASON_API_ERROR,
    FAIL_REASON_CIRCUIT_OPEN,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_TIMEOUT,
)
from src.python.llm.session import record_per_module, track_session_usage

logger = logging.getLogger("invest")

__all__ = [
    "_last_llm_failure_reason",
    "clear_last_llm_failure",
    "_get_last_llm_failure",
    "_get_last_thinking_exhausted",
    "clear_last_thinking_exhausted",
    "LLM_TIMEOUT",
    "_RETRY_DELAYS",
    "TRUNCATION_MARKER",
    "AUTO_INCREASE_FACTOR",
    "CACHE_LINE_HTML",
    "_cache_line_model_tpl",
    "_MODEL_LINE_RE",
    "_THINKING_SUPPORTED_PREFIXES",
    "_THINKING_EFFORT_MODEL_PREFIXES",
    "_supports_extended_thinking",
    "_is_effort_model",
    "_truncation_warning",
    "_check_claude_truncation",
    "_check_openai_truncation",
    "_check_gemini_truncation",
    "_extract_content",
    "_extract_content_from_gemini",
    "_extract_model_from_cached",
    "_log_token_usage",
    "_get_retry_max",
    "_sanitize_endpoint",
    "_check_circuit_breaker",
    "_process_success_response",
    "_attempt_api_call",
    "_is_retry_available",
    "call_llm_with_retry",
]

# ── 上次失败的详细原因（供调用方区分失败类型，不改变函数签名） ──

_last_llm_failure_reason: str | None = None
"""最近一次 LLM API 调用失败的详细原因（FAIL_REASON_* 常量），成功调用后为 None。"""

# 思考耗尽标志使用线程局部存储：LLM 生成在 ThreadPoolExecutor(llm_max_concurrency=3)
# 下并发执行（generators_orchestrator），若用模块级全局会被其他线程 _extract_content 的
# 无条件复位踩踏，导致 call_claude"关闭 thinking 重试"安全网静默失效。
_thinking_exhausted_local = threading.local()
"""线程局部的思考耗尽标志。

仅由 _extract_content 设置：`stop_reason == "max_tokens"` 且无任何 text block 时为 True，
其余路径复位为 False。供 call_claude 判断是否可用"关闭 thinking 重试"安全网兜底。
"""


def _set_last_thinking_exhausted(value: bool) -> None:
    """设置当前线程的思考耗尽标志。"""
    _thinking_exhausted_local.last = value


def clear_last_llm_failure() -> None:
    """清除上次失败原因记录。"""
    global _last_llm_failure_reason
    _last_llm_failure_reason = None


def _get_last_thinking_exhausted() -> bool:
    """返回当前线程最近一次响应提取是否因思考耗尽而空内容。"""
    return getattr(_thinking_exhausted_local, "last", False)


def clear_last_thinking_exhausted() -> None:
    """清除当前线程的思考耗尽标志（重试前复位）。"""
    try:
        del _thinking_exhausted_local.last
    except AttributeError:
        pass


def _get_last_llm_failure() -> str | None:
    """返回最近一次 LLM API 调用的失败原因，无失败时返回 None。"""
    return _last_llm_failure_reason


# ── 默认超时 ─────────────────────────────────────────────────

LLM_TIMEOUT = 120.0

# ── 重试配置 ─────────────────────────────────────────────────

_RETRY_DELAYS = [1.0, 3.0, 5.0, 10.0, 15.0]  # 指数退避：第 1~5 次依次等待

# ── 输出截断自适应重试 ────────────────────────────────

TRUNCATION_MARKER = "【⚠ 输出已被截断"
"""截断警告中的唯一标记，用于检测输出是否被 max_tokens 截断。"""

AUTO_INCREASE_FACTOR = 1.5
"""截断时自动增大的倍数。"""

# _CONTENT_FILTER_RECOVERY（留在 api.py，仅 _call_llm 使用 — 见复盘修正记录）


# ── 缓存行定义 ────────────────────────────────────

CACHE_LINE_HTML = '<p style="color:#888;font-size:12px">本次使用LLM缓存，未直接使用LLM服务能力</p>'
"""缓存命中的 HTML 提示行。"""


def _cache_line_model_tpl(model: str) -> str:
    """生成缓存命中提示行（含模型名）。"""
    return f'<p style="color:#888;font-size:12px">本次使用LLM缓存（原始模型：{model}）</p>'


def _build_cache_hint_and_record(
    cached: str,
    module_key: str,
    llm_config: dict,
    thinking_enabled: bool,
    endpoint: str = "",
    model_hint: str | None = None,
) -> str:
    """构建缓存 HTML 提示行并记录模块用量。

    统一 _handle_cache_hit 与 _precheck_one_cache 中的重复逻辑。

    Args:
        cached: 缓存的原始 HTML 内容
        module_key: 模块键名
        llm_config: LLM 配置
        thinking_enabled: 是否启用 Extended Thinking
        endpoint: API 端点（可为空字符串）
        model_hint: 模型名称提示（用于当缓存中无法提取模型名时回退）

    Returns:
        附加了缓存提示的 HTML 内容
    """
    orig_model = _extract_model_from_cached(cached)
    hint = _cache_line_model_tpl(orig_model) if orig_model else CACHE_LINE_HTML
    if thinking_enabled:
        hint = hint.rstrip().replace("</p>", " | Extended Thinking</p>", 1)
    if module_key:
        model_for_record = orig_model or model_hint or llm_config.get("model", "") or "缓存命中"
        endpoint_for_record = endpoint or llm_config.get("endpoint", "") or ""
        record_per_module(
            module_key, model_for_record, cached=True, thinking=thinking_enabled, endpoint=endpoint_for_record
        )
    return cached + hint


# 含原始模型名称的缓存提示行模板。

_MODEL_LINE_RE = re.compile(r"模型[：:]\s*([^|<\s][^|]*)")
"""从 token 行中提取模型名称的正则。"""


# ── Extended Thinking 模型兼容性名单 ──

_THINKING_SUPPORTED_PREFIXES = (
    "claude-sonnet-4",
    "claude-opus-4",
    "claude-fable-5",
    "deepseek-v4-",
    "deepseek-chat",
    "gemini-3.5-",
    "gemini-2.5-",
)

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
        f"\n\n{TRUNCATION_MARKER}！{config_field} 上限不足，内容不完整。"
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
            "LLM 输出被截断 [%s]: %s=%d, 实际输出=%d tokens。内容不完整，请在 llm_settings.json 中增大 %s",
            label,
            config_field,
            max_tokens,
            out_tokens,
            config_field,
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
            "LLM 输出被截断 [%s]: %s=%d, 实际输出=%d tokens。内容不完整，请在 llm_settings.json 中增大 %s",
            label,
            config_field,
            max_tokens,
            out_tokens,
            config_field,
        )
        return True
    return False


def _check_gemini_truncation(data: dict, max_tokens: int, label: str, config_field: str = "max_tokens") -> bool:
    """检查 Gemini 响应是否被 max_tokens 截断。

    finishReason 为 "MAX_TOKENS" 表示达到 token 上限被截断。
    """
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            return False
        finish_reason = candidates[0].get("finishReason", "")
        if finish_reason == "MAX_TOKENS":
            usage_meta = data.get("usageMetadata", {})
            out_tokens = usage_meta.get("candidatesTokenCount", 0)
            logger.error(
                "LLM 输出被截断 [%s]: %s=%d, 实际输出=%d tokens。内容不完整，请在 llm_settings.json 中增大 %s",
                label,
                config_field,
                max_tokens,
                out_tokens,
                config_field,
            )
            return True
    except (KeyError, IndexError, TypeError, AttributeError):
        return False
    return False


def _extract_content(data: dict) -> str | None:
    """从 Anthropic Messages API 兼容响应中提取文本内容。

    兼容标准 Claude 格式及 DeepSeek Anthropic 兼容端点等多种格式变体。
    会遍历 content 列表中所有 text block 并拼接返回。

    Returns:
        str: 提取的文本内容
        None: 响应格式异常或内容被过滤
    """
    _set_last_thinking_exhausted(False)  # 每次提取前复位（当前线程），仅 max_tokens 无正文分支置 True
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
        # content 无任何 text block（如只有 thinking / redacted_thinking，或空列表）。
        # 区分根因，避免误报"内容被过滤"：
        #   1) stop_reason=max_tokens → 思考部分耗尽 max_tokens 预算（DeepSeek V4 等强制
        #      推理模型常见），未产出最终文本。安抚重试（改 system prompt）对该场景无效，
        #      返回 None 触发 provider 切换而非无效重试。
        #   2) 其他 → 内容可能被过滤拦截，同样视为无可用文本，返回 None。
        if data.get("stop_reason") == "max_tokens":
            _set_last_thinking_exhausted(True)
            logger.warning(
                "LLM 输出思考部分耗尽 max_tokens 预算，未生成最终文本"
                "（建议增大对应 max_tokens 配置或降低 reasoning_effort）"
            )
        else:
            logger.warning("LLM API 返回空内容（可能被内容过滤机制拦截）")
        return None

    return None


def _extract_content_from_gemini(data: dict) -> str | None:
    """从 Gemini generateContent 响应中提取文本内容。

    Gemini 响应格式：
    {
      "candidates": [{
        "content": {"parts": [{"text": "..."}], "role": "model"},
        "finishReason": "STOP"
      }],
      "usageMetadata": {...}
    }

    Returns:
        str: 提取的文本内容
        None: 响应格式异常
    """
    if data and "error" in data:
        logger.warning("Gemini API 返回错误: %s", data["error"])
        return None

    try:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
        if texts:
            return "\n".join(texts)
        return "" if candidates else None
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        logger.warning("Gemini API 响应格式异常: %s", e)
        return None


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
    if model_name:
        msg += f" | 模型: {model_name}"
    if cache_hit:
        msg += f" (缓存命中 {cache_hit:,})"
    if model_name:
        _cost = estimate_cost(model_name, inp, out, cache_hit_input_tokens=cache_hit)
        if _cost != "-":
            msg += f" | 估算费用: {_cost}"
    logger.info("%s", msg)


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


def _check_circuit_breaker(url: str, label: str) -> bool:
    """检查熔断器状态，若已熔断则记录日志并返回 True。"""
    if _cb_is_open(url):
        logger.warning("%s API 熔断中 (%s)，跳过本次请求", label, _cb_endpoint(url))
        return True
    return False


def _process_success_response(
    data: dict,
    extract_fn: Callable[[dict], str | None],
    check_truncation_fn: Callable[[dict, int], bool],
    max_tokens: int,
    config_field: str,
    provider: str,
    model_name: str,
    label: str,
    url: str,
) -> tuple[str | None, dict | None]:
    """处理成功响应：内容提取、截断检测、Token 日志。"""
    content = extract_fn(data)
    if content is None:
        logger.warning("%s API 响应格式异常", label)
        _cb_record_failure(url)
        return (None, None)
    if not content.strip():
        logger.warning("%s API 返回空内容（可能被内容过滤机制拦截）", label)
        return ("", data.get("usage"))

    truncated = check_truncation_fn(data, max_tokens)
    # 兼容 Gemini usageMetadata：若 usage 字段不存在但 usageMetadata 存在则转换
    usage = data.get("usage")
    if usage is None:
        usage_meta = data.get("usageMetadata")
        if usage_meta:
            usage = {
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
            }
    _log_token_usage(provider, usage, label, model_name=model_name)
    track_session_usage(provider, usage, model_name=model_name)

    content = content.strip()
    if truncated:
        content += _truncation_warning(config_field)

    return (content, usage)


def _attempt_api_call(
    client: httpx.Client,
    url: str,
    headers: dict,
    payload: dict,
    timeout: float,
) -> tuple[str, Any]:
    """执行一次 LLM API 调用，返回 (kind, info)。

    Returns:
        ("success", data) — 调用成功，data 为解析后的 JSON
        ("retryable", detail) — 可重试（detail 可为 int 状态码或 str 描述）
        ("fatal", error_msg) — 不可恢复（响应解析失败）
    """
    try:
        resp = client.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code in (429, 503):
            if resp.status_code == 429:
                logger.warning(
                    "%s API 返回 429 Too Many Requests（API 限速），建议调低 llm_max_concurrency（当前并发数可能过高）",
                    _sanitize_endpoint(url),
                )
            return ("retryable", resp.status_code)
        resp.raise_for_status()
        return ("success", resp.json())
    except httpx.TimeoutException:
        logger.debug("[llm/api] 请求超时: %s", _sanitize_endpoint(url))
        return ("retryable", None)
    except httpx.HTTPError:
        host = _sanitize_endpoint(url)
        logger.debug("[llm/api] HTTP 异常: %s", host)
        return ("retryable", host)
    except (ValueError, KeyError) as e:
        logger.warning("[llm/api] 响应解析失败: %s", e)
        return ("fatal", str(e))


def _is_retry_available(label: str, attempt: int, max_retries: int, detail: str, _url: str) -> bool:
    """判断是否可重试；若可则等待后返回 True，否则 False。"""
    if attempt < max_retries:
        delay = _RETRY_DELAYS[attempt]
        logger.warning(
            "%s API %s (尝试 %d/%d)，%.1fs 后重试...",
            label,
            detail,
            attempt + 1,
            max_retries + 1,
            delay,
        )
        time.sleep(delay)
        return True
    logger.warning("%s API %s（已重试 %d 次）", label, detail, max_retries)
    return False


def call_llm_with_retry(
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
) -> tuple[str | None, dict | None]:
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
    global _last_llm_failure_reason
    if _check_circuit_breaker(url, label):
        _last_llm_failure_reason = FAIL_REASON_CIRCUIT_OPEN
        return (None, None)

    for attempt in range(max_retries + 1):
        kind, info = _attempt_api_call(client, url, headers, payload, timeout)

        if kind == "success":
            clear_last_llm_failure()
            _cb_record_success(url)
            return _process_success_response(
                info,
                extract_fn,
                check_truncation_fn,
                max_tokens,
                config_field,
                provider,
                model_name,
                label,
                url,
            )

        if kind == "retryable":
            detail = "超时" if info is None else (f"{info}" if isinstance(info, int) else f"网络错误 ({info})")
            if _is_retry_available(label, attempt, max_retries, detail, url):
                continue
            _cb_record_failure(url)
            _last_llm_failure_reason = FAIL_REASON_TIMEOUT if info is None else FAIL_REASON_NETWORK_ERROR
            return (None, None)

        # kind == "fatal"
        logger.warning("%s API 响应解析失败: %s", label, info)
        _cb_record_failure(url)
        _last_llm_failure_reason = FAIL_REASON_API_ERROR
        return (None, None)

    _cb_record_failure(url)
    _last_llm_failure_reason = FAIL_REASON_API_ERROR
    return (None, None)
