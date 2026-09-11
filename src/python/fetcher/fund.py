"""基金业绩排名、底层持仓、业绩比较基准。

不同数据类型的 Provider Chain 可配置：
  - fund_rank: 天天基金
  - fund_hold: 天天基金
  - 比较基准：API 解析 → 内置知识库 → config.json 用户扩展
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import Callable
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import get_ttl
from src.python.cache import set as cache_set
from src.python.config import get_config
from src.python.core.constants import PROJECT_ROOT
from src.python.fetcher.chain import FailureDiagnostics, fetch_with_fallback
from src.python.core.http_client import make_http_client
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
    diag = FailureDiagnostics()
    result = fetch_with_fallback(
        "fund_rank",
        _FUND_RANK_PROVIDERS,
        rank_cache_key,
        get_ttl("rank", rank_cache_key),
        fn_kwargs={"code": code},
        diagnostics=diag,
    )
    if result is not None:
        _t.record(_src_key, "T2", success=True)
    else:
        _t.record(_src_key, "T2", success=False, failure_type="unreachable", message=diag.summary())
    return result


# ═══════════════════════════════════════════════════════════
#  基金底层持仓（穿透深度分析用）
# ═══════════════════════════════════════════════════════════

_FUND_HOLD_CACHE_PREFIX = "fund_hold_"

_FUND_HOLD_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tiantian": ("天天基金", fetch_fund_holdings),
}


def fetch_fund_holdings(code: str) -> dict[str, Any] | None:
    """获取基金底层持仓（联接基金穿透到其目标 ETF）。

    Provider Chain（可配置）：天天基金

    联接基金（ETF 联接/指数联接）的资产就是目标 ETF、本身不持有股票，其季报
    股票表按构造为空。此时 provider 会带回 ``feeder_target_code``，本函数以该
    代码**发起一次独立取数**（走完整链路 + 会话缓存）取其持仓，并在结果上标注
    ``feeder_penetration`` 来源，供报告层说明「底层暴露穿透自目标 ETF」。

    穿透深度恒为 1：只有名称含「联接」的基金才带回目标 ETF，而 ETF 名称不含
    「联接」，故第二跳的结果不会再生出新的目标。第二跳失败时原样返回该基金的
    自身结果（通常为空），由既有「持仓不可用」路径降级。
    """
    from src.python.report.data_status import get_tracker

    code = code.strip()
    _t = get_tracker()
    _src_key = f"fund_hold_{code}"
    hold_cache_key = _FUND_HOLD_CACHE_PREFIX + code
    diag = FailureDiagnostics()
    result = fetch_with_fallback(
        "fund_hold",
        _FUND_HOLD_PROVIDERS,
        hold_cache_key,
        get_ttl("hold", hold_cache_key),
        fn_kwargs={"code": code},
        diagnostics=diag,
    )
    if result is not None:
        _t.record(_src_key, "T2", success=True)
    else:
        _t.record(_src_key, "T2", success=False, failure_type="unreachable", message=diag.summary())

    return with_feeder_penetration(code, result)


def with_feeder_penetration(code: str, result: dict[str, Any] | None) -> dict[str, Any] | None:
    """联接基金穿透：以目标 ETF 的持仓代理该基金的底层暴露（**幂等**）。

    目标 ETF 经 :func:`fetch_fund_holdings_cached` 取数——与任何基金走同一条
    链路与会话缓存。若用户同时持有该目标 ETF，同一会话内其持仓只请求一次。

    **为何是幂等的后处理而非链路内一步**：批量的缓存预检（``execute_with_cache_check``）
    命中文件缓存时会直接返回缓存值、**不执行任务**，因此单条取数路径上的穿透
    在缓存热时不会被触发。凡「从缓存或网络产出持仓」之处都须过一遍本函数；
    已带 ``feeder_penetration`` 的结果原样返回，重复调用无副作用。

    Args:
        code: 基金代码
        result: 取数结果（可为 None）

    Returns:
        穿透后的合并结果；非联接基金、开关关闭或目标 ETF 亦不可得时原样返回 result。
    """
    if not result or result.get("feeder_penetration"):
        return result
    target_code = result.get("feeder_target_code")
    if not target_code:
        return result

    from src.python.config.features import is_feature_enabled

    if not is_feature_enabled("feeder_penetration"):
        logger.info("基金 %s 为联接基金，但 switch feeder_penetration 已关闭，不穿透目标 ETF %s", code, target_code)
        return result

    target = fetch_fund_holdings_cached(target_code)
    if not target or not target.get("holdings"):
        logger.warning("[穿透] 联接基金 %s 的目标 ETF %s 亦无持仓数据，维持原结果", code, target_code)
        return result

    logger.info(
        "[穿透] 联接基金 %s 的底层资产穿透自目标 ETF %s（%s），报告期 %s",
        code,
        target_code,
        target.get("name") or "未知",
        target.get("date") or "未知",
    )
    return {
        **target,
        "code": code,
        "name": result.get("name") or target.get("name", ""),
        "feeder_penetration": {
            "target_code": target_code,
            "target_name": target.get("name", ""),
        },
    }


def fetch_fund_rankings_cached(code: str) -> dict[str, Any] | None:
    """基金排名获取（含会话缓存），同一报告生成中同基金只获取一次。

    消除 Excel/HTML 双管线间重复的文件缓存读取。
    """
    from src.python.core.provider_registry import NOT_FOUND, get_registry

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
            rate_limit_provider="tiantian",
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
            rate_limit_provider="tiantian",
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
        # 缓存预检命中时任务未执行，穿透须在此补做（幂等，未命中项为无操作）
        hold_map[code] = with_feeder_penetration(code, r.result if r.success else None)

    if own:
        dispatcher.shutdown()
    return hold_map


def fetch_fund_holdings_cached(code: str) -> dict[str, Any] | None:
    """基金持仓获取（含会话缓存），同一报告生成中同基金只获取一次。

    消除多个模块独立调用 fetch_fund_holdings 的冗余文件缓存读取。
    """
    from src.python.core.provider_registry import NOT_FOUND, get_registry

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

_BENCHMARKS_FILE = os.path.join(PROJECT_ROOT, "data/knowledge/fund_benchmarks.json")


def _load_builtin_benchmarks() -> dict[str, str]:
    """从 fund_benchmarks.json 加载内置基金基准对照表。"""
    if not os.path.exists(_BENCHMARKS_FILE):
        logger.warning("[基准] 内置基准文件 %s 不存在，使用空表", _BENCHMARKS_FILE)
        return {}
    try:
        with open(_BENCHMARKS_FILE, encoding="utf-8") as f:
            data: dict[str, str] = json.load(f)
        logger.info("[基准] 已加载 %d 条内置基准对照", len(data))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[基准] 加载内置基准文件失败: %s，使用空表", e)
        return {}


_BUILTIN_BENCHMARKS: dict[str, str] = _load_builtin_benchmarks()


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
