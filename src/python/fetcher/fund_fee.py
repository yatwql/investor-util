"""基金申赎费率 — Provider Chain 接线、缓存准入、会话复用与配置兜底。

数据类型 ``fund_fee``：F10 交易费率页（申购优惠档 + 赎回费阶梯），**按基金代码
分键缓存**（``fund_fee_{code}``，费率低频变动 → TTL 周档）。

  - 主链路：天天基金 F10 直连（``providers/tiantian_fund_fee.py`` 解析器）
  - 备链路：akshare ``fund_fee_em`` 封装（解析器冗余，仅赎回阶梯）
  - 兜底：过期缓存（``fetch_with_fallback`` 统一路径）；载荷语义版本
    ``fee_schema`` 不符按未命中丢弃（防旧条目遮蔽修复）

费率索引装配 :func:`fetch_fee_index`（消费侧 = whatif 交易成本面板）逐侧标注来源：

  - **申购**：F10 优惠档（``f10_tier``） → 全量申购状态表单档（``table_single``，
    col12 手续费，同会话只取一次） → 配置兜底（``config``） → 未知
  - **赎回**：F10 阶梯（``f10_tier``） → 配置兜底（``config``） → 未知

配置兜底键 ``fund_fee_fallback``（``data/config/config.json``，经 ``get_config()``
绝对路径化单源读取，形态见 ``_config_defaults`` 注释与
:func:`trade_cost_model.build_config_fee_schedules`）——**仅当在线来源不可得时
生效**（兜底而非覆盖）。两侧全未知的代码不入索引，消费侧按「费率未知」标注
（不出成本后数字），不以 0 费率冒充已计成本。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis.fee_schedule_model import (
    SRC_F10,
    SRC_TABLE_SINGLE,
    build_config_fee_schedules,
    build_single_purchase_schedule,
    parse_purchase_fee_schedule,
    parse_redemption_fee_schedule,
)
from src.python.cache import get_ttl
from src.python.config import get_config
from src.python.fetcher.chain import FailureDiagnostics, fetch_with_fallback
from src.python.providers.tiantian_fund_fee import (
    fee_payload_is_valid,
    fetch_fund_fee_page,
    fetch_fund_fee_page_via_akshare,
)

logger = logging.getLogger("invest")

#: 按基金代码分键（单基金费率页）
_CACHE_PREFIX = "fund_fee_"
#: 会话缓存域/键（DataSourceRegistry.session_cache，同一次报告生成内每代码单次经链）
_SESSION_DOMAIN = "fund_fee"

_ProviderFunc = Any

#: 顺序即链路顺序；键名与 ``fetcher/chain_config.py::_DEFAULT_CHAINS["fund_fee"]`` 对应
_FEE_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tiantian_f10": ("天天基金F10", fetch_fund_fee_page),
    "akshare_fee": ("天天基金F10(akshare)", fetch_fund_fee_page_via_akshare),
}


def _stamp_source(payload: dict[str, Any], source_label: str) -> dict[str, Any]:
    """transform：把命中的链路展示名盖进载荷（诊断/日志用；档位来源仍以费率表为准）。"""
    return {**payload, "source": source_label}


def _admit(payload: object, _source_label: str) -> bool:
    """写侧准入（``validate`` 两参签名）：与读侧 ``cache_validate`` 同一份判据。"""
    return fee_payload_is_valid(payload)


def fetch_fund_fee(code: str) -> dict[str, Any] | None:
    """双链路获取单基金费率载荷（chain + 准入校验 + 缓存 + 熔断/追踪）。

    Returns:
        ``{"redemption_rows", "purchase_rows", "fetched_at", fee_schema, "source"}``；
        全链失败且无（有效的）过期缓存时返回 None。
    """
    code = (code or "").strip()
    diag = FailureDiagnostics()
    return fetch_with_fallback(
        "fund_fee",
        _FEE_PROVIDERS,
        _CACHE_PREFIX + code,
        get_ttl("fund_fee", _CACHE_PREFIX + code),
        fn_kwargs={"code": code},
        diagnostics=diag,
        validate=_admit,
        transform=_stamp_source,
        # 载荷语义版本准入：fee_schema 不符即丢弃重取（含过期降级条目），
        # 损坏/截断的缓存体不得经过期缓存兜底流入费率装配。
        cache_validate=fee_payload_is_valid,
    )


def fetch_fund_fee_cached(code: str) -> dict[str, Any] | None:
    """单基金费率载荷（含会话缓存），同一次报告生成内每代码只经链一次。

    会话命中直接返回（含 ``source``/``fetched_at``）；未命中走
    :func:`fetch_fund_fee` 并回写会话缓存（``None`` 亦缓存，避免同会话内
    全链失败被反复重试）。
    """
    from src.python.core.provider_registry import NOT_FOUND, get_registry

    registry = get_registry()
    key = (code or "").strip()
    cached = registry.session_cache_get(_SESSION_DOMAIN, key)
    if cached is not NOT_FOUND:
        return cached
    result = fetch_fund_fee(key)
    registry.session_cache_set(_SESSION_DOMAIN, key, result, source="api")
    return result


# ═══════════════════════════════════════════════════════════════
#  费率索引装配（消费侧 = whatif 交易成本面板）
# ═══════════════════════════════════════════════════════════════


def _config_fallback_map() -> dict[str, Any]:
    """配置兜底表 ``fund_fee_fallback``（非 dict 视同未配置；单源经 get_config）。"""
    try:
        raw = get_config().get("fund_fee_fallback")
    except (TypeError, ValueError, KeyError, AttributeError, RuntimeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _purchase_single_rate(code: str, table: dict[str, Any] | None) -> float | None:
    """全量申购状态表 → 单档申购费率（小数；表不可得/无该代码/未知 → None）。"""
    if not isinstance(table, dict):
        return None
    row = (table.get("rows") or {}).get(code)
    if not isinstance(row, dict):
        return None
    rate = row.get("purchase_fee_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return None
    return rate


def fetch_fee_index(codes: list[str] | tuple[str, ...] | set[str]) -> dict[str, dict[str, Any]]:
    """按基金代码装配 ``trade_cost_model`` 费率索引（逐侧标注来源）。

    逐侧优先级（设计文档 §4 的门槛降级判定动作）：

      申购：F10 优惠档（f10_tier） → 全量申购状态表单档（table_single，延迟
            至少一侧需要时才取，同会话命中缓存零额外请求） → 配置兜底（config）
      赎回：F10 阶梯（f10_tier） → 配置兜底（config）

    Returns:
        ``{code: {"purchase": 费率表|None, "redemption": 费率表|None}}``——
        **只含至少一侧已知的代码**；两侧全未知不入索引（消费侧按未知腿标注，
        语义等价且载荷更小）。单个代码取数失败不中断其余代码。
    """
    fee_index: dict[str, dict[str, Any]] = {}
    _UNLOADED: Any = object()  # 哨兵：全量表**未尝试过**（与「尝试过但取不到的 None」区分，防逐代码重试）
    purchase_table: Any = _UNLOADED  # 延迟加载：全量表单档兜底才取一次（同会话命中缓存零额外请求）
    config_fb = _config_fallback_map()

    for raw_code in codes or ():
        code = str(raw_code or "").strip()
        if not code:
            continue

        purchase: dict[str, Any] | None = None
        redemption: dict[str, Any] | None = None
        try:
            payload = fetch_fund_fee_cached(code)
        except Exception as exc:  # 链路应自行消化传输异常；此处兜住不放大（单代码不中断批）
            logger.warning("[基金费率] %s 取数异常，按未知继续: %s", code, exc)
            payload = None
        if payload is not None:
            purchase = parse_purchase_fee_schedule(payload.get("purchase_rows") or [], SRC_F10)
            redemption = parse_redemption_fee_schedule(payload.get("redemption_rows") or [], SRC_F10)
            if redemption is None:
                logger.warning("[基金费率] %s 赎回阶梯解析失败，走配置兜底/未知", code)

        if purchase is None:
            if purchase_table is _UNLOADED:
                from src.python.fetcher.fund_purchase import fetch_fund_purchase_status_cached

                try:
                    purchase_table = fetch_fund_purchase_status_cached()
                except Exception as exc:
                    logger.warning("[基金费率] 全量申购状态表取数异常，申购单档兜底跳过: %s", exc)
                    purchase_table = None
                if purchase_table is None:
                    logger.info("[基金费率] 全量申购状态表不可得，申购单档兜底跳过")
            rate = _purchase_single_rate(code, purchase_table)
            if rate is not None:
                purchase = build_single_purchase_schedule(rate, SRC_TABLE_SINGLE)

        if purchase is None or redemption is None:
            fallback = build_config_fee_schedules(config_fb.get(code))
            if fallback is not None:
                if purchase is None:
                    purchase = fallback.get("purchase")
                if redemption is None:
                    redemption = fallback.get("redemption")

        if purchase is not None or redemption is not None:
            fee_index[code] = {"purchase": purchase, "redemption": redemption}

    return fee_index


__all__ = [
    "fetch_fund_fee",
    "fetch_fund_fee_cached",
    "fetch_fee_index",
]
