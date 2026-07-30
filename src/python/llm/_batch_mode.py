"""LLM 批量处理模块 — 批量 LLM 调用的缓存检查、执行与合并。

提取自 ``llm/skeleton.py``，管理批量模式下的缓存预检、并行调用和结果合并。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.http_client import make_http_client
from src.python.llm.api import call_llm
from src.python.llm.api_base import LLM_TIMEOUT, TRUNCATION_MARKER
from src.python.llm.fingerprint import get_cache_ttl_llm

logger = logging.getLogger("invest")

# 批量调用参数
_BATCH_CHUNK_SIZE = 10  # 每批最大条目数
_BATCH_MAX_WORKERS = 6  # 批量调用最大并行度


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
            cached = cache_get(ck, get_cache_ttl_llm(module_key))
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
    from src.python.llm.skeleton import _MN, _handle_truncation

    logger.info(
        "%s [%d/%d] 批处理中 (%d 条)...",
        _MN(module_key),
        batch_id + 1,
        total_batches,
        len(batch_indices),
    )
    batch_client = make_http_client(timeout=LLM_TIMEOUT)
    total_in = 0
    total_out = 0
    try:
        batch_items = [items[i] for i in batch_indices]
        user_prompt = batch_prompt_fn(batch_items, context_fp)
        result, usage, _ = call_llm(
            system_prompt,
            user_prompt,
            llm_config,
            timeout=timeout,
            http_client=batch_client,
            max_tokens=max_tokens,
            config_field=f"max_tokens_{module_key}",
            temperature=temperature,
            model=model,
        )
        if result and TRUNCATION_MARKER in result:
            result, usage = _handle_truncation(
                result,
                usage,
                max_tokens,
                system_prompt,
                user_prompt,
                llm_config,
                timeout,
                batch_client,
                f"max_tokens_{module_key}",
                temperature,
                model,
            )

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
            logger.info("%s [%d/%d] 批完成", _MN(module_key), batch_id + 1, total_batches)
        else:
            logger.warning("%s（批 %d/%d）: 分析失败", _MN(module_key), batch_id + 1, total_batches)
    finally:
        batch_client.close()
    return total_in, total_out


def run_batch_mode(
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
    from src.python.llm.skeleton import _MN

    cache_enabled = llm_config.get(f"cache_enabled_{module_key}", True)
    max_tokens = llm_config.get(f"max_tokens_{module_key}") or max_tokens_default
    _timeout = llm_config.get(f"timeout_{module_key}", timeout_default)
    _temp = llm_config.get(f"temperature_{module_key}")
    _model = llm_config.get(f"model_{module_key}")
    system_prompt = llm_config.get(f"system_prompt_{module_key}") or system_prompt_default

    items, context_fp = batch_preparer()
    results_map, item_cache_keys, uncached_indices, cached_count, all_cached = _check_batch_caches(
        items,
        per_item_cache_fn,
        cache_enabled,
        force,
        module_key,
        context_fp,
    )

    total_in = 0
    total_out = 0

    if uncached_indices and batch_prompt_fn and response_parser:
        batches = [
            uncached_indices[i : i + _BATCH_CHUNK_SIZE] for i in range(0, len(uncached_indices), _BATCH_CHUNK_SIZE)
        ]
        logger.info("正在调用 %s（%d 批未缓存，每批最多 %d 条）...", _MN(module_key), len(batches), _BATCH_CHUNK_SIZE)

        with ThreadPoolExecutor(max_workers=min(3, len(batches), _BATCH_MAX_WORKERS)) as ex:
            _fut_map = {
                ex.submit(
                    _execute_and_merge_batch,
                    i,
                    indices,
                    items,
                    context_fp,
                    system_prompt,
                    llm_config,
                    module_key,
                    max_tokens,
                    _timeout,
                    _temp,
                    _model,
                    batch_prompt_fn,
                    response_parser,
                    results_map,
                    item_cache_keys,
                    per_item_cache_fn,
                    len(batches),
                ): i
                for i, indices in enumerate(batches)
            }
            for future in as_completed(_fut_map):
                try:
                    inp, out = future.result()
                    total_in += inp
                    total_out += out
                except Exception as e:  # noqa: PERF203
                    logger.warning("批处理异常: %s", e)

    return (results_map, all_cached, {"input": total_in, "output": total_out, "model": _model}, cached_count)
