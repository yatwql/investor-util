"""prompts_core 格式化函数与系统提示常量单元测试。"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm]


class TestPromptsCore:
    """prompts_core 基础函数与常量测试。"""

    def test_system_global_macro_constant(self):
        """_SYSTEM_GLOBAL_MACRO 是非常字符串。"""
        from src.python.llm.prompts_core import _SYSTEM_GLOBAL_MACRO

        assert isinstance(_SYSTEM_GLOBAL_MACRO, str)
        assert len(_SYSTEM_GLOBAL_MACRO) > 50

    def test_system_expert_review_constant(self):
        """_SYSTEM_EXPERT_REVIEW 包含关键指令短语。"""
        from src.python.llm.prompts_core import _SYSTEM_EXPERT_REVIEW

        assert isinstance(_SYSTEM_EXPERT_REVIEW, str)
        assert "Phase" in _SYSTEM_EXPERT_REVIEW or "定音锤" in _SYSTEM_EXPERT_REVIEW
        assert "置信度指引" in _SYSTEM_EXPERT_REVIEW
        assert "竞争语境约束" in _SYSTEM_EXPERT_REVIEW

    def test_system_health_check_constant(self):
        """_SYSTEM_HEALTH_CHECK 是非常字符串。"""
        from src.python.llm.prompts_core import _SYSTEM_HEALTH_CHECK

        assert isinstance(_SYSTEM_HEALTH_CHECK, str)
        assert len(_SYSTEM_HEALTH_CHECK) > 50

    def test_fmt_wan_yi(self):
        """≥1亿 → 亿单位。"""
        from src.python.llm.prompts_core import _fmt_wan

        assert _fmt_wan(123_000_000) == "1.23亿"
        assert _fmt_wan(100_000_000) == "1.00亿"

    def test_fmt_wan_wan(self):
        """≥1万 → 万单位。"""
        from src.python.llm.prompts_core import _fmt_wan

        assert _fmt_wan(12_345) == "1.2万"
        assert _fmt_wan(99_999) == "10.0万"

    def test_fmt_wan_yuan(self):
        """<1万 → 元。"""
        from src.python.llm.prompts_core import _fmt_wan

        assert _fmt_wan(9999) == "9,999"
        assert _fmt_wan(0) == "0"
        assert _fmt_wan(-500) == "-500"

    def test_fmt_holding_line_basic(self):
        """_fmt_holding_line 基础格式。"""
        from src.python.llm.prompts_core import _fmt_holding_line

        h = {"code": "600519", "name": "贵州茅台", "market_value": 200_000, "profit": 5000, "profit_rate": 2.5}
        result = _fmt_holding_line(h)
        assert isinstance(result, str)
        assert "600519" in result
        assert "20.0万" in result

    def test_llm_module_failure_dict(self):
        """LLM_MODULE_FAILURE 是 dict。"""
        from src.python.llm.prompts_core import LLM_MODULE_FAILURE

        assert isinstance(LLM_MODULE_FAILURE, dict)
