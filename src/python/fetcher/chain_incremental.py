"""历史序列增量合并 —— payload 语义版本闸门、按日合并/连续性校验、历史 provider 递补调度。

``fetch_with_incremental_fallback`` 是「链外手写降级路径」的统一出口：过期缓存回写一律盖
``_payload_ver`` 语义版本戳（``write_stale_with_version``），准入由 ``payload_version_current``
判定；取数按日合并（``_merge_by_date``）并校验交易日连续性（``_validate_continuity``）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import clear as cache_clear
from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.core.constants import CACHE_WEEKLY
from src.python.core.datasource_credential import (
    credential_hint,
    credential_ready_enabled,
    missing_credential,
)
from src.python.core.provider_registry import get_registry
from src.python.core.trading_calendar import count_trading_days_elapsed
from src.python.fetcher.chain_config import _get_chain
from src.python.fetcher.chain_diagnostics import (
    FailureDiagnostics,
    _brief_reason,
    _mark_provider_used,
)


logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════════
#  过期缓存降级回写（链外手写降级路径的统一出口）
# ═══════════════════════════════════════════════════════════════

# 载荷语义版本戳字段与当前版本。「语义已变更但结构未变」的载荷仅靠 TTL
# 会在过期前持续遮蔽修复（fund ranking 实测教训，见 rank_payload_is_current）——
# 任何过期缓存回写都必须盖戳，后续准入判据按字段比对自动作废旧语义条目。
_CACHE_PAYLOAD_FIELD = "_payload_ver"


_CACHE_PAYLOAD_VER = "1"


def payload_version_current(payload: object) -> bool:
    """缓存载荷是否由**当前语义版本**的回写端写出（准入判据用）。"""
    if not isinstance(payload, dict) or _CACHE_PAYLOAD_FIELD not in payload:
        return True  # 未盖戳的载荷（主链路成功回写等）不拦，拦了会无限重取
    return payload[_CACHE_PAYLOAD_FIELD] == _CACHE_PAYLOAD_VER


def write_stale_with_version(
    cache_key: str,
    data: dict[str, Any],
    source: str = "stale_cache",
) -> dict[str, Any]:
    """过期缓存降级回写统一助手：标记来源 + 盖语义版本戳 + 回写缓存。

    链外手写降级路径（如 fetcher/index.py 的手写判断链）回写过期数据时**必须**
    经本助手——直接 ``cache_set`` 回写未盖戳载荷，语义版本机制上线后会成为
    「版本缺失」的遮蔽点。返回盖戳后的载荷（调用方直接入结果字典）。
    """
    data = dict(data)
    data["_source"] = source
    data[_CACHE_PAYLOAD_FIELD] = _CACHE_PAYLOAD_VER
    cache_set(cache_key, data)
    return data


def _try_providers(
    providers: list[str],
    registry: Any,
    chain_name: str,
    code: str,
    days: int,
    start_from: str | None,
    diagnostics: FailureDiagnostics | None = None,
) -> list[dict]:
    """遍历 providers 获取数据，返回第一个非空结果。

    Args:
        providers: provider 名称列表（按优先级排序）
        registry: DataSourceRegistry（熔断检测用）
        chain_name: chain 名称
        code: 证券代码
        days: 获取天数
        start_from: 起始日期，None 时获取完整 days 条数据
        diagnostics: 可选的失败原因收集器（不传则零采集）

    Returns:
        list[dict] 或 []（全部链路失败时）
    """
    for provider_name in providers:
        if registry.is_circuit_broken(provider_name):
            logger.debug("[%s] %s 已被熔断，跳过", chain_name, provider_name)
            if diagnostics is not None:
                diagnostics.add(provider_name, "已被熔断跳过")
            continue
        # 凭据就绪预检：与 fetch_with_fallback 同一判定（见彼处注释——配置级
        # 问题不计入熔断）。历史 chain 若缺此分支，需 key 的源会在此被当作
        # 「不可达」反复重试并累计熔断，正是本机制要消除的行为。
        _spec = missing_credential(provider_name) if credential_ready_enabled() else None
        if _spec is not None:
            logger.info("[%s] %s 缺少凭据，跳过（%s）", chain_name, provider_name, _spec.env_var)
            if diagnostics is not None:
                diagnostics.add(provider_name, credential_hint(_spec))
            continue
        logger.info("[%s] 尝试 %s（code=%s, days=%d）", chain_name, provider_name, code, days)
        try:
            data = _call_history_provider(provider_name, chain_name, code, days, start_from)
            if not data:
                logger.info("[%s] %s 返回空数据（无此品种历史数据），尝试下一链路", chain_name, provider_name)
                if diagnostics is not None:
                    diagnostics.add(provider_name, "返回空")
                continue
            registry.record_success(provider_name)
            _mark_provider_used(chain_name, provider_name, _history_provider_label(provider_name))
            return data
        except Exception as e:
            reason = _brief_reason(f"{type(e).__name__}: {e}")
            registry.record_failure(provider_name, f"{chain_name}: {reason}")
            if diagnostics is not None:
                diagnostics.add(provider_name, reason)
            continue
    return []


def fetch_with_incremental_fallback(
    chain_name: str,
    code: str,
    days: int = 30,
    diagnostics: FailureDiagnostics | None = None,
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
        diagnostics: 可选的失败原因收集器（不传则零采集）

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
    new_data = _try_providers(providers, registry, chain_name, code, days, last_cached_date, diagnostics)

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
            full_data = _try_providers(providers, registry, chain_name, code, days, None, diagnostics)
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
    "tiantian": "src.python.providers.tiantian_nav",
    "eastmoney": "src.python.providers.eastmoney",
    "hithink": "src.python.providers.hithink",
}


#: 历史链路 provider 展示名——模块未声明 ``DISPLAY_NAME`` 者在此补齐（声明了的以模块为准）
_HISTORY_PROVIDER_LABELS: dict[str, str] = {
    "tencent": "腾讯财经",
    "sina": "新浪财经",
    "tiantian": "天天基金",
    "eastmoney": "东方财富",
}


def _history_provider_label(provider_name: str) -> str:
    """历史链路 provider → 展示名（模块 ``DISPLAY_NAME`` 优先；其次本表；末位回退标识）。"""
    module_path = _HISTORY_PROVIDER_MAP.get(provider_name)
    if module_path:
        try:
            import importlib

            declared = getattr(importlib.import_module(module_path), "DISPLAY_NAME", "")
            if declared:
                return str(declared)
        except Exception:  # 展示名解析失败不影响取数
            logger.debug("[history] provider 展示名解析失败: %s", provider_name, exc_info=True)
    return _HISTORY_PROVIDER_LABELS.get(provider_name, provider_name)


# 新旧 K 线之间缺失的交易日数超过此值 → 判定数据跳空（部分历史不可达）
_MAX_GAP_TRADING_DAYS: int = 5


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
    elif chain_name in ("history_index", "history_index_us"):
        # 两条链共用指数 K 线函数：命中 provider 有实现才真正发起请求，
        # 无实现者落到末尾的统一告警。
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
        "history_index_us": "fetch_index_kline",
        "history_fund_otc": "fetch_fund_nav_history",
    }.get(chain_name, "未知函数")
    logger.warning("[history] %s 无 %s 函数", provider_name, fn_name)
    return []


def clear_incremental_cache(chain_name: str, code: str) -> None:
    """清空增量链路的文件缓存（供调用方检测到窗口缩水时强制全量重取）。

    缓存键格式与 :func:`fetch_with_incremental_fallback` 保持一致，
    避免调用方重复拼接键名。
    """
    cache_clear(f"history_{chain_name}_{code}")


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
    else:
        gap = _missing_trading_days(last_old.get("date"), first_new.get("date"))
        if gap > _MAX_GAP_TRADING_DAYS:
            logger.warning("[%s] 数据跳空 %d 个交易日——部分历史不可达", cache_key, gap)
    return False


def _missing_trading_days(date1: str | None, date2: str | None) -> int:
    """计算两个 K 线日期之间**缺失**的交易日数（不含两端）。

    以交易日而非自然日计——周末与长假会放大自然日差（如国庆前后相邻的两个
    交易日相差 10 个自然日），按自然日判定会把正常连续的 K 线误判为跳空。
    相邻交易日 → 0；两端相等/逆序、日期为空或格式非法 → 0。
    """
    if not date1 or not date2:
        return 0
    elapsed = count_trading_days_elapsed(date1, date2)
    if elapsed is None or elapsed <= 0:
        return 0
    return elapsed - 1
