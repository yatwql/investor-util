"""LLM 客户端模块单元测试。

测试目标：
  - _markdown_to_html — 各类 Markdown → HTML 的正确渲染
  - _compute_fingerprint — 确定性哈希、不同输入不同指纹
  - _get_cache_ttl_llm — 模块 7/8 分 TTL
  - _build_macro_prompt — 北京时间注入 + 紧凑格式
  - _build_review_prompt — 北京时间注入 + 穿透数据拼接
  - _call_llm — provider 路由
  - generate_all_llm — force 参数透传

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_llm_client -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.llm_client import (
    _SYSTEM_MACRO,
    _SYSTEM_EXPERT,
    _build_macro_prompt,
    _build_review_prompt,
    _call_claude,
    _call_llm,
    _call_openai,
    _compute_fingerprint,
    _extract_content,
    _get_cache_ttl_llm,
    _log_token_usage,
    _markdown_to_html,
    generate_all_llm,
    generate_expert_review,
    generate_global_macro,
)


# ═══════════════════════════════════════════════════════════
#  _markdown_to_html
# ═══════════════════════════════════════════════════════════


class TestMarkdownToHtml(unittest.TestCase):
    """测试 Markdown → HTML 渲染的各类输入。"""

    def test_empty(self) -> None:
        self.assertEqual(_markdown_to_html(""), "")
        self.assertEqual(_markdown_to_html(None), "")

    def test_bare_text(self) -> None:
        r = _markdown_to_html("Hello 你好")
        self.assertEqual(r, "<p>Hello 你好</p>")

    def test_bold(self) -> None:
        r = _markdown_to_html("这是 **粗体** 文字")
        self.assertIn("<strong>粗体</strong>", r)
        self.assertIn("<p>", r)

    def test_italic(self) -> None:
        r = _markdown_to_html("这是 *斜体* 文字")
        self.assertIn("<em>斜体</em>", r)

    def test_heading_h2(self) -> None:
        r = _markdown_to_html("## 标题二\n\n正文内容")
        self.assertIn("<h2>标题二</h2>", r)
        self.assertIn("<p>正文内容</p>", r)

    def test_heading_h3(self) -> None:
        r = _markdown_to_html("### 标题三\n\n正文")
        self.assertIn("<h3>", r)

    def test_unordered_list(self) -> None:
        r = _markdown_to_html("- 项目一\n- 项目二\n\n后续段落")
        self.assertIn("<ul>", r)
        self.assertIn("<li>项目一</li>", r)
        self.assertIn("<li>项目二</li>", r)
        self.assertIn("<p>后续段落</p>", r)

    def test_ordered_list(self) -> None:
        r = _markdown_to_html("1. 第一步\n2. 第二步\n\n结束")
        self.assertIn("<ol>", r)
        self.assertIn("<li>第一步</li>", r)
        self.assertIn("<li>第二步</li>", r)

    def test_inline_code(self) -> None:
        r = _markdown_to_html("使用 `code` 行内代码")
        self.assertIn("<code>code</code>", r)

    def test_horizontal_rule(self) -> None:
        r = _markdown_to_html("上面\n---\n下面")
        self.assertIn("<hr>", r)

    def test_mixed_complex(self) -> None:
        """模拟智囊团输出的真实混合场景。"""
        text = """## 定音锤

**核心建议**：减仓科技

- 减持 300750 至 5%
- 增持 600519 至 15%

