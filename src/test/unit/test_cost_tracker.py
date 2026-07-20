"""LLM Token 成本追踪模块单元测试。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/test_cost_tracker.py -v
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


class TestBudgetManagement:
    """预算管理功能测试。"""

    def test_default_budget(self):
        """默认预算为 8000。"""
        from src.python.llm.cost_tracker import DEFAULT_INPUT_BUDGET, get_budget_status, reset_budget

        reset_budget()
        status = get_budget_status()
        assert status["budget"] == DEFAULT_INPUT_BUDGET
        assert status["used"] >= 0
        assert status["remaining"] <= DEFAULT_INPUT_BUDGET

    def test_set_custom_budget(self):
        """设置自定义预算。"""
        from src.python.llm.cost_tracker import get_budget_status, set_input_budget

        set_input_budget(5000)
        status = get_budget_status()
        assert status["budget"] == 5000

    def test_reset_clears_warned(self):
        """reset_budget 清除告警状态。"""
        from src.python.llm.cost_tracker import get_budget_status, reset_budget

        reset_budget()
        status = get_budget_status()
        assert status["warned"] is False

    def test_minimum_budget_floor(self):
        """最低预算下限为 1000。"""
        from src.python.llm.cost_tracker import get_budget_status, set_input_budget

        set_input_budget(100)
        status = get_budget_status()
        assert status["budget"] == 1000


class TestCostSummary:
    """成本摘要格式化测试。"""

    def test_empty_summary(self):
        """无调用记录时返回空字符串。"""
        from src.python.llm.cost_tracker import get_cost_summary
        from src.python.llm.session import reset_session_usage

        reset_session_usage()
        assert get_cost_summary() == ""

    def test_summary_format(self):
        """有记录时返回非空字符串。"""
        from src.python.llm.cost_tracker import get_cost_summary
        from src.python.llm.session import record_per_module, reset_session_usage

        reset_session_usage()
        record_per_module("expert_review", "claude-sonnet-4-6", inp=1000, out=500, cost=0.005)
        summary = get_cost_summary()
        assert summary != ""
        assert "Token" in summary

    def test_verbose_summary(self):
        """详细格式含模块明细。"""
        from src.python.llm.cost_tracker import get_cost_summary
        from src.python.llm.session import record_per_module, reset_session_usage

        reset_session_usage()
        record_per_module("expert_review", "claude-sonnet-4-6", inp=2000, out=1000, cost=0.01)
        record_per_module("health_check", "claude-sonnet-4-6", inp=1500, out=800, cost=0.008)
        verbose = get_cost_summary(for_report=False)
        assert "expert_review" in verbose
        assert "health_check" in verbose
        assert "按模块明细" in verbose


class TestRecordPerModuleDuration:
    """record_per_module 的 duration 参数测试。"""

    def test_duration_recorded(self):
        """duration 参数被正确记录。"""
        from src.python.llm.session import get_session_usage, record_per_module, reset_session_usage

        reset_session_usage()
        record_per_module("expert_review", "claude-sonnet-4-6", inp=100, out=50, duration=3.5)
        usage = get_session_usage()
        pm = usage.get("per_module", {})
        assert "expert_review" in pm
        assert pm["expert_review"]["duration"] == 3.5

    def test_duration_accumulates(self):
        """同一模块多次调用 duration 累加。"""
        from src.python.llm.session import get_session_usage, record_per_module, reset_session_usage

        reset_session_usage()
        record_per_module("expert_review", "claude-sonnet-4-6", inp=100, out=50, duration=2.0)
        record_per_module("expert_review", "claude-sonnet-4-6", inp=200, out=100, duration=3.0)
        usage = get_session_usage()
        assert usage["per_module"]["expert_review"]["duration"] == 5.0
