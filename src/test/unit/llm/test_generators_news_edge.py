"""边缘测试：LLM 新闻关联分析模块 — generators_news.py

R-198 新增边缘测试文件（I-01 骨架阶段）。
TODO: I-06 填充实际边缘测试用例。
"""

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
    pytest.mark.edge,
]


@pytest.mark.skip(reason="I-01 骨架占位 — I-06 填充")
class TestGeneratorsNewsEdgePlaceholder:
    """占位：generators_news.py 边缘测试容器（I-06 添加）。"""

    def test_placeholder(self) -> None:
        pass
