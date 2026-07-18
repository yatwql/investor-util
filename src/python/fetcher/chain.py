"""Provider Chain 定义与通用 Fallback 获取器。

每类数据（price/index/rank/holding）对应一个 Provider Chain，
chain 中按优先级列出 provider，主链路失败后自动递补。
用户可通过 config.json 的 preferred_provider 手动指定首选链路。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from src.python.cache import clear as cache_clear
from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.config import get_config
from src.python.constants import CACHE_WEEKLY
from src.python.provider_registry import TRANSPORT_FAILURE, get_registry

logger = logging.getLogger("invest")

# ── Provider Chain 定义 ──────────────────────────────────────

_DEFAULT_CHAINS: dict[str, list[str]] = {
    "price_stock": ["tencent", "sina"],
    "price_fund_otc": ["eastmoney"],
    "price": ["tencent", "eastmoney"],
    "fund_rank": ["tiantian"],
    "fund_hold": ["tiantian"],
    "industry": ["eastmoney_industry", "eastmoney_industry_rest"],
    # 组合历史走势：历史数据 chains（复用现有 provider name，熔断器共享）
    "history_stock": ["tencent", "sina"],
    "history_fund_otc": ["tiantian", "eastmoney"],
    "history_index": ["tencent", "sina"],
    "history_index_us": ["sina", "tencent"],
}


def _get_chain(data_type: str) -> list[str]:
    """获取指定数据类型的 Provider Chain（考虑用户配置）。

    用户可在 config.json 中通过 preferred_provider.<data_type> 指定首选。
    """
    chain = list(_DEFAULT_CHAINS.get(data_type, []))
    try:
        config = get_config()
        preferred = (config.get("preferred_provider") or {}).get(data_type)
        if preferred and preferred in chain and chain[0] != preferred:
            chain.remove(preferred)
            chain.insert(0, preferred)
            logger.info("%s Provider Chain: 根据配置首选 '%s'", data_type, preferred)
    except (KeyError, TypeError):
        logger.debug("[chain] preferred_provider 配置解析失败，使用默认链")
    return chain


# ── 会话级 Provider 熔断（委托 DataSourceRegistry） ──────
# 熔断逻辑集中在 provider_registry.py：
#   - 连续 3 次传输级失败 → 熔断 300s → 冷却期满自动恢复
#   - record_failure(provider, context) / record_success(provider)
#   - is_circuit_broken(provider) → bool
#   - is_chain_broken(chain) → bool


def reset_provider_skip() -> None:
    """重置 Provider 熔断状态（测试用）。委托 DataSourceRegistry.reset()。"""
    get_registry().reset()


def is_provider_chain_broken(data_type: str) -> bool:
    """检查指定数据类型的全部 Provider 是否都已熔断。

    batch 入口调用一次即可预判全链不可用，避免逐条重复尝试。

    Returns:
        True — 链上所有 provider 均在熔断中，全链不可用
        False — 至少有一个 provider 可用
    """
    chain = _get_chain(data_type)
    if not chain:
        return True
    return get_registry().is_chain_broken(chain)


_ProviderFunc = Callable[..., dict[str, Any] | None]

# TRANSPORT_FAILURE sentinel 定义于 provider_registry.py，
# 跨模块共享用于 _try_provider_fetch 的传输级异常标记。


# ── 通用带缓存的 Fallback 调用 ──────────────────────────────


def _try_provider_fetch(
    data_type: str,
    provider_name: str,
    source_label: str,
    fetch_fn: _ProviderFunc,
    kwargs: dict,
    validate: Callable[[dict[str, Any], str], bool] | None,
    transform: Callable[[dict[str, Any], str], dict[str, Any] | None]
    | dict[str, Callable[[dict[str, Any], str], dict[str, Any] | None]]
    | None,
) -> dict[str, Any] | None:
    """尝试调用单个 provider 的 fetch 函数，返回转换后的结果或 None。"""
    _code_tag = f" [{kwargs.get('code', '')}]" if kwargs.get("code") else ""
    try:
        raw = fetch_fn(**kwargs)
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "Too Many Requests" in err_str or "rate" in err_str.lower():
            logger.warning("[%s]%s %s API 限速(429): %s", data_type, _code_tag, provider_name, err_str)
        else:
            logger.warning("[%s]%s %s 调用异常: %s", data_type, _code_tag, provider_name, err_str)
        return cast("dict[str, Any] | None", TRANSPORT_FAILURE)  # 传输级异常 → 应计入熔断

    if raw is None:
        logger.info("[%s]%s %s 返回空，尝试下一链路", data_type, _code_tag, provider_name)
        return None

    # 数据验证
    if validate:
        try:
            if not validate(raw, provider_name):
                logger.info("[%s]%s %s 数据验证未通过，尝试下一链路", data_type, _code_tag, provider_name)
                return None
        except Exception as e:
            logger.warning("[%s]%s %s 数据验证异常: %s", data_type, _code_tag, provider_name, e)
            return None

    # 应用数据转换
    try:
        if isinstance(transform, dict):
            fn = transform.get(provider_name)
            result = fn(raw, source_label) if fn else raw
        elif transform:
            result = transform(raw, source_label)
        else:
            result = raw
    except Exception as e:
        logger.warning("[%s] %s 数据转换失败: %s", data_type, provider_name, e)
        return None

    if result is not None:
        logger.info("[%s]%s %s 成功", data_type, _code_tag, provider_name)
    return result


def fetch_with_fallback(
    data_type: str,
    provider_fn_map: dict[str, tuple[str, _ProviderFunc]],
    cache_key: str,
    cache_ttl: float,
    fn_kwargs: dict[str, Any] | None = None,
    transform: Callable[[dict[str, Any], str], dict[str, Any] | None]
    | dict[str, Callable[[dict[str, Any], str], dict[str, Any] | None]]
    | None = None,
    validate: Callable[[dict[str, Any], str], bool] | None = None,
) -> dict[str, Any] | None:
    """通用 Fallback 获取器。

    对于指定数据类型，依次尝试 chain 中的每个 provider，
    第一个成功的返回结果，全部失败返回 None。

    熔断逻辑委托 DataSourceRegistry，取代旧版 _PROVIDER_SKIP 等全局变量。
    """
    chain = _get_chain(data_type)

    # 1) 读缓存
    cached = cache_get(cache_key, cache_ttl)
    if cached is not None:
        return cached

    # 2) 遍历 chain 尝试（熔断委托 registry）
    kwargs = fn_kwargs or {}
    _code_tag = f" [{kwargs.get('code', '')}]" if kwargs.get("code") else ""
    reg = get_registry()
    for provider_name in chain:
        # 熔断检查（含自动冷却恢复）
        if reg.is_circuit_broken(provider_name):
            logger.debug("[%s]%s %s 已被熔断，跳过", data_type, _code_tag, provider_name)
            continue

        entry = provider_fn_map.get(provider_name)
        if not entry:
            logger.warning("[%s]%s 未知 Provider '%s'，跳过", data_type, _code_tag, provider_name)
            continue

        source_label, fetch_fn = entry
        logger.info("[%s]%s 尝试 %s (%s)", data_type, _code_tag, source_label, provider_name)

        if fetch_fn is None:
            logger.warning("[%s] %s 没有注册的 fetch 函数", data_type, provider_name)
            continue

        result = _try_provider_fetch(data_type, provider_name, source_label, fetch_fn, kwargs, validate, transform)
        if result is not None and result is not TRANSPORT_FAILURE:
            # 成功 → 恢复熔断计数器
            reg.record_success(provider_name)
            cache_set(cache_key, result)
            return result

        if result is TRANSPORT_FAILURE:
            # 传输级异常（超时/断连/DNS/5xx）→ 累计连续失败计数
            reg.record_failure(provider_name, f"{data_type}:transport")
            if reg.is_circuit_broken(provider_name):
                logger.warning("[%s]%s %s 连续失败，本会话后续请求跳过", data_type, _code_tag, provider_name)
        # else: 代码级空结果（API 不识别该代码）→ 不计入熔断计数器

    # 3) 降级：全部 Provider 失败时尝试过期缓存
    stale = cache_get(cache_key, CACHE_WEEKLY)
    if stale is not None:
        logger.info("[%s]%s 全部 Provider 不可用，降级使用过期缓存", data_type, _code_tag)
        return stale

    logger.warning("[%s]%s 全链路失败（无过期缓存可用），数据不可用", data_type, _code_tag)
    return None


# ═══════════════════════════════════════════════════════════════
#  组合历史走势：增量合并 Fallback 路由
# ═══════════════════════════════════════════════════════════════


def _try_providers(
    providers: list[str],
    registry: Any,
    chain_name: str,
    code: str,
    days: int,
    start_from: str | None,
) -> list[dict]:
    """遍历 providers 获取数据，返回第一个非空结果。

    Args:
        providers: provider 名称列表（按优先级排序）
        registry: DataSourceRegistry（熔断检测用）
        chain_name: chain 名称
        code: 证券代码
        days: 获取天数
        start_from: 起始日期，None 时获取完整 days 条数据

    Returns:
        list[dict] 或 []（全部链路失败时）
    """
    for provider_name in providers:
        if registry.is_circuit_broken(provider_name):
            logger.debug("[%s] %s 已被熔断，跳过", chain_name, provider_name)
            continue
        logger.info("[%s] 尝试 %s（code=%s, days=%d）", chain_name, provider_name, code, days)
        try:
            data = _call_history_provider(provider_name, chain_name, code, days, start_from)
            if not data:
                logger.info("[%s] %s 返回空数据（无此品种历史数据），尝试下一链路", chain_name, provider_name)
                continue
            registry.record_success(provider_name)
            return data
        except Exception:
            registry.record_failure(provider_name, f"{chain_name}:transport")
            continue
    return []


def fetch_with_incremental_fallback(
    chain_name: str,
    code: str,
    days: int = 30,
    param_fn: Callable | None = None,
) -> list[dict]:
    """增量合并版 Fallback 路由（历史数据用）。

    当检测到新旧数据重叠时，自动全量刷新缓存，确保历史修正被正确覆盖。

    - chain 层管理缓存读/写/合并
    - Provider 函数只负责纯数据获取（不碰缓存层）
    - 熔断器预检、fallback 遍历与 fetch_with_fallback() 共享

    Args:
        chain_name: chain 名称（如 "history_stock"、"history_fund_otc"）
        code: 证券代码
        days: 获取天数（默认 30）
        param_fn: 将 (code, start_from, days) 转换为 provider_fn_kwargs 的函数。
                  None 时直接使用原始的 (code, days, start_from) 作为 kwargs。

    Returns:
        list[dict]: 按日期升序排列的数据列表，至少返回 days 条。
        全链路失败时返回空列表（不使用过期缓存——走势数据降级后显示占位文本）。
    """
    cache_key = f"history_{chain_name}_{code}"
    cached = cache_get(cache_key, CACHE_WEEKLY) or []
    last_cached_date = cached[-1]["date"] if cached else None

    registry = get_registry()
    providers = _get_chain(chain_name)

    # 第一轮：增量获取（从 last_cached_date 开始）
    new_data = _try_providers(providers, registry, chain_name, code, days, last_cached_date)

    if new_data:
        # 判断 provider 是否实际支持增量获取。
        # 若新数据起点 ≤ 缓存起点，说明 provider 未按 start_from 过滤
        # （如 OTC 基金 fetch_fund_nav_history 始终全量返回），
        # 直接写入新数据，跳过合并与重叠检测。
        if cached and new_data and new_data[0].get("date", "") <= cached[0].get("date", ""):
            logger.debug("[%s] %s provider 全量返回，直接使用新数据", chain_name, code)
            cache_set(cache_key, new_data)
            return new_data[-days:]

        merged = _merge_by_date(cached, new_data)
        needs_refresh = False
        try:
            needs_refresh = _validate_continuity(cached, new_data, cache_key)
        except Exception:
            logger.warning("[%s] 连续性校验异常（不影响合并）", cache_key)

        if needs_refresh and cached:
            # 检测到历史修正（如除权除息回溯调整）：旧缓存中非重叠部分已过时
            # 自动全量刷新：删旧缓存，不带 start_from 重新获取完整历史
            logger.info("[%s] 检测到历史修正 → 自动全量刷新", chain_name)
            cache_clear(cache_key)
            full_data = _try_providers(providers, registry, chain_name, code, days, None)
            if full_data:
                cache_set(cache_key, full_data)
                return full_data[-days:]
            logger.warning("[%s] 全量刷新失败，使用增量合并数据（仅修正重叠窗口）", chain_name)

        cache_set(cache_key, merged)
        return merged[-days:]
    elif cached:
        # 有缓存但无新数据 — 返回已有缓存
        return cached[-days:]

    return []


_HISTORY_PROVIDER_MAP: dict[str, str] = {
    "tencent": "src.python.providers.tencent",
    "sina": "src.python.providers.sina",
    "tiantian": "src.python.providers.tiantian",
    "eastmoney": "src.python.providers.eastmoney",
}


def _call_history_provider(
    provider_name: str,
    chain_name: str,
    code: str,
    days: int,
    start_from: str | None,
) -> list[dict]:
    """动态调用对应 provider 的历史数据获取函数。

    通过 _HISTORY_PROVIDER_MAP 实现惰性导入，避免模块加载时的循环依赖。

    Args:
        provider_name: provider 名称（如 "tencent"、"sina"、"tiantian"）
        chain_name: chain 名称（决定调用 fetch_kline 还是 fetch_fund_nav_history）
        code: 证券代码
        days: 获取天数
        start_from: 起始日期（YYYY-MM-DD），增量获取参数

    Returns:
        list[dict] 或 []（失败时）
    """
    import importlib

    module_path = _HISTORY_PROVIDER_MAP.get(provider_name)
    if not module_path:
        logger.warning("[history] 未知 Provider: %s", provider_name)
        return []

    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        logger.warning("[history] 导入 %s 失败: %s", module_path, e)
        return []

    if chain_name == "history_fund_otc":
        fn = getattr(mod, "fetch_fund_nav_history", None)
        if fn:
            return fn(code)
    elif chain_name == "history_index":
        fn = getattr(mod, "fetch_index_kline", None)
        if fn:
            return fn(code, days=days, start_from=start_from)
    elif chain_name == "history_stock":
        fn = getattr(mod, "fetch_kline", None)
        if fn:
            return fn(code, days=days, start_from=start_from)

    fn_name = {
        "history_stock": "fetch_kline",
        "history_index": "fetch_index_kline",
        "history_fund_otc": "fetch_fund_nav_history",
    }.get(chain_name, "未知函数")
    logger.warning("[history] %s 无 %s 函数", provider_name, fn_name)
    return []


def _merge_by_date(cached: list[dict], new_data: list[dict]) -> list[dict]:
    """按日期合并去重，new_data 中同天数据覆盖 cached（修正感知）。

    Args:
        cached: 已有的缓存数据列表（按日期升序）
        new_data: 新获取的数据列表（按日期升序）

    Returns:
        合并后的完整数据列表（按日期升序）
    """
    seen = {d["date"] for d in cached}
    merged = list(cached)
    for d in new_data:
        if d["date"] in seen:
            # 覆盖旧数据（处理历史修正）
            _replace_by_date(merged, d)
        else:
            merged.append(d)
    return sorted(merged, key=lambda x: x["date"])


def _replace_by_date(data: list[dict], item: dict) -> None:
    """在已排序列表中用同日期项替换。"""
    for i, existing in enumerate(data):
        if existing["date"] == item["date"]:
            data[i] = item
            break


def _validate_continuity(cached: list[dict], new_data: list[dict], cache_key: str) -> bool:
    """校验新旧数据连续性，检测历史修正信号。

    注意：此函数为纯检测/日志用途，异常不影响主流程。
    调用方应在 try/except 中包装。

    Returns:
        True 检测到数据重叠（可能为历史修正，调用方可据此触发全量刷新）
        False 无重叠或数据不足
    """
    if not cached or not new_data:
        return False
    last_old = cached[-1]
    first_new = new_data[0]

    # 检测日期重叠：新数据首日早于旧数据末日（非相等，相等=API 包含边界日），说明有修正
    if first_new.get("date") < last_old.get("date"):
        logger.warning("[%s] 新旧数据重叠——可能是历史修正，自动全量刷新", cache_key)
        cache_set(f"{cache_key}_correction_flag", True)
        return True
    elif _gap_days(last_old.get("date"), first_new.get("date")) > 5:
        logger.warning("[%s] 数据跳空 >5 交易日——部分历史不可达", cache_key)
    return False


def _gap_days(date1: str | None, date2: str | None) -> int:
    """计算两个日期字符串之间的天数差（简单近似）。"""
    if not date1 or not date2:
        return 0
    try:
        from datetime import datetime

        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        return abs((d2 - d1).days)
    except (ValueError, TypeError):
        return 0


# 模块加载时自动注册默认 Provider Chain，使 registry.get_chain() 和策略选择器生效
get_registry().register_default_chains()
