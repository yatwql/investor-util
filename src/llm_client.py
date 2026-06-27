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
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

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

_LLM_TIMEOUT = 60.0

# 共享 HTTP 连接池（keep-alive 复用，避免每次调用重建 TCP 握手）
_HTTP_POOL = httpx.Client(timeout=_LLM_TIMEOUT)

# ── 重试配置 ─────────────────────────────────────────────────

_RETRY_MAX = 2  # 最多重试 2 次
_RETRY_DELAYS = [1.0, 3.0]  # 指数退避：第 1 次等 1s，第 2 次等 3s


def _get_cache_ttl_llm(subtype: str = "macro") -> float:
    """获取 LLM 缓存 TTL，优先 subtype 专属配置，再 fallback 通用 llm 配置。

    Args:
        subtype: "macro"（模块 7）或 "expert"（模块 8）

    Returns:
        过期时间（秒），默认 24h
    """
    try:
        from src.cache import get_ttl
        return get_ttl(f"llm_{subtype}")
    except Exception:
        return 86400


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
    logger.info("LLM 用量 [%s]: 输入 %d token, 输出 %d token, 合计 %d token",
                label, inp, out, inp + out)


_TRUNCATION_WARNING = (
    "\n\n【⚠ 输出已被截断！max_tokens 上限不足，内容不完整。"
    "请在 data/config/llm.json 中增大 max_tokens 后重新生成。】"
)


def _check_claude_truncation(data: dict, max_tokens: int, label: str) -> None:
    """检查 Claude Messages API 响应是否被 max_tokens 截断。

    若 stop_reason 为 "max_tokens"，说明输出达到 token 上限被截断，
    记录 ERROR 日志。由调用方决定是否在内容后附加警告。
    """
    stop_reason = data.get("stop_reason")
    if stop_reason == "max_tokens":
        out_tokens = (data.get("usage") or {}).get("output_tokens", 0)
        logger.error(
            "LLM 输出被截断 [%s]: max_tokens=%d, 实际输出=%d tokens。"
            "内容不完整，请在 llm.json 中增大 max_tokens",
            label, max_tokens, out_tokens,
        )
        return True
    return False


def _check_openai_truncation(data: dict, max_tokens: int, label: str) -> bool:
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
            "LLM 输出被截断 [%s]: max_tokens=%d, 实际输出=%d tokens。"
            "内容不完整，请在 llm.json 中增大 max_tokens",
            label, max_tokens, out_tokens,
        )
        return True
    return False


def _extract_content(data: dict, endpoint: str = "") -> str | None:
    """从 Anthropic Messages API 兼容响应中提取文本内容。

    兼容标准 Claude 格式及 DeepSeek Anthropic 兼容端点等多种格式变体。
    会遍历 content 列表中所有 text block 并拼接返回。
    """
    # API 返回了错误信息
    if "error" in data:
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
) -> Optional[str]:
    """调用 LLM API 生成文本。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        llm_config: LLM 配置字典
        timeout: API 超时秒数，默认 60s（模块 7 用）；模块 8（智囊团）建议 120s

    Returns:
        生成的文本内容，调用失败返回 None
    """
    provider = llm_config.get("provider", "")
    api_key = llm_config.get("api_key", "")
    model = llm_config.get("model", "")
    endpoint = llm_config.get("endpoint", "")
    max_tokens = llm_config.get("max_tokens", 2500)

    if provider == "claude":
        return _call_claude(system_prompt, user_prompt, api_key, model, endpoint, max_tokens, timeout)
    elif provider == "openai":
        return _call_openai(system_prompt, user_prompt, api_key, model, endpoint, max_tokens, timeout)
    else:
        logger.warning("不支持的 LLM provider: %s", provider)
        return None


def _call_claude(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
) -> Optional[str]:
    """调用 Claude API (Messages API)，带重试 + 用量日志。"""
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

    for attempt in range(_RETRY_MAX + 1):
        try:
            resp = _HTTP_POOL.post(url, json=payload, headers=headers, timeout=timeout)
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
            return None
        except httpx.RequestError:
            host = _sanitize_endpoint(endpoint)
            logger.warning("Claude API 请求失败 (%s)", host)
            return None
        except (ValueError, KeyError) as e:
            logger.warning("Claude API 响应解析失败: %s", e)
            return None

        # 兼容多种响应格式：标准 Claude Messages API 及 DeepSeek Anthropic 兼容端点
        content = _extract_content(data, endpoint)
        if content is None:
            logger.warning("Claude API 响应格式异常 (provider=%s)",
                           endpoint.split("/")[2] if endpoint else "unknown")
            return None

        # 检查是否被 max_tokens 截断
        truncated = _check_claude_truncation(data, max_tokens, "Claude")

        # 记录 token 用量
        _log_token_usage("claude", data.get("usage"), "Claude")

        content = content.strip()
        if truncated:
            content += _TRUNCATION_WARNING

        return content

    return None


