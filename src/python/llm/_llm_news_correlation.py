"""财经新闻 LLM 关联分析子模块 — 安全直调入口。

承载新闻关联责任单元：
  - `run_news_correlation_safe()` 不经线程池的安全直调入口

**本模块不走 `generate_all_llm` 线程池**：新闻关联的返回类型是
``(list[dict], bool, dict)``（富化后的新闻列表），与其余四个 HTML 生成模块的
``(str, bool)`` 不同，故由报告侧 `report/news_correlation.py` 直接调用本入口，
而不是注册进编排层的 `_MODULE_FNS`。编排层曾另有一条「预计算 + 模块级变量传递」
的路径，但该路径的参数（news_data / holdings_data）没有任何调用方传入，分支永不
执行——属误导性注册，已移除；模块显示名/设置键仍由 `core/registry` 单一登记
（`get_llm_module_name`）。

由 `generators_orchestrator.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

import logging

from src.python.config import get_llm_config
from src.python.core.registry import get_llm_module_name
from src.python.llm.prompts import (
    FAIL_REASON_API_ERROR,
    FAIL_REASON_DISABLED,
    LLM_MODULE_FAILURE,
)

logger = logging.getLogger("invest")
_MN = get_llm_module_name


def run_news_correlation_safe(
    news_items: list[dict],
    holdings: list,
    penetrated_assets: list[dict] | None = None,
    industry_data: dict[str, dict] | None = None,
    force: bool = False,
) -> tuple[list[dict], bool, dict]:
    """安全执行新闻关联 LLM 分析，提供一致缓存/失败处理/日志。

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
