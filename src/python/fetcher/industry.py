"""行业分类 / 概念板块数据获取。

Provider Chain（可配置）：东方财富 push2
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.cache import CACHE_WEEKLY
from src.python.fetcher.chain import _fetch_with_fallback
from src.python.providers import eastmoney_industry

logger = logging.getLogger("invest")


_INDUSTRY_CACHE_PREFIX = "industry_"

_INDUSTRY_PROVIDERS: dict[str, tuple[str, Any]] = {
    "eastmoney_industry": ("东方财富行业", eastmoney_industry.fetch_industry_and_concepts),
}


def _industry_transform(raw: dict, source: str) -> dict | None:
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
    return _fetch_with_fallback(
        "industry",
        _INDUSTRY_PROVIDERS,
        _INDUSTRY_CACHE_PREFIX + code.strip(),
        CACHE_WEEKLY,
        fn_kwargs={"code": code.strip()},
        transform=_industry_transform,
    )


def batch_fetch_industry_data(codes: list[str], max_workers: int = 5) -> dict[str, dict]:
    """批量获取多只证券的行业分类和概念板块归属。

    使用线程池并发获取，已缓存的不重复请求。

    Args:
        codes: 6 位证券代码列表
        max_workers: 最大并发线程数

    Returns:
        {code: {code, industry, concepts, ...}, ...}
    """
    valid_codes = [c.strip() for c in codes if c and c.strip()]
    if not valid_codes:
        return {}

    result: dict[str, dict] = {}
    lock = threading.Lock()

    def _fetch_one(code: str) -> tuple[str, dict] | None:
        data = fetch_industry_data(code)
        if data:
            return code, data
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, code): code for code in valid_codes}
        for future in as_completed(futures):
            try:
                res = future.result()
            except Exception as exc:
                logger.warning("批量行业数据获取异常: %s", exc)
                continue
            if res is not None:
                code, data = res
                with lock:
                    result[code] = data

    logger.info("批量行业数据获取完成: 共 %d 个代码, 成功 %d 个",
                len(valid_codes), len(result))
    return result
