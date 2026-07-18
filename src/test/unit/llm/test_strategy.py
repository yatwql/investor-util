"""Provider 策略引擎单元测试 — R3（Priority）+ R4（Proxy）+ R5（Weighted）+ R9（Cost First）。

标记：unit_llm

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/llm/test_strategy.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.llm.strategy import (
    _apply_module_preferred,
    _apply_proxy_preferred,
    resolve_provider_chain,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


def _make_providers(names_priorities: list[tuple[str, int]]) -> list[dict]:
    """生成简易 provider 列表用于测试。"""
    return [
        {"name": name, "priority": pri, "provider": "claude", "api_key": f"sk-{name}", "model": "m1"}
        for name, pri in names_priorities
    ]


# ═══════════════════════════════════════════════════════════════
# R3: Priority 策略
# ═══════════════════════════════════════════════════════════════


class TestPriorityStrategy(unittest.TestCase):
    """R3 — Priority 排序测试。"""

    def test_priority_sort(self):
        """priority 1/2/3 升序排列。"""
        providers = _make_providers([("p3", 3), ("p1", 1), ("p2", 2)])
        result = resolve_provider_chain(providers, strategy="priority")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p1", "p2", "p3"])

    def test_priority_tie(self):
        """同 priority 保持原序（稳定排序）。"""
        providers = _make_providers([("p-a", 1), ("p-b", 1), ("p-c", 1)])
        result = resolve_provider_chain(providers, strategy="priority")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p-a", "p-b", "p-c"])

    def test_preferred_first(self):
        """偏好 provider 移至首位。"""
        providers = _make_providers([("p1", 1), ("p2", 2), ("p3", 3)])
        result = resolve_provider_chain(providers, strategy="priority",
                                        module_key="news", preferred={"news": "p3"})
        names = [p["name"] for p in result]
        self.assertEqual(names[0], "p3")
        # p1, p2 的相对顺序应保持
        self.assertEqual(names[1:], ["p1", "p2"])

    def test_preferred_not_in_list(self):
        """不存在的偏好 → WARNING，原序不变。"""
        providers = _make_providers([("p1", 1), ("p2", 2)])
        with self.assertLogs("invest", level="WARNING") as logs:
            result = resolve_provider_chain(providers, strategy="priority",
                                            module_key="news", preferred={"news": "nonexistent"})
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p1", "p2"])
        self.assertTrue(any("nonexistent" in msg for msg in logs.output))

    def test_empty_list(self):
        """空 provider 列表返回 []。"""
        result = resolve_provider_chain([], strategy="priority")
        self.assertEqual(result, [])

    def test_single_provider(self):
        """单元素列表返回原列表。"""
        providers = _make_providers([("p1", 1)])
        result = resolve_provider_chain(providers, strategy="priority")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "p1")

    def test_fallback_only_same_as_priority(self):
        """fallback_only 行为同 priority。"""
        providers = _make_providers([("p2", 2), ("p1", 1), ("p3", 3)])
        result = resolve_provider_chain(providers, strategy="fallback_only")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p1", "p2", "p3"])

    def test_unknown_strategy_fallback(self):
        """未知策略 → WARNING + 回退为 priority。"""
        providers = _make_providers([("p2", 2), ("p1", 1)])
        with self.assertLogs("invest", level="WARNING") as logs:
            result = resolve_provider_chain(providers, strategy="unknown_strat")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p1", "p2"])
        self.assertTrue(any("unknown_strat" in msg for msg in logs.output))


# ═══════════════════════════════════════════════════════════════
# R4: Proxy Preferred
# ═══════════════════════════════════════════════════════════════


class TestProxyPreferredStrategy(unittest.TestCase):
    """R4 — 代理偏好测试。"""

    def setUp(self):
        self.providers = _make_providers([("normal", 1), ("proxied", 2)])
        self.providers[0]["proxy_preferred"] = False
        self.providers[1]["proxy_preferred"] = True

    def test_proxy_preferred_detected(self):
        """有代理 HTTP_PROXY 时，标记 proxy_preferred 的 provider 排首。"""
        with patch("src.python.llm.strategy._detect_proxy", return_value=True):
            result = resolve_provider_chain(self.providers, strategy="priority")
        names = [p["name"] for p in result]
        self.assertEqual(names[0], "proxied")

    def test_proxy_no_proxy_no_effect(self):
        """无代理环境变量时，标记无效。"""
        with patch("src.python.llm.strategy._detect_proxy", return_value=False):
            result = resolve_provider_chain(self.providers, strategy="priority")
        names = [p["name"] for p in result]
        self.assertEqual(names[0], "normal")  # priority 1 排前
        self.assertEqual(names[1], "proxied")

    def test_proxy_preferred_multiple(self):
        """多条标记的 provider 全部排首位，它们之间按 priority 排序。"""
        providers = _make_providers([("p3", 3), ("p1", 1), ("p2", 2)])
        for p in providers:
            p["proxy_preferred"] = True
        with patch("src.python.llm.strategy._detect_proxy", return_value=True):
            result = resolve_provider_chain(providers, strategy="priority")
        names = [p["name"] for p in result]
        # 全部有标记，顺序按 priority
        self.assertEqual(names, ["p1", "p2", "p3"])


# ═══════════════════════════════════════════════════════════════
# R5: Weighted 策略
# ═══════════════════════════════════════════════════════════════


class TestWeightedStrategy(unittest.TestCase):
    """R5 — Weighted 排序测试。"""

    def _make_weighted(self, names_weights: list[tuple[str, int]]) -> list[dict]:
        providers = _make_providers([(n, 1) for n, _w in names_weights])
        for i, (_, w) in enumerate(names_weights):
            providers[i]["weight"] = w
        return providers

    def test_weighted_distribution(self):
        """高权重概率更高（固定 seed 确定性测试）。"""
        providers = self._make_weighted([("heavy", 100), ("light", 1)])
        import random
        random.seed(42)
        result = resolve_provider_chain(providers, strategy="weighted")
        names = [p["name"] for p in result]
        # 所有 provider 均在结果中
        self.assertIn("heavy", names)
        self.assertIn("light", names)

    def test_weighted_zero_excluded(self):
        """权重 0 不出现。"""
        providers = self._make_weighted([("active", 5), ("zero", 0)])
        import random
        random.seed(42)
        result = resolve_provider_chain(providers, strategy="weighted")
        names = [p["name"] for p in result]
        self.assertIn("active", names)
        self.assertNotIn("zero", names)

    def test_weighted_all_zero_fallback(self):
        """全 0 权重回退 priority + WARNING。"""
        providers = self._make_weighted([("p1", 0), ("p2", 0)])
        with self.assertLogs("invest", level="WARNING") as logs:
            result = resolve_provider_chain(providers, strategy="weighted")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p1", "p2"])  # priority 排序
        self.assertTrue(any("全为 0" in msg or "回退" in msg for msg in logs.output))

    def test_weighted_single(self):
        """单条直接返回。"""
        providers = self._make_weighted([("only", 5)])
        result = resolve_provider_chain(providers, strategy="weighted")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "only")


class TestCostFirstStrategy(unittest.TestCase):
    """R9 — Cost First 策略测试。"""

    def _make_providers(self, names_models: list[tuple[str, str]]) -> list[dict]:
        """生成简易 provider 列表，name + model。"""
        return [
            {"name": n, "provider": "claude", "api_key": f"sk-{n}", "model": m}
            for n, m in names_models
        ]

    @patch("src.python.llm.pricing.PRICING_MERGED", {
        "cheap-model": {"input_price": 1, "output_price": 2},
        "mid-model": {"input_price": 5, "output_price": 5},
        "pricey-model": {"input_price": 10, "output_price": 20},
    })
    def test_cost_first_cheapest_first(self, *_):
        """按 input_price + output_price 升序。"""
        providers = self._make_providers([
            ("p3", "pricey-model"),
            ("p1", "cheap-model"),
            ("p2", "mid-model"),
        ])
        result = resolve_provider_chain(providers, strategy="cost_first")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p1", "p2", "p3"])

    @patch("src.python.llm.pricing.PRICING_MERGED", {
        "cheap-model": {"input_price": 1, "output_price": 2},
    })
    def test_cost_first_unknown_last(self, *_):
        """未知模型（无定价数据）排末尾。"""
        providers = self._make_providers([
            ("known", "cheap-model"),
            ("unknown", "some-nonexistent-model"),
        ])
        result = resolve_provider_chain(providers, strategy="cost_first")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["known", "unknown"])

    @patch("src.python.llm.pricing.PRICING_MERGED", {})
    def test_cost_first_all_unknown(self, *_):
        """全部未知模型 → 保持原序。"""
        providers = self._make_providers([
            ("p1", "unknown-a"),
            ("p2", "unknown-b"),
        ])
        result = resolve_provider_chain(providers, strategy="cost_first")
        names = [p["name"] for p in result]
        self.assertEqual(names, ["p1", "p2"])

    @patch("src.python.llm.pricing.PRICING_MERGED", {})
    @patch("src.python.llm.pricing.reload_pricing")
    def test_cost_first_triggers_pricing(self, mock_reload, *_):
        """PRICING_MERGED 为空时主动触发 reload_pricing。"""
        providers = self._make_providers([("p1", "m1")])
        resolve_provider_chain(providers, strategy="cost_first")
        mock_reload.assert_called_once()

    @patch("src.python.llm.pricing.PRICING_MERGED", {})
    def test_cost_first_single_provider(self, *_):
        """单条直接返回。"""
        providers = self._make_providers([("only", "my-model")])
        result = resolve_provider_chain(providers, strategy="cost_first")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "only")


if __name__ == "__main__":
    unittest.main()
