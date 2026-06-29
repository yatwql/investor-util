"""数据获取路由 — 基于 Provider Chain 的自动/手动备用链路切换。

架构：
  每类数据（price/index/rank/holding）对应一个 Provider Chain，
  chain 中按优先级列出 provider，主链路失败后自动递补。
  用户可通过 config.json 的 preferred_provider 手动指定首选链路。

Provider Chain DSL:
  {
    "price": ["tencent", "eastmoney"],  # 先腾讯 → 失败自动切东方财富
    "index": ["tencent", "sina"],
    "fund_rank": ["tiantian"],
    "fund_hold": ["tiantian"],
  }

缓存频率说明（秒）：
  - CACHE_DAILY(86400):   价格/净值、基金业绩
  - CACHE_WEEKLY(604800): 基金底层持仓
"""

from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from src.python.cache import CACHE_DAILY, CACHE_WEEKLY, get as cache_get, get_ttl, set as cache_set
from src.python.config import get_config
from src.python.providers import eastmoney, eastmoney_industry, sina, tencent, tiantian

logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════
#  Provider Chain 定义
# ═══════════════════════════════════════════════════════════

# 每个数据类型的 Provider Chain（按优先级排列）
# 可通过 config.json 的 preferred_provider 手动覆盖首选
_DEFAULT_CHAINS: dict[str, list[str]] = {
    "price": ["tencent", "eastmoney"],
    "index": ["tencent", "sina"],
    "us_index": ["sina"],
    "fund_rank": ["tiantian"],
    "fund_hold": ["tiantian"],
}


def _get_chain(data_type: str) -> list[str]:
    """获取指定数据类型的 Provider Chain（考虑用户配置）。

    用户可在 config.json 中通过 preferred_provider.<data_type> 指定首选：
    {"preferred_provider": {"price": "eastmoney", ...}}

    如果指定了有效的首选 provider，将其提到 chain 第一位。
    """
    chain = list(_DEFAULT_CHAINS.get(data_type, []))
    try:
        config = get_config()
        preferred = (config.get("preferred_provider") or {}).get(data_type)
        if preferred and preferred in chain and chain[0] != preferred:
            chain.remove(preferred)
            chain.insert(0, preferred)
            logger.info("%s Provider Chain: 根据配置首选 '%s'", data_type, preferred)
    except Exception:
        pass
    return chain


# ═══════════════════════════════════════════════════════════
#  Provider 注册表
# ═══════════════════════════════════════════════════════════

# 每个 provider 对应一个 ("来源标签", fetch_function)
# fetch_function(code, **kwargs) → dict | None
_ProviderFunc = Callable[..., dict[str, Any] | None]

_PROVIDER_REGISTRY: dict[str, tuple[str, _ProviderFunc]] = {
    "tencent": ("腾讯财经", tencent.fetch_price),
    "eastmoney": ("东方财富", eastmoney.fetch_nav),
    "sina": ("新浪财经", sina.fetch_us_indices),
    "tiantian": ("天天基金", tiantian.fetch_fund_rankings),
}


# ═══════════════════════════════════════════════════════════
#  通用带缓存的 Fallback 调用
# ═══════════════════════════════════════════════════════════


