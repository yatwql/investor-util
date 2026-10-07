"""测试：LLM Token 用量日志 — api_base._log_token_usage 计量口径。

覆盖：
  - claude 协议三件套（input/output/cache_read）回显
  - openai 协议 prompt_tokens/completion_tokens 与 details.cached_tokens 命中回显
  - 无 details 字段时不出现缓存命中行
  - None / 空 usage 提前返回
"""

import unittest

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_llm,
    pytest.mark.llm,
]


class TestLogTokenUsage(unittest.TestCase):
    """_log_token_usage — Token 用量日志（info 行内容与 silent 分支）。"""

    def test_claude_usage_logged(self) -> None:
        """Claude 格式用量 → info 日志含输入/输出/缓存命中，不抛异常。"""
        from src.python.llm.api_base import _log_token_usage

        usage = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 10}
        with self.assertLogs("invest", level="INFO") as cm:
            _log_token_usage("claude", usage, "test_label", model_name="test-model")
        joined = "".join(cm.output)
        self.assertIn("输入 100", joined)
        self.assertIn("输出 50", joined)
        self.assertIn("缓存命中 10", joined)
        self.assertIn("test_label", joined)

    def test_openai_usage_logged(self) -> None:
        """OpenAI 格式用量 → info 日志含输入/输出（无缓存命中字段）。"""
        from src.python.llm.api_base import _log_token_usage

        usage = {"prompt_tokens": 200, "completion_tokens": 100}
        with self.assertLogs("invest", level="INFO") as cm:
            _log_token_usage("openai", usage, "test_label", model_name="test-model")
        joined = "".join(cm.output)
        self.assertIn("输入 200", joined)
        self.assertIn("输出 100", joined)
        self.assertNotIn("缓存命中", joined)

    def test_openai_cache_hit_logged(self) -> None:
        """OpenAI 带 prompt_tokens_details.cached_tokens → info 日志含缓存命中（计量口径回归）。"""
        from src.python.llm.api_base import _log_token_usage

        usage = {
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 60},
        }
        with self.assertLogs("invest", level="INFO") as cm:
            _log_token_usage("openai", usage, "test_label", model_name="test-model")
        joined = "".join(cm.output)
        self.assertIn("输入 200", joined)
        self.assertIn("缓存命中 60", joined)

    def test_none_usage_ignored(self) -> None:
        """usage 为 None → 提前返回，不产生 info 日志。"""
        from src.python.llm.api_base import _log_token_usage

        with self.assertNoLogs("invest", level="INFO"):
            _log_token_usage("claude", None, "test_label")

    def test_empty_usage_ignored(self) -> None:
        """usage 为空 dict（falsy）→ 提前返回，不产生 info 日志。"""
        from src.python.llm.api_base import _log_token_usage

        with self.assertNoLogs("invest", level="INFO"):
            _log_token_usage("claude", {}, "test_label")
