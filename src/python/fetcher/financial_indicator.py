"""财务指标域取数编排 —— 多期指标序列（缓存 + 降级）。

**分层说明（与单期链路的边界）**：

- **单期**最新记录走既有 Provider Chain（``fetcher/chain.py`` 的
  ``financial_indicator`` 链 + ``fetcher/financial_indicator_adapters.py`` 两槽），
  主源失败自动落解析支路；本模块 :func:`fetch_latest_indicator` 即该链路的薄封装。
- **多期序列**（趋势与后续估值分位所需）以主源为一次调用取多期；主源不可用或
  无覆盖时**退化为单期**（解析支路只能给出最新章节的一期），并在返回值上如实体现
  —— 不伪造历史期，调用方据期数自行判断能否做趋势/分位。

缓存键前缀 ``fin_indicator_hist_`` 归入 ``core/registry`` 的 ``fin_indicator`` 模块
（一月 TTL、基础类），与单期记录共用 TTL 口径。不新增 HTTP 通道：provider 的超时与
限速、链路的缓存与熔断均复用既有实现。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import get_ttl
from src.python.cache import set as cache_set
from src.python.core.code_utils import is_a_share_code
from src.python.providers import akshare_financial, hithink
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_INDICATOR

logger = logging.getLogger("invest")

#: 多期序列缓存键前缀（单期记录键为 ``fin_indicator_{code}``）
HISTORY_PREFIX = "fin_indicator_hist_"

#: 默认取用期数（覆盖同比与多年趋势）
DEFAULT_PERIODS = 8


def fetch_latest_indicator(code: str) -> dict[str, Any] | None:
    """取最新报告期的标准指标记录（经链路：主源 → 解析支路）。"""
    from src.python.fetcher.chain import fetch_with_fallback
    from src.python.fetcher.source_adapter import adapter_chain_slots

    code = str(code or "").strip()
    if not is_a_share_code(code):
        return None
    provider_map, transform_map = adapter_chain_slots(DOMAIN_FINANCIAL_INDICATOR)
    cache_key = f"fin_indicator_{code}"
    record = fetch_with_fallback(
        "financial_indicator",
        provider_map,
        cache_key,
        get_ttl("fin_indicator", cache_key),
        fn_kwargs={"code": code},
        transform=transform_map,
    )
    if record:
        from src.python.report.data_status import mark_data_used

        mark_data_used(f"fin_indicator_{record.get('source_api') or 'unknown'}")
    return record


def fetch_indicator_series(code: str, limit: int = DEFAULT_PERIODS) -> list[dict[str, Any]]:
    """取多期标准指标记录（报告期降序）；无覆盖返回空列表。

    主源一次调用即得多期；主源不可用时退化为链路单期记录（列表长度 ≤ 1）。
    """
    code = str(code or "").strip()
    if not is_a_share_code(code):
        logger.debug("[financial_indicator] 非 A 股代码，跳过: %s", code)
        return []

    cache_key = f"{HISTORY_PREFIX}{code}"
    cached = cache_get(cache_key, get_ttl("fin_indicator", cache_key))
    if isinstance(cached, list):
        return cached

    from src.python.report.data_status import mark_data_used, mark_provider_used

    records: list[dict[str, Any]] = list(akshare_financial.fetch_financial_indicator_history(code, limit=limit))
    if records:
        mark_data_used(f"fin_indicator_{akshare_financial.SOURCE_ID}")
        mark_provider_used("financial_indicator", akshare_financial.SOURCE_ID, akshare_financial.DISPLAY_NAME)
    if not records:
        # 主源不可用 → 官方合并报表派生（同花顺，需 key；一次链路给足多期，优于单期兜底）
        records = fetch_hithink_indicator_series(code, limit=limit)
        if records:
            mark_data_used(f"fin_indicator_{hithink.SOURCE_ID}")
            mark_provider_used("financial_indicator", hithink.SOURCE_ID, hithink.DISPLAY_NAME)
    if not records:
        latest = fetch_latest_indicator(code)
        if latest:
            records = [latest]
    if records:
        cache_set(cache_key, records)
    return records


def fetch_hithink_indicator_series(code: str, limit: int = DEFAULT_PERIODS) -> list[dict[str, Any]]:
    """同花顺官方报表派生的**多期**指标记录（主源不可用时的第二选择）。

    与 :func:`fetch_latest_indicator`（链路单期）互补：三张报表各一次请求即得近若干期，
    使趋势/质量档在同源序列上仍可计算。任一报表缺失即返回空列表，由链路继续降级。
    """
    from src.python.analysis.financial_statement_derive import derive_indicator_records
    from src.python.providers import hithink

    symbol = hithink.to_thscode(code)
    if not symbol:
        return []
    return derive_indicator_records(
        hithink.fetch_income_statements(symbol, period="quarterly", limit=limit + 4),
        hithink.fetch_balance_sheets(symbol, period="quarterly", limit=limit + 4),
        hithink.fetch_cash_flow_statements(symbol, period="quarterly", limit=limit + 4),
        code=code,
        symbol=symbol,
        limit=limit,
    )


def collect_price_map(details: Any) -> dict[str, float]:
    """从行情明细列表装配 ``{代码: 现价}``（供 PE/PB 当前值计算）。

    非数值/非正价格一律跳过（缺价即不产 PE/PB，宁缺勿错）。
    """
    prices: dict[str, float] = {}
    for d in details or []:
        code = str(getattr(d, "code", "") or "").strip()
        try:
            price = float(getattr(d, "price", 0) or 0)
        except (TypeError, ValueError):
            continue
        if code and price > 0:
            prices[code] = price
    return prices
