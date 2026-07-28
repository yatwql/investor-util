"""行业分类 / 概念板块数据获取。

Provider Chain（可配置）：
  1. eastmoney_industry — 东方财富 push2（主链路，含概念板块）
  2. eastmoney_industry_rest — 东方财富行情页（备用，纯行业分类）
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import get_ttl
from src.python.code_utils import is_a_share_code
from src.python.fetcher.chain import fetch_with_fallback, is_provider_chain_broken
from src.python.providers import eastmoney_industry, eastmoney_industry_rest
from src.python.providers.eastmoney_industry import make_push2_request as _make_push2_request

logger = logging.getLogger("invest")


_INDUSTRY_CACHE_PREFIX = "industry_"

_INDUSTRY_PROVIDERS: dict[str, tuple[str, Any]] = {
    "eastmoney_industry": ("东方财富行业", eastmoney_industry.fetch_industry_and_concepts),
    "eastmoney_industry_rest": ("东方财富行业(行情页)", eastmoney_industry_rest.fetch_industry_and_concepts),
}

# 批量获取失败重试：重试等待基秒数 + 随机抖动
_BATCH_RETRY_DELAY = 0.8
_BATCH_RETRY_JITTER = 0.4


def _industry_transform(raw: dict, _source: str) -> dict | None:
    """东方财富行业原始数据 → 统一行业格式。"""
    if not raw:
        return None
    return {
        "code": raw.get("code", ""),
        "industry": raw.get("industry", ""),
        "industry_id": raw.get("industry_id", ""),
        "concepts": raw.get("concepts", []),
        "concept_ids": raw.get("concept_ids", []),
    }


def fetch_industry_data(code: str) -> dict | None:
    """获取一只证券的行业分类和概念板块归属。

    缓存键: industry_{code}.json
    缓存 TTL: 7 天（可通过 cache_ttl.industry 配置）

    Args:
        code: 6 位证券代码

    Returns:
        {code, industry, industry_id, concepts, concept_ids}
        失败返回 None
    """
    from src.python.report.data_status import get_tracker

    _t = get_tracker()
    _src_key = f"industry_{code.strip()}"
    industry_cache_key = _INDUSTRY_CACHE_PREFIX + code.strip()
    result = fetch_with_fallback(
        "industry",
        _INDUSTRY_PROVIDERS,
        industry_cache_key,
        get_ttl("industry", industry_cache_key),
        fn_kwargs={"code": code.strip()},
        transform=_industry_transform,
    )
    if result is not None:
        _t.record(_src_key, "T3", success=True)
    else:
        _t.record(_src_key, "T3", success=False, failure_type="unreachable")
    return result


def _is_a_share_code(code: str) -> bool:
    """判断是否为 A 股代码（委托至 code_utils.is_a_share_code）。"""
    return is_a_share_code(code)


def batch_fetch_industry_data(codes: list[str], max_workers: int = 8) -> dict[str, dict]:
    """批量获取多只证券的行业分类和概念板块归属。

    使用 BatchDispatcher 统一并行调度，支持缓存优先、熔断预检、通用重试。
    非 A 股代码（美股/港股等）自动跳过，不调用 API。

    Args:
        codes: 6 位证券代码列表
        max_workers: 最大并发线程数（默认 8）

    Returns:
        {code: {code, industry, concepts, ...}, ...}
    """
    valid_codes = [c.strip() for c in codes if c and c.strip()]
    if not valid_codes:
        return {}

    # 过滤非 A 股代码，避免无效 API 调用
    a_codes = [c for c in valid_codes if _is_a_share_code(c)]
    skipped = len(valid_codes) - len(a_codes)
    if skipped:
        logger.debug("跳过 %d 个非 A 股代码（行业数据仅支持 A 股）", skipped)

    if not a_codes:
        return {}

    # 熔断预检：全链已熔断时跳过批量请求，避免逐条冗余调用
    if is_provider_chain_broken("industry"):
        logger.warning("[industry] 行业数据 API 全链不可用（熔断），跳过 %d 个代码的批量获取", len(a_codes))
        return {}

    from functools import partial

    from src.python.cache import get as cache_get
    from src.python.fetcher.batch import BatchDispatcher, get_batch_worker_count

    dispatcher = BatchDispatcher(
        max_workers=get_batch_worker_count("industry_workers", 8),
        thread_name_prefix="batch_industry",
    )

    items = [
        (
            f"{_INDUSTRY_CACHE_PREFIX}{code}",
            partial(fetch_industry_data, code=code),
        )
        for code in a_codes
    ]

    results = dispatcher.execute_with_cache_check(
        items,
        cache_check_fn=lambda cache_id: cache_get(cache_id, get_ttl("industry", cache_id)),
        strict_none=True,
    )

    # 通用重试（复用主 executor）
    results = dispatcher.retry_failed(
        results,
        task_factory=lambda idx: partial(fetch_industry_data, code=a_codes[idx]),
        delay=_BATCH_RETRY_DELAY,
        jitter=_BATCH_RETRY_JITTER,
    )

    result_map: dict[str, dict] = {}
    for code, r in zip(a_codes, results):
        if r.success and r.result:
            result_map[code] = r.result

    dispatcher.shutdown()
    logger.info("批量行业数据就绪: %d/%d 个代码（含缓存命中）", len(result_map), len(a_codes))
    return result_map


def make_push2_request(code: str, retries: int = 3) -> dict | None:
    """执行东方财富 push2 API 请求，返回扩展行情数据。

    委托给 ``providers.eastmoney_industry.make_push2_request``。

    Args:
        code: 6 位 A 股代码
        retries: 重试次数

    Returns:
        {"f20": market_cap, "f9": pe, "f23": pb, ...} 或 None
    """
    return _make_push2_request(code, retries=retries)
