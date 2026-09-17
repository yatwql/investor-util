"""链路失败原因诊断单元测试 —— 「错误即 UX」。

缺陷背景：链路全部失败时调用方只拿到 ``None``，失败原因仅存在于 logger
输出中。用户看到「行情数据不可用」却无从知道是超时、限速还是返回空，
也无从判断该找哪个数据源。本文件锁定 ``FailureDiagnostics`` 的采集契约：
逐 provider 记录可读原因，且不传时链路行为逐字不变。
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pytest

from src.python.fetcher.chain import (
    _REASON_MAX_LEN,
    FailureDiagnostics,
    _brief_reason,
    fetch_with_fallback,
    reset_provider_skip,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]


@pytest.mark.unit
@pytest.mark.unit_fetcher
class TestBriefReason(unittest.TestCase):
    """短原因格式化：压成一行、超长截断。"""

    def test_whitespace_collapsed_to_single_line(self):
        self.assertEqual(_brief_reason("连接\n超时\t 重试"), "连接 超时 重试")

    def test_short_text_unchanged(self):
        self.assertEqual(_brief_reason("返回空"), "返回空")

    def test_long_text_truncated_with_ellipsis(self):
        reason = _brief_reason("x" * 500)
        self.assertEqual(len(reason), _REASON_MAX_LEN)
        self.assertTrue(reason.endswith("…"))

    def test_boundary_length_not_truncated(self):
        text = "y" * _REASON_MAX_LEN
        self.assertEqual(_brief_reason(text), text)

    def test_non_string_input_coerced(self):
        self.assertEqual(_brief_reason(ValueError("boom")), "boom")


@pytest.mark.unit
@pytest.mark.unit_fetcher
class TestFailureDiagnosticsCollector(unittest.TestCase):
    """收集器本身：空态、追加、汇总格式。"""

    def test_empty_has_no_failure(self):
        diag = FailureDiagnostics()
        self.assertFalse(diag.has_failure)
        self.assertEqual(diag.summary(), "")

    def test_add_then_has_failure(self):
        diag = FailureDiagnostics()
        diag.add("腾讯财经", "连接超时")
        self.assertTrue(diag.has_failure)

    def test_summary_is_human_readable(self):
        diag = FailureDiagnostics()
        diag.add("腾讯财经", "连接超时")
        diag.add("新浪财经", "返回空")
        self.assertEqual(diag.summary(), "腾讯财经(连接超时)；新浪财经(返回空)")

    def test_instances_do_not_share_state(self):
        """默认工厂必须各自新建列表——共享会跨调用串味。"""
        first = FailureDiagnostics()
        first.add("A", "x")
        self.assertFalse(FailureDiagnostics().has_failure)


@pytest.mark.unit
@pytest.mark.unit_fetcher
class TestFetchWithFallbackDiagnostics(unittest.TestCase):
    """fetch_with_fallback 的失败原因采集。"""

    def setUp(self):
        reset_provider_skip()

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_success_collects_nothing(self, mock_chain, mock_get):
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        diag = FailureDiagnostics()

        result = fetch_with_fallback(
            "price", {"p1": ("P1", MagicMock(return_value={"ok": 1}))}, "k", 3600, diagnostics=diag
        )

        self.assertEqual(result, {"ok": 1})
        self.assertFalse(diag.has_failure)

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_transport_exception_reason_is_readable(self, mock_chain, mock_get):
        """异常 → 原因含异常类型，而非不透明的 "transport"。"""
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        fn = MagicMock(side_effect=TimeoutError("连接超时"))
        diag = FailureDiagnostics()

        fetch_with_fallback("price", {"p1": ("腾讯财经", fn)}, "k", 3600, diagnostics=diag)

        self.assertEqual(diag.summary(), "腾讯财经(TimeoutError: 连接超时)")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_rate_limit_reason_is_specific(self, mock_chain, mock_get):
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        fn = MagicMock(side_effect=RuntimeError("HTTP 429 Too Many Requests"))
        diag = FailureDiagnostics()

        fetch_with_fallback("price", {"p1": ("腾讯财经", fn)}, "k", 3600, diagnostics=diag)

        self.assertEqual(diag.summary(), "腾讯财经(API 限速(429))")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_empty_result_reason(self, mock_chain, mock_get):
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        diag = FailureDiagnostics()

        fetch_with_fallback("price", {"p1": ("新浪财经", MagicMock(return_value=None))}, "k", 3600, diagnostics=diag)

        self.assertEqual(diag.summary(), "新浪财经(返回空)")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_validation_failure_reason(self, mock_chain, mock_get):
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        diag = FailureDiagnostics()

        fetch_with_fallback(
            "price",
            {"p1": ("东方财富", MagicMock(return_value={"nav": 0}))},
            "k",
            3600,
            validate=lambda raw, provider: False,
            diagnostics=diag,
        )

        self.assertEqual(diag.summary(), "东方财富(数据校验未通过)")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_all_providers_recorded_in_order(self, mock_chain, mock_get):
        """多 provider 全失败 → 逐个记录，顺序与链路一致。"""
        mock_chain.return_value = ["p1", "p2", "p3"]
        mock_get.return_value = None
        provider_map = {
            "p1": ("腾讯财经", MagicMock(side_effect=TimeoutError("超时"))),
            "p2": ("新浪财经", MagicMock(return_value=None)),
            "p3": ("东方财富", MagicMock(side_effect=ConnectionError("拒绝连接"))),
        }
        diag = FailureDiagnostics()

        result = fetch_with_fallback("price", provider_map, "k", 3600, diagnostics=diag)

        self.assertIsNone(result)
        self.assertEqual(
            diag.summary(),
            "腾讯财经(TimeoutError: 超时)；新浪财经(返回空)；东方财富(ConnectionError: 拒绝连接)",
        )

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_unknown_provider_recorded(self, mock_chain, mock_get):
        mock_chain.return_value = ["ghost", "p1"]
        mock_get.return_value = None
        diag = FailureDiagnostics()

        fetch_with_fallback("price", {"p1": ("P1", MagicMock(return_value={"ok": 1}))}, "k", 3600, diagnostics=diag)

        self.assertEqual(diag.summary(), "ghost(未注册)")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_provider_without_fn_recorded(self, mock_chain, mock_get):
        mock_chain.return_value = ["p1", "p2"]
        mock_get.return_value = None
        diag = FailureDiagnostics()

        fetch_with_fallback(
            "price",
            {"p1": ("P1", None), "p2": ("P2", MagicMock(return_value={"ok": 1}))},
            "k",
            3600,
            diagnostics=diag,
        )

        self.assertEqual(diag.summary(), "P1(无 fetch 函数)")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_circuit_broken_provider_recorded(self, mock_chain, mock_get):
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None
        diag = FailureDiagnostics()

        with patch("src.python.fetcher.chain.get_registry") as mock_reg:
            mock_reg.return_value.is_circuit_broken.return_value = True
            fetch_with_fallback("price", {"p1": ("腾讯财经", MagicMock())}, "k", 3600, diagnostics=diag)

        self.assertEqual(diag.summary(), "腾讯财经(已被熔断跳过)")

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_no_diagnostics_keeps_legacy_behavior(self, mock_chain, mock_get):
        """不传 diagnostics → 返回值与既往逐字一致（不因新增采集而变）。"""
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None

        result = fetch_with_fallback("price", {"p1": ("P1", MagicMock(side_effect=TimeoutError("x")))}, "k", 3600)

        self.assertIsNone(result)


@pytest.mark.unit
@pytest.mark.unit_fetcher
class TestRegistryFailureContextIsReadable(unittest.TestCase):
    """契约登记处：熔断上下文不再是不透明的 ":transport"。"""

    def setUp(self):
        reset_provider_skip()

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_transport_failure_records_readable_context(self, mock_chain, mock_get):
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None

        with patch("src.python.fetcher.chain.get_registry") as mock_reg:
            reg = mock_reg.return_value
            reg.is_circuit_broken.return_value = False
            fetch_with_fallback(
                "price",
                {"p1": ("腾讯财经", MagicMock(side_effect=TimeoutError("连接超时")))},
                "k",
                3600,
            )

        reg.record_failure.assert_called_once()
        provider_name, context = reg.record_failure.call_args[0]
        self.assertEqual(provider_name, "p1")
        self.assertIn("price", context)
        self.assertIn("TimeoutError", context)
        self.assertNotIn(":transport", context)

    @patch("src.python.fetcher.chain.cache_get")
    @patch("src.python.fetcher.chain._get_chain")
    def test_code_level_empty_does_not_trip_circuit(self, mock_chain, mock_get):
        """返回空属代码级（API 不识别该代码），不计入熔断——既有口径不变。"""
        mock_chain.return_value = ["p1"]
        mock_get.return_value = None

        with patch("src.python.fetcher.chain.get_registry") as mock_reg:
            reg = mock_reg.return_value
            reg.is_circuit_broken.return_value = False
            fetch_with_fallback("price", {"p1": ("P1", MagicMock(return_value=None))}, "k", 3600)

        reg.record_failure.assert_not_called()
