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
import threading as _threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Optional
import httpx

from src.python.cache import get as cache_get, set as cache_set

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

# ── 输出截断自适应重试 ────────────────────────────────

_TRUNCATION_MARKER = "【⚠ 输出已被截断"
"""截断警告中的唯一标记，用于检测输出是否被 max_tokens 截断。"""

_AUTO_INCREASE_FACTOR = 1.5
"""截断时自动增大的倍数。"""

_AUTO_INCREASE_MAX_RETRIES = 1
"""自适应重试最多尝试次数（防止无限循环）。"""

# ── 内容过滤安抚重试 ────────────────────────────────

_CONTENT_FILTER_RECOVERY = (
    "\n\n注意：请确保你的回答包含实质性的分析内容。"
    "如果前一版本未输出任何内容，请提供完整的分析结果。"
    "所有数据均基于公开市场信息，请客观分析即可。"
)
"""当 API 返回空内容（可能被内容过滤机制拦截）时，
追加到 system prompt 尾部重新请求。"""

# ── 费用估算 ─────────────────────────────────────────

_MODEL_PRICING: dict[str, dict[str, float]] = {
    # Per 1M token 定价 — 硬编码默认值（具体货币由 llm_settings.json → pricing.currency 决定）
    # 可通过 llm_settings.json 的 "pricing" 段覆盖或新增模型，
    # 文件配置优先级高于此默认表。
    # input: 标准输入（缓存未命中）
    # output: 输出
    # input_cache_hit: 缓存命中输入（可选，默认等于 input 即无折扣）
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "claude-sonnet-4-8": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "input_cache_hit": 1.50},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0, "input_cache_hit": 1.50},
    "claude-haiku-4-5": {"input": 0.25, "output": 1.25, "input_cache_hit": 0.025},
    "claude-fable-5": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.30},
    "gpt-4o": {"input": 2.5, "output": 10.0, "input_cache_hit": 2.5},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "input_cache_hit": 0.15},
    "deepseek-v4-flash": {"input": 1, "output": 2, "input_cache_hit": 0.02},
    "deepseek-v4-pro": {"input": 3, "output": 6, "input_cache_hit": 0.025},
    "deepseek-chat": {"input": 1, "output": 2, "input_cache_hit": 0.02},
}

# 运行时合并定价表：硬编码 + llm_settings.json 覆盖
_PRICING_MERGED: dict[str, dict[str, float]] = dict(_MODEL_PRICING)

# 定价货币标识，默认 CNY；可通过 llm_settings.json → pricing.currency 覆盖
_PRICING_CURRENCY: str = "CNY"

# 货币符号映射
_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "CNY": "¥",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
}


def _reload_pricing() -> None:
    """从 llm_settings.json 重新加载定价配置。

    - "currency" 字段（可选，默认 "USD"）设定货币类型，影响费用显示的符号。
    - 其余字段按模型名合并到 _PRICING_MERGED（文件配置优先级高于内置默认）。
      文件中的 input_cache_hit 为可选字段，缺失时继承内置默认值（如内置也无则等于 input）。
    """
    global _PRICING_CURRENCY
    try:
        from src.python.config import get_llm_config
        cfg = get_llm_config()
        if cfg and "pricing" in cfg:
            file_pricing = cfg["pricing"]
            if isinstance(file_pricing, dict):
                # 提取货币标识
                if "currency" in file_pricing:
                    _PRICING_CURRENCY = str(file_pricing["currency"]).upper().strip()
                # 合并模型定价（跳过 currency 等非模型字段）
                for model, prices in file_pricing.items():
                    if model == "currency":
                        continue
                    if isinstance(prices, dict) and "input" in prices and "output" in prices:
                        entry: dict[str, float] = {
                            "input": float(prices["input"]),
                            "output": float(prices["output"]),
                        }
                        if "input_cache_hit" in prices:
                            entry["input_cache_hit"] = float(prices["input_cache_hit"])
                        else:
                            # 文件未指定缓存命中价时，继承内置默认或等于 input
                            existing = _PRICING_MERGED.get(model, {})
                            entry["input_cache_hit"] = float(
                                existing.get("input_cache_hit", prices["input"])
                            )
                        _PRICING_MERGED[model] = entry
                    elif isinstance(prices, dict):
                        # 部分字段缺失时保持已有值
                        existing = _PRICING_MERGED.get(model, {"input": 0, "output": 0, "input_cache_hit": 0})
                        if "input" in prices:
                            existing["input"] = float(prices["input"])
                        if "output" in prices:
                            existing["output"] = float(prices["output"])
                        if "input_cache_hit" in prices:
                            existing["input_cache_hit"] = float(prices["input_cache_hit"])
                        _PRICING_MERGED[model] = existing
    except Exception:
        logger.debug("加载定价配置失败，使用默认定价", exc_info=True)


# 模块加载时自动合并一次
_reload_pricing()


def _estimate_cost(model: str, input_tokens: int, output_tokens: int,
                   cache_hit_input_tokens: int = 0) -> str:
    """估算 LLM API 调用的费用。

    基于已知模型定价（每百万 token 价格）。
    未知模型返回 "-"。
    货币符号由 _PRICING_CURRENCY 决定（自 llm_settings.json → pricing.currency）。
    若存在缓存命中 token，按 input_cache_hit 费率计算（通常为 input 的 10%）。

    Args:
        model: 模型名称
        input_tokens: 总输入 token 数（含缓存命中+缓存未命中）
        output_tokens: 输出 token 数
        cache_hit_input_tokens: 其中属于缓存命中的 token 数（默认 0）

    Returns:
        格式化费用字符串，如 "$0.008"、"¥0.06" 或 "-"
    """
    if not input_tokens and not output_tokens:
        return "-"
    model_lower = model.lower().strip()
    pricing = _PRICING_MERGED.get(model_lower)
    if not pricing:
        for known, price in _PRICING_MERGED.items():
            if model_lower.startswith(known):
                pricing = price
                break
    if not pricing:
        return "-"
    cache_miss = input_tokens - cache_hit_input_tokens
    cost = (cache_miss / 1_000_000 * pricing["input"] +
            output_tokens / 1_000_000 * pricing["output"])
    if cache_hit_input_tokens > 0:
        cache_rate = pricing.get("input_cache_hit", pricing["input"])
        cost += cache_hit_input_tokens / 1_000_000 * cache_rate
    symbol = _CURRENCY_SYMBOLS.get(_PRICING_CURRENCY, "$")
    if cost < 0.01:
        return f"{symbol}{cost:.4f}"
    return f"{symbol}{cost:.3f}"


