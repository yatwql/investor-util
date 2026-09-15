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


def test_chain_registered_with_main_and_fallback():
    from src.python.fetcher.chain import _get_chain

    assert _get_chain("financial_indicator") == ["akshare_financial", "datasink_indicator"]


def test_datasink_indicator_adapter_registered_and_self_test_ok():
    """解析适配器同样受三段式契约自检保护（输出恰为标准字段集）。"""
    from src.python.fetcher.source_adapter import get_adapters, survey_adapters

    adapters = get_adapters(DOMAIN_FINANCIAL_INDICATOR)
    assert "datasink_indicator" in adapters
    assert adapters["datasink_indicator"].self_test() == []
    rows = {r["source_id"]: r for r in survey_adapters()}
    assert rows["datasink_indicator"]["ok"] is True


def test_datasink_indicator_adapter_parses_report_section(monkeypatch):
    """解析适配器：取回章节正文 → 标准字段记录，源身份由适配器注入。"""
    from src.python.fetcher import financial_report
    from src.python.fetcher.source_adapter import get_adapters

    content = (
        "(一) 主要会计数据单位：元币种：人民币主要会计数据2025年2024年本期比上年同期增减2023年调整后调整前"
        "营业收入86,241,940,222.2084,491,870,566.52"
        "归属于上市公司股东的净利润34,502,809,176.3932,496,172,808.65"
        "基本每股收益（元／股）1.41011.3281"
    )
    monkeypatch.setattr(
        financial_report,
        "fetch_symbol_report",
        lambda symbol, **kw: {
            "symbol": symbol,
            "report_period": "2025-12-31",
            "doc_type": "annual",
            "content": content,
        },
    )

    adapter = get_adapters(DOMAIN_FINANCIAL_INDICATOR)["datasink_indicator"]
    raw = adapter.fetch_raw(code="600900")
    record = adapter.transform_record(raw, adapter.display_name)

    assert record is not None
    assert set(record) == set(FinancialIndicatorFields().to_dict())
    assert record["revenue"] == pytest.approx(86_241_940_222.20)
    assert record["eps"] == pytest.approx(1.4101)
    assert record["report_period"] == "2025-12-31"
    assert record["source_api"] == "datasink_indicator"
    assert record["source"] == "DataSinking 指标解析"


def test_datasink_indicator_adapter_tries_next_section(monkeypatch):
    """首个章节无语料时继续试下一章节（命中即止，不重复取同一章节）。"""
    from src.python.fetcher import financial_report
    from src.python.fetcher.source_adapter import get_adapters

    seen: list[str] = []

    def _fake(symbol: str, **kw):
        section = kw["sections"][0]
        seen.append(section)
        if section == "公司简介和主要财务指标":
            return None
        return {
            "report_period": "2026-03-31",
            "doc_type": "q1",
            "content": "单位：元币种：人民币营业收入86,241,940,222.2084,491,870,566.52",
        }

    monkeypatch.setattr(financial_report, "fetch_symbol_report", _fake)
    adapter = get_adapters(DOMAIN_FINANCIAL_INDICATOR)["datasink_indicator"]
    record = adapter.transform_record(adapter.fetch_raw(code="600900"), adapter.display_name)

    assert seen == ["公司简介和主要财务指标", "主要财务数据"]
    assert record["revenue"] == pytest.approx(86_241_940_222.20)
    assert record["doc_type"] == "q1"


def test_datasink_indicator_adapter_none_when_unparsable(monkeypatch):
    """章节存在但无可识别指标行 → None（交由链路继续降级）。"""
    from src.python.fetcher import financial_report
    from src.python.fetcher.source_adapter import get_adapters

    monkeypatch.setattr(
        financial_report,
        "fetch_symbol_report",
        lambda symbol, **kw: {"report_period": "2025-12-31", "doc_type": "annual", "content": "无指标"},
    )
    adapter = get_adapters(DOMAIN_FINANCIAL_INDICATOR)["datasink_indicator"]
    assert adapter.fetch_raw(code="600900") is None


