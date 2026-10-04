"""基金申购状态总表 — Provider Chain 接线、缓存准入与会话复用。

数据类型 ``fund_purchase``：天天基金全量申购状态表（开放申购/限大额/暂停申购 +
日累计限定金额 + 下一开放日），供持仓明细「申购状态」列消费。

  - 主链路：直连端点（``providers/tiantian_purchase.py`` 解析器）
  - 备链路：akshare ``fund_purchase_em()`` 封装（解析器冗余，共享上游端点）
  - 兜底：过期缓存（``fetch_with_fallback`` 统一路径，``fetched_at`` 随载荷返回）

使用模式为**每日 1 次全量** → 单键缓存 TTL 1 天（远低于上游风控阈值）；
载荷准入（``purchase_status_payload_is_valid``）写侧读侧同判据，
语义版本 ``purchase_schema`` 变更即自动作废旧缓存。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import get_ttl
from src.python.fetcher.chain import FailureDiagnostics, fetch_with_fallback
from src.python.providers.tiantian_purchase import (
    fetch_fund_purchase_table,
    fetch_fund_purchase_table_via_akshare,
    purchase_status_payload_is_valid,
)

logger = logging.getLogger("invest")

#: 单键全量缓存（非按代码分键——一次抓取覆盖全部持仓代码），TTL 1 天
_PURCHASE_CACHE_KEY = "fund_purchase_status_table"
#: 会话缓存域/键（DataSourceRegistry.session_cache，同一次报告生成内单次抓取）
_SESSION_DOMAIN = "fund_purchase"
_SESSION_KEY = "table"

_ProviderFunc = Any

#: 顺序即链路顺序；键名与 ``fetcher/chain.py::_DEFAULT_CHAINS["fund_purchase"]`` 对应
_PURCHASE_PROVIDERS: dict[str, tuple[str, _ProviderFunc]] = {
    "tiantian": ("天天基金", fetch_fund_purchase_table),
    "akshare_purchase": ("天天基金(akshare)", fetch_fund_purchase_table_via_akshare),
}


def _stamp_source(payload: dict[str, Any], source_label: str) -> dict[str, Any]:
    """transform：把命中的链路展示名盖进载荷（PurchaseStatus 契约的 ``source`` 字段）。"""
    return {**payload, "source": source_label}


def _admit(payload: object, _source_label: str) -> bool:
    """写侧准入（``validate`` 两参签名）：与读侧 ``cache_validate`` 同一份判据。

    不通过 → 本 provider 判失败、递补下一链路，且**不写缓存**（旧缓存不被污染）。
    """
    return purchase_status_payload_is_valid(payload)


def fetch_fund_purchase_status() -> dict[str, Any] | None:
    """双链路获取全量申购状态载荷（chain + 准入校验 + 缓存 + 熔断/追踪）。

    Returns:
        ``{"rows", "fetched_at", "purchase_schema", "source"}``；全链失败且
        无（有效的）过期缓存时返回 None。
    """
    from src.python.report.data_status import get_tracker

    _t = get_tracker()
    diag = FailureDiagnostics()
    result = fetch_with_fallback(
        "fund_purchase",
        _PURCHASE_PROVIDERS,
        _PURCHASE_CACHE_KEY,
        get_ttl("fund_purchase", _PURCHASE_CACHE_KEY),
        diagnostics=diag,
        validate=_admit,
        transform=_stamp_source,
        # 载荷语义版本准入：purchase_schema 不符即丢弃重取（含过期降级条目），
        # 损坏/截断的缓存体不得经过期缓存兜底流入展示层。
        cache_validate=purchase_status_payload_is_valid,
    )
    if result is not None:
        _t.record("fund_purchase", "T2", success=True)
    else:
        _t.record("fund_purchase", "T2", success=False, failure_type="unreachable", message=diag.summary())
    return result


def fetch_fund_purchase_status_cached() -> dict[str, Any] | None:
    """全量申购状态（含会话缓存），同一次报告生成内只经链路一次。

    会话命中直接返回（含 ``source``/``fetched_at``）；未命中走
    :func:`fetch_fund_purchase_status` 并回写会话缓存（``None`` 亦缓存，
    避免同会话内全链失败被反复重试）。
    """
    from src.python.core.provider_registry import NOT_FOUND, get_registry

    registry = get_registry()
    cached = registry.session_cache_get(_SESSION_DOMAIN, _SESSION_KEY)
    if cached is not NOT_FOUND:
        return cached
    result = fetch_fund_purchase_status()
    registry.session_cache_set(_SESSION_DOMAIN, _SESSION_KEY, result, source="api")
    return result
