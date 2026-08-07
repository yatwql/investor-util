"""行业分类 / 概念板块数据获取。

Provider Chain（可配置）：
  1. eastmoney_industry — 东方财富 push2（主链路，含概念板块）
  2. eastmoney_industry_rest — 东方财富行情页（备用，纯行业分类）
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.python.cache import get_ttl
from src.python.core.code_utils import is_a_share_code
from src.python.fetcher.chain import fetch_with_fallback, is_provider_chain_broken
from src.python.providers import eastmoney_industry, eastmoney_industry_rest
from src.python.providers.eastmoney_industry import make_push2_request as _make_push2_request

logger = logging.getLogger("invest")

# 申万行业层级后缀：行业名末尾的 Ⅰ/Ⅱ/Ⅲ/Ⅳ（如「银行Ⅱ」「白酒Ⅱ」）是申万分层命名标记
# （层级与上级/同名行业区分），对零售报告是纯展示噪音。统一在网关剥离，消费方见干净名。
_HIERARCHY_SUFFIX_RE = re.compile(r"[ⅠⅡⅢⅣ]+$")


_INDUSTRY_CACHE_PREFIX = "industry_"

_INDUSTRY_PROVIDERS: dict[str, tuple[str, Any]] = {
    "eastmoney_industry": ("东方财富行业", eastmoney_industry.fetch_industry_and_concepts),
    "eastmoney_industry_rest": ("东方财富行业(行情页)", eastmoney_industry_rest.fetch_industry_and_concepts),
}

# 批量获取失败重试：重试等待基秒数 + 随机抖动
_BATCH_RETRY_DELAY = 0.8
_BATCH_RETRY_JITTER = 0.4


def strip_hierarchy_suffix(name: str) -> str:
    """剥离行业名末尾的申万层级后缀（Ⅰ/Ⅱ/Ⅲ/Ⅳ）。

    东方财富 f127 / bk_name 返回申万行业名带层级标记（如「银行Ⅱ」「白酒Ⅱ」——
    申万用 Ⅰ/Ⅱ/Ⅲ 区分同级同名行业与上级层级）。对零售报告读者，该后缀是纯
    层级噪音，展示时统一剥离（「银行Ⅱ」→「银行」）；无后缀或空串原样返回。

    Args:
        name: 原始行业名（如 "银行Ⅱ"）

    Returns:
        剥离层级后缀后的行业名（如 "银行"）
    """
    if not name:
        return name
    return _HIERARCHY_SUFFIX_RE.sub("", name)


def _industry_transform(raw: dict, _source: str) -> dict | None:
    """东方财富行业原始数据 → 统一行业格式（行业名剥离申万层级后缀）。"""
    if not raw:
        return None
    return {
        "code": raw.get("code", ""),
        "industry": strip_hierarchy_suffix(raw.get("industry", "") or ""),
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
        # 热缓存命中的旧值可能未经 transform（历史缓存含申万层级后缀），出口统一归一化
        result["industry"] = strip_hierarchy_suffix(result.get("industry") or "")
        _t.record(_src_key, "T3", success=True)
    else:
        _t.record(_src_key, "T3", success=False, failure_type="unreachable")
    return result


def fetch_industry_data_cached(code: str) -> dict | None:
    """行业数据获取（含会话缓存），同一报告生成中同证券只获取一次。

    消除多个模块独立调用 fetch_industry_data 的冗余文件缓存读取。
    """
    from src.python.core.provider_registry import NOT_FOUND, get_registry

    registry = get_registry()
    cached = registry.session_cache_get("industry", code)
    if cached is not NOT_FOUND:
        return cached
    result = fetch_industry_data(code)
    if result is not None:
        registry.session_cache_set("industry", code, result, source="api")
    return result


def batch_fetch_industry_data(codes: list[str]) -> dict[str, dict]:
    """批量获取多只证券的行业分类和概念板块归属。

    使用 BatchDispatcher 统一并行调度，支持缓存优先、熔断预检、通用重试。
    非 A 股代码（美股/港股等）自动跳过，不调用 API。
    并发数由配置 `industry_workers` 控制（见 get_batch_worker_count）。

    Args:
        codes: 6 位证券代码列表

    Returns:
        {code: {code, industry, concepts, ...}, ...}
    """
    valid_codes = [c.strip() for c in codes if c and c.strip()]
    if not valid_codes:
        return {}

    # 过滤非 A 股代码，避免无效 API 调用
    a_codes = [c for c in valid_codes if is_a_share_code(c)]
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
        rate_limit_provider="eastmoney_industry",
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
            # 缓存命中路径绕过 fetch_industry_data 出口归一化，组装时兜底剥离层级后缀
            r.result["industry"] = strip_hierarchy_suffix(r.result.get("industry") or "")
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
