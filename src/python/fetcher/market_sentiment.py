"""市场情绪与资金热点域取数网关 — 报告层与 Provider 之间的唯一通道。

职责划分：
  - HTTP、凭据读取、限速、配额护栏：``providers/hithink.py``（上游承担）
  - 链路路由、熔断激活、fallback 递补、命中源登记（数据源矩阵「本次使用」）：
    ``fetcher/chain.fetch_with_fallback``（本模块必经，Provider Chain 必经约束）
  - 取哪一类数据（龙虎榜 / 连板梯队）、缓存键与 TTL：本模块编排

报告层消费者：``report/market_sentiment.py``（只做装配，不触取数细节）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import get_ttl
from src.python.providers import hithink

logger = logging.getLogger("invest")

LHB_CACHE_KEY = "sentiment_dragon_tiger"
LADDER_CACHE_KEY = "sentiment_ladder"


def credential_missing() -> str | None:
    """同花顺凭据就绪判定（缺什么、去哪申请，文案由凭据登记点提供）。"""
    return hithink.missing_credential(hithink.SOURCE_ID)


def fetch_dragon_tiger() -> dict[str, Any] | None:
    """龙虎榜数据（带 1 小时缓存；熔断/递补/命中源登记全在 fetch_with_fallback 内）。"""
    from src.python.fetcher.chain import fetch_with_fallback

    return fetch_with_fallback(
        "sentiment",
        {"hithink": (hithink.DISPLAY_NAME, hithink.fetch_dragon_tiger_list)},
        LHB_CACHE_KEY,
        get_ttl("sentiment", LHB_CACHE_KEY),
        fn_kwargs={"board_type": "all"},
    )


def fetch_limit_up_ladder() -> dict[str, Any] | None:
    """连板梯队数据（带 1 小时缓存；链路语义同上）。"""
    from src.python.fetcher.chain import fetch_with_fallback

    return fetch_with_fallback(
        "sentiment",
        {"hithink": (hithink.DISPLAY_NAME, hithink.fetch_limit_up_ladder)},
        LADDER_CACHE_KEY,
        get_ttl("sentiment", LADDER_CACHE_KEY),
    )
