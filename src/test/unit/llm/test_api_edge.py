"""LLM API edge 场景专项测试。

从 test_api.py 提取的 edge 场景：
  - content_filter 安抚重试后 usage 传播正确性
  - content_filter 安抚重试仍空 + 无回退

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/llm/test_api_edge.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm, pytest.mark.edge]


class TestCallLlmEdge(unittest.TestCase):
    """call_llm edge 场景：content_filter 安抚重试边界。"""

    @patch("src.python.llm.api.call_single_provider")
    def test_recovery_retry_usage_propagated(self, mock_single: MagicMock) -> None:
        """安抚重试成功后，返回的是重试调用的 usage（非原始空调用的）。"""
        from src.python.llm.api import call_llm

        mock_single.side_effect = [
            ("", {"input_tokens": 10, "output_tokens": 0}),
            ("安抚成功", {"input_tokens": 15, "output_tokens": 200}),
        ]
        result, usage = call_llm("system", "user", {"provider": "claude", "api_key": "sk-x"})
        self.assertEqual(result, "安抚成功")
        self.assertEqual(usage["input_tokens"], 15, "usage 应来自安抚重试，非原始调用")
        self.assertEqual(usage["output_tokens"], 200)

    @patch("src.python.llm.api.call_single_provider")
    def test_recovery_retry_still_empty_no_fallback(self, mock_single: MagicMock) -> None:
        """安抚重试仍空 + 无回退 → (None, None)。"""
        from src.python.llm.api import call_llm

        mock_single.side_effect = [
            ("", {"input_tokens": 10}),
            ("   ", {"input_tokens": 20}),  # 仅空白字符，strip() 后为空
        ]
        result, usage = call_llm("system", "user", {"provider": "claude", "api_key": "sk-x"})
        self.assertIsNone(result)
        self.assertIsNone(usage)
        self.assertEqual(mock_single.call_count, 2)


if __name__ == "__main__":
    unittest.main()
