"""财务指标域适配器与链路的契约测试。

覆盖：适配器登记与自检、标准字段集、链路注册与顺序、经 fetch_with_fallback
取回恰为标准字段集的记录、以及 provider 不可用时的降级。

运行：
  pytest src/test/unit/fetcher/test_financial_indicator.py -v
"""

from __future__ import annotations

import pytest

from src.python.schemas.datasource_fields import DOMAIN_FINANCIAL_INDICATOR, FinancialIndicatorFields

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

_SAMPLE = {
    "code": "600519",
    "symbol": "600519.SS",
    "report_period": "2026-06-30",
    "doc_type": "semiannual",
    "revenue": 92278072083.21,
    "net_profit": 44516880421.86,
    "revenue_yoy": 0.013001,
    "net_profit_yoy": -0.019516,
    "gross_margin": 0.895552,
    "roe": 0.1675,
    "debt_ratio": 0.151931,
    "operating_cash_flow": 70690750119.06,
    "eps": 35.57,
    "bvps": 200.989754,
    "source_api": "akshare_financial",
    "source": "akshare 财务指标",
}


def test_adapter_registered_and_self_test_ok():
    from src.python.fetcher.source_adapter import get_adapters, survey_adapters

    adapters = get_adapters(DOMAIN_FINANCIAL_INDICATOR)
    assert "akshare_financial" in adapters
    assert adapters["akshare_financial"].self_test() == []
    rows = {r["source_id"]: r for r in survey_adapters()}
    assert rows["akshare_financial"]["ok"] is True


def test_standard_fields_exact_set():
    """标准字段集与记录类声明一致（防字段名漂移）。"""
    assert set(FinancialIndicatorFields().to_dict()) == {
        "code",
        "symbol",
        "report_period",
        "doc_type",
        "revenue",
        "net_profit",
        "revenue_yoy",
        "net_profit_yoy",
        "gross_margin",
        "roe",
        "debt_ratio",
        "operating_cash_flow",
        "eps",
        "bvps",
        "source_api",
        "source",
    }


def test_chain_registered_with_single_provider():
    from src.python.fetcher.chain import _get_chain

    assert _get_chain("financial_indicator") == ["akshare_financial"]


def test_fetch_via_chain_returns_standard_record(monkeypatch):
    """经链路两槽取回恰为标准字段集（provider 已输出标准键，无需 alias）。"""
    from src.python.cache import get_ttl
    from src.python.fetcher.chain import fetch_with_fallback
    from src.python.fetcher.source_adapter import adapter_chain_slots
    from src.python.providers import akshare_financial

    monkeypatch.setattr(akshare_financial, "fetch_financial_indicators", lambda code: dict(_SAMPLE, code=code))
    provider_map, transform_map = adapter_chain_slots(DOMAIN_FINANCIAL_INDICATOR)
    cache_key = "fin_indicator_unittest_600519"
    out = fetch_with_fallback(
        "financial_indicator",
        provider_map,
        cache_key,
        get_ttl("fin_indicator", cache_key),
        fn_kwargs={"code": "600519"},
        transform=transform_map,
    )

    assert out is not None
    assert set(out) == set(FinancialIndicatorFields().to_dict())
    assert out["code"] == "600519"
    assert out["roe"] == pytest.approx(0.1675)


def test_fetch_via_chain_degrades_when_provider_empty(monkeypatch):
    """provider 返回 None → 链路返回 None（不抛异常，交由上层写占位）。"""
    from src.python.cache import get_ttl
    from src.python.fetcher.chain import fetch_with_fallback
    from src.python.fetcher.source_adapter import adapter_chain_slots
    from src.python.providers import akshare_financial

    monkeypatch.setattr(akshare_financial, "fetch_financial_indicators", lambda code: None)
    provider_map, transform_map = adapter_chain_slots(DOMAIN_FINANCIAL_INDICATOR)
    cache_key = "fin_indicator_unittest_missing"
    out = fetch_with_fallback(
        "financial_indicator",
        provider_map,
        cache_key,
        get_ttl("fin_indicator", cache_key),
        fn_kwargs={"code": "999999"},
        transform=transform_map,
    )
    assert out is None
