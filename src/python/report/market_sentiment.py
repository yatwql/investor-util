"""市场情绪与资金热点 —— 报告层取数与装配（开关 ``market_sentiment``，默认关）。

链路：同花顺官方（龙虎榜 + 连板梯队）→ ``analysis/market_sentiment.py`` 纯装配（只保留命中
持仓/穿透标的的事件行）→ 数据契约 ``market_sentiment_data``。

降级与闸门：
  - 功能开关关闭 → 返回 ``None``（章节隐藏，零网络开销）
  - 缺凭据 / 两源皆不可用 / 无标的命中 → ``available=False`` 的降级契约（写占位，不阻断主链路）
  - 取数带 1 小时缓存（``sentiment_lhb`` / ``sentiment_ladder``，随菜单刷新与 TTL 管理）
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis.market_sentiment import build_market_sentiment, tracked_targets
from src.python.cache import get as cache_get
from src.python.cache import get_ttl
from src.python.cache import set as cache_set
from src.python.providers import hithink

logger = logging.getLogger("invest")

_LHB_CACHE_KEY = "sentiment_dragon_tiger"
_LADDER_CACHE_KEY = "sentiment_ladder"


def build_market_sentiment_data(
    holdings: list,
    penetrated_assets: list | None,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """装配市场情绪契约（开关关闭返回 ``None``）。"""
    from src.python.config import is_enable_market_sentiment

    if not is_enable_market_sentiment(config):
        return None
    if hithink.missing_credential(hithink.SOURCE_ID) is not None:
        return {
            "available": False,
            "reason": "未配置同花顺 API key（详见数据源可用性矩阵）",
            "trade_date": "",
            "summary": {},
            "rows": [],
            "failures": [],
            "entry_count": 0,
        }

    dragon_tiger = _fetch_cached(_LHB_CACHE_KEY, lambda: hithink.fetch_dragon_tiger_list("all"))
    ladder = _fetch_cached(_LADDER_CACHE_KEY, hithink.fetch_limit_up_ladder)
    if dragon_tiger or ladder:
        from src.python.report.data_status import mark_data_used

        mark_data_used("sentiment")

    contract = build_market_sentiment(dragon_tiger, ladder, tracked_targets(holdings, penetrated_assets))
    logger.info(
        "[market_sentiment] 命中 %d 条（龙虎榜/连板梯队 ∩ 持仓与穿透），交易日 %s",
        contract["entry_count"],
        contract["trade_date"] or "未知",
    )
    return contract


def _fetch_cached(cache_key: str, fetch_fn: Any) -> dict[str, Any] | None:
    """取数并缓存（1 小时 TTL；命中缓存直接返回，不记降级）。"""
    cached = cache_get(cache_key, get_ttl("sentiment", cache_key))
    if isinstance(cached, dict):
        return cached
    data = fetch_fn()
    if isinstance(data, dict):
        cache_set(cache_key, data)
    return data


__all__ = ["build_market_sentiment_data"]