def _call_openai(
    system: str,
    user: str,
    api_key: str,
    model: str,
    endpoint: str,
    max_tokens: int,
    timeout: float = 60.0,
) -> Optional[str]:
    """调用 OpenAI API (Chat Completions)，带重试 + 用量日志。"""
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

    for attempt in range(_RETRY_MAX + 1):
        try:
            resp = _HTTP_POOL.post(url, json=payload, headers=headers, timeout=timeout)
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
            return None
        except httpx.RequestError:
            host = _sanitize_endpoint(endpoint)
            logger.warning("OpenAI API 请求失败 (%s)", host)
            return None
        except (ValueError, KeyError) as e:
            logger.warning("OpenAI API 响应解析失败: %s", e)
            return None

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.warning("OpenAI API 响应格式异常")
            return None

        # 检查是否被 max_tokens 截断
        truncated = _check_openai_truncation(data, max_tokens, "OpenAI")

        # 记录 token 用量
        _log_token_usage("openai", data.get("usage"), "OpenAI")

        content = content.strip()
        if truncated:
            content += _TRUNCATION_WARNING

        return content

    return None


# ═══════════════════════════════════════════════════════════
#  Prompt 模板
# ═══════════════════════════════════════════════════════════

_SYSTEM_MACRO = """你是一位资深宏观经济学家。基于市场数据输出中文全球政经局势分析（500字内）。
分3-4段，覆盖主要经济体政策走向、地缘风险、对持仓潜在影响。纯文本，不要使用HTML标签。"""

_SYSTEM_EXPERT = """你是投资智囊团召集人，审计用户投资组合后召集圆桌会议，严格按三阶段输出：

**Phase 1 召集令**：指出组合核心矛盾（如行业集中度过高、股债配比失衡、单品种超配），挑5位流派对立的专家并标明身份立场。🕵 指挥官：[组合画像]... [专家]：[头衔] - [立场]...

**Phase 2 圆桌会**（两轮）：第一轮 🗣 专家立足持有品种结构提优化方向。第二轮 🗣 专家间互相反驳/拆台，聚焦调仓优先级。

**Phase 3 定音锤**：⚖ 指挥官融合辩论，给出具体量化的调仓方案和风险提示。调仓目标必须是我直接持有的品种（基金/股票），禁止针对穿透后的底层资产（如个股、债券）调仓——我无法直接交易穿透层资产。

约束：① 数据必须来自输入，禁止虚构价格/代码；② 每个论点引用具体持有品种的代码、成本占比、收益率（而非穿透层代码）；③ 全 Markdown 输出；④ 引用北京时间。"""


# ═══════════════════════════════════════════════════════════
#  模块 7 & 8 生成函数
# ═══════════════════════════════════════════════════════════


