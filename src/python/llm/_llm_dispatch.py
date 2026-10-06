"""LLM 批量生成的 worker 装配与线程池并发分发 —— 进度回调与并发上限调度。

`_build_module_fns` 把 LLM 模块名映射到对应生成函数（**新增 LLM 模块在此登记**，
无需深入分发函数）；`_dispatch_llm_workers` 用 `ThreadPoolExecutor` 并发跑 worker、
按完成顺序回报进度，内含 thinking 模块串行上限与辩论模式组合的调度决策。

对外门面 `generators_orchestrator.py` re-export `_dispatch_llm_workers`（`generate_all_llm`
在门面内消费它，既有 patch 点不变）；`_build_module_fns` / `_LLM_CLIENT_SETTINGS`
仅由本模块持有，测试直接从本模块 import/patch。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from src.python.core.http_client import make_http_client
from src.python.core.registry import get_llm_module_names
from src.python.llm.api_base import LLM_TIMEOUT
from src.python.llm.generators import (
    generate_debate_procon,
    generate_expert_review,
    generate_global_macro,
    generate_health_check,
    generate_penetration_deep_analysis,
)

logger = logging.getLogger("invest")


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
    data_quality_text: str = "",
    history_data: dict | None = None,
    purchase_constraint_block: str = "",
    holding_change_block: str = "",
    event_impact_block: str = "",
    schedule_replay_block: str = "",
) -> dict[str, Callable]:
    """构建 LLM 模块名称 → 生成函数闭包 的映射。

    模块级集中注册，新增 LLM 模块只需在此添加条目。
    每个闭包签名: (http_client, llm_config) → (result_str | None, from_cache)。

    history_data 贯通到三个承接模块，使其写侧指纹与预检指纹同源（见
    ``llm/module_fingerprint.py``）；漏传会让写侧指纹少一项风险信号摘要，
    预检键永不命中。
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
            purchase_constraint_block=purchase_constraint_block,
            holding_change_block=holding_change_block,
            event_impact_block=event_impact_block,
            schedule_replay_block=schedule_replay_block,
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
            purchase_constraint_block=purchase_constraint_block,
            holding_change_block=holding_change_block,
            event_impact_block=event_impact_block,
            schedule_replay_block=schedule_replay_block,
            force=force,
            http_client=c,
            llm_config=lc,
            pipeline_data=pipeline_data,
            competitive_context=competitive_context,
            metrics=metrics,
            history_data=history_data,
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
            purchase_constraint_block=purchase_constraint_block,
            holding_change_block=holding_change_block,
            event_impact_block=event_impact_block,
            schedule_replay_block=schedule_replay_block,
            force=force,
            http_client=c,
            llm_config=lc,
            pipeline_data=pipeline_data,
            data_quality_text=data_quality_text,
            history_data=history_data,
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
            purchase_constraint_block=purchase_constraint_block,
            holding_change_block=holding_change_block,
            event_impact_block=event_impact_block,
            schedule_replay_block=schedule_replay_block,
            force=force,
            http_client=c,
            llm_config=lc,
            history_data=history_data,
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
    metrics: dict | None = None,
    data_quality_text: str = "",
    comparison_indices: dict[str, str] | None = None,
    history_data: dict | None = None,
    _debate_info_container: list | None = None,
    competitive_context: str = "",
    purchase_constraint_block: str = "",
    holding_change_block: str = "",
    event_impact_block: str = "",
    schedule_replay_block: str = "",
) -> dict[str, dict]:
    """对缓存未命中的模块提交线程池任务，返回结果字典。

    Args:
        _debate_info_container: 辩论模式信息捕获容器（list[dict|None]），
            启用辩论模式时闭包写入 debate_info dict，调用方事后读取。
        competitive_context: 由调用方（``generate_all_llm``）渲染一次的竞争语境
            文本块，与其交给预检侧的**同一实例**——本函数不再自行渲染，
            否则进提示词的文本可能与进指纹的文本不同（缓存键与内容脱钩）。
        data_quality_text: 同理由调用方渲染一次的数据质量详细状态块，同样与
            预检侧共享同一实例（仅 health_check 提示词含该段）。
    """
    if not any(needs.values()):
        return {}

    # 量化指标 + 数据质量块传递
    _metrics = metrics
    _data_quality_text = data_quality_text

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
        competitive_context=competitive_context,
        metrics=_metrics,
        data_quality_text=_data_quality_text,
        history_data=history_data,
        purchase_constraint_block=purchase_constraint_block,
        holding_change_block=holding_change_block,
        event_impact_block=event_impact_block,
        schedule_replay_block=schedule_replay_block,
    )

    # ── 辩论模式路由：替换 expert_review 条目 ─────────────────
    from src.python.config.features import is_feature_enabled

    def _build_debate_mode_combination() -> str:
        """构建当前启用的辩论模式组合标识字符串。

        Returns:
            如 "正反辩论+条件推理" 等形式。集中度问答段已内建于辩论流程
            （阈值触发），不再作为组合维度。
        """
        _parts = []
        if is_feature_enabled("llm_debate_procon"):
            _parts.append("正反辩论")
        if is_feature_enabled("llm_debate_conditional"):
            _parts.append("条件推理")
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
                    competitive_context=competitive_context,
                    metrics=_metrics,
                    purchase_constraint_block=purchase_constraint_block,
                    holding_change_block=holding_change_block,
                    event_impact_block=event_impact_block,
                    schedule_replay_block=schedule_replay_block,
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

    return results_dict
