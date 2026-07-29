"""Utility / helper 模块单元测试（markdown_to_html、compute_fingerprint、get_cache_ttl_llm、
_supports_extended_thinking、_is_effort_model、_log_token_usage、_extract_content、
截断检测、Prompt 常量、Pricing 估算）。"""

from __future__ import annotations

import unittest

import pytest

from src.python.llm.api_base import (
    _check_claude_truncation,
    _check_openai_truncation,
    _extract_content,
    _is_effort_model,
    _log_token_usage,
    _supports_extended_thinking,
)
from src.python.llm.fingerprint import compute_fingerprint, get_cache_ttl_llm
from src.python.llm.markdown import markdown_to_html
from src.python.llm.pricing import CURRENCY_SYMBOLS, PRICING_MERGED, estimate_cost, reload_pricing
from src.python.llm.prompts import _SYSTEM_EXPERT_REVIEW, _SYSTEM_GLOBAL_MACRO

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


# ═══════════════════════════════════════════════════════════
#  markdown_to_html
# ═══════════════════════════════════════════════════════════


class TestMarkdownToHtml(unittest.TestCase):
    """测试 Markdown → HTML 渲染的各类输入。"""

    def test_empty(self) -> None:
        self.assertEqual(markdown_to_html(""), "")
        self.assertEqual(markdown_to_html(None), "")

    def test_bare_text(self) -> None:
        r = markdown_to_html("Hello 你好")
        self.assertEqual(r, "<p>Hello 你好</p>")

    def test_bold(self) -> None:
        r = markdown_to_html("这是 **粗体** 文字")
        self.assertIn("<strong>粗体</strong>", r)
        self.assertIn("<p>", r)

    def test_italic(self) -> None:
        r = markdown_to_html("这是 *斜体* 文字")
        self.assertIn("<em>斜体</em>", r)

    def test_heading_h2(self) -> None:
        r = markdown_to_html("## 标题二\n\n正文内容")
        self.assertIn("<h2>标题二</h2>", r)
        self.assertIn("<p>正文内容</p>", r)

    def test_heading_h3(self) -> None:
        r = markdown_to_html("### 标题三\n\n正文")
        self.assertIn("<h3>", r)

    def test_unordered_list(self) -> None:
        r = markdown_to_html("- 项目一\n- 项目二\n\n后续段落")
        self.assertIn("<ul>", r)
        self.assertIn("<li>项目一</li>", r)
        self.assertIn("<li>项目二</li>", r)
        self.assertIn("<p>后续段落</p>", r)

    def test_ordered_list(self) -> None:
        r = markdown_to_html("1. 第一步\n2. 第二步\n\n结束")
        self.assertIn("<ol>", r)
        self.assertIn("<li>第一步</li>", r)
        self.assertIn("<li>第二步</li>", r)

    def test_inline_code(self) -> None:
        r = markdown_to_html("使用 `code` 行内代码")
        self.assertIn("<code>code</code>", r)

    def test_horizontal_rule(self) -> None:
        r = markdown_to_html("上面\n---\n下面")
        self.assertIn("<hr>", r)

    def test_mixed_complex(self) -> None:
        """模拟智囊团输出的真实混合场景。"""
        text = """## 定音锤

**核心建议**：减仓科技

- 减持 300750 至 5%
- 增持 600519 至 15%

> 风险提示：注意政策转向"""
        r = markdown_to_html(text)
        self.assertIn("<h2>定音锤</h2>", r)
        self.assertIn("<strong>核心建议</strong>", r)
        self.assertIn("<ul>", r)
        self.assertIn("<li>减持 300750 至 5%</li>", r)

    def test_multi_paragraph(self) -> None:
        text = "第一段\n\n第二段\n\n第三段"
        r = markdown_to_html(text)
        self.assertEqual(r.count("<p>"), 3)
        self.assertIn("第一段", r)


# ═══════════════════════════════════════════════════════════
#  compute_fingerprint
# ═══════════════════════════════════════════════════════════


class TestComputeFingerprint(unittest.TestCase):
    """测试指纹计算的确定性和区分性。"""

    def test_deterministic(self) -> None:
        """相同输入 → 相同指纹。"""
        fp1 = compute_fingerprint([{"a": 1}], 100.0)
        fp2 = compute_fingerprint([{"a": 1}], 100.0)
        self.assertEqual(fp1, fp2)

    def test_different_input_differs(self) -> None:
        """不同输入 → 不同指纹。"""
        fp1 = compute_fingerprint([{"a": 1}], 100.0)
        fp2 = compute_fingerprint([{"a": 2}], 100.0)
        self.assertNotEqual(fp1, fp2)

    def test_length(self) -> None:
        """指纹是 12 位十六进制字符串。"""
        fp = compute_fingerprint("test")
        self.assertEqual(len(fp), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))