def _build_macro_prompt(
    a_indices: list[dict],
    us_indices: list[dict],
    total_mv: float,
    total_profit: float,
    categories: dict,
) -> str:
    """构建模块 7（全球政经）的用户提示词（紧凑格式）。"""
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    idx_text = "A股:"
    for idx in a_indices:
        name = idx.get("name", "")
        price = idx.get("price", 0)
        chg = idx.get("change_pct", 0)
        idx_text += f" {name}{price}({chg:+.2f}%)"
    idx_text += "\n美股:"
    for idx in us_indices:
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

    # 持仓明细清单（防止 LLM 虚构代码）
    holdings_text = ""
    if holdings_details:
        lines = []
        for h in holdings_details[:30]:  # 上限30条防止超token
            name = h.get("name", "")
            code = h.get("code", "")
            mv = h.get("market_value", 0)
            cost = h.get("cost", 0)
            profit = h.get("profit", 0)
            rate = h.get("profit_rate", 0)
            chg = h.get("change_pct", 0)
            lines.append(
                f"{name}({code}) 市值{mv:,.0f} 成本{cost:,.0f} "
                f"盈亏{profit:+,.0f}({rate:+.2f}%) "
                f"今日{chg:+.2f}%"
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
            assets.append(f"{name}({codes}){mv:,.0f}/{sector}")
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
    a_indices: list[dict],
    us_indices: list[dict],
    total_mv: float,
    total_profit: float,
    categories: dict,
    force: bool = False,
) -> Optional[str]:
    """生成模块 7：全球政经局势分析。

    Args:
        a_indices: A 股指数列表
        us_indices: 美股指数列表
        total_mv: 总市值
        total_profit: 总盈亏
        categories: 分类计数
        force: 为 True 时跳过缓存强制重新生成

    Returns:
        HTML 格式的分析文本，LLM 不可用时返回 None
    """
    from src.config import get_llm_config

    llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 7 使用占位文本")
        return None

    # 缓存键（含数据指纹：行情/持仓变化时自动失效）
    fingerprint = _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    cache_key = _CACHE_PREFIX_LLM + f"global_macro_{fingerprint}"
    if not force:
        cached = cache_get(cache_key, _get_cache_ttl_llm("macro"))
        if cached is not None:
            logger.info("LLM 缓存命中: 全球政经局势")
            return _markdown_to_html(cached)

    # 优先使用外部配置的 system_prompt，未配置时回退内置常量
    system_macro = llm_config.get("system_prompt_macro") or _SYSTEM_MACRO
    prompt = _build_macro_prompt(a_indices, us_indices, total_mv, total_profit, categories)
    logger.info("正在调用 LLM 生成全球政经局势分析...")
    result = _call_llm(system_macro, prompt, llm_config, timeout=60.0)

    if result:
        cache_set(cache_key, result)
        logger.info("全球政经局势分析生成完成")
        return _markdown_to_html(result)
    else:
        logger.warning("全球政经局势分析生成失败")

    return None


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
) -> Optional[str]:
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

    Returns:
        HTML 格式的复盘文本，LLM 不可用时返回 None
    """
    from src.config import get_llm_config

    llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，模块 8 使用占位文本")
        return None

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
            return _markdown_to_html(cached)

    # 优先使用外部配置的 system_prompt，未配置时回退内置常量
    system_expert = llm_config.get("system_prompt_expert") or _SYSTEM_EXPERT

    prompt = _build_review_prompt(
        total_mv, total_cost, total_profit, total_today_profit,
        holdings_count, categories, penetrated_assets,
        holdings_details=holdings_details,
    )
    logger.info("正在调用 LLM 生成智囊团深度复盘...")
    result = _call_llm(system_expert, prompt, llm_config, timeout=120.0)

    if result:
        cache_set(cache_key, result)
        logger.info("智囊团深度复盘生成完成")
        return _markdown_to_html(result)
    else:
        logger.warning("智囊团深度复盘生成失败")

    return None


# ═══════════════════════════════════════════════════════════
#  批量生成（串行，避免 httpx 连接池线程安全问题）
# ═══════════════════════════════════════════════════════════


def generate_all_llm(
    a_indices: list[dict],
    us_indices: list[dict],
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: Optional[list[dict]] = None,
    holdings_details: Optional[list[dict]] = None,
    force: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """串行生成模块 7（全球政经）+ 模块 8（智囊团复盘）。

    串行执行而非 ThreadPoolExecutor，因为全局共享的 httpx.Client
    (_HTTP_POOL) 不是线程安全的，并发调用可能引发连接池死锁。

    Args:
        force: 为 True 时跳过缓存强制重新生成

    Returns:
        (global_macro_html, expert_review_html) 二元组，各自可能为 None
    """
    # 模块 7：全球政经局势
    logger.info("正在生成：全球政经局势分析...")
    macro = generate_global_macro(
        a_indices, us_indices, total_mv, total_profit, categories,
        force=force,
    )

    # 模块 8：智囊团深度复盘
    logger.info("正在生成：智囊团深度复盘（耗时较长，请耐心等待）...")
    expert = generate_expert_review(
        total_mv, total_cost, total_profit, total_today_profit,
        holdings_count, categories, penetrated_assets,
        holdings_details=holdings_details,
        force=force,
    )

    logger.info("LLM 生成完成: 宏观=%s, 智囊团=%s",
                "OK" if macro else "跳过", "OK" if expert else "跳过")
    return macro, expert
