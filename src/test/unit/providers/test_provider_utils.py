"""providers/_utils 共享原语测试 —— 「provider 自陈失败原因」载体。

回归：provider 返回 None 时链路只能记「返回空」，无法区分「源故障」（要排查网络/凭据）
与「该文档确实没这一节」（正常业务结果）。载体必须**按线程隔离**（批量取数是多线程），
且**消费即清**（避免上一次调用的原因串到下一次）。

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
