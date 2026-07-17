"""LLM 新闻关联分析模块 — LLM 增强的新闻与持仓关联分析。

R-198 从 generators.py 拆分：包含 _apply_llm_news_correlation ~ enhance_news_correlation 全部 7 个函数。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from src.python.llm.api_base import (
    CACHE_LINE_HTML,
    LLM_TIMEOUT,
    _cache_line_model_tpl,
    _extract_model_from_cached,
    _log_token_usage,
)
from src.python.llm.fingerprint import compute_fingerprint
from src.python.llm.pricing import estimate_cost
from src.python.llm.prompts import (
    CACHE_PREFIX_LLM,
    LLM_MODULE_FAILURE,
    _SYSTEM_NEWS_CORRELATION,
    _build_holdings_summary,
    _build_news_correlation_summary,
)
from src.python.llm.session import record_per_module
from src.python.llm.skeleton import generate_llm_module
from src.python.registry import get_llm_module_name, get_llm_module_names

logger = logging.getLogger("invest")
_MN = get_llm_module_name


__all__ = [
    "_apply_llm_news_correlation",
    "_select_top_news",
    "_build_news_hooks",
    "_map_llm_results",
    "_merge_llm_analysis",
    "_finalize_news_token_usage",
    "enhance_news_correlation",
]


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


def _select_top_news(
    news_data: list[dict], top_n: int = 30,
) -> tuple[list[dict], dict[int, int]]:
    """按关键词匹配数排序，选取 TOP N 条送 LLM 分析。

    Returns:
        (top_news, top_to_original)
        top_to_original: top_news 索引 → news_data 索引的映射
    """
    sorted_with_idx = sorted(
        enumerate(news_data),
        key=lambda x: len(x[1].get("matched_keywords", [])),
        reverse=True,
    )
    top_news = [item for _, item in sorted_with_idx[:top_n]]
    top_to_original = {ti: orig_i for ti, (orig_i, _) in enumerate(sorted_with_idx[:top_n])}
    return top_news, top_to_original


def _build_news_hooks(
    top_news: list[dict], holdings: list, penetrated_assets: list | None,
    industry_data: dict[str, dict] | None, llm_config: dict | None,
) -> tuple[Callable, Callable, Callable, str]:
    """构建批量处理 hooks。

    Args:
        top_news: 选取的 TOP N 条新闻（供 _batch_preparer 返回）

    Returns:
        (batch_preparer, per_item_cache_fn, batch_prompt_fn, model_name)
    """
    _model = (llm_config.get("model_news_correlation") or
              (llm_config or {}).get("model", "") or "未指定") if llm_config else "未指定"

    def _batch_preparer():
        holdings_summary = [{"name": h.name, "code": h.code} for h in holdings[:20]]
        holdings_fp = compute_fingerprint(holdings_summary, penetrated_assets)
        return top_news, holdings_fp

    def _per_item_cache(_idx: int, item: dict, context_fp: str) -> str:
        title_prefix = (item.get("title", "") or "")[:80]
        article_fp = compute_fingerprint({"title": title_prefix, "holdings_fp": context_fp})
        return CACHE_PREFIX_LLM + f"news_item_{article_fp}"

    def _batch_prompt(batch_items: list[dict], _context_fp: str) -> str:
        holdings_text = _build_holdings_summary(holdings, penetrated_assets, industry_data)
        news_text = _build_news_correlation_summary(batch_items)
        return (
            f"【持仓信息】\n{holdings_text}\n\n"
            f"【新闻列表】\n{news_text}\n\n"
            f"请分析以上每条新闻与持仓的关联性，输出JSON数组。"
        )

    return _batch_preparer, _per_item_cache, _batch_prompt, _model


def _map_llm_results(
    results_map: dict[int, tuple], top_to_original: dict[int, int],
) -> dict[int, tuple]:
    """将 LLM results_map（top_news idx→parsed）映射到原始 news_data idx。"""
    analysis_by_orig_idx: dict[int, tuple] = {}
    for top_idx, parsed in results_map.items():
        orig_i = top_to_original.get(top_idx)
        if orig_i is not None:
            analysis_by_orig_idx[orig_i] = parsed
    return analysis_by_orig_idx


def _merge_llm_analysis(
    news_data: list[dict], analysis_by_orig_idx: dict[int, tuple],
) -> tuple[list[dict], int]:
    """将 LLM 分析结果合并回 news_data，返回 (enriched, analysis_count)。"""
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
    return enriched, analysis_count


def _finalize_news_token_usage(
    batch_usage: dict, llm_config: dict | None, _model: str,
    top_news: list, cached_count: int, news_data: list, analysis_count: int,
    all_cached: bool = False,
) -> dict:
    """计算 Token 用量并记录日志。返回 token_usage dict。"""
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
    # 无论是否有新用量，都记录 per_module（all_cached 时也需标记缓存状态）
    if llm_config:
        if total_in > 0 or total_out > 0:
            _log_token_usage(
                llm_config.get("provider", "unknown"),
                {"input_tokens": total_in, "output_tokens": total_out},
                f"{_MN('news_correlation')}（批处理）",
                model_name=_model,
            )
        _cost_val = 0.0
        _cost = estimate_cost(_model, total_in, total_out, cache_hit_input_tokens=0)
        if _cost != "-":
            try:
                _cost_val = float(_cost.lstrip("$¥€£"))
            except ValueError as e:
                logger.warning("[llm] 费用估值 JSON 解码失败: %s", e)
        _endpoint = llm_config.get("endpoint", "") or ""
        record_per_module(
            "news_correlation", _model, inp=total_in, out=total_out,
            cached=all_cached, cost=_cost_val, endpoint=_endpoint,
        )

    fresh_count = len(top_news) - cached_count
    logger.info(
        "%s完成: %d 条 → %d 条含 LLM 分析（缓存 %d 条 + 新处理 %d 条）",
        _MN("news_correlation"), len(news_data), analysis_count, cached_count, fresh_count,
    )
    return token_usage


def enhance_news_correlation(
    news_data: list[dict],
    holdings: list,
    penetrated_assets: list | None = None,
    industry_data: dict[str, dict] | None = None,
    force: bool = False,
    _http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
) -> tuple[list[dict], bool, dict]:
    """使用 LLM 增强新闻与持仓的关联分析。

    通过 generate_llm_module 的批量模式 hooks 实现：
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

    top_n = (llm_config or {}).get("news_correlation_top_n", 30)
    top_news, top_to_original = _select_top_news(news_data, top_n=top_n)
    batch_preparer, per_item_cache_fn, batch_prompt_fn, _model = _build_news_hooks(
        top_news, holdings, penetrated_assets, industry_data, llm_config,
    )

    results_map, all_cached, batch_usage, cached_count = generate_llm_module(
        llm_config, "news_correlation",
        force=force,
        system_prompt_default=_SYSTEM_NEWS_CORRELATION,
        max_tokens_default=2000,
        timeout_default=60.0,
        batch_preparer=batch_preparer,
        per_item_cache_fn=per_item_cache_fn,
        batch_prompt_fn=batch_prompt_fn,
        response_parser=_apply_llm_news_correlation,
    )

    analysis_by_orig_idx = _map_llm_results(results_map, top_to_original)
    enriched, analysis_count = _merge_llm_analysis(news_data, analysis_by_orig_idx)
    token_usage = _finalize_news_token_usage(
        batch_usage, llm_config, _model, top_news, cached_count, news_data, analysis_count,
        all_cached=all_cached,
    )

    return (enriched, all_cached, token_usage)
