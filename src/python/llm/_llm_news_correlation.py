"""财经新闻 LLM 关联分析子模块 — 模块级结果缓存 + 闭包 + 安全执行。

承载新闻关联责任单元：
  - `_news_correlation_result` 模块级结果缓存（新闻关联分析结果不经
    `generate_all_llm` 8 元组返回，通过此变量传递）
  - `get_news_correlation_result()` 公开读取接口
  - `_make_news_correlation_closure()` 与 `_dispatch_llm_workers` 兼容的闭包
  - `run_news_correlation_safe()` 不经线程池的安全直调入口
  - `_store_news_correlation_result()` 供门面分发线程池提取结果写入

由 `generators_orchestrator.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import httpx

from src.python.config import get_llm_config
from src.python.core.registry import get_llm_module_name
from src.python.llm.prompts import (
    FAIL_REASON_API_ERROR,
    FAIL_REASON_DISABLED,
    LLM_MODULE_FAILURE,
)

logger = logging.getLogger("invest")
_MN = get_llm_module_name


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


def _store_news_correlation_result(nc_result: str | None) -> None:
    """将 worker 结果 JSON 解析后写入模块级缓存（供门面分发线程池调用）。

    Args:
        nc_result: `_dispatch_llm_workers` 中 news_correlation worker 的
            原始 JSON 字符串（None/空 → 清空缓存）。
    """
    global _news_correlation_result
    if not nc_result:
        _news_correlation_result = None
        return
    try:
        _news_correlation_result = json.loads(nc_result)
    except (json.JSONDecodeError, TypeError):
        logger.warning("news_correlation 结果 JSON 解析失败")
        _news_correlation_result = ([], False, {})


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
                news_data,
                holdings_data,
                penetrated_assets=penetrated_assets_for_news,
                force=force,
                _http_client=c,
                llm_config=lc,
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
            news_items,
            holdings,
            penetrated_assets=penetrated_assets,
            industry_data=industry_data,
            force=force,
            llm_config=llmc,
        )
        LLM_MODULE_FAILURE.pop("news_correlation", None)
        logger.info("%s生成完成%s", _MN("news_correlation"), "（缓存）" if cached else "")
        return result, cached, token_usage
    except Exception as e:
        LLM_MODULE_FAILURE["news_correlation"] = FAIL_REASON_API_ERROR
        logger.warning("%s出错: %s", _MN("news_correlation"), e)
        return news_items, False, {}