def _fetch_with_fallback(
    data_type: str,
    provider_fn_map: dict[str, tuple[str, _ProviderFunc]],
    cache_key: str,
    cache_ttl: float,
    fn_kwargs: dict[str, Any] | None = None,
    transform: Callable[[dict[str, Any], str], dict[str, Any] | None] | None = None,
) -> dict[str, Any] | None:
    """通用 Fallback 获取器。

    对于指定数据类型，依次尝试 chain 中的每个 provider，
    第一个成功的返回结果，全部失败返回 None。

    Args:
        data_type: 数据类型（用于 chain 查找和日志）
        provider_fn_map: provider_name → (source_label, fetch_fn)
        cache_key: 缓存键
        cache_ttl: 缓存 TTL（秒）
        fn_kwargs: 传给 fetch_fn 的额外参数
        transform: 将 provider 原始结果转为统一输出格式
                   (raw_result, source_label) → unified_dict | None

    Returns:
        unified dict 或 None
    """
    chain = _get_chain(data_type)

    # 1) 读缓存
    cached = cache_get(cache_key, cache_ttl)
    if cached is not None:
        logger.debug("缓存命中: %s", cache_key)
        return cached

    # 2) 遍历 chain 尝试
    kwargs = fn_kwargs or {}
    for provider_name in chain:
        entry = provider_fn_map.get(provider_name)
        if not entry:
            logger.warning("[%s] 未知 Provider '%s'，跳过", data_type, provider_name)
            continue

        source_label, fetch_fn = entry
        logger.info("[%s] 尝试 %s (%s)", data_type, source_label, provider_name)

        try:
            raw = fetch_fn(**kwargs)
        except Exception as e:
            logger.warning("[%s] %s 调用异常: %s", data_type, provider_name, e)
            continue

        if raw is None:
            logger.info("[%s] %s 返回空，尝试下一链路", data_type, provider_name)
            continue

        # 应用数据转换
        if transform:
            try:
                result = transform(raw, source_label)
            except Exception as e:
                logger.warning("[%s] %s 数据转换失败: %s", data_type, provider_name, e)
                continue
        else:
            result = raw

        if result is not None:
            logger.info("[%s] %s 成功", data_type, provider_name)
            cache_set(cache_key, result)
            return result

    # 降级：全部 Provider 失败时尝试过期缓存
    stale = cache_get(cache_key, CACHE_WEEKLY)
    if stale is not None:
        logger.info("[%s] 全部 Provider 不可用，降级使用过期缓存", data_type)
        return stale

    return None


# ═══════════════════════════════════════════════════════════
#  市场行情数据（场内/场外价格）
# ═══════════════════════════════════════════════════════════


def _name_matches(a: str, b: str) -> bool:
    """判断两个证券名称是否指向同一标的。

    Tencent 命名格式与持仓文件可能不同（"电池ETF招商" VS "招商中证电池主题ETF"）。
    用核心汉字重叠率替代精确字符串比较。
    """
    a = a.strip()
    b = b.strip()
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return True
    a_chars = set(re.findall(r"[一-鿿]", a))
    b_chars = set(re.findall(r"[一-鿿]", b))
    if not a_chars or not b_chars:
        return False
    overlap = len(a_chars & b_chars) / min(len(a_chars), len(b_chars))
    return overlap >= 0.7


def _price_cache_key(code: str) -> str:
    return f"price_{code}"


def _index_cache_key(code: str) -> str:
    return f"index_{code}"


# Price Provider 映射（带名称比对逻辑）
_PRICE_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tencent": ("腾讯财经", tencent.fetch_price),
    "eastmoney": ("东方财富", eastmoney.fetch_nav),
}


def _price_transform_tencent(raw: dict, source: str) -> dict | None:
    """腾讯财经原始数据 → 统一价格格式。"""
    return {
        "name": raw.get("name", ""),
        "code": raw.get("code", ""),
        "price": raw.get("price", 0.0),
        "yesterday_close": raw.get("yesterday_close", 0.0),
        "price_date": raw.get("price_date", ""),
        "source_api": "tencent",
        "source": source,
    }


def _price_transform_eastmoney(raw: dict, source: str) -> dict | None:
    """东方财富原始数据 → 统一价格格式。"""
    nav = raw.get("nav", 0.0)
    if nav <= 0:
        return None
    return {
        "name": raw.get("name", ""),
        "code": raw.get("code", ""),
        "price": nav,
        "yesterday_close": raw.get("yesterday_nav", 0.0),
        "price_date": raw.get("nav_date", ""),
        "source_api": "eastmoney",
        "source": source,
    }


