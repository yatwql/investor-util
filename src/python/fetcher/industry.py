"""行业分类 / 概念板块数据获取。

Provider Chain（可配置）：
  1. eastmoney_industry — 东方财富 push2（主链路，含概念板块）
  2. eastmoney_industry_rest — 东方财富行情页（备用，纯行业分类）
"""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def batch_fetch_industry_data(codes: list[str], max_workers: int = 3) -> dict[str, dict]:
    """批量获取多只证券的行业分类和概念板块归属。

    使用线程池并发获取，已缓存的不重复请求。
    非 A 股代码（美股/港股等）自动跳过，不调用 API。

    Args:
        codes: 6 位证券代码列表
        max_workers: 最大并发线程数

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

    result: dict[str, dict] = {}
    lock = threading.Lock()

    def _fetch_one(code: str) -> tuple[str, dict] | None:
        data = fetch_industry_data(code)
        if data:
            return code, data
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, code): code for code in a_codes}
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

    # 首次获取失败的代码，短暂等幅后重试一次
    failed = [c for c in a_codes if c not in result]
    if failed:
        # 重试预检：如熔断未恢复则跳过重试，避免无效等待
        if is_provider_chain_broken("industry"):
            logger.info("[industry] 行业数据全链熔断未恢复，跳过 %d 个失败代码重试", len(failed))
        else:
            delay = _BATCH_RETRY_DELAY + random.uniform(0, _BATCH_RETRY_JITTER)
            logger.info("批量行业数据重试 %d 个失败代码（%.1fs 后）", len(failed), delay)
            time.sleep(delay)
            with ThreadPoolExecutor(max_workers=min(max_workers, len(failed))) as executor:
                futures = {executor.submit(_fetch_one, code): code for code in failed}
                for future in as_completed(futures):
                    try:
                        res = future.result()
                    except Exception:
                        _failed_code = futures[future]
                        logger.warning("[industry] 重试批量 %s 仍失败", _failed_code, exc_info=True)
                        continue
                    if res is not None:
                        code, data = res
                        with lock:
                            result[code] = data

    logger.info("批量行业数据就绪: %d/%d 个代码（含缓存命中）", len(result), len(a_codes))
    return result


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
