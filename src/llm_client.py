"""LLM 智能分析客户端 — 接入 Claude API / OpenAI API。

为报告模块 7（全球政经局势）和模块 8（智囊团深度复盘）生成内容。

API Key 通过 data/config/llm_key.json 管理，非敏感配置通过 data/config/llm_settings.json 管理，
不直接存储在 config.json 中。支持结果缓存，避免重复扣费。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional
import httpx

from src.cache import get as cache_get, set as cache_set

logger = logging.getLogger("invest")


def _markdown_to_html(text: str) -> str:
    """将 Markdown 文本转换为基础 HTML，供 HTML 报告模板渲染。

    支持：标题（## / ###）、粗体、斜体、行内代码、
    无序列表（-）、有序列表（1.）、水平分割线（---）、段落。

    Args:
        text: 含 Markdown 标记的纯文本

    Returns:
        HTML 片段，不含 <html>/<body> 包裹
    """
    if not text:
        return ""

    # 预处理：统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    parts: list[str] = []
    in_ul = False
    in_ol = False

    def _close_list() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            parts.append("</ul>")
            in_ul = False
        if in_ol:
            parts.append("</ol>")
            in_ol = False

    def _inline(text: str) -> str:
        """处理行内 Markdown 标记。"""
        # 粗体 **text**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # 斜体 *text*（避免误伤粗体已处理过的）
        text = re.sub(r"(?<!\*)\*(?![*])(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        # 行内代码 `code`
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            _close_list()
            continue

        # 标题（必须行首）
        h_match = re.match(r"^#{2,3}\s+(.+)$", line)
        if h_match:
            _close_list()
            level = min(6, line.split(" ")[0].count("#"))
            tag = f"h{level}"  # ## → h2, ### → h3
            parts.append(f"<{tag}>{_inline(h_match.group(1))}</{tag}>")
            continue

        # 水平分割线
        if re.match(r"^-{3,}$|^_{3,}$|^\*{3,}$", line):
            _close_list()
            parts.append("<hr>")
            continue

        # 无序列表
        ul_match = re.match(r"^[-*+]\s+(.+)$", line)
        if ul_match:
            if not in_ul:
                _close_list()
                parts.append("<ul>")
                in_ul = True
            elif in_ol:
                _close_list()
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_inline(ul_match.group(1))}</li>")
            continue

        # 有序列表
        ol_match = re.match(r"^\d+[.)]\s+(.+)$", line)
        if ol_match:
            if not in_ol:
                _close_list()
                parts.append("<ol>")
                in_ol = True
            elif in_ul:
                _close_list()
                parts.append("<ol>")
                in_ol = True
            parts.append(f"<li>{_inline(ol_match.group(1))}</li>")
            continue

        # 普通段落
        _close_list()
        parts.append(f"<p>{_inline(line)}</p>")

    _close_list()
    return "".join(parts)


# ── 缓存前缀 ─────────────────────────────────────────────────

_CACHE_PREFIX_LLM = "llm_"

# ── 默认超时 ─────────────────────────────────────────────────

_LLM_TIMEOUT = 120.0

# ── 重试配置 ─────────────────────────────────────────────────

_RETRY_MAX = 2  # 最多重试 2 次
_RETRY_DELAYS = [1.0, 3.0, 5.0, 10.0, 15.0]  # 指数退避：第 1~5 次依次等待


def _get_cache_ttl_llm(subtype: str = "macro") -> float:
    """获取 LLM 缓存 TTL。

    TTL 优先级：
      1. 已废弃（原 llm_settings.json 的 cache_ttl_macro/expert/news 已移除）
      2. config.json 中的 cache_ttl.llm_global_macro / llm_expert_review / llm_news_corr
      3. 代码默认值（全局政经 86400s / 智囊团 7200s / 新闻关联 3600s）
      3. 代码默认值（全局政经 86400s / 智囊团 7200s / 新闻关联 3600s）

    Args:
        subtype: "macro"（模块 7）、"expert"（模块 8）或 "news"（新闻关联）

    Returns:
        过期时间（秒）
    """
    # 从 config.json cache_ttl 读取
    _key_map: dict[str, str] = {
        "macro": "llm_global_macro",
        "expert": "llm_expert_review",
        "news": "llm_news_corr",
    }
    data_type = _key_map.get(subtype, "llm_global_macro")
    try:
        from src.cache import get_ttl
        return get_ttl(data_type)
    except Exception:
        defaults: dict[str, float] = {"macro": 86400, "expert": 7200, "news": 3600}
        return defaults.get(subtype, 3600)


def _generate_llm_content(
    llm_config: dict,
    cache_key: str,
    cache_ttl: float,
    system_prompt: str,
    user_prompt: str,
    cache_enabled: bool,
    force: bool,
    max_tokens: int,
    timeout: float,
    temperature: float | None,
    model: str | None,
    config_field: str,
    http_client: httpx.Client | None = None,
    thinking_enabled: bool = False,
) -> tuple[Optional[str], bool]:
    """通用 LLM 内容生成骨架，带缓存检查与写入。

    Args:
        llm_config: LLM 配置字典
        cache_key: 缓存键
        cache_ttl: 缓存过期时间（秒）
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        cache_enabled: 是否启用缓存
        force: 为 True 时跳过缓存
        max_tokens: 最大输出 token 数
        timeout: API 超时秒数
        temperature: 温度参数（None=使用 API 默认）
        model: 模型名称
        config_field: llm_settings.json 中的配置字段名（截断时提示）
        http_client: 可选的 httpx.Client 实例
        thinking_enabled: 是否已开启 Extended Thinking（为 True 时底部追加标识）

    Returns:
        (HTML 文本或 None, 是否来自缓存)
    """
    # ── 缓存检查 ──
    if cache_enabled and not force:
        cached = cache_get(cache_key, cache_ttl)
        if cached:
            logger.info("LLM 缓存命中: %s", cache_key)
            cached_clean = _strip_token_line(cached) + _CACHE_LINE_HTML
            return (cached_clean, True)

    # ── LLM 调用 ──
    result, usage = _call_llm(system_prompt, user_prompt, llm_config,
                              timeout=timeout, http_client=http_client,
                              max_tokens=max_tokens, config_field=config_field,
                              temperature=temperature, model=model)

    if result:
        html = _markdown_to_html(result)
        if result and not html.strip():
            logger.warning("LLM 返回内容为空，跳过缓存")
            return (None, False)
        _model_name = model or llm_config.get("model", "") or "未指定"
        if usage:
            inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            out = usage.get("output_tokens", usage.get("completion_tokens", 0))
            _footer = f"模型：{_model_name} | Token 用量：输入 {inp:,} / 输出 {out:,} = {inp + out:,}"
            if thinking_enabled:
                _footer += " | Extended Thinking"
            html += f'<p style="color:#888;font-size:12px">{_footer}</p>'
        cache_set(cache_key, html)
        logger.info("LLM 内容生成完成: %s", cache_key)
        return (html, False)

    logger.warning("LLM 内容生成失败: %s", cache_key)
    return (None, False)


def _expert_fingerprint(
    total_mv: float = 0,
    total_cost: float = 0,
    total_profit: float = 0,
    total_today_profit: float = 0,
    holdings_details: list[dict] | None = None,
    penetrated_assets: list[dict] | None = None,
    categories: dict | None = None,
) -> str:
    """计算智囊团深度回测的缓存指纹。

    包含持仓汇总 + 结构稳定字段，剔除单品级行情波动（market_value / profit / change_pct）。

    包含：
      - total_mv / total_cost / total_profit / total_today_profit — 持仓汇总（求和无精度抖动）
      - categories — 分类计数
      - penetrated_assets — 穿透 TOP10 资产列表
      - holdings_details — 仅取 (name, code, cost) 三元组

    不包含（避免浮点精度导致误失效）：
      - holdings_details 中的 market_value / profit / profit_rate / change_pct
    """
    _stable_details = []
    if holdings_details:
        for d in holdings_details:
            _stable_details.append({
                "name": d.get("name", ""),
                "code": d.get("code", ""),
                "cost": d.get("cost", 0),
            })
    return _compute_fingerprint(
        total_mv, total_cost, total_profit, total_today_profit,
        categories, penetrated_assets, _stable_details,
    )


def _compute_fingerprint(*args: Any) -> str:
    """计算输入数据的确定性哈希值（前 12 位），用作缓存键后缀。

    当市场行情、持仓数据变化时指纹随之改变，
    自动跳过旧缓存，无需等待 TTL 过期。
    """
    raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _log_token_usage(provider: str, usage: dict | None, label: str) -> None:
    """记录 LLM API 调用的 token 使用量。

    Args:
        provider: "claude" 或 "openai"
        usage: API 响应中的 usage 字典
        label: 调用标签（如 "全球政经"）
    """
    if not usage:
        return
    if provider == "claude":
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
    else:
        inp = usage.get("prompt_tokens", 0)
        out = usage.get("completion_tokens", 0)
    total = inp + out
    logger.info("LLM 用量 [%s]: 输入 %d token, 输出 %d token, 合计 %d token",
                label, inp, out, total)
    print(f"  [LLM] {label}: 输入 {inp:,} + 输出 {out:,} = {total:,} tokens")


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


def _strip_token_line(html: str) -> str:
    """从缓存的 HTML 中剥离旧的 Token 用量行。"""
    return _TOKEN_LINE_RE.sub("", html).strip()


def _truncation_warning(config_field: str) -> str:
    """生成截断警告，指明 llm_settings.json 中需要增大的具体配置项。"""
    return (
        f"\n\n【⚠ 输出已被截断！{config_field} 上限不足，内容不完整。"
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
    """
    # API 返回了错误信息
    if data and "error" in data:
        logger.warning("LLM API 返回错误: %s", data["error"])
        return None

    try:
        content_field = data.get("content")
    except Exception:
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

    return None