# ── 熔断器（Circuit Breaker）— 防止对故障 endpoint 持续无效请求 ────

_CIRCUIT_BREAKER_THRESHOLD = 3   # 连续失败 N 次后开启熔断
_CIRCUIT_BREAKER_RECOVERY = 60  # 冷却时间（秒）

_circuit_failures: dict[str, int] = {}        # endpoint → 连续失败次数
_circuit_open_until: dict[str, float] = {}     # endpoint → 冷却到期时间
_circuit_lock = _threading.Lock()


def _cb_endpoint(url: str) -> str:
    """从 URL 提取域名作为熔断器 key。"""
    try:
        return url.split("/")[2] if url else "unknown"
    except Exception:
        return "unknown"


def _cb_record_failure(url: str) -> None:
    """记录一次失败，达到阈值时开启熔断。"""
    ep = _cb_endpoint(url)
    with _circuit_lock:
        _circuit_failures[ep] = _circuit_failures.get(ep, 0) + 1
        if _circuit_failures[ep] >= _CIRCUIT_BREAKER_THRESHOLD:
            expiry = time.time() + _CIRCUIT_BREAKER_RECOVERY
            _circuit_open_until[ep] = expiry
            logger.warning("熔断器已开启: %s (连续失败 %d 次, 冷却 %.0fs)",
                          ep, _circuit_failures[ep], _CIRCUIT_BREAKER_RECOVERY)


def _cb_record_success(url: str) -> None:
    """成功时重置熔断状态。"""
    ep = _cb_endpoint(url)
    with _circuit_lock:
        _circuit_failures.pop(ep, None)
        _circuit_open_until.pop(ep, None)


def _cb_is_open(url: str) -> bool:
    """检查熔断是否开启。若冷却期已过则自动转为半开（返回 False）。"""
    ep = _cb_endpoint(url)
    with _circuit_lock:
        if ep not in _circuit_open_until:
            return False
        if time.time() >= _circuit_open_until[ep]:
            del _circuit_open_until[ep]  # 冷却结束 → 半开，允许一次试探
            return False
        return True


# ── 模块级失败原因记录（供 write_llm_sheets 读取以输出具体提示） ──

# 失败原因常量
FAIL_REASON_NOT_CONFIGURED = "not_configured"
FAIL_REASON_API_ERROR = "api_error"
FAIL_REASON_NETWORK_ERROR = "network_error"
FAIL_REASON_TIMEOUT = "timeout"
FAIL_REASON_CIRCUIT_OPEN = "circuit_open"
FAIL_REASON_FALLBACK_FAILED = "fallback_failed"

_LLM_MODULE_FAILURE: dict[str, str] = {}
"""{module_key: reason} 各 LLM 模块最近一次生成的失败原因。
key 为 "macro"/"expert"/"health"/"penetration"，
value 为 FAIL_REASON_* 常量。每次新生成开始时清除对应 key。"""

# ── 会话级 Token 用量累计跟踪 ──

_session_usage: dict[str, Any] = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_hit_tokens": 0,
    "total_cost": 0.0,
    "currency": "CNY",
    "model": "未指定",
    "call_count": 0,
    "per_module": {},
}
"""会话期间所有 LLM 调用的累计 Token 用量和费用。
per_module: {module_key: {"model": str, "input_tokens": int, "output_tokens": int}}
生成报告后可在 TUI/汇总页展示。"""


def reset_session_usage() -> None:
    """重置会话累计用量（新会话开始时调用）。"""
    _session_usage["input_tokens"] = 0
    _session_usage["output_tokens"] = 0
    _session_usage["cache_hit_tokens"] = 0
    _session_usage["total_cost"] = 0.0
    _session_usage["call_count"] = 0
    _session_usage["per_module"] = {}


def get_session_usage() -> dict[str, Any]:
    """返回会话累计用量字典的副本（供 TUI/报告展示）。"""
    return dict(_session_usage)


def _track_session_usage(provider: str, usage: dict | None,
                         model_name: str = "") -> None:
    """将一次 LLM 调用的用量累计到会话统计。"""
    global _session_usage
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
    _session_usage["input_tokens"] += inp
    _session_usage["output_tokens"] += out
    _session_usage["cache_hit_tokens"] += cache_hit
    _session_usage["call_count"] += 1
    if model_name:
        _session_usage["model"] = model_name

    # 累计费用
    _cost_str = _estimate_cost(model_name, inp, out,
                               cache_hit_input_tokens=cache_hit)
    if _cost_str != "-":
        # 解析费用数值
        try:
            cost_val = float(_cost_str.lstrip("$¥€£"))
            _session_usage["total_cost"] += cost_val
        except (ValueError, AttributeError):
            pass
    _session_usage["currency"] = _PRICING_CURRENCY


def _record_per_module(module_key: str, model_name: str,
                       inp: int = 0, out: int = 0,
                       cached: bool = False) -> None:
    """按模块记录本次 LLM 调用的模型和 Token 用量，用于 TUI 退出统计展示。"""
    pm = _session_usage.setdefault("per_module", {})
    if module_key not in pm:
        pm[module_key] = {"model": model_name, "input_tokens": 0, "output_tokens": 0}
    elif cached and not pm[module_key].get("model"):
        pm[module_key]["model"] = model_name
    pm[module_key]["input_tokens"] += inp
    pm[module_key]["output_tokens"] += out
    if model_name:
        pm[module_key]["model"] = model_name