> 风险提示：注意政策转向"""
        r = _markdown_to_html(text)
        self.assertIn("<h2>定音锤</h2>", r)
        self.assertIn("<strong>核心建议</strong>", r)
        self.assertIn("<ul>", r)
        self.assertIn("<li>减持 300750 至 5%</li>", r)

    def test_multi_paragraph(self) -> None:
        text = "第一段\n\n第二段\n\n第三段"
        r = _markdown_to_html(text)
        self.assertEqual(r.count("<p>"), 3)
        self.assertIn("第一段", r)


# ═══════════════════════════════════════════════════════════
#  _compute_fingerprint
# ═══════════════════════════════════════════════════════════


class TestComputeFingerprint(unittest.TestCase):
    """测试指纹计算的确定性和区分性。"""

    def test_deterministic(self) -> None:
        """相同输入 → 相同指纹。"""
        fp1 = _compute_fingerprint([{"a": 1}], 100.0)
        fp2 = _compute_fingerprint([{"a": 1}], 100.0)
        self.assertEqual(fp1, fp2)

    def test_different_input_differs(self) -> None:
        """不同输入 → 不同指纹。"""
        fp1 = _compute_fingerprint([{"a": 1}], 100.0)
        fp2 = _compute_fingerprint([{"a": 2}], 100.0)
        self.assertNotEqual(fp1, fp2)

    def test_length(self) -> None:
        """指纹是 12 位十六进制字符串。"""
        fp = _compute_fingerprint("test")
        self.assertEqual(len(fp), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))


# ═══════════════════════════════════════════════════════════
#  _get_cache_ttl_llm
# ═══════════════════════════════════════════════════════════


class TestGetCacheTtlLlm(unittest.TestCase):
    """测试 LLM TTL 取值。"""

    def test_macro_default(self) -> None:
        ttl = _get_cache_ttl_llm("macro")
        self.assertGreater(ttl, 0)
        self.assertEqual(ttl, 14400)

    def test_expert_default(self) -> None:
        ttl = _get_cache_ttl_llm("expert")
        self.assertEqual(ttl, 7200)


# ═══════════════════════════════════════════════════════════
#  _build_macro_prompt
# ═══════════════════════════════════════════════════════════


class TestBuildMacroPrompt(unittest.TestCase):
    """测试模块 7 用户提示词。"""

    def test_has_timestamp(self) -> None:
        r = _build_macro_prompt({}, {}, 100.0, 10.0, {"股票": 3})
        self.assertIn("北京时间", r)
        self.assertIn("当前时间", r)

    def test_compact_format(self) -> None:
        a_idx = {"sh000001": {"name": "上证指数", "price": 3120, "change_pct": 1.2}}
        r = _build_macro_prompt(a_idx, {}, 100000, 5000, {"股票": 3, "基金": 2})
        self.assertIn("上证指数", r)
        self.assertIn("3120", r)
        self.assertIn("+1.20%", r)
        self.assertIn("股票3只", r)
        self.assertIn("基金2只", r)

    def test_single_line_indices(self) -> None:
        """指数应为紧凑单行格式。"""
        a_idx = {"sh000001": {"name": "上证", "price": 3000, "change_pct": -0.5}}
        r = _build_macro_prompt(a_idx, {}, 0, 0, {})
        self.assertIn("上证3000(-0.50%)", r)

    def test_no_categories(self) -> None:
        r = _build_macro_prompt({}, {}, 0, 0, {})
        self.assertIn("当前时间", r)
        # 不应该有 AssertionError


# ═══════════════════════════════════════════════════════════
#  _build_review_prompt
# ═══════════════════════════════════════════════════════════


class TestBuildReviewPrompt(unittest.TestCase):
    """测试模块 8 用户提示词。"""

    def test_has_timestamp(self) -> None:
        r = _build_review_prompt(100, 80, 20, 5, 5, {"股票": 3})
        self.assertIn("北京时间", r)
        self.assertIn("当前时间", r)

    def test_with_penetration(self) -> None:
        pen = [
            {"name": "茅台", "codes": ["600519"], "mv": 50000, "sector": "消费"},
            {"name": "宁德", "codes": ["300750"], "mv": 30000, "sector": "新能源"},
        ]
        r = _build_review_prompt(100000, 80000, 20000, 1000, 3, {"基金": 2}, pen)
        self.assertIn("茅台", r)
        self.assertIn("穿透", r)

    def test_without_penetration(self) -> None:
        r = _build_review_prompt(100, 80, 20, 5, 5, {"股票": 3})
        self.assertNotIn("穿透", r)

    def test_compact_format(self) -> None:
        r = _build_review_prompt(100000, 80000, 20000, 1000, 3, {"股票": 2, "基金": 1})
        self.assertIn("股票2只", r)
        self.assertIn("基金1只", r)


# ═══════════════════════════════════════════════════════════
#  _call_llm provider routing
# ═══════════════════════════════════════════════════════════


class TestCallLlmProvider(unittest.TestCase):
    """测试 _call_llm 的 provider 路由。"""

    def test_unsupported_provider(self) -> None:
        config = {"provider": "unknown", "api_key": "test"}
        content, usage = _call_llm("system", "user", config)
        self.assertIsNone(content)
        self.assertIsNone(usage)

    @patch("src.llm_client._call_claude")
    def test_claude_routing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("claude result", {"input_tokens": 10, "output_tokens": 50})
        config = {"provider": "claude", "api_key": "sk-xxx"}
        content, usage = _call_llm("system", "user", config)
        self.assertEqual(content, "claude result")
        self.assertEqual(usage, {"input_tokens": 10, "output_tokens": 50})
        mock_call.assert_called_once()

    @patch("src.llm_client._call_openai")
    def test_openai_routing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("openai result", {"prompt_tokens": 20, "completion_tokens": 80})
        config = {"provider": "openai", "api_key": "sk-xxx"}
        content, usage = _call_llm("system", "user", config)
        self.assertEqual(content, "openai result")
        self.assertEqual(usage, {"prompt_tokens": 20, "completion_tokens": 80})
        mock_call.assert_called_once()


# ═══════════════════════════════════════════════════════════
#  generate_all_llm force passthrough
# ═══════════════════════════════════════════════════════════


@patch("src.llm_client.generate_global_macro")
@patch("src.llm_client.generate_expert_review")
class TestGenerateAllLlm(unittest.TestCase):
    """测试并行生成函数。"""

    def test_force_passthrough(self, mock_expert: MagicMock, mock_macro: MagicMock) -> None:
        mock_macro.return_value = "<p>宏</p>"
        mock_expert.return_value = "<p>策略</p>"

        macro, expert = generate_all_llm([], [], 0, 0, 0, 0, 0, {}, force=True)

        self.assertEqual(macro, "<p>宏</p>")
        self.assertEqual(expert, "<p>策略</p>")
        # 验证 force=True 被透传
        _, kwargs_m = mock_macro.call_args
        _, kwargs_e = mock_expert.call_args
        self.assertTrue(kwargs_m.get("force"))
        self.assertTrue(kwargs_e.get("force"))

    def test_force_false_default(self, mock_expert: MagicMock, mock_macro: MagicMock) -> None:
        mock_macro.return_value = "<p>m</p>"
        mock_expert.return_value = "<p>e</p>"

        generate_all_llm([], [], 0, 0, 0, 0, 0, {})

        _, kwargs_m = mock_macro.call_args
        self.assertFalse(kwargs_m.get("force"))


# ═══════════════════════════════════════════════════════════
#  Prompt 常量完整性
# ═══════════════════════════════════════════════════════════


class TestPromptConstants(unittest.TestCase):
    """测试 _SYSTEM_* 常量完整性。"""

    def test_macro_not_empty(self) -> None:
        self.assertTrue(len(_SYSTEM_MACRO) > 50)
        self.assertIn("宏观", _SYSTEM_MACRO)

    def test_expert_compact(self) -> None:
        """智囊团 Prompt 已精简。"""
        self.assertLess(len(_SYSTEM_EXPERT), 500,
                        f"EXPERT prompt too long: {len(_SYSTEM_EXPERT)} chars")
        self.assertIn("Phase", _SYSTEM_EXPERT)
        self.assertIn("约束", _SYSTEM_EXPERT)
        self.assertIn("Markdown", _SYSTEM_EXPERT)


# ═══════════════════════════════════════════════════════════
#  _log_token_usage（不会崩溃）
# ═══════════════════════════════════════════════════════════


class TestLogTokenUsage(unittest.TestCase):
    """_log_token_usage 不会抛出异常。"""

    def test_claude_usage(self) -> None:
        # 应该正常日志，不抛异常
        _log_token_usage("claude", {"input_tokens": 100, "output_tokens": 50}, "测试")

    def test_openai_usage(self) -> None:
        _log_token_usage("openai", {"prompt_tokens": 100, "completion_tokens": 50}, "测试")

    def test_none_usage(self) -> None:
        _log_token_usage("claude", None, "测试")

    def test_empty_usage(self) -> None:
        _log_token_usage("claude", {}, "测试")


# ═══════════════════════════════════════════════════════════
#  _extract_content — 兼容多种 Anthropic Messages API 格式
# ═══════════════════════════════════════════════════════════


class TestExtractContent(unittest.TestCase):
    """测试从多种 Anthropic 兼容响应中提取文本。"""

    def test_standard_claude(self) -> None:
        """标准 Claude Messages API 格式。"""
        data = {"content": [{"type": "text", "text": "你好世界"}]}
        self.assertEqual(_extract_content(data), "你好世界")

    def test_deepseek_anthropic_compat(self) -> None:
        """DeepSeek Anthropic 兼容端点格式（与标准 Claude 一致）。"""
        data = {"content": [{"type": "text", "text": "DeepSeek 回复"}], "usage": {}}
        self.assertEqual(_extract_content(data), "DeepSeek 回复")

    def test_content_as_string(self) -> None:
        """content 直接为字符串。"""
        data = {"content": "直接字符串回复"}
        self.assertEqual(_extract_content(data), "直接字符串回复")

    def test_content_as_empty_list(self) -> None:
        """content 为空列表。"""
        data = {"content": []}
        self.assertIsNone(_extract_content(data))

    def test_content_missing(self) -> None:
        """响应中无 content 字段。"""
        data = {"error": "rate limit exceeded"}
        self.assertIsNone(_extract_content(data))

    def test_multiple_text_blocks(self) -> None:
        """多个 text block，拼接返回。"""
        data = {"content": [
            {"type": "text", "text": "第一段"},
            {"type": "tool_use", "id": "tool1"},
            {"type": "text", "text": "第二段"},
        ]}
        result = _extract_content(data)
        self.assertIn("第一段", result)
        self.assertIn("第二段", result)

    def test_empty_data(self) -> None:
        """空字典。"""
        self.assertIsNone(_extract_content({}))

    def test_none_content(self) -> None:
        """content 为 None。"""
        data = {"content": None}
        self.assertIsNone(_extract_content(data))

    def test_content_list_no_text(self) -> None:
        """content 列表但元素无 text 字段。"""
        data = {"content": [{"type": "image"}, {"type": "tool_use"}]}
        self.assertIsNone(_extract_content(data))

# ═══════════════════════════════════════════════════════════
#  截断检测
# ═══════════════════════════════════════════════════════════


class TestCheckTruncation(unittest.TestCase):
    """测试 _check_claude_truncation / _check_openai_truncation 的 config_field 参数。"""

    def test_check_claude_truncation_default_field(self) -> None:
        """默认 config_field='max_tokens' → 日志含 max_tokens。"""
        from src.llm_client import _check_claude_truncation

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 1000, "Claude")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens", log_text)

    def test_check_claude_truncation_custom_field(self) -> None:
        """config_field='max_tokens_expert' → 日志提示 max_tokens_expert。"""
        from src.llm_client import _check_claude_truncation

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 8192, "Claude", config_field="max_tokens_expert")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens_expert", log_text)
        self.assertIn("8192", log_text)

    def test_check_claude_truncation_not_truncated(self) -> None:
        """stop_reason 不是 max_tokens → 不记录日志。"""
        from src.llm_client import _check_claude_truncation

        data = {"stop_reason": "end_turn", "usage": {"output_tokens": 100}}
        result = _check_claude_truncation(data, 8192, "Claude")
        self.assertFalse(result)

    def test_check_openai_truncation_custom_field(self) -> None:
        """OpenAI config_field='max_tokens_macro' → 日志提示 max_tokens_macro。"""
        from src.llm_client import _check_openai_truncation

        data = {"choices": [{"finish_reason": "length", "message": {"content": "..."}}],
                "usage": {"completion_tokens": 800}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_openai_truncation(data, 800, "OpenAI", config_field="max_tokens_macro")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens_macro", log_text)
        self.assertIn("800", log_text)

    def test_check_openai_truncation_not_truncated(self) -> None:
        """finish_reason 不是 length → 不记录日志。"""
        from src.llm_client import _check_openai_truncation

        data = {"choices": [{"finish_reason": "stop", "message": {"content": "..."}}],
                "usage": {"completion_tokens": 100}}
        result = _check_openai_truncation(data, 8192, "OpenAI")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
