"""Rf 获取器测试用例 — P1-15。

测试场景：
  1. mock bond_zh_us_rate 正常返回 → 提取 0.017404
  2. mock akshare 异常 → 降级到用户配置
  3. mock 用户配置 Rf=0.02 → 跳过 fetcher 直接返回
  4. 缓存命中测试
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class TestBondYieldFetcher:
    """bond_yield.py 获取器单元测试。"""

    # ── 测试数据 ──────────────────────────────────────────────

    @staticmethod
    def _make_mock_df() -> pd.DataFrame:
        """构造模拟的 bond_zh_us_rate() 返回值。

        DataFrame 列结构：
          col 0: 日期（str）
          col 1: 中国国债收益率2年
          col 2: 中国国债收益率5年
          col 3: 中国国债收益率10年
          col 4: 中国国债收益率30年
        """
        columns = [
            "日期",
            "中国国债收益率2年",
            "中国国债收益率5年",
            "中国国债收益率10年",
            "中国国债收益率30年",
            "中国国债收益率10年-2年",
            "中国GDP同比增长",
            "美国国债收益率2年",
            "美国国债收益率5年",
            "美国国债收益率10年",
            "美国国债收益率30年",
            "美国国债收益率10年-2年",
            "美国GDP同比增长",
        ]
        data = [
            ["2026-07-17", 1.2645, 1.4466, 1.7404, 2.2425, 0.4759, None,
             4.18, 4.28, 4.55, 5.06, 0.37, None],
        ]
        return pd.DataFrame(data, columns=columns)

    @staticmethod
    def _make_empty_df() -> pd.DataFrame:
        """构造空的 DataFrame。"""
        return pd.DataFrame()

    # ── 场景 1：正常返回 ──────────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_normal_fetch(
        self,
        mock_bond_rate: MagicMock,
        mock_get_config: MagicMock,
        mock_cache_get: MagicMock,
    ):
        """mock bond_zh_us_rate 正常返回 → 提取 0.017404。"""
        mock_cache_get.return_value = None
        mock_get_config.return_value = {"risk_free_rate": None}
        mock_bond_rate.return_value = self._make_mock_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is not None
        assert abs(rf - 0.017404) < 1e-6, f"期望 0.017404，实际 {rf}"

    # ── 场景 2：akshare 异常 → 降级到用户配置 ─────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_akshare_fallback_to_config(
        self,
        mock_bond_rate: MagicMock,
        mock_get_config: MagicMock,
        mock_cache_get: MagicMock,
    ):
        """mock akshare 异常 → 降级到用户配置。"""
        mock_cache_get.return_value = None
        mock_get_config.return_value = {"risk_free_rate": 0.025}
        mock_bond_rate.side_effect = RuntimeError("API 不可用")

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is not None
        assert abs(rf - 0.025) < 1e-6, f"期望 0.025，实际 {rf}"

    # ── 场景 3：用户配置优先 ─────────────────────────────────

    @patch("src.python.fetcher.bond_yield.get_config")
    def test_config_priority(self, mock_get_config: MagicMock):
        """mock 用户配置 Rf=0.02 → 跳过 fetcher 直接返回。"""
        mock_get_config.return_value = {"risk_free_rate": 0.02}

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate()
        assert rf is not None
        assert abs(rf - 0.02) < 1e-6, f"期望 0.02，实际 {rf}"

    # ── 场景 4：缓存命中 ─────────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    def test_cache_hit(
        self,
        mock_get_config: MagicMock,
        mock_cache_get: MagicMock,
    ):
        """缓存命中 → 不触发网络请求，直接返回缓存值。"""
        mock_cache_get.return_value = 0.030
        mock_get_config.return_value = {"risk_free_rate": None}

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=True)
        assert rf is not None
        assert abs(rf - 0.030) < 1e-6, f"期望 0.030，实际 {rf}"
        mock_cache_get.assert_called_once()

    # ── 场景 5：用户配置为百分比格式 ─────────────────────────

    @patch("src.python.fetcher.bond_yield.get_config")
    def test_config_percentage_auto_convert(self, mock_get_config: MagicMock):
        """用户配置填 1.74（百分比）→ 自动转为 0.0174。"""
        mock_get_config.return_value = {"risk_free_rate": 1.74}

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate()
        assert rf is not None
        assert abs(rf - 0.0174) < 1e-6, f"期望 0.0174，实际 {rf}"

    # ── 场景 6：全部数据源不可用 → None ──────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_all_sources_unavailable(
        self,
        mock_bond_rate: MagicMock,
        mock_get_config: MagicMock,
        mock_cache_get: MagicMock,
    ):
        """全部不可用 → 返回 None。"""
        mock_cache_get.return_value = None
        mock_get_config.return_value = {"risk_free_rate": None}
        mock_bond_rate.side_effect = RuntimeError("API 不可用")

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None

    # ── 场景 7：空 DataFrame ─────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_empty_dataframe(
        self,
        mock_bond_rate: MagicMock,
        mock_get_config: MagicMock,
        mock_cache_get: MagicMock,
    ):
        """bond_zh_us_rate 返回空 DataFrame → 返回 None。"""
        mock_cache_get.return_value = None
        mock_get_config.return_value = {"risk_free_rate": None}
        mock_bond_rate.return_value = self._make_empty_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None

    # ── 场景 8：NaN 值处理 ───────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_nan_value(
        self,
        mock_bond_rate: MagicMock,
        mock_get_config: MagicMock,
        mock_cache_get: MagicMock,
    ):
        """最新值为 NaN → 返回 None。"""
        mock_cache_get.return_value = None
        mock_get_config.return_value = {"risk_free_rate": None}
        df = self._make_mock_df()
        df.iloc[-1, 3] = None  # 将 10Y 收益率设为 None
        mock_bond_rate.return_value = df

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None
