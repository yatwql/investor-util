"""市场情绪报告层装配单元测试（开关门禁 / 凭据门禁 / 取数缓存 / 契约装配）。

运行：
  pytest src/test/unit/report/test_market_sentiment.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.python.fetcher import market_sentiment as fms
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
    """patch 报告层持有的网关函数绑定（调用点所在模块属忢，见 CLAUDE.md patch 纪律）。"""
    calls = {"lhb": 0, "ladder": 0}
    if missing:
        monkeypatch.setattr(ms, "_credential_missing", lambda: object())
    else:
        monkeypatch.setattr(ms, "_credential_missing", lambda: None)
        monkeypatch.setattr(
            ms, "_fetch_dragon_tiger", lambda: calls.__setitem__("lhb", calls["lhb"] + 1) or lhb
        )
        monkeypatch.setattr(
            ms, "_fetch_limit_up_ladder", lambda: calls.__setitem__("ladder", calls["ladder"] + 1) or ladder
        )
    monkeypatch.setattr("src.python.report.data_status.mark_data_used", lambda key: None, raising=False)
    return calls, {}


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

    def test_fetch_routed_via_gateway(self, monkeypatch):
        """报告层不触缓存/链路细节，取数全部经 fetcher 网关函数（Provider Chain 必经约束）。"""
        _enable(monkeypatch, True)
        calls, _ = _patch_sources(monkeypatch)
        ms.build_market_sentiment_data([_holding()], None)
        assert calls == {"lhb": 1, "ladder": 1}
        # 报告层已无取/缓存私有实现（取数细节收敛到 fetcher 内聚层）
        assert not hasattr(ms, "_fetch_cached")

    def test_gateway_caches_via_chain(self, monkeypatch):
        """网关的缓存/熔断/降级由 fetch_with_fallback 承担（缓存命中不再发请求）。"""
        calls: list[tuple] = []
        monkeypatch.setattr(fms, "credential_missing", lambda: None)
        monkeypatch.setattr(
            "src.python.fetcher.market_sentiment.get_ttl", lambda data_type, key: 0.0, raising=False
        )

        def _fake_fallback(data_type, fn_map, cache_key, cache_ttl, fn_kwargs=None, **_k):
            calls.append((data_type, fn_map and list(fn_map), cache_key))
            return {"cached": True}

        monkeypatch.setattr("src.python.fetcher.chain.fetch_with_fallback", _fake_fallback)
        assert fms.fetch_dragon_tiger() == {"cached": True}
        assert calls[0][2] == fms.LHB_CACHE_KEY
        assert fms.fetch_limit_up_ladder() == {"cached": True}
        assert calls[1][2] == fms.LADDER_CACHE_KEY

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
