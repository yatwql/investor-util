"""Provider Chain 回退机制单元测试。

测试目标：
  - _get_chain — 默认顺序、preferred_provider 前置
  - _fetch_with_fallback — 缓存命中、Provider 遍历、验证、转换、降级

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/test_chain.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.python.fetcher.chain import _get_chain, _fetch_with_fallback
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]




# ============================================================
#  _get_chain
# ============================================================


class TestGetChain(unittest.TestCase):
    """Provider Chain 顺序获取测试。"""

    def test_default_chain(self):
        """无 preferred_provider → 返回默认顺序。"""
        chain = _get_chain("price")
        self.assertEqual(chain, ["tencent", "eastmoney"])

    def test_default_chain_unknown_type(self):
        """未知 data_type → 返回空列表。"""
        chain = _get_chain("nonexistent")
        self.assertEqual(chain, [])

    @patch("src.python.fetcher.chain.get_config")
    def test_preferred_moves_to_front(self, mock_config):
        """preferred_provider.price = eastmoney → eastmoney 前置。"""
        mock_config.return_value = {"preferred_provider": {"price": "eastmoney"}}
        chain = _get_chain("price")
        self.assertEqual(chain[0], "eastmoney")
        self.assertEqual(chain, ["eastmoney", "tencent"])

    @patch("src.python.fetcher.chain.get_config")
    def test_preferred_already_first(self, mock_config):
        """preferred 已在首位 → 顺序不变。"""
        mock_config.return_value = {"preferred_provider": {"price": "tencent"}}
        chain = _get_chain("price")
        self.assertEqual(chain, ["tencent", "eastmoney"])

    @patch("src.python.fetcher.chain.get_config")
    def test_preferred_not_in_chain(self, mock_config):
        """preferred 不在默认 chain 中 → 忽略，返回原顺序。"""
        mock_config.return_value = {"preferred_provider": {"price": "alibaba"}}
        chain = _get_chain("price")
        self.assertEqual(chain, ["tencent", "eastmoney"])

    @patch("src.python.fetcher.chain.get_config")
    def test_no_preferred_provider_key(self, mock_config):
        """config 中没有 preferred_provider 键 → 返回默认。"""
        mock_config.return_value = {}
        chain = _get_chain("price")
        self.assertEqual(chain, ["tencent", "eastmoney"])

    @patch("src.python.fetcher.chain.get_config")
    def test_config_raises_key_error(self, mock_config):
        """get_config 抛出异常 → 安全返回默认 chain。"""
        mock_config.side_effect = KeyError("test")
        chain = _get_chain("price")
        self.assertEqual(chain, ["tencent", "eastmoney"])


# ============================================================
#  _fetch_with_fallback
# ============================================================

class TestFetchWithFallback(unittest.TestCase):
    """Provider Chain 通用 Fallback 获取器测试。"""

    def setUp(self):
        self.provider_fn_map = {
            "p1": ("Provider1", None),
            "p2": ("Provider2", None),
        }

    # ── 缓存命中 ─────────────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    def test_cache_hit_returns_cached(self, mock_cache_get):
        """缓存命中 → 直接返回缓存数据。"""
        mock_cache_get.return_value = {"cached": True}
        result = _fetch_with_fallback("price", self.provider_fn_map, "test_key", 3600)
        self.assertEqual(result, {"cached": True})

    # ── Provider 成功路径 ────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_first_provider_succeeds(self, mock_chain, mock_set, mock_get):
        """第一个 Provider 成功 → 返回其数据并写入缓存。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None  # 缓存未命中
        fn1 = MagicMock(return_value={"data": "from_p1"})
        fn2 = MagicMock(return_value={"data": "from_p2"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "from_p1"})
        fn1.assert_called_once()
        fn2.assert_not_called()
        mock_set.assert_called_once_with("test_key", {"data": "from_p1"})

    # ── Provider 回退 ────────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_fallback_on_failure(self, mock_chain, mock_set, mock_get):
        """第一个 Provider 失败 → 自动回退到第二个。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(side_effect=Exception("timeout"))
        fn2 = MagicMock(return_value={"data": "from_p2"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "from_p2"})
        fn1.assert_called_once()
        fn2.assert_called_once()

    # ── 全部 Provider 失败 + 过期缓存降级 ────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_all_fail_stale_cache(self, mock_chain, mock_set, mock_get):
        """全部 Provider 失败 + 有过期缓存 → 降级使用过期缓存。"""
        mock_chain.return_value = ["p1", "p2"]
        # 第一次 cache_get（最新缓存）→ None
        # 第二次 cache_get（过期缓存降级）→ stale data
        mock_get.side_effect = [None, {"stale": True}]
        fn1 = MagicMock(side_effect=Exception("fail"))
        fn2 = MagicMock(side_effect=Exception("fail"))
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"stale": True})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_all_fail_no_stale(self, mock_chain, mock_get):
        """全部 Provider 失败 + 无过期缓存 → 返回 None。"""
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None  # 最新 + 过期全都 None
        fn1 = MagicMock(side_effect=Exception("fail"))
        provider_map = {"p1": ("P1", fn1)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertIsNone(result)

    # ── Provider 返回 None ───────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_provider_returns_none(self, mock_chain, mock_get):
        """Provider 返回 None → 尝试下一个。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value=None)
        fn2 = MagicMock(return_value={"data": "from_p2"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "from_p2"})

    # ── 未知 Provider ────────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_unknown_provider_skipped(self, mock_chain, mock_get):
        """chain 中有未注册的 provider → 跳过，尝试下一个。"""
        mock_chain.return_value = ["unknown", "p1"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"data": "ok"})
        provider_map = {"p1": ("P1", fn1)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "ok"})

    # ── 未注册 fetch 函数 ────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_provider_without_fn_skipped(self, mock_chain, mock_get):
        """provider 注册了但 fetch_fn 为 None → 跳过。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn2 = MagicMock(return_value={"data": "from_p2"})
        provider_map = {"p1": ("P1", None), "p2": ("P2", fn2)}

        result = _fetch_with_fallback("price", provider_map, "test_key", 3600)

        self.assertEqual(result, {"data": "from_p2"})

    # ── 数据验证 ─────────────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_validate_rejects_then_next(self, mock_chain, mock_get):
        """验证函数拒绝 p1 数据 → 尝试 p2。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"invalid": True})
        fn2 = MagicMock(return_value={"data": "ok"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        def validate(raw, provider):
            return provider == "p2" or raw.get("data") is not None

        result = _fetch_with_fallback(
            "price", provider_map, "test_key", 3600, validate=validate)

        self.assertEqual(result, {"data": "ok"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_validate_passes_first(self, mock_chain, mock_get):
        """验证函数通过 p1 数据 → 使用 p1。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"data": "good"})
        fn2 = MagicMock()
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        def validate(raw, provider):
            return True

        result = _fetch_with_fallback(
            "price", provider_map, "test_key", 3600, validate=validate)

        self.assertEqual(result, {"data": "good"})
        fn2.assert_not_called()

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_validate_exception_caught(self, mock_chain, mock_get):
        """验证函数抛出异常 → 跳过当前 provider 尝试下一个。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"data": "bad"})
        fn2 = MagicMock(return_value={"data": "ok"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        def validate(raw, provider):
            if provider == "p1":
                raise ValueError("validation error")
            return True

        result = _fetch_with_fallback(
            "price", provider_map, "test_key", 3600, validate=validate)

        self.assertEqual(result, {"data": "ok"})

    # ── 数据转换 ─────────────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_transform_function(self, mock_chain, mock_set, mock_get):
        """传入 transform 函数 → 对结果应用转换。"""
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"price": "100"})
        provider_map = {"p1": ("P1", fn1)}

        def transform(raw, source_label):
            return {"price": float(raw["price"]), "source": source_label}

        result = _fetch_with_fallback(
            "price", provider_map, "test_key", 3600, transform=transform)

        self.assertEqual(result, {"price": 100.0, "source": "P1"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain.cache_set")
    @patch("src.python.fetcher.chain._get_chain")
    def test_transform_dict_per_provider(self, mock_chain, mock_set, mock_get):
        """transform 为 dict → 按 provider 名选择转换函数。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"price": "100"})
        fn2 = MagicMock(return_value={"price": "200"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        def t1(raw, label):
            return {"price": int(raw["price"]) * 2, "from": label}
        def t2(raw, label):
            return {"price": int(raw["price"]) * 3, "from": label}

        result = _fetch_with_fallback(
            "price", provider_map, "test_key", 3600, transform={"p1": t1, "p2": t2})

        # p1 成功，使用 t1 转换
        self.assertEqual(result, {"price": 200, "from": "P1"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_transform_no_match_in_dict(self, mock_chain, mock_get):
        """transform dict 中没有对应的 provider 转换函数 → 用原始数据。"""
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"data": "raw"})
        provider_map = {"p1": ("P1", fn1)}

        result = _fetch_with_fallback(
            "price", provider_map, "test_key", 3600, transform={"p_other": lambda r, l: None})

        self.assertEqual(result, {"data": "raw"})

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_transform_exception_falls_through(self, mock_chain, mock_get):
        """单 provider 转换失败 → 跳过当前，尝试下一个（不同 provider 走不同 transform）。"""
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"data": "bad"})
        fn2 = MagicMock(return_value={"data": "good"})
        provider_map = {"p1": ("P1", fn1), "p2": ("P2", fn2)}

        def t1(raw, label):
            raise ValueError("p1 transform failed")
        def t2(raw, label):
            return {"data": raw["data"], "transformed": True}

        result = _fetch_with_fallback(
            "price", provider_map, "test_key", 3600, transform={"p1": t1, "p2": t2})

        self.assertEqual(result, {"data": "good", "transformed": True})

    # ── 参数传递 ─────────────────────────────────────────

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_fn_kwargs_passed(self, mock_chain, mock_get):
        """fn_kwargs 正确传递给 fetch 函数。"""
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        fn1 = MagicMock(return_value={"ok": True})
        provider_map = {"p1": ("P1", fn1)}

        _fetch_with_fallback("price", provider_map, "test_key", 3600, fn_kwargs={"code": "600900"})

        fn1.assert_called_once_with(code="600900")


if __name__ == "__main__":
    unittest.main()
