"""LLM 生成编排模块 — LLM 调用编排与批量生成。"""

from __future__ import annotations

import logging
from concurrent.futures import as_completed
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx

from src.python.cache import set as cache_set  # noqa: F401
from src.python.llm.api import (
    _AUTO_INCREASE_FACTOR,
    _CACHE_LINE_HTML,
    _CACHE_LINE_MODEL_TPL,
    _CONTENT_FILTER_RECOVERY,
    _LLM_TIMEOUT,
    _TRUNCATION_MARKER,
    _extract_model_from_cached,
    _log_token_usage,
    _strip_token_line,
)
from src.python.llm.fingerprint import (
    _compute_fingerprint,
    _expert_review_fingerprint,
    _get_cache_ttl_llm,
    _health_check_fingerprint,
    _penetration_deep_fingerprint,
)
from src.python.llm.markdown import _markdown_to_html
from src.python.llm.pricing import _estimate_cost
from src.python.llm.session import _record_per_module
from src.python.llm.prompts import (
    _CACHE_PREFIX_LLM,
    _LLM_MODULE_FAILURE,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_API_ERROR,
    FAIL_REASON_DISABLED,
    _SYSTEM_GLOBAL_MACRO,
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_HEALTH_CHECK,
    _SYSTEM_PENETRATION_DEEP,
    _SYSTEM_NEWS_CORRELATION,
    _build_global_macro_prompt,
    _build_expert_review_prompt,
    _build_health_check_prompt,
    _build_penetration_deep_prompt,
    _build_holdings_summary,
    _build_news_correlation_summary,
)

logger = logging.getLogger("invest")

__all__ = [
    "_is_llm_module_enabled",
    "_generate_llm_content",
    "_apply_llm_news_correlation",
    "generate_global_macro",
    "generate_expert_review",
    "generate_health_check",
    "generate_penetration_deep_analysis",
    "enhance_news_correlation",
    "generate_all_llm",
]


