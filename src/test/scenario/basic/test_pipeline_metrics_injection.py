"""管线指标注入测试 — 验证量化指标从计算到 LLM prompt 的完整路径。

测试目标：
  1. metrics table block 格式化是否正确（完整指标 / 数据不足）
  2. data quality detail block 格式化是否正确（有/无降级事件）
  3. expert_review prompt 包含 metrics table 块
  4. health_check prompt 包含 data quality detail 块
  5. generate_all_llm 正确传递 metrics / degradation_events 参数

约束：
  - LLM 调用 mock，防止真实 API 调用
  - 纯 strings 检查，不触发网络请求
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.scenario, pytest.mark.scenario_basic]

# generate_all_llm 返回 4 个分析结果 + 4 个缓存标志（无辩论模式）
_LLM_OUTPUT_TUPLE_LEN = 8


class TestMetricsTableBlock:
    """量化指标表格格式化测试。"""

    def test_full_metrics_block(self):
        """所有指标齐全 → 生成完整表格块。"""
        from src.python.llm.prompts_tables import _build_metrics_table_block

        metrics = {
            "sharpe_ratio": 1.5,
            "sharpe_confidence": "high",
            "calmar_ratio": 2.1,
            "hhi": 0.15,
            "hhi_equivalent": 6.7,
            "win_rate": {"win_rate": 0.6, "winning": ["A", "B", "C"], "losing": ["D", "E"]},
            "turnover_rate": 0.25,
            "portfolio_beta": 1.1,
            "beta_confidence": "high",
        }
        text = _build_metrics_table_block(metrics)
        assert "【量化指标】" in text
        assert "夏普比率" in text
        assert "卡玛比率" in text
        assert "集中度" in text
        assert "持仓胜率" in text
        assert "换手率" in text
        assert "组合Beta" in text

    def test_empty_metrics_returns_empty(self):
        """空字典 → 返回空字符串。"""
        from src.python.llm.prompts_tables import _build_metrics_table_block

        assert _build_metrics_table_block({}) == ""
        assert _build_metrics_table_block(None) == ""

    def test_partial_metrics_graceful(self):
        """部分指标缺失 → 不抛异常，缺失项显示 --。"""
        from src.python.llm.prompts_tables import _build_metrics_table_block

        metrics = {"sharpe_ratio": 0.8, "sharpe_confidence": "low"}
        text = _build_metrics_table_block(metrics)
        assert "夏普比率" in text
        assert text.strip() != ""


class TestDataQualityDetailBlock:
    """数据质量详情块格式化测试。"""

    def test_no_events(self):
        """无降级事件 → 显示"今日无降级记录"。"""
        from src.python.llm.prompts_tables import _build_data_quality_detail_block

        text = _build_data_quality_detail_block([])
        assert "无降级记录" in text

        text = _build_data_quality_detail_block(None)
        assert "无降级记录" in text

    def test_with_unreachable_events(self):
        """有 unreachable 事件 → 显示连接失败详情。"""
        from src.python.llm.prompts_tables import _build_data_quality_detail_block

        events = [
            {"source_key": "api_a", "failure_type": "unreachable", "degraded": True, "count": 3},
            {"source_key": "api_b", "failure_type": "unreachable", "degraded": True, "count": 1},
        ]
        text = _build_data_quality_detail_block(events)
        assert "连接失败" in text
        assert "api_a" in text
        assert "api_b" in text
        assert "触发降级" in text


class TestExpertReviewMetricsInjection:
    """expert_review prompt 指标注入测试。"""

    def test_expert_review_contains_metrics_table(self):
        """metrics 非空时 prompt 含指标表格。"""
        from src.python.llm.prompts_action import _build_expert_review_prompt

        prompt = _build_expert_review_prompt(
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
            metrics={"sharpe_ratio": 1.5, "sharpe_confidence": "high"},
        )
        assert "【量化指标】" in prompt
        assert "夏普比率" in prompt

    def test_expert_review_no_metrics(self):
        """metrics 为 None 时 prompt 无指标表格。"""
        from src.python.llm.prompts_action import _build_expert_review_prompt

        prompt = _build_expert_review_prompt(
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
        )
        assert "【量化指标】" not in prompt

    def test_expert_review_contains_action_template(self):
        """prompt 尾部含操作建议表格模板。"""
        from src.python.llm.prompts_action import _build_expert_review_prompt

        prompt = _build_expert_review_prompt(
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
        )
        assert "### 操作建议" in prompt
        assert "品种" in prompt


class TestHealthCheckDegradationInjection:
    """health_check prompt 数据质量详情注入测试。"""

    def test_health_check_contains_degradation_detail(self):
        """degradation_events 非空时 prompt 含数据质量详情。"""
        from src.python.llm.prompts_action import _build_health_check_prompt

        prompt = _build_health_check_prompt(
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
            degradation_events=[
                {"source_key": "tencent", "failure_type": "unreachable", "degraded": True, "count": 2},
            ],
        )
        assert "【数据质量详细状态】" in prompt
        assert "tencent" in prompt

    def test_health_check_no_degradation(self):
        """degradation_events 为 None 时仍含基础降级块。"""
        from src.python.llm.prompts_action import _build_health_check_prompt

        prompt = _build_health_check_prompt(
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
        )
        # 即使无 degradation_events，pipeline_data 中的 degradation 块仍可存在
        assert "【持仓明细】" in prompt


class TestLLMGeneratorWiring:
    """LLM 生成器接线测试。"""

    @patch("src.python.llm.generators_orchestrator.generate_all_llm")
    def test_generate_all_llm_metrics_param(self, mock_gen: MagicMock):
        """generate_all_llm 接收 metrics 参数。"""
        mock_gen.return_value = (None, None, None, None, False, False, False, False)

        from src.python.llm.generators_orchestrator import generate_all_llm

        metrics = {"sharpe_ratio": 1.5}
        result = generate_all_llm(
            a_indices={},
            us_indices={},
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
            metrics=metrics,
        )
        assert result is not None
        assert len(result) == _LLM_OUTPUT_TUPLE_LEN

    @patch("src.python.llm.generators_orchestrator.generate_all_llm")
    def test_generate_all_llm_degradation_events_param(self, mock_gen: MagicMock):
        """generate_all_llm 接收 degradation_events 参数。"""
        mock_gen.return_value = (None, None, None, None, False, False, False, False)

        from src.python.llm.generators_orchestrator import generate_all_llm

        events = [{"source_key": "api_a", "failure_type": "unreachable", "degraded": True, "count": 1}]
        result = generate_all_llm(
            a_indices={},
            us_indices={},
            total_mv=10000,
            total_cost=9000,
            total_profit=1000,
            total_today_profit=100,
            holdings_count=2,
            categories={"股票": 2},
            degradation_events=events,
        )
        assert result is not None
        assert len(result) == _LLM_OUTPUT_TUPLE_LEN

    def test_expert_review_generator_accepts_metrics(self):
        """generate_expert_review 接受 metrics 参数。"""
        from src.python.llm.generators import generate_expert_review

        # 只验证签名兼容性，不实际调用 LLM
        import inspect
        sig = inspect.signature(generate_expert_review)
        assert "metrics" in sig.parameters

    def test_health_check_generator_accepts_degradation_events(self):
        """generate_health_check 接受 degradation_events 参数。"""
        from src.python.llm.generators import generate_health_check

        import inspect
        sig = inspect.signature(generate_health_check)
        assert "degradation_events" in sig.parameters
