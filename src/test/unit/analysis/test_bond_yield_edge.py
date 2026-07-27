"""Rf 获取器 edge 测试 — 缓存/配置/数据源异常路径。

覆盖 bond_yield.py 的边界场景：
  - 用户配置异常（零值/负数/非数值）
  - 缓存值类型异常
  - akshare 导入失败 / 返回异常值
  - DataFrame 结构异常
  - 通用异常兜底
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis, pytest.mark.edge]


class TestBondYieldEdge:
    """bond_yield.py edge 测试。"""

    # ── fixture：基础 mock DataFrame ─────────────────────────

    @staticmethod
    def _make_mock_df() -> pd.DataFrame:
        """标准 13 列 bond_zh_us_rate 返回值。"""
        columns = [
            "日期", "中国国债收益率2年", "中国国债收益率5年", "中国国债收益率10年",
            "中国国债收益率30年", "中国国债收益率10年-2年", "中国GDP同比增长",
            "美国国债收益率2年", "美国国债收益率5年", "美国国债收益率10年",
            "美国国债收益率30年", "美国国债收益率10年-2年", "美国GDP同比增长",
        ]
        data = [["2026-07-17", 1.2645, 1.4466, 1.7404, 2.2425, 0.4759, None,
                  4.18, 4.28, 4.55, 5.06, 0.37, None]]
        return pd.DataFrame(data, columns=columns)

    # ── 用户配置异常 ───────────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_config_negative_skipped(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """risk_free_rate 为负值 → 跳过配置，降级到 akshare。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": -0.01}
        mock_bond.return_value = self._make_mock_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        # 负值被跳过 → 走 akshare → 正常返回 0.017404
        assert rf is not None
        assert abs(rf - 0.017404) < 1e-6

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_config_zero_skipped(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """risk_free_rate = 0 → 不满足 0<rf<1 → 跳过。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": 0.0}
        mock_bond.return_value = self._make_mock_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is not None
        assert abs(rf - 0.017404) < 1e-6

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_config_non_numeric_skipped(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """risk_free_rate 为非数值字符串 → ValueError → 跳过。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": "invalid"}
        mock_bond.return_value = self._make_mock_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is not None
        assert abs(rf - 0.017404) < 1e-6

    def test_config_just_above_one_converted(self):
        """配置值为 1.5（>=1）→ 自动转为 0.015。"""
        with patch("src.python.fetcher.bond_yield.get_config") as mock_config:
            mock_config.return_value = {"risk_free_rate": 1.5}

            from src.python.fetcher.bond_yield import get_risk_free_rate

            # 配置满足 >=1 → /100 转换后返回，不触发网络
            rf = get_risk_free_rate()
            assert rf is not None
            assert abs(rf - 0.015) < 1e-6

    # ── 配置获取异常 ───────────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_get_config_raises_type_error(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """get_config() 抛出 TypeError → 被捕获，降级到 akshare。"""
        mock_cache.return_value = None
        mock_config.side_effect = TypeError("config corrupt")
        mock_bond.return_value = self._make_mock_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is not None
        assert abs(rf - 0.017404) < 1e-6

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_config_missing_key(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """config 不含 risk_free_rate 键 → KeyError 被捕获 → 降级。"""
        mock_cache.return_value = None
        mock_config.return_value = {"other_key": 0.02}
        mock_bond.return_value = self._make_mock_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is not None
        assert abs(rf - 0.017404) < 1e-6

    # ── 缓存异常 ──────────────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_cache_returns_dict(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """缓存返回 dict → float(dict) 失败 → 跳过缓存。"""
        mock_cache.return_value = {"value": 0.03}
        mock_config.return_value = {"risk_free_rate": None}
        mock_bond.return_value = self._make_mock_df()

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=True)
        assert rf is not None
        assert abs(rf - 0.017404) < 1e-6

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    def test_cache_returns_string_float(
        self,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """缓存返回字符串 "0.03" → float("0.03") 解析成功。"""
        mock_cache.return_value = "0.03"
        mock_config.return_value = {"risk_free_rate": None}

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=True)
        assert rf is not None
        assert abs(rf - 0.03) < 1e-6

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    def test_cache_returns_non_float_string(
        self,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """缓存返回不可解析字符串 → ValueError 被捕获 → 跳过缓存。"""
        mock_cache.return_value = "not_a_number"
        mock_config.return_value = {"risk_free_rate": None}

        # 需要 mock akshare 避免真实调用
        with patch("akshare.bond_zh_us_rate", return_value=None):
            from src.python.fetcher.bond_yield import get_risk_free_rate

            rf = get_risk_free_rate(cache_ok=True)
            assert rf is None  # 全部不可用

    # ── akshare 异常 ───────────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    def test_akshare_import_error(
        self,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """akshare 未安装 → ImportError 被捕获 → 返回 None。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": None}

        # mock akshare import 在 _fetch_from_akshare 内部
        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "akshare":
                raise ImportError("No module named 'akshare'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            from src.python.fetcher.bond_yield import get_risk_free_rate

            rf = get_risk_free_rate(cache_ok=False)
            assert rf is None

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_akshare_returns_none(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """bond_zh_us_rate 返回 None → 返回 None。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": None}
        mock_bond.return_value = None

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_akshare_general_exception(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """bond_zh_us_rate 抛出任意异常 → 被捕获 → 返回 None。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": None}
        mock_bond.side_effect = RuntimeError("API timeout")

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None

    # ── DataFrame 异常 ─────────────────────────────────────

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_dataframe_too_few_columns(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """DataFrame 列数 <4 → IndexError → 被捕获 → 返回 None。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": None}
        df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})  # 仅 3 列
        mock_bond.return_value = df

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_dataframe_empty_index(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """DataFrame 无行 → iloc[-1] 抛出 IndexError → 被捕获。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": None}
        df = pd.DataFrame(columns=["日期", "a", "b", "中国国债收益率10年"])
        mock_bond.return_value = df

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    @patch("akshare.bond_zh_us_rate")
    def test_rf_out_of_range_after_division(
        self,
        mock_bond: MagicMock,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """raw_value > 100 → rf > 1 → 超出合理范围 → 返回 None。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": None}
        df = self._make_mock_df()
        df.iloc[-1, 3] = 150.0  # 中国 10Y = 150%（异常值）
        mock_bond.return_value = df

        from src.python.fetcher.bond_yield import get_risk_free_rate

        rf = get_risk_free_rate(cache_ok=False)
        assert rf is None

    @patch("src.python.fetcher.bond_yield.cache_get")
    @patch("src.python.fetcher.bond_yield.get_config")
    def test_all_sources_fail(
        self,
        mock_config: MagicMock,
        mock_cache: MagicMock,
    ):
        """全部数据源不可用 → 返回 None。"""
        mock_cache.return_value = None
        mock_config.return_value = {"risk_free_rate": None}

        with patch("akshare.bond_zh_us_rate", side_effect=RuntimeError("API down")):
            from src.python.fetcher.bond_yield import get_risk_free_rate

            rf = get_risk_free_rate(cache_ok=True)
            assert rf is None