# ═══════════════════════════════════════════════════════════
#  核心调用
# ═══════════════════════════════════════════════════════════


def _get_retry_max(llm_config: dict) -> int:
    """从 llm_config 中读取最大重试次数，兜底返回 2。"""
    try:
        val = int(llm_config.get("max_retries", 2))
        return max(0, val)
    except (TypeError, ValueError):
        return 2


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

    Returns:
        (content, usage) — content 为文本，usage 为 API 用量字典，失败时均为 None
    """
    for attempt in range(max_retries + 1):
        try:
            resp = client.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in (429, 503) and attempt < max_retries:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "%s API %d (尝试 %d/%d)，%.1fs 后重试...",
                    label, resp.status_code, attempt + 1, max_retries + 1, delay,
                )
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            if attempt < max_retries:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "%s API 超时 (尝试 %d/%d)，%.1fs 后重试...",
                    label, attempt + 1, max_retries + 1, delay,
                )
                time.sleep(delay)
                continue
            logger.warning("%s API 超时（已重试 %d 次）", label, max_retries)
            return (None, None)
        except httpx.RequestError:
            host = _sanitize_endpoint(url)
            if attempt < max_retries:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "%s API 请求失败 (%s) (尝试 %d/%d)，%.1fs 后重试...",
                    label, host, attempt + 1, max_retries + 1, delay,
                )
                time.sleep(delay)
                continue
            logger.warning("%s API 请求失败 (%s)（已重试 %d 次）", label, host, max_retries)
            return (None, None)
        except (ValueError, KeyError) as e:
            logger.warning("%s API 响应解析失败: %s", label, e)
            return (None, None)

        content = extract_fn(data)
        if content is None:
            logger.warning("%s API 响应格式异常", label)
            return (None, None)

        truncated = check_truncation_fn(data, max_tokens)
        usage = data.get("usage")
        _log_token_usage(provider, usage, label)

        content = content.strip()
        if truncated:
            content += _truncation_warning(config_field)

        return (content, usage)

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

    if provider == "claude":
        return _call_claude(system_prompt, user_prompt, api_key, resolved_model, endpoint,
                            max_tokens, timeout, max_retries=max_retries,
                            http_client=http_client, config_field=config_field,
                            temperature=temperature, llm_config=llm_config)
    elif provider == "openai":
        return _call_openai(system_prompt, user_prompt, api_key, resolved_model, endpoint,
                            max_tokens, timeout, max_retries=max_retries,
                            http_client=http_client, config_field=config_field,
                            temperature=temperature)
    else:
        logger.warning("不支持的 LLM provider: %s", provider)
        return (None, None)


# ── Extended Thinking 模型兼容性名单 ──
# 已知支持 Extended Thinking 的模型前缀。
# 若使用的模型不在此列，即使配置了 thinking_enabled 也会自动降级跳过。
_THINKING_SUPPORTED_PREFIXES = ("claude-sonnet-4", "claude-opus-4", "deepseek-v4-", "deepseek-chat")

# 使用 output_config.effort（而非 thinking.budget_tokens）控制思考深度的模型。
# Anthropic Claude → budget_tokens（token 数量预算）；
# DeepSeek → effort（"high"/"max" 定性控制）。
_THINKING_EFFORT_MODEL_PREFIXES = ("deepseek-v4-", "deepseek-chat")


def _supports_extended_thinking(model: str) -> bool:
    """检查模型是否支持 Extended Thinking。"""
    return any(model.lower().startswith(p) for p in _THINKING_SUPPORTED_PREFIXES)


def _is_effort_model(model: str) -> bool:
    """检查模型是否使用 effort（而非 budget_tokens）控制思考深度。"""
    return any(model.lower().startswith(p) for p in _THINKING_EFFORT_MODEL_PREFIXES)


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
    推荐仅在智囊团深度复盘（expert）场景开启，全局政经和新闻分析收益有限。
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

    return _call_llm_with_retry(
        label="Claude", client=client, url=url, headers=headers,
        payload=payload, timeout=timeout, max_retries=max_retries,
        max_tokens=max_tokens, config_field=config_field,
        extract_fn=_extract_content,
        check_truncation_fn=lambda d, mt: _check_claude_truncation(d, mt, "Claude", config_field),
        provider="claude",
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

    return _call_llm_with_retry(
        label="OpenAI", client=client, url=url, headers=headers,
        payload=payload, timeout=timeout, max_retries=max_retries,
        max_tokens=max_tokens, config_field=config_field,
        extract_fn=_extract_openai,
        check_truncation_fn=lambda d, mt: _check_openai_truncation(d, mt, "OpenAI", config_field),
        provider="openai",
    )


# ═══════════════════════════════════════════════════════════
#  Prompt 模板
# ═══════════════════════════════════════════════════════════

_SYSTEM_MACRO = """你是一位资深宏观经济学家。基于市场数据输出中文全球政经局势分析（500字内）。
分3-4段，覆盖主要经济体政策走向、地缘风险、对持仓潜在影响。纯文本，不要使用HTML标签。"""

_SYSTEM_EXPERT = """你是投资智囊团召集人，审计用户投资组合后按三阶段输出：

