"""指数估值历史获取器测试用例（乐咕 akshare PE/PB 月频）。

测试场景：
  1. mock PE/PB 双源正常 → 外连接合并、日期升序、非正值置 None
  2. 单源失败（PB 空）→ 保留 PE，pb=None
  3. 双源失败 → 过期缓存兜底（月频数据容忍陈旧）；无兜底 → None
  4. 熔断中 → 不发起 akshare 调用，走兜底/None
  5. 无 symbol 映射（非 sh000300）→ None 且不触达 akshare
  6. 缓存命中 → 不触达 akshare
  7. 熔断隔离回归：任何路径都不向共享 akshare 熔断键写失败/成功
     （曾把可选源失败计入共享键，会连坐无风险利率 bond_yield）
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


def _pe_df(rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["日期", "滚动市盈率"])


def _pb_df(rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["日期", "市净率"])


def _stale_cache(fresh_ttl_hit: bool = False):
    """cache_get side_effect：fresh 窗口按参量返回 None，30 天窗口返回陈旧行。"""

    def _get(key: str, ttl: float):
        from src.python.core.constants import CACHE_MONTHLY

        if ttl >= CACHE_MONTHLY and not fresh_ttl_hit:
            return [{"date": "2026-01-31", "pe": 10.0, "pb": 1.2}]
        return None

    return _get


class TestFetchIndexValuationHistory:
    """fetch_index_valuation_history 主路径与降级。"""

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("src.python.fetcher.index_valuation.cache_get", return_value=None)
    @patch("akshare.stock_index_pb_lg")
    @patch("akshare.stock_index_pe_lg")
    def test_merge_two_sources(self, mock_pe, mock_pb, _cg, _cs):
        """双源正常 → 按日期外连接合并、升序。"""
        mock_pe.return_value = _pe_df([["2026-01-31", 12.0], ["2026-02-28", 13.0]])
        mock_pb.return_value = _pb_df([["2026-01-31", 1.4], ["2026-02-28", None]])

        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        rows = fetch_index_valuation_history("sh000300")
        assert [r["date"] for r in rows] == ["2026-01-31", "2026-02-28"]
        assert rows[0] == {"date": "2026-01-31", "pe": 12.0, "pb": 1.4}
        assert rows[1]["pe"] == 13.0
        assert rows[1]["pb"] is None

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("src.python.fetcher.index_valuation.cache_get", return_value=None)
    @patch("akshare.stock_index_pb_lg")
    @patch("akshare.stock_index_pe_lg")
    def test_non_positive_filtered(self, mock_pe, mock_pb, _cg, _cs):
        """非正 PE（亏损期/异常）置 None，另一源正常时行保留。"""
        mock_pe.return_value = _pe_df([["2026-01-31", -5.0], ["2026-02-28", 12.0]])
        mock_pb.return_value = _pb_df([["2026-01-31", 1.4], ["2026-02-28", 1.5]])

        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        rows = fetch_index_valuation_history("sh000300")
        assert rows[0]["pe"] is None
        assert rows[0]["pb"] == 1.4
        assert rows[1]["pe"] == 12.0

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("src.python.fetcher.index_valuation.cache_get", return_value=None)
    @patch("akshare.stock_index_pb_lg")
    @patch("akshare.stock_index_pe_lg")
    def test_single_source_failure_keeps_other(self, mock_pe, mock_pb, _cg, _cs):
        """PB 源空 → 保留 PE 序列（pb=None），不整体缺席。"""
        mock_pe.return_value = _pe_df([["2026-01-31", 12.0]])
        mock_pb.return_value = pd.DataFrame()

        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        rows = fetch_index_valuation_history("sh000300")
        assert rows is not None
        assert [r["pe"] for r in rows] == [12.0]
        assert rows[0]["pb"] is None

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("src.python.fetcher.index_valuation.cache_get")
    @patch("akshare.stock_index_pb_lg")
    @patch("akshare.stock_index_pe_lg")
    def test_both_fail_stale_fallback(self, mock_pe, mock_pb, mock_cg, _cs):
        """双源失败 → 30 天内旧缓存兜底（月频数据容忍陈旧，防口径来回跳）。"""
        mock_pe.return_value = pd.DataFrame()
        mock_pb.return_value = pd.DataFrame()
        mock_cg.side_effect = _stale_cache()

        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        rows = fetch_index_valuation_history("sh000300")
        assert rows == [{"date": "2026-01-31", "pe": 10.0, "pb": 1.2}]

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("src.python.fetcher.index_valuation.cache_get", return_value=None)
    @patch("akshare.stock_index_pb_lg")
    @patch("akshare.stock_index_pe_lg")
    def test_both_fail_no_stale_returns_none(self, mock_pe, mock_pb, _cg, _cs):
        """双源失败且无兜底 → None（缺席，消费方回落点位分位）。"""
        mock_pe.return_value = pd.DataFrame()
        mock_pb.return_value = pd.DataFrame()

        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        assert fetch_index_valuation_history("sh000300") is None

    @patch("src.python.fetcher.index_valuation.cache_get", return_value=None)
    @patch("akshare.stock_index_pe_lg")
    def test_unknown_code_returns_none_without_ak(self, mock_pe, _cg):
        """无 symbol 映射的指数 → None，不触达 akshare（避免无谓调用）。"""
        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        assert fetch_index_valuation_history("sz399006") is None
        mock_pe.assert_not_called()

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("akshare.stock_index_pe_lg")
    @patch("src.python.fetcher.index_valuation.cache_get")
    def test_cache_hit_skips_ak(self, mock_cg, mock_pe, _cs):
        """fresh 缓存命中 → 直接返回，不触达 akshare。"""
        cached = [{"date": "2026-01-31", "pe": 10.0, "pb": 1.2}]
        mock_cg.return_value = cached

        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        assert fetch_index_valuation_history("sh000300") == cached
        mock_pe.assert_not_called()

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("src.python.fetcher.index_valuation.cache_get")
    @patch("akshare.stock_index_pb_lg")
    @patch("akshare.stock_index_pe_lg")
    def test_circuit_broken_skips_ak_with_stale(self, mock_pe, mock_pb, mock_cg, _cs):
        """熔断中 → 不发起调用；有过期缓存则兜底。"""
        mock_cg.side_effect = _stale_cache()
        from src.python.core.provider_registry import get_registry

        reg = get_registry()
        reg.register_provider("akshare")
        reg.record_failure("akshare", "test:transport")
        reg.record_failure("akshare", "test:transport")
        reg.record_failure("akshare", "test:transport")
        assert reg.is_circuit_broken("akshare")

        from src.python.fetcher.index_valuation import fetch_index_valuation_history

        rows = fetch_index_valuation_history("sh000300")
        assert rows == [{"date": "2026-01-31", "pe": 10.0, "pb": 1.2}]
        mock_pe.assert_not_called()
        mock_pb.assert_not_called()

    @patch("src.python.fetcher.index_valuation.cache_set")
    @patch("src.python.fetcher.index_valuation.cache_get", return_value=None)
    @patch("akshare.stock_index_pb_lg")
    @patch("akshare.stock_index_pe_lg")
    def test_no_breaker_writes_on_failure(self, mock_pe, mock_pb, _cg, _cs):
        """熔断隔离回归：可选源失败不得向共享 akshare 键写失败/成功。"""
        mock_pe.return_value = pd.DataFrame()
        mock_pb.return_value = pd.DataFrame()

        with patch("src.python.core.provider_registry.get_registry") as mock_reg:
            mock_reg.return_value.is_circuit_broken.return_value = False
            from src.python.fetcher.index_valuation import fetch_index_valuation_history

            assert fetch_index_valuation_history("sh000300") is None
        mock_reg.return_value.record_failure.assert_not_called()
        mock_reg.return_value.record_success.assert_not_called()
