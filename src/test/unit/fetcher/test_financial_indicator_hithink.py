"""财务指标域「同花顺官方报表派生」链路单元测试（第三链路）。

覆盖：适配器抓取三张报表并归一为标准字段、非 A 股跳过、链路顺序、
主源不可用时序列回退（官方报表派生多期）与数据使用标记。

运行：
  pytest src/test/unit/fetcher/test_financial_indicator_hithink.py -v
"""

from __future__ import annotations

from unittest import mock

import pytest

from src.python.fetcher import financial_indicator_adapters as fia
from src.python.fetcher import source_adapter

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

_MS_2026Q2 = 1782748800000  # 2026-06-30


def _income(revenue: float = 37_929_268_927.18, net_profit: float = 14_755_694_774.53, cost: float = 15_971_160_694.54):
    return {
        "item": [
            {
                "fiscal_year": "2026",
                "fiscal_period": "Q2",
                "period_end_ms": _MS_2026Q2,
                "operating_income": revenue,
                "parent_holder_net_profit": net_profit,
                "operating_costs": cost,
                "basic_eps": 0.6031,
            }
        ]
    }


def _balance():
    return {
        "item": [
            {
                "fiscal_year": "2026",
                "fiscal_period": "Q2",
                "period_end_ms": _MS_2026Q2,
                "assets_total": 600_000_000_000.0,
                "total_debt": 356_190_000_000.0,
                "holder_equity_total": 228_000_000_000.0,
            }
        ]
    }


def _cashflow():
    return {
        "item": [
            {
                "fiscal_year": "2026",
                "fiscal_period": "Q2",
                "period_end_ms": _MS_2026Q2,
                "act_cash_flow_net": 24_128_313_774.37,
            }
        ]
    }


class TestHithinkIndicatorAdapter:
    """适配器：三张报表 → 标准字段记录（链条单期契约）。"""

    def _patch(self, monkeypatch, **overrides):
        calls: list[tuple[str, str]] = []

        def _income_fn(symbol, **kw):
            calls.append(("income", symbol))
            return overrides.get("income", _income())

        def _balance_fn(symbol, **kw):
            calls.append(("balance", symbol))
            return overrides.get("balance", _balance())

        def _cashflow_fn(symbol, **kw):
            calls.append(("cashflow", symbol))
            return overrides.get("cashflow", _cashflow())

        monkeypatch.setattr(fia.hithink, "fetch_income_statements", _income_fn)
        monkeypatch.setattr(fia.hithink, "fetch_balance_sheets", _balance_fn)
        monkeypatch.setattr(fia.hithink, "fetch_cash_flow_statements", _cashflow_fn)
        return calls

    def test_extract_returns_latest_standard_record(self, monkeypatch):
        calls = self._patch(monkeypatch)
        raw = fia.HithinkIndicatorAdapter().extract_data({"code": "600900"})
        assert [c[0] for c in calls] == ["income", "balance", "cashflow"]
        assert all(c[1] == "600900.SH" for c in calls)
        assert raw["report_period"] == "2026-06-30"
        assert raw["revenue"] == pytest.approx(37_929_268_927.18)
        assert raw["gross_margin"] == pytest.approx(0.578923, abs=1e-5)

    def test_transform_data_yields_standard_fields_only(self, monkeypatch):
        self._patch(monkeypatch)
        adapter = fia.HithinkIndicatorAdapter()
        raw = adapter.extract_data({"code": "600900"})
        record = adapter.transform_data(raw, source=adapter.display_name)
        assert set(record) == set(adapter.standard_fields())
        assert record["source_api"] == "hithink"
        assert record["source"] == "同花顺金融数据"
        assert record["code"] == "600900"

    def test_non_a_share_code_skips_without_requests(self, monkeypatch):
        calls = self._patch(monkeypatch)
        assert fia.HithinkIndicatorAdapter().extract_data({"code": "AAPL"}) is None
        assert calls == []

    def test_missing_table_returns_none(self, monkeypatch):
        """任一张报表缺失 → None（不由链路之外的半份数据冒充记录）。"""
        self._patch(monkeypatch, cashflow={"item": []})
        assert fia.HithinkIndicatorAdapter().extract_data({"code": "600900"}) is None

    def test_adapter_self_test_passes(self):
        """契约自检（域/标识声明齐备、输出恰好标准字段集）。"""
        assert fia.HithinkIndicatorAdapter().self_test() == []

    def test_registered_in_domain(self):
        adapters = source_adapter.ADAPTER_REGISTRY["financial_indicator"]
        assert "hithink" in adapters
        assert adapters["hithink"].display_name == "同花顺金融数据"


class TestChainOrderAndSeriesFallback:
    def test_chain_order(self):
        from src.python.fetcher.chain import _get_chain

        assert _get_chain("financial_indicator") == ["akshare_financial", "datasink_indicator", "hithink"]

    def test_series_falls_back_to_hithink_when_primary_empty(self, monkeypatch):
        """主源无数据 → 官方报表派生多期序列，并打「本次使用」标记。"""
        from src.python.fetcher import financial_indicator as fi

        derived = [
            {"code": "600900", "report_period": "2026-06-30", "source_api": "hithink"},
            {"code": "600900", "report_period": "2026-03-31", "source_api": "hithink"},
        ]
        marked: list[str] = []
        monkeypatch.setattr(fi, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fi, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fi.akshare_financial, "fetch_financial_indicator_history", lambda code, limit: [])
        monkeypatch.setattr(fi, "fetch_hithink_indicator_series", lambda code, limit: derived)
        monkeypatch.setattr(
            "src.python.report.data_status.mark_data_used", lambda key: marked.append(key), raising=False
        )

        records = fi.fetch_indicator_series("600900")
        assert records == derived
        assert any("hithink" in m for m in marked)

    def test_series_prefers_primary_when_available(self, monkeypatch):
        from src.python.fetcher import financial_indicator as fi

        primary = [{"code": "600900", "report_period": "2026-06-30", "source_api": "akshare_financial"}]
        called: list[int] = []
        monkeypatch.setattr(fi, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(fi, "cache_set", lambda *a, **k: None)
        monkeypatch.setattr(fi.akshare_financial, "fetch_financial_indicator_history", lambda code, limit: primary)
        monkeypatch.setattr(fi, "fetch_hithink_indicator_series", lambda code, limit: called.append(1) or [])
        monkeypatch.setattr("src.python.report.data_status.mark_data_used", lambda key: None, raising=False)

        assert fi.fetch_indicator_series("600900") == primary
        assert called == []  # 主源可用时不得触碰备源

    def test_hithink_series_skips_non_a_share(self, monkeypatch):
        from src.python.fetcher import financial_indicator as fi

        with mock.patch("src.python.providers.hithink.to_thscode", return_value=""):
            assert fi.fetch_hithink_indicator_series("AAPL") == []
