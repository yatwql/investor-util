"""LLM 生成编排模块 — LLM 入口函数与批量编排。"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from src.python.cache import get as cache_get
from src.python.config import get_llm_config
from src.python.llm.api import (
    _CACHE_LINE_HTML,
    _CACHE_LINE_MODEL_TPL,
    _LLM_TIMEOUT,
    _extract_model_from_cached,
    _log_token_usage,
    _strip_token_line,
)
from src.python.llm.fingerprint import (
    _build_llm_fingerprint,
    _compute_fingerprint,
    _get_cache_ttl_llm,
)
from src.python.llm.prompts import (
    _CACHE_PREFIX_LLM,
    _LLM_MODULE_FAILURE,
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
from src.python.llm.session import _record_per_module
from src.python.llm.skeleton import (
    _is_llm_module_enabled,
    _generate_llm_content,
    _generate_llm_module,
)
from src.python.registry import get_llm_module_name, get_llm_module_names

_MN = get_llm_module_name

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
) -> tuple[str | None, bool]:
    """生成全球政经局势。"""
    def _fingerprint():
        return _compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)
    def _prompt():
        return _build_global_macro_prompt(a_indices, us_indices, total_mv, total_profit, categories, sector_flow)
    return _generate_llm_module(
        llm_config, "global_macro",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_GLOBAL_MACRO,
        prompt_builder=_prompt,
        max_tokens_default=800,
        timeout_default=60.0,
        output_brief_limit=200,
    )


def generate_expert_review(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, bool]:
    """生成智囊团深度复盘。"""
    def _fingerprint():
        return _build_llm_fingerprint(
            total_mv=total_mv, total_cost=total_cost,
            total_profit=total_profit, total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
        )
    def _prompt():
        return _build_expert_review_prompt(
            total_mv, total_cost, total_profit, total_today_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details,
        )
    return _generate_llm_module(
        llm_config, "expert_review",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_EXPERT_REVIEW,
        prompt_builder=_prompt,
        max_tokens_default=8192,
        timeout_default=120.0,
        output_brief_limit=300,
    )


def generate_health_check(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, bool]:
    """生成持仓体检报告。"""
    def _fingerprint():
        return _build_llm_fingerprint(
            total_mv=total_mv, total_cost=total_cost,
            total_profit=total_profit, total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
        )
    def _prompt():
        return _build_health_check_prompt(
            total_mv, total_cost, total_profit, total_today_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details,
        )
    return _generate_llm_module(
        llm_config, "health_check",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_HEALTH_CHECK,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=120.0,
        output_brief_limit=300,
    )


def generate_penetration_deep_analysis(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, bool]:
    """生成穿透深度分析。"""
    def _fingerprint():
        return _build_llm_fingerprint(
            total_mv=total_mv, total_cost=total_cost,
            total_profit=total_profit, total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
            full_penetration=True,
        )
    def _prompt():
        return _build_penetration_deep_prompt(
            total_mv, total_cost, total_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details,
        )
    return _generate_llm_module(
        llm_config, "penetration_deep",
        force=force, http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_PENETRATION_DEEP,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=90.0,
        output_brief_limit=300,
    )


# ═══════════════════════════════════════════════════════════
#  财经新闻热点与持仓关联分析（LLM 增强）
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
        logger.warning("%s JSON 解析失败: %s", _MN("news_correlation"), e)
        return [("低", "中性", "")] * batch_size

    if not isinstance(analyses, list):
        logger.warning("%s 返回格式异常: 非数组", _MN("news_correlation"))
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

    通过 _generate_llm_module 的批量模式 hooks 实现：
    逐条缓存 → 分批并行 → JSON 解析 → 合并回 news_data。

    Args:
        news_data: 关键词匹配后的新闻列表（由 build_news_data 返回）
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产（可选）
        industry_data: 行业/概念数据 {code: {industry, concepts, ...}}（可选）
        force: 跳过缓存强制重新生成
        http_client: 可选的 httpx.Client 实例
        llm_config: 可选的 LLM 配置字典

    Returns:
        (富化后的新闻列表, 是否来自缓存, token 用量字典)
        token 用量含 {"input_tokens": N, "output_tokens": N, "total_tokens": N}
        LLM 不可用或失败时返回 (news_data, False, {})
    """
    if not news_data:
        return (news_data, False, {})

    # 按关键词匹配数排序，取前 30 条送给 LLM
    _sorted_with_idx = sorted(
        enumerate(news_data),
        key=lambda x: len(x[1].get("matched_keywords", [])),
        reverse=True,
    )
    top_news = [item for _, item in _sorted_with_idx[:30]]
    top_to_original = {ti: orig_i for ti, (orig_i, _) in enumerate(_sorted_with_idx[:30])}

    # ── 闭包捕获变量（供 hook 使用） ─────────────────────
    _model = (llm_config.get("model_news_correlation") or
              (llm_config or {}).get("model", "") or "未指定") if llm_config else "未指定"

    def _batch_preparer():
        """返回 (top_news 列表, 持仓指纹上下文)。"""
        holdings_summary = [{"name": h.name, "code": h.code} for h in holdings[:20]]
        holdings_fp = _compute_fingerprint(holdings_summary, penetrated_assets)
        return top_news, holdings_fp

    def _per_item_cache(idx: int, item: dict, context_fp: str) -> str:
        title_prefix = (item.get("title", "") or "")[:80]
        article_fp = _compute_fingerprint({"title": title_prefix, "holdings_fp": context_fp})
        return _CACHE_PREFIX_LLM + f"news_item_{article_fp}"

    def _batch_prompt(batch_items: list[dict], context_fp: str) -> str:
        holdings_text = _build_holdings_summary(holdings, penetrated_assets, industry_data)
        news_text = _build_news_correlation_summary(batch_items)
        return (
            f"【持仓信息】\n{holdings_text}\n\n"
            f"【新闻列表】\n{news_text}\n\n"
            f"请分析以上每条新闻与持仓的关联性，输出JSON数组。"
        )

    # ── 委托 _generate_llm_module 骨架 ─────────────────
    results_map, all_cached, batch_usage, cached_count = _generate_llm_module(
        llm_config, "news_correlation",
        force=force,
        system_prompt_default=_SYSTEM_NEWS_CORRELATION,
        max_tokens_default=2000,
        timeout_default=60.0,
        batch_preparer=_batch_preparer,
        per_item_cache_fn=_per_item_cache,
        batch_prompt_fn=_batch_prompt,
        response_parser=_apply_llm_news_correlation,
    )

    # ── 映射 results_map（top_news idx → 原始 news_data idx） ───
    analysis_by_orig_idx: dict[int, tuple] = {}
    for top_idx, parsed in results_map.items():
        orig_i = top_to_original.get(top_idx)
        if orig_i is not None:
            analysis_by_orig_idx[orig_i] = parsed

    # ── 合并回 news_data ──────────────────────────────
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

    # ── Token 用量 ─────────────────────────────────────
    total_in = batch_usage.get("input", 0)
    total_out = batch_usage.get("output", 0)
    token_usage: dict = {}
    if total_in > 0 or total_out > 0:
        token_usage = {
            "model": _model,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "total_tokens": total_in + total_out,
        }
        if llm_config:
            _log_token_usage(
                llm_config.get("provider", "unknown"),
                {"input_tokens": total_in, "output_tokens": total_out},
                f"{_MN('news_correlation')}（批处理）",
                model_name=_model,
            )
            _record_per_module("news_correlation", _model, inp=total_in, out=total_out)

    _fresh_count = len(top_news) - cached_count
    logger.info(
        "%s完成: %d 条 → %d 条含 LLM 分析（缓存 %d 条 + 新处理 %d 条）",
        _MN("news_correlation"), len(news_data), analysis_count, cached_count, _fresh_count,
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
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    sector_flow: list[dict] | None = None,
    force: bool = False,
) -> tuple[str | None, str | None, str | None, str | None, bool, bool, bool, bool]:
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
    fp_expert_review = _build_llm_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
    )
    fp_health_check = _build_llm_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
    )
    fp_penetration_deep = _build_llm_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
        full_penetration=True,
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

    # ── 预检缓存（仅对已启用且缓存可用的模块）──
    if enabled_global_macro:
        global_macro_result, global_macro_cached_flag = _precheck(
            key_global_macro, ttl_global_macro, can_cache_global_macro, "thinking_enabled_global_macro",
        )
    else:
        logger.info("%s LLM 分析已禁用（enabled_llm.global_macro = false）", _MN("global_macro"))
        _LLM_MODULE_FAILURE["global_macro"] = FAIL_REASON_DISABLED
        global_macro_result, global_macro_cached_flag = None, False

    if enabled_expert_review:
        expert_review_result, expert_review_cached_flag = _precheck(
            key_expert_review, ttl_expert_review, can_cache_expert_review, "thinking_enabled_expert_review",
        )
    else:
        logger.info("%s LLM 分析已禁用（enabled_llm.expert_review = false）", _MN("expert_review"))
        _LLM_MODULE_FAILURE["expert_review"] = FAIL_REASON_DISABLED
        expert_review_result, expert_review_cached_flag = None, False

    if enabled_health_check:
        health_check_result, health_check_cached_flag = _precheck(
            key_health_check, ttl_health_check, can_cache_health_check, "thinking_enabled_health_check",
        )
    else:
        logger.info("%s LLM 分析已禁用（enabled_llm.health_check = false）", _MN("health_check"))
        _LLM_MODULE_FAILURE["health_check"] = FAIL_REASON_DISABLED
        health_check_result, health_check_cached_flag = None, False

    if enabled_penetration_deep:
        penetration_deep_result, penetration_deep_cached_flag = _precheck(
            key_penetration_deep, ttl_penetration_deep, can_cache_penetration_deep, "thinking_enabled_penetration_deep",
        )
    else:
        logger.info("%s LLM 分析已禁用（enabled_llm.penetration_deep = false）", _MN("penetration_deep"))
        _LLM_MODULE_FAILURE["penetration_deep"] = FAIL_REASON_DISABLED
        penetration_deep_result, penetration_deep_cached_flag = None, False

    # ── 仅对缓存未命中的模块提交线程池任务 ──
    needs_global_macro = global_macro_result is None and enabled_global_macro
    needs_expert_review = expert_review_result is None and enabled_expert_review
    needs_health_check = health_check_result is None and enabled_health_check
    needs_penetration_deep = penetration_deep_result is None and enabled_penetration_deep

    if needs_global_macro or needs_expert_review or needs_health_check or needs_penetration_deep:
        with ThreadPoolExecutor(max_workers=4) as executor:
            _futures: dict[Future, str] = {}

            if needs_global_macro:
                def _run_global_macro() -> tuple[str | None, bool]:
                    logger.info("正在生成：%s...", _MN("global_macro"))
                    c = httpx.Client(timeout=_LLM_TIMEOUT)
                    try:
                        return generate_global_macro(
                            a_indices, us_indices, total_mv, total_profit, categories,
                            sector_flow=sector_flow, force=force_flag,
                            http_client=c, llm_config=llm_config,
                        )
                    finally:
                        c.close()
                _futures[executor.submit(_run_global_macro)] = "global_macro"

            if needs_expert_review:
                def _run_expert_review() -> tuple[str | None, bool]:
                    logger.info("正在生成：%s（耗时较长，请耐心等待）...", _MN("expert_review"))
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
                _futures[executor.submit(_run_expert_review)] = "expert_review"

            if needs_health_check:
                def _run_health_check() -> tuple[str | None, bool]:
                    logger.info("正在生成：%s（耗时较长，请耐心等待）...", _MN("health_check"))
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
                _futures[executor.submit(_run_health_check)] = "health_check"

            if needs_penetration_deep:
                def _run_penetration_deep() -> tuple[str | None, bool]:
                    logger.info("正在生成：%s...", _MN("penetration_deep"))
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
                _futures[executor.submit(_run_penetration_deep)] = "penetration_deep"

            _label_map: dict[str, str] = get_llm_module_names()

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

    logger.info("LLM 生成完成: %s=%s, %s=%s, %s=%s, %s=%s",
                _MN("global_macro"), "OK" if global_macro_result else "跳过",
                _MN("expert_review"), "OK" if expert_review_result else "跳过",
                _MN("health_check"), "OK" if health_check_result else "跳过",
                _MN("penetration_deep"), "OK" if penetration_deep_result else "跳过")
    return (global_macro_result, expert_review_result, health_check_result, penetration_deep_result,
            global_macro_cached_flag, expert_review_cached_flag, health_check_cached_flag, penetration_deep_cached_flag)
