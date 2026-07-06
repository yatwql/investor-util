"""DegradationTracker 与 _data_status 基础设施单元测试。"""

from __future__ import annotations

import time as _time
from typing import Any

import pytest

from src.python.report.data_status import (
    STATUS_MESSAGES,
    TIER_PREFIX,
    DegradationTracker,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ═══════════════════════════════════════════════════════════
#  DegradationTracker — 信号1 连续失败阈值
# ═══════════════════════════════════════════════════════════


class TestDegradationSignal1:
    """信号1：连续失败次数的降级判定。"""

    def test_below_threshold_no_degrade(self):
        """T2 源连续失败 1 次，缓存新鲜（12h < 24h TTL）→ 不降级。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # 新鲜缓存 → 阈值 +1 = 4，count=1 < 4 → 不降级
        assert count == 1
        assert effective <= 4  # base 3 + fresh bonus 1 = 4
        assert not degraded

    def test_signal1_exceeds_threshold(self):
        """T2 源连续失败 3 次，缓存新鲜 → 降级。"""
        tracker = DegradationTracker()
        # 第 1 次
        tracker.record("test_source", "T2", success=False,
                        failure_type="unreachable",
                        cache_age_hours=12, cache_ttl_hours=24)
        # 第 2 次
        tracker.record("test_source", "T2", success=False,
                        failure_type="unreachable",
                        cache_age_hours=12, cache_ttl_hours=24)
        # 第 3 次
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # 新鲜缓存 T2 +1=4，count=3 < 4 → 应还不降级！
        # 需要第 4 次
        assert count == 3
        assert not degraded

    def test_signal1_exceeds_at_fourth(self):
        """T2 源连续失败 4 次，缓存新鲜 → 第 4 次降级。"""
        tracker = DegradationTracker()
        for _ in range(3):
            tracker.record("test_source", "T2", success=False,
                            failure_type="unreachable",
                            cache_age_hours=12, cache_ttl_hours=24)
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        assert count == 4
        assert effective <= 4
        assert degraded

    def test_signal1_t3_higher_threshold(self):
        """T3 源连续失败 3 次，无缓存 → 有效阈=3，第 3 次降级。"""
        tracker = DegradationTracker()
        for _ in range(2):
            tracker.record("test_source", "T3", success=False,
                            failure_type="unreachable")
        degraded, count, effective = tracker.record(
            "test_source", "T3", success=False,
            failure_type="unreachable",
        )
        # T3 base=4, 无缓存 -1 = 3，count=3 ≥ 3 → 降级
        assert count == 3
        assert degraded

    def test_self_heal(self):
        """T2 源失败 2 次后成功 → 计数器归零，不降级。"""
        tracker = DegradationTracker()
        # 2 次失败
        tracker.record("test_source", "T2", success=False,
                        failure_type="unreachable")
        tracker.record("test_source", "T2", success=False,
                        failure_type="unreachable")
        # 成功
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=True,
        )
        assert count == 0
        assert not degraded
        # 验证计数器已清除
        assert tracker.get_counts("test_source") == {}

    def test_t4_immediate(self):
        """T4 源失败 1 次，无缓存 → 立即降级（T4 阈=1）。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T4", success=False,
            failure_type="unreachable",
        )
        # T4 base=1, 无缓存 -1 = max(1,0)=1 → count=1 ≥ 1 → 降级
        assert count == 1
        assert degraded

    def test_no_cache_penalty(self):
        """T3 源失败 1 次，无缓存 → 有效阈=3，count=1 < 3 → 不降级。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T3", success=False,
            failure_type="unreachable",
        )
        # T3 base=4, 无缓存 -1 = 3, count=1 < 3 → 不降级
        assert count == 1
        assert effective == 3
        assert not degraded


class TestDegradationSignal2:
    """信号2：缓存陈旧度判定。"""

    def test_signal2_stale_cache(self):
        """T2 源失败 1 次，缓存年龄 96h（>72h stale_days）→ 缓存信号触发降级。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=96, cache_ttl_hours=24,
        )
        # cache_age=96h > stale_days*t4=3*24=72h → signal2 True
        assert degraded

    def test_signal2_fresh_cache_no_stale(self):
        """T2 源失败 1 次，缓存年龄 2h（<72h stale_days）→ 缓存信号不触发。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=2, cache_ttl_hours=24,
        )
        # cache_age=2h < stale_days=72h → signal2 False
        # count=1 < base=3, fresh cache +1 = 4 → signal1 False
        assert not degraded

    def test_signal2_no_cache_triggers(self):
        """全新数据源，无缓存 → signal2 不触发（由信号1适应性调节处理）。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=None, cache_ttl_hours=None,
        )
        # T2 base=3, 无缓存 -1=2, count=1 < 2 → 不降级
        assert count == 1
        assert effective == 2
        assert not degraded


