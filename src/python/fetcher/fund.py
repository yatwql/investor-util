"""基金业绩排名、底层持仓、业绩比较基准。

不同数据类型的 Provider Chain 可配置：
  - fund_rank: 天天基金
  - fund_hold: 天天基金
  - 比较基准：API 解析 → 内置知识库 → config.json 用户扩展
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import get_ttl
from src.python.cache import set as cache_set
from src.python.config import get_config
from src.python.fetcher.chain import fetch_with_fallback
from src.python.http_client import make_http_client
from src.python.providers.tiantian_holdings import fetch_fund_holdings
from src.python.providers.tiantian_ranking import fetch_fund_rankings

logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════
#  基金业绩排名
# ═══════════════════════════════════════════════════════════

_FUND_PERF_CACHE_PREFIX = "fund_perf_"

_ProviderFunc = Callable[..., dict[str, Any] | None]

_FUND_RANK_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tiantian": ("天天基金", fetch_fund_rankings),
}


def fetch_fund_rankings(code: str) -> dict[str, Any] | None:
    """获取基金同类排名和区间收益率。

    Provider Chain（可配置）：天天基金
    """
    from src.python.report.data_status import get_tracker

    code = code.strip()
    _t = get_tracker()
    _src_key = f"fund_rank_{code}"
    rank_cache_key = _FUND_PERF_CACHE_PREFIX + code
    result = fetch_with_fallback(
        "fund_rank",
        _FUND_RANK_PROVIDERS,
        rank_cache_key,
        get_ttl("rank", rank_cache_key),
        fn_kwargs={"code": code},
    )
    if result is not None:
        _t.record(_src_key, "T2", success=True)
    else:
        _t.record(_src_key, "T2", success=False, failure_type="unreachable")
    return result


# ═══════════════════════════════════════════════════════════
#  基金底层持仓（穿透深度分析用）
# ═══════════════════════════════════════════════════════════

_FUND_HOLD_CACHE_PREFIX = "fund_hold_"

_FUND_HOLD_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tiantian": ("天天基金", fetch_fund_holdings),
}


def fetch_fund_holdings(code: str) -> dict[str, Any] | None:
    """获取基金前 10 大持仓。

    Provider Chain（可配置）：天天基金
    """
    from src.python.report.data_status import get_tracker

    code = code.strip()
    _t = get_tracker()
    _src_key = f"fund_hold_{code}"
    hold_cache_key = _FUND_HOLD_CACHE_PREFIX + code
    result = fetch_with_fallback(
        "fund_hold",
        _FUND_HOLD_PROVIDERS,
        hold_cache_key,
        get_ttl("hold", hold_cache_key),
        fn_kwargs={"code": code},
    )
    if result is not None:
        _t.record(_src_key, "T2", success=True)
    else:
        _t.record(_src_key, "T2", success=False, failure_type="unreachable")
    return result


def fetch_fund_rankings_cached(code: str) -> dict[str, Any] | None:
    """基金排名获取（含会话缓存），同一报告生成中同基金只获取一次。

    消除 Excel/HTML 双管线间重复的文件缓存读取。
    """
    from src.python.provider_registry import NOT_FOUND, get_registry

    registry = get_registry()
    cached = registry.session_cache_get("fund_rank", code)
    if cached is not NOT_FOUND:
        return cached
    result = fetch_fund_rankings(code)
    registry.session_cache_set("fund_rank", code, result, source="api")
    return result


# ═══════════════════════════════════════════════════════════
#  批量接口
# ═══════════════════════════════════════════════════════════


def fetch_fund_rankings_batch(
    fund_codes: list[str],
    dispatcher: Any = None,
) -> dict[str, dict[str, Any] | None]:
    """批量获取基金排名数据。

    使用 BatchDispatcher 并行获取多只基金排名，按 fund code 返回映射。
    支持传入外部 dispatcher 以便共享线程池；不传时内部创建并自动 shutdown。
    内部使用 fetch_fund_rankings_cached（含 session_cache），
    同报告生成中 Excel/HTML 双管线间消除重复文件 IO。

    Args:
        fund_codes: 基金代码列表。
        dispatcher: 可选外部 BatchDispatcher 实例，None 时内部新建。

    Returns:
        {code: 排名数据 dict} 映射，失败项为 None。
    """
    if not fund_codes:
        return {}

    own = dispatcher is None
    if dispatcher is None:
        from src.python.fetcher.batch import BatchDispatcher, get_batch_worker_count

        dispatcher = BatchDispatcher(
            max_workers=get_batch_worker_count("fund_workers", 3),
            thread_name_prefix="batch_fund_rank",
        )

    from functools import partial

    from src.python.cache import get as cache_get
    from src.python.cache import get_ttl

    items = [
        (
            f"{_FUND_PERF_CACHE_PREFIX}{code}",
            partial(fetch_fund_rankings_cached, code=code),
        )
        for code in fund_codes
    ]

    results = dispatcher.execute_with_cache_check(
        items,
        cache_check_fn=lambda cache_id: cache_get(cache_id, get_ttl("rank", cache_id)),
    )

    rank_map: dict[str, dict[str, Any] | None] = {}
    for code, r in zip(fund_codes, results):
        rank_map[code] = r.result if r.success else None

    if own:
        dispatcher.shutdown()
    return rank_map


def fetch_fund_holdings_batch(
    fund_codes: list[str],
    dispatcher: Any = None,
) -> dict[str, dict[str, Any] | None]:
    """批量获取基金持仓数据。

    使用 BatchDispatcher 并行获取多只基金持仓，按 fund code 返回映射。
    内部使用 fetch_fund_holdings_cached（含 session_cache），同基金跨环节去重。

    Args:
        fund_codes: 基金代码列表。
        dispatcher: 可选外部 BatchDispatcher 实例，None 时内部新建。

    Returns:
        {code: 持仓数据 dict} 映射，失败项为 None。
    """
    if not fund_codes:
        return {}

    own = dispatcher is None
    if dispatcher is None:
        from src.python.fetcher.batch import BatchDispatcher, get_batch_worker_count

        dispatcher = BatchDispatcher(
            max_workers=get_batch_worker_count("fund_workers", 3),
            thread_name_prefix="batch_fund_hold",
        )

    from functools import partial

    from src.python.cache import get as cache_get
    from src.python.cache import get_ttl

    items = [
        (
            f"{_FUND_HOLD_CACHE_PREFIX}{code}",
            partial(fetch_fund_holdings_cached, code=code),
        )
        for code in fund_codes
    ]

    results = dispatcher.execute_with_cache_check(
        items,
        cache_check_fn=lambda cache_id: cache_get(cache_id, get_ttl("hold", cache_id)),
    )

    hold_map: dict[str, dict[str, Any] | None] = {}
    for code, r in zip(fund_codes, results):
        hold_map[code] = r.result if r.success else None

    if own:
        dispatcher.shutdown()
    return hold_map


def fetch_fund_holdings_cached(code: str) -> dict[str, Any] | None:
    """基金持仓获取（含会话缓存），同一报告生成中同基金只获取一次。

    消除多个模块独立调用 fetch_fund_holdings 的冗余文件缓存读取。
    """
    from src.python.provider_registry import NOT_FOUND, get_registry

    registry = get_registry()
    cached = registry.session_cache_get("fund_hold", code)
    if cached is not NOT_FOUND:
        return cached
    result = fetch_fund_holdings(code)
    registry.session_cache_set("fund_hold", code, result, source="api")
    return result


# ═══════════════════════════════════════════════════════════
#  基金业绩比较基准
# ═══════════════════════════════════════════════════════════

_BENCHMARK_TABLE_KEY = "fund_benchmarks"


# ── 第 1 层：API 获取 ──────────────────────────────────


def _fetch_benchmark_from_api(code: str) -> str | None:
    """尝试从东方财富基金页面解析业绩比较基准。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://fund.eastmoney.com/",
    }
    import httpx as _httpx_loc

    urls = [
        f"https://fund.eastmoney.com/{code}.html",
        f"https://fundf10.eastmoney.com/jbgk_{code}.html",
    ]
    for url in urls:
        try:
            with make_http_client(timeout=10, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                resp.encoding = "utf-8"
                html = resp.text
        except (_httpx_loc.RequestError, OSError):
            logger.debug("[基准] %s API 请求失败（url=%s）", code, url)
            continue

        patterns = [
            r"业绩比较基准[：:]\s*([^<\"\n\r]{5,120})",
            r"benchmark[：:]\s*([^<\"\n\r]{5,120})",
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                text = m.group(1).strip()
                if text and len(text) > 5:
                    return text

        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        for script in scripts:
            if "基准" in script:
                bm = re.search(r"基准[：:]\s*([^\"\n\r,]{5,120})", script)
                if bm:
                    return bm.group(1).strip()

    return None


# ── 第 2 层：内置知识库 ────────────────────────────────

_BUILTIN_BENCHMARKS: dict[str, str] = {
    "561910": "中证电池主题指数收益率",
    "159941": "汇率调整后的纳斯达克100指数收益率",
    "159222": "国证自由现金流指数收益率",
    "518880": "国内黄金现货价格收益率",
    "011506": "中证高端装备制造指数75% + 中证全债15% + 中证港股通10%",
    "017730": "MSCI全球指数75% + 沪深30020% + 活期存款5%",
    "022365": "战略性新兴产业成份指数70% + 恒生科技10% + 中债综合20%",
    "016055": "经汇率调整的纳斯达克100指数95% + 活期存款5%",
    "002943": "中证800 65% + 中债全债35%",
    "096001": "标普500等权重指数（全收益指数）",
    "240012": "中国债券总指数收益率100%",
    "012325": "中债综合财富(1年以下)85% + 一年定存15%",
    "040046": "纳斯达克100指数(经汇率)95% + 活期存款5%",
}


# ── 第 3 层：用户配置覆盖 ──────────────────────────────


def _get_full_benchmark_table() -> dict[str, str]:
    """获取完整基准对照表（内置库 + config.json 扩展）。"""
    table = dict(_BUILTIN_BENCHMARKS)
    try:
        config = get_config()
        user_benchmarks = config.get("user_fund_benchmarks") or {}
        table.update(user_benchmarks)
    except (KeyError, TypeError):
        logger.debug("[基准] 获取用户配置覆盖失败，使用内置库")
        pass
    return table


# ── per-code 锁 ─────────────────────────────────────────

_benchmark_locks: dict[str, threading.Lock] = {}
_benchmark_locks_lock = threading.Lock()


def _get_benchmark_lock(code: str) -> threading.Lock:
    with _benchmark_locks_lock:
        if code not in _benchmark_locks:
            _benchmark_locks[code] = threading.Lock()
        return _benchmark_locks[code]


# ── 公开接口 ────────────────────────────────────────────


def fetch_fund_benchmark(code: str) -> str:
    """获取基金业绩比较基准。

    三层策略：API 解析 → 内置知识库 → config.json 用户扩展。
    结果缓存至 fund_benchmarks.json（每月刷新）。

    Args:
        code: 6 位基金代码

    Returns:
        业绩比较基准描述字符串；未找到返回 "--"
    """
    code = code.strip()
    cache_key = _BENCHMARK_TABLE_KEY
    cached = cache_get(cache_key, get_ttl("benchmark", cache_key))
    if cached is not None and isinstance(cached, dict):
        return cached.get(code, "--")

    lock = _get_benchmark_lock(code)
    with lock:
        cached = cache_get(cache_key, get_ttl("benchmark", cache_key))
        if cached is not None and isinstance(cached, dict):
            return cached.get(code, "--")

        table = _get_full_benchmark_table()

        api_result = _fetch_benchmark_from_api(code)
        if api_result:
            table[code] = api_result
            logger.info("[基准] %s API 解析成功: %s", code, api_result)
        elif code in table:
            logger.info("[基准] %s 使用内置知识库", code)
        else:
            logger.warning("[基准] %s 无基准数据", code)

        cache_set(cache_key, table)
        return table.get(code, "--")
