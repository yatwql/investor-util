"""价格获取 chain 模块单元测试。

测试目标：
  - _name_matches — 名称匹配逻辑
  - _price_cache_key — 缓存键生成
  - _price_transform_tencent — 腾讯数据转换
  - _price_transform_eastmoney — 东方财富数据转换
  - fetch_market_data — 完整链路（mock chain）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_fetcher_price.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


class TestNameMatches(unittest.TestCase):
    """_name_matches 纯函数测试。"""

    def _call(self, a: str, b: str) -> bool:
        from src.python.fetcher.price import _name_matches

        return _name_matches(a, b)

    def test_exact_match(self):
        """完全匹配 → True。"""
        self.assertTrue(self._call("长江电力", "长江电力"))

    def test_empty_a(self):
        """a 为空 → False。"""
        self.assertFalse(self._call("", "长江电力"))

    def test_empty_b(self):
        """b 为空 → False。"""
        self.assertFalse(self._call("长江电力", ""))

    def test_substring_match(self):
        """子串匹配（>3 字）→ True。"""
        self.assertTrue(self._call("长江电力", "长江电力股份"))

    def test_substring_reverse(self):
        """另一方向子串匹配 → True。"""
        self.assertTrue(self._call("长江电力股份", "长江电力"))

    def test_cjk_overlap(self):
        """CJK 字符重叠 >= 70% → True。"""
        self.assertTrue(self._call("长江电力", "长江电"))

    def test_low_overlap(self):
        """CJK 重叠 < 70% → False。"""
        self.assertFalse(self._call("长江电力", "贵州茅台"))

    def test_no_cjk_chars(self):
        """无非汉字的名称 → False。"""
        self.assertFalse(self._call("ABC", "XYZ"))


class TestPriceCacheKey(unittest.TestCase):
    """_price_cache_key 纯函数测试。"""

    def _call(self, code: str) -> str:
        from src.python.fetcher.price import _price_cache_key

        return _price_cache_key(code)

    def test_format(self):
        """格式为 price_{code}。"""
        self.assertEqual(self._call("600900"), "price_600900")

    def test_different_code(self):
        """不同代码 → 不同键。"""
        self.assertNotEqual(self._call("600900"), self._call("000001"))


class TestPriceTransformTencent(unittest.TestCase):
    """_price_transform_tencent 纯函数测试。"""

    def _call(self, raw: dict, source: str = "腾讯财经"):
        from src.python.fetcher.price import _price_transform_tencent

        return _price_transform_tencent(raw, source)

    def test_normal(self):
        """正常数据 → 统一格式。"""
        raw = {
            "name": "长江电力",
            "code": "600900",
            "price": 26.65,
            "yesterday_close": 26.50,
            "price_date": "2026-07-01",
        }
        result = self._call(raw)
        self.assertEqual(result["name"], "长江电力")
        self.assertEqual(result["price"], 26.65)
        self.assertEqual(result["source_api"], "tencent")
        self.assertEqual(result["source"], "腾讯财经")

    def test_empty_fields(self):
        """缺字段 → 不抛异常。"""
        result = self._call({"code": "600900"})
        self.assertEqual(result["price"], 0.0)
        self.assertEqual(result["name"], "")


class TestPriceTransformEastmoney(unittest.TestCase):
    """_price_transform_eastmoney 纯函数测试。"""

    def _call(self, raw: dict, source: str = "东方财富"):
        from src.python.fetcher.price import _price_transform_eastmoney

        return _price_transform_eastmoney(raw, source)

    def test_normal(self):
        """正常数据 → 统一格式。"""
        raw = {
            "name": "测试基金",
            "code": "011506",
            "nav": 1.2345,
            "yesterday_nav": 1.2000,
            "nav_date": "2026-07-01",
        }
        result = self._call(raw)
        self.assertEqual(result["name"], "测试基金")
        self.assertEqual(result["price"], 1.2345)
        self.assertEqual(result["yesterday_close"], 1.2000)
        self.assertEqual(result["source_api"], "eastmoney")

    def test_zero_nav_returns_none(self):
        """nav <= 0 → None。"""
        self.assertIsNone(self._call({"code": "011506", "nav": 0.0}))

    def test_negative_nav_returns_none(self):
        """nav 负数 → None。"""
        self.assertIsNone(self._call({"code": "011506", "nav": -1.0}))

    def test_missing_nav(self):
        """无 nav 字段 → None（默认 0.0）。"""
        self.assertIsNone(self._call({"code": "011506"}))


class TestFetchMarketData(unittest.TestCase):
    """fetch_market_data 测试（mock chain）。"""

    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_success(self, mock_fallback):
        """正常返回。"""
        mock_fallback.return_value = {
            "name": "长江电力",
            "code": "600900",
            "price": 26.65,
            "source": "腾讯财经",
        }
        from src.python.fetcher.price import fetch_market_data

        result = fetch_market_data("600900", "长江电力")
        self.assertEqual(result["price"], 26.65)

    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_all_fail_returns_none(self, mock_fallback):
        """全部失败 → None。"""
        mock_fallback.return_value = None
        from src.python.fetcher.price import fetch_market_data

        self.assertIsNone(fetch_market_data("600900"))

    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_expected_name_passed(self, mock_fallback):
        """expected_name 正确传递到 validate。"""
        mock_fallback.return_value = None
        from src.python.fetcher.price import fetch_market_data

        fetch_market_data("600900", "长江电力")
        # _fetch_with_fallback 被调用，validate 从 fn_kwargs 读取
        args, kwargs = mock_fallback.call_args
        self.assertIn("validate", kwargs)

    # ── OTC 三路路由（is_otc_fund_by_name 预判） ──────────────

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_otc_fund_bypassed_stock_chain(
        self,
        mock_fallback,
        mock_fresh,
    ):
        """002943 场外基金（名称可识别）→ 直接走 fund_otc，不经过 stock 链路。"""
        from src.python.fetcher.price import fetch_market_data

        mock_fallback.return_value = None  # 无关返回值，我们只检查调用次数
        fetch_market_data("002943", "广发多因子灵活配置混合")
        # 仅 1 次调用（无降级重试）
        self.assertEqual(mock_fallback.call_count, 1)
        args, kwargs = mock_fallback.call_args
        self.assertEqual(kwargs["data_type"], "price_fund_otc")

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_otc_fund_empty_name_fallback_to_degrade(
        self,
        mock_fallback,
        mock_fresh,
    ):
        """002943 无 expected_name → 先走 stock 失败后降级 fund_otc（2 次调用）。"""
        from src.python.fetcher.price import fetch_market_data

        mock_fallback.side_effect = [None, None]
        fetch_market_data("002943", "")
        self.assertEqual(mock_fallback.call_count, 2)
        args1, kwargs1 = mock_fallback.call_args_list[0]
        self.assertEqual(kwargs1["data_type"], "price_stock")
        args2, kwargs2 = mock_fallback.call_args_list[1]
        self.assertEqual(kwargs2["data_type"], "price_fund_otc")

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_a_share_stock_only_one_call(
        self,
        mock_fallback,
        mock_fresh,
    ):
        """600900 A 股 → 仅走 stock 链路，不降级。"""
        from src.python.fetcher.price import fetch_market_data

        mock_fallback.return_value = None
        fetch_market_data("600900", "长江电力")
        self.assertEqual(mock_fallback.call_count, 1)
        args, kwargs = mock_fallback.call_args
        self.assertEqual(kwargs["data_type"], "price_stock")

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_etf_fund_only_stock_chain(
        self,
        mock_fallback,
        mock_fresh,
    ):
        """161725 ETF 基金 → 仅走 stock 链路（exchange_fund 判定），不降级。"""
        from src.python.fetcher.price import fetch_market_data

        mock_fallback.return_value = None
        fetch_market_data("161725", "招商中证白酒指数(LOF)")
        self.assertEqual(mock_fallback.call_count, 1)
        args, kwargs = mock_fallback.call_args
        self.assertEqual(kwargs["data_type"], "price_stock")

    # ── 00 代码降级 ──────────────────────────────────────

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_code_fallback_to_eastmoney(
        self,
        mock_fallback,
        mock_fresh,
    ):
        """00 代码股票链路全失败 → 降级场外基金净值链路。"""
        mock_fallback.side_effect = [
            None,  # 第 1 次：stock 链路返回 None
            {  # 第 2 次：降级到 fund_otc（eastmoney 转换后格式）
                "name": "广发多因子",
                "code": "002943",
                "price": 1.2345,
                "yesterday_close": 1.2000,
                "price_date": "2026-07-13",
                "source_api": "eastmoney",
                "source": "东方财富",
            },
        ]
        from src.python.fetcher.price import fetch_market_data

        result = fetch_market_data("002943", "广发多因子")
        self.assertIsNotNone(result)
        self.assertEqual(result["source_api"], "eastmoney")
        self.assertEqual(result["price"], 1.2345)
        self.assertEqual(mock_fallback.call_count, 2)

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_code_fallback_all_fail(
        self,
        mock_fallback,
        mock_fresh,
    ):
        """00 代码股票链路 + 降级链路均失败 → None。"""
        mock_fallback.side_effect = [None, None]
        from src.python.fetcher.price import fetch_market_data

        result = fetch_market_data("002943", "广发多因子")
        self.assertIsNone(result)
        self.assertEqual(mock_fallback.call_count, 2)

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_code_stock_no_fallback(
        self,
        mock_fallback,
        mock_fresh,
    ):
        """00 代码但股票链路成功 → 不回退降级。"""
        mock_fallback.return_value = {
            "name": "平安银行",
            "code": "000001",
            "price": 12.50,
            "source_api": "tencent",
        }
        from src.python.fetcher.price import fetch_market_data

        result = fetch_market_data("000001", "平安银行")
        self.assertIsNotNone(result)
        self.assertEqual(result["source_api"], "tencent")
        self.assertEqual(mock_fallback.call_count, 1)


class TestPriceCacheFresh(unittest.TestCase):
    """_price_cache_fresh 收市后新鲜度验证测试。"""

    def _call(self, data: dict) -> bool:
        from src.python.fetcher.price import _price_cache_fresh

        return _price_cache_fresh(data)

    @patch("src.python.core.market_hours.is_market_open", return_value=True)
    def test_market_open_always_fresh(self, mock_open):
        """盘中 → 无论 price_date 多旧均视为新鲜（短 TTL 已保证实时性）。"""
        self.assertTrue(self._call({"price_date": "2020-01-01"}))

    @patch("src.python.core.market_hours.is_market_open", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-07-31")
    def test_after_close_fresh(self, mock_td, mock_open):
        """盘后 price_date >= 最近交易日 → 新鲜。"""
        self.assertTrue(self._call({"price_date": "2026-07-31"}))
        self.assertTrue(self._call({"price_date": "2026-08-01"}))

    @patch("src.python.core.market_hours.is_market_open", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-07-31")
    def test_after_close_stale(self, mock_td, mock_open):
        """盘后 price_date < 最近交易日 → 跨日残留，判定不新鲜。"""
        self.assertFalse(self._call({"price_date": "2026-07-30"}))

    @patch("src.python.core.market_hours.is_market_open", return_value=False)
    @patch("src.python.report.market_value.get_last_trading_day", return_value="2026-07-31")
    def test_after_close_no_date(self, mock_td, mock_open):
        """盘后无 price_date → 视为不新鲜（强制刷新兜底）。"""
        self.assertFalse(self._call({}))
        self.assertFalse(self._call({"price_date": ""}))

    @patch("src.python.core.market_hours.is_market_open", side_effect=RuntimeError("boom"))
    def test_exception_conservative_fresh(self, mock_open):
        """校验异常 → 保守视为新鲜，不阻塞取价流程。"""
        self.assertTrue(self._call({"price_date": "2026-07-30"}))


class TestFetchPriceCacheRefresh(unittest.TestCase):
    """_fetch_price_with_cache_refresh 跨日残留强刷路径测试。"""

    _STALE = {
        "name": "测试基金",
        "code": "011506",
        "price": 1.2000,
        "yesterday_close": 1.1900,
        "price_date": "2026-07-30",  # 早于最近交易日 → 跨日残留
        "source_api": "eastmoney",
        "source": "东方财富",
    }
    _FRESH = {
        "name": "测试基金",
        "code": "011506",
        "price": 1.2345,
        "yesterday_close": 1.2000,
        "price_date": "2026-07-31",
        "source_api": "eastmoney",
        "source": "东方财富",
    }

    def _call(self):
        from src.python.fetcher.price import _fetch_price_with_cache_refresh

        return _fetch_price_with_cache_refresh(
            "price_fund_otc",
            "011506",
            "price_011506",
            "测试基金",
        )

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=False)
    @patch("src.python.cache.clear")
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_stale_triggers_clear_and_refetch(self, mock_fallback, mock_clear, mock_fresh):
        """跨日残留 → 清除缓存 + 重新拉取，返回最新净值并写回缓存。"""
        mock_fallback.side_effect = [self._STALE, self._FRESH]
        result = self._call()
        self.assertEqual(result["price"], 1.2345)  # 返回第二次（最新）结果
        self.assertEqual(result["price_date"], "2026-07-31")
        self.assertEqual(mock_fallback.call_count, 2)
        mock_clear.assert_called_once_with("price_011506")

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=True)
    @patch("src.python.cache.clear")
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_fresh_no_clear(self, mock_fallback, mock_clear, mock_fresh):
        """新鲜缓存 → 不触发强刷，仅一次 fetch。"""
        mock_fallback.return_value = self._FRESH
        result = self._call()
        self.assertEqual(result["price"], 1.2345)
        self.assertEqual(mock_fallback.call_count, 1)
        mock_clear.assert_not_called()

    @patch("src.python.fetcher.price._price_cache_fresh", return_value=False)
    @patch("src.python.cache.clear")
    @patch("src.python.fetcher.price.fetch_with_fallback")
    def test_fetch_none_no_clear(self, mock_fallback, mock_clear, mock_fresh):
        """首次 fetch 即 None → 不进入强刷分支（无缓存可清）。"""
        mock_fallback.return_value = None
        result = self._call()
        self.assertIsNone(result)
        self.assertEqual(mock_fallback.call_count, 1)
        mock_clear.assert_not_called()