_PRICE_TRANSFORMS: dict[str, Callable] = {
    "tencent": _price_transform_tencent,
    "eastmoney": _price_transform_eastmoney,
}


def fetch_market_data(code: str, expected_name: str = "") -> dict[str, Any] | None:
    """获取一只证券的市场行情（含自动/手动备用链路切换）。

    Provider Chain（可配置）：腾讯财经 → 东方财富

    Args:
        code: 6 位证券代码
        expected_name: 持仓名称（用于代码重叠识别，如 002943 既是股票也是基金）

    Returns:
        {name, code, price, yesterday_close, price_date, source_api, source}
        None: 全部接口失败
    """
    code = code.strip()
    cache_key = _price_cache_key(code)

    # 1) 读缓存（TTL 从 config.json cache_ttl.price 读取，可配置）
    cached = cache_get(cache_key, get_ttl("price"))
    if cached is not None:
        logger.debug("行情缓存命中: %s", code)
        return cached

    # 2) 遍历 Provider Chain
    chain = _get_chain("price")

    for provider_name in chain:
        entry = _PRICE_PROVIDERS.get(provider_name)
        if not entry:
            continue

        source_label, fetch_fn = entry
        transform = _PRICE_TRANSFORMS.get(provider_name)
        logger.info("[价格] %s 尝试 %s (%s)", code, source_label, provider_name)

        try:
            raw = fetch_fn(code)
        except Exception as e:
            logger.warning("[价格] %s (%s): %s", provider_name, code, e)
            continue

        if raw is None or not raw.get("name" if provider_name == "tencent" else "nav"):
            logger.info("[价格] %s (%s) 返回空", provider_name, code)
            continue

        # 名称比对（仅 Tencent 需要，因为可能代码重叠）
        if provider_name == "tencent":
            tencent_name = raw.get("name", "").strip()
            if expected_name and tencent_name and not _name_matches(tencent_name, expected_name):
                logger.info("[价格] %s 名称不匹配 '%s' vs '%s'，尝试下一链路",
                           code, tencent_name, expected_name)
                continue

        # 转换并返回
        if transform:
            out = transform(raw, source_label)
            if out:
                cache_set(cache_key, out)
                return out

    # 降级：全部 Provider 失败时尝试过期缓存
    stale = cache_get(cache_key, CACHE_WEEKLY)
    if stale is not None:
        logger.info("[价格] %s 全部 Provider 不可用，降级使用过期缓存", code)
        return stale

    return None


# ═══════════════════════════════════════════════════════════
#  A 股指数
# ═══════════════════════════════════════════════════════════

_A_INDICES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sh000300": "沪深300",
    "sh000688": "科创板50",
    "sz399006": "创业板指",
}


def fetch_indices() -> dict[str, dict[str, Any]]:
    """获取 A 股主要指数行情。Provider: 腾讯财经

    Note: 新浪备用链路尚未实现 A 股指数接口
    """
    indices: dict[str, dict[str, Any]] = {}

    # 先行收集已缓存的指数
    uncached_codes: list[str] = []
    for index_code in _A_INDICES:
        cache_key = _index_cache_key(index_code)
        cached = cache_get(cache_key, CACHE_DAILY)
        if cached is not None:
            indices[index_code] = cached
        else:
            uncached_codes.append(index_code)

    if not uncached_codes:
        return indices

    def _fetch_one(index_code: str) -> tuple[str, dict] | None:
        index_name = _A_INDICES[index_code]
        # Chain: 腾讯主导（新浪备用链路尚未实现 A 股指数接口）
        result = tencent.fetch_price(index_code)
        if result and result.get("price", 0) > 0:
            price = result.get("price", 0.0)
            yclose = result.get("yesterday_close", 0.0)
            change = round(price - yclose, 2)
            change_pct = round(change / yclose * 100, 2) if yclose > 0 else 0.0

            data = {
                "name": result.get("name", index_name),
                "code": index_code,
                "price": price,
                "yesterday_close": yclose,
                "price_date": result.get("price_date", ""),
                "change": change,
                "change_pct": change_pct,
            }
            cache_set(_index_cache_key(index_code), data)
            return index_code, data
        else:
            # 降级：尝试过期缓存
            stale = cache_get(_index_cache_key(index_code), CACHE_WEEKLY)
            if stale is not None:
                return index_code, stale
        return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_one, code): code for code in uncached_codes}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                code, data = result
                indices[code] = data

    return indices