def test_datasink_indicator_adapter_skips_non_a_share(monkeypatch):
    """非 A 股代码不发请求（符号映射为空即返回）。"""
    from src.python.fetcher import financial_report
    from src.python.fetcher.source_adapter import get_adapters

    called = {"n": 0}

    def _fake(symbol: str, **kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(financial_report, "fetch_symbol_report", _fake)
    adapter = get_adapters(DOMAIN_FINANCIAL_INDICATOR)["datasink_indicator"]
    assert adapter.fetch_raw(code="7203") is None
    assert called["n"] == 0


def test_chain_falls_back_to_datasink(monkeypatch):
    """主源无数据时落到解析支路，且记录源身份为 datasink_indicator。"""
    from src.python.cache import get_ttl
    from src.python.fetcher import financial_report
    from src.python.fetcher.chain import fetch_with_fallback
    from src.python.fetcher.source_adapter import adapter_chain_slots
    from src.python.providers import akshare_financial

    monkeypatch.setattr(akshare_financial, "fetch_financial_indicators", lambda code: None)
    monkeypatch.setattr(
        financial_report,
        "fetch_symbol_report",
        lambda symbol, **kw: {
            "report_period": "2025-12-31",
            "doc_type": "annual",
            "content": (
                "单位：元币种：人民币营业收入86,241,940,222.2084,491,870,566.52"
                "归属于上市公司股东的净利润34,502,809,176.3932,496,172,808.65"
            ),
        },
    )

    provider_map, transform_map = adapter_chain_slots(DOMAIN_FINANCIAL_INDICATOR)
    cache_key = "fin_indicator_unittest_fallback_600900"
    out = fetch_with_fallback(
        "financial_indicator",
        provider_map,
        cache_key,
        get_ttl("fin_indicator", cache_key),
        fn_kwargs={"code": "600900"},
        transform=transform_map,
    )

    assert out is not None
    assert out["source_api"] == "datasink_indicator"
    assert out["revenue"] == pytest.approx(86_241_940_222.20)
    assert out["net_profit_yoy"] == pytest.approx(0.0617)


def test_chain_returns_none_when_both_unavailable(monkeypatch):
    """主源与解析支路均不可用时返回 None（不抛异常）。"""
    from src.python.cache import get_ttl
    from src.python.fetcher import financial_report
    from src.python.fetcher.chain import fetch_with_fallback
    from src.python.fetcher.source_adapter import adapter_chain_slots
    from src.python.providers import akshare_financial

    monkeypatch.setattr(akshare_financial, "fetch_financial_indicators", lambda code: None)
    monkeypatch.setattr(financial_report, "fetch_symbol_report", lambda symbol, **kw: None)

    provider_map, transform_map = adapter_chain_slots(DOMAIN_FINANCIAL_INDICATOR)
    cache_key = "fin_indicator_unittest_both_down"
    out = fetch_with_fallback(
        "financial_indicator",
        provider_map,
        cache_key,
        get_ttl("fin_indicator", cache_key),
        fn_kwargs={"code": "600900"},
        transform=transform_map,
    )
    assert out is None


class TestIndicatorSeries:
    """多期序列取数（主源多期 / 降级单期 / 缓存 / 价格映射）。"""

    def test_main_source_multiperiod(self, monkeypatch):
        from src.python.fetcher import financial_indicator as fi
        from src.python.providers import akshare_financial

        records = [
            {"report_period": "2025-12-31", "revenue": 130.0},
            {"report_period": "2024-12-31", "revenue": 100.0},
        ]
        monkeypatch.setattr(akshare_financial, "fetch_financial_indicator_history", lambda code, limit=8: records)
        assert fi.fetch_indicator_series("600900") == records

    def test_fallback_to_chain_single_period(self, monkeypatch):
        """主源无覆盖时退化为链路单期记录（不伪造历史期）。"""
        from src.python.fetcher import financial_indicator as fi
        from src.python.providers import akshare_financial

        monkeypatch.setattr(akshare_financial, "fetch_financial_indicator_history", lambda code, limit=8: [])
        monkeypatch.setattr(fi, "fetch_latest_indicator", lambda code: {"report_period": "2025-12-31"})
        series = fi.fetch_indicator_series("600900")
        assert [r["report_period"] for r in series] == ["2025-12-31"]

    def test_series_cached_across_calls(self, monkeypatch):
        from src.python.fetcher import financial_indicator as fi
        from src.python.providers import akshare_financial

        calls = {"n": 0}

        def _history(code, limit=8):
            calls["n"] += 1
            return [{"report_period": "2025-12-31"}]

        monkeypatch.setattr(akshare_financial, "fetch_financial_indicator_history", _history)
        fi.fetch_indicator_series("600900")
        fi.fetch_indicator_series("600900")
        assert calls["n"] == 1

    def test_non_a_share_returns_empty_without_request(self, monkeypatch):
        from src.python.fetcher import financial_indicator as fi
        from src.python.providers import akshare_financial

        called = {"n": 0}

        def _history(code, limit=8):
            called["n"] += 1
            return []

        monkeypatch.setattr(akshare_financial, "fetch_financial_indicator_history", _history)
        assert fi.fetch_indicator_series("7203") == []
        assert called["n"] == 0

    def test_collect_price_map_skips_bad_prices(self):
        from types import SimpleNamespace

        from src.python.fetcher.financial_indicator import collect_price_map

        details = [
            SimpleNamespace(code="600900", price=28.5),
            SimpleNamespace(code="000001", price=0),
            SimpleNamespace(code="600519", price="bad"),
            SimpleNamespace(code="", price=10.0),
            SimpleNamespace(code="601398", price=5.2),
        ]
        assert collect_price_map(details) == {"600900": 28.5, "601398": 5.2}
        assert collect_price_map(None) == {}


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


class TestIndicatorUsageMarking:
    """财务指标域取数须打「本次取用」标记（主源与解析支路分别标记）。"""

    def _keys(self):
        from src.python.report.data_status import get_tracker

        return [e["source_key"] for e in get_tracker().get_log()]

    def test_main_source_marks_used(self, monkeypatch):
        from src.python.fetcher import financial_indicator as fi
        from src.python.providers import akshare_financial

        monkeypatch.setattr(
            akshare_financial,
            "fetch_financial_indicator_history",
            lambda code, limit=8: [{"report_period": "2025-12-31"}],
        )
        fi.fetch_indicator_series("600900")
        assert "fin_indicator_akshare_financial" in self._keys()

    def test_fallback_delegates_to_latest_indicator(self, monkeypatch):
        """主源无覆盖 → 委派链路取单期记录（取用标记由链路段负责）。"""
        from src.python.fetcher import financial_indicator as fi
        from src.python.providers import akshare_financial

        calls = {"n": 0}

        def _latest(code):
            calls["n"] += 1
            return {"report_period": "2025-12-31", "source_api": "datasink_indicator"}

        monkeypatch.setattr(akshare_financial, "fetch_financial_indicator_history", lambda code, limit=8: [])
        monkeypatch.setattr(fi, "fetch_latest_indicator", _latest)
        assert fi.fetch_indicator_series("600900")[0]["source_api"] == "datasink_indicator"
        assert calls["n"] == 1

    def test_chain_path_marks_source_from_record(self, monkeypatch):
        """链路单期路径按记录的 source_api 打标（解析支路也算本次取用）。"""
        from src.python.fetcher import financial_indicator as fi

        monkeypatch.setattr("src.python.fetcher.source_adapter.adapter_chain_slots", lambda domain: ({}, {}))
        monkeypatch.setattr(
            "src.python.fetcher.chain.fetch_with_fallback",
            lambda *a, **k: {"report_period": "2025-12-31", "source_api": "datasink_indicator"},
        )
        assert fi.fetch_latest_indicator("600900") is not None
        assert "fin_indicator_datasink_indicator" in self._keys()

    def test_no_data_marks_nothing(self, monkeypatch):
        from src.python.fetcher import financial_indicator as fi
        from src.python.providers import akshare_financial

        monkeypatch.setattr(akshare_financial, "fetch_financial_indicator_history", lambda code, limit=8: [])
        monkeypatch.setattr(fi, "fetch_latest_indicator", lambda code: None)
        assert fi.fetch_indicator_series("600900") == []
        assert self._keys() == []
