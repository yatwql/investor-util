"""行业分类 API 模块单元测试。

测试目标：
  - _industry_transform — 原始数据转换
  - fetch_industry_data — 单只证券行业查询（mock chain）
  - batch_fetch_industry_data — 批量查询（含非 A 股过滤）

（is_a_share_code 见 core/test_code_utils.py；
  eastmoney_industry_rest 模块见 providers/test_eastmoney_industry_rest.py）

运行：
  pytest src/test/unit/fetcher/test_fetcher_industry.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]



class TestIndustryTransform(unittest.TestCase):
    """_industry_transform 纯函数测试。"""

    def _call(self, raw: dict | None, source: str = "eastmoney"):
        from src.python.fetcher.industry import _industry_transform
        return _industry_transform(raw, source)

    def test_normal(self):
        """正常数据 → 正确转换。"""
        raw = {
            "code": "000001",
            "industry": "银行",
            "industry_id": "BK0477",
            "concepts": ["沪深300", "MSCI"],
            "concept_ids": ["BK0500", "BK0600"],
        }
        result = self._call(raw)
        self.assertEqual(result["code"], "000001")
        self.assertEqual(result["industry"], "银行")
        self.assertEqual(len(result["concepts"]), 2)

    def test_none_input(self):
        """None 输入 → None。"""
        self.assertIsNone(self._call(None))

    def test_empty_dict(self):
        """空字典（falsy）→ None。"""
        self.assertIsNone(self._call({}))

    def test_missing_fields(self):
        """缺字段 → 不抛异常。"""
        result = self._call({"code": "000001"})
        self.assertEqual(result["code"], "000001")
        self.assertEqual(result["industry"], "")
        self.assertEqual(result["concepts"], [])

    def test_strips_hierarchy_suffix(self):
        """申万层级后缀（银行Ⅱ/白酒Ⅱ/国有大型银行Ⅱ）→ 剥离为干净名。"""
        for raw_name, expected in [("银行Ⅱ", "银行"), ("白酒Ⅱ", "白酒"), ("国有大型银行Ⅱ", "国有大型银行")]:
            result = self._call({"code": "000001", "industry": raw_name})
            self.assertEqual(result["industry"], expected, f"{raw_name} → {expected}")

    def test_keeps_plain_name(self):
        """无层级后缀的行业名（电力）→ 原样保留。"""
        result = self._call({"code": "600900", "industry": "电力"})
        self.assertEqual(result["industry"], "电力")


class TestStripHierarchySuffix(unittest.TestCase):
    """strip_hierarchy_suffix 纯函数测试。"""

    def test_strips_trailing_roman(self):
        """末尾 Ⅰ/Ⅱ/Ⅲ/Ⅳ → 剥离。"""
        from src.python.fetcher.industry import strip_hierarchy_suffix
        self.assertEqual(strip_hierarchy_suffix("银行Ⅱ"), "银行")
        self.assertEqual(strip_hierarchy_suffix("白酒Ⅱ"), "白酒")
        self.assertEqual(strip_hierarchy_suffix("光学光电子Ⅲ"), "光学光电子")

    def test_no_suffix_unchanged(self):
        """无后缀 → 原样。"""
        from src.python.fetcher.industry import strip_hierarchy_suffix
        self.assertEqual(strip_hierarchy_suffix("电力"), "电力")
        self.assertEqual(strip_hierarchy_suffix(""), "")
        self.assertIsNone(strip_hierarchy_suffix(None))


class TestFetchIndustryData(unittest.TestCase):
    """fetch_industry_data 测试。"""

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_success(self, mock_fallback):
        """正常返回 → 返回行业数据。"""
        mock_fallback.return_value = {
            "code": "000001", "industry": "银行", "concepts": ["沪深300"],
        }
        from src.python.fetcher.industry import fetch_industry_data
        result = fetch_industry_data("000001")
        self.assertEqual(result["industry"], "银行")
        mock_fallback.assert_called_once()

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_failure_returns_none(self, mock_fallback):
        """获取失败 → None。"""
        mock_fallback.return_value = None
        from src.python.fetcher.industry import fetch_industry_data
        self.assertIsNone(fetch_industry_data("000001"))

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_cache_key_includes_code(self, mock_fallback):
        """缓存键包含代码。"""
        mock_fallback.return_value = {}
        from src.python.fetcher.industry import fetch_industry_data
        fetch_industry_data("600900")
        args, kwargs = mock_fallback.call_args
        # 第三个位置参数是 cache_key
        self.assertIn("industry_600900", args)

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_cached_raw_suffix_stripped(self, mock_fallback):
        """热缓存命中旧值（未经 transform 含层级后缀）→ 出口归一化剥离。"""
        mock_fallback.return_value = {"code": "000001", "industry": "银行Ⅱ", "concepts": []}
        from src.python.fetcher.industry import fetch_industry_data
        result = fetch_industry_data("000001")
        self.assertEqual(result["industry"], "银行")


class TestLegacyIndustryCacheMigration(unittest.TestCase):
    """缺扩展行情字段的行业缓存载荷清理 — 见 `_drop_legacy_cached_payload`。

    背景：行业载荷透传 pe/pb/market_cap，缺键载荷不含这三个键，而缓存 TTL 为
    两周、`fetch_with_fallback` 命中即返回——不剔除缺键载荷，估值分位与基金风格
    的 PE 取用会在存活期内静默退化为「不可得」。
    """

    def _fresh_payload(self) -> dict:
        """新载荷形态：无论 provider 是否给出，三个扩展键都存在（值为 None 表不提供）。"""
        return {"code": "000001", "industry": "银行", "concepts": [], "pe": None, "pb": None, "market_cap": None}

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_legacy_payload_purged(self, mock_fallback):
        """缓存为旧载荷（无 pe 键）→ 清除该键（本次调用随之回落到 provider 重取）。"""
        mock_fallback.return_value = self._fresh_payload()
        legacy = {"code": "000001", "industry": "银行", "concepts": []}

        with (
            patch("src.python.fetcher.industry.cache_get", return_value=legacy),
            patch("src.python.fetcher.industry.cache_clear") as mock_clear,
        ):
            from src.python.fetcher.industry import fetch_industry_data

            fetch_industry_data("000001")

        mock_clear.assert_called_once_with("industry_000001")

    @patch("src.python.fetcher.industry.fetch_with_fallback")
    def test_fresh_payload_kept(self, mock_fallback):
        """缓存为新载荷（含 pe 键，值为 None 表该源不提供）→ 不得误删。"""
        mock_fallback.return_value = self._fresh_payload()

        with (
            patch("src.python.fetcher.industry.cache_get", return_value=self._fresh_payload()),
            patch("src.python.fetcher.industry.cache_clear") as mock_clear,
        ):
            from src.python.fetcher.industry import fetch_industry_data

            fetch_industry_data("000001")

        mock_clear.assert_not_called()

    def test_transform_carries_valuation_fields(self):
        """_industry_transform 透传同一次 push2 响应的 pe/pb/market_cap。"""
        from src.python.fetcher.industry import _industry_transform

        result = _industry_transform(
            {"code": "600900", "industry": "电力", "pe": 12.5, "pb": 1.2, "market_cap": 1e11}, "eastmoney"
        )

        self.assertEqual(result["pe"], 12.5)
        self.assertEqual(result["pb"], 1.2)
        self.assertEqual(result["market_cap"], 1e11)


class TestFetchValuationFields(unittest.TestCase):
    """fetch_valuation_fields — 经 Provider Chain 取 PE/PB（唯一网关入口）。

    背景：报告层曾直接 import ``providers.eastmoney_industry`` 的估值取值函数，
    绕开 fetcher 网关（无链路降级/诊断）。现值取值经本网关取用，断言：
      - 结果透传行业请求带出的 pe/pb；
      - 取数走行业数据入口（不直连 provider）。
    """

    def setUp(self):
        from src.python.core.provider_registry import get_registry

        get_registry().session_cache_clear("industry")

    @patch("src.python.fetcher.industry.fetch_industry_data_cached")
    def test_projects_pe_pb(self, mock_cached):
        """行业数据自带 pe/pb → 投影为估值字段契约。"""
        mock_cached.return_value = {"industry": "电力", "pe": 12.34, "pb": 1.56, "market_cap": 1e11}
        from src.python.fetcher.industry import fetch_valuation_fields

        result = fetch_valuation_fields("600900")
        self.assertEqual(result, {"pe": 12.34, "pb": 1.56})

    @patch("src.python.fetcher.industry.fetch_industry_data_cached")
    def test_none_when_unavailable(self, mock_cached):
        """行业数据不可得 → None（链路全失败时估值列走占位）。"""
        mock_cached.return_value = None
        from src.python.fetcher.industry import fetch_valuation_fields

        self.assertIsNone(fetch_valuation_fields("600900"))

    @patch("src.python.fetcher.industry.fetch_industry_data_cached")
    def test_missing_fields_projected_as_none(self, mock_cached):
        """字段缺失 → 对应键为 None（不伪造 0）。"""
        mock_cached.return_value = {"industry": "电力"}
        from src.python.fetcher.industry import fetch_valuation_fields

        self.assertEqual(fetch_valuation_fields("600900"), {"pe": None, "pb": None})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_uses_gateway_entry(self, mock_fetch):
        """取数经行业数据入口（网关），不直连 provider 模块。"""
        from src.python.core.provider_registry import get_registry
        from src.python.fetcher.industry import fetch_valuation_fields

        get_registry().session_cache_clear("industry")
        mock_fetch.return_value = {"industry": "电力", "pe": 20.0, "pb": 2.0}

        result = fetch_valuation_fields("600900")
        self.assertEqual(result["pe"], 20.0)
        mock_fetch.assert_called_once_with("600900")


class TestBatchFetchIndustryData(unittest.TestCase):
    """batch_fetch_industry_data 测试。"""

    def test_empty_input(self):
        """空列表 → 空字典。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        self.assertEqual(batch_fetch_industry_data([]), {})

    def test_all_empty_codes(self):
        """全空/无效代码 → 空字典。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        self.assertEqual(batch_fetch_industry_data(["", " ", None]), {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_batch_success(self, mock_fetch):
        """批量 A 股成功 → 返回映射。"""
        def side_effect(code, **kwargs):
            return {"code": code, "industry": "测试"}
        mock_fetch.side_effect = side_effect

        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001", "600900"])
        self.assertEqual(len(result), 2)
        self.assertIn("000001", result)

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_batch_strips_suffix_from_industry(self, mock_fetch):
        """批量组装兜底剥离层级后缀（覆盖缓存命中原始值路径）。"""
        def side_effect(code, **kwargs):
            return {"code": code, "industry": "银行Ⅱ"}
        mock_fetch.side_effect = side_effect

        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001"])
        self.assertEqual(result["000001"]["industry"], "银行")

    @patch("src.python.fetcher.industry.fetch_industry_data", return_value=None)
    def test_batch_partial_failure(self, mock_fetch):
        """部分失败 → 只返回成功的。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001", "600900"])
        self.assertEqual(result, {})

    @patch("src.python.fetcher.industry.fetch_industry_data", return_value=None)
    def test_us_stock_filtered_out(self, mock_fetch):
        """美股代码自动过滤，不调 API。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["600900", "AAPL", "00700", "PEP"])
        # AAPL/00700/PEP 被过滤，只调用了 600900（首次失败后重试一次）
        self.assertEqual(mock_fetch.call_count, 2)
        # 600900 两次均返回 None，全空
        self.assertEqual(result, {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_all_us_stocks_return_empty(self, mock_fetch):
        """全是美股 → 不调 API，直接返回空字典。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["AAPL", "GOOG", "TSLA"])
        mock_fetch.assert_not_called()
        self.assertEqual(result, {})

    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_mixed_with_prefixed_codes(self, mock_fetch):
        """带 sh/sz 前缀和美股混合 → 前缀码通过，美股过滤。"""
        def side_effect(code, **kwargs):
            return {"code": code, "industry": "测试"}
        mock_fetch.side_effect = side_effect

        from src.python.fetcher.industry import batch_fetch_industry_data

        result = batch_fetch_industry_data(["sh600000", "sz000001", "AAPL"])
        self.assertEqual(len(result), 2)
        self.assertIn("sh600000", result)
        self.assertIn("sz000001", result)
        self.assertNotIn("AAPL", result)


