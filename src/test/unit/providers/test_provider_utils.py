"""providers/_utils 共享原语测试 —— 「provider 自陈失败原因」载体。

回归：provider 返回 None 时链路只能记「返回空」，无法区分「源故障」（要排查网络/凭据）
与「该文档确实没这一节」（正常业务结果）。载体必须**按线程隔离**（批量取数是多线程），
且**消费即清**（避免上一次调用的原因串到下一次）。

另有两条防串味护栏（实测 CI 3.11 暴露）：① 链路在每次尝试 provider 前先
``clear_last_reason()``（防未经消费的残值串到本次诊断）；② conftest 的
autouse fixture 在每个用例前复位载体（防测试间串味）。

运行：
  pytest src/test/unit/providers/test_provider_utils.py -v
"""

from __future__ import annotations

import threading

import pytest

from src.python.providers import _utils as pu

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class TestLastReasonCarrier:
    """set_last_reason / take_last_reason 的取值、消费即清与线程隔离。"""

    def teardown_method(self):
        pu.take_last_reason()  # 清残留

    def test_set_then_take(self):
        pu.set_last_reason("该文档无目标章节")
        assert pu.take_last_reason() == "该文档无目标章节"

    def test_take_clears_value(self):
        """消费即清：第二次取回落到默认值，避免原因串到下一次调用。"""
        pu.set_last_reason("第一次的原因")
        assert pu.take_last_reason() == "第一次的原因"
        assert pu.take_last_reason() == ""

    def test_default_when_unset(self):
        assert pu.take_last_reason() == ""
        assert pu.take_last_reason("返回空") == "返回空"

    def test_default_not_used_when_reason_present(self):
        pu.set_last_reason("HTTP 404")
        assert pu.take_last_reason("返回空") == "HTTP 404"

    def test_reason_is_thread_local(self):
        """按线程隔离：子线程设置的原因不影响主线程（批量取数并发安全）。"""
        seen: dict[str, str] = {}

        def _worker():
            pu.set_last_reason("子线程原因")
            seen["child"] = pu.take_last_reason()

        t = threading.Thread(target=_worker)
        t.start()
        t.join()

        assert seen["child"] == "子线程原因"
        assert pu.take_last_reason() == "", "子线程的原因不得泄漏到主线程"

    def test_clear_last_reason_discards_residue(self):
        """`clear_last_reason` 丢弃残值（供链路「尝试前先清」使用）。"""
        pu.set_last_reason("HTTP 500")
        pu.clear_last_reason()
        assert pu.take_last_reason() == ""

    def test_stale_reason_does_not_leak_into_next_chain_attempt(self, monkeypatch):
        """回归：**未消费的残值不得串到下一次链路尝试**（链路「尝试前先清」契约）。

        实测故障：provider 把原因写好后未经链路消费（直连调用 / 命中缓存直接返回）
        就结束，残值留在本线程载体里；当后续另一个 provider 返回 ``None`` 时，
        链路读到的会是**上一条命令的失败原因**。
        """
        from src.python.fetcher import chain as ch

        # 上一次调用留下的残值（模拟另一个 provider 未经消费的写入）
        pu.set_last_reason("HTTP 500")

        def _fetch_returns_none(**_kwargs):
            return None  # 本次 provider 未写原因（真正的「返回空」）

        monkeypatch.setattr(ch, "cache_get", lambda *a, **k: None)
        monkeypatch.setattr(ch, "cache_set", lambda *a, **k: None)
        diag = ch.FailureDiagnostics()
        result = ch.fetch_with_fallback(
            "price",
            {"tencent": ("腾讯财经", _fetch_returns_none)},
            "price_stock_000000",
            60.0,
            diagnostics=diag,
        )
        assert result is None
        # 链路尝试前已清残值 → 诊断只反映本次（「返回空」），不带上一次的 HTTP 500
        assert "HTTP 500" not in diag.summary()
        assert pu.take_last_reason() == "", "上一条命令的失败原因不得残留到下一次尝试"

    def test_residue_cannot_cross_tests(self):
        """回归：**测试间不得串味**（conftest 的 ``_auto_reset_last_reason`` 兜底）。

        实测故障：provider 用例直接调 ``datasink``/``cninfo`` 只看返回值、不消费原因，
        残值留在 worker 主线程槽位，污染同 worker 中下一个读载体的用例（CI 3.11 上
        ``test_reason_is_thread_local`` 读到 ``'HTTP 500'``）。本用例钉住「进入用例时
        载体已是干净的」这一由 autouse fixture 保证的不变量。
        """
        assert getattr(pu._last_reason, "value", "") == ""
        assert pu.take_last_reason() == ""