# ═══════════════════════════════════════════════════════════
#  美股指数
# ═══════════════════════════════════════════════════════════

_US_INDEX_CODES = {
    "gb_dji": "道琼斯",
    "gb_ixic": "纳斯达克",
    "gb_inx": "标普500",
}


def fetch_us_indices() -> dict[str, dict[str, Any]]:
    """获取美股三大指数行情（Provider Chain: 新浪，带重试和缓存降级）。

    策略：
      1. 优先读缓存（24h TTL）
      2. 缓存缺失/过期 → 调新浪 API（最多重试 2 次）
      3. API 全部失败 → 降级接受过期缓存（7 天内有效）
      4. 全部失败 → 返回空字典

    Returns:
        {code: {name, price, yesterday_close, price_date, change, change_pct}}
    """
    indices: dict[str, dict[str, Any]] = {}
    expired_cached: dict[str, dict[str, Any]] = {}

    for code in _US_INDEX_CODES:
        cache_key = _index_cache_key(code)
        # 尝试正常缓存
        cached = cache_get(cache_key, CACHE_DAILY)
        if cached is not None:
            indices[code] = cached
        else:
            # 尝试过期缓存（7天内有效）
            stale = cache_get(cache_key, 604800)
            if stale is not None:
                expired_cached[code] = stale

    if len(indices) == len(_US_INDEX_CODES):
        return indices

    # 调新浪 API（带重试）
    import time as _time
    for attempt in range(2):
        try:
            sina_data = sina.fetch_us_indices()
            if sina_data:
                for code, data in sina_data.items():
                    cache_set(_index_cache_key(code), data)
                    indices[code] = data
                return indices
        except Exception as e:
            logger.warning("美股指数 API 请求失败（第 %d 次）: %s", attempt + 1, e)
            if attempt == 0:
                _time.sleep(1)
        else:
            break

    # API 全部失败 → 降级使用过期缓存
    if expired_cached:
        logger.info("美股指数 API 不可用，使用过期缓存数据")
        for code, data in expired_cached.items():
            indices[code] = data
            # 刷新过期缓存的时间戳，避免每次请求都调 API
            cache_set(_index_cache_key(code), data)
            logger.info("美股指数 %s 降级为缓存数据", code)
    else:
        logger.warning("美股指数全部获取失败（API + 缓存均无数据）")

    return indices


# ═══════════════════════════════════════════════════════════
#  基金业绩排名
# ═══════════════════════════════════════════════════════════

_FUND_PERF_CACHE_PREFIX = "fund_perf_"

_FUND_RANK_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tiantian": ("天天基金", tiantian.fetch_fund_rankings),
}


def fetch_fund_rankings(code: str) -> dict[str, Any] | None:
    """获取基金同类排名和区间收益率。

    Provider Chain（可配置）：天天基金
    """
    code = code.strip()
    return _fetch_with_fallback(
        "fund_rank",
        _FUND_RANK_PROVIDERS,
        _FUND_PERF_CACHE_PREFIX + code,
        CACHE_DAILY,
        fn_kwargs={"code": code},
    )


# ═══════════════════════════════════════════════════════════
#  基金底层持仓（穿透分析用）
# ═══════════════════════════════════════════════════════════

_FUND_HOLD_CACHE_PREFIX = "fund_hold_"

