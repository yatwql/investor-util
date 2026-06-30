"""LLM 骨架模块 — 共享的生成骨架与批量处理逻辑。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from src.python.cache import get as cache_get, set as cache_set  # noqa: F401
from src.python.config import get_llm_config
from src.python.llm.api import (
    _AUTO_INCREASE_FACTOR,
    _call_llm,
    _CACHE_LINE_HTML,
    _CACHE_LINE_MODEL_TPL,
    _LLM_TIMEOUT,
    _TRUNCATION_MARKER,
    _extract_model_from_cached,
    _strip_token_line,
)
from src.python.llm.fingerprint import _get_cache_ttl_llm
from src.python.llm.markdown import _markdown_to_html
from src.python.llm.pricing import _estimate_cost
from src.python.llm.session import _record_per_module
from src.python.llm.prompts import (
    _CACHE_PREFIX_LLM,
    _LLM_MODULE_FAILURE,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_API_ERROR,
    FAIL_REASON_DISABLED,
)

from src.python.registry import get_llm_module_name

_MN = get_llm_module_name

logger = logging.getLogger("invest")

__all__ = [
    "_is_llm_module_enabled",
    "_generate_llm_content",
    "_generate_llm_module",
    "_run_batch_mode",
]


def _is_llm_module_enabled(llm_config: dict | None, module_suffix: str) -> bool:
    """检查 LLM 模块是否已启用。

    读取 enabled_llm 嵌套字典，模块默认启用。

    Args:
        llm_config: LLM 配置字典
        module_suffix: 模块后缀名（global_macro / expert_review / health_check /
                       penetration_deep / news_correlation）

    Returns:
        模块是否启用了 LLM 生成
    """
    if llm_config is None:
        return False
    enabled_map = llm_config.get("enabled_llm") or {}
    return bool(enabled_map.get(module_suffix, True))


def _handle_cache_hit(
    cached: str,
    cache_key: str,
    module_key: str,
    model: str | None,
    llm_config: dict,
    thinking_enabled: bool,
) -> str:
    """处理 LLM 缓存命中：格式化缓存 HTML 并记录模块用量。

    Returns:
        带缓存标记的 HTML 字符串
    """
    logger.info("LLM 缓存命中: %s", cache_key)
    cached_clean = _strip_token_line(cached)
    _orig_model = _extract_model_from_cached(cached)
    if _orig_model:
        _hint = _CACHE_LINE_MODEL_TPL.format(model=_orig_model)
    else:
        _hint = _CACHE_LINE_HTML
    if thinking_enabled:
        _hint = _hint.rstrip().replace("</p>", " | Extended Thinking</p>", 1)
    cached_clean += _hint
    if module_key:
        _model_for_record = _orig_model or model or llm_config.get("model", "") or "缓存命中"
        _endpoint_for_record = llm_config.get("endpoint", "") or ""
        _record_per_module(module_key, _model_for_record, cached=True,
                           thinking=thinking_enabled, endpoint=_endpoint_for_record)
    return cached_clean


def _finalize_and_cache(
    result: str,
    usage: dict | None,
    cache_key: str,
    module_key: str,
    model: str | None,
    llm_config: dict,
    thinking_enabled: bool,
) -> tuple[str, bool]:
    """处理 LLM 返回结果：Markdown→HTML → 拼接页脚 → 缓存 → 记录。

    Returns:
        (HTML 文本, False)
    """
    html = _markdown_to_html(result)
    if not html.strip():
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
            _cost_val = 0.0
            if _cost != "-":
                try:
                    _cost_val = float(_cost.lstrip("$¥€£"))
                except ValueError:
                    logger.warning("LLM 费用字符串解析失败: %s", _cost)
            _endpoint_for_record = llm_config.get("endpoint", "") or ""
            _cache_hit = usage.get("cache_read_input_tokens", 0)
            _record_per_module(module_key, _model_name, inp=_inp, out=_out,
                               thinking=thinking_enabled, cost=_cost_val,
                               endpoint=_endpoint_for_record, cache_hit_tokens=_cache_hit)

    cache_set(cache_key, html)
    logger.info("LLM 内容生成完成: %s", cache_key)
    return (html, False)


def _handle_truncation(
    result: str | None,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
    llm_config: dict,
    timeout: float,
    http_client: httpx.Client | None,
    config_field: str,
    temperature: float | None,
    model: str | None,
) -> tuple[str | None, dict | None]:
    """检测截断并自动增大 max_tokens 重试。

    Returns:
        (result, usage) — 重试后的结果，或原结果（未截断时）
    """
    if not result or _TRUNCATION_MARKER not in result:
        return result, None

    new_max = int(max_tokens * _AUTO_INCREASE_FACTOR)
    logger.warning("输出被截断（max_tokens=%d），自动以 %d 重新生成...", max_tokens, new_max)
    print(f"  [..] 输出被截断，自动增大 max_tokens ({max_tokens} → {new_max}) 重新生成...")
    result2, usage2 = _call_llm(
        system_prompt, user_prompt, llm_config,
        timeout=timeout, http_client=http_client,
        max_tokens=new_max, config_field=config_field,
        temperature=temperature, model=model,
    )
    if result2:
        if _TRUNCATION_MARKER in result2:
            logger.warning("增大 max_tokens=%d 后仍被截断，请手动增大配置", new_max)
        return result2, usage2
    return result, None


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
) -> tuple[str | None, bool]:
    """通用 LLM 内容生成骨架，带缓存检查与写入。"""
    if module_key:
        _LLM_MODULE_FAILURE.pop(module_key, None)

    # ── 缓存检查 ──
    if cache_enabled and not force:
        cached = cache_get(cache_key, cache_ttl)
        if cached:
            return (_handle_cache_hit(cached, cache_key, module_key, model, llm_config, thinking_enabled), True)

    # ── LLM 调用 → 截断重试 → 处理结果 ──
    result, usage = _call_llm(system_prompt, user_prompt, llm_config,
                              timeout=timeout, http_client=http_client,
                              max_tokens=max_tokens, config_field=config_field,
                              temperature=temperature, model=model)
    result, usage = _handle_truncation(result, max_tokens, system_prompt, user_prompt,
                                       llm_config, timeout, http_client, config_field,
                                       temperature, model)

    if result:
        return _finalize_and_cache(result, usage, cache_key, module_key, model, llm_config, thinking_enabled)

    logger.warning("LLM 内容生成失败: %s", cache_key)
    if module_key:
        _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_API_ERROR
    return (None, False)


def _generate_llm_module(
    llm_config: dict | None,
    module_key: str,
    *,
    force: bool = False,
    http_client: httpx.Client | None = None,
    fingerprint_fn: Any = None,
    system_prompt_default: str = "",
    prompt_builder: Any = None,
    max_tokens_default: int = 4096,
    timeout_default: float = 120.0,
    output_brief_limit: int = 300,
    # ── 批量模式 hooks（用于 news_correlation 类模块） ──
    batch_preparer: Any = None,       # fn() → (items, context) or None（None=标准模式）
    per_item_cache_fn: Any = None,    # fn(index, item, context_fp) → cache_key or None
    batch_prompt_fn: Any = None,      # fn(batch_items, context) → user_prompt 字符串
    response_parser: Any = None,      # fn(batch_items, llm_response) → [parsed 列表]
) -> Any:
    """通用 LLM 模块生成骨架。

    标准模式（无 batch_preparer）：生成单篇分析内容。
    批量模式（有 batch_preparer）：逐条缓存、分批并行、JSON 解析。

    标准模式返回 (HTML 或 None, 是否来自缓存)。
    批量模式返回 (results_dict, all_cached, token_usage, cached_count)。
    """
    if llm_config is None:
        llm_config = get_llm_config()
    if llm_config is None:
        logger.info("LLM 未配置，%s 使用占位文本", _MN(module_key))
        _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_NOT_CONFIGURED
        if batch_preparer:
            return ({}, False, {}, 0)
        return (None, False)

    if not _is_llm_module_enabled(llm_config, module_key):
        logger.info("%s LLM 分析已禁用（enabled_llm.%s = false）", _MN(module_key), module_key)
        _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_DISABLED
        if batch_preparer:
            return ({}, False, {}, 0)
        return (None, False)

    # ── 批量模式分支 ─────────────────────────────────────
    if batch_preparer is not None:
        return _run_batch_mode(
            llm_config, module_key, force=force,
            batch_preparer=batch_preparer,
            per_item_cache_fn=per_item_cache_fn,
            batch_prompt_fn=batch_prompt_fn,
            response_parser=response_parser,
            system_prompt_default=system_prompt_default,
            max_tokens_default=max_tokens_default,
            timeout_default=timeout_default,
        )

    # ── 标准模式（原有的 4 个分析模块） ──────────────────
    cache_enabled = llm_config.get(f"cache_enabled_{module_key}", True)
    fingerprint = fingerprint_fn() if fingerprint_fn else ""
    cache_key = _CACHE_PREFIX_LLM + f"{module_key}_{fingerprint}"

    system_prompt = llm_config.get(f"system_prompt_{module_key}") or system_prompt_default
    if llm_config.get(f"output_brief_{module_key}", False):
        system_prompt += f"\n（精简模式，输出 {output_brief_limit} 字以内。）"

    user_prompt = prompt_builder() if prompt_builder else ""

    return _generate_llm_content(
        llm_config, cache_key, _get_cache_ttl_llm(module_key),
        system_prompt, user_prompt, cache_enabled, force,
        max_tokens=llm_config.get(f"max_tokens_{module_key}") or llm_config.get("max_tokens", max_tokens_default),
        timeout=llm_config.get(f"timeout_{module_key}", timeout_default),
        temperature=llm_config.get(f"temperature_{module_key}"),
        model=llm_config.get(f"model_{module_key}"),
        config_field=f"max_tokens_{module_key}",
        http_client=http_client,
        thinking_enabled=llm_config.get(f"thinking_enabled_{module_key}", False),
        module_key=module_key,
    )


def _check_batch_caches(
    items: list,
    per_item_cache_fn: Any,
    cache_enabled: bool,
    force: bool,
    module_key: str,
    context_fp: str,
) -> tuple[dict[int, Any], dict[int, str], list[int], int, bool]:
    """逐条检查批量缓存，返回 (results_map, item_cache_keys, uncached_indices, cached_count, all_cached)。"""
    results_map: dict[int, Any] = {}
    item_cache_keys: dict[int, str] = {}
    uncached_indices: list[int] = []
    cached_count = 0

    for idx, item in enumerate(items):
        if per_item_cache_fn and cache_enabled and not force:
            ck = per_item_cache_fn(idx, item, context_fp)
            item_cache_keys[idx] = ck
            cached = cache_get(ck, _get_cache_ttl_llm(module_key))
            if cached is not None:
                results_map[idx] = cached
                cached_count += 1
                continue
        uncached_indices.append(idx)

    return results_map, item_cache_keys, uncached_indices, cached_count, len(uncached_indices) == 0


def _execute_and_merge_batch(
    batch_id: int,
    batch_indices: list[int],
    items: list,
    context_fp: str,
    system_prompt: str,
    llm_config: dict,
    module_key: str,
    max_tokens: int,
    timeout: float,
    temperature: float | None,
    model: str | None,
    batch_prompt_fn: Any,
    response_parser: Any,
    results_map: dict[int, Any],
    item_cache_keys: dict[int, str],
    per_item_cache_fn: Any,
    total_batches: int,
) -> tuple[int, int]:
    """执行单批 LLM 调用、解析结果并写入缓存。

    Returns:
        (input_tokens, output_tokens) 本批的 token 用量
    """
    print(f"  [..] {_MN(module_key)} [{batch_id + 1}/{total_batches}] 批处理中 ({len(batch_indices)} 条)...")
    batch_client = httpx.Client(timeout=_LLM_TIMEOUT)
    total_in = 0
    total_out = 0
    try:
        batch_items = [items[i] for i in batch_indices]
        user_prompt = batch_prompt_fn(batch_items, context_fp)
        result, usage = _call_llm(
            system_prompt, user_prompt, llm_config,
            timeout=timeout, http_client=batch_client,
            max_tokens=max_tokens,
            config_field=f"max_tokens_{module_key}",
            temperature=temperature, model=model,
        )
        if result and _TRUNCATION_MARKER in result:
            new_max = int(max_tokens * _AUTO_INCREASE_FACTOR)
            logger.warning("%s 输出被截断，自动以 %d 重新生成 [批 %d/%d]",
                           _MN(module_key), new_max, batch_id + 1, total_batches)
            result2, usage2 = _call_llm(
                system_prompt, user_prompt, llm_config,
                timeout=timeout, http_client=batch_client,
                max_tokens=new_max, config_field=f"max_tokens_{module_key}",
                temperature=temperature, model=model,
            )
            if result2:
                result, usage = result2, usage2

        if result:
            parsed_list = response_parser(batch_items, result)
            for local_idx, parsed in enumerate(parsed_list):
                global_idx = batch_indices[local_idx]
                results_map[global_idx] = parsed
                if per_item_cache_fn and item_cache_keys.get(global_idx):
                    cache_set(item_cache_keys[global_idx], parsed)
            if usage:
                total_in += usage.get("input_tokens", usage.get("prompt_tokens", 0))
                total_out += usage.get("output_tokens", usage.get("completion_tokens", 0))
            print(f"  [OK] {_MN(module_key)} [{batch_id + 1}/{total_batches}] 批完成")
        else:
            logger.warning("%s（批 %d/%d）: 分析失败",
                           _MN(module_key), batch_id + 1, total_batches)
    finally:
        batch_client.close()
    return total_in, total_out


def _run_batch_mode(
    llm_config: dict,
    module_key: str,
    *,
    force: bool = False,
    batch_preparer: Any,
    per_item_cache_fn: Any,
    batch_prompt_fn: Any,
    response_parser: Any,
    system_prompt_default: str = "",
    max_tokens_default: int = 4096,
    timeout_default: float = 120.0,
) -> tuple[dict, bool, dict, int]:
    """批量模式骨架：逐条缓存检查 → 分批并行 → JSON 解析合并。

    Returns:
        (idx → parsed 结果映射, 是否全缓存, token 用量字典, 缓存命中条数)
    """
    cache_enabled = llm_config.get(f"cache_enabled_{module_key}", True)
    max_tokens = llm_config.get(f"max_tokens_{module_key}") or max_tokens_default
    _timeout = llm_config.get(f"timeout_{module_key}", timeout_default)
    _temp = llm_config.get(f"temperature_{module_key}")
    _model = llm_config.get(f"model_{module_key}")
    system_prompt = llm_config.get(f"system_prompt_{module_key}") or system_prompt_default

    items, context_fp = batch_preparer()
    results_map, item_cache_keys, uncached_indices, cached_count, all_cached = _check_batch_caches(
        items, per_item_cache_fn, cache_enabled, force, module_key, context_fp,
    )

    total_in = 0
    total_out = 0

    if uncached_indices and batch_prompt_fn and response_parser:
        BATCH_SIZE = 10
        batches = [uncached_indices[i:i + BATCH_SIZE]
                   for i in range(0, len(uncached_indices), BATCH_SIZE)]
        logger.info("正在调用 %s（%d 批未缓存，每批最多 %d 条）...",
                    _MN(module_key), len(batches), BATCH_SIZE)

        with ThreadPoolExecutor(max_workers=min(3, len(batches), 6)) as ex:
            _fut_map = {
                ex.submit(_execute_and_merge_batch, i, indices, items, context_fp,
                          system_prompt, llm_config, module_key, max_tokens,
                          _timeout, _temp, _model, batch_prompt_fn, response_parser,
                          results_map, item_cache_keys, per_item_cache_fn, len(batches)): i
                for i, indices in enumerate(batches)
            }
            for future in as_completed(_fut_map):
                try:
                    inp, out = future.result()
                    total_in += inp
                    total_out += out
                except Exception as e:
                    logger.warning("批处理异常: %s", e)

    return (results_map, all_cached, {"input": total_in, "output": total_out, "model": _model}, cached_count)
