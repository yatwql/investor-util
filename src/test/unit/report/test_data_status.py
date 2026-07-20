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
        # T2 base=2，新鲜缓存 +1 = 3，count=1 < 3 → 不降级
        # effective = min(unreachable_eff=3, empty_eff=4) = 3
        assert count == 1
        assert effective == 3
        assert not degraded

    def test_signal1_exceeds_threshold(self):
        """T2 源连续失败 3 次，缓存新鲜 → 第 3 次降级（T2 base=2，新鲜+1=3）。"""
        tracker = DegradationTracker()
        for _ in range(2):
            tracker.record("test_source", "T2", success=False,
                            failure_type="unreachable",
                            cache_age_hours=12, cache_ttl_hours=24)
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        assert count == 3
        assert effective == 3
        assert degraded

    def test_signal1_exceeds_at_fourth(self):
        """T2 源连续失败 4 次（无缓存）→ 即使阈降到最低也降级。"""
        tracker = DegradationTracker()
        for _ in range(4):
            tracker.record("test_source", "T2", success=False,
                            failure_type="unreachable")
        # T2 base=2, 无缓存 -1=1, count=4≥1 → 降级
        counts = tracker.get_counts("test_source")
        assert counts["unreachable"] == 4

    def test_signal1_t3_higher_empty_threshold(self):
        """T3 empty（base=3）比 unreachable（base=2）需要更多失败才降级。"""
        tracker = DegradationTracker()
        # T3 empty 在新鲜缓存下 effective empty=4，2 次不降级
        for _ in range(2):
            tracker.record("test_source", "T3", success=False,
                            failure_type="empty",
                            cache_age_hours=12, cache_ttl_hours=24)
        # 第 3 次：empty_count=3 < empty_eff=4 → 不降级
        # effective = min(unreachable_eff=3, empty_eff=4) = 3
        degraded, count, effective = tracker.record(
            "test_source", "T3", success=False,
            failure_type="empty",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        assert count == 3
        assert not degraded

    def test_signal1_t3_empty_reaches_threshold(self):
        """T3 连续 4 次 empty，新鲜缓存 → 第 4 次降级。"""
        tracker = DegradationTracker()
        for _ in range(3):
            tracker.record("test_source", "T3", success=False,
                            failure_type="empty",
                            cache_age_hours=12, cache_ttl_hours=24)
        # 第 4 次：empty_count=4 ≥ empty_eff=4 → 降级
        degraded, count, effective = tracker.record(
            "test_source", "T3", success=False,
            failure_type="empty",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        assert count == 4
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
        """T3 源失败 1 次，无缓存 → 信号1自适应触达阈值（T3 base=2→无缓存-1=1）。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T3", success=False,
            failure_type="unreachable",
        )
        # T3 base=2, 无缓存 -1=1, count=1 ≥ 1 → 信号1触发降级
        # count 尚未达到新鲜缓存时的阈=3，但无缓存惩罚让阈降到最低=1
        assert count == 1
        assert degraded

    def test_fresh_cache_prevents_premature_degrade(self):
        """T3 源失败 1 次，新鲜缓存 → 有效阈=3，count=1 < 3 → 不降级。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T3", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # T3 base=2, 新鲜缓存+1=3, count=1 < 3 → 不降级
        # effective = min(unreachable_eff=3, empty_eff=4) = 3
        # cache_age=12h < stale_days=14d=336h → 信号2不触发
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
        # cache_age=96h > stale_days*t2=3*24=72h → signal2 True
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
        # count=1 < 有效阈=3（T2 base=2, fresh+1）→ signal1 False
        assert not degraded

    def test_signal2_no_cache_triggers(self):
        """全新数据源，无缓存 → 信号1自适应触达阈值（T2 base=2→无缓存-1=1）。"""
        tracker = DegradationTracker()
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=None, cache_ttl_hours=None,
        )
        # T2 base=2, 无缓存 -1=1 → count=1 ≥ 1 → 降级
        # effective = min(unreachable_eff=1, empty_eff=2) = 1
        assert count == 1
        assert effective == 1
        assert degraded


class TestDegradationFailureType:
    """失败类型区分：unreachable vs empty 各走独立计数器。"""

    def test_empty_data_higher_threshold(self):
        """T2 empty（base=3）比 unreachable（base=2）需要更多失败才降级。"""
        tracker = DegradationTracker()
        # fresh cache 下 unreachable_eff=3, empty_eff=4
        # 2 次 empty：count=2 < 4 → 不降级
        for _ in range(2):
            tracker.record("test_source", "T2", success=False,
                            failure_type="empty",
                            cache_age_hours=12, cache_ttl_hours=24)
        # 第 3 次仍小于 empty 有效阈
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="empty",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # empty_count=3 < empty_eff=4 → 不降级
        assert count == 3
        assert not degraded
        # 而 3 次 unreachable 在此环境下会降级（unreachable_eff=3）
        for _ in range(2):
            tracker.record("test_source2", "T2", success=False,
                            failure_type="unreachable",
                            cache_age_hours=12, cache_ttl_hours=24)
        degraded2, count2, _ = tracker.record(
            "test_source2", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        assert count2 == 3
        assert degraded2

    def test_empty_data_reaches_threshold(self):
        """T2 连续 4 次 empty，新鲜缓存 → 第 4 次降级（base=3, fresh+1=4）。"""
        tracker = DegradationTracker()
        for _ in range(3):
            tracker.record("test_source", "T2", success=False,
                            failure_type="empty",
                            cache_age_hours=12, cache_ttl_hours=24)
        degraded, count, effective = tracker.record(
            "test_source", "T2", success=False,
            failure_type="empty",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # empty_count=4 ≥ empty_eff=4 → 降级
        assert count == 4
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
        # unreachable=2 < 新鲜有效阈=3, empty=3 < 新鲜有效阈=4 → 都不降级
        counts = tracker.get_counts("test_source")
        assert counts["unreachable"] == 2
        assert counts["empty"] == 3
        # 第 3 次 unreachable（独立计数器，不受 empty 影响）
        degraded, _, _ = tracker.record(
            "test_source", "T2", success=False,
            failure_type="unreachable",
            cache_age_hours=12, cache_ttl_hours=24,
        )
        # unreachable=3 ≥ 新鲜有效阈=3 → 降级（empty=3 未达自身阈值但独立不影响）
        assert degraded

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
#  DegradationTracker — 跨会话持久化
# ═══════════════════════════════════════════════════════════


class TestDegradationPersistence:
    """跨会话持久化机制（模拟会话重启）。"""

    def test_success_writes_persist_file(self, tmp_path):
        """成功 record() 后持久化文件应包含时间戳。"""
        p = tmp_path / "test_state.json"
        tracker = DegradationTracker(persist_path=str(p))
        tracker.record("src_a", "T2", success=True)
        assert p.exists()
        import json
        state = json.loads(p.read_text(encoding="utf-8"))
        assert "src_a" in state
        assert isinstance(state["src_a"], float)

    def test_cross_session_stale_detected(self, tmp_path):
        """新会话能读取旧会话的成功时间戳 → 信号2跨会话触发。"""
        p = tmp_path / "test_cross.json"
        # 会话 1：记录一次成功
        t1 = DegradationTracker(persist_path=str(p))
        t1.record("src_a", "T2", success=True)
        # 将会话1抛弃，模拟重启
        import json
        state = json.loads(p.read_text(encoding="utf-8"))
        # 把时间戳改到极旧（超过 stale_days=3）
        old_ts = 1000000.0
        state["src_a"] = old_ts
        p.write_text(json.dumps(state), encoding="utf-8")
        # 会话 2：加载旧状态，检测到陈旧
        t2 = DegradationTracker(persist_path=str(p))
        # 一次失败 + 无缓存 → 自适应调节阈值-1（T2 base=2→1）
        # 而持久化时间戳 56 年前 > stale_days 3d → 信号2应触发
        degraded, _, _ = t2.record(
            "src_a", "T2", success=False,
            failure_type="unreachable",
        )
        assert degraded


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


# ═══════════════════════════════════════════════════════════
#  get_tracker() 单例工厂 + get_log() + reset_tracker()
# ═══════════════════════════════════════════════════════════


class TestGetTracker:
    """get_tracker() 单例工厂 + get_log() + reset_tracker()."""

    def test_get_tracker_returns_same_instance(self):
        """连续两次调用 get_tracker() 返回同一实例。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2

    def test_get_log_after_record(self):
        """record() 成功调用后 get_log() 应包含对应事件。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t = get_tracker()
        t.record("test_source", "T2", success=True)
        log = t.get_log()
        assert len(log) == 1
        assert log[0]["source_key"] == "test_source"
        assert log[0]["success"] is True
        assert log[0]["degraded"] is False

    def test_get_log_failure_event(self):
        """record(success=False) 后 get_log() 应包含失败事件。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t = get_tracker()
        t.record("src_fail", "T4", success=False, failure_type="unreachable")
        log = t.get_log()
        assert len(log) == 1
        assert log[0]["source_key"] == "src_fail"
        assert log[0]["success"] is False
        assert log[0]["failure_type"] == "unreachable"

    def test_get_log_multiple_events_in_order(self):
        """多次 record() 调用按顺序记录在日志中。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t = get_tracker()
        t.record("src_a", "T2", success=True)
        t.record("src_b", "T3", success=False, failure_type="empty")
        t.record("src_c", "T2", success=True)
        log = t.get_log()
        assert len(log) == 3
        assert log[0]["source_key"] == "src_a"
        assert log[1]["source_key"] == "src_b"
        assert log[1]["success"] is False
        assert log[2]["source_key"] == "src_c"

    def test_clear_log(self):
        """clear_log() 后 get_log() 应返回空列表。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t = get_tracker()
        t.record("src_a", "T2", success=True)
        assert len(t.get_log()) == 1
        t.clear_log()
        assert len(t.get_log()) == 0

    def test_reset_tracker_creates_new_instance(self):
        """reset_tracker() 后 get_tracker() 返回新实例，旧日志清除。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t1 = get_tracker()
        t1.record("src_a", "T2", success=True)
        assert len(t1.get_log()) == 1
        reset_tracker()
        t2 = get_tracker()
        assert t1 is not t2
        assert len(t2.get_log()) == 0

    def test_get_log_contains_timestamp(self):
        """get_log() 条目应含有效的时间戳。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t = get_tracker()
        t.record("src_ts", "T2", success=True)
        log = t.get_log()
        assert isinstance(log[0]["timestamp"], float)
        assert log[0]["timestamp"] > 0

    def test_get_log_failure_contains_degraded(self):
        """失败事件的 degraded 字段反映是否触发降级。"""
        from src.python.report.data_status import get_tracker, reset_tracker
        reset_tracker()
        t = get_tracker()
        # T4 单次失败即降级
        t.record("src_degrade", "T4", success=False, failure_type="unreachable")
        log = t.get_log()
        assert log[0]["degraded"] is True
        assert log[0]["count"] >= 1
