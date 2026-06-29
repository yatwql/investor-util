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

from src.python.llm_client import (
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
    _is_effort_model,
    _log_token_usage,
    _markdown_to_html,
    _supports_extended_thinking,
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
        self.assertEqual(ttl, 86400)

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

    def test_with_sector_flow(self) -> None:
        """传入行业资金流向时，prompt 应包含资金流向数据。"""
        sector_flow = [
            {"name": "半导体", "change_pct": 2.5, "main_net_inflow": 1500000000, "main_net_inflow_pct": 3.2},
            {"name": "银行", "change_pct": -0.8, "main_net_inflow": -500000000, "main_net_inflow_pct": -1.1},
        ]
        r = _build_macro_prompt({}, {}, 100000, 5000, {"股票": 3}, sector_flow=sector_flow)
        self.assertIn("行业资金流向", r)
        self.assertIn("半导体", r)
        self.assertIn("+2.50%", r)
        self.assertIn("银行", r)
        self.assertIn("-0.80%", r)
        self.assertIn("主力净流入", r)

    def test_sector_flow_none(self) -> None:
        """sector_flow=None 时不应包含资金流向内容。"""
        r = _build_macro_prompt({}, {}, 0, 0, {})
        self.assertNotIn("行业资金流向", r)


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
#  _call_llm provider routing
# ═══════════════════════════════════════════════════════════


class TestCallLlmProvider(unittest.TestCase):
    """测试 _call_llm 的 provider 路由。"""

    def test_unsupported_provider(self) -> None:
        config = {"provider": "unknown", "api_key": "test"}
        content, usage = _call_llm("system", "user", config)
        self.assertIsNone(content)
        self.assertIsNone(usage)

    @patch("src.python.llm_client._call_claude")
    def test_claude_routing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("claude result", {"input_tokens": 10, "output_tokens": 50})
        config = {"provider": "claude", "api_key": "sk-xxx"}
        content, usage = _call_llm("system", "user", config)
        self.assertEqual(content, "claude result")
        self.assertEqual(usage, {"input_tokens": 10, "output_tokens": 50})
        mock_call.assert_called_once()

    @patch("src.python.llm_client._call_openai")
    def test_openai_routing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("openai result", {"prompt_tokens": 20, "completion_tokens": 80})
        config = {"provider": "openai", "api_key": "sk-xxx"}
        content, usage = _call_llm("system", "user", config)
        self.assertEqual(content, "openai result")
        self.assertEqual(usage, {"prompt_tokens": 20, "completion_tokens": 80})
        mock_call.assert_called_once()


# ═══════════════════════════════════════════════════════════
#  _call_claude Extended Thinking 降级
# ═══════════════════════════════════════════════════════════


class TestCallClaudeThinkingDegradation(unittest.TestCase):
    """测试 _call_claude 中 Extended Thinking 的降级行为。

    通过 mock _call_llm_with_retry 捕获 payload，验证 thinking 注入逻辑。
    """

    def setUp(self) -> None:
        self.base_kw = dict(
            system="system", user="user", api_key="sk-test",
            endpoint="", max_tokens=800,
        )
        self.llm_config = {
            "thinking_enabled_global_macro": True,
            "thinking_budget_global_macro": 4000,
        }

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_thinking_injected_for_supported_model(self, mock_retry: MagicMock) -> None:
        """Sonnet-4 支持 Extended Thinking，应注入 thinking 参数。"""
        _call_claude(
            **self.base_kw, model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro", llm_config=self.llm_config,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertIn("thinking", _payload)
        self.assertEqual(_payload["thinking"]["type"], "enabled")
        # temperature 应在 thinking 开启时被移除
        self.assertNotIn("temperature", _payload)

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_thinking_skipped_for_unsupported_model(self, mock_retry: MagicMock) -> None:
        """Sonnet-3.5 不支持 Extended Thinking，应降级跳过。"""
        _call_claude(
            **self.base_kw, model="claude-sonnet-3-5-20241022",
            config_field="max_tokens_global_macro", llm_config=self.llm_config,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_thinking_skipped_when_disabled(self, mock_retry: MagicMock) -> None:
        """thinking_enabled=False 时不应注入 thinking 参数。"""
        cfg = {"thinking_enabled_global_macro": False}
        _call_claude(
            **self.base_kw, model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro", llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_thinking_skipped_when_no_llm_config(self, mock_retry: MagicMock) -> None:
        """llm_config=None 时不报错、不注入。"""
        _call_claude(
            **self.base_kw, model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro", llm_config=None,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_budget_auto_padding(self, mock_retry: MagicMock) -> None:
        """budget 小于 max_tokens + 1024 时自动补足到 max_tokens + 4096。"""
        cfg = {"thinking_enabled_global_macro": True, "thinking_budget_global_macro": 100}
        _call_claude(
            **self.base_kw, model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro", llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        # max_tokens=800 → auto_pad=800+4096=4896
        self.assertEqual(_payload["thinking"]["budget_tokens"], 4896)

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_deepseek_uses_effort_not_budget(self, mock_retry: MagicMock) -> None:
        """DeepSeek 使用 effort 而非 budget_tokens 控制思考深度。"""
        cfg = {
            "thinking_enabled_global_macro": True,
            "reasoning_effort_global_macro": "high",
        }
        _call_claude(
            **self.base_kw, model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro", llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertEqual(_payload["thinking"]["type"], "enabled")
        self.assertIn("output_config", _payload)
        self.assertEqual(_payload["output_config"]["effort"], "high")
        # DeepSeek 不发送 budget_tokens
        self.assertNotIn("budget_tokens", _payload["thinking"])
        # temperature 应被移除
        self.assertNotIn("temperature", _payload)

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_deepseek_effort_default_high(self, mock_retry: MagicMock) -> None:
        """DeepSeek 未配置 reasoning_effort 时默认 high。"""
        cfg = {"thinking_enabled_global_macro": True}
        _call_claude(
            **self.base_kw, model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro", llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertEqual(_payload["output_config"]["effort"], "high")

    @patch("src.python.llm_client._call_llm_with_retry")
    def test_deepseek_effort_max(self, mock_retry: MagicMock) -> None:
        """DeepSeek reasoning_effort 可以设为 max。"""
        cfg = {
            "thinking_enabled_global_macro": True,
            "reasoning_effort_global_macro": "max",
        }
        _call_claude(
            **self.base_kw, model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro", llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertEqual(_payload["output_config"]["effort"], "max")


# ═══════════════════════════════════════════════════════════
#  generate_all_llm force passthrough
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm_client.generate_penetration_deep_analysis")
@patch("src.python.llm_client.generate_health_check")
@patch("src.python.llm_client.generate_global_macro")
@patch("src.python.llm_client.generate_expert_review")
class TestGenerateAllLlm(unittest.TestCase):
    """测试并行生成函数。"""

    def test_force_passthrough(self, mock_expert: MagicMock, mock_macro: MagicMock, mock_health: MagicMock, mock_penetration: MagicMock) -> None:
        mock_macro.return_value = ("<p>宏</p>", False)
        mock_expert.return_value = ("<p>策略</p>", False)
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, penetration, mc, ec, hc, pc = generate_all_llm([], [], 0, 0, 0, 0, 0, {}, force=True)

        self.assertEqual(macro, "<p>宏</p>")
        self.assertEqual(expert, "<p>策略</p>")
        self.assertEqual(health, "<p>体检</p>")
        self.assertEqual(penetration, "<p>穿透</p>")
        self.assertFalse(mc)
        self.assertFalse(ec)
        self.assertFalse(hc)
        self.assertFalse(pc)
        # 验证 force=True 被透传
        _, kwargs_m = mock_macro.call_args
        _, kwargs_e = mock_expert.call_args
        self.assertTrue(kwargs_m.get("force"))
        self.assertTrue(kwargs_e.get("force"))

    def test_force_false_default(self, mock_expert: MagicMock, mock_macro: MagicMock, mock_health: MagicMock, mock_penetration: MagicMock) -> None:
        mock_macro.return_value = ("<p>m</p>", False)
        mock_expert.return_value = ("<p>e</p>", False)
        mock_health.return_value = ("<p>h</p>", False)
        mock_penetration.return_value = ("<p>p</p>", False)

        macro, expert, health, penetration, mc, ec, hc, pc = generate_all_llm([], [], 0, 0, 0, 0, 0, {})

        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(penetration)
        self.assertFalse(mc)
        self.assertFalse(ec)
        self.assertFalse(hc)
        self.assertFalse(pc)
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
        from src.python.llm_client import _check_claude_truncation

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 1000, "Claude")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens", log_text)

    def test_check_claude_truncation_custom_field(self) -> None:
        """config_field='max_tokens_expert_review' → 日志提示 max_tokens_expert_review。"""
        from src.python.llm_client import _check_claude_truncation

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 8192, "Claude", config_field="max_tokens_expert_review")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens_expert_review", log_text)
        self.assertIn("8192", log_text)

    def test_check_claude_truncation_not_truncated(self) -> None:
        """stop_reason 不是 max_tokens → 不记录日志。"""
        from src.python.llm_client import _check_claude_truncation

        data = {"stop_reason": "end_turn", "usage": {"output_tokens": 100}}
        result = _check_claude_truncation(data, 8192, "Claude")
        self.assertFalse(result)

    def test_check_openai_truncation_custom_field(self) -> None:
        """OpenAI config_field='max_tokens_global_macro' → 日志提示 max_tokens_macro。"""
        from src.python.llm_client import _check_openai_truncation

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
        from src.python.llm_client import _check_openai_truncation

        data = {"choices": [{"finish_reason": "stop", "message": {"content": "..."}}],
                "usage": {"completion_tokens": 100}}
        result = _check_openai_truncation(data, 8192, "OpenAI")
        self.assertFalse(result)


# ═══════════════════════════════════════════════════════════
#  _build_holdings_summary — 持仓摘要生成
# ═══════════════════════════════════════════════════════════


class TestBuildHoldingsSummary(unittest.TestCase):
    """测试 _build_holdings_summary 的格式和内容。"""

    def setUp(self) -> None:
        from collections import namedtuple
        Holding = namedtuple("Holding", ["name", "code"])
        self.holdings = [
            Holding(name="长江电力", code="600900"),
            Holding(name="贵州茅台", code="600519"),
        ]
        self.penetrated = [
            {"name": "宁德时代", "codes": ["300750"]},
        ]

    def test_basic(self) -> None:
        from src.python.llm_client import _build_holdings_summary
        result = _build_holdings_summary(self.holdings)
        self.assertIn("长江电力", result)
        self.assertIn("600900", result)
        self.assertIn("600519", result)

    def test_with_penetration(self) -> None:
        from src.python.llm_client import _build_holdings_summary
        result = _build_holdings_summary(self.holdings, self.penetrated)
        self.assertIn("[穿透]", result)

    def test_with_industry_data(self) -> None:
        """industry_data 中包含行业和概念 → 显示到摘要中。"""
        from src.python.llm_client import _build_holdings_summary
        industry_data = {
            "600900": {"industry": "电力", "concepts": ["核电", "水电"]},
            "600519": {"industry": "白酒Ⅱ", "concepts": ["白酒", "超级品牌"]},
        }
        result = _build_holdings_summary(self.holdings, industry_data=industry_data)
        self.assertIn("电力", result)
        self.assertIn("白酒Ⅱ", result)
        self.assertIn("核电", result)

    def test_empty(self) -> None:
        from src.python.llm_client import _build_holdings_summary
        result = _build_holdings_summary([], None)
        self.assertEqual(result, "")

    def test_limit_20(self) -> None:
        """超过 20 只持仓时截断。"""
        from collections import namedtuple
        from src.python.llm_client import _build_holdings_summary
        H = namedtuple("Holding", ["name", "code"])
        many = [H(name=f"股票{i}", code=f"{i:06d}") for i in range(30)]
        result = _build_holdings_summary(many)
        lines = [l for l in result.split("\n") if l.strip()]
        # 最多 20 行持仓
        holding_lines = [l for l in lines if "[穿透]" not in l]
        self.assertLessEqual(len(holding_lines), 20)


# ═══════════════════════════════════════════════════════════
#  _build_news_summary — 新闻摘要生成
# ═══════════════════════════════════════════════════════════


class TestBuildNewsSummary(unittest.TestCase):
    """测试 _build_news_summary 的格式和内容。"""

    def test_basic(self) -> None:
        from src.python.llm_client import _build_news_summary
        news = [
            {"title": "能源改革新方案", "intro": "国家能源局发布电力改革方案...",
             "matched_keywords": ["长江电力"]},
        ]
        result = _build_news_summary(news)
        self.assertIn("能源改革", result)
        self.assertIn("长江电力", result)

    def test_empty(self) -> None:
        from src.python.llm_client import _build_news_summary
        self.assertEqual(_build_news_summary([]), "")

    def test_limit_30(self) -> None:
        """超过 30 条时截断。"""
        from src.python.llm_client import _build_news_summary
        many = [{"title": f"新闻{i}", "matched_keywords": []} for i in range(50)]
        result = _build_news_summary(many)
        # 最多 30 条
        count = result.count("标题:")
        self.assertLessEqual(count, 30)


# ═══════════════════════════════════════════════════════════
#  _apply_llm_analysis — LLM 响应解析
# ═══════════════════════════════════════════════════════════


class TestApplyLLMAnalysis(unittest.TestCase):
    """测试 LLM JSON 响应的解析 — 返回 (relevance, sentiment, analysis) 元组列表。"""

    def setUp(self) -> None:
        self.news = [
            {"title": "新闻A", "matched_keywords": ["茅台"]},
            {"title": "新闻B", "matched_keywords": ["五粮液"]},
            {"title": "新闻C", "matched_keywords": []},
        ]

    def test_standard_response(self) -> None:
        from src.python.llm_client import _apply_llm_analysis
        llm_resp = '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "白酒利好"}, {"idx": 1, "relevance": "中", "sentiment": "中性", "analysis": "间接影响"}]'
        result = _apply_llm_analysis(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("高", "利好", "白酒利好"))
        self.assertEqual(result[1], ("中", "中性", "间接影响"))
        self.assertEqual(result[2], ("低", "中性", ""))  # 缺失项默认值

    def test_with_sentiment(self) -> None:
        """解析 sentiment 字段。"""
        from src.python.llm_client import _apply_llm_analysis
        llm_resp = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "白酒利好"},'
            ' {"idx": 1, "relevance": "高", "sentiment": "利空", "analysis": "利空影响"},'
            ' {"idx": 2, "relevance": "低", "sentiment": "中性", "analysis": "中性影响"}]'
        )
        batch = self.news + [{"title": "新闻D", "matched_keywords": []}]
        result = _apply_llm_analysis(batch, llm_resp)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], ("高", "利好", "白酒利好"))
        self.assertEqual(result[1], ("高", "利空", "利空影响"))
        self.assertEqual(result[2], ("低", "中性", "中性影响"))
        self.assertEqual(result[3], ("低", "中性", ""))  # 缺失项默认值

    def test_irrelevant_not_filtered(self) -> None:
        """"无关"不再被过滤——元组中直接返回原始数据，由调用方决定是否跳过。"""
        from src.python.llm_client import _apply_llm_analysis
        llm_resp = '[{"idx": 0, "relevance": "高", "sentiment": "中性", "analysis": "利好"}, {"idx": 1, "relevance": "无关", "sentiment": "中性", "analysis": "无关内容"}]'
        result = _apply_llm_analysis(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("高", "中性", "利好"))
        self.assertEqual(result[1], ("无关", "中性", "无关内容"))
        self.assertEqual(result[2], ("低", "中性", ""))

    def test_malformed_json(self) -> None:
        """JSON 解析失败 → 全部返回默认值。"""
        from src.python.llm_client import _apply_llm_analysis
        result = _apply_llm_analysis(self.news, "不是json")
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_not_a_list(self) -> None:
        """LLM 返回非数组 → 全部返回默认值。"""
        from src.python.llm_client import _apply_llm_analysis
        result = _apply_llm_analysis(self.news, '{"error": "wrong"}')
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_with_code_block(self) -> None:
        """响应包含 Markdown 代码块 → 正确提取 JSON。"""
        from src.python.llm_client import _apply_llm_analysis
        llm_resp = '```json\n[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "直接利好"}]\n```'
        result = _apply_llm_analysis(self.news[:1], llm_resp)
        self.assertEqual(result[0], ("高", "利好", "直接利好"))

    def test_idx_out_of_range(self) -> None:
        """idx 越界时忽略该条目，使用默认值填充。"""
        from src.python.llm_client import _apply_llm_analysis
        llm_resp = '[{"idx": 99, "relevance": "高", "sentiment": "利好", "analysis": "越界"}]'
        result = _apply_llm_analysis(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_empty_batch(self) -> None:
        """空列表 → 返回空列表。"""
        from src.python.llm_client import _apply_llm_analysis
        result = _apply_llm_analysis([], "[]")
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════
#  批次 LLM 新闻分析（TestBatchNewsAnalysis）
# ═══════════════════════════════════════════════════════════


class TestBatchNewsAnalysis(unittest.TestCase):
    """测试批次 LLM 新闻分析功能。"""

    def setUp(self) -> None:
        self.news_5 = [
            {"title": f"新闻{i}", "matched_keywords": ["茅台"]}
            for i in range(5)
        ]

    def test_handle_5_items_in_one_batch(self) -> None:
        """处理 5 条新闻的批次，全部成功返回。"""
        from src.python.llm_client import _apply_llm_analysis
        import json
        llm_resp = json.dumps([
            {"idx": i, "relevance": "高", "sentiment": "利好", "analysis": f"原因{i}"}
            for i in range(5)
        ])
        result = _apply_llm_analysis(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        for i in range(5):
            self.assertEqual(result[i], ("高", "利好", f"原因{i}"))

    def test_partial_json_response(self) -> None:
        """LLM 返回 3 条结果给 5 条新闻 → 缺失 2 条填充默认值。"""
        from src.python.llm_client import _apply_llm_analysis
        import json
        llm_resp = json.dumps([
            {"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "原因0"},
            {"idx": 2, "relevance": "中", "sentiment": "中性", "analysis": "原因2"},
            {"idx": 4, "relevance": "高", "sentiment": "利空", "analysis": "原因4"},
        ])
        result = _apply_llm_analysis(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], ("高", "利好", "原因0"))
        self.assertEqual(result[1], ("低", "中性", ""))  # 缺失
        self.assertEqual(result[2], ("中", "中性", "原因2"))
        self.assertEqual(result[3], ("低", "中性", ""))  # 缺失
        self.assertEqual(result[4], ("高", "利空", "原因4"))

    def test_empty_batch(self) -> None:
        """空批次 → 返回空列表。"""
        from src.python.llm_client import _apply_llm_analysis
        result = _apply_llm_analysis([], "[]")
        self.assertEqual(result, [])

    def test_fewer_results_than_requested(self) -> None:
        """LLM 返回 1 条结果给 5 条新闻 → 缺失 4 条填充默认值。"""
        from src.python.llm_client import _apply_llm_analysis
        import json
        llm_resp = json.dumps([
            {"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "原因0"},
        ])
        result = _apply_llm_analysis(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], ("高", "利好", "原因0"))
        for i in range(1, 5):
            self.assertEqual(result[i], ("低", "中性", ""))

    def test_malformed_json_in_batch(self) -> None:
        """JSON 格式错误 → 全部返回默认值。"""
        from src.python.llm_client import _apply_llm_analysis
        result = _apply_llm_analysis(self.news_5, "这不是JSON")
        self.assertEqual(len(result), 5)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))


# ═══════════════════════════════════════════════════════════
#  enhance_news_correlation — LLM 新闻关联增强
# ═══════════════════════════════════════════════════════════


@patch("src.python.config.get_llm_config")
class TestEnhanceNewsCorrelation(unittest.TestCase):
    """测试 enhance_news_correlation 的主流程。"""

    def setUp(self) -> None:
        self.news = [
            {"title": "新闻A", "intro": "简介", "matched_keywords": ["茅台"]},
            {"title": "新闻B", "intro": "简介", "matched_keywords": ["五粮液"]},
        ]
        self.holdings = [
            MagicMock(name="长江电力", code="600900"),
            MagicMock(name="贵州茅台", code="600519"),
        ]

    def test_llm_not_configured(self, mock_cfg: MagicMock) -> None:
        """LLM 未配置 → 返回原始数据 + 空 token 用量。"""
        from src.python.llm_client import enhance_news_correlation
        mock_cfg.return_value = None
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertEqual(result, self.news)
        self.assertFalse(cached)
        self.assertEqual(usage, {})

    def test_empty_news(self, mock_cfg: MagicMock) -> None:
        """空新闻列表 → 直接返回。"""
        from src.python.llm_client import enhance_news_correlation
        result, cached, usage = enhance_news_correlation([], self.holdings)
        self.assertEqual(result, [])
        self.assertFalse(cached)
        self.assertEqual(usage, {})

    @patch("src.python.llm_client._call_llm")
    @patch("src.python.llm_client.cache_get")
    def test_cache_hit(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """缓存命中 → 直接返回缓存数据，不调用 LLM。"""
        from src.python.llm_client import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = self.news  # 缓存命中
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertTrue(cached)
        mock_call.assert_not_called()

    @patch("src.python.llm_client._call_llm")
    @patch("src.python.llm_client.cache_get")
    def test_llm_success(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """LLM 调用成功 → 返回富化数据。"""
        from src.python.llm_client import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = None  # 缓存未命中
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "高", "analysis": "直接相关"}, '
            '{"idx": 1, "relevance": "中", "analysis": "间接影响"}]',
            {"input_tokens": 100, "output_tokens": 50},
        )
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)
        self.assertIn("llm_analysis", result[0])
        self.assertEqual(usage.get("total_tokens"), 150)

    @patch("src.python.llm_client._call_llm")
    @patch("src.python.llm_client.cache_get")
    def test_llm_failure(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """LLM 调用失败 → 返回原始数据 + 空 token 用量。"""
        from src.python.llm_client import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = None  # 缓存未命中
        mock_call.return_value = (None, None)  # 调用失败
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)
        self.assertEqual(usage, {})
        # 不应有 llm_analysis
        for item in result:
            self.assertNotIn("llm_analysis", item)


if __name__ == "__main__":
    unittest.main()