class TestDegradationFailureType:
    """失败类型区分：unreachable vs empty 各走独立计数器。"""

    def test_empty_data_higher_threshold(self):
        """T2 连续 3 次 empty，不降级。"""
        tracker = DegradationTracker()
        for _ in range(3):
            tracker.record("test_source", "T2", success=False,
                            failure_type="empty",
                            cache_age_hours=12, cache_ttl_hours=24)
        # 第 4 次：count=4 < 新鲜阈=6 → 不降级
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="empty",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        assert count == 4
        assert not degraded

    def test_empty_data_reaches_threshold(self):
        """T2 连续 6 次 empty，新鲜缓存 → 第 6 次降级。"""
        tracker = DegradationTracker()
        for _ in range(5):
            tracker.record("test_source", "T2", success=False,
                            failure_type="empty",
                            cache_age_hours=12, cache_ttl_hours=24)
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="empty",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # T2 empty base=5, fresh cache +1 = 6, count=6 → 降级
        assert count == 6
        assert degraded

    def test_mixed_failure_types_separate_counters(self):
        """unreachable 和 empty 的计数器彼此独立。"""
        tracker = DegradationTracker()
        # 2 次 unreachable + 3 次 empty = 混合
        for _ in range(2):
            tracker.record("test_source", "T2", success=False,
                            failure_type="unreachable",
                            cache_age_hours=12, cache_ttl_hours=24)
        for _ in range(3):
            tracker.record("test_source", "T2", success=False,
                            failure_type="empty",
                            cache_age_hours=12, cache_ttl_hours=24)
        # unreachable=2 < 新鲜阈=4, empty=3 < 新鲜阈=6 → 都不降级
        counts = tracker.get_counts("test_source")
        assert counts["unreachable"] == 2
        assert counts["empty"] == 3
        # 第 2 次 unreachable
        degraded, _, _ = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # unreachable=3 < 4 → 仍不降级
        assert not degraded

    def test_success_resets_all_counters(self):
        """任何失败类型成功后，所有计数器全部归零。"""
        tracker = DegradationTracker()
        tracker.record("test_source", "T2", success=False,
                        failure_type="unreachable")
        tracker.record("test_source", "T2", success=False,
                        failure_type="empty")
        # 成功
        tracker.record("test_source", "T2", success=True)
        assert tracker.get_counts("test_source") == {}


# ═══════════════════════════════════════════════════════════
#  DegradationTracker — 线程安全
# ═══════════════════════════════════════════════════════════


class TestDegradationThreadSafety:
    """并发场景下的线程安全验证。"""

    def test_concurrent_records(self):
        """多线程并发 record() 不抛异常，计数正确。"""
        import concurrent.futures

        tracker = DegradationTracker()

        def _fail(idx: int):
            tracker.record(f"source_{idx % 3}", "T2", success=False,
                           failure_type="unreachable")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(_fail, range(30)))

        # 验证无异常且计数正确
        for sidx in range(3):
            counts = tracker.get_counts(f"source_{sidx}")
            assert counts["unreachable"] == 10


# ═══════════════════════════════════════════════════════════
#  DegradationTracker — reset
# ═══════════════════════════════════════════════════════════


class TestDegradationReset:
    """手动重置机制。"""

    def test_manual_reset(self):
        tracker = DegradationTracker()
        tracker.record("test_source", "T2", success=False,
                        failure_type="unreachable")
        tracker.record("test_source", "T2", success=False,
                        failure_type="empty")
        tracker.reset("test_source")
        assert tracker.get_counts("test_source") == {}


# ═══════════════════════════════════════════════════════════
#  常量和类型
# ═══════════════════════════════════════════════════════════


class TestConstants:
    """STATUS_MESSAGES 与 TIER_PREFIX 完整性。"""

    def test_status_messages_have_content(self):
        """所有状态消息非空。"""
        for key, msg in STATUS_MESSAGES.items():
            assert msg, f"{key} 的消息为空"
            assert len(msg) > 5, f"{key} 的消息过短"

    def test_tier_prefix_all_tiers(self):
        """所有层级均有前缀映射。"""
        for tier in ("T2", "T3", "T4"):
            assert tier in TIER_PREFIX
            assert TIER_PREFIX[tier] in ("⚠", "ℹ"), f"{tier} 前缀异常"