def _is_llm_module_enabled(llm_config: dict | None, module_suffix: str) -> bool:
    """检查 LLM 模块是否已启用。

    读取 enabled_llm 嵌套字典（由 config.py _migrate_llm_settings 保证存在），
    默认 True（即旧配置无该开关时模块仍保持启用状态）。

    Args:
        llm_config: LLM 配置字典
        module_suffix: 模块后缀名（global_macro / expert_review / health_check /
                       penetration_deep / news_correlation）

    Returns:
        模块是否启用了 LLM 生成
    """
    if llm_config is None:
        return False
    enabled_map = llm_config.get("enabled_llm")
    if not isinstance(enabled_map, dict):
        return True  # 无 enabled_llm 配置时默认启用
    return bool(enabled_map.get(module_suffix, True))


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
        module_key: 模块键名（"global_macro"/"expert_review"/"health_check"/"penetration_deep"），
            用于记录失败原因供写入层读取

    Returns:
        (HTML 文本或 None, 是否来自缓存)
    """
    # 使用 lazy import 通过 llm_client 获取缓存和调用函数，
    # 确保 unittest.mock.patch("src.python.llm_client.XXX") 对测试生效
    import src.python.llm_client as _lm  # noqa: F811

    # 清除旧的失败原因
    if module_key:
        _LLM_MODULE_FAILURE.pop(module_key, None)

    # ── 缓存检查 ──
    if cache_enabled and not force:
        cached = _lm.cache_get(cache_key, cache_ttl)
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
    result, usage = _lm._call_llm(system_prompt, user_prompt, llm_config,
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
        result2, usage2 = _lm._call_llm(
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
        _lm.cache_set(cache_key, html)
        logger.info("LLM 内容生成完成: %s", cache_key)
        return (html, False)

    logger.warning("LLM 内容生成失败: %s", cache_key)
    if module_key:
        _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_API_ERROR
    return (None, False)


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
    """生成全球政经局势分析。

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
        logger.info("LLM 未配置，全球政经局势使用占位文本")
        _LLM_MODULE_FAILURE["global_macro"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    if not _is_llm_module_enabled(llm_config, "global_macro"):
        logger.info("全球政经局势 LLM 分析已禁用（enabled_llm.global_macro = false）")
        _LLM_MODULE_FAILURE["global_macro"] = FAIL_REASON_DISABLED
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_global_macro", True)
    fingerprint = _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    cache_key = _CACHE_PREFIX_LLM + f"global_macro_{fingerprint}"

    system_prompt = llm_config.get("system_prompt_global_macro") or _SYSTEM_GLOBAL_MACRO
    if llm_config.get("output_brief_global_macro", False):
        system_prompt += "\n（精简模式，输出 200 字以内。）"

    user_prompt = _build_global_macro_prompt(a_indices, us_indices, total_mv, total_profit, categories, sector_flow)

    import src.python.llm_client as _lm  # noqa: F811
    return _lm._generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("global_macro"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_global_macro") or llm_config.get("max_tokens", 800),
        timeout=llm_config.get("timeout_global_macro", 60.0),
        temperature=llm_config.get("temperature_global_macro"),
        model=llm_config.get("model_global_macro"),
        config_field="max_tokens_global_macro",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_global_macro", False),
        module_key="global_macro",
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
    """生成智囊团深度复盘。

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
        logger.info("LLM 未配置，智囊团深度复盘使用占位文本")
        _LLM_MODULE_FAILURE["expert_review"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    if not _is_llm_module_enabled(llm_config, "expert_review"):
        logger.info("智囊团深度复盘 LLM 分析已禁用（enabled_llm.expert_review = false）")
        _LLM_MODULE_FAILURE["expert_review"] = FAIL_REASON_DISABLED
        return (None, False)

    cache_enabled = llm_config.get("cache_enabled_expert_review", True)
    fingerprint = _expert_review_fingerprint(
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

    import src.python.llm_client as _lm  # noqa: F811
    return _lm._generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("expert_review"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_expert_review") or llm_config.get("max_tokens", 8192),
        timeout=llm_config.get("timeout_expert_review", 120.0),
        temperature=llm_config.get("temperature_expert_review"),
        model=llm_config.get("model_expert_review"),
        config_field="max_tokens_expert_review",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_expert_review", False),
        module_key="expert_review",
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
    """生成持仓体检报告。

    从风险分散度/流动性/收益合理性/成本结构四维度打分并给出改进建议。

    Args:
        llm_config: 可选的 LLM 配置字典。传入时跳过内部 get_llm_config() 调用。

    Returns:
        (HTML 格式的持仓体检报告或 None, 是否来自缓存)
    """
    if llm_config is None:
        from src.python.config import get_llm_config
        llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，持仓体检报告跳过")
        _LLM_MODULE_FAILURE["health_check"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    if not _is_llm_module_enabled(llm_config, "health_check"):
        logger.info("持仓体检报告 LLM 分析已禁用（enabled_llm.health_check = false）")
        _LLM_MODULE_FAILURE["health_check"] = FAIL_REASON_DISABLED
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

    import src.python.llm_client as _lm  # noqa: F811
    return _lm._generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("health_check"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_health_check") or llm_config.get("max_tokens", 4096),
        timeout=llm_config.get("timeout_health_check", 120.0),
        temperature=llm_config.get("temperature_health_check"),
        model=llm_config.get("model_health_check"),
        config_field="max_tokens_health_check",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_health_check", False),
        module_key="health_check",
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
    """生成穿透深度分析。

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
        logger.info("LLM 未配置，穿透深度分析跳过")
        _LLM_MODULE_FAILURE["penetration_deep"] = FAIL_REASON_NOT_CONFIGURED
        return (None, False)

    if not _is_llm_module_enabled(llm_config, "penetration_deep"):
        logger.info("穿透深度分析 LLM 分析已禁用（enabled_llm.penetration_deep = false）")
        _LLM_MODULE_FAILURE["penetration_deep"] = FAIL_REASON_DISABLED
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

    import src.python.llm_client as _lm  # noqa: F811
    return _lm._generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm("penetration_deep"),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get("max_tokens_penetration_deep") or llm_config.get("max_tokens", 4096),
        timeout=llm_config.get("timeout_penetration_deep", 90.0),
        temperature=llm_config.get("temperature_penetration_deep"),
        model=llm_config.get("model_penetration_deep"),
        config_field="max_tokens_penetration_deep",
        http_client=http_client,
        thinking_enabled=llm_config.get("thinking_enabled_penetration_deep", False),
        module_key="penetration_deep",
    )


# ═══════════════════════════════════════════════════════════
#  新闻关联分析（LLM 增强）
# ═══════════════════════════════════════════════════════════


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
        logger.warning("LLM 新闻关联分析 JSON 解析失败: %s", e)
        return [("低", "中性", "")] * batch_size

    if not isinstance(analyses, list):
        logger.warning("LLM 新闻关联分析返回格式异常: 非数组")
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
    _model_name_news_correlation = _model or llm_config.get("model", "") or "未指定"

    import src.python.llm_client as _lm_nc  # noqa: F811

    for global_pos in range(len(top_news)):
        item = top_news[global_pos]
        title_prefix = (item.get("title", "") or "")[:80]
        article_fp = _compute_fingerprint({"title": title_prefix, "holdings_fp": holdings_fp})
        article_key = _CACHE_PREFIX_LLM + f"news_item_{article_fp}"
        article_cache_keys[global_pos] = article_key

        if cache_enabled and not force:
            cached = _lm_nc.cache_get(article_key, _get_cache_ttl_llm("news_correlation"))
            if cached is not None:
                orig_i = top_to_original[global_pos]
                analysis_by_orig_idx[orig_i] = (
                    cached.get("relevance", "低"),
                    cached.get("sentiment", "中性"),
                    cached.get("analysis", ""),
                )
                logger.debug("LLM 新闻关联分析缓存命中: pos=%d orig=%d", global_pos, orig_i)
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
        logger.info("正在调用 LLM 新闻关联分析（%d 批未缓存，每批最多 %d 条）...",
                    len(uncached_batches), BATCH_SIZE)

        def _process_uncached_batch(batch_id: int, batch_positions: list[int]) -> tuple:
            """线程内处理一批未缓存新闻的 LLM 分析。"""
            import src.python.llm_client as _lm  # noqa: F811
            total_batches = len(uncached_batches)
            print(f"  [..] LLM 新闻关联分析 [{batch_id + 1}/{total_batches}] 批处理中 ({len(batch_positions)} 条)...")
            batch_client = _lm.httpx.Client(timeout=_LLM_TIMEOUT)
            try:
                batch_items = [top_news[gp] for gp in batch_positions]
                news_text = _build_news_correlation_summary(batch_items)  # idx 从 0 开始本批
                user_prompt = (
                    f"【持仓信息】\n"
                    f"{holdings_text}\n\n"
                    f"【新闻列表】\n"
                    f"{news_text}\n\n"
                    f"请分析以上每条新闻与持仓的关联性，输出JSON数组。"
                )
                result, usage = _lm._call_llm(
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
                        "LLM 新闻关联分析输出被截断（max_tokens=%d），自动以 %d 重新生成 [批 %d/%d]",
                        max_tokens, new_max, batch_id + 1, len(uncached_batches),
                    )
                    result2, usage2 = _lm._call_llm(
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

        import src.python.llm_client as _lm_pool  # noqa: F811
        with _lm_pool.ThreadPoolExecutor(max_workers=min(3, len(uncached_batches), 6)) as ex:
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
                    print(f"  [OK] LLM 新闻关联分析 [{_bid + 1}/{total_batches_proc}] 批完成")
                else:
                    logger.warning("LLM 新闻关联分析（批 %d/%d）: 分析失败",
                                   _bid + 1, total_batches_proc)
                    print(f"  [!] LLM 新闻关联分析 [{_bid + 1}/{total_batches_proc}] 批失败")
    else:
        _record_per_module("news_correlation", _model_name_news_correlation, cached=True)

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
            "model": _model_name_news_correlation,
            "input_tokens": total_tokens_input,
            "output_tokens": total_tokens_output,
            "total_tokens": total_tokens_input + total_tokens_output,
        }
        _log_token_usage(
            llm_config.get("provider", "unknown"),
            {"input_tokens": total_tokens_input, "output_tokens": total_tokens_output},
            "财经新闻热点与持仓关联分析（批处理）",
            model_name=_model_name_news_correlation,
        )
        _record_per_module("news_correlation", _model_name_news_correlation, inp=total_tokens_input, out=total_tokens_output)

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
    """并行生成全球政经局势 + 智囊团深度复盘 + 持仓体检报告 + 穿透深度分析。

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

    # ── 每模块启用状态检查 ──
    enabled_global_macro = _is_llm_module_enabled(llm_config, "global_macro")
    enabled_expert_review = _is_llm_module_enabled(llm_config, "expert_review")
    enabled_health_check = _is_llm_module_enabled(llm_config, "health_check")
    enabled_penetration_deep = _is_llm_module_enabled(llm_config, "penetration_deep")

    # ── 预计算指纹 + 缓存键（仅对已启用的模块） ──
    fp_global_macro = _compute_fingerprint(
        a_indices, us_indices, total_mv, total_profit, categories,
    )
    fp_expert_review = _expert_review_fingerprint(
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

    ttl_global_macro = _get_cache_ttl_llm("global_macro")
    ttl_expert_review = _get_cache_ttl_llm("expert_review")
    ttl_health_check = _get_cache_ttl_llm("health_check")
    ttl_penetration_deep = _get_cache_ttl_llm("penetration_deep")

    force_flag = force
    can_cache_global_macro = not force_flag and llm_config.get("cache_enabled_global_macro", True)
    can_cache_expert_review = not force_flag and llm_config.get("cache_enabled_expert_review", True)
    can_cache_health_check = not force_flag and llm_config.get("cache_enabled_health_check", True)
    can_cache_penetration_deep = not force_flag and llm_config.get("cache_enabled_penetration_deep", True)

    # ── 预检缓存（仅当缓存开启且非强制模式）──
    def _precheck(cache_key, cache_ttl, can_cache, thinking_key):
        import src.python.llm_client as _lm_pre  # noqa: F811
        if not can_cache:
            return (None, False)
        cached = _lm_pre.cache_get(cache_key, cache_ttl)
        if not cached:
            return (None, False)
        clean = _strip_token_line(cached)
        model = _extract_model_from_cached(cached)
        hint = _CACHE_LINE_MODEL_TPL.format(model=model) if model else _CACHE_LINE_HTML
        if llm_config.get(thinking_key, False):
            hint = hint.rstrip().replace("</p>", " | Extended Thinking</p>", 1)
        return (clean + hint, True)

    # ── 预检缓存（仅对已启用且缓存可用的模块）──
    if enabled_global_macro:
        global_macro_result, global_macro_cached_flag = _precheck(
            key_global_macro, ttl_global_macro, can_cache_global_macro, "thinking_enabled_global_macro",
        )
    else:
        logger.info("全球政经局势 LLM 分析已禁用（enabled_llm.global_macro = false）")
        global_macro_result, global_macro_cached_flag = None, False

    if enabled_expert_review:
        expert_review_result, expert_review_cached_flag = _precheck(
            key_expert_review, ttl_expert_review, can_cache_expert_review, "thinking_enabled_expert_review",
        )
    else:
        logger.info("智囊团深度复盘 LLM 分析已禁用（enabled_llm.expert_review = false）")
        expert_review_result, expert_review_cached_flag = None, False

    if enabled_health_check:
        health_check_result, health_check_cached_flag = _precheck(
            key_health_check, ttl_health_check, can_cache_health_check, "thinking_enabled_health_check",
        )
    else:
        logger.info("持仓体检报告 LLM 分析已禁用（enabled_llm.health_check = false）")
        health_check_result, health_check_cached_flag = None, False

    if enabled_penetration_deep:
        penetration_deep_result, penetration_deep_cached_flag = _precheck(
            key_penetration_deep, ttl_penetration_deep, can_cache_penetration_deep, "thinking_enabled_penetration_deep",
        )
    else:
        logger.info("穿透深度分析 LLM 分析已禁用（enabled_llm.penetration_deep = false）")
        penetration_deep_result, penetration_deep_cached_flag = None, False

    # ── 仅对缓存未命中的模块提交线程池任务 ──
    needs_global_macro = global_macro_result is None and enabled_global_macro
    needs_expert_review = expert_review_result is None and enabled_expert_review
    needs_health_check = health_check_result is None and enabled_health_check
    needs_penetration_deep = penetration_deep_result is None and enabled_penetration_deep

    if needs_global_macro or needs_expert_review or needs_health_check or needs_penetration_deep:
        import src.python.llm_client as _lm_pool  # noqa: F811
        with _lm_pool.ThreadPoolExecutor(max_workers=4) as executor:
            _futures: dict[Any, str] = {}

            if needs_global_macro:
                def _run_global_macro() -> tuple[Optional[str], bool]:
                    import src.python.llm_client as _lm_run  # noqa: F811
                    logger.info("正在生成：全球政经局势分析...")
                    c = _lm_run.httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return _lm_run.generate_global_macro(
                            a_indices, us_indices, total_mv, total_profit, categories,
                            sector_flow=sector_flow, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_global_macro)] = "global_macro"

            if needs_expert_review:
                def _run_expert_review() -> tuple[Optional[str], bool]:
                    import src.python.llm_client as _lm_run  # noqa: F811
                    logger.info("正在生成：智囊团深度复盘（耗时较长，请耐心等待）...")
                    c = _lm_run.httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return _lm_run.generate_expert_review(
                            total_mv, total_cost, total_profit, total_today_profit,
                            holdings_count, categories, penetrated_assets,
                            holdings_details=holdings_details, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_expert_review)] = "expert_review"

            if needs_health_check:
                def _run_health_check() -> tuple[Optional[str], bool]:
                    import src.python.llm_client as _lm_run  # noqa: F811
                    logger.info("正在生成：持仓体检报告（耗时较长，请耐心等待）...")
                    c = _lm_run.httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return _lm_run.generate_health_check(
                            total_mv, total_cost, total_profit, total_today_profit,
                            holdings_count, categories, penetrated_assets,
                            holdings_details=holdings_details, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_health_check)] = "health_check"

            if needs_penetration_deep:
                def _run_penetration_deep() -> tuple[Optional[str], bool]:
                    import src.python.llm_client as _lm_run  # noqa: F811
                    logger.info("正在生成：穿透深度分析...")
                    c = _lm_run.httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return _lm_run.generate_penetration_deep_analysis(
                            total_mv, total_cost, total_profit, total_today_profit,
                            holdings_count, categories, penetrated_assets,
                            holdings_details=holdings_details, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_penetration_deep)] = "penetration_deep"

            _label_map: dict[str, str] = {
                "global_macro": "全球政经局势", "expert_review": "智囊团深度复盘",
                "health_check": "持仓体检报告", "penetration_deep": "穿透深度分析",
            }

            for future in as_completed(_futures):
                try:
                    result, from_cache = future.result()
                    key = _futures[future]
                    if key == "global_macro":
                        global_macro_result, global_macro_cached_flag = result, from_cache
                    elif key == "expert_review":
                        expert_review_result, expert_review_cached_flag = result, from_cache
                    elif key == "health_check":
                        health_check_result, health_check_cached_flag = result, from_cache
                    elif key == "penetration_deep":
                        penetration_deep_result, penetration_deep_cached_flag = result, from_cache
                    logger.info("%s生成完成" if result else "%s生成失败（跳过）", _label_map.get(key, key))
                except Exception:
                    logger.warning("LLM 生成线程异常", exc_info=True)

    logger.info("LLM 生成完成: 全球政经局势=%s, 智囊团深度复盘=%s, 持仓体检报告=%s, 穿透深度分析=%s",
                "OK" if global_macro_result else "跳过",
                "OK" if expert_review_result else "跳过",
                "OK" if health_check_result else "跳过",
                "OK" if penetration_deep_result else "跳过")
    return (global_macro_result, expert_review_result, health_check_result, penetration_deep_result,
            global_macro_cached_flag, expert_review_cached_flag, health_check_cached_flag, penetration_deep_cached_flag)