# ═══════════════════════════════════════════════════════════
#  get_cache_ttl_llm
# ═══════════════════════════════════════════════════════════


class TestGetCacheTtlLlm(unittest.TestCase):
    """测试 LLM TTL 取值。"""

    def test_global_macro_default(self) -> None:
        ttl = get_cache_ttl_llm("global_macro")
        self.assertGreater(ttl, 0)
        self.assertEqual(ttl, 86400)

    def test_expert_review_default(self) -> None:
        ttl = get_cache_ttl_llm("expert_review")
        self.assertEqual(ttl, 7200)

    def test_news_correlation_default(self) -> None:
        ttl = get_cache_ttl_llm("news_correlation")
        self.assertGreater(ttl, 0)
        self.assertEqual(ttl, 3600)


# ═══════════════════════════════════════════════════════════
#  _supports_extended_thinking
# ═══════════════════════════════════════════════════════════


class TestSupportsExtendedThinking(unittest.TestCase):
    """测试 Extended Thinking 模型兼容性检查。"""

    def test_sonnet4_supported(self) -> None:
        self.assertTrue(_supports_extended_thinking("claude-sonnet-4-20250514"))

    def test_opus4_supported(self) -> None:
        self.assertTrue(_supports_extended_thinking("claude-opus-4-20250514"))

    def test_sonnet4_variant_supported(self) -> None:
        """claude-sonnet-4 系列任意变体都应支持。"""
        self.assertTrue(_supports_extended_thinking("claude-sonnet-4-20251022"))

    def test_opus4_variant_supported(self) -> None:
        self.assertTrue(_supports_extended_thinking("claude-opus-4-20251022"))

    def test_sonnet35_not_supported(self) -> None:
        self.assertFalse(_supports_extended_thinking("claude-sonnet-3-5-20241022"))

    def test_haiku35_not_supported(self) -> None:
        self.assertFalse(_supports_extended_thinking("claude-haiku-3-5-20241022"))

    def test_claude3_not_supported(self) -> None:
        self.assertFalse(_supports_extended_thinking("claude-3-opus-20240229"))
        self.assertFalse(_supports_extended_thinking("claude-3-sonnet-20240229"))
        self.assertFalse(_supports_extended_thinking("claude-3-haiku-20240307"))

    def test_empty_string_not_supported(self) -> None:
        self.assertFalse(_supports_extended_thinking(""))

    def test_deepseek_v4_flash_supported(self) -> None:
        self.assertTrue(_supports_extended_thinking("DeepSeek-V4-Flash"))

    def test_deepseek_v4_pro_supported(self) -> None:
        self.assertTrue(_supports_extended_thinking("deepseek-v4-pro"))

    def test_deepseek_chat_supported(self) -> None:
        self.assertTrue(_supports_extended_thinking("deepseek-chat"))

    def test_deepseek_v3_not_supported(self) -> None:
        self.assertFalse(_supports_extended_thinking("deepseek-v3"))


# ═══════════════════════════════════════════════════════════
#  _is_effort_model
# ═══════════════════════════════════════════════════════════


class TestIsEffortModel(unittest.TestCase):
    """测试模型类型识别：budget（Claude）vs effort（DeepSeek）。"""

    def test_claude_sonnet4_is_not_effort(self) -> None:
        self.assertFalse(_is_effort_model("claude-sonnet-4-20250514"))

    def test_claude_opus4_is_not_effort(self) -> None:
        self.assertFalse(_is_effort_model("claude-opus-4-20250514"))

    def test_deepseek_v4_flash_is_effort(self) -> None:
        self.assertTrue(_is_effort_model("DeepSeek-V4-Flash"))

    def test_deepseek_v4_pro_is_effort(self) -> None:
        self.assertTrue(_is_effort_model("deepseek-v4-pro"))

    def test_deepseek_chat_is_effort(self) -> None:
        self.assertTrue(_is_effort_model("deepseek-chat"))

    def test_empty_is_not_effort(self) -> None:
        self.assertFalse(_is_effort_model(""))


# ═══════════════════════════════════════════════════════════
#  Prompt 常量完整性
# ═══════════════════════════════════════════════════════════


