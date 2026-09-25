"""LLM 端点级节流与并发治理（`llm/pacing.py`）单元测试。

覆盖：
  - 策略解析（正常 / 缺失 / 全零 / 非法字段逐字段容错）
  - 注册与查询（声明式：provider 条目名 → 策略）
  - 无约束端点零开销直通（不阻塞、不改行为）
  - 最小间隔生效（含抖动路径）
  - 在途并发上限生效（多线程压测峰值 == 上限）
  - 403 配额/风控拒绝 → 不重试且不计入「网络类」失败原因

回归背景：全局常量 `llm_max_concurrency` 无法表达「同一程序、不同端点不同策略」——
订阅制编码端点需要低频串行，按量付费端点可放开并发。本机制把策略声明化到
`llm_providers.json` 的 provider 条目，缺省即无约束（与未引入时逐字节一致）。
"""

from __future__ import annotations

import threading
import time

import pytest

from src.python.llm.pacing import (
    PacingGate,
    get_policy,
    parse_policy,
    register_policies,
    reset_policies,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


@pytest.fixture(autouse=True)
def _isolate_policies():
    """策略为模块级单例：每个用例前清空、后清空，避免相互污染。"""
    reset_policies()
    yield
    reset_policies()


class TestParsePolicy:
    """配置段 → 策略的解析与容错。"""

    def test_none_and_empty_are_noop(self):
        assert parse_policy(None) is None
        assert parse_policy({}) is None
        assert parse_policy({"min_interval": 0, "max_concurrency": 0}) is None

    def test_full_policy_parsed(self):
        policy = parse_policy({"min_interval": 20, "jitter": 0.2, "max_concurrency": 1})
        assert policy is not None
        assert policy.min_interval == 20.0
        assert policy.jitter == 0.2
        assert policy.max_concurrency == 1
        assert not policy.is_noop

    def test_invalid_field_ignored_per_field(self):
        """坏字段逐字段忽略并保留其余有效字段（不因笔误使端点不可用）。"""
        policy = parse_policy({"min_interval": "abc", "max_concurrency": 2})
        assert policy is not None
        assert policy.min_interval == 0.0
        assert policy.max_concurrency == 2

    def test_values_clamped_to_sane_range(self):
        policy = parse_policy({"min_interval": -5, "jitter": 5, "max_concurrency": -3})
        assert policy is None  # 全部夹到 0 → 无约束

    def test_interval_only_policy(self):
        """只声明间隔（不限制并发）也生效——支持「串行不限、仅控频」的端点。"""
        policy = parse_policy({"min_interval": 3})
        assert policy is not None and policy.max_concurrency == 0


class TestRegistry:
    def test_register_and_query(self):
        register_policies(
            [
                {"name": "kimi-code", "pacing": {"min_interval": 1, "max_concurrency": 1}},
                {"name": "openai-paid"},
            ]
        )
        assert get_policy("kimi-code") is not None
        assert get_policy("openai-paid") is None, "未声明 pacing 的端点必须无约束"
        assert get_policy("unknown") is None

    def test_reregister_replaces(self):
        register_policies([{"name": "a", "pacing": {"min_interval": 1}}])
        assert get_policy("a") is not None
        register_policies([{"name": "a"}])
        assert get_policy("a") is None, "重载后应反映最新配置"

    def test_entries_without_name_skipped(self):
        register_policies([{"pacing": {"min_interval": 1}}, None])  # type: ignore[list-item]
        assert get_policy("") is None


class TestPacingGate:
    def test_unconstrained_is_near_zero_cost(self):
        """无约束端点：大量过闸不得引入可观测延迟（回归「默认零影响」）。"""
        register_policies([{"name": "paid"}])
        t0 = time.monotonic()
        for _ in range(200):
            with PacingGate("paid"):
                pass
        assert time.monotonic() - t0 < 0.05

    def test_min_interval_serializes_requests(self):
        """间隔生效：连续多次请求的总耗时 ≥ 请求次数减一 乘 间隔。"""
        register_policies([{"name": "slow", "pacing": {"min_interval": 0.05}}])
        t0 = time.monotonic()
        for _ in range(3):
            with PacingGate("slow"):
                pass
        assert time.monotonic() - t0 >= 0.09

    def test_jitter_path_also_waits(self):
        """抖动非零时走另一分支，仍须遵守间隔下限。"""
        register_policies([{"name": "jit", "pacing": {"min_interval": 0.05, "jitter": 0.5}}])
        t0 = time.monotonic()
        for _ in range(2):
            with PacingGate("jit"):
                pass
        assert time.monotonic() - t0 >= 0.045

    def test_max_concurrency_enforced(self):
        """在途并发峰值不得超过声明的上限。"""
        register_policies([{"name": "serial", "pacing": {"max_concurrency": 1}}])
        counters = {"cur": 0, "peak": 0}
        lock = threading.Lock()

        def worker():
            with PacingGate("serial"):
                with lock:
                    counters["cur"] += 1
                    counters["peak"] = max(counters["peak"], counters["cur"])
                time.sleep(0.03)
                with lock:
                    counters["cur"] -= 1

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert counters["peak"] == 1

    def test_gate_releases_semaphore_on_exception(self):
        """异常退出也必须释放并发许可（否则端点被永久占死）。"""
        register_policies([{"name": "serial", "pacing": {"max_concurrency": 1}}])
        for _ in range(3):
            with pytest.raises(RuntimeError):
                with PacingGate("serial"):
                    raise RuntimeError("boom")
        # 若未释放，此处会阻塞超时；能走完即证明已释放
        done = threading.Event()

        def worker():
            with PacingGate("serial"):
                pass
            done.set()

        threading.Thread(target=worker, daemon=True).start()
        assert done.wait(timeout=2.0)

    def test_no_policy_gate_is_noop_property(self):
        register_policies([{"name": "paid"}])
        assert PacingGate("paid").is_noop
        register_policies([{"name": "paid", "pacing": {"min_interval": 1}}])
        assert not PacingGate("paid").is_noop


class TestQuotaFailureReason:
    """403 配额/风控拒绝的失败原因与「网络类」区分（差异化提示的基础）。"""

    def test_quota_reason_constant_distinct(self):
        from src.python.llm.prompts_core import (
            FAIL_REASON_NETWORK_ERROR,
            FAIL_REASON_QUOTA_EXCEEDED,
            FAIL_REASON_TIMEOUT,
        )

        assert FAIL_REASON_QUOTA_EXCEEDED not in (FAIL_REASON_NETWORK_ERROR, FAIL_REASON_TIMEOUT)

    def test_all_protocol_facades_export_reason(self):
        """三层门面（llm.prompts_core / llm.prompts / llm 包）均须可导入。"""
        from src.python.llm import FAIL_REASON_QUOTA_EXCEEDED as a
        from src.python.llm.prompts import FAIL_REASON_QUOTA_EXCEEDED as b
        from src.python.llm.prompts_core import FAIL_REASON_QUOTA_EXCEEDED as c

        assert a == b == c == "quota_exceeded"
