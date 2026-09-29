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
from src.python.core.retry import STRATEGY_EXPONENTIAL, RetryPolicy, retry_transient
from src.python.providers import akshare_financial, hithink
from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_INDICATOR

logger = logging.getLogger("invest")

#: 多期序列缓存键前缀（单期记录键为 ``fin_indicator_{code}``）
HISTORY_PREFIX = "fin_indicator_hist_"

#: 默认取用期数（覆盖同比与多年趋势）
DEFAULT_PERIODS = 8

#: 多期指标**直连路径**的重试策略：provider 内 ``run_with_timeout`` 已重试一次，
#: 直连路径不承装链路的传输级重试，故在此再补一层有界退避重试（总尝试 2 次）。
_SERIES_RETRY_POLICY = RetryPolicy(attempts=2, strategy=STRATEGY_EXPONENTIAL, base_backoff=0.5, factor=2.0, jitter=0.2)


def _on_series_retry(failed_attempt: int, delay: float, exc: BaseException | None) -> None:
    """多期指标重试日志（与链路重试文案同习语）。"""
    logger.warning(
        "[financial_indicator] 主源多期指标传输级失败（%s），%.1fs 后同源重试 %d/%d",
        type(exc).__name__ if exc is not None else "超时",
        delay,
        failed_attempt,
        _SERIES_RETRY_POLICY.attempts - 1,
    )


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

    records: list[dict[str, Any]] = []
    try:
        # 直连路径不承装链路的传输级重试：akshare 超时/断连多为一过性抖动，
        # 补一层有界退避重试，避免一次抖动就把主源判为不可用而落到需 key 的兜底槽。
        records = retry_transient(
            lambda: list(akshare_financial.fetch_financial_indicator_history(code, limit=limit)),
            policy=_SERIES_RETRY_POLICY,
            retry_on=lambda _e: True,  # akshare 异常种类不可枚举：与 run_with_timeout 同口径
            on_retry=_on_series_retry,
        )
    except Exception as e:  # 重试耗尽 → 不中断，走后续同花顺/链路兜底
        logger.warning("[financial_indicator] 主源多期指标取数失败（%s），转同花顺/链路兜底", e)
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
    try:
        return derive_indicator_records(
            hithink.fetch_income_statements(symbol, period="quarterly", limit=limit + 4),
            hithink.fetch_balance_sheets(symbol, period="quarterly", limit=limit + 4),
            hithink.fetch_cash_flow_statements(symbol, period="quarterly", limit=limit + 4),
            code=code,
            symbol=symbol,
            limit=limit,
        )
    except Exception as e:  # 传输级失败（连接级重试已耗尽而上抛）→ 返回空列表，由调用方继续降级
        logger.warning("[financial_indicator] 同花顺多期报表取数失败（%s），返回空序列", e)
        return []


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
