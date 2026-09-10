"""行业分类 / 概念板块数据获取。

Provider Chain（可配置）：
  1. eastmoney_industry — 东方财富 push2（主链路，含概念板块）
  2. eastmoney_industry_rest — 东方财富行情页（备用，纯行业分类）
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.python.cache import clear as cache_clear
from src.python.cache import get as cache_get
from src.python.cache import get_ttl
from src.python.core.code_utils import is_a_share_code
from src.python.fetcher.chain import FailureDiagnostics, fetch_with_fallback, is_provider_chain_broken
from src.python.providers import eastmoney_industry, eastmoney_industry_rest

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
    """东方财富行业原始数据 → 统一行业格式（行业名剥离申万层级后缀）。

    同时**透传**同一次 push2 响应已带出的扩展行情字段（pe/pb/market_cap）。
    这些字段与行业分类来自同一个请求（见 ``_FIELDS``），在此丢弃会让消费方
    只能再发一次同参数请求——即会话缓存要消除的重复取数。
    """
    if not raw:
        return None
    return {
        "code": raw.get("code", ""),
        "industry": strip_hierarchy_suffix(raw.get("industry", "") or ""),
        "industry_id": raw.get("industry_id", ""),
        "concepts": raw.get("concepts", []),
        "concept_ids": raw.get("concept_ids", []),
        "pe": raw.get("pe"),
        "pb": raw.get("pb"),
        "market_cap": raw.get("market_cap"),
    }


def _drop_legacy_cached_payload(cache_key: str) -> None:
    """清除不含扩展行情字段的行业缓存载荷（缓存载荷 schema 迁移）。

    ``_industry_transform`` 透传同一次 push2 响应带出的 pe/pb/market_cap，
    而**缺键载荷不含这三个键**。行业缓存 TTL 为两周，``fetch_with_fallback`` 的
    第一步就是「命中即返回」——不处理的话，缺键载荷会在存活期内被当作有效命中，
    使估值分位与基金风格的 PE 取用静默退化为「不可得」（无异常、无告警）。

    判据取「键是否存在」而非值是否为 None：带键载荷无论 provider 是否给出该字段
    都会带上键（值为 None 表示该源不提供，属正常），只有缺键载荷才清除。

    清除后本次调用即自然回落到 provider 重取，此后写入的即是带键载荷——每个代码
    至多清理一次。待缺键载荷全部过期（≤ 两周）后本函数成为纯字典判定的无害空转。
    """
    cached = cache_get(cache_key, get_ttl("industry", cache_key))
    if isinstance(cached, dict) and "pe" not in cached:
        logger.info("[industry] 清除不含扩展行情字段的缓存载荷，将重新获取: %s", cache_key)
        cache_clear(cache_key)


def fetch_industry_data(code: str) -> dict | None:
    """获取一只证券的行业分类和概念板块归属。

    缓存键: industry_{code}.json
    缓存 TTL: 两周（可通过 cache_ttl.industry 配置）

    Args:
        code: 6 位证券代码

    Returns:
        {code, industry, industry_id, concepts, concept_ids, pe, pb, market_cap}
        失败返回 None
    """
    from src.python.report.data_status import get_tracker

    _t = get_tracker()
    _src_key = f"industry_{code.strip()}"
    industry_cache_key = _INDUSTRY_CACHE_PREFIX + code.strip()
    _drop_legacy_cached_payload(industry_cache_key)
    diag = FailureDiagnostics()
    result = fetch_with_fallback(
        "industry",
        _INDUSTRY_PROVIDERS,
        industry_cache_key,
        get_ttl("industry", industry_cache_key),
        fn_kwargs={"code": code.strip()},
        transform=_industry_transform,
        diagnostics=diag,
    )
    if result is not None:
        # 热缓存命中的旧值可能未经 transform（历史缓存含申万层级后缀），出口统一归一化
        result["industry"] = strip_hierarchy_suffix(result.get("industry") or "")
        _t.record(_src_key, "T3", success=True)
    else:
        _t.record(_src_key, "T3", success=False, failure_type="unreachable", message=diag.summary())
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


def fetch_valuation_fields(code: str) -> dict[str, float | None] | None:
    """获取一只证券的当前 PE/PB（经 Provider Chain + 文件/会话缓存）。

    PE 与市净率是东财 push2 响应中的扩展字段（f9/f23），与行业分类同属一次
    请求——故经行业数据入口取用，而不是绕开 Provider Chain 直连 provider。
    好处：享受链路熔断/降级/诊断与 7 天文件缓存，同一代码同会话不重复取数。

    Args:
        code: 6 位 A 股代码

    Returns:
        {"pe": float|None, "pb": float|None}；数据不可得返回 None。
    """
    data = fetch_industry_data_cached(code)
    if data is None:
        return None
    return {"pe": data.get("pe"), "pb": data.get("pb")}


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

    def _cache_check(cache_id: str) -> Any:
        """缓存命中判据：先剔除缺扩展行情字段的载荷，再按 TTL 读取（见 _drop_legacy_cached_payload）。"""
        _drop_legacy_cached_payload(cache_id)
        return cache_get(cache_id, get_ttl("industry", cache_id))

    results = dispatcher.execute_with_cache_check(
        items,
        cache_check_fn=_cache_check,
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