Phase 1（召集令）指出组合核心矛盾，挑5位流派对立专家并标明立场。指挥官画像，专家列头衔立场。

Phase 2（圆桌会）两轮辩论：第一轮立足结构提方向，第二轮互相反驳聚焦调仓优先级。

Phase 3（定音锤）指挥官融合辩论给出量化调仓方案和风险提示。禁止调仓穿透层底层资产，只调直接持有品种。

约束：数据来自输入不虚构；每个论点引用品种代码和收益率；全 Markdown 输出；引用北京时间。"""

_SYSTEM_NEWS_CORRELATION = """你是一位资深金融分析师。以下会给你多批财经新闻（每批最多5条），请逐批分析每条新闻与用户投资组合持仓的关联性。

关联度标准：
- 高：新闻内容直接涉及持仓品种、所属行业或相关重大政策
- 中：新闻内容与持仓品种有间接关联（产业链、相关行业）
- 低：新闻内容与持仓品种关联较弱
- 无关：新闻内容与持仓品种无明显关联

每批输出一个JSON数组，为本批【每条新闻】分别输出关联分析结果，格式：
[{"idx": 0, "relevance": "高|中|低|无关", "sentiment": "利好|利空|中性", "analysis": "不超过30字的原因分析"}, ...]

每条新闻必须分析，不允许跳过任何一条。idx 对应当前批新闻列表中的序号（0 开始）。
sentiment 字段判断该新闻对持仓的利好/利空影响（结合行业和概念判断）。
只输出JSON，不要其他内容。"""


# ═══════════════════════════════════════════════════════════
#  模块 7 & 8 生成函数
# ═══════════════════════════════════════════════════════════


def _build_macro_prompt(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_profit: float,
    categories: dict,
    sector_flow: list[dict[str, Any]] | None = None,
) -> str:
    """构建模块 7（全球政经）的用户提示词（紧凑格式）。

    Args:
        a_indices: A 股指数行情
        us_indices: 美股指数行情
        total_mv: 持仓总市值
        total_profit: 持仓总盈亏
        categories: 品种分类计数
        sector_flow: 行业资金流向数据（可选），含主力净流入排名
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    idx_text = "A股:"
    for idx in (a_indices or {}).values():
        name = idx.get("name", "")
        price = idx.get("price", 0)
        chg = idx.get("change_pct", 0)
        idx_text += f" {name}{price}({chg:+.2f}%)"
    idx_text += "\n美股:"
    for idx in (us_indices or {}).values():
        name = idx.get("name", "")
        price = idx.get("price", 0)
        chg = idx.get("change_pct", 0)
        idx_text += f" {name}{price}({chg:+.2f}%)"

    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    # ── 行业资金流向 ──
    flow_text = ""
    if sector_flow:
        top_sectors = sector_flow[:5]  # 前 5 个行业
        flow_lines = []
        for s in top_sectors:
            name = s.get("name", "")
            chg = s.get("change_pct")
            inflow = s.get("main_net_inflow")
            inflow_pct = s.get("main_net_inflow_pct")
            parts = [f"{name}"]
            if chg is not None:
                parts.append(f"涨跌{chg:+.2f}%")
            if inflow is not None:
                parts.append(f"主力净流入{inflow:,.0f}")
            if inflow_pct is not None:
                parts.append(f"净占比{inflow_pct:.2f}%")
            flow_lines.append("  ".join(parts))
        flow_text = "\n【行业资金流向】\n" + "\n".join(flow_lines)

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【指数】{idx_text}\n"
        f"【持仓】总市值{total_mv:,.0f} 总盈亏{total_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}\n"
        f"{flow_text}"
        f"请基于以上数据，分析当前全球政经局势对持仓的潜在影响。"
    )