def _get_cache_ttl_llm(subtype: str = "macro") -> float:
    """获取 LLM 缓存 TTL。

    TTL 优先级：
      1. 已废弃（原 llm_settings.json 的 cache_ttl_macro/expert/news 已移除）
      2. config.json 中的 cache_ttl.llm_global_macro / llm_expert_review / llm_news_correlation
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
        "news": "llm_news_correlation",
        "health": "llm_health_check",
        "penetration": "llm_penetration_deep",
    }
    data_type = _key_map.get(subtype, "llm_global_macro")
    try:
        from src.python.cache import get_ttl
        return get_ttl(data_type)
    except Exception:
        defaults: dict[str, float] = {"macro": 86400, "expert": 7200, "news": 3600, "health": 7200, "penetration": 86400}
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
    module_key: str = "",
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
        module_key: 模块键名（"macro"/"expert"/"health"/"penetration"），
            用于记录失败原因供写入层读取

    Returns:
        (HTML 文本或 None, 是否来自缓存)
    """
    # 清除旧的失败原因
    if module_key:
        _LLM_MODULE_FAILURE.pop(module_key, None)

    # ── 缓存检查 ──
    if cache_enabled and not force:
        cached = cache_get(cache_key, cache_ttl)
        if cached:
            logger.info("LLM 缓存命中: %s", cache_key)
            cached_clean = _strip_token_line(cached)
            _orig_model = _extract_model_from_cached(cached)
            if _orig_model:
                _hint = _CACHE_LINE_MODEL_TPL.format(model=_orig_model)
            else:
                _hint = _CACHE_LINE_HTML
            if thinking_enabled:
                # 在缓存提示行尾部追加 Extended Thinking 标识
                _hint = _hint.rstrip().replace("</p>", " | Extended Thinking</p>", 1)
            cached_clean += _hint
            if module_key:
                _record_per_module(module_key, _orig_model or model or llm_config.get("model", "") or "缓存命中", cached=True)
            return (cached_clean, True)

    # ── LLM 调用 ──
    result, usage = _call_llm(system_prompt, user_prompt, llm_config,
                              timeout=timeout, http_client=http_client,
                              max_tokens=max_tokens, config_field=config_field,
                              temperature=temperature, model=model)

    # ── 自适应 max_tokens：检测截断并自动增大 token 上限重试 ──
    if result and _TRUNCATION_MARKER in result:
        new_max = int(max_tokens * _AUTO_INCREASE_FACTOR)
        logger.warning(
            "输出被截断（max_tokens=%d），自动以 %d 重新生成...",
            max_tokens, new_max,
        )
        print(f"  [..] 输出被截断，自动增大 max_tokens ({max_tokens} → {new_max}) 重新生成...")
        result2, usage2 = _call_llm(
            system_prompt, user_prompt, llm_config,
            timeout=timeout, http_client=http_client,
            max_tokens=new_max, config_field=config_field,
            temperature=temperature, model=model,
        )
        if result2:
            result, usage = result2, usage2
            if _TRUNCATION_MARKER in result2:
                logger.warning("增大 max_tokens=%d 后仍被截断，请手动增大配置", new_max)

    if result:
        html = _markdown_to_html(result)
        if result and not html.strip():
            logger.warning("LLM 返回内容为空，跳过缓存")
            if module_key:
                _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_API_ERROR
            return (None, False)
        _model_name = model or llm_config.get("model", "") or "未指定"
        if usage:
            inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            out = usage.get("output_tokens", usage.get("completion_tokens", 0))
            cache_hit = usage.get("cache_read_input_tokens", 0)
            _footer = f"模型：{_model_name} | Token 用量：输入 {inp:,} / 输出 {out:,} = {inp + out:,}"
            _cost = _estimate_cost(_model_name, inp, out, cache_hit_input_tokens=cache_hit)
            if _cost != "-":
                _footer += f" | 估算费用：{_cost}"
            if cache_hit:
                _footer += f" | 缓存命中：{cache_hit:,} tokens"
            if thinking_enabled:
                _footer += " | Extended Thinking"
            html += f'<p style="color:#888;font-size:12px">{_footer}</p>'
            if module_key:
                _inp = usage.get("input_tokens", usage.get("prompt_tokens", 0)) if usage else 0
                _out = usage.get("output_tokens", usage.get("completion_tokens", 0)) if usage else 0
                _record_per_module(module_key, _model_name, inp=_inp, out=_out)
        cache_set(cache_key, html)
        logger.info("LLM 内容生成完成: %s", cache_key)
        return (html, False)

    logger.warning("LLM 内容生成失败: %s", cache_key)
    if module_key:
        _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_API_ERROR
    return (None, False)


def _extract_stable_holdings(holdings_details: list[dict] | None) -> list[dict]:
    """从持仓明细中提取稳定的（无行情波动）字段。"""
    result: list[dict] = []
    if holdings_details:
        for d in holdings_details:
            result.append({
                "name": d.get("name", ""),
                "code": d.get("code", ""),
                "cost": d.get("cost", 0),
            })
    return result


def _extract_stable_penetration(penetrated_assets: list[dict] | None,
                                 full: bool = False) -> list[dict]:
    """从穿透资产中提取稳定的（无行情波动）字段。

    Args:
        penetrated_assets: 穿透 TOP10 资产列表
        full: 若为 True 则包含 mv/ratio/sector（用于穿透深度分析的额外区分）

    Returns:
        稳定字段的字典列表
    """
    result: list[dict] = []
    if penetrated_assets:
        for a in penetrated_assets:
            entry = {"name": a.get("name", ""), "codes": a.get("codes", [])}
            if full:
                entry["mv"] = a.get("mv", 0)
                entry["sector"] = a.get("sector", "")
                entry["ratio"] = a.get("ratio", 0)
            result.append(entry)
    return result


def _compute_fingerprint(*args: Any) -> str:
    """计算输入数据的确定性哈希值（前 12 位），用作缓存键后缀。

    当市场行情、持仓数据变化时指纹随之改变，
    自动跳过旧缓存，无需等待 TTL 过期。
    """
    raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


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

    使用 _extract_stable_holdings 剔除行情波动，
    穿透资产仅取 (name, codes) 不包含 mv/ratio 等行情字段。
    委托 _compute_fingerprint 计算哈希。
    """
    _details = _extract_stable_holdings(holdings_details)
    _pen = _extract_stable_penetration(penetrated_assets, full=False)
    return _compute_fingerprint(
        total_mv, total_cost, total_profit, total_today_profit,
        categories, _details, _pen,
    )


def _health_check_fingerprint(
    total_mv: float = 0,
    total_cost: float = 0,
    total_profit: float = 0,
    total_today_profit: float = 0,
    holdings_details: list[dict] | None = None,
    penetrated_assets: list[dict] | None = None,
    categories: dict | None = None,
) -> str:
    """计算持仓体检报告的缓存指纹。

    与 _expert_fingerprint 完全同构，统一使用 _extract_stable_* 辅助函数。
    """
    _details = _extract_stable_holdings(holdings_details)
    _pen = _extract_stable_penetration(penetrated_assets, full=False)
    return _compute_fingerprint(
        total_mv, total_cost, total_profit, total_today_profit,
        categories, _details, _pen,
    )


def _penetration_deep_fingerprint(
    total_mv: float = 0,
    total_cost: float = 0,
    total_profit: float = 0,
    total_today_profit: float = 0,
    holdings_details: list[dict] | None = None,
    penetrated_assets: list[dict] | None = None,
    categories: dict | None = None,
) -> str:
    """计算穿透深度分析的缓存指纹。

    与 _expert_fingerprint 区别：穿透资产额外包含 mv/sector/ratio，
    使得仅穿透数据更新时也能触发缓存失效。
    """
    _details = _extract_stable_holdings(holdings_details)
    _pen = _extract_stable_penetration(penetrated_assets, full=True)
    return _compute_fingerprint(
        total_mv, total_cost, total_profit, total_today_profit,
        categories, _details, _pen,
   )


def _log_token_usage(provider: str, usage: dict | None, label: str, model_name: str = "") -> None:
    """记录 LLM API 调用的 token 使用量，可选估算费用。

    Args:
        provider: "claude" 或 "openai"
        usage: API 响应中的 usage 字典
        label: 调用标签（如 "全球政经"）
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


