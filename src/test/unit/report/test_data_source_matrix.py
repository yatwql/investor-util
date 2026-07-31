"""build_data_source_matrix 单元测试。

测试目标：
  - degraded 事件 → degraded_list 正确填充
  - failed 事件 → sample_failures 正确填充
  - 混合 degraded + failed → 状态为 "degraded"，两种列表均填充
  - 无 degraded → degraded_list 为空
  - 无事件 → 返回空列表
  - 全失败 → status="failed"

运行：
  python -m pytest src/test/unit/report/test_data_source_matrix.py -v
"""

from __future__ import annotations

from typing import Any

import pytest

from src.python.report.data_status import (
    get_tracker,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestBuildDataSourceMatrixDegradedList:
    """build_data_source_matrix — degraded_list 字段（新增）。"""

    # ── 辅助 ─────────────────────────────────

    def _add_event(
        self,
        source_key: str,
        tier: str = "T2",
        success: bool = False,
        degraded: bool = False,
        failure_type: str = "unreachable",
    ) -> None:
        """向 DegradationTracker 注入一条 record 事件。"""
        t = get_tracker()
        t._events.append(t._make_event(
            source_key=source_key,
            tier=tier,
            success=success,
            failure_type=failure_type,
            degraded=degraded,
            count=1,
            effective_threshold=1,
            timestamp=1000.0,
        ))
        # 同步更新计数器（避免 _record_unsafe 影响，直接操作 _events）
        # 注：_make_event 是私有的——我们直接构造 DegradationEvent 对象

    def _add_raw_event(self, **kwargs) -> None:
        """向 DegradationTracker 注入一条 DegradationEvent。"""
        from src.python.report.data_status import DegradationEvent
        t = get_tracker()
        ev = DegradationEvent(**kwargs)
        t._events.append(ev)

    def _build(self) -> list[dict[str, Any]]:
        from src.python.report.data_source_matrix import build_data_source_matrix
        return build_data_source_matrix()

    # ── 测试用例 ─────────────────────────────

    def test_degraded_only_one_category(self):
        """单类别单条 degraded → degraded_list 含 1 项，sample_failures 空。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=True,
            count=3,
            effective_threshold=2,
            timestamp=1000.0,
        )
        matrix = self._build()
        assert len(matrix) >= 1
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["degraded"] == 1
        assert len(price_row["degraded_list"]) == 1
        assert "price_600900" in price_row["degraded_list"][0]
        assert price_row["failed"] == 0
        assert len(price_row["sample_failures"]) == 0
        assert price_row["status"] == "degraded"

    def test_failed_only(self):
        """单类别单条 failed（非 degraded）→ sample_failures 含 1 项，degraded_list 空。"""
        self._add_raw_event(
            source_key="price_000001",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=False,
            count=1,
            effective_threshold=2,
            timestamp=1000.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["failed"] == 1
        assert len(price_row["sample_failures"]) == 1
        assert price_row["degraded"] == 0
        assert len(price_row["degraded_list"]) == 0

    def test_mixed_degraded_and_failed(self):
        """同一类别有 1 ok + 1 degraded + 1 failed → 两种列表均填充，status='degraded'。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2",
            success=True,
            failure_type="unreachable",
            degraded=False,
            count=0,
            effective_threshold=0,
            timestamp=999.0,
        )
        self._add_raw_event(
            source_key="price_600519",
            tier="T2",
            success=False,
            failure_type="unreachable",
            degraded=True,
            count=3,
            effective_threshold=2,
            timestamp=1000.0,
        )
        self._add_raw_event(
            source_key="price_000001",
            tier="T2",
            success=False,
            failure_type="empty",
            degraded=False,
            count=1,
            effective_threshold=2,
            timestamp=1001.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["ok"] == 1
        assert price_row["degraded"] == 1
        assert price_row["failed"] == 1
        assert len(price_row["degraded_list"]) == 1
        assert len(price_row["sample_failures"]) == 1
        assert price_row["status"] == "degraded"

    def test_all_ok_no_degraded_list(self):
        """全部成功 → degraded_list 和 sample_failures 均为空。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2",
            success=True,
            failure_type="unreachable",
            degraded=False,
            count=0,
            effective_threshold=0,
            timestamp=1000.0,
        )
        self._add_raw_event(
            source_key="price_000001",
            tier="T2",
            success=True,
            failure_type="unreachable",
            degraded=False,
            count=0,
            effective_threshold=0,
            timestamp=1001.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["status"] == "ok"
        assert len(price_row["degraded_list"]) == 0
        assert len(price_row["sample_failures"]) == 0

    def test_multiple_degraded_same_category(self):
        """同一类别多条 degraded → degraded_list 含多项。"""
        self._add_raw_event(
            source_key="price_600900",
            tier="T2", success=False, failure_type="unreachable",
            degraded=True, count=3, effective_threshold=2, timestamp=1000.0,
        )
        self._add_raw_event(
            source_key="price_600519",
            tier="T2", success=False, failure_type="timeout",
            degraded=True, count=4, effective_threshold=2, timestamp=1001.0,
        )
        self._add_raw_event(
            source_key="price_000001",
            tier="T2", success=False, failure_type="unreachable",
            degraded=True, count=3, effective_threshold=2, timestamp=1002.0,
        )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["degraded"] == 3
        assert len(price_row["degraded_list"]) == 3
        # 每项都应包含 source_key 前缀
        for dg in price_row["degraded_list"]:
            assert "price_" in dg

    def test_all_failed_degraded_list_empty(self):
        """全部失败（非 degraded）→ status='failed', degraded_list 空。"""
        for code in ("price_a", "price_b", "price_c"):
            self._add_raw_event(
                source_key=code,
                tier="T4", success=False, failure_type="unreachable",
                degraded=False, count=1, effective_threshold=1, timestamp=1000.0,
            )
        matrix = self._build()
        price_row = next(r for r in matrix if r["key"] == "price")
        assert price_row["status"] == "failed"
        assert price_row["failed"] == 3
        assert price_row["degraded"] == 0
        assert len(price_row["degraded_list"]) == 0
        assert len(price_row["sample_failures"]) == 3

    def test_no_events_returns_empty(self):
        """无任何事件 → 空列表。"""
        from src.python.report.data_status import reset_tracker
        reset_tracker()
        matrix = self._build()
        assert matrix == []

    def test_degraded_list_includes_failure_type(self):
        """degraded_list 每项格式包含 failure_type 描述。"""
        self._add_raw_event(
            source_key="fund_rank_001",
            tier="T2", success=False, failure_type="empty",
            degraded=True, count=3, effective_threshold=2, timestamp=1000.0,
        )
        matrix = self._build()
        rank_row = next(r for r in matrix if r["key"] == "fund_rank")
        assert len(rank_row["degraded_list"]) == 1
        assert "empty" in rank_row["degraded_list"][0]
        assert "fund_rank_001" in rank_row["degraded_list"][0]