class TestPromptConstants(unittest.TestCase):
    """测试 _SYSTEM_* 常量完整性。"""

    def test_macro_not_empty(self) -> None:
        self.assertTrue(len(_SYSTEM_GLOBAL_MACRO) > 50)
        self.assertIn("宏观", _SYSTEM_GLOBAL_MACRO)

    def test_expert_compact(self) -> None:
        """智囊团 Prompt 已精简。"""
        self.assertLess(len(_SYSTEM_EXPERT_REVIEW), 1000,
                        f"EXPERT prompt too long: {len(_SYSTEM_EXPERT_REVIEW)} chars")
        self.assertIn("Phase", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("约束", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("Markdown", _SYSTEM_EXPERT_REVIEW)


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
        """content 为空列表 → 返回空字符串（视为空内容而非格式异常）。"""
        data = {"content": []}
        self.assertEqual(_extract_content(data), "")

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
        """content 列表但元素无 text 字段 → 返回空字符串（视为空内容而非格式异常）。"""
        data = {"content": [{"type": "image"}, {"type": "tool_use"}]}
        self.assertEqual(_extract_content(data), "")

# ═══════════════════════════════════════════════════════════
#  截断检测
# ═══════════════════════════════════════════════════════════


class TestCheckTruncation(unittest.TestCase):
    """测试 _check_claude_truncation / _check_openai_truncation 的 config_field 参数。"""

    def test_check_claude_truncation_default_field(self) -> None:
        """默认 config_field='max_tokens' → 日志含 max_tokens。"""

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 1000, "Claude")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens", log_text)

    def test_check_claude_truncation_custom_field(self) -> None:
        """config_field='max_tokens_expert_review' → 日志提示 max_tokens_expert_review。"""

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 8192, "Claude", config_field="max_tokens_expert_review")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens_expert_review", log_text)
        self.assertIn("8192", log_text)

    def test_check_claude_truncation_not_truncated(self) -> None:
        """stop_reason 不是 max_tokens → 不记录日志。"""

        data = {"stop_reason": "end_turn", "usage": {"output_tokens": 100}}
        result = _check_claude_truncation(data, 8192, "Claude")
        self.assertFalse(result)

    def test_check_openai_truncation_custom_field(self) -> None:
        """OpenAI config_field='max_tokens_global_macro' → 日志提示 max_tokens_global_macro。"""

        data = {"choices": [{"finish_reason": "length", "message": {"content": "..."}}],
                "usage": {"completion_tokens": 800}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_openai_truncation(data, 800, "OpenAI", config_field="max_tokens_global_macro")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens_global_macro", log_text)
        self.assertIn("800", log_text)

    def test_check_openai_truncation_not_truncated(self) -> None:
        """finish_reason 不是 length → 不记录日志。"""

        data = {"choices": [{"finish_reason": "stop", "message": {"content": "..."}}],
                "usage": {"completion_tokens": 100}}
        result = _check_openai_truncation(data, 8192, "OpenAI")
        self.assertFalse(result)


# ═══════════════════════════════════════════════════════════
#  Pricing — estimate_cost / reload_pricing / PRICING_MERGED
# ═══════════════════════════════════════════════════════════


class TestPricing(unittest.TestCase):
    """测试 LLM 费用估算和定价管理。"""

    def testestimate_cost_known_model(self) -> None:
        """已知模型应返回正确的费用估算。"""
        cost = estimate_cost("deepseek-v4-flash", 3000, 2000)
        # (3000/1M)*1 + (2000/1M)*2 = 0.003 + 0.004 = 0.007
        self.assertIn("0.007", cost)

    def testestimate_cost_cache_hit(self) -> None:
        """缓存命中应降低费用。"""
        cost = estimate_cost("deepseek-v4-flash", 3000, 2000, cache_hit_input_tokens=2000)
        cost_no = estimate_cost("deepseek-v4-flash", 3000, 2000, cache_hit_input_tokens=0)
        self.assertNotEqual(cost, cost_no)

    def testestimate_cost_unknown_model(self) -> None:
        """未知模型应返回 -。"""
        self.assertEqual(estimate_cost("nonexistent-model", 100, 100), "-")

    def testestimate_cost_zero_tokens(self) -> None:
        """零 token 应返回 -。"""
        self.assertEqual(estimate_cost("deepseek-v4-flash", 0, 0), "-")

    def testestimate_cost_model_prefix_match(self) -> None:
        """模型名前缀匹配应选择正确的定价。"""
        cost = estimate_cost("claude-sonnet-4-6-20250514", 1000, 500)
        self.assertNotEqual(cost, "-")

    def test_pricing_merged_has_defaults(self) -> None:
        """PRICING_MERGED 应包含所有内置模型。"""
        for model in ("deepseek-v4-flash", "claude-sonnet-4-6", "gpt-4o"):
            self.assertIn(model, PRICING_MERGED)

    def test_currency_symbols(self) -> None:
        """货币符号映射应包含主要货币。"""
        self.assertIn("CNY", CURRENCY_SYMBOLS)
        self.assertIn("USD", CURRENCY_SYMBOLS)
        self.assertEqual(CURRENCY_SYMBOLS["CNY"], "¥")
        self.assertEqual(CURRENCY_SYMBOLS["USD"], "$")

    def testreload_pricing_merge(self) -> None:
        """reload_pricing 应合并不覆盖已有值。"""
        orig = dict(PRICING_MERGED)
        reload_pricing()
        self.assertEqual(PRICING_MERGED.get("deepseek-v4-flash"),
                         orig.get("deepseek-v4-flash"))
