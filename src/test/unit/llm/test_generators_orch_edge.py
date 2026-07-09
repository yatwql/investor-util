"""边缘测试：LLM 批量编排模块 — generators_orchestrator.py

R-198 新增边缘测试文件（I-01 骨架阶段）。
TODO: I-09 填充实际边缘测试用例。
"""

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
    pytest.mark.edge,
]


@pytest.mark.skip(reason="I-01 骨架占位 — I-09 填充")
class TestGeneratorsOrchEdgePlaceholder:
    """占位：generators_orchestrator.py 边缘测试容器（I-09 添加）。"""

    def test_placeholder(self) -> None:
        pass