_FUND_HOLD_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tiantian": ("天天基金", tiantian.fetch_fund_holdings),
}


def fetch_fund_holdings(code: str) -> dict[str, Any] | None:
    """获取基金前 10 大持仓。

    Provider Chain（可配置）：天天基金
    """
    code = code.strip()
    return _fetch_with_fallback(
        "fund_hold",
        _FUND_HOLD_PROVIDERS,
        _FUND_HOLD_CACHE_PREFIX + code,
        CACHE_WEEKLY,
        fn_kwargs={"code": code},
    )


# ═══════════════════════════════════════════════════════════
#  基金业绩比较基准
# ═══════════════════════════════════════════════════════════

_BENCHMARK_TABLE_KEY = "fund_benchmarks"


# ── 第 1 层：API 获取 ──────────────────────────────────


def _fetch_benchmark_from_api(code: str) -> str | None:
    """尝试从东方财富基金页面解析业绩比较基准。

    Returns:
        基准描述字符串，失败返回 None
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://fund.eastmoney.com/",
    }
    urls = [
        f"https://fund.eastmoney.com/{code}.html",
        f"https://fundf10.eastmoney.com/jbgk_{code}.html",
    ]
    for url in urls:
        try:
            import httpx as _httpx_loc
            with _httpx_loc.Client(timeout=10, follow_redirects=True, verify=False) as client:
                resp = client.get(url, headers=headers)
                resp.encoding = "utf-8"
                html = resp.text
        except Exception:
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
    except Exception:
        pass
    return table


# ── 公开接口 ────────────────────────────────────────────

# per-code 锁，防止 fetch_fund_benchmark 并发写入缓存互相覆盖
_benchmark_locks: dict[str, threading.Lock] = {}
_benchmark_locks_lock = threading.Lock()


def _get_benchmark_lock(code: str) -> threading.Lock:
    with _benchmark_locks_lock:
        if code not in _benchmark_locks:
            _benchmark_locks[code] = threading.Lock()
        return _benchmark_locks[code]


def fetch_fund_benchmark(code: str) -> str:
    """获取基金业绩比较基准。

    三层策略：API 解析 → 内置知识库 → config.json 用户扩展。
    结果缓存至 fund_benchmarks.json（每月刷新）。
    仅在缓存过期或不存在时才走完整的 1→2→3 链路。

    Args:
        code: 6 位基金代码

    Returns:
        业绩比较基准描述字符串；未找到返回 "--"
    """
    code = code.strip()
    from src.python.cache import CACHE_MONTHLY
    from src.python.cache import get as cache_get, set as cache_set

    cache_key = _BENCHMARK_TABLE_KEY
    cached = cache_get(cache_key, CACHE_MONTHLY)
    if cached is not None and isinstance(cached, dict):
        return cached.get(code, "--")

    lock = _get_benchmark_lock(code)
    with lock:
        # 双重检查：获得锁后确认缓存未被其他线程更新
        cached = cache_get(cache_key, CACHE_MONTHLY)
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


# ═══════════════════════════════════════════════════════════
#  行业分类 / 概念板块
# ═══════════════════════════════════════════════════════════

_INDUSTRY_CACHE_PREFIX = "industry_"

_INDUSTRY_PROVIDERS: dict[str, tuple[str, Callable]] = {
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

    Provider Chain: 东方财富 push2

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


def batch_fetch_industry_data(codes: list[str], max_workers: int = 10) -> dict[str, dict]:
    """批量获取多只证券的行业分类和概念板块归属。

    使用线程池并发获取，已缓存的不重复请求。

    Args:
        codes: 6 位证券代码列表
        max_workers: 最大并发线程数，默认 10

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
            res = future.result()
            if res is not None:
                code, data = res
                with lock:
                    result[code] = data

    logger.info("批量行业数据获取完成: 共 %d 个代码, 成功 %d 个",
                len(valid_codes), len(result))
    return result
