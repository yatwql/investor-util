"""缓存编排下沉 cache.operations：update_all / warm 预热 / stats 载荷单源。

三处原为渠道内编排（CLI 最大努力聚合、TUI 新资产预热、Web 统计载荷组装），
现下沉共享层——本文件锁定其行为与「渠道只调用不编排」的回归基础。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.python.cache.operations import get_cache_stats_payload, update_all_cache, warm_new_asset_caches

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class _Holder:
    """最小持仓替身（warm 需要 code/name 属性）。"""

    def __init__(self, code: str, name: str):
        self.code = code
        self.name = name


class TestUpdateAllCache:
    """最大努力模式：basic 失败仍执行 position，退出码取最大值。"""

    def test_exit_code_is_max_of_both(self):
        with (
            patch(
                "src.python.cache.operations.update_basic_cache",
                return_value=SimpleNamespace(exit_code=0),
            ) as m_basic,
            patch(
                "src.python.cache.operations.update_position_cache",
                return_value=SimpleNamespace(exit_code=3),
            ) as m_pos,
        ):
            code = update_all_cache([_Holder("1", "x")], MagicMock())
        assert code == 3
        m_basic.assert_called_once()
        m_pos.assert_called_once()

    def test_basic_failure_still_runs_position(self):
        with (
            patch(
                "src.python.cache.operations.update_basic_cache",
                return_value=SimpleNamespace(exit_code=3),
            ) as m_basic,
            patch(
                "src.python.cache.operations.update_position_cache",
                return_value=SimpleNamespace(exit_code=0),
            ) as m_pos,
        ):
            code = update_all_cache([], MagicMock())
        assert code == 3
        m_basic.assert_called_once()
        m_pos.assert_called_once()


class TestWarmNewAssetCaches:
    """预热编排在共享层：变更检测 → 行情/基金 → 行业；异常不阻断。"""

    @patch("src.python.report.fund_performance.is_fund", return_value=False)
    @patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={"SH510300": {"industry": "指数"}})
    @patch("src.python.fetcher.price.fetch_market_data", return_value={"price": 4.2})
    @patch("src.python.cache.check_and_refresh_caches", return_value=["SH510300"])
    def test_warms_new_code(self, mock_refresh, mock_price, mock_industry, mock_is_fund):
        reporter = MagicMock()
        holders = [_Holder("SH510300", "沪深300ETF")]
        result = warm_new_asset_caches(holders, reporter)
        assert result == ["SH510300"]
        mock_refresh.assert_called_once_with(holders)
        mock_price.assert_called_once_with("SH510300", "沪深300ETF")
        mock_industry.assert_called_once_with(["SH510300"])

    @patch("src.python.cache.check_and_refresh_caches", return_value=[])
    def test_no_new_codes_returns_empty(self, mock_refresh):
        reporter = MagicMock()
        assert warm_new_asset_caches([], reporter) == []
        mock_refresh.assert_called_once()
        reporter.info.assert_not_called()

    @patch("src.python.fetcher.price.fetch_market_data", side_effect=RuntimeError("net down"))
    @patch("src.python.cache.check_and_refresh_caches", return_value=["SH1"])
    def test_fetcher_exception_does_not_block(self, mock_refresh, mock_price):
        reporter = MagicMock()
        result = warm_new_asset_caches([_Holder("SH1", "x")], reporter)
        # 异常被吞（不阻断后续生成），返回已检测到的新增码
        assert result == ["SH1"]


class TestStatsPayload:
    """GET /api/cache 载荷单源组装：契约键、保序数组、top 截断。"""

    @patch("src.python.cache.cleanup_expired", return_value=7)
    @patch("src.python.cache.get_cache_hit_rate", return_value={"hit": 5, "miss": 1, "hit_rate": 0.83})
    @patch(
        "src.python.cache.get_cache_stats",
        return_value={
            "total_files": 42,
            "total_size_bytes": 1024,
            "by_prefix": {"price": 3, "fund": 10, "industry": 5},
            "top_by_size": [{"name": f"f{i}", "size": i} for i in range(10)],
        },
    )
    def test_payload_contract(self, mock_stats, mock_rate, mock_expired):
        payload = get_cache_stats_payload()
        assert payload["total_files"] == 42
        assert payload["total_size_bytes"] == 1024
        # by_prefix = 二维数组、按文件数降序（保序下发，防 Flask sort_keys 重排）
        assert payload["by_prefix"] == [["fund", 10], ["industry", 5], ["price", 3]]
        # top_by_size 截断前 5
        assert len(payload["top_by_size"]) == 5
        assert payload["hit_rate"] == {"hit": 5, "miss": 1, "hit_rate": 0.83}
        assert payload["expired_count"] == 7
        # 契约键完整（双向相等，不写死新增键）
        assert set(payload) == {
            "total_files",
            "total_size_bytes",
            "by_prefix",
            "top_by_size",
            "hit_rate",
            "expired_count",
        }

    @patch("src.python.cache.cleanup_expired", return_value=0)
    @patch("src.python.cache.get_cache_hit_rate", return_value={})
    @patch("src.python.cache.get_cache_stats", return_value={})
    def test_payload_defaults_on_empty_stats(self, mock_stats, mock_rate, mock_expired):
        payload = get_cache_stats_payload()
        assert payload["total_files"] == 0
        assert payload["by_prefix"] == []
        assert payload["top_by_size"] == []
        # json 可序列化（前端契约）
        assert json.dumps(payload, ensure_ascii=False)
