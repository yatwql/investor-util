"""LLM 批量编排模块 — 缓存预检查、线程池分发与 LLM 全量生成。

R-198 从 generators.py 拆分：包含 _compute_module_cache_info、
_precheck_one_cache、_precheck_all_modules、_dispatch_llm_workers、
generate_all_llm 和 _LLM_CLIENT_SETTINGS。

``_MODULE_FNS`` 集中管理所有 LLM 模块的生成函数，确保一致的
缓存预检、线程池分发和失败处理。新增模块需在此注册。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from src.python.cache import get as cache_get
from src.python.config import get_llm_config
from src.python.http_client import make_http_client
from src.python.llm.api_base import (
    CACHE_LINE_HTML,
    LLM_TIMEOUT,
    _cache_line_model_tpl,
    _extract_model_from_cached,
)
from src.python.llm.fingerprint import (
    build_llm_fingerprint,
    compute_fingerprint,
    get_cache_ttl_llm,
)
from src.python.llm.prompts import (
    CACHE_PREFIX_LLM,
    LLM_MODULE_FAILURE,
    FAIL_REASON_DISABLED,
    FAIL_REASON_API_ERROR,
)
from src.python.llm.session import record_per_module
from src.python.llm.skeleton import is_llm_module_enabled
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
    "get_news_correlation_result",
    "run_news_correlation_safe",
]


# ── news_correlation 模块级结果缓存 ──────────────────────────
# news_correlation 的 LLM 分析结果不通过 generate_all_llm 的 8 元组返回
# （因返回类型与其余 HTML 生成模块不同），通过此模块级变量传递
# 给 report/news_correlation.py 消费。
_news_correlation_result: tuple[list[dict], bool, dict] | None = None


def get_news_correlation_result() -> tuple[list[dict], bool, dict] | None:
    """获取预计算的新闻关联 LLM 分析结果。

    若通过 ``generate_all_llm`` 的 news_* 参数集成了 news_correlation，
    其结果存储于此。report/news_correlation.py 应优先使用此结果，
    避免重复调用 LLM API。
    """
    return _news_correlation_result


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
    fp_global_macro = compute_fingerprint(
        a_indices, us_indices, total_mv, total_profit, categories,
    )
    fp_expert_review = build_llm_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
    )
    fp_health_check = build_llm_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories,
    )
    fp_penetration_deep = build_llm_fingerprint(
        total_mv=total_mv, total_cost=total_cost,
        total_profit=total_profit, total_today_profit=total_today_profit,
        holdings_details=holdings_details, penetrated_assets=penetrated_assets,
        categories=categories, full_penetration=True,
    )

    force_flag = force
    info: dict[str, dict] = {
        "global_macro": {
            "key": CACHE_PREFIX_LLM + f"global_macro_{fp_global_macro}",
            "ttl": get_cache_ttl_llm("global_macro"),
            "can_cache": not force_flag and llm_config.get("cache_enabled_global_macro", True),
            "thinking_key": "thinking_enabled_global_macro",
        },
        "expert_review": {
            "key": CACHE_PREFIX_LLM + f"expert_review_{fp_expert_review}",
            "ttl": get_cache_ttl_llm("expert_review"),
            "can_cache": not force_flag and llm_config.get("cache_enabled_expert_review", True),
            "thinking_key": "thinking_enabled_expert_review",
        },
        "health_check": {
            "key": CACHE_PREFIX_LLM + f"health_check_{fp_health_check}",
            "ttl": get_cache_ttl_llm("health_check"),
            "can_cache": not force_flag and llm_config.get("cache_enabled_health_check", True),
            "thinking_key": "thinking_enabled_health_check",
        },
        "penetration_deep": {
            "key": CACHE_PREFIX_LLM + f"penetration_deep_{fp_penetration_deep}",
            "ttl": get_cache_ttl_llm("penetration_deep"),
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
    hint = _cache_line_model_tpl(model) if model else CACHE_LINE_HTML
    thinking_enabled = llm_config.get(cache_info["thinking_key"], False)
    if thinking_enabled:
        hint = hint.rstrip().replace("</p>", " | Extended Thinking</p>", 1)
    # 记录模块用量，确保 API 用量页签显示"缓存"状态而非"—"
    if module_key:
        _name_for_record = model or llm_config.get("model", "") or "缓存命中"
        _endpoint_for_record = llm_config.get("endpoint", "") or ""
        if not _endpoint_for_record and llm_config.get("_provider_list") and module_key:
            from src.python.llm.api import _resolve_first_provider_model_endpoint
            _, _endpoint_for_record = _resolve_first_provider_model_endpoint(llm_config, module_key)
        record_per_module(module_key, _name_for_record, cached=True,
                           thinking=thinking_enabled, endpoint=_endpoint_for_record)
    return (clean + hint, True)


def _precheck_all_modules(
    llm_config: dict, cache_info: dict[str, dict], _force: bool,
) -> dict[str, dict]:
    """检查所有模块的状态（已禁用/缓存命中/缓存未命中）。"""
    results: dict[str, dict] = {}
    for module_key, info in cache_info.items():
        enabled = is_llm_module_enabled(llm_config, module_key)
        if not enabled:
            logger.info("%s LLM 分析已禁用（enabled_llm.%s = false）", _MN(module_key), module_key)
            LLM_MODULE_FAILURE[module_key] = FAIL_REASON_DISABLED
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
    *,
    news_data: list[dict] | None = None,
    holdings_data: list | None = None,
    penetrated_assets_for_news: list[dict] | None = None,
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
                c = make_http_client(timeout=LLM_TIMEOUT, **_LLM_CLIENT_SETTINGS)
            except ImportError:
                # h2 包未安装时降级到 HTTP/1.1
                logger.info("h2 包未安装，降级到 HTTP/1.1")
                _settings = dict(_LLM_CLIENT_SETTINGS)
                _settings.pop("http2", None)
                c = make_http_client(timeout=LLM_TIMEOUT, **_settings)
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

    # news_correlation 可选集成：仅在提供了新闻和持仓数据时注册
    if news_data is not None and holdings_data is not None:
        _MODULE_FNS["news_correlation"] = _make_news_correlation_closure(
            news_data, holdings_data, penetrated_assets_for_news, force,
        )

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

    # 提取 news_correlation 结果到模块级变量
    if "news_correlation" in results_dict:
        global _news_correlation_result
        nc_result = results_dict["news_correlation"]["result"]
        if nc_result:
            try:
                _news_correlation_result = json.loads(nc_result)
            except (json.JSONDecodeError, TypeError):
                logger.warning("news_correlation 结果 JSON 解析失败")
                _news_correlation_result = ([], False, {})
        else:
            _news_correlation_result = None

    return results_dict


def _make_news_correlation_closure(
    news_data: list[dict],
    holdings_data: list,
    penetrated_assets_for_news: list[dict] | None,
    force: bool,
) -> Callable:
    """创建 news_correlation 的闭包，与 _MODULE_FNS 签名兼容。

    ``enhance_news_correlation`` 返回 ``(list[dict], bool, dict)``，
    与 _make_runner 期望的 ``(str | None, bool)`` 不兼容。
    此闭包包装为 ``(json.dumps(result_list), cached)`` 返回，
    实际结果通过 ``_news_correlation_result`` 模块级变量传递。
    """
    def _fn(c: httpx.Client, lc: dict | None) -> tuple[str | None, bool]:
        try:
            from src.python.llm.generators_news import enhance_news_correlation
            result_list, cached, token_usage = enhance_news_correlation(
                news_data, holdings_data,
                penetrated_assets=penetrated_assets_for_news,
                force=force, _http_client=c, llm_config=lc,
            )
            LLM_MODULE_FAILURE.pop("news_correlation", None)
            return json.dumps([result_list, cached, token_usage], ensure_ascii=False), cached
        except Exception as e:
            LLM_MODULE_FAILURE["news_correlation"] = FAIL_REASON_API_ERROR
            logger.warning("%s出错: %s", _MN("news_correlation"), e)
            return None, False
    return _fn


def run_news_correlation_safe(
    news_items: list[dict],
    holdings: list,
    penetrated_assets: list[dict] | None = None,
    industry_data: dict[str, dict] | None = None,
    force: bool = False,
) -> tuple[list[dict], bool, dict]:
    """安全执行新闻关联 LLM 分析，提供一致缓存/失败处理/日志。

    与 ``_dispatch_llm_workers`` 中的 ``_make_news_correlation_closure``
    共享相同的失败处理和日志模式，但可在不经过线程池时直接调用。

    Args:
        news_items: 关键词匹配后的新闻列表
        holdings: 持仓列表
        penetrated_assets: 穿透资产数据（可选）
        industry_data: 行业/概念数据（可选）
        force: 跳过缓存强制重新生成

    Returns:
        (富化后的新闻列表, 是否来自缓存, token 用量字典)
    """
    from src.python.config import get_llm_config

    llmc = get_llm_config()
    if not llmc:
        return news_items, False, {}

    # 检查是否已通过 orchestrator 预计算
    if _news_correlation_result is not None:
        logger.info("%s 使用 orchestrator 预计算结果", _MN("news_correlation"))
        return _news_correlation_result

    # 检查 LLM 配置
    enabled_llm = llmc.get("enabled_llm") if llmc else None
    llm_enabled = enabled_llm.get("news_correlation", False) if isinstance(enabled_llm, dict) else False
    if not llmc or not llm_enabled:
        logger.info("%s LLM 分析已禁用（enabled_llm.news_correlation = false）", _MN("news_correlation"))
        LLM_MODULE_FAILURE["news_correlation"] = FAIL_REASON_DISABLED
        return news_items, False, {}

    try:
        from src.python.llm.generators_news import enhance_news_correlation
        result, cached, token_usage = enhance_news_correlation(
            news_items, holdings,
            penetrated_assets=penetrated_assets,
            industry_data=industry_data,
            force=force, llm_config=llmc,
        )
        LLM_MODULE_FAILURE.pop("news_correlation", None)
        logger.info("%s生成完成%s", _MN("news_correlation"),
                    "（缓存）" if cached else "")
        return result, cached, token_usage
    except Exception as e:
        LLM_MODULE_FAILURE["news_correlation"] = FAIL_REASON_API_ERROR
        logger.warning("%s出错: %s", _MN("news_correlation"), e)
        return news_items, False, {}


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
        f_context: 组合历史走势时间维度上下文（含 diff 差异摘要），传递给 expert_review 和 health_check。

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

    needs = {k: (v["result"] is None and is_llm_module_enabled(llm_config, k))
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
