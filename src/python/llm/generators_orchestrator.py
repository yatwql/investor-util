"""LLM 批量编排门面 — 缓存预检查、线程池分发与 LLM 全量生成。

本文件为聚合门面：
  - 新闻关联安全直调入口 → `_llm_news_correlation.py`（该模块不经本门面的线程池，
    运行路径见其模块文档）
  - worker 装配与线程池并发分发 → `_llm_dispatch.py`（`_build_module_fns` /
    `_dispatch_llm_workers` / `_LLM_CLIENT_SETTINGS`；本门面 re-export
    `_dispatch_llm_workers`，`generate_all_llm` 在门面内消费它）
门面保留缓存预检（`_compute_module_cache_info`/`_precheck_*`）与主编排入口
（`generate_all_llm`）——其内部经门面命名空间解析被 mock patch 的辅助符号
（`cache_get`、`run_fact_check`、`get_llm_config` 等），并 re-export 子模块符号。

新增 LLM 模块需在 ``_llm_dispatch._build_module_fns`` 中添加条目，无需深入分发函数。
"""

from __future__ import annotations

import logging
from typing import Any


from src.python.cache import get as cache_get
from src.python.config import get_llm_config
from src.python.llm.api_base import (
    _build_cache_hint_and_record,
)
from src.python.llm.fingerprint import get_cache_ttl_llm
from src.python.llm.fact_checker import run_fact_check
from src.python.llm.module_fingerprint import (
    ModuleFingerprintInputs,
    expert_review_fingerprint,
    global_macro_fingerprint,
    health_check_fingerprint,
    penetration_deep_fingerprint,
)
from src.python.llm.prompts import (
    CACHE_PREFIX_LLM,
    FAIL_REASON_DISABLED,
    LLM_MODULE_FAILURE,
    _build_competitive_context_block,
    _build_data_quality_detail_block,
)
from src.python.llm.skeleton import is_llm_module_enabled
from src.python.core.registry import get_llm_module_name, get_llm_module_names

logger = logging.getLogger("invest")
_MN = get_llm_module_name


# ── 子模块 re-export ──────────────────────────────────────
# news_correlation 安全直调入口在 `_llm_news_correlation.py` 中实现，此处 re-export。
from src.python.llm._llm_dispatch import (  # noqa: F401  # 并发分发子模块（消费方在本门面）
    _dispatch_llm_workers,
)
from src.python.llm._llm_news_correlation import (  # noqa: F401
    run_news_correlation_safe,
)


__all__ = [
    "_compute_module_cache_info",
    "_precheck_one_cache",
    "_precheck_all_modules",
    "_dispatch_llm_workers",
    "generate_all_llm",
    "run_news_correlation_safe",
]


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
    pipeline_data: dict | None = None,
    competitive_context: str = "",
    metrics: dict | None = None,
    data_quality_text: str = "",
    purchase_constraint_block: str = "",
) -> dict[str, dict]:
    """预计算各模块指纹/缓存键/TTL/可缓存性，返回数据结构。

    指纹一律取自 ``llm/module_fingerprint.py``（读写同源的唯一事实来源），
    本函数**不再自行拼接**模块指纹——预检键与写侧键同源由结构保证，
    而非靠两侧逐字对齐的注释纪律（历史偏差见该模块 docstring）。

    ``competitive_context`` / ``metrics`` / ``data_quality_text`` 是提示词正文段的
    输入（详见 ``llm/module_fingerprint.py``）：本函数只对**调用方已渲染好**的
    同一实例取哈希，不自行渲染——两次渲染会让「进键的文本」与「进提示词的文本」
    脱钩。
    """
    _inputs = ModuleFingerprintInputs(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
        history_data=history_data,
        pipeline_data=pipeline_data,
        a_indices=a_indices,
        us_indices=us_indices,
        competitive_context=competitive_context,
        metrics=metrics,
        data_quality_text=data_quality_text,
        purchase_block=purchase_constraint_block or "",
    )
    fp_global_macro = global_macro_fingerprint(_inputs)
    fp_expert_review = expert_review_fingerprint(_inputs)
    fp_health_check = health_check_fingerprint(_inputs)
    fp_penetration_deep = penetration_deep_fingerprint(_inputs)

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


