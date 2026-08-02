"""市场行情获取策略边缘测试 — 策略选择器集成验证。

覆盖：
- 非交易时段 → CACHE_ONLY（零 HTTP）
- 全链熔断 → CACHE_ONLY
- 链健康 + 交易时段 → LIVE_FETCH
- QDII 始终 LIVE_FETCH
- 混合类型持仓策略分组
- 空链回退（未注册 chain 时不影响业务）
"""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

import pytest

from src.python.core.models import Holding
from src.python.core.provider_registry import FetchStrategy, get_registry
from src.python.report import market_value as mv

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]

# ── 测试数据 ────────────────────────────────────────────────

_TENCENT_DATA = {
    "name": "电池ETF", "code": "561910",
    "price": 10.5, "yesterday_close": 10.0,
    "price_date": "2026-06-26",
    "source_api": "tencent", "source": "腾讯财经",
}

_EASTMONEY_DATA = {
    "name": "中欧医疗健康混合C", "code": "003095",
    "price": 1.5, "yesterday_close": 1.48,
    "price_date": "2026-06-25",
    "source_api": "eastmoney", "source": "东方财富",
}

_QDII_DATA = {
    "name": "华夏纳斯达克100ETF(QDII)", "code": "513300",
    "price": 1.6, "yesterday_close": 1.55,
    "price_date": "2026-06-25",
    "source_api": "tencent", "source": "腾讯财经",
}


def _setup_registry() -> None:
    """初始化 registry 的默认 chain。"""
    reg = get_registry()
    reg.register_default_chains()


# ════════════════════════════════════════════════════════════
# 策略选择
# ════════════════════════════════════════════════════════════


class TestStrategyMarketClosed:
    """非交易时段：CACHE_ONLY → 走缓存，不发起 HTTP。"""

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-06-26")
    @patch("src.python.report.market_value.fetch_market_data")
    def test_a_share_cache_only_skips_http(self, mock_fetch, mock_ltd, mock_open):
        """非交易时段，A 股持仓走缓存，fetch_market_data 不被调用。

        注意：mock get_last_trading_day 使缓存 price_date 与最近交易日一致，
        避免 _price_cache_fresh 因真实日期判定缓存过期而降级 live。
        """
        _setup_registry()
        # 预填 session cache
        get_registry().session_cache_set("price", "561910", _TENCENT_DATA, source="test")

        holdings = [Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)]
        details = mv._generate_details(holdings, "2026-06-26")

        mock_fetch.assert_not_called()
        assert len(details) == 1
        # session cache 数据应被正确读取
        assert details[0].price == 10.5
        assert details[0].source_api == "tencent"

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.fetch_market_data", return_value=None)
    def test_cache_only_fallback_to_file_cache(self, mock_fetch, mock_open):
        """非交易时段，session cache 未命中时回退到 file cache → 仍无数据。"""
        _setup_registry()

        h = Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)
        # session cache 为空 → 回退 LIVE_FETCH → fetch 返回 None → 标注"无数据"
        details = mv._generate_details([h], "2026-06-26")

        mock_fetch.assert_called_once_with("561910", "电池ETF")
        assert len(details) == 1
        # 无缓存数据 → price=0, source="无数据"
        assert details[0].price == 0.0
        assert details[0].source == "无数据"
        assert details[0].price_type == "暂无行情"


class TestStrategyCircuitBreaker:
    """全链熔断 → CACHE_ONLY。"""

    @patch("src.python.report.market_value.is_market_open", return_value=True)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-06-26")
    @patch("src.python.report.market_value.fetch_market_data")
    @patch("src.python.core.provider_registry.time")
    def test_chain_broken_reads_cache(self, mock_time, mock_fetch, mock_ltd, mock_open):
        """交易时段但全链熔断，A 股持仓走缓存。

        注意：mock get_last_trading_day 使 _price_cache_fresh 在真实收市
        （周末/非交易时段）也不判定缓存过期，聚焦熔断→CACHE_ONLY 行为本身。
        """
        _setup_registry()
        reg = get_registry()
        # 模拟全链熔断（tencent + eastmoney 各 3 次失败）
        mock_time.time.return_value = 1000.0
        for p in ("tencent", "eastmoney"):
            reg.record_failure(p, "timeout")
            reg.record_failure(p, "timeout")
            reg.record_failure(p, "timeout")
        # 预填 session cache
        reg.session_cache_set("price", "561910", _TENCENT_DATA, source="test")

        holdings = [Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)]
        details = mv._generate_details(holdings, "2026-06-26")

        mock_fetch.assert_not_called()
        assert len(details) == 1
        assert details[0].price == 10.5


