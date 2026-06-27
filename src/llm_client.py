"""LLM 智能分析客户端 — 接入 Claude API / OpenAI API。

为报告模块 7（全球政经局势）和模块 8（智囊团深度复盘）生成内容。

API Key 通过外部配置文件管理（data/config/llm.json），
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
from typing import Any, Optional
import threading

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

# 线程本地 HTTP 连接池（每个线程独立创建，避免多线程竞态）
_thread_local = threading.local()


def _get_http_pool() -> httpx.Client:
    """获取当前线程的 HTTP 连接池，懒加载确保每个线程只创建一次。"""
    pool: httpx.Client | None = getattr(_thread_local, "http_pool", None)
    if pool is None:
        pool = httpx.Client(timeout=_LLM_TIMEOUT)
        _thread_local.http_pool = pool
    return pool

# ── 重试配置 ─────────────────────────────────────────────────

_RETRY_MAX = 2  # 最多重试 2 次
_RETRY_DELAYS = [1.0, 3.0]  # 指数退避：第 1 次等 1s，第 2 次等 3s


def _get_cache_ttl_llm(subtype: str = "macro") -> float:
    """获取 LLM 缓存 TTL。

    TTL 优先级：
      1. llm.json 中的 cache_ttl_macro / cache_ttl_expert（自定义配置）
      2. config.json 中的 cache_ttl.llm_macro / cache_ttl.llm_expert
      3. 代码默认值（全局政经 14400s / 智囊团 7200s）

    Args:
        subtype: "macro"（模块 7）、"expert"（模块 8）或 "news"（新闻关联）

    Returns:
        过期时间（秒）
    """
    # 优先从 llm.json 读取自定义 TTL
    try:
        from src.config import get_llm_config
        llm_config = get_llm_config()
        if llm_config:
            key = f"cache_ttl_{subtype}"
            ttl = llm_config.get(key)
            if ttl is not None and isinstance(ttl, (int, float)) and ttl > 0:
                return float(ttl)
    except Exception:
        pass

    # fallback 到 config.json cache_ttl -> 代码默认值
    try:
        from src.cache import get_ttl
        return get_ttl(f"llm_{subtype}")
    except Exception:
        defaults: dict[str, float] = {"macro": 14400, "expert": 7200, "news": 3600}
        return defaults.get(subtype, 3600)


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


_TRUNCATION_WARNING = (
    "\n\n【⚠ 输出已被截断！max_tokens 上限不足，内容不完整。"
    "请在 data/config/llm.json 中增大 max_tokens 后重新生成。】"
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
            "内容不完整，请在 llm.json 中增大 %s",
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
            "内容不完整，请在 llm.json 中增大 %s",
            label, config_field, max_tokens, out_tokens, config_field,
        )
        return True
    return False


def _extract_content(data: dict, endpoint: str = "") -> str | None:
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


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    llm_config: dict,
    timeout: float = 60.0,
    http_client: httpx.Client | None = None,
    max_tokens: int | None = None,
    config_field: str = "max_tokens",
) -> tuple[Optional[str], Optional[dict]]:
    """调用 LLM API 生成文本。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        llm_config: LLM 配置字典
        timeout: API 超时秒数，默认 60s（模块 7 用）；模块 8（智囊团）建议 120s
        http_client: 可选的 httpx.Client 实例
        max_tokens: 可选覆盖值，优先级高于 llm_config 中的对应字段
        config_field: llm.json 中的配置字段名（如 "max_tokens_macro" / "max_tokens_expert"），
            截断时在日志中提示用户增大该字段

    Returns:
        (content, usage) — content 为文本，usage 为 API 用量字典，失败时均为 None
    """
    provider = llm_config.get("provider", "")
    api_key = llm_config.get("api_key", "")
    model = llm_config.get("model", "")
    endpoint = llm_config.get("endpoint", "")
    max_tokens = max_tokens or 2500

    if provider == "claude":
        return _call_claude(system_prompt, user_prompt, api_key, model, endpoint, max_tokens, timeout, http_client=http_client, config_field=config_field)
    elif provider == "openai":
        return _call_openai(system_prompt, user_prompt, api_key, model, endpoint, max_tokens, timeout, http_client=http_client, config_field=config_field)
    else:
        logger.warning("不支持的 LLM provider: %s", provider)
        return (None, None)


def _call_claude(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
    http_client: httpx.Client | None = None,
    config_field: str = "max_tokens",
) -> tuple[Optional[str], Optional[dict]]:
    """调用 Claude API (Messages API)，带重试 + 用量日志。

    Args:
        http_client: 可选的 httpx.Client 实例。传入时使用该客户端发起 HTTP 请求，
            而非全局共享的 _HTTP_POOL。用于多线程场景下避免连接池线程安全问题。

    Returns:
        (content, usage) — usage 为 API 返回的用量字典，失败时均为 None
    """
    url = endpoint or "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model or "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    client = http_client or _get_http_pool()

    for attempt in range(_RETRY_MAX + 1):
        try:
            resp = client.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in (429, 503) and attempt < _RETRY_MAX:
                delay = _RETRY_DELAYS[attempt]
                logger.warning("Claude API %d (尝试 %d/%d)，%.1fs 后重试...",
                               resp.status_code, attempt + 1, _RETRY_MAX + 1, delay)
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            logger.warning("Claude API 超时")
            return (None, None)
        except httpx.RequestError:
            host = _sanitize_endpoint(endpoint)
            logger.warning("Claude API 请求失败 (%s)", host)
            return (None, None)
        except (ValueError, KeyError) as e:
            logger.warning("Claude API 响应解析失败: %s", e)
            return (None, None)

        # 兼容多种响应格式：标准 Claude Messages API 及 DeepSeek Anthropic 兼容端点
        content = _extract_content(data, endpoint)
        if content is None:
            logger.warning("Claude API 响应格式异常 (provider=%s)",
                           endpoint.split("/")[2] if endpoint else "unknown")
            return (None, None)

        # 检查是否被 max_tokens 截断
        truncated = _check_claude_truncation(data, max_tokens, "Claude", config_field)

        # 记录 token 用量
        usage = data.get("usage")
        _log_token_usage("claude", usage, "Claude")

        content = content.strip()
        if truncated:
            content += _TRUNCATION_WARNING

        return (content, usage)

    return (None, None)


def _call_openai(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
    http_client: httpx.Client | None = None,
    config_field: str = "max_tokens",
) -> tuple[Optional[str], Optional[dict]]:
    """调用 OpenAI API (Chat Completions)，带重试 + 用量日志。

    Args:
        http_client: 可选的 httpx.Client 实例。传入时使用该客户端发起 HTTP 请求，
            而非全局共享的 _HTTP_POOL。用于多线程场景下避免连接池线程安全问题。

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
    client = http_client or _get_http_pool()

    for attempt in range(_RETRY_MAX + 1):
        try:
            resp = client.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in (429, 503) and attempt < _RETRY_MAX:
                delay = _RETRY_DELAYS[attempt]
                logger.warning("OpenAI API %d (尝试 %d/%d)，%.1fs 后重试...",
                               resp.status_code, attempt + 1, _RETRY_MAX + 1, delay)
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            logger.warning("OpenAI API 超时")
            return (None, None)
        except httpx.RequestError:
            host = _sanitize_endpoint(endpoint)
            logger.warning("OpenAI API 请求失败 (%s)", host)
            return (None, None)
        except (ValueError, KeyError) as e:
            logger.warning("OpenAI API 响应解析失败: %s", e)
            return (None, None)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.warning("OpenAI API 响应格式异常")
            return (None, None)

        # 检查是否被 max_tokens 截断
        truncated = _check_openai_truncation(data, max_tokens, "OpenAI", config_field)

        # 记录 token 用量
        usage = data.get("usage")
        _log_token_usage("openai", usage, "OpenAI")

        content = content.strip()
        if truncated:
            content += _TRUNCATION_WARNING

        return (content, usage)

    return (None, None)


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

