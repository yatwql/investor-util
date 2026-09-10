"""降级事件失败原因上屏单元测试。

缺陷背景：降级事件只带 ``failure_type``（``unreachable`` / ``empty``）这类
机器短标识，报告的数据源可用性矩阵上屏后用户只看到「industry_x: unreachable」，
不知道到底发生了什么。本文件锁定「可读原因能一路走到矩阵条目」这一链路。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.report.data_source_matrix import _failure_entry
from src.python.report.data_status import DegradationTracker

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


@pytest.fixture
def tracker(tmp_path):
    """隔离到临时目录的降级跟踪器（不触碰真实持久化文件）。"""
    return DegradationTracker(persist_path=str(tmp_path / "degradation_state.json"))


@pytest.mark.unit
@pytest.mark.unit_report
class TestRecordMessage:
    """record() 的可选 message 入参与事件 detail。"""

    def test_message_stored_in_detail(self, tracker):
        tracker.record("industry_000001", "T3", success=False, failure_type="unreachable", message="东方财富(连接超时)")

        events = tracker.get_log()
        assert len(events) == 1
        assert events[0]["detail"] == {"message": "东方财富(连接超时)"}

    def test_no_message_keeps_detail_none(self, tracker):
        """不传 message → detail 仍为 None（既有调用方与测试不受影响）。"""
        tracker.record("industry_000001", "T3", success=False)

        assert tracker.get_log()[0]["detail"] is None

    def test_message_does_not_affect_degradation_decision(self, tracker):
        """message 仅作诊断展示，不参与降级判定。"""
        with_message = tracker.record("src_a", "T3", success=False, message="原因")
        without_message = tracker.record("src_b", "T3", success=False)

        assert with_message == without_message

    def test_success_event_has_no_detail(self, tracker):
        tracker.record("src_a", "T3", success=True, message="不该出现")

        assert tracker.get_log()[0]["detail"] is None

    def test_get_log_exposes_detail_key(self, tracker):
        tracker.record("src_a", "T3", success=False)

        assert "detail" in tracker.get_log()[0]

    def test_message_survives_repeated_failures(self, tracker):
        """连续失败每次都要带原因——用户看的是最新一次。"""
        tracker.record("src_a", "T3", success=False, message="第一次")
        tracker.record("src_a", "T3", success=False, message="第二次")

        assert tracker.get_log()[-1]["detail"] == {"message": "第二次"}


@pytest.mark.unit
@pytest.mark.unit_report
class TestFailureEntryRendering:
    """矩阵条目的渲染：有可读原因用它，没有则回落失败类型。"""

    def test_message_preferred_over_failure_type(self):
        entry = _failure_entry(
            "industry_000001", {"failure_type": "unreachable", "detail": {"message": "东方财富(连接超时)"}}
        )
        assert entry == "industry_000001: 东方财富(连接超时)"

    def test_falls_back_to_failure_type(self):
        """无 message → 输出与既往逐字一致。"""
        entry = _failure_entry("industry_000001", {"failure_type": "unreachable", "detail": None})
        assert entry == "industry_000001: unreachable"

    def test_falls_back_when_detail_lacks_message(self):
        entry = _failure_entry("fund_rank_1", {"failure_type": "empty", "detail": {"ratio": 0.5}})
        assert entry == "fund_rank_1: empty"

    def test_falls_back_when_detail_missing_key(self):
        entry = _failure_entry("price_x", {"failure_type": "empty"})
        assert entry == "price_x: empty"

    def test_unknown_when_no_failure_type_at_all(self):
        entry = _failure_entry("price_x", {})
        assert entry == "price_x: unknown"

    def test_empty_message_string_falls_back(self):
        """空串不算可读原因——否则上屏会是「src: 」这样的残缺条目。"""
        entry = _failure_entry("price_x", {"failure_type": "empty", "detail": {"message": ""}})
        assert entry == "price_x: empty"


@pytest.mark.unit
@pytest.mark.unit_report
class TestMatrixUsesReadableReason:
    """端到端：链路写入的 message 出现在矩阵的失败条目中。"""

    def _matrix_for(self, tracker):
        """返回矩阵中所有失败/降级条目的文本。

        单次失败即可能触发 T3 降级阈值，条目因此落在 degraded_list 而非
        sample_failures；两处都是用户可见面，一并收敛后断言。
        """
        from src.python.report import data_source_matrix

        with patch.object(data_source_matrix, "get_tracker", return_value=tracker):
            rows = data_source_matrix.build_data_source_matrix()
        return [e for row in rows for key in ("sample_failures", "degraded_list") for e in row.get(key, [])]

    def test_entry_carries_readable_reason(self, tracker):
        tracker.record("industry_000001", "T3", success=False, failure_type="unreachable", message="东方财富(连接超时)")

        assert "industry_000001: 东方财富(连接超时)" in self._matrix_for(tracker)

    def test_no_message_keeps_legacy_entry_text(self, tracker):
        tracker.record("industry_000001", "T3", success=False, failure_type="unreachable")

        assert "industry_000001: unreachable" in self._matrix_for(tracker)