class TestStrategyHealthyChain:
    """链健康 + 交易时段 → LIVE_FETCH。"""

    @patch("src.python.report.market_value.is_market_open", return_value=True)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-06-26")
    @patch("src.python.report.market_value.fetch_market_data")
    def test_healthy_chain_live_fetch(self, mock_fetch, mock_ltd, mock_midday, mock_open):
        """交易时段 + 链健康 → 调用 fetch_market_data。"""
        _setup_registry()
        mock_fetch.return_value = _TENCENT_DATA

        holdings = [Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)]
        details = mv._generate_details(holdings, "2026-06-26")

        mock_fetch.assert_called_once_with("561910", "电池ETF")
        assert len(details) == 1
        assert details[0].price == 10.5
        assert details[0].source == "腾讯财经"


class TestStrategyQDII:
    """QDII 不受交易时段/熔断影响，始终 LIVE_FETCH。"""

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-06-26")
    @patch("src.python.report.market_value.fetch_market_data")
    def test_qdii_live_fetch_when_market_closed(self, mock_fetch, mock_ltd, mock_midday, mock_open):
        """非交易时段，QDII 仍调用 fetch_market_data。"""
        _setup_registry()
        mock_fetch.return_value = _QDII_DATA

        holdings = [Holding("证券账户", "华夏纳斯达克100ETF(QDII)", "513300", 100.0, 1.5)]
        details = mv._generate_details(holdings, "2026-06-26")

        mock_fetch.assert_called_once()
        assert details[0].price == 1.6


class TestStrategyMixed:
    """混合类型持仓：各类型按各自策略获取。"""

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-06-26")
    @patch("src.python.report.market_value.fetch_market_data")
    def test_mixed_qdii_and_a_share(self, mock_fetch, mock_ltd, mock_midday, mock_open):
        """非交易时段：A 股走缓存，QDII 走 HTTP。"""
        _setup_registry()
        reg = get_registry()
        # 预填 A 股缓存
        reg.session_cache_set("price", "561910", _TENCENT_DATA, source="test")
        mock_fetch.return_value = _QDII_DATA

        holdings = [
            Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0),
            Holding("证券账户", "华夏纳斯达克100ETF(QDII)", "513300", 100.0, 1.5),
        ]
        details = mv._generate_details(holdings, "2026-06-26")

        # QDII 走 HTTP，A 股走缓存
        mock_fetch.assert_called_once()
        assert len(details) == 2
        # A 股从缓存读取
        a_detail = next(d for d in details if d.code == "561910")
        assert a_detail.price == 10.5
        # QDII 从 mock 读取
        qdii_detail = next(d for d in details if d.code == "513300")
        assert qdii_detail.price == 1.6
        mock_fetch.assert_called_with("513300", "华夏纳斯达克100ETF(QDII)")


class TestStrategyEmptyChain:
    """空 chain（未注册）→ 回退 LIVE_FETCH，不影响业务。"""

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.is_midday_break", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-06-26")
    @patch("src.python.report.market_value.fetch_market_data")
    def test_empty_chain_defaults_to_live_fetch(self, mock_fetch, mock_ltd, mock_midday, mock_open):
        """不调用 register_default_chains 时，chain 为空 → 回退 LIVE_FETCH。"""
        # 注意：不设置 registry chain
        mock_fetch.return_value = _TENCENT_DATA

        holdings = [Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)]
        details = mv._generate_details(holdings, "2026-06-26")

        mock_fetch.assert_called_once()
        assert len(details) == 1


class TestStrategyLogging:
    """策略选择日志和计数。"""

    @patch("src.python.report.market_value.is_market_open", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-06-26")
    @patch("src.python.report.market_value.fetch_market_data")
    def test_cache_only_logged_no_http(self, mock_fetch, mock_ltd, mock_open, caplog):
        """CACHE_ONLY 路径不产生 HTTP 调用日志，不统计为失败。

        注意：mock get_last_trading_day 避免 _price_cache_fresh 因真实日期
        判定缓存过期而降级 live（与 test_a_share_cache_only_skips_http 同理）。
        """
        _setup_registry()
        import logging
        caplog.set_level(logging.INFO)
        # 预填 session cache
        get_registry().session_cache_set("price", "561910", _TENCENT_DATA, source="test")

        holdings = [Holding("证券账户", "电池ETF", "561910", 1000.0, 1.0)]
        mv._generate_details(holdings, "2026-06-26")

        mock_fetch.assert_not_called()
        # 应有"全部成功"日志（因为缓存命中）
        assert any("全部" in msg for msg in caplog.messages)