def extract_purchase_constraint_block(pipeline_data: dict | None) -> str:
    """从管线数据提取申购限购约束块（契约字段 ``constraint_block`` 的唯一提取点）。

    消费方两处必须同源读取：本编排层（LLM 分析章统一附录与指纹）与报告侧新闻
    批量链（``report/_llm_news.py``）。契约键名或嵌套调整只改此处，避免两份
    表达式漏改一处导致块静默缺席（降级面被误触）。

    Args:
        pipeline_data: 管线数据字典（可为 None，如无管线上下文的直调路径）。

    Returns:
        约束块原文；契约缺席（None/字段缺/降级产出空串）→ ``""``（提示词与缓存键回退原样）。
    """
    return str(((pipeline_data or {}).get("purchase_status_data") or {}).get("constraint_block") or "")


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
        degradation_events: DegradationTracker.get_log() 输出。本函数将其渲染成数据质量
            详细状态块**一次**，同一实例既进 health_check 指纹又进其提示词——否则
            数据源恢复后仍会复用故障期间缓存的健康结论。
        comparison_indices: {代码: 名称} 对比指数池，用于竞争语境多指数对比。

    Returns:
        (global_macro_html, expert_review_html, health_check_html, penetration_deep_html,
         global_macro_cached, expert_review_cached, health_check_cached, penetration_deep_cached) 八元组
    """
    llm_config = get_llm_config()
    if llm_config is None:
        return (None, None, None, None, False, False, False, False)

    # ── 竞争语境块：此处渲染**一次**，同一实例既进指纹（经预检）又进提示词
    #    （经 worker 分发）。两个消费点各自渲染会让「进键的文本」与「进提示词的
    #    文本」只能靠纪律对齐——渲染器一改而键不动，预检就会命中旧键复用按旧
    #    指数算出的对比结论。 ──
    competitive_context = _build_competitive_context_block(
        a_indices,
        total_mv,
        total_today_profit,
        comparison_indices=comparison_indices,
        history_data=history_data,
        metrics=metrics,
    )

    # ── 数据质量详细状态块：同样渲染**一次**，同一实例既进指纹（经预检）又进
    #    health_check 提示词（经 worker 分发）。否则数据源故障期间生成的体检结论
    #    会在源恢复后仍被复用——报告陈述与此刻事实相反，且不报错。 ──
    #    一并注入 data_freshness 契约：体检第 5 维还要评净值新鲜度，其基准是
    #    交易日（非运行时刻），且滞后清单须与「数据质量仪表盘」可信度区块同源。 ──
    data_quality_text = _build_data_quality_detail_block(
        degradation_events, (pipeline_data or {}).get("data_freshness")
    )

    # ── 申购限购约束块：契约构建期（report 侧）已渲染一次，此处只提取同一实例——
    #    同时交预检侧指纹与写侧提示词（进提示词必进指纹，见 module_fingerprint）。
    #    缺席（契约 None/字段缺/降级）→ ""，提示词与键双不变（降级矩阵）。 ──
    purchase_constraint_block = extract_purchase_constraint_block(pipeline_data)
    if purchase_constraint_block:
        logger.debug(
            "申购限购约束块注入 LLM 分析章（含表头共 %d 行）",
            purchase_constraint_block.count("\n") + 1,
        )
    else:
        logger.debug("申购限购约束块缺席（准入未过/未产出），提示词与缓存键回退原样")

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
        pipeline_data=pipeline_data,
        competitive_context=competitive_context,
        metrics=metrics,
        data_quality_text=data_quality_text,
        purchase_constraint_block=purchase_constraint_block,
    )

    precheck_results = _precheck_all_modules(llm_config, cache_info, force)

    from src.python.config.features import is_feature_enabled
    from src.python.llm.depth_profile import depth_gate, resolve_depth_profile

    # 深度档位：在逐模块开关之上**收窄**参与集合（brief ⊂ standard），不放大已关闭的模块
    _depth = resolve_depth_profile()
    needs = {
        k: (v["result"] is None and depth_gate(is_llm_module_enabled(llm_config, k), k, _depth))
        for k, v in precheck_results.items()
    }

    # ── 辩论模式：强制不走标准 expert_review 缓存预检 ──────
    # 辩论路由使用独立缓存键（llm_debate_pro_/llm_debate_con_/llm_debate_synthesis_），
    # 与标准 expert_review 缓存键（llm_expert_review_）不同，需绕过标准缓存预检。
    if is_feature_enabled("llm_debate_procon"):
        needs["expert_review"] = depth_gate(is_llm_module_enabled(llm_config, "expert_review"), "expert_review", _depth)

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
        data_quality_text=data_quality_text,
        comparison_indices=comparison_indices,
        history_data=history_data,
        _debate_info_container=_debate_info_container,
        competitive_context=competitive_context,
        purchase_constraint_block=purchase_constraint_block,
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

    # ── 生成后自检（开关开启时执行；自检输入是上面四个模块的产出，必须在它们之后）──
    # 不属线程池并行调度模块，故**不登记**进 _MODULE_FNS（注册纪律：无独立调度语义的
    # 编排注册属注册漂移）；模块本身仍在 core/registry.py 登记以复用缓存/统计/失败载体。
    from src.python.llm.self_review import run_self_review

    run_self_review(
        {
            "global_macro": gm_r,
            "expert_review": er_r,
            "health_check": hc_r,
            "penetration_deep": pd_r,
        },
        holdings_details,
        penetrated_assets,
        llm_config,
        force=force,
        purchase_constraint_block=purchase_constraint_block,
    )

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