_SYSTEM_NEWS_CORRELATION = """你是一位资深金融分析师。分析以下每条财经新闻与用户投资组合持仓的关联性。

关联度标准：
- 高：新闻内容直接涉及持仓品种、所属行业或相关重大政策
- 中：新闻内容与持仓品种有间接关联（产业链、相关行业）
- 低：新闻内容与持仓品种关联较弱
- 无关：新闻内容与持仓品种无明显关联

对每条新闻输出JSON数组，格式：
[{"idx": 0, "relevance": "高|中|低|无关", "analysis": "不超过30字的原因分析"}, ...]

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
) -> str:
    """构建模块 7（全球政经）的用户提示词（紧凑格式）。"""
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

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【指数】{idx_text}\n"
        f"【持仓】总市值{total_mv:,.0f} 总盈亏{total_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}\n"
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

    # 缓存键（含数据指纹：行情/持仓变化时自动失效）
    fingerprint = _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    cache_key = _CACHE_PREFIX_LLM + f"global_macro_{fingerprint}"
    if not force:
        cached = cache_get(cache_key, _get_cache_ttl_llm("macro"))
        if cached is not None:
            logger.info("LLM 缓存命中: 全球政经局势")
            return (cached, True)

    # 优先使用外部配置的 system_prompt，未配置时回退内置常量
    system_macro = llm_config.get("system_prompt_macro") or _SYSTEM_MACRO
    prompt = _build_macro_prompt(a_indices, us_indices, total_mv, total_profit, categories)
    logger.info("正在调用 LLM 生成全球政经局势分析...")
    macro_mt = llm_config.get("max_tokens_macro") or llm_config.get("max_tokens", 800)
    result, usage = _call_llm(system_macro, prompt, llm_config, timeout=60.0, http_client=http_client, max_tokens=macro_mt, config_field="max_tokens_macro")

    if result:
        html = _markdown_to_html(result)
        if usage:
            inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            out = usage.get("output_tokens", usage.get("completion_tokens", 0))
            html += f'<p style="color:#888;font-size:12px">⚡ Token 用量：输入 {inp:,} / 输出 {out:,} = {inp + out:,}</p>'
        cache_set(cache_key, html)
        logger.info("全球政经局势分析生成完成")
        return (html, False)
    else:
        logger.warning("全球政经局势分析生成失败")

    return (None, False)


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

    # 缓存键（含数据指纹：持仓变化时自动失效）
    fingerprint = _compute_fingerprint(total_mv, total_cost, total_profit,
                                       total_today_profit, holdings_count,
                                       categories, penetrated_assets,
                                       holdings_details)
    cache_key = _CACHE_PREFIX_LLM + f"expert_review_{fingerprint}"
    if not force:
        cached = cache_get(cache_key, _get_cache_ttl_llm("expert"))
        if cached is not None:
            logger.info("LLM 缓存命中: 智囊团深度复盘")
            return (cached, True)

    # 优先使用外部配置的 system_prompt，未配置时回退内置常量
    system_expert = llm_config.get("system_prompt_expert") or _SYSTEM_EXPERT

    prompt = _build_review_prompt(
        total_mv, total_cost, total_profit, total_today_profit,
        holdings_count, categories, penetrated_assets,
        holdings_details=holdings_details,
    )
    expert_mt = llm_config.get("max_tokens_expert") or llm_config.get("max_tokens", 8192)
    logger.info("正在调用 LLM 生成智囊团深度复盘...")
    result, usage = _call_llm(system_expert, prompt, llm_config, timeout=120.0, http_client=http_client, max_tokens=expert_mt, config_field="max_tokens_expert")

    if result:
        html = _markdown_to_html(result)
        if usage:
            inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
            out = usage.get("output_tokens", usage.get("completion_tokens", 0))
            html += f'<p style="color:#888;font-size:12px">⚡ Token 用量：输入 {inp:,} / 输出 {out:,} = {inp + out:,}</p>'
        cache_set(cache_key, html)
        logger.info("智囊团深度复盘生成完成")
        return (html, False)
    else:
        logger.warning("智囊团深度复盘生成失败")

    return (None, False)


# ═══════════════════════════════════════════════════════════
#  新闻关联分析（LLM 增强）
# ═══════════════════════════════════════════════════════════


def _build_holdings_summary(holdings: list, penetrated_assets: list | None = None) -> str:
    """构建持仓摘要文本（紧凑格式），供新闻关联分析 Prompt 使用。

    Args:
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产（可选）

    Returns:
        紧凑格式的持仓摘要文本
    """
    lines: list[str] = []
    for i, h in enumerate(holdings[:20]):
        lines.append(f"{i + 1}. {h.name} ({h.code})")
    if penetrated_assets:
        for a in penetrated_assets[:10]:
            name = a.get("name", "")
            codes = ",".join(a.get("codes", []))
            if name or codes:
                lines.append(f"    [穿透] {name} ({codes})")
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


def _apply_llm_analysis(news_data: list[dict], llm_response: str) -> list[dict]:
    """解析 LLM JSON 响应并富化新闻数据。

    遍历 LLM 返回的 JSON 数组，将每条新闻的关联分析写入
    news_data 对应项的 llm_analysis 字段。

    Args:
        news_data: 原始新闻列表
        llm_response: LLM 返回的 JSON 字符串

    Returns:
        富化后的新闻列表（含 llm_analysis 字段），
        解析失败时返回原始新闻列表
    """
    import json
    import re

    # 从可能含 Markdown 代码块的文本中提取 JSON
    text = llm_response.strip()
    if "```" in text:
        # 取第一个代码块的内容
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
        return news_data

    if not isinstance(analyses, list):
        logger.warning("LLM 新闻分析返回格式异常: 非数组")
        return news_data

    # 建立 idx → (relevance, analysis) 映射
    analysis_map: dict[int, str] = {}
    for a in analyses:
        idx = a.get("idx")
        if not isinstance(idx, int) or idx < 0 or idx >= len(news_data):
            continue
        relevance = a.get("relevance", "")
        analysis_text = a.get("analysis", "")
        # 跳过"无关"项，不浪费列空间
        if relevance == "无关":
            continue
        if analysis_text:
            analysis_map[idx] = f"[{relevance}] {analysis_text}"
        else:
            analysis_map[idx] = f"[{relevance}]"

    # 富化新闻数据
    enriched: list[dict] = []
    for i, item in enumerate(news_data):
        item_copy = dict(item)
        if i in analysis_map:
            item_copy["llm_analysis"] = analysis_map[i]
        enriched.append(item_copy)

    if analysis_map:
        logger.info("LLM 新闻关联: 富化 %d/%d 条", len(analysis_map), len(news_data))
    else:
        logger.info("LLM 新闻关联: 全部判定为无关")

    return enriched


def enhance_news_correlation(
    news_data: list[dict],
    holdings: list,
    penetrated_assets: list | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
) -> tuple[list[dict], bool, dict]:
    """使用 LLM 增强新闻与持仓的关联分析。

    对关键词匹配后的新闻进行 LLM 二次分析：
    - 判定每条的关联度（高/中/低/无关）
    - 给出简要原因分析
    - 写入 news_data 各条的 llm_analysis 字段

    Args:
        news_data: 关键词匹配后的新闻列表（由 build_news_data 返回）
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产（可选）
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
    sorted_news = sorted(
        news_data,
        key=lambda x: len(x.get("matched_keywords", [])),
        reverse=True,
    )
    top_news = sorted_news[:30]

    # 缓存键（含新闻内容 + 持仓的指纹）
    holdings_summary = [
        {"name": h.name, "code": h.code}
        for h in holdings[:20]
    ]
    fingerprint = _compute_fingerprint(
        top_news, holdings_summary, penetrated_assets,
    )
    cache_key = _CACHE_PREFIX_LLM + f"news_corr_{fingerprint}"

    if not force:
        cached = cache_get(cache_key, _get_cache_ttl_llm("news"))
        if cached is not None:
            logger.info("LLM 缓存命中: 新闻关联分析")
            return (cached, True, {})

    # 构建 Prompt
    system_prompt = (
        llm_config.get("system_prompt_news_correlation")
        or _SYSTEM_NEWS_CORRELATION
    )
    holdings_text = _build_holdings_summary(holdings, penetrated_assets)
    news_text = _build_news_summary(top_news)
    user_prompt = (
        f"【持仓信息】\n"
        f"{holdings_text}\n\n"
        f"【新闻列表】\n"
        f"{news_text}\n\n"
        f"请分析以上每条新闻与持仓的关联性，输出JSON数组。"
    )

    logger.info("正在调用 LLM 增强新闻关联分析...")
    max_tokens = llm_config.get("max_tokens_news_correlation", 2000)
    result, usage = _call_llm(
        system_prompt, user_prompt, llm_config,
        timeout=60.0, http_client=http_client,
        max_tokens=max_tokens,
        config_field="max_tokens_news_correlation",
    )

    if not result:
        logger.warning("LLM 新闻关联分析失败")
        return (news_data, False, {})

    # 解析 JSON 并富化
    enriched = _apply_llm_analysis(news_data, result)

    # 构建 token 用量字典
    token_usage: dict = {}
    if usage:
        inp = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        out = usage.get("output_tokens", usage.get("completion_tokens", 0))
        token_usage = {
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": inp + out,
        }
        _log_token_usage(
            llm_config.get("provider", "unknown"),
            usage, "新闻关联",
        )

    # 缓存
    cache_set(cache_key, enriched)
    logger.info(
        "LLM 新闻关联分析完成: %d 条 → %d 条含 LLM 分析",
        len(news_data),
        sum(1 for n in enriched if n.get("llm_analysis")),
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
        force: 为 True 时跳过缓存强制重新生成

    Returns:
        (macro_html, expert_html, macro_cached, expert_cached) 四元组
        各自可能为 None/False
    """

    def _run_macro() -> tuple[Optional[str], bool]:
        """在线程中生成模块 7，使用独立 httpx.Client。"""
        logger.info("正在生成：全球政经局势分析...")
        client = httpx.Client(timeout=_LLM_TIMEOUT)
        try:
            return generate_global_macro(
                a_indices, us_indices, total_mv, total_profit, categories,
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

    # 缓存预检：先检查双方是否已缓存，避免不必要线程开销
    _macro_fp = _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    _macro_key = _CACHE_PREFIX_LLM + f"global_macro_{_macro_fp}"
    _expert_fp = _compute_fingerprint(total_mv, total_cost, total_profit,
                                       total_today_profit, holdings_count,
                                       categories, penetrated_assets,
                                       holdings_details)
    _expert_key = _CACHE_PREFIX_LLM + f"expert_review_{_expert_fp}"
    _macro_cached = cache_get(_macro_key, _get_cache_ttl_llm("macro"))
    _expert_cached = cache_get(_expert_key, _get_cache_ttl_llm("expert"))
    if _macro_cached is not None and _expert_cached is not None:
        logger.info("LLM 双缓存命中，跳过线程池")
        return (_macro_cached, _expert_cached, True, True)

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
