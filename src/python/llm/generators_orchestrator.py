"""LLM 批量编排模块 — 缓存预检查、线程池分发与 LLM 全量生成。

R-198 从 generators.py 拆分：包含 _compute_module_cache_info、
_precheck_one_cache、_precheck_all_modules、_dispatch_llm_workers、
generate_all_llm 和 _LLM_CLIENT_SETTINGS。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from src.python.cache import get as cache_get
from src.python.config import get_llm_config
from src.python.llm.api_base import (
    _CACHE_LINE_HTML,
    _LLM_TIMEOUT,
    _cache_line_model_tpl,
    _extract_model_from_cached,
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
)
from src.python.llm.session import _record_per_module
from src.python.llm.skeleton import _is_llm_module_enabled
from src.python.llm.generators import (
    generate_expert_review,
    generate_global_macro,
    generate_health_check,
    generate_penetration_deep_analysis,
)
from src.python.registry import get_llm_module_name, get_llm_module_names

logger = logging.getLogger("invest")
_MN = get_llm_module_name


__all__ = [
    "_LLM_CLIENT_SETTINGS",
    "_compute_module_cache_info",
    "_precheck_one_cache",
    "_precheck_all_modules",
    "_dispatch_llm_workers",
    "generate_all_llm",
]


# ── HTTP 客户端配置 ──────────────────────────────────────────
# 各工作线程共享同一组连接参数，通过 HTTP/2 + keepalive 减少连接建立开销
_LLM_CLIENT_SETTINGS: dict[str, Any] = {
    "http2": True,                               # HTTP/2 多路复用
    "limits": httpx.Limits(
        max_connections=20,                      # 总连接池上限
        max_keepalive_connections=10,            # 空闲保持连接数
    ),
}


def _compute_module_cache_info(
    llm_config: dict, a_indices, us_indices,
    total_mv: float, total_cost: float, total_profit: float,
    total_today_profit: float, _holdings_count: int, categories: dict,
    penetrated_assets: list[dict] | None, holdings_details: list[dict] | None,
    force: bool,
) -> dict[str, dict]:
    """预计算各模块指纹/缓存键/TTL/可缓存性，返回数据结构。"""
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
        categories=categories, full_penetration=True,
    )

    force_flag = force
    info: dict[str, dict] = {
        "global_macro": {
            "key": _CACHE_PREFIX_LLM + f"global_macro_{fp_global_macro}",
            "ttl": _get_cache_ttl_llm("global_macro"),
            "can_cache": not force_flag and llm_config.get("cache_enabled_global_macro", True),
            "thinking_key": "thinking_enabled_global_macro",
        },
        "expert_review": {
            "key": _CACHE_PREFIX_LLM + f"expert_review_{fp_expert_review}",
            "ttl": _get_cache_ttl_llm("expert_review"),
            "can_cache": not force_flag and llm_config.get("cache_enabled_expert_review", True),
            "thinking_key": "thinking_enabled_expert_review",
        },
        "health_check": {
            "key": _CACHE_PREFIX_LLM + f"health_check_{fp_health_check}",
            "ttl": _get_cache_ttl_llm("health_check"),
            "can_cache": not force_flag and llm_config.get("cache_enabled_health_check", True),
            "thinking_key": "thinking_enabled_health_check",
        },
        "penetration_deep": {
            "key": _CACHE_PREFIX_LLM + f"penetration_deep_{fp_penetration_deep}",
            "ttl": _get_cache_ttl_llm("penetration_deep"),
            "can_cache": not force_flag and llm_config.get("cache_enabled_penetration_deep", True),
            "thinking_key": "thinking_enabled_penetration_deep",
        },
    }
    return info


def _precheck_one_cache(
    cache_info: dict, llm_config: dict, module_key: str = "",
) -> tuple[str | None, bool]:
    """预检单个模块的缓存，返回 (result, from_cached)。

    缓存命中时同时记录模块用量（_record_per_module），
    确保 LLM API 用量页签能正确显示"缓存"状态。
    """
    if not cache_info["can_cache"]:
        return (None, False)
    cached = cache_get(cache_info["key"], cache_info["ttl"])
    if not cached:
        return (None, False)
    clean = cached
    model = _extract_model_from_cached(cached)
    hint = _cache_line_model_tpl(model) if model else _CACHE_LINE_HTML
    thinking_enabled = llm_config.get(cache_info["thinking_key"], False)
    if thinking_enabled:
        hint = hint.rstrip().replace("</p>", " | Extended Thinking</p>", 1)
    # 记录模块用量，确保 API 用量页签显示"缓存"状态而非"—"
    if module_key:
        _name_for_record = model or llm_config.get("model", "") or "缓存命中"
        _endpoint_for_record = llm_config.get("endpoint", "") or ""
        _record_per_module(module_key, _name_for_record, cached=True,
                           thinking=thinking_enabled, endpoint=_endpoint_for_record)
    return (clean + hint, True)


def _precheck_all_modules(
    llm_config: dict, cache_info: dict[str, dict], _force: bool,
) -> dict[str, dict]:
    """检查所有模块的状态（已禁用/缓存命中/缓存未命中）。"""
    results: dict[str, dict] = {}
    for module_key, info in cache_info.items():
        enabled = _is_llm_module_enabled(llm_config, module_key)
        if not enabled:
            logger.info("%s LLM 分析已禁用（enabled_llm.%s = false）", _MN(module_key), module_key)
            _LLM_MODULE_FAILURE[module_key] = FAIL_REASON_DISABLED
            results[module_key] = {"result": None, "cached": False}
            continue
        result, from_cache = _precheck_one_cache(info, llm_config, module_key)
        results[module_key] = {"result": result, "cached": from_cache}
    return results


def _dispatch_llm_workers(
    needs: dict[str, bool], llm_config: dict | None, force: bool,
    a_indices, us_indices,
    total_mv: float, total_cost: float, total_profit: float,
    total_today_profit: float, holdings_count: int, categories: dict,
    penetrated_assets: list[dict] | None, holdings_details: list[dict] | None,
    sector_flow: list[dict] | None,
    f_context: dict | None = None,
) -> dict[str, dict]:
    """对缓存未命中的模块提交线程池任务，返回结果字典。"""
    if not any(needs.values()):
        return {}

    results_dict: dict[str, dict] = {}
    _label_map: dict[str, str] = get_llm_module_names()

    def _make_runner(label: str, fn: Callable) -> Callable:
        """创建闭包：持 httpx.Client（HTTP/2 + 连接池）运行 fn(c, llm_config)。"""
        def _run() -> tuple[str | None, bool]:
            logger.info("正在生成：%s...", _label_map.get(label, label))
            try:
                c = httpx.Client(timeout=_LLM_TIMEOUT, **_LLM_CLIENT_SETTINGS)
            except ImportError:
                # h2 包未安装时降级到 HTTP/1.1
                logger.info("h2 包未安装，降级到 HTTP/1.1")
                _settings = dict(_LLM_CLIENT_SETTINGS)
                _settings.pop("http2", None)
                c = httpx.Client(timeout=_LLM_TIMEOUT, **_settings)
            try:
                return fn(c, llm_config)
            finally:
                c.close()
        return _run

    _MODULE_FNS: dict[str, Callable] = {
        "global_macro": lambda c, lc: generate_global_macro(
            a_indices, us_indices, total_mv, total_profit, categories,
            sector_flow=sector_flow, force=force, http_client=c, llm_config=lc,
        ),
        "expert_review": lambda c, lc: generate_expert_review(
            total_mv, total_cost, total_profit, total_today_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details, force=force,
            http_client=c, llm_config=lc,
            f_context=f_context,
        ),
        "health_check": lambda c, lc: generate_health_check(
            total_mv, total_cost, total_profit, total_today_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details, force=force,
            http_client=c, llm_config=lc,
            f_context=f_context,
        ),
        "penetration_deep": lambda c, lc: generate_penetration_deep_analysis(
            total_mv, total_cost, total_profit, total_today_profit,
            holdings_count, categories, penetrated_assets,
            holdings_details=holdings_details, force=force,
            http_client=c, llm_config=lc,
        ),
    }

    _max_workers = (llm_config or {}).get("llm_max_concurrency", 3)
    with ThreadPoolExecutor(max_workers=_max_workers) as executor:
        _futures: dict[Future, str] = {
            executor.submit(_make_runner(k, fn)): k
            for k, fn in _MODULE_FNS.items() if needs.get(k)
        }

        for future in as_completed(_futures):
            try:
                result, from_cache = future.result()
                key = _futures[future]
                results_dict[key] = {"result": result, "cached": from_cache}
                logger.info("%s生成完成" if result else "%s生成失败（跳过）", _label_map.get(key, key))
            except Exception:  # noqa: PERF203
                logger.warning("LLM 生成线程异常", exc_info=True)

    return results_dict


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
    f_context: dict | None = None,
) -> tuple[str | None, str | None, str | None, str | None, bool, bool, bool, bool]:
    """并行生成全球政经局势 + 智囊团深度复盘 + 持仓体检报告 + 穿透深度分析。

    优化：
      - 调用 get_llm_config() 仅一次，避免各生成函数内部重复文件 I/O
      - 预计算指纹 + 缓存键，仅对缓存未命中的模块提交线程池任务
      - 缓存命中的模块直接读取内容，节省线程开销

    使用 ThreadPoolExecutor(max_workers=llm_config.llm_max_concurrency, 默认 3) 并发调用四个 LLM 生成任务。
    每个工作线程创建独立的 httpx.Client，避免全局共享连接池的线程安全问题。

    Args:
        f_context: F 迭代时间维度上下文（含 diff 差异摘要），传递给 expert_review 和 health_check。

    Returns:
        (global_macro_html, expert_review_html, health_check_html, penetration_deep_html,
         global_macro_cached, expert_review_cached, health_check_cached, penetration_deep_cached) 八元组
    """
    llm_config = get_llm_config()
    if llm_config is None:
        return (None, None, None, None, False, False, False, False)

    cache_info = _compute_module_cache_info(
        llm_config, a_indices, us_indices,
        total_mv, total_cost, total_profit, total_today_profit,
        holdings_count, categories, penetrated_assets, holdings_details,
        force,
    )

    precheck_results = _precheck_all_modules(llm_config, cache_info, force)

    needs = {k: (v["result"] is None and _is_llm_module_enabled(llm_config, k))
             for k, v in precheck_results.items()}

    worker_results = _dispatch_llm_workers(
        needs, llm_config, force,
        a_indices, us_indices, total_mv, total_cost, total_profit,
        total_today_profit, holdings_count, categories,
        penetrated_assets, holdings_details, sector_flow,
        f_context=f_context,
    )

    # 合并预检结果 + 工作线程结果
    for k, v in worker_results.items():
        if k in precheck_results:
            precheck_results[k] = v

    # 提取最终结果
    def _get(mk: str) -> tuple[str | None, bool]:
        r = precheck_results.get(mk, {})
        return (r.get("result"), r.get("cached", False))

    gm_r, gm_c = _get("global_macro")
    er_r, er_c = _get("expert_review")
    hc_r, hc_c = _get("health_check")
    pd_r, pd_c = _get("penetration_deep")

    logger.info("LLM 生成完成: %s=%s, %s=%s, %s=%s, %s=%s",
                _MN("global_macro"), "OK" if gm_r else "跳过",
                _MN("expert_review"), "OK" if er_r else "跳过",
                _MN("health_check"), "OK" if hc_r else "跳过",
                _MN("penetration_deep"), "OK" if pd_r else "跳过")
    return (gm_r, er_r, hc_r, pd_r, gm_c, er_c, hc_c, pd_c)