def _sanitize_endpoint(endpoint: str) -> str:
    """从 endpoint URL 中提取纯域名，避免路径/参数泄露到日志。"""
    try:
        return endpoint.split("/")[2] if endpoint else "unknown"
    except Exception:
        return "unknown"


def _fmt_wan(num: float) -> str:
    """将数值格式化为中文单位（万/亿），减少 token 消耗。"""
    if abs(num) >= 100_000_000:
        return f"{num/100_000_000:.2f}亿"
    if abs(num) >= 10_000:
        return f"{num/10_000:.1f}万"
    return f"{num:,.0f}"


def _build_review_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: Optional[list[dict]] = None,
    holdings_details: Optional[list[dict]] = None,
) -> str:
    """构建模块 8（智囊团复盘）的用户提示词（紧凑格式）。

    必须包含实际持仓明细（名称、代码、市值、成本、盈亏），
    防止 LLM 虚构持仓代码。同时包含穿透 TOP10 供参考。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    # 持仓明细清单（防止 LLM 虚构代码）—— 用中文单位压缩 token
    holdings_text = ""
    if holdings_details:
        lines = []
        for h in holdings_details[:30]:
            code = h.get("code", "")
            mv = h.get("market_value", 0)
            profit = h.get("profit", 0)
            rate = h.get("profit_rate", 0)
            chg = h.get("change_pct", 0)
            lines.append(
                f"{code} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}({rate:+.2f}%) 今{chg:+.2f}%"
            )
        holdings_text = "\n".join(lines)

    # 穿透 TOP10（辅助参考）
    pen_text = ""
    if penetrated_assets:
        assets = []
        for asset in penetrated_assets[:10]:
            name = asset.get("name", "")
            codes = ",".join(asset.get("codes", []))
            mv = asset.get("mv", 0)
            sector = asset.get("sector", "--")
            assets.append(f"{name}({codes}){_fmt_wan(mv)}/{sector}")
        pen_text = " | 穿透:" + " ".join(assets)

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} "
        f"成本{total_cost:,.0f} 盈亏{total_profit:+,.0f} 今日{total_today_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}{pen_text}\n"
        f"\n"
        f"【持仓明细】\n"
        f"{holdings_text}\n"
        f"\n"
        f"请严格基于以上【持仓明细】中的品种进行深度复盘，"
        f"只引用我实际持有的品种代码（上面列出的），"
        f"不要虚构任何持仓代码。每个建议必须引用具体品种的名称和代码。"
        f"给出优化建议和风险预警。"
    )


def generate_global_macro(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_profit: float,
    categories: dict,
    sector_flow: list[dict[str, Any]] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
) -> tuple[Optional[str], bool]:
    """生成模块 7：全球政经局势分析。

    Args:
        a_indices: A 股指数列表
        us_indices: 美股指数列表
        total_mv: 总市值
        total_profit: 总盈亏
        categories: 分类计数
        sector_flow: 行业资金流向数据（可选），含主力净流入排名
        force: 为 True 时跳过缓存强制重新生成
        http_client: 可选的 httpx.Client 实例。传入时使用该客户端发起 HTTP 请求，
            而非全局共享的 _HTTP_POOL。用于多线程场景下避免连接池线程安全问题。

    Returns:
        (HTML 格式的分析文本或 None, 是否来自缓存)
    """
    from src.config import get_llm_config

    llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 7 使用占位文本")
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_macro", True)
    fingerprint = _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    cache_key = _CACHE_PREFIX_LLM + f"global_macro_{fingerprint}"

    system_prompt = llm_config.get("system_prompt_macro") or _SYSTEM_MACRO
    if llm_config.get("output_brief_macro", False):
        system_prompt += "\n（精简模式，输出 200 字以内。）"

    user_prompt = _build_macro_prompt(a_indices, us_indices, total_mv, total_profit, categories, sector_flow)

    return _generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("macro"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_macro") or llm_config.get("max_tokens", 800),
        timeout=llm_config.get("timeout_macro", 60.0),
        temperature=llm_config.get("temperature_macro"),
        model=llm_config.get("model_macro"),
        config_field="max_tokens_macro",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_macro", False),
    )


def generate_expert_review(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: Optional[list[dict]] = None,
    holdings_details: Optional[list[dict]] = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
) -> tuple[Optional[str], bool]:
    """生成模块 8：智囊团深度复盘。

    Args:
        total_mv: 总市值
        total_cost: 总成本
        total_profit: 总盈亏
        total_today_profit: 本日盈亏
        holdings_count: 持仓总数
        categories: 分类计数
        penetrated_assets: 穿透 TOP10 资产列表（可选）
        holdings_details: 持仓明细列表，每项含 name/code/market_value/cost/profit/profit_rate（可选）
        force: 为 True 时跳过缓存强制重新生成
        http_client: 可选的 httpx.Client 实例。传入时使用该客户端发起 HTTP 请求，
            而非全局共享的 _HTTP_POOL。用于多线程场景下避免连接池线程安全问题。

    Returns:
        (HTML 格式的复盘文本或 None, 是否来自缓存)
    """
    from src.config import get_llm_config

    llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 8 使用占位文本")
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_expert", True)
    fingerprint = _expert_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
    )
    cache_key = _CACHE_PREFIX_LLM + f"expert_review_{fingerprint}"

    system_prompt = llm_config.get("system_prompt_expert") or _SYSTEM_EXPERT
    if llm_config.get("output_brief_expert", False):
        system_prompt += "\n（精简模式，输出 300 字以内。）"

    user_prompt = _build_review_prompt(
        total_mv, total_cost, total_profit, total_today_profit,
        holdings_count, categories, penetrated_assets,
        holdings_details=holdings_details,
    )

    return _generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("expert"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_expert") or llm_config.get("max_tokens", 8192),
        timeout=llm_config.get("timeout_expert", 120.0),
        temperature=llm_config.get("temperature_expert"),
        model=llm_config.get("model_expert"),
        config_field="max_tokens_expert",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_expert", False),
    )


# ═══════════════════════════════════════════════════════════
#  新闻关联分析（LLM 增强）
# ═══════════════════════════════════════════════════════════


def _build_holdings_summary(
    holdings: list,
    penetrated_assets: list | None = None,
    industry_data: dict[str, dict] | None = None,
) -> str:
    """构建持仓摘要文本（紧凑格式），供新闻关联分析 Prompt 使用。

    可选注入行业分类和概念板块信息（industry_data），
    使 LLM 能更准确判断新闻对持仓的利好/利空影响。

    Args:
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产（可选）
        industry_data: 行业/概念数据 {code: {industry, concepts, ...}}（可选）

    Returns:
        紧凑格式的持仓摘要文本
    """
    lines: list[str] = []
    for i, h in enumerate(holdings[:20]):
        code = (h.code or "").strip()
        line = f"{i + 1}. {h.name} ({code})"
        if industry_data and code in industry_data:
            idata = industry_data[code]
            tags = []
            if idata.get("industry"):
                tags.append(idata["industry"])
            if idata.get("concepts"):
                tags.extend(idata["concepts"][:3])
            if tags:
                line += f" [{'·'.join(tags)}]"
        lines.append(line)
    if penetrated_assets:
        for a in penetrated_assets[:10]:
            name = a.get("name", "")
            codes = ",".join(a.get("codes", []))
            line = f"    [穿透] {name} ({codes})"
            if industry_data:
                tags = []
                for ac in (a.get("codes") or []):
                    ac = ac.strip()
                    if ac in industry_data:
                        idata = industry_data[ac]
                        if idata.get("industry"):
                            tags.append(idata["industry"])
                        if idata.get("concepts"):
                            tags.extend(idata["concepts"][:2])
                if tags:
                    line += f" [{'·'.join(tags)}]"
            lines.append(line)
    return "\n".join(lines)


def _build_news_summary(news_data: list[dict]) -> str:
    """构建新闻摘要文本（紧凑格式），供新闻关联分析 Prompt 使用。

    Args:
        news_data: 关键词匹配后的新闻列表，取前 30 条

    Returns:
        紧凑格式的新闻摘要文本
    """
    parts: list[str] = []
    for i, item in enumerate(news_data[:30]):
        title = (item.get("title") or "")[:120]
        intro = (item.get("intro") or "")[:150]
        keywords = ", ".join(item.get("matched_keywords", []))
        parts.append(
            f"[{i}] 标题: {title}\n"
            f"    摘要: {intro}\n"
            f"    关键词: {keywords or '--'}"
        )
    return "\n".join(parts)


def _apply_llm_analysis(
    news_batch: list[dict],
    llm_response: str,
) -> list[tuple[str, str, str]]:
    """解析 LLM JSON 响应，返回批次内每条新闻的 (relevance, sentiment, analysis) 元组。

    Args:
        news_batch: 本批新闻列表（用于确定预期的条目数）
        llm_response: LLM 返回的 JSON 字符串

    Returns:
        (relevance, sentiment, analysis) 元组列表，长度与 news_batch 一致。
        LLM 返回结果少于请求数时，缺失项用默认值 ("低", "中性", "") 填充。
        JSON 解析失败时，所有项返回默认值。
    """
    import json
    import re

    batch_size = len(news_batch)
    if batch_size == 0:
        return []

    # 从可能含 Markdown 代码块的文本中提取 JSON
    text = llm_response.strip()
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("json"):
                text = block[4:].strip()
                break
            elif block.startswith("[") or block.startswith("{"):
                text = block
                break
    text = text.strip()

    try:
        analyses = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("LLM 新闻分析 JSON 解析失败: %s", e)
        return [("低", "中性", "")] * batch_size

    if not isinstance(analyses, list):
        logger.warning("LLM 新闻分析返回格式异常: 非数组")
        return [("低", "中性", "")] * batch_size

    # 建立 idx → (relevance, sentiment, analysis) 映射
    result_map: dict[int, tuple[str, str, str]] = {}
    for a in analyses:
        idx = a.get("idx")
        if not isinstance(idx, int) or idx < 0 or idx >= batch_size:
            continue
        relevance = a.get("relevance", "低")
        sentiment = a.get("sentiment", "中性")
        analysis = a.get("analysis", "")
        result_map[idx] = (relevance, sentiment, analysis)

    # 按顺序组装结果，缺失项填充默认值
    results: list[tuple[str, str, str]] = []
    for i in range(batch_size):
        if i in result_map:
            results.append(result_map[i])
        else:
            results.append(("低", "中性", ""))

    return results


def enhance_news_correlation(
    news_data: list[dict],
    holdings: list,
    penetrated_assets: list | None = None,
    industry_data: dict[str, dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
) -> tuple[list[dict], bool, dict]:
    """使用 LLM 增强新闻与持仓的关联分析。

    对关键词匹配后的新闻进行 LLM 二次分析：
    - 判定每条的关联度（高/中/低/无关）
    - 判断利好/利空影响
    - 给出简要原因分析
    - 写入 news_data 各条的 llm_analysis 字段

    支持分批并行处理：将新闻按每批至多 5 条分组，用 ThreadPoolExecutor
    并行调用 LLM 分析（最多 3 批并发）。每批独立处理，单批失败仅影响本批
    5 条（降级为默认值）。

    Args:
        news_data: 关键词匹配后的新闻列表（由 build_news_data 返回）
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产（可选）
        industry_data: 行业/概念数据 {code: {industry, concepts, ...}}（可选）
        force: 为 True 时跳过缓存强制重新生成
        http_client: 可选的 httpx.Client 实例

    Returns:
        (富化后的新闻列表, 是否来自缓存, token 用量字典)
        token 用量含 {"input_tokens": N, "output_tokens": N, "total_tokens": N}
        LLM 不可用或失败时返回 (news_data, False, {})
    """
    from src.config import get_llm_config

    llm_config = get_llm_config()
    if llm_config is None:
        return (news_data, False, {})

    if not news_data:
        return (news_data, False, {})

    # 按关键词匹配数排序，取前 30 条送给 LLM（最相关的才需要深度分析）
    # 使用 enumerate 保留原始索引，避免依赖 id() 做映射
    _sorted_with_idx = sorted(
        enumerate(news_data),
        key=lambda x: len(x[1].get("matched_keywords", [])),
        reverse=True,
    )
    top_news = [item for _, item in _sorted_with_idx[:30]]
    top_to_original = {ti: orig_i for ti, (orig_i, _) in enumerate(_sorted_with_idx[:30])}

    # 缓存开关（默认启用）
    cache_enabled = llm_config.get("cache_enabled_news_correlation", True)

    # 缓存键（含新闻标题摘要 + 持仓的指纹）
    # 使用 (序号, 标题前80字) 作指纹摘要，而非完整新闻内容，
    # 避免新闻正文小差异导致 TTL 内缓存频繁失效。
    holdings_summary = [
        {"name": h.name, "code": h.code}
        for h in holdings[:20]
    ]
    _news_fp_data = [(i, item.get("title", "")[:80]) for i, item in enumerate(top_news)]
    fingerprint = _compute_fingerprint(
        _news_fp_data, holdings_summary, penetrated_assets,
    )
    cache_key = _CACHE_PREFIX_LLM + f"news_corr_{fingerprint}"

    if cache_enabled and not force:
        cached = cache_get(cache_key, _get_cache_ttl_llm("news"))
        if cached is not None:
            logger.info("LLM 缓存命中: 新闻关联分析")
            return (cached, True, {})

    # ── 分批并行处理 ─────────────────────────────────────
    BATCH_SIZE = 5
    system_prompt = (
        llm_config.get("system_prompt_news_correlation")
        or _SYSTEM_NEWS_CORRELATION
    )
    holdings_text = _build_holdings_summary(holdings, penetrated_assets, industry_data)
    max_tokens = llm_config.get("max_tokens_news_correlation", 2000)
    _timeout = llm_config.get("timeout_news_correlation", 60.0)
    _temp = llm_config.get("temperature_news_correlation")
    _model = llm_config.get("model_news_correlation")
    _model_name = _model or llm_config.get("model", "") or "未指定"

    # analysis_by_orig_idx[news_data_index] = (relevance, sentiment, analysis)
    analysis_by_orig_idx: dict[int, tuple[str, str, str]] = {}
    total_tokens_input = 0
    total_tokens_output = 0

    batches = [top_news[i:i + BATCH_SIZE] for i in range(0, len(top_news), BATCH_SIZE)]
    logger.info("正在调用 LLM 增强新闻关联分析（%d 批，每批最多 %d 条，并行 %d 批）...",
                len(batches), BATCH_SIZE, min(3, len(batches)))

    def _process_batch(batch_idx: int, batch: list) -> tuple:
        """线程内处理一批新闻的 LLM 分析，使用独立 httpx 客户端。"""
        batch_client = httpx.Client(timeout=_LLM_TIMEOUT)
        try:
            news_text = _build_news_summary(batch)
            user_prompt = (
                f"【持仓信息】\n"
                f"{holdings_text}\n\n"
                f"【新闻列表】\n"
                f"{news_text}\n\n"
                f"请分析以上每条新闻与持仓的关联性，输出JSON数组。"
            )
            result, usage = _call_llm(
                system_prompt, user_prompt, llm_config,
                timeout=_timeout, http_client=batch_client,
                max_tokens=max_tokens,
                config_field="max_tokens_news_correlation",
                temperature=_temp, model=_model,
            )
            return batch_idx, result, usage
        finally:
            batch_client.close()

    with ThreadPoolExecutor(max_workers=min(3, len(batches), 6)) as ex:
        fut_map = {ex.submit(_process_batch, i, b): i for i, b in enumerate(batches)}
        for future in as_completed(fut_map):
            batch_idx, result, usage = future.result()
            batch = batches[batch_idx]
            if result:
                batch_tuples = _apply_llm_analysis(batch, result)
                for local_idx, (rel, sent, analysis_text) in enumerate(batch_tuples):
                    global_pos = batch_idx * BATCH_SIZE + local_idx
                    if global_pos in top_to_original:
                        orig_i = top_to_original[global_pos]
                        analysis_by_orig_idx[orig_i] = (rel, sent, analysis_text)
                if usage:
                    inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                    out = usage.get("output_tokens", usage.get("completion_tokens", 0))
                    total_tokens_input += inp
                    total_tokens_output += out
            else:
                logger.warning("LLM 新闻关联分析（批 %d/%d）: 分析失败，使用默认值",
                               batch_idx + 1, len(batches))

    # ── 合并结果 ─────────────────────────────────────────
    enriched: list[dict] = []
    analysis_count = 0
    for i, item in enumerate(news_data):
        item_copy = dict(item)
        if i in analysis_by_orig_idx:
            relevance, sentiment, analysis_text = analysis_by_orig_idx[i]
            if relevance != "无关":
                prefix = f"[{relevance}]"
                if sentiment in ("利好", "利空"):
                    prefix += f"[{sentiment}]"
                item_copy["llm_analysis"] = (
                    f"{prefix} {analysis_text}" if analysis_text else prefix
                )
                analysis_count += 1
        enriched.append(item_copy)

    # 构建 token 用量字典
    token_usage: dict = {}
    if total_tokens_input > 0 or total_tokens_output > 0:
        token_usage = {
            "model": _model_name,
            "input_tokens": total_tokens_input,
            "output_tokens": total_tokens_output,
            "total_tokens": total_tokens_input + total_tokens_output,
        }
        _log_token_usage(
            llm_config.get("provider", "unknown"),
            {"input_tokens": total_tokens_input, "output_tokens": total_tokens_output},
            "新闻关联（批处理）",
        )

    # 缓存
    cache_set(cache_key, enriched)
    logger.info(
        "LLM 新闻关联分析完成: %d 条 → %d 条含 LLM 分析（%d 批）",
        len(news_data), analysis_count, len(batches),
    )

    return (enriched, False, token_usage)


# ═══════════════════════════════════════════════════════════
#  批量生成（线程池并行，每个线程持有独立 httpx.Client）
# ═══════════════════════════════════════════════════════════


def generate_all_llm(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: Optional[list[dict]] = None,
    holdings_details: Optional[list[dict]] = None,
    sector_flow: Optional[list[dict]] = None,
    force: bool = False,
) -> tuple[Optional[str], Optional[str], bool, bool]:
    """并行生成模块 7（全球政经）+ 模块 8（智囊团复盘）。

    使用 ThreadPoolExecutor(max_workers=2) 并发调用两个 LLM 生成任务。
    每个工作线程创建独立的 httpx.Client，避免全局共享连接池的线程安全问题。

    Args:
        a_indices: A 股指数列表
        us_indices: 美股指数列表
        total_mv: 总市值
        total_cost: 总成本
        total_profit: 总盈亏
        total_today_profit: 本日盈亏
        holdings_count: 持仓总数
        categories: 分类计数
        penetrated_assets: 穿透 TOP10 资产列表（可选）
        holdings_details: 持仓明细列表（可选）
        sector_flow: 行业资金流向数据（可选），注入全球政经 prompt
        force: 为 True 时跳过缓存强制重新生成

    Returns:
        (macro_html, expert_html, macro_cached, expert_cached) 四元组
        各自可能为 None/False
    """

    from src.config import get_llm_config

    def _run_macro() -> tuple[Optional[str], bool]:
        """在线程中生成模块 7，使用独立 httpx.Client。"""
        logger.info("正在生成：全球政经局势分析...")
        client = httpx.Client(timeout=_LLM_TIMEOUT)
        try:
            return generate_global_macro(
                a_indices, us_indices, total_mv, total_profit, categories,
                sector_flow=sector_flow,
                force=force, http_client=client,
            )
        finally:
            client.close()

    def _run_expert() -> tuple[Optional[str], bool]:
        """在线程中生成模块 8，使用独立 httpx.Client。"""
        logger.info("正在生成：智囊团深度复盘（耗时较长，请耐心等待）...")
        client = httpx.Client(timeout=_LLM_TIMEOUT)
        try:
            return generate_expert_review(
                total_mv, total_cost, total_profit, total_today_profit,
                holdings_count, categories, penetrated_assets,
                holdings_details=holdings_details, force=force,
                http_client=client,
            )
        finally:
            client.close()

    macro_result: Optional[str] = None
    expert_result: Optional[str] = None
    macro_cached_flag: bool = False
    expert_cached_flag: bool = False

    with ThreadPoolExecutor(max_workers=2) as executor:
        macro_future = executor.submit(_run_macro)
        expert_future = executor.submit(_run_expert)

        for future in as_completed([macro_future, expert_future]):
            try:
                result, from_cache = future.result()
                if future == macro_future:
                    macro_result = result
                    macro_cached_flag = from_cache
                    logger.info("全球政经局势分析生成完成" if result
                                else "全球政经局势分析生成失败（跳过）")
                else:
                    expert_result = result
                    expert_cached_flag = from_cache
                    logger.info("智囊团深度复盘生成完成" if result
                                else "智囊团深度复盘生成失败（跳过）")
            except Exception:
                logger.warning("LLM 生成线程异常", exc_info=True)

    logger.info("LLM 生成完成: 宏观=%s, 智囊团=%s",
                "OK" if macro_result else "跳过", "OK" if expert_result else "跳过")
    return macro_result, expert_result, macro_cached_flag, expert_cached_flag
