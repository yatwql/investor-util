"""市场情绪报告层装配单元测试（开关门禁 / 凭据门禁 / 取数缓存 / 契约装配）。

运行：
  pytest src/test/unit/report/test_market_sentiment.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.python.report import market_sentiment as ms

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _holding(code="600900", name="长江电力"):
    return SimpleNamespace(code=code, name=name)


_LHB = {
    "trade_date": "2026-09-16",
    "stock_count": 63,
    "stock_items": [{"ticker": "600900", "name": "长江电力", "net_value": 100_000_000.0}],
}
_LADDER = {"window": {"date_list": ["2026-09-16"], "board_caps": {"two_board": 4}}, "item": []}


def _enable(monkeypatch, on: bool = True):
    from src.python.config.features import set_feature_enabled

    set_feature_enabled("market_sentiment", on)


def _patch_sources(monkeypatch, lhb=_LHB, ladder=_LADDER, cached=None, missing: bool = False):
    calls = {"lhb": 0, "ladder": 0}
    if missing:
        monkeypatch.setattr(ms.hithink, "missing_credential", lambda _sid: object())
    else:
        monkeypatch.setattr(ms.hithink, "missing_credential", lambda _sid: None)
        monkeypatch.setattr(
            ms.hithink, "fetch_dragon_tiger_list", lambda board="all": calls.__setitem__("lhb", calls["lhb"] + 1) or lhb
        )
        monkeypatch.setattr(
            ms.hithink, "fetch_limit_up_ladder", lambda: calls.__setitem__("ladder", calls["ladder"] + 1) or ladder
        )
    monkeypatch.setattr(ms, "cache_get", lambda key, ttl: (cached or {}).get(key))
    written: dict = {}
    monkeypatch.setattr(ms, "cache_set", lambda key, value: written.__setitem__(key, value))
    monkeypatch.setattr("src.python.report.data_status.mark_data_used", lambda key: None, raising=False)
    return calls, written


class TestGates:
    def test_switch_off_returns_none(self, monkeypatch):
        _enable(monkeypatch, False)
        assert ms.build_market_sentiment_data([_holding()], None) is None

    def test_missing_credential_returns_guide(self, monkeypatch):
        _enable(monkeypatch, True)
        _patch_sources(monkeypatch, missing=True)
        out = ms.build_market_sentiment_data([_holding()], None)
        assert out["available"] is False and "同花顺" in out["reason"]


class TestAssembly:
    def test_hit_rows_and_summary(self, monkeypatch):
        _enable(monkeypatch, True)
        _patch_sources(monkeypatch)
        out = ms.build_market_sentiment_data([_holding()], [{"name": "中际旭创", "codes": ["300308"]}])
        assert out["available"] is True
        assert out["rows"][0]["code"] == "600900"
        assert out["rows"][0]["holding_kind"] == "直接持有"
        assert out["summary"]["lhb_stock_count"] == 63

    def test_sources_cached_after_first_fetch(self, monkeypatch):
        """首次取数写缓存；缓存命中时不再请求（按 key 精确断言）。"""
        _enable(monkeypatch, True)
        calls, written = _patch_sources(monkeypatch)
        ms.build_market_sentiment_data([_holding()], None)
        assert calls == {"lhb": 1, "ladder": 1}
        assert ms._LHB_CACHE_KEY in written and ms._LADDER_CACHE_KEY in written

        calls2, _ = _patch_sources(monkeypatch, cached={ms._LHB_CACHE_KEY: _LHB, ms._LADDER_CACHE_KEY: _LADDER})
        out = ms.build_market_sentiment_data([_holding()], None)
        assert calls2 == {"lhb": 0, "ladder": 0}
        assert out["available"] is True

    def test_no_hits_degrades(self, monkeypatch):
        _enable(monkeypatch, True)
        _patch_sources(monkeypatch, lhb={}, ladder={})
        out = ms.build_market_sentiment_data([_holding()], None)
        assert out["available"] is False


class TestFeatureRegistry:
    def test_switch_registered_in_report_group(self):
        from src.python.config.features import GROUP_REPORT, feature_switch_registry

        entry = feature_switch_registry["market_sentiment"]
        assert entry.group == GROUP_REPORT
        assert entry.default is False

    def test_accessor_reads_registry(self, monkeypatch):
        from src.python.config import is_enable_market_sentiment

        _enable(monkeypatch, True)
        assert is_enable_market_sentiment() is True
        _enable(monkeypatch, False)
        assert is_enable_market_sentiment() is False


class TestCacheModule:
    def test_sentiment_module_registered(self):
        from src.python.core.registry import _MODULE_REGISTRY

        entry = next(m for m in _MODULE_REGISTRY if m.data_type == "sentiment")
        assert "sentiment_" in entry.cache_prefixes