def _strip_token_line(html: str) -> str:
    """从缓存的 HTML 中剥离旧的 Token 用量行。"""
    return _TOKEN_LINE_RE.sub("", html).strip()


_MODEL_LINE_RE = re.compile(r'模型[：:]\s*([^|<\s][^|]*)')
"""从 token 行中提取模型名称的正则。"""


def _extract_model_from_cached(html: str) -> str:
    """从缓存的 HTML 中提取原始模型名称。"""
    m = _MODEL_LINE_RE.search(html)
    return m.group(1).strip() if m else ""


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
        # content 列表为空或只有 non-text block（如 thinking / redacted_thinking）
        # 可能是内容被过滤，返回空字符串而非 None 以便上层做针对性处理
        if not texts and content_field:
            return ""
        return ""  # 空列表也视为空内容而非格式异常

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

    # ── 主 provider ──
    result, usage = _call_single_provider(
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
        result2, usage2 = _call_single_provider(
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
        result, usage = _call_single_provider(
            fallback_provider, system_prompt, user_prompt, fb_api_key, fb_model, fb_endpoint,
            max_tokens, timeout, max_retries, http_client, config_field, temperature, llm_config,
        )
        if result is not None:
            return result, usage
        logger.warning("回退 provider (%s) 同样失败", fallback_provider)

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

    return _call_llm_with_retry(
        label="OpenAI", client=client, url=url, headers=headers,
        payload=payload, timeout=timeout, max_retries=max_retries,
        max_tokens=max_tokens, config_field=config_field,
        extract_fn=_extract_openai,
        check_truncation_fn=lambda d, mt: _check_openai_truncation(d, mt, "OpenAI", config_field),
        provider="openai", model_name=model,
    )


# ═══════════════════════════════════════════════════════════
#  Prompt 模板
# ═══════════════════════════════════════════════════════════

_SYSTEM_GLOBAL_MACRO = """你是一位资深宏观经济学家。基于市场数据输出中文全球政经局势分析（500字内）。
分3-4段，覆盖主要经济体政策走向、地缘风险、对持仓潜在影响。纯文本，不要使用HTML标签。"""

_SYSTEM_EXPERT_REVIEW = """你是投资智囊团召集人，审计用户投资组合后按三阶段输出：

Phase 1（召集令）指出组合核心矛盾，挑5位流派对立专家并标明立场。指挥官画像，专家列头衔立场。

Phase 2（圆桌会）两轮辩论：第一轮立足结构提方向，第二轮互相反驳聚焦调仓优先级。

Phase 3（定音锤）指挥官融合辩论给出量化调仓方案和风险提示。禁止调仓穿透层底层资产，只调直接持有品种。

约束：数据来自输入不虚构；每个论点引用品种代码和收益率；全 Markdown 输出；引用北京时间。
标注了"净值:YYYY-MM-DD"的品种其涨跌幅数据截止该日期，并非今日涨跌幅，不得在简报和辩论中提及本日盈亏。
标注了"(QDII滞后1日)"的 QDII 基金净值天然滞后一个交易日，即使净值日期显示为今日，其底层资产定价也截止上一交易日，同样不得讨论本日盈亏。"""

_SYSTEM_HEALTH_CHECK = """你是专业投资组合体检分析师。基于用户持仓数据，从四个维度打分：

## 评分标准（每项满分100）

1. **风险分散度**：评估行业集中度、单品种集中度、穿透资产集中度
2. **流动性**：评估场内/场外比例、停牌风险、基金封闭期
3. **收益合理性**：评估盈亏是否合理、与大盘/同类对比
4. **成本结构**：评估成本分布、浮盈浮亏比

## 输出格式（Markdown）

## 综合评分
**总分：XX/100** | 评级：优/良/中/差

## 一、风险分散度（XX/100）
评分依据：…
扣分项：…

## 二、流动性（XX/100）
评分依据：…
风险提示：…

## 三、收益合理性（XX/100）
评分依据：…
异常说明：…

## 四、成本结构（XX/100）
评分依据：…
优化建议：…

## 改进建议
按优先级列出3-5条具体可操作建议。

约束：只引用数据中实际存在的品种，不虚构任何数据。每个判断必须有数据支撑。"""

_SYSTEM_PENETRATION_DEEP = """你是穿透深度分析专家。基于用户穿透 TOP10 数据和持仓行业分类，分析以下维度：

## 输出格式（Markdown）

## 行业集中度分析
- 前 N 大行业及占比
- 集中度风险判断（>30%标注风险）
- 行业分散度评分

## 品种集中度分析
- TOP 10 底层资产及占比（占总市值百分比）
- 单品种风险判断（>15%标注风险）

## 国别/币种暴露
- A股/港股/美股 各占比
- 外汇风险敞口判断

## 综合建议
- 2-3条调整建议

约束：只引用数据中实际存在的品种，不虚构任何数据。
每个结论须有具体数据支撑（占比百分比）。"""

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
#  共享持仓明细格式化（智囊团 / 体检 / 穿透共用）
# ═══════════════════════════════════════════════════════════


def _is_qdii(name: str) -> bool:
    return "QDII" in name.upper() if name else False


def _fmt_holding_line(h: dict, show_cost: bool = False) -> str:
    """格式化单条持仓明细行，含净值日期 / QDII 标注。

    Args:
        h: 持仓明细字典（code, market_value, profit, profit_rate,
           nav_date, source_api, name, change_pct, 可选 cost）
        show_cost: 是否显示成本（体检报告用）

    Returns:
        格式化的文本行
    """
    code = h.get("code", "")
    mv = h.get("market_value", 0)
    profit = h.get("profit", 0)
    rate = h.get("profit_rate", 0)
    nav_date = h.get("nav_date", "")
    source_api = h.get("source_api", "")
    name = h.get("name", "")
    qdii_suffix = "(QDII滞后1日)" if _is_qdii(name) else ""

    if show_cost:
        cost = h.get("cost", 0)
        base = f"{code} 成本{_fmt_wan(cost)} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}({rate:+.2f}%)"
    else:
        base = f"{code} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}({rate:+.2f}%)"

    if source_api != "tencent" and nav_date:
        return f"{base} 净值:{nav_date}{qdii_suffix}"
    chg = h.get("change_pct", 0)
    return f"{base} 今{chg:+.2f}%{qdii_suffix}"


# ═══════════════════════════════════════════════════════════
#  构建 Prompts
# ═══════════════════════════════════════════════════════════


def _build_global_macro_prompt(
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


def _build_expert_review_prompt(
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
            lines.append(_fmt_holding_line(h))
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


def _build_health_check_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: Optional[list[dict]] = None,
    holdings_details: Optional[list[dict]] = None,
) -> str:
    """构建模块 9（持仓体检报告）的用户提示词。

    要求 LLM 从风险分散度/流动性/收益合理性/成本结构四维度打分。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    # 持仓明细
    holdings_text = ""
    if holdings_details:
        lines = []
        for h in holdings_details[:30]:
            lines.append(_fmt_holding_line(h, show_cost=True))
        holdings_text = "\n".join(lines)

    # 穿透 TOP10
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
        f"请从以下四个维度对以上投资组合进行全面体检并打分：\n"
        f"1. 风险分散度 — 行业/品种集中度\n"
        f"2. 流动性 — 场内场外/停牌/封闭期\n"
        f"3. 收益合理性 — 盈亏是否与市场匹配\n"
        f"4. 成本结构 — 成本分布与浮盈浮亏比\n"
        f"按要求的输出格式给出评分和改进建议。"
    )


def _build_penetration_deep_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: Optional[list[dict]] = None,
    holdings_details: Optional[list[dict]] = None,
) -> str:
    """构建模块 10（穿透深度分析）的用户提示词。

    要求 LLM 基于穿透 TOP10 和持仓行业分类，
    分析行业集中度、品种集中度、国别/币种暴露。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    # 持仓明细
    holdings_text = ""
    if holdings_details:
        lines = []
        for h in holdings_details[:30]:
            code = h.get("code", "")
            mv = h.get("market_value", 0)
            profit = h.get("profit", 0)
            cost = h.get("cost", 0)
            lines.append(
                f"{code} 成本{_fmt_wan(cost)} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}"
            )
        holdings_text = "\n".join(lines)

    # 穿透 TOP10 明细（包含行业/板块）
    pen_list = ""
    if penetrated_assets:
        items = []
        for a in penetrated_assets[:10]:
            name = a.get("name", "")
            codes = ",".join(a.get("codes", []))
            mv = a.get("mv", 0)
            ratio = a.get("ratio", 0)
            sector = a.get("sector", "--")
            items.append(f"{name}({codes}) 市值{_fmt_wan(mv)} 占比{ratio:.1f}% 行业:{sector}")
        pen_list = "\n".join(items)

    # 根据代码前缀推断国别/币种
    _country_map: dict[str, str] = {"hk": "港股", "us": "美股", "sh": "A股", "sz": "A股", "bj": "A股"}
    country_exposure: dict[str, float] = {}
    if holdings_details:
        for h in holdings_details:
            code = h.get("code", "")
            mv = h.get("market_value", 0)
            prefix = code.split(".")[0].split("_")[0].split("-")[0].lower() if "." in code else code[:2].lower()
            country = _country_map.get(prefix, "其他")
            if prefix.startswith("sh") or prefix.startswith("sz") or prefix.startswith("bj"):
                country = "A股"
            country_exposure[country] = country_exposure.get(country, 0) + mv

    country_lines = [f"{k}: {_fmt_wan(v)}" for k, v in sorted(country_exposure.items(), key=lambda x: -x[1])]

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} 成本{total_cost:,.0f} 盈亏{total_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}\n"
        f"\n"
        f"【持仓明细】\n"
        f"{holdings_text}\n"
        f"\n"
        f"【穿透TOP10底层资产】\n"
        f"{pen_list}\n"
        f"\n"
        f"【国别/币种分布】\n"
        f"{chr(10).join(country_lines)}\n"
        f"\n"
        f"请基于以上数据，从以下维度进行穿透深度分析：\n"
        f"1. 行业集中度评估 — TOP 10 行业及占比，>30%时标注风险\n"
        f"2. 品种集中度评估 — TOP 10 底层资产及占比\n"
        f"3. 国别/币种暴露 — 外汇风险敞口判断\n"
        f"按要求的输出格式给出分析结论和建议。"
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
    llm_config: dict | None = None,
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
        llm_config: 可选的 LLM 配置字典。传入时跳过内部 get_llm_config() 调用，
            避免多线程场景下冗余文件 I/O。

    Returns:
        (HTML 格式的分析文本或 None, 是否来自缓存)
    """
    if llm_config is None:
        from src.python.config import get_llm_config
        llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 7 使用占位文本")
        _LLM_MODULE_FAILURE["macro"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_global_macro", True)
    fingerprint = _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    cache_key = _CACHE_PREFIX_LLM + f"global_macro_{fingerprint}"

    system_prompt = llm_config.get("system_prompt_global_macro") or _SYSTEM_GLOBAL_MACRO
    if llm_config.get("output_brief_global_macro", False):
        system_prompt += "\n（精简模式，输出 200 字以内。）"

    user_prompt = _build_global_macro_prompt(a_indices, us_indices, total_mv, total_profit, categories, sector_flow)

    return _generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("macro"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_global_macro") or llm_config.get("max_tokens", 800),
        timeout=llm_config.get("timeout_global_macro", 60.0),
        temperature=llm_config.get("temperature_global_macro"),
        model=llm_config.get("model_global_macro"),
        config_field="max_tokens_global_macro",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_global_macro", False),
        module_key="macro",
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
    llm_config: dict | None = None,
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
        llm_config: 可选的 LLM 配置字典。传入时跳过内部 get_llm_config() 调用。

    Returns:
        (HTML 格式的复盘文本或 None, 是否来自缓存)
    """
    if llm_config is None:
        from src.python.config import get_llm_config
        llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 8 使用占位文本")
        _LLM_MODULE_FAILURE["expert"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_expert_review", True)
    fingerprint = _expert_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
    )
    cache_key = _CACHE_PREFIX_LLM + f"expert_review_{fingerprint}"

    system_prompt = llm_config.get("system_prompt_expert_review") or _SYSTEM_EXPERT_REVIEW
    if llm_config.get("output_brief_expert_review", False):
        system_prompt += "\n（精简模式，输出 300 字以内。）"

    user_prompt = _build_expert_review_prompt(
        total_mv, total_cost, total_profit, total_today_profit,
        holdings_count, categories, penetrated_assets,
        holdings_details=holdings_details,
    )

    return _generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("expert"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_expert_review") or llm_config.get("max_tokens", 8192),
        timeout=llm_config.get("timeout_expert_review", 120.0),
        temperature=llm_config.get("temperature_expert_review"),
        model=llm_config.get("model_expert_review"),
        config_field="max_tokens_expert_review",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_expert_review", False),
        module_key="expert",
    )


def generate_health_check(
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
    llm_config: dict | None = None,
) -> tuple[Optional[str], bool]:
    """生成模块 9：持仓体检报告。

    从风险分散度/流动性/收益合理性/成本结构四维度打分并给出改进建议。

    Args:
        llm_config: 可选的 LLM 配置字典。传入时跳过内部 get_llm_config() 调用。

    Returns:
        (HTML 格式的体检报告或 None, 是否来自缓存)
    """
    if llm_config is None:
        from src.python.config import get_llm_config
        llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 9 跳过")
        _LLM_MODULE_FAILURE["health"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_health_check", True)
    fingerprint = _health_check_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
    )
    cache_key = _CACHE_PREFIX_LLM + f"health_check_{fingerprint}"

    system_prompt = llm_config.get("system_prompt_health_check") or _SYSTEM_HEALTH_CHECK
    if llm_config.get("output_brief_health_check", False):
        system_prompt += "\n（精简模式，输出 300 字以内。）"

    user_prompt = _build_health_check_prompt(
        total_mv, total_cost, total_profit, total_today_profit,
        holdings_count, categories, penetrated_assets,
        holdings_details=holdings_details,
    )

    return _generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("health"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_health_check") or llm_config.get("max_tokens", 4096),
        timeout=llm_config.get("timeout_health_check", 120.0),
        temperature=llm_config.get("temperature_health_check"),
        model=llm_config.get("model_health_check"),
        config_field="max_tokens_health_check",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_health_check", False),
        module_key="health",
    )


def generate_penetration_deep_analysis(
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
    llm_config: dict | None = None,
) -> tuple[Optional[str], bool]:
    """生成模块 10：穿透深度分析。

    分析行业集中度、品种集中度、国别/币种暴露。
    缓存 TTL 设为 1 天，使用持仓数据做指纹。

    Args:
        llm_config: 可选的 LLM 配置字典。传入时跳过内部 get_llm_config() 调用。

    Returns:
        (HTML 格式的分析报告或 None, 是否来自缓存)
    """
    if llm_config is None:
        from src.python.config import get_llm_config
        llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 10 跳过")
        _LLM_MODULE_FAILURE["penetration"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_penetration_deep", True)
    fingerprint = _penetration_deep_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
    )
    cache_key = _CACHE_PREFIX_LLM + f"penetration_deep_{fingerprint}"

    system_prompt = llm_config.get("system_prompt_penetration_deep") or _SYSTEM_PENETRATION_DEEP
    if llm_config.get("output_brief_penetration_deep", False):
        system_prompt += "\n（精简模式，输出 300 字以内。）"

    user_prompt = _build_penetration_deep_prompt(
        total_mv, total_cost, total_profit,
        holdings_count, categories, penetrated_assets,
        holdings_details=holdings_details,
    )

    return _generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("penetration"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_penetration_deep") or llm_config.get("max_tokens", 4096),
        timeout=llm_config.get("timeout_penetration_deep", 90.0),
        temperature=llm_config.get("temperature_penetration_deep"),
        model=llm_config.get("model_penetration_deep"),
        config_field="max_tokens_penetration_deep",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_penetration_deep", False),
        module_key="penetration",
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


def _apply_llm_news_correlation(
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
    llm_config: dict | None = None,
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
        llm_config: 可选的 LLM 配置字典。传入时跳过内部 get_llm_config() 调用，
            与 generate_all_llm 中的缓存预检优化一致

    Returns:
        (富化后的新闻列表, 是否来自缓存, token 用量字典)
        token 用量含 {"input_tokens": N, "output_tokens": N, "total_tokens": N}
        LLM 不可用或失败时返回 (news_data, False, {})
    """
    if llm_config is None:
        from src.python.config import get_llm_config
        llm_config = get_llm_config()
    if llm_config is None:
        return (news_data, False, {})

    if not news_data:
        return (news_data, False, {})

    # 按关键词匹配数排序，取前 30 条送给 LLM（最相关的才需要深度分析）
    _sorted_with_idx = sorted(
        enumerate(news_data),
        key=lambda x: len(x[1].get("matched_keywords", [])),
        reverse=True,
    )
    top_news = [item for _, item in _sorted_with_idx[:30]]
    top_to_original = {ti: orig_i for ti, (orig_i, _) in enumerate(_sorted_with_idx[:30])}

    cache_enabled = llm_config.get("cache_enabled_news_correlation", True)
    holdings_summary = [{"name": h.name, "code": h.code} for h in holdings[:20]]
    BATCH_SIZE = 10

    # ── 稳定持仓指纹（用于所有文章共享的 holdings 标识） ──
    holdings_fp = _compute_fingerprint(holdings_summary, penetrated_assets)

    # analysis_by_orig_idx[news_data_index] = (relevance, sentiment, analysis)
    analysis_by_orig_idx: dict[int, tuple[str, str, str]] = {}
    total_tokens_input = 0
    total_tokens_output = 0

    # ── 每篇文章独立缓存（而非整批统一缓存） ─────────
    # 缓存键 = hash(标题前80字 + 持仓指纹)。新文章加入时，
    # 仅新文章的缓存缺失，已缓存的老文章不受影响。
    # 只要持仓结构不变，已分析的新闻在 TTL 内直接复用。
    article_cache_keys: dict[int, str] = {}  # global_pos in top_news → cache_key
    _uncached_positions: list[int] = []
    _model = llm_config.get("model_news_correlation")
    _model_name_news = _model or llm_config.get("model", "") or "未指定"

    for global_pos in range(len(top_news)):
        item = top_news[global_pos]
        title_prefix = (item.get("title", "") or "")[:80]
        article_fp = _compute_fingerprint({"title": title_prefix, "holdings_fp": holdings_fp})
        article_key = _CACHE_PREFIX_LLM + f"news_item_{article_fp}"
        article_cache_keys[global_pos] = article_key

        if cache_enabled and not force:
            cached = cache_get(article_key, _get_cache_ttl_llm("news"))
            if cached is not None:
                orig_i = top_to_original[global_pos]
                analysis_by_orig_idx[orig_i] = (
                    cached.get("relevance", "低"),
                    cached.get("sentiment", "中性"),
                    cached.get("analysis", ""),
                )
                logger.debug("新闻关联缓存命中: pos=%d orig=%d", global_pos, orig_i)
                continue
        _uncached_positions.append(global_pos)

    all_cached = (len(_uncached_positions) == 0)

    # ── 仅对未缓存的文章调用 LLM（分批并行） ────────
    if _uncached_positions:
        system_prompt = (
            llm_config.get("system_prompt_news_correlation")
            or _SYSTEM_NEWS_CORRELATION
        )
        holdings_text = _build_holdings_summary(holdings, penetrated_assets, industry_data)
        max_tokens = llm_config.get("max_tokens_news_correlation", 2000)
        _timeout = llm_config.get("timeout_news_correlation", 60.0)
        _temp = llm_config.get("temperature_news_correlation")
        # 按 BATCH_SIZE 分批
        uncached_batches = [
            _uncached_positions[i:i + BATCH_SIZE]
            for i in range(0, len(_uncached_positions), BATCH_SIZE)
        ]
        logger.info("正在调用 LLM 增强新闻关联分析（%d 批未缓存，每批最多 %d 条）...",
                    len(uncached_batches), BATCH_SIZE)

        def _process_uncached_batch(batch_id: int, batch_positions: list[int]) -> tuple:
            """线程内处理一批未缓存新闻的 LLM 分析。"""
            total_batches = len(uncached_batches)
            print(f"  [..] LLM 新闻分析 [{batch_id + 1}/{total_batches}] 批处理中 ({len(batch_positions)} 条)...")
            batch_client = httpx.Client(timeout=_LLM_TIMEOUT)
            try:
                batch_items = [top_news[gp] for gp in batch_positions]
                news_text = _build_news_summary(batch_items)  # idx 从 0 开始本批
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
                # ── 自适应 max_tokens ──
                if result and _TRUNCATION_MARKER in result:
                    new_max = int(max_tokens * _AUTO_INCREASE_FACTOR)
                    logger.warning(
                        "新闻分析输出被截断（max_tokens=%d），自动以 %d 重新生成 [批 %d/%d]",
                        max_tokens, new_max, batch_id + 1, len(uncached_batches),
                    )
                    result2, usage2 = _call_llm(
                        system_prompt, user_prompt, llm_config,
                        timeout=_timeout, http_client=batch_client,
                        max_tokens=new_max,
                        config_field="max_tokens_news_correlation",
                        temperature=_temp, model=_model,
                    )
                    if result2:
                        result, usage = result2, usage2
                return (batch_id, batch_positions, result, usage)
            finally:
                batch_client.close()

        with ThreadPoolExecutor(max_workers=min(3, len(uncached_batches), 6)) as ex:
            _fut_map = {
                ex.submit(_process_uncached_batch, i, positions): i
                for i, positions in enumerate(uncached_batches)
            }
            for future in as_completed(_fut_map):
                _bid, _positions, result, usage = future.result()
                total_batches_proc = len(uncached_batches)
                if result:
                    _batch_items = [top_news[gp] for gp in _positions]
                    batch_tuples = _apply_llm_news_correlation(_batch_items, result)
                    for local_idx, (rel, sent, analysis_text) in enumerate(batch_tuples):
                        global_pos = _positions[local_idx]
                        orig_i = top_to_original[global_pos]
                        analysis_by_orig_idx[orig_i] = (rel, sent, analysis_text)
                        # 每篇文章独立缓存
                        cache_set(
                            article_cache_keys[global_pos],
                            {"relevance": rel, "sentiment": sent, "analysis": analysis_text},
                        )
                    if usage:
                        inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                        out = usage.get("output_tokens", usage.get("completion_tokens", 0))
                        total_tokens_input += inp
                        total_tokens_output += out
                    print(f"  [OK] LLM 新闻分析 [{_bid + 1}/{total_batches_proc}] 批完成")
                else:
                    logger.warning("LLM 新闻关联分析（批 %d/%d）: 分析失败",
                                   _bid + 1, total_batches_proc)
                    print(f"  [!] LLM 新闻分析 [{_bid + 1}/{total_batches_proc}] 批失败")
    else:
        _record_per_module("news", _model_name_news, cached=True)

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
            "model": _model_name_news,
            "input_tokens": total_tokens_input,
            "output_tokens": total_tokens_output,
            "total_tokens": total_tokens_input + total_tokens_output,
        }
        _log_token_usage(
            llm_config.get("provider", "unknown"),
            {"input_tokens": total_tokens_input, "output_tokens": total_tokens_output},
            "新闻关联（批处理）",
            model_name=_model_name_news,
        )
        _record_per_module("news", _model_name_news, inp=total_tokens_input, out=total_tokens_output)

    _cached_count = len(top_news) - len(_uncached_positions)
    _fresh_count = len(_uncached_positions)
    logger.info(
        "LLM 新闻关联分析完成: %d 条 → %d 条含 LLM 分析（缓存 %d 条 + 新处理 %d 条）",
        len(news_data), analysis_count, _cached_count, _fresh_count,
    )

    return (enriched, all_cached, token_usage)


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
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], bool, bool, bool, bool]:
    """并行生成模块 7（全球政经）+ 模块 8（智囊团复盘）+ 模块 9（持仓体检）+ 模块 10（穿透深度）。

    优化：
      - 调用 get_llm_config() 仅一次，避免各生成函数内部重复文件 I/O
      - 预计算指纹 + 缓存键，仅对缓存未命中的模块提交线程池任务
      - 缓存命中的模块直接读取内容，节省线程开销

    使用 ThreadPoolExecutor(max_workers=4) 并发调用四个 LLM 生成任务。
    每个工作线程创建独立的 httpx.Client，避免全局共享连接池的线程安全问题。

    Returns:
        (global_macro_html, expert_review_html, health_check_html, penetration_deep_html,
         global_macro_cached, expert_review_cached, health_check_cached, penetration_deep_cached) 八元组
    """
    from src.python.config import get_llm_config

    llm_config = get_llm_config()
    if llm_config is None:
        return (None, None, None, None, False, False, False, False)

    # ── 预计算指纹 + 缓存键 ──
    fp_global_macro = _compute_fingerprint(
        a_indices, us_indices, total_mv, total_profit, categories,
    )
    fp_expert_review = _expert_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
    )
    fp_health_check = _health_check_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
    )
    fp_penetration_deep = _penetration_deep_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
    )

    key_global_macro = _CACHE_PREFIX_LLM + f"global_macro_{fp_global_macro}"
    key_expert_review = _CACHE_PREFIX_LLM + f"expert_review_{fp_expert_review}"
    key_health_check = _CACHE_PREFIX_LLM + f"health_check_{fp_health_check}"
    key_penetration_deep = _CACHE_PREFIX_LLM + f"penetration_deep_{fp_penetration_deep}"

    ttl_global_macro = _get_cache_ttl_llm("macro")
    ttl_expert_review = _get_cache_ttl_llm("expert")
    ttl_health_check = _get_cache_ttl_llm("health")
    ttl_penetration_deep = _get_cache_ttl_llm("penetration")

    force_flag = force
    can_cache_global_macro = not force_flag and llm_config.get("cache_enabled_global_macro", True)
    can_cache_expert_review = not force_flag and llm_config.get("cache_enabled_expert_review", True)
    can_cache_health_check = not force_flag and llm_config.get("cache_enabled_health_check", True)
    can_cache_penetration_deep = not force_flag and llm_config.get("cache_enabled_penetration_deep", True)

    # ── 预检缓存（仅当缓存开启且非强制模式）──
    def _precheck(cache_key, cache_ttl, can_cache, thinking_key):
        if not can_cache:
            return (None, False)
        cached = cache_get(cache_key, cache_ttl)
        if not cached:
            return (None, False)
        clean = _strip_token_line(cached)
        model = _extract_model_from_cached(cached)
        hint = _CACHE_LINE_MODEL_TPL.format(model=model) if model else _CACHE_LINE_HTML
        if llm_config.get(thinking_key, False):
            hint = hint.rstrip().replace("</p>", " | Extended Thinking</p>", 1)
        return (clean + hint, True)

    global_macro_result, global_macro_cached_flag = _precheck(
        key_global_macro, ttl_global_macro, can_cache_global_macro, "thinking_enabled_global_macro",
    )
    expert_review_result, expert_review_cached_flag = _precheck(
        key_expert_review, ttl_expert_review, can_cache_expert_review, "thinking_enabled_expert_review",
    )
    health_check_result, health_check_cached_flag = _precheck(
        key_health_check, ttl_health_check, can_cache_health_check, "thinking_enabled_health_check",
    )
    penetration_deep_result, penetration_deep_cached_flag = _precheck(
        key_penetration_deep, ttl_penetration_deep, can_cache_penetration_deep, "thinking_enabled_penetration_deep",
    )

    # ── 仅对缓存未命中的模块提交线程池任务 ──
    needs_global_macro = global_macro_result is None
    needs_expert_review = expert_review_result is None
    needs_health_check = health_check_result is None
    needs_penetration_deep = penetration_deep_result is None

    if needs_global_macro or needs_expert_review or needs_health_check or needs_penetration_deep:
        with ThreadPoolExecutor(max_workers=4) as executor:
            _futures: dict[Any, str] = {}

            if needs_global_macro:
                def _run_global_macro() -> tuple[Optional[str], bool]:
                    logger.info("正在生成：全球政经局势分析...")
                    c = httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return generate_global_macro(
                            a_indices, us_indices, total_mv, total_profit, categories,
                            sector_flow=sector_flow, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_global_macro)] = "macro"

            if needs_expert_review:
                def _run_expert_review() -> tuple[Optional[str], bool]:
                    logger.info("正在生成：智囊团深度复盘（耗时较长，请耐心等待）...")
                    c = httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return generate_expert_review(
                            total_mv, total_cost, total_profit, total_today_profit,
                            holdings_count, categories, penetrated_assets,
                            holdings_details=holdings_details, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_expert_review)] = "expert"

            if needs_health_check:
                def _run_health_check() -> tuple[Optional[str], bool]:
                    logger.info("正在生成：持仓体检报告（耗时较长，请耐心等待）...")
                    c = httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return generate_health_check(
                            total_mv, total_cost, total_profit, total_today_profit,
                            holdings_count, categories, penetrated_assets,
                            holdings_details=holdings_details, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_health_check)] = "health"

            if needs_penetration_deep:
                def _run_penetration_deep() -> tuple[Optional[str], bool]:
                    logger.info("正在生成：穿透深度分析...")
                    c = httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return generate_penetration_deep_analysis(
                            total_mv, total_cost, total_profit, total_today_profit,
                            holdings_count, categories, penetrated_assets,
                            holdings_details=holdings_details, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_penetration_deep)] = "penetration"

            _label_map: dict[str, str] = {
                "macro": "全球政经局势", "expert": "智囊团深度复盘",
                "health": "持仓体检报告", "penetration": "穿透深度分析",
            }

            for future in as_completed(_futures):
                try:
                    result, from_cache = future.result()
                    key = _futures[future]
                    if key == "macro":
                        global_macro_result, global_macro_cached_flag = result, from_cache
                    elif key == "expert":
                        expert_review_result, expert_review_cached_flag = result, from_cache
                    elif key == "health":
                        health_check_result, health_check_cached_flag = result, from_cache
                    elif key == "penetration":
                        penetration_deep_result, penetration_deep_cached_flag = result, from_cache
                    logger.info("%s生成完成" if result else "%s生成失败（跳过）", _label_map.get(key, key))
                except Exception:
                    logger.warning("LLM 生成线程异常", exc_info=True)

    logger.info("LLM 生成完成: 全球政经=%s, 智囊团=%s, 体检=%s, 穿透=%s",
                "OK" if global_macro_result else "跳过",
                "OK" if expert_review_result else "跳过",
                "OK" if health_check_result else "跳过",
                "OK" if penetration_deep_result else "跳过")
    return (global_macro_result, expert_review_result, health_check_result, penetration_deep_result,
            global_macro_cached_flag, expert_review_cached_flag, health_check_cached_flag, penetration_deep_cached_flag)
