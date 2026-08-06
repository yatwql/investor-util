"""LLM 批量编排门面 — 缓存预检查、线程池分发与 LLM 全量生成。

本文件为聚合门面：
  - 新闻关联责任单元（模块级结果缓存/闭包/安全直调） → `_llm_news_correlation.py`
门面保留缓存预检（`_compute_module_cache_info`/`_precheck_*`）、worker 分发
（`_dispatch_llm_workers`/`_build_module_fns`）与主编排入口（`generate_all_llm`）
——其内部经门面命名空间解析被 mock patch 的辅助符号（`ThreadPoolExecutor`、
`httpx`、`generate_*`、`cache_get` 等），并 re-export 子模块符号。

新增 LLM 模块需在 ``_build_module_fns`` 中添加条目，无需深入分发函数。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from src.python.cache import get as cache_get
from src.python.config import get_llm_config
from src.python.core.http_client import make_http_client
from src.python.llm.api_base import (
    LLM_TIMEOUT,
    _build_cache_hint_and_record,
)
from src.python.llm.fingerprint import (
    build_llm_fingerprint,
    compute_fingerprint,
    get_cache_ttl_llm,
)
from src.python.llm.fact_checker import run_fact_check
from src.python.llm.generators import (
    generate_debate_procon,
    generate_expert_review,
    generate_global_macro,
    generate_health_check,
    generate_penetration_deep_analysis,
)
from src.python.llm.prompts import (
    CACHE_PREFIX_LLM,
    FAIL_REASON_DISABLED,
    LLM_MODULE_FAILURE,
    _build_competitive_context_block,
)
from src.python.llm.skeleton import is_llm_module_enabled
from src.python.core.registry import get_llm_module_name, get_llm_module_names

logger = logging.getLogger("invest")
_MN = get_llm_module_name


# ── 子模块 re-export ──────────────────────────────────────
# news_correlation 责任单元（模块级结果缓存 + 闭包 + 安全直调）
# 在 `_llm_news_correlation.py` 中实现，此处 re-export。
from src.python.llm._llm_news_correlation import (  # noqa: F401
    _make_news_correlation_closure,
    _store_news_correlation_result,
    get_news_correlation_result,
    run_news_correlation_safe,
)


__all__ = [
    "_build_module_fns",
    "_LLM_CLIENT_SETTINGS",
    "_compute_module_cache_info",
    "_precheck_one_cache",
    "_precheck_all_modules",
    "_dispatch_llm_workers",
    "generate_all_llm",
    "get_news_correlation_result",
    "run_news_correlation_safe",
]


# ── HTTP 客户端配置 ──────────────────────────────────────────
# 各工作线程共享同一组连接参数，通过 HTTP/2 + keepalive 减少连接建立开销
_LLM_MAX_CONNECTIONS = 20  # 总连接池上限
_LLM_MAX_KEEPALIVE = 10  # 空闲保持连接数
_LLM_CLIENT_SETTINGS: dict[str, Any] = {
    "http2": True,  # HTTP/2 多路复用
    "limits": httpx.Limits(
        max_connections=_LLM_MAX_CONNECTIONS,
        max_keepalive_connections=_LLM_MAX_KEEPALIVE,
    ),
}


def _compute_module_cache_info(
    llm_config: dict,
    a_indices,
    us_indices,
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    _holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None,
    holdings_details: list[dict] | None,
    force: bool,
    *,
    history_data: dict | None = None,
) -> dict[str, dict]:
    """预计算各模块指纹/缓存键/TTL/可缓存性，返回数据结构。

    history_data 风险信号 Hash 加入专家/体检/穿透指纹。
    """
    fp_global_macro = compute_fingerprint(
        a_indices,
        us_indices,
        total_mv,
        total_profit,
        categories,
    )
    fp_expert_review = build_llm_fingerprint(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
        history_data=history_data,
    )
    fp_health_check = build_llm_fingerprint(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
        history_data=history_data,
    )
    fp_penetration_deep = build_llm_fingerprint(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
        full_penetration=True,
        history_data=history_data,
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
    cache_info: dict,
    llm_config: dict,
    module_key: str = "",
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
    thinking_enabled = llm_config.get(cache_info["thinking_key"], False)
    # 当 endpoint 为空时有 provider chain 则尝试解析
    endpoint = llm_config.get("endpoint", "") or ""
    if not endpoint and llm_config.get("_provider_list") and module_key:
        from src.python.llm.api import _resolve_first_provider_model_endpoint

        _, endpoint = _resolve_first_provider_model_endpoint(llm_config, module_key)
    augmented_html = _build_cache_hint_and_record(
        cached,
        module_key,
        llm_config,
        thinking_enabled,
        endpoint=endpoint,
    )
    return (augmented_html, True)


def _precheck_all_modules(
    llm_config: dict,
    cache_info: dict[str, dict],
    _force: bool,
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


def _build_module_fns(
    a_indices,
    us_indices,
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None,
    holdings_details: list[dict] | None,
    sector_flow: list[dict] | None,
    force: bool,
    pipeline_data: dict | None = None,
    competitive_context: str = "",
    metrics: dict | None = None,
    degradation_events: list[dict] | None = None,
) -> dict[str, Callable]:
    """构建 LLM 模块名称 → 生成函数闭包 的映射。

    模块级集中注册，新增 LLM 模块只需在此添加条目。
    每个闭包签名: (http_client, llm_config) → (result_str | None, from_cache)。
    """
    return {
        "global_macro": lambda c, lc: generate_global_macro(
            a_indices,
            us_indices,
            total_mv,
            total_profit,
            total_cost,
            categories,
            sector_flow=sector_flow,
            force=force,
            http_client=c,
            llm_config=lc,
            competitive_context=competitive_context,
            holdings_details=holdings_details,
        ),
        "expert_review": lambda c, lc: generate_expert_review(
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
            force=force,
            http_client=c,
            llm_config=lc,
            pipeline_data=pipeline_data,
            competitive_context=competitive_context,
            metrics=metrics,
        ),
        "health_check": lambda c, lc: generate_health_check(
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
            force=force,
            http_client=c,
            llm_config=lc,
            pipeline_data=pipeline_data,
            degradation_events=degradation_events,
        ),
        "penetration_deep": lambda c, lc: generate_penetration_deep_analysis(
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
            force=force,
            http_client=c,
            llm_config=lc,
        ),
    }


def _dispatch_llm_workers(
    needs: dict[str, bool],
    llm_config: dict | None,
    force: bool,
    a_indices,
    us_indices,
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None,
    holdings_details: list[dict] | None,
    sector_flow: list[dict] | None,
    pipeline_data: dict | None = None,
    *,
    news_data: list[dict] | None = None,
    holdings_data: list | None = None,
    penetrated_assets_for_news: list[dict] | None = None,
    metrics: dict | None = None,
    degradation_events: list[dict] | None = None,
    comparison_indices: dict[str, str] | None = None,
    history_data: dict | None = None,
    _debate_info_container: list | None = None,
) -> dict[str, dict]:
    """对缓存未命中的模块提交线程池任务，返回结果字典。

    Args:
        _debate_info_container: 辩论模式信息捕获容器（list[dict|None]），
            启用辩论模式时闭包写入 debate_info dict，调用方事后读取。
    """
    if not any(needs.values()):
        return {}

    # ── 预计算竞争语境文本块 ──
    _competitive_context = _build_competitive_context_block(
        a_indices,
        total_mv,
        total_today_profit,
        comparison_indices=comparison_indices,
        history_data=history_data,
        metrics=metrics,
    )
    # 量化指标 + 降级事件传递
    _metrics = metrics
    _degradation_events = degradation_events

    results_dict: dict[str, dict] = {}
    _label_map: dict[str, str] = get_llm_module_names()

    # ── thinking 并发限制：开启 Extended Thinking 的模块（health_check / expert_review
    #    ）并发涌向 DeepSeek 时偶发返回空 content（HTTP 200 + 空响应）。用信号量限制
    #    thinking 请求同时最多 llm_max_thinking_concurrency 个（默认 1），从源头降低
    #    偶发概率；非 thinking 模块不受限，保持原有并发。 ──
    try:
        _thinking_limit = max(1, int((llm_config or {}).get("llm_max_thinking_concurrency", 1)))
    except (TypeError, ValueError):
        _thinking_limit = 1
    _thinking_sem = threading.BoundedSemaphore(_thinking_limit)

    def _is_thinking_module(label: str) -> bool:
        return bool((llm_config or {}).get(f"thinking_enabled_{label}", False))

    def _make_runner(label: str, fn: Callable) -> Callable:
        """创建闭包：持 httpx.Client（HTTP/2 + 连接池）运行 fn(c, llm_config)。

        thinking 模块（thinking_enabled_{label}=true）受信号量约束，同一时刻最多
        llm_max_thinking_concurrency 个并发请求；非 thinking 模块直接运行。
        """

        def _run() -> tuple[str | None, bool]:
            if _is_thinking_module(label):
                with _thinking_sem:
                    return _execute(label, fn)
            return _execute(label, fn)

        def _execute(label: str, fn: Callable) -> tuple[str | None, bool]:
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

    _MODULE_FNS = _build_module_fns(
        a_indices=a_indices,
        us_indices=us_indices,
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_count=holdings_count,
        categories=categories,
        penetrated_assets=penetrated_assets,
        holdings_details=holdings_details,
        sector_flow=sector_flow,
        force=force,
        pipeline_data=pipeline_data,
        competitive_context=_competitive_context,
        metrics=_metrics,
        degradation_events=_degradation_events,
    )

    # ── 辩论模式路由：替换 expert_review 条目 ─────────────────
    from src.python.config.features import is_feature_enabled

    def _build_debate_mode_combination() -> str:
        """构建当前启用的辩论模式组合标识字符串。

        Returns:
            如 "正反辩论+条件推理" 或 "条件推理+集中度问答" 等形式。
        """
        _parts = []
        if is_feature_enabled("llm_debate_procon"):
            _parts.append("正反辩论")
        if is_feature_enabled("llm_debate_conditional"):
            _parts.append("条件推理")
        if is_feature_enabled("llm_debate_qa_concentration"):
            _parts.append("集中度问答")
        return "+".join(_parts) if _parts else ""

    if is_feature_enabled("llm_debate_procon") and needs.get("expert_review"):
        _original_expert = _MODULE_FNS["expert_review"]

        def _debate_wrapper(c, lc) -> tuple[str | None, bool]:
            """辩论包装闭包：pro→con→synthesis，两级 fallback。"""
            try:
                _result = generate_debate_procon(
                    total_mv,
                    total_cost,
                    total_profit,
                    total_today_profit,
                    holdings_count,
                    categories,
                    penetrated_assets,
                    holdings_details=holdings_details,
                    force=force,
                    http_client=c,
                    llm_config=lc,
                    pipeline_data=pipeline_data,
                    competitive_context=_competitive_context,
                    metrics=_metrics,
                )
                pro, con, synthesis = _result
                if pro and con:
                    # 记录 debate_info
                    if _debate_info_container is not None:
                        _debate_info_container[0] = {
                            "pro_text": pro,
                            "con_text": con,
                            "mode_label": "🧪 辩论模式",
                            "mode_combination": _build_debate_mode_combination(),
                        }
                    if synthesis:
                        return (synthesis, True)
                    # synthesis 失败 → 返回 pro+con 拼接
                    logger.warning("[debate] 综合失败，返回 pro+con 拼接")
                    return (f"【白脸观点】\n{pro}\n\n【黑脸观点】\n{con}", True)
                # pro 或 con 失败 → 回退普通 expert_review
                logger.warning("[debate] pro/con 失败，回退普通 expert_review")
                if _debate_info_container is not None:
                    _debate_info_container[0] = None
                return _original_expert(c, lc)
            except Exception:
                logger.warning("[debate] 异常，回退普通 expert_review", exc_info=True)
                if _debate_info_container is not None:
                    _debate_info_container[0] = None
                return _original_expert(c, lc)

        _MODULE_FNS["expert_review"] = _debate_wrapper
        logger.info("[debate] 辩论模式已启用，expert_review 路由已替换")

    # news_correlation 可选集成：仅在提供了新闻和持仓数据时注册
    if news_data is not None and holdings_data is not None:
        _MODULE_FNS["news_correlation"] = _make_news_correlation_closure(
            news_data,
            holdings_data,
            penetrated_assets_for_news,
            force,
        )

    _max_workers = (llm_config or {}).get("llm_max_concurrency", 3)
    with ThreadPoolExecutor(max_workers=_max_workers) as executor:
        _futures: dict[Future, str] = {
            executor.submit(_make_runner(k, fn)): k for k, fn in _MODULE_FNS.items() if needs.get(k)
        }

        for future in as_completed(_futures):
            try:
                result, from_cache = future.result()
                key = _futures[future]
                results_dict[key] = {"result": result, "cached": from_cache}
                logger.info("%s生成完成" if result else "%s生成失败（跳过）", _label_map.get(key, key))
            except Exception:  # noqa: PERF203
                logger.warning("LLM 生成线程异常", exc_info=True)

    # 提取 news_correlation 结果到模块级变量（委托子模块存储）
    if "news_correlation" in results_dict:
        _store_news_correlation_result(results_dict["news_correlation"]["result"])

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
    pipeline_data: dict | None = None,
    history_data: dict | None = None,
    metrics: dict | None = None,
    degradation_events: list[dict] | None = None,
    comparison_indices: dict[str, str] | None = None,
) -> tuple[str | None, str | None, str | None, str | None, bool, bool, bool, bool]:
    """并行生成全球政经局势 + 智囊团深度复盘 + 持仓体检报告 + 穿透深度分析。

    优化：
      - 调用 get_llm_config() 仅一次，避免各生成函数内部重复文件 I/O
      - 预计算指纹 + 缓存键，仅对缓存未命中的模块提交线程池任务
      - 缓存命中的模块直接读取内容，节省线程开销

    使用 ThreadPoolExecutor(max_workers=llm_config.llm_max_concurrency, 默认 3) 并发调用四个 LLM 生成任务。
    每个工作线程创建独立的 httpx.Client，避免全局共享连接池的线程安全问题。

    Args:
        pipeline_data: 组合历史走势时间维度上下文（含 diff 差异摘要），传递给 expert_review 和 health_check。
        history_data: 组合历史走势数据字典（含风险指标）。
        metrics: 量化指标字典，compute_all_metrics() 的输出。
        degradation_events: DegradationTracker.get_log() 输出。
        comparison_indices: {代码: 名称} 对比指数池，用于竞争语境多指数对比。

    Returns:
        (global_macro_html, expert_review_html, health_check_html, penetration_deep_html,
         global_macro_cached, expert_review_cached, health_check_cached, penetration_deep_cached) 八元组
    """
    llm_config = get_llm_config()
    if llm_config is None:
        return (None, None, None, None, False, False, False, False)

    cache_info = _compute_module_cache_info(
        llm_config,
        a_indices,
        us_indices,
        total_mv,
        total_cost,
        total_profit,
        total_today_profit,
        holdings_count,
        categories,
        penetrated_assets,
        holdings_details,
        force,
        history_data=history_data,
    )

    precheck_results = _precheck_all_modules(llm_config, cache_info, force)

    from src.python.config.features import is_feature_enabled

    needs = {k: (v["result"] is None and is_llm_module_enabled(llm_config, k)) for k, v in precheck_results.items()}

    # ── 辩论模式：强制不走标准 expert_review 缓存预检 ──────
    # 辩论路由使用独立缓存键（llm_debate_pro_/llm_debate_con_/llm_debate_synthesis_），
    # 与标准 expert_review 缓存键（llm_expert_review_）不同，需绕过标准缓存预检。
    if is_feature_enabled("llm_debate_procon"):
        needs["expert_review"] = is_llm_module_enabled(llm_config, "expert_review")

    # ── 辩论模式容器（用于闭包捕获 debate_info） ────────
    _debate_info_container: list[dict | None] = [None]
    _has_debate = is_feature_enabled("llm_debate_procon")

    worker_results = _dispatch_llm_workers(
        needs,
        llm_config,
        force,
        a_indices,
        us_indices,
        total_mv,
        total_cost,
        total_profit,
        total_today_profit,
        holdings_count,
        categories,
        penetrated_assets,
        holdings_details,
        sector_flow,
        pipeline_data=pipeline_data,
        metrics=metrics,
        degradation_events=degradation_events,
        comparison_indices=comparison_indices,
        history_data=history_data,
        _debate_info_container=_debate_info_container,
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

    # ── 事实锚定校验 ──────────────────────────────────────
    # 对已生成的 LLM 内容运行纯算法层事实校验，追加校验摘要到 HTML 底部。
    # 仅检查非缓存且非空的模块（缓存命中说明内容未变化，无需重复校验）。
    _module_labels = get_llm_module_names()

    # 读取事实校验容差配置（来自 llm_settings.json fact_check 段）
    _fc_cfg = (llm_config or {}).get("fact_check", {})
    _fc_tolerance: float = _fc_cfg.get("tolerance", 1.0)
    _fc_overrides: dict = _fc_cfg.get("tolerance_overrides", {})

    # 提取穿透资产中的股票代码（用于穿透分析的品种存在性校验）

    # 提取穿透资产中的股票代码（用于穿透分析的品种存在性校验）
    _penetrated_codes: set[str] = set()
    if penetrated_assets:
        for _asset in penetrated_assets:
            _codes = _asset.get("codes") or []
            _penetrated_codes.update(_codes)

    if holdings_details and any(r is not None for r in (gm_r, er_r, hc_r, pd_r)):
        for _mk, _result, _cached in [
            ("global_macro", gm_r, gm_c),
            ("expert_review", er_r, er_c),
            ("health_check", hc_r, hc_c),
            ("penetration_deep", pd_r, pd_c),
        ]:
            if _result:
                _mod_tolerance = _fc_overrides.get(_mk, _fc_tolerance)
                _corrected, _summary = run_fact_check(
                    _result,
                    holdings_details,
                    module_label=_module_labels.get(_mk, _mk),
                    # 智囊团/持仓体检/穿透深度三模块的提示词均含【穿透 TOP10】数据
                    # （_format_penetration_block），LLM 会引用穿透股票代码（如宁德时代
                    # 300750、阳光电源 300274）——它们非直接持仓但属于组合穿透范围，
                    # 品种存在性校验时须作为额外有效代码，否则误报"不在当前持仓中"。
                    # 全球政经（global_macro）提示词不含穿透数据，保持严格校验。
                    extra_valid_codes=_penetrated_codes
                    if _mk in ("penetration_deep", "expert_review", "health_check")
                    else None,
                    is_penetration_module=_mk == "penetration_deep",
                    tolerance_pct=_mod_tolerance,
                    history_data=history_data,
                    # 缓存命中：LLM 内容基于生成时的数据快照，用当前市值校验其
                    # 排名声称会因价格变动产生"排名翻转"误报 → 跳过排名校验。
                    # 数值/品种校验仍执行，缓存内容中的数值错误仍会被自动修正。
                    skip_ranking_check=_cached,
                )
                # 用修正后的内容替换原结果
                if _corrected != _result and _corrected != _summary:
                    _result = _corrected
                if _summary and _summary not in _result:
                    _result = _result + "\n" + _summary
                # 写回元组变量
                if _mk == "global_macro":
                    gm_r = _result
                elif _mk == "expert_review":
                    er_r = _result
                elif _mk == "health_check":
                    hc_r = _result
                elif _mk == "penetration_deep":
                    pd_r = _result

    logger.info(
        "LLM 生成完成: %s=%s, %s=%s, %s=%s, %s=%s",
        _MN("global_macro"),
        "OK" if gm_r else "跳过",
        _MN("expert_review"),
        "OK" if er_r else "跳过",
        _MN("health_check"),
        "OK" if hc_r else "跳过",
        _MN("penetration_deep"),
        "OK" if pd_r else "跳过",
    )
    _raw_debate_info = _debate_info_container[0] if _has_debate else None
    if _has_debate:
        return (gm_r, er_r, hc_r, pd_r, gm_c, er_c, hc_c, pd_c, _raw_debate_info)
    return (gm_r, er_r, hc_r, pd_r, gm_c, er_c, hc_c, pd_c)