class TestBatchFetchIndustryDataBroken(unittest.TestCase):
    """batch_fetch_industry_data 熔断预检测试。

    全链已熔断时跳过批量请求和重试，避免逐条冗余调用。
    """

    @patch("src.python.fetcher.industry.is_provider_chain_broken", return_value=True)
    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_entry_skipped_on_full_broken(self, mock_fetch, mock_broken):
        """全链熔断 → 入口预检返回空，不调用 fetch。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001", "600900"])
        self.assertEqual(result, {})
        mock_fetch.assert_not_called()

    @patch("src.python.fetcher.industry.is_provider_chain_broken")
    def test_entry_logs_warning(self, mock_broken):
        """全链熔断 → 日志含熔断提示。"""
        mock_broken.return_value = True
        with self.assertLogs("invest", level="WARNING") as log:
            from src.python.fetcher.industry import batch_fetch_industry_data
            batch_fetch_industry_data(["000001"])
            self.assertTrue(any("全链不可用（熔断）" in msg for msg in log.output))

    @patch("src.python.fetcher.industry.is_provider_chain_broken", return_value=True)
    @patch("src.python.fetcher.industry.fetch_industry_data")
    def test_empty_returned_on_full_broken(self, mock_fetch, mock_broken):
        """全链熔断 → 即使有代码也不调 API。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["sh600000", "sz000001"])
        self.assertEqual(result, {})
        mock_fetch.assert_not_called()

    @patch("src.python.fetcher.industry.is_provider_chain_broken", return_value=False)
    @patch("src.python.fetcher.industry.fetch_industry_data", return_value={"code": "000001", "industry": "银行"})
    def test_normal_when_not_broken(self, mock_fetch, mock_broken):
        """未熔断 → 正常调用不受影响。"""
        from src.python.fetcher.industry import batch_fetch_industry_data
        result = batch_fetch_industry_data(["000001"])
        self.assertEqual(len(result), 1)
        mock_fetch.assert_called()
