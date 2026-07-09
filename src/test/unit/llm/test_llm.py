"""LLM 客户端模块单元测试。

测试目标：
  - _markdown_to_html — 各类 Markdown → HTML 的正确渲染
  - _compute_fingerprint — 确定性哈希、不同输入不同指纹
  - _get_cache_ttl_llm — 全球政经局势 / 智囊团深度复盘 分 TTL
  - _build_global_macro_prompt — 北京时间注入 + 紧凑格式
  - _build_expert_review_prompt — 北京时间注入 + 穿透数据拼接
  - _call_llm — provider 路由
  - generate_all_llm — force 参数透传

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_llm -v
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


from src.python.llm import (
    format_session_usage,
    generate_all_llm,
    get_session_usage,
)
from src.python.llm.session import reset_session_usage
from src.python.llm.generators import generate_expert_review, generate_global_macro
from src.python.llm.api_base import (
    _extract_content,
    _is_effort_model,
    _log_token_usage,
    _supports_extended_thinking,
)
from src.python.llm.api import (
    _call_claude,
    _call_llm,
    _call_openai,
)
from src.python.llm.circuit_breaker import (
    _CIRCUIT_BREAKER_THRESHOLD,
    _CIRCUIT_BREAKER_RECOVERY,
    _cb_endpoint,
    _cb_is_open,
    _cb_record_failure,
    _cb_record_success,
)
from src.python.llm.fingerprint import (
    _compute_fingerprint,
    _get_cache_ttl_llm,
)
from src.python.llm.markdown import _markdown_to_html
from src.python.llm.pricing import (
    _CURRENCY_SYMBOLS,
    _PRICING_MERGED,
    _estimate_cost,
    _reload_pricing,
)
from src.python.llm.prompts import (
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_GLOBAL_MACRO,
    _build_expert_review_prompt,
    _build_global_macro_prompt,
)
from src.python.llm.session import (
    _record_per_module,
    _session_usage,
    _track_session_usage,
)

from src.test.helpers import SynchronousExecutor
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


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

    def test_global_macro_default(self) -> None:
        ttl = _get_cache_ttl_llm("global_macro")
        self.assertGreater(ttl, 0)
        self.assertEqual(ttl, 86400)

    def test_expert_review_default(self) -> None:
        ttl = _get_cache_ttl_llm("expert_review")
        self.assertEqual(ttl, 7200)

    def test_news_correlation_default(self) -> None:
        ttl = _get_cache_ttl_llm("news_correlation")
        self.assertGreater(ttl, 0)
        self.assertEqual(ttl, 3600)


# ═══════════════════════════════════════════════════════════
#  _build_global_macro_prompt
# ═══════════════════════════════════════════════════════════


class TestBuildGlobalMacroPrompt(unittest.TestCase):
    """测试全球政经局势用户提示词。"""

    def test_has_timestamp(self) -> None:
        r = _build_global_macro_prompt({}, {}, 100.0, 10.0, {"股票": 3})
        self.assertIn("北京时间", r)
        self.assertIn("当前时间", r)

    def test_compact_format(self) -> None:
        a_idx = {"sh000001": {"name": "上证指数", "price": 3120, "change_pct": 1.2}}
        r = _build_global_macro_prompt(a_idx, {}, 100000, 5000, {"股票": 3, "基金": 2})
        self.assertIn("上证指数", r)
        self.assertIn("3120", r)
        self.assertIn("+1.20%", r)
        self.assertIn("股票3只", r)
        self.assertIn("基金2只", r)

    def test_single_line_indices(self) -> None:
        """指数应为紧凑单行格式。"""
        a_idx = {"sh000001": {"name": "上证", "price": 3000, "change_pct": -0.5}}
        r = _build_global_macro_prompt(a_idx, {}, 0, 0, {})
        self.assertIn("上证3000(-0.50%)", r)

    def test_no_categories(self) -> None:
        r = _build_global_macro_prompt({}, {}, 0, 0, {})
        self.assertIn("当前时间", r)
        # 不应该有 AssertionError

    def test_with_sector_flow(self) -> None:
        """传入行业资金流向时，prompt 应包含资金流向数据。"""
        sector_flow = [
            {"name": "半导体", "change_pct": 2.5, "main_net_inflow": 1500000000, "main_net_inflow_pct": 3.2},
            {"name": "银行", "change_pct": -0.8, "main_net_inflow": -500000000, "main_net_inflow_pct": -1.1},
        ]
        r = _build_global_macro_prompt({}, {}, 100000, 5000, {"股票": 3}, sector_flow=sector_flow)
        self.assertIn("行业资金流向", r)
        self.assertIn("半导体", r)
        self.assertIn("+2.50%", r)
        self.assertIn("银行", r)
        self.assertIn("-0.80%", r)
        self.assertIn("主力净流入", r)

    def test_sector_flow_none(self) -> None:
        """sector_flow=None 时不应包含资金流向内容。"""
        r = _build_global_macro_prompt({}, {}, 0, 0, {})
        self.assertNotIn("行业资金流向", r)


# ═══════════════════════════════════════════════════════════
#  _build_expert_review_prompt
# ═══════════════════════════════════════════════════════════


class TestBuildReviewPrompt(unittest.TestCase):
    """测试智囊团深度复盘用户提示词。"""

    def test_has_timestamp(self) -> None:
        r = _build_expert_review_prompt(100, 80, 20, 5, 5, {"股票": 3})
        self.assertIn("北京时间", r)
        self.assertIn("当前时间", r)

    def test_with_penetration(self) -> None:
        pen = [
            {"name": "茅台", "codes": ["600519"], "mv": 50000, "sector": "消费"},
            {"name": "宁德", "codes": ["300750"], "mv": 30000, "sector": "新能源"},
        ]
        r = _build_expert_review_prompt(100000, 80000, 20000, 1000, 3, {"基金": 2}, pen)
        self.assertIn("茅台", r)
        self.assertIn("穿透", r)

    def test_without_penetration(self) -> None:
        r = _build_expert_review_prompt(100, 80, 20, 5, 5, {"股票": 3})
        self.assertNotIn("穿透", r)

    def test_compact_format(self) -> None:
        r = _build_expert_review_prompt(100000, 80000, 20000, 1000, 3, {"股票": 2, "基金": 1})
        self.assertIn("股票2只", r)
        self.assertIn("基金1只", r)

    def test_nav_date_label(self) -> None:
        """tencent→今涨跌幅，场外→净值日期。"""
        details = [
            {"code": "600900", "market_value": 100000, "cost": 80000,
             "profit": 20000, "profit_rate": 25.0, "change_pct": 1.2,
             "nav_date": "", "source_api": "tencent"},
            {"code": "110011", "market_value": 50000, "cost": 40000,
             "profit": 10000, "profit_rate": 25.0, "change_pct": -0.5,
             "nav_date": "2026-06-26", "source_api": "eastmoney"},
        ]
        r = _build_expert_review_prompt(150000, 120000, 30000, 1500, 2, {},
                                 holdings_details=details)
        # compact 模式省略今日涨跌幅，保留净值日期
        self.assertNotIn("今+1.20%", r)
        self.assertIn("净值:2026-06-26", r)

    def test_nav_date_empty_fallback(self) -> None:
        """compact 模式下场内品种无今日涨跌幅（减少 token）。"""
        details = [
            {"code": "600900", "market_value": 100000, "cost": 80000,
             "profit": 20000, "profit_rate": 25.0, "change_pct": 1.2},
        ]
        r = _build_expert_review_prompt(100000, 80000, 20000, 1200, 1, {},
                                 holdings_details=details)
        self.assertNotIn("今+1.20%", r)

    def test_qdii_label(self) -> None:
        """compact 模式下 QDII 品种标注 (QDII滞后1日)，省略今日涨跌幅。"""
        details = [
            {"code": "000041", "name": "华夏全球QDII混合", "market_value": 30000, "cost": 25000,
             "profit": 5000, "profit_rate": 20.0, "change_pct": 0.3,
             "nav_date": "2026-06-26", "source_api": "eastmoney"},
            {"code": "513100", "name": "纳指ETF(QDII)", "market_value": 20000, "cost": 18000,
             "profit": 2000, "profit_rate": 11.1, "change_pct": 1.5,
             "nav_date": "", "source_api": "tencent"},
        ]
        r = _build_expert_review_prompt(50000, 43000, 7000, 200, 2, {},
                                 holdings_details=details)
        self.assertIn("净值:2026-06-26(QDII滞后1日)", r)
        # compact 模式省略今日涨跌幅
        self.assertNotIn("今+1.50%", r)
        self.assertIn("(QDII滞后1日)", r)

    def test_system_expert_constraint_updated(self) -> None:
        """_SYSTEM_EXPERT_REVIEW 包含净值约束和 QDII 说明。"""
        self.assertIn("净值", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("QDII", _SYSTEM_EXPERT_REVIEW)
        self.assertIn("滞后", _SYSTEM_EXPERT_REVIEW)


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

    @patch("src.python.llm.api._call_claude")
    def test_claude_routing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = ("claude result", {"input_tokens": 10, "output_tokens": 50})
        config = {"provider": "claude", "api_key": "sk-xxx"}
        content, usage = _call_llm("system", "user", config)
        self.assertEqual(content, "claude result")
        self.assertEqual(usage, {"input_tokens": 10, "output_tokens": 50})
        mock_call.assert_called_once()

    @patch("src.python.llm.api._call_openai")
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
            endpoint="", max_tokens=800, http_client=MagicMock(),
        )
        self.llm_config = {
            "thinking_enabled_global_macro": True,
            "thinking_budget_global_macro": 4000,
        }

    @patch("src.python.llm.api._call_llm_with_retry")
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

    @patch("src.python.llm.api._call_llm_with_retry")
    def test_thinking_skipped_for_unsupported_model(self, mock_retry: MagicMock) -> None:
        """Sonnet-3.5 不支持 Extended Thinking，应降级跳过。"""
        _call_claude(
            **self.base_kw, model="claude-sonnet-3-5-20241022",
            config_field="max_tokens_global_macro", llm_config=self.llm_config,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm.api._call_llm_with_retry")
    def test_thinking_skipped_when_disabled(self, mock_retry: MagicMock) -> None:
        """thinking_enabled=False 时不应注入 thinking 参数。"""
        cfg = {"thinking_enabled_global_macro": False}
        _call_claude(
            **self.base_kw, model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro", llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm.api._call_llm_with_retry")
    def test_thinking_skipped_when_no_llm_config(self, mock_retry: MagicMock) -> None:
        """llm_config=None 时不报错、不注入。"""
        _call_claude(
            **self.base_kw, model="claude-sonnet-4-20250514",
            config_field="max_tokens_global_macro", llm_config=None,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertNotIn("thinking", _payload)

    @patch("src.python.llm.api._call_llm_with_retry")
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

    @patch("src.python.llm.api._call_llm_with_retry")
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

    @patch("src.python.llm.api._call_llm_with_retry")
    def test_deepseek_effort_default_high(self, mock_retry: MagicMock) -> None:
        """DeepSeek 未配置 reasoning_effort 时默认 high。"""
        cfg = {"thinking_enabled_global_macro": True}
        _call_claude(
            **self.base_kw, model="DeepSeek-V4-Flash",
            config_field="max_tokens_global_macro", llm_config=cfg,
        )
        _payload = mock_retry.call_args[1]["payload"]
        self.assertEqual(_payload["output_config"]["effort"], "high")

    @patch("src.python.llm.api._call_llm_with_retry")
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


@patch("src.python.llm.generators_orchestrator.generate_penetration_deep_analysis")
@patch("src.python.llm.generators_orchestrator.generate_health_check")
@patch("src.python.llm.generators_orchestrator.generate_global_macro")
@patch("src.python.llm.generators_orchestrator.generate_expert_review")
class TestGenerateAllLlm(unittest.TestCase):
    """测试并行生成函数。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._cfg_patcher = patch("src.python.llm.generators_orchestrator.get_llm_config",
                                  return_value={"enabled_llm": {
                                      "global_macro": True,
                                      "expert_review": True,
                                      "health_check": True,
                                      "penetration_deep": True,
                                  }})
        cls._cfg_patcher.start()
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
        cls._cfg_patcher.stop()

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
        self.assertTrue(len(_SYSTEM_GLOBAL_MACRO) > 50)
        self.assertIn("宏观", _SYSTEM_GLOBAL_MACRO)

    def test_expert_compact(self) -> None:
        """智囊团 Prompt 已精简。"""
        self.assertLess(len(_SYSTEM_EXPERT_REVIEW), 500,
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
        from src.python.llm.api_base import _check_claude_truncation

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 1000, "Claude")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens", log_text)

    def test_check_claude_truncation_custom_field(self) -> None:
        """config_field='max_tokens_expert_review' → 日志提示 max_tokens_expert_review。"""
        from src.python.llm.api_base import _check_claude_truncation

        data = {"stop_reason": "max_tokens", "usage": {"output_tokens": 500}}
        with self.assertLogs("invest", level="ERROR") as logs:
            result = _check_claude_truncation(data, 8192, "Claude", config_field="max_tokens_expert_review")
        self.assertTrue(result)
        log_text = logs.output[0]
        self.assertIn("max_tokens_expert_review", log_text)
        self.assertIn("8192", log_text)

    def test_check_claude_truncation_not_truncated(self) -> None:
        """stop_reason 不是 max_tokens → 不记录日志。"""
        from src.python.llm.api_base import _check_claude_truncation

        data = {"stop_reason": "end_turn", "usage": {"output_tokens": 100}}
        result = _check_claude_truncation(data, 8192, "Claude")
        self.assertFalse(result)

    def test_check_openai_truncation_custom_field(self) -> None:
        """OpenAI config_field='max_tokens_global_macro' → 日志提示 max_tokens_global_macro。"""
        from src.python.llm.api_base import _check_openai_truncation

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
        from src.python.llm.api_base import _check_openai_truncation

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
        from src.python.llm.prompts import _build_holdings_summary
        result = _build_holdings_summary(self.holdings)
        self.assertIn("长江电力", result)
        self.assertIn("600900", result)
        self.assertIn("600519", result)

    def test_with_penetration(self) -> None:
        from src.python.llm.prompts import _build_holdings_summary
        result = _build_holdings_summary(self.holdings, self.penetrated)
        self.assertIn("[穿透]", result)

    def test_with_industry_data(self) -> None:
        """industry_data 中包含行业和概念 → 显示到摘要中。"""
        from src.python.llm.prompts import _build_holdings_summary
        industry_data = {
            "600900": {"industry": "电力", "concepts": ["核电", "水电"]},
            "600519": {"industry": "白酒Ⅱ", "concepts": ["白酒", "超级品牌"]},
        }
        result = _build_holdings_summary(self.holdings, industry_data=industry_data)
        self.assertIn("电力", result)
        self.assertIn("白酒Ⅱ", result)
        self.assertIn("核电", result)

    def test_empty(self) -> None:
        from src.python.llm.prompts import _build_holdings_summary
        result = _build_holdings_summary([], None)
        self.assertEqual(result, "")

    def test_limit_20(self) -> None:
        """超过 20 只持仓时截断。"""
        from collections import namedtuple
        from src.python.llm.prompts import _build_holdings_summary
        H = namedtuple("Holding", ["name", "code"])
        many = [H(name=f"股票{i}", code=f"{i:06d}") for i in range(30)]
        result = _build_holdings_summary(many)
        lines = [l for l in result.split("\n") if l.strip()]
        # 最多 20 行持仓
        holding_lines = [l for l in lines if "[穿透]" not in l]
        self.assertLessEqual(len(holding_lines), 20)


# ═══════════════════════════════════════════════════════════
#  _build_news_correlation_summary — 新闻摘要生成（LLM 关联分析用）
# ═══════════════════════════════════════════════════════════


class TestBuildNewsSummary(unittest.TestCase):
    """测试 _build_news_correlation_summary 的格式和内容。"""

    def test_basic(self) -> None:
        from src.python.llm.prompts import _build_news_correlation_summary
        news = [
            {"title": "能源改革新方案", "intro": "国家能源局发布电力改革方案...",
             "matched_keywords": ["长江电力"]},
        ]
        result = _build_news_correlation_summary(news)
        self.assertIn("能源改革", result)
        self.assertIn("长江电力", result)

    def test_empty(self) -> None:
        from src.python.llm.prompts import _build_news_correlation_summary
        self.assertEqual(_build_news_correlation_summary([]), "")

    def test_limit_30(self) -> None:
        """超过 30 条时截断。"""
        from src.python.llm.prompts import _build_news_correlation_summary
        many = [{"title": f"新闻{i}", "matched_keywords": []} for i in range(50)]
        result = _build_news_correlation_summary(many)
        # 最多 30 条
        count = result.count("标题:")
        self.assertLessEqual(count, 30)


# ═══════════════════════════════════════════════════════════
#  _apply_llm_news_correlation — LLM 响应解析
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
        from src.python.llm.generators_news import _apply_llm_news_correlation
        llm_resp = '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "白酒利好"}, {"idx": 1, "relevance": "中", "sentiment": "中性", "analysis": "间接影响"}]'
        result = _apply_llm_news_correlation(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("高", "利好", "白酒利好"))
        self.assertEqual(result[1], ("中", "中性", "间接影响"))
        self.assertEqual(result[2], ("低", "中性", ""))  # 缺失项默认值

    def test_with_sentiment(self) -> None:
        """解析 sentiment 字段。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        llm_resp = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "白酒利好"},'
            ' {"idx": 1, "relevance": "高", "sentiment": "利空", "analysis": "利空影响"},'
            ' {"idx": 2, "relevance": "低", "sentiment": "中性", "analysis": "中性影响"}]'
        )
        batch = self.news + [{"title": "新闻D", "matched_keywords": []}]
        result = _apply_llm_news_correlation(batch, llm_resp)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], ("高", "利好", "白酒利好"))
        self.assertEqual(result[1], ("高", "利空", "利空影响"))
        self.assertEqual(result[2], ("低", "中性", "中性影响"))
        self.assertEqual(result[3], ("低", "中性", ""))  # 缺失项默认值

    def test_irrelevant_not_filtered(self) -> None:
        """"无关"不再被过滤——元组中直接返回原始数据，由调用方决定是否跳过。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        llm_resp = '[{"idx": 0, "relevance": "高", "sentiment": "中性", "analysis": "利好"}, {"idx": 1, "relevance": "无关", "sentiment": "中性", "analysis": "无关内容"}]'
        result = _apply_llm_news_correlation(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("高", "中性", "利好"))
        self.assertEqual(result[1], ("无关", "中性", "无关内容"))
        self.assertEqual(result[2], ("低", "中性", ""))

    def test_malformed_json(self) -> None:
        """JSON 解析失败 → 全部返回默认值。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        result = _apply_llm_news_correlation(self.news, "不是json")
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_not_a_list(self) -> None:
        """LLM 返回非数组 → 全部返回默认值。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        result = _apply_llm_news_correlation(self.news, '{"error": "wrong"}')
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_with_code_block(self) -> None:
        """响应包含 Markdown 代码块 → 正确提取 JSON。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        llm_resp = '```json\n[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "直接利好"}]\n```'
        result = _apply_llm_news_correlation(self.news[:1], llm_resp)
        self.assertEqual(result[0], ("高", "利好", "直接利好"))

    def test_idx_out_of_range(self) -> None:
        """idx 越界时忽略该条目，使用默认值填充。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        llm_resp = '[{"idx": 99, "relevance": "高", "sentiment": "利好", "analysis": "越界"}]'
        result = _apply_llm_news_correlation(self.news, llm_resp)
        self.assertEqual(len(result), 3)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))

    def test_empty_batch(self) -> None:
        """空列表 → 返回空列表。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        result = _apply_llm_news_correlation([], "[]")
        self.assertEqual(result, [])


# ═══════════════════════════════════════════════════════════
#  批次 财经新闻热点与持仓关联分析（TestBatchNewsAnalysis）
# ═══════════════════════════════════════════════════════════


class TestBatchNewsAnalysis(unittest.TestCase):
    """测试批次 财经新闻热点与持仓关联分析功能。"""

    def setUp(self) -> None:
        self.news_5 = [
            {"title": f"新闻{i}", "matched_keywords": ["茅台"]}
            for i in range(5)
        ]

    def test_handle_5_items_in_one_batch(self) -> None:
        """处理 5 条新闻的批次，全部成功返回。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        import json
        llm_resp = json.dumps([
            {"idx": i, "relevance": "高", "sentiment": "利好", "analysis": f"原因{i}"}
            for i in range(5)
        ])
        result = _apply_llm_news_correlation(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        for i in range(5):
            self.assertEqual(result[i], ("高", "利好", f"原因{i}"))

    def test_partial_json_response(self) -> None:
        """LLM 返回 3 条结果给 5 条新闻 → 缺失 2 条填充默认值。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        import json
        llm_resp = json.dumps([
            {"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "原因0"},
            {"idx": 2, "relevance": "中", "sentiment": "中性", "analysis": "原因2"},
            {"idx": 4, "relevance": "高", "sentiment": "利空", "analysis": "原因4"},
        ])
        result = _apply_llm_news_correlation(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], ("高", "利好", "原因0"))
        self.assertEqual(result[1], ("低", "中性", ""))  # 缺失
        self.assertEqual(result[2], ("中", "中性", "原因2"))
        self.assertEqual(result[3], ("低", "中性", ""))  # 缺失
        self.assertEqual(result[4], ("高", "利空", "原因4"))

    def test_empty_batch(self) -> None:
        """空批次 → 返回空列表。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        result = _apply_llm_news_correlation([], "[]")
        self.assertEqual(result, [])

    def test_fewer_results_than_requested(self) -> None:
        """LLM 返回 1 条结果给 5 条新闻 → 缺失 4 条填充默认值。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        import json
        llm_resp = json.dumps([
            {"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "原因0"},
        ])
        result = _apply_llm_news_correlation(self.news_5, llm_resp)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0], ("高", "利好", "原因0"))
        for i in range(1, 5):
            self.assertEqual(result[i], ("低", "中性", ""))

    def test_malformed_json_in_batch(self) -> None:
        """JSON 格式错误 → 全部返回默认值。"""
        from src.python.llm.generators_news import _apply_llm_news_correlation
        result = _apply_llm_news_correlation(self.news_5, "这不是JSON")
        self.assertEqual(len(result), 5)
        for t in result:
            self.assertEqual(t, ("低", "中性", ""))


# ═══════════════════════════════════════════════════════════
#  enhance_news_correlation — 财经新闻热点与持仓关联分析 LLM 增强
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.get_llm_config")
class TestEnhanceNewsCorrelation(unittest.TestCase):
    """测试 enhance_news_correlation 的主流程。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm.skeleton.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.skeleton.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()

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
        from src.python.llm import enhance_news_correlation
        mock_cfg.return_value = None
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertEqual(result, self.news)
        self.assertFalse(cached)
        self.assertEqual(usage, {})

    def test_empty_news(self, mock_cfg: MagicMock) -> None:
        """空新闻列表 → 直接返回。"""
        from src.python.llm import enhance_news_correlation
        result, cached, usage = enhance_news_correlation([], self.holdings)
        self.assertEqual(result, [])
        self.assertFalse(cached)
        self.assertEqual(usage, {})

    @patch("src.python.llm.skeleton._call_llm")
    @patch("src.python.llm.skeleton.cache_get")
    def test_cache_hit(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """每篇文章独立缓存命中 → 直接返回，不调用 LLM。"""
        from src.python.llm import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        # 每篇文章的独立缓存存储 dict {relevance, sentiment, analysis}
        mock_cache_get.return_value = {"relevance": "高", "sentiment": "利好", "analysis": "已缓存"}
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertTrue(cached)
        mock_call.assert_not_called()

    @patch("src.python.llm.skeleton._call_llm")
    @patch("src.python.llm.skeleton.cache_get")
    def test_llm_success(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """LLM 调用成功 → 返回富化数据。"""
        from src.python.llm import enhance_news_correlation
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

    @patch("src.python.llm.skeleton._call_llm")
    @patch("src.python.llm.skeleton.cache_get")
    def test_llm_failure(self, mock_cache_get: MagicMock, mock_call: MagicMock, mock_cfg: MagicMock) -> None:
        """LLM 调用失败 → 返回原始数据 + 空 token 用量。"""
        from src.python.llm import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = None  # 缓存未命中
        mock_call.return_value = (None, None)  # 调用失败
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)
        self.assertEqual(usage, {})
        # 不应有 llm_analysis
        for item in result:
            self.assertNotIn("llm_analysis", item)


# ═══════════════════════════════════════════════════════════
#  generate_* 传递 llm_config 参数
# ═══════════════════════════════════════════════════════════


class TestGenerateFunctionsAcceptLlmConfig(unittest.TestCase):
    """测试 generate_* 函数传递 llm_config 参数。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
    """测试 generate_* 函数接受外部 llm_config 参数。"""

    @patch("src.python.llm.skeleton._generate_llm_content")
    def test_global_macro_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """传入 llm_config → 被 _generate_llm_content 接收。"""
        from src.python.llm.generators import generate_global_macro
        mock_gen.return_value = ("<p>结果</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_global_macro": False}
        result, cached = generate_global_macro(
            a_indices={}, us_indices={}, total_mv=0, total_profit=0,
            categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>结果</p>")
        # 验证传递给 _generate_llm_content 的第一个参数是传入的 llm_config
        self.assertIs(mock_gen.call_args[0][0], llm_config)

    @patch("src.python.llm.skeleton._generate_llm_content")
    def test_expert_review_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """gen_expert_review 传递 llm_config 到 _generate_llm_content。"""
        from src.python.llm.generators import generate_expert_review
        mock_gen.return_value = ("<p>复盘</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_expert_review": False}
        result, cached = generate_expert_review(
            total_mv=0, total_cost=0, total_profit=0, total_today_profit=0,
            holdings_count=1, categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>复盘</p>")
        self.assertIs(mock_gen.call_args[0][0], llm_config)

    @patch("src.python.llm.skeleton._generate_llm_content")
    def test_health_check_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """gen_health_check 传递 llm_config 到 _generate_llm_content。"""
        from src.python.llm.generators import generate_health_check
        mock_gen.return_value = ("<p>体检</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_health_check": False}
        result, cached = generate_health_check(
            total_mv=0, total_cost=0, total_profit=0, total_today_profit=0,
            holdings_count=1, categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>体检</p>")
        self.assertIs(mock_gen.call_args[0][0], llm_config)

    @patch("src.python.llm.skeleton._generate_llm_content")
    def test_penetration_uses_passed_config(
        self, mock_gen: MagicMock,
    ) -> None:
        """gen_penetration_deep_analysis 传递 llm_config。"""
        from src.python.llm.generators import generate_penetration_deep_analysis
        mock_gen.return_value = ("<p>穿透</p>", False)
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_penetration_deep": False}
        result, cached = generate_penetration_deep_analysis(
            total_mv=0, total_cost=0, total_profit=0, total_today_profit=0,
            holdings_count=1, categories={}, llm_config=llm_config,
        )
        self.assertEqual(result, "<p>穿透</p>")
        self.assertIs(mock_gen.call_args[0][0], llm_config)


class TestEnhanceNewsCorrelationUsesLlmConfig(unittest.TestCase):
    """测试 enhance_news_correlation 接受 llm_config 参数。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()

    @patch("src.python.llm.skeleton.cache_get", return_value=None)
    @patch("src.python.llm.skeleton._call_llm")
    def test_passed_config_used(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
    ) -> None:
        """传入 llm_config → 不需要内部 get_llm_config()。"""
        from src.python.llm import enhance_news_correlation
        news = [{"title": "A", "matched_keywords": ["茅台"]}]
        holdings = [MagicMock(name="茅台", code="600519")]
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "好"}]',
            {"input_tokens": 10, "output_tokens": 5},
        )
        llm_config = {"provider": "claude", "api_key": "sk-test", "cache_enabled_news_correlation": False}
        result, cached, usage = enhance_news_correlation(
            news, holdings, llm_config=llm_config,
        )
        self.assertIn("llm_analysis", result[0])
        # 验证 _call_llm 接受到 config（首个参数应为 llm_config）
        self.assertIs(mock_call.call_args[0][2], llm_config)


# ═══════════════════════════════════════════════════════════
#  generate_all_llm 缓存预检
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm.generators_orchestrator.generate_penetration_deep_analysis")
@patch("src.python.llm.generators_orchestrator.generate_health_check")
@patch("src.python.llm.generators_orchestrator.generate_global_macro")
@patch("src.python.llm.generators_orchestrator.generate_expert_review")
class TestGenerateAllLlmCachePrecheck(unittest.TestCase):
    """测试 generate_all_llm 缓存预检行为。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._cfg_patcher = patch("src.python.llm.generators_orchestrator.get_llm_config",
                                  return_value={"enabled_llm": {
                                      "global_macro": True,
                                      "expert_review": True,
                                      "health_check": True,
                                      "penetration_deep": True,
                                  }})
        cls._cfg_patcher.start()
        cls._exec_patcher = patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.generators_orchestrator.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()
        cls._cfg_patcher.stop()

    CACHED_CONTENT = '<p>缓存内容</p><p style="color:#888;font-size:12px">本次使用LLM缓存</p>'

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_all_cached_no_threads(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """全部缓存命中 → 不调用 generate_* 函数。"""
        mock_cache_get.return_value = self.CACHED_CONTENT
        macro, expert, health, pen, mc, ec, hc, pc = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        self.assertTrue(mc)
        self.assertTrue(ec)
        self.assertTrue(hc)
        self.assertTrue(pc)
        mock_macro.assert_not_called()
        mock_expert.assert_not_called()
        mock_health.assert_not_called()
        mock_penetration.assert_not_called()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_none_cached_all_threads(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """全部未缓存 → 调用全部 generate_* 函数。"""
        mock_cache_get.return_value = None
        mock_macro.return_value = ("<p>宏</p>", False)
        mock_expert.return_value = ("<p>策略</p>", False)
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, pen, mc, ec, hc, pc = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        mock_macro.assert_called_once()
        mock_expert.assert_called_once()
        mock_health.assert_called_once()
        mock_penetration.assert_called_once()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_force_skips_cache(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """force=True → 跳过缓存预检，全部线程生成。"""
        mock_cache_get.return_value = self.CACHED_CONTENT
        mock_macro.return_value = ("<p>宏</p>", False)
        mock_expert.return_value = ("<p>策略</p>", False)
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, pen, mc, ec, hc, pc = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
            force=True,
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        # force=True 时 force_flag=True → can_cache_* 全为 False → 不走缓存
        mock_macro.assert_called_once()
        mock_expert.assert_called_once()
        mock_health.assert_called_once()
        mock_penetration.assert_called_once()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    def test_partial_cache_some_threads(
        self, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """部分缓存命中 → 仅未命中的模块提交线程。"""
        # 模拟 macro 和 expert 命中缓存，health 和 penetration 未命中
        def _side_effect(key, ttl=None):
            if "global_macro" in key or "expert_review" in key:
                return self.CACHED_CONTENT
            return None
        mock_cache_get.side_effect = _side_effect
        mock_health.return_value = ("<p>体检</p>", False)
        mock_penetration.return_value = ("<p>穿透</p>", False)

        macro, expert, health, pen, mc, ec, hc, pc = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )
        self.assertIsNotNone(macro)
        self.assertIsNotNone(expert)
        self.assertIsNotNone(health)
        self.assertIsNotNone(pen)
        self.assertTrue(mc)
        self.assertTrue(ec)
        self.assertFalse(hc)
        self.assertFalse(pc)
        mock_macro.assert_not_called()
        mock_expert.assert_not_called()
        mock_health.assert_called_once()
        mock_penetration.assert_called_once()

    @patch("src.python.llm.generators_orchestrator.cache_get")
    @patch("src.python.llm.generators_orchestrator._record_per_module")
    def test_cache_hit_records_per_module(
        self, mock_record: MagicMock, mock_cache_get: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """全部缓存命中 → 为每个模块记录 per_module 用量（cached=True）。"""
        mock_cache_get.return_value = self.CACHED_CONTENT

        macro, expert, health, pen, mc, ec, hc, pc = generate_all_llm(
            {}, {}, 0, 0, 0, 0, 0, {},
            holdings_details=[], penetrated_assets=[],
        )

        self.assertEqual(mock_record.call_count, 4)
        expected_keys = {"global_macro", "expert_review", "health_check", "penetration_deep"}
        actual_keys = {call[0][0] for call in mock_record.call_args_list}
        self.assertEqual(actual_keys, expected_keys)
        # 每个调用必须带 cached=True
        for call in mock_record.call_args_list:
            kwargs = call[1] if len(call) > 1 else {}
            cached = kwargs.get("cached") if "cached" in kwargs else (call[0][2] if len(call[0]) > 2 else False)
            self.assertTrue(cached, f"模块 {call[0][0]} 的 cached 不是 True")

    @patch("src.python.llm.generators_orchestrator._record_per_module")
    def test_partial_cache_records_per_module(
        self, mock_record: MagicMock,
        mock_expert: MagicMock, mock_macro: MagicMock,
        mock_health: MagicMock, mock_penetration: MagicMock,
    ) -> None:
        """部分缓存命中 → 仅缓存命中模块记录 per_module。"""
        # 模拟 precheck 缓存：需要 mock cache_get 但该函数在 @patch 顺序中未直接传入
        # 直接调用 _precheck_one_cache 验证，而非 generate_all_llm
        from src.python.llm.generators_orchestrator import _precheck_one_cache

        cache_info = {"key": "llm_global_macro_fp", "ttl": 3600,
                       "can_cache": True, "thinking_key": "thinking_enabled_global_macro"}
        llm_config = {"model": "test-model", "endpoint": "https://test.endpoint"}

        with patch("src.python.llm.generators_orchestrator.cache_get", return_value=self.CACHED_CONTENT):
            result, from_cache = _precheck_one_cache(cache_info, llm_config, "global_macro")

        self.assertIsNotNone(result)
        self.assertTrue(from_cache)
        # 当缓存内容不含模型名时，使用 llm_config["model"] 作为模型名
        mock_record.assert_called_once_with(
            "global_macro", "test-model", cached=True,
            thinking=False, endpoint="https://test.endpoint",
        )


# ═══════════════════════════════════════════════════════════
#  enhance_news_correlation 逐条缓存
# ═══════════════════════════════════════════════════════════


@patch("src.python.llm.skeleton.get_llm_config")
class TestEnhanceNewsCorrelationGranularCache(unittest.TestCase):
    """测试财经新闻热点与持仓关联分析的逐条缓存行为。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._exec_patcher = patch("src.python.llm.skeleton.ThreadPoolExecutor",
                                   new=SynchronousExecutor)
        cls._exec_patcher.start()
        cls._httpx_patcher = patch("src.python.llm.skeleton.httpx.Client",
                                    new=MagicMock())
        cls._httpx_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._httpx_patcher.stop()
        cls._exec_patcher.stop()

    def setUp(self):
        self.news = [
            {"title": "新闻A", "intro": "简介", "matched_keywords": ["茅台"]},
            {"title": "新闻B", "intro": "简介", "matched_keywords": ["五粮液"]},
            {"title": "新闻C", "intro": "简介", "matched_keywords": ["茅台", "五粮液"]},
        ]
        self.holdings = [
            MagicMock(name="长江电力", code="600900"),
            MagicMock(name="贵州茅台", code="600519"),
        ]

    @patch("src.python.llm.skeleton.cache_get")
    @patch("src.python.llm.skeleton._call_llm")
    def test_all_articles_cached(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
        mock_cfg: MagicMock,
    ) -> None:
        """全部文章独立缓存命中 → cached=True + 不调用 LLM。"""
        from src.python.llm import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_cache_get.return_value = {"relevance": "高", "sentiment": "利好", "analysis": "缓存"}
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertTrue(cached)
        mock_call.assert_not_called()
        # 文章应有 llm_analysis 字段
        for item in result:
            self.assertIn("llm_analysis", item)

    @patch("src.python.llm.skeleton.cache_get", return_value=None)
    @patch("src.python.llm.skeleton._call_llm")
    def test_no_cache_all_fresh(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
        mock_cfg: MagicMock,
    ) -> None:
        """全部未缓存 → cached=False + 调用 LLM。"""
        from src.python.llm import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "高", "sentiment": "利好", "analysis": "A"},'
            '{"idx": 1, "relevance": "中", "sentiment": "中性", "analysis": "B"},'
            '{"idx": 2, "relevance": "低", "sentiment": "利空", "analysis": "C"}]',
            {"input_tokens": 200, "output_tokens": 100},
        )
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)
        self.assertGreater(usage.get("total_tokens", 0), 0)
        mock_call.assert_called_once()

    @patch("src.python.llm.skeleton.cache_get")
    @patch("src.python.llm.skeleton._call_llm")
    def test_mixed_cache(
        self, mock_call: MagicMock, mock_cache_get: MagicMock,
        mock_cfg: MagicMock,
    ) -> None:
        """部分文章缓存 → 仅未缓存文章走 LLM。"""
        from src.python.llm import enhance_news_correlation
        mock_cfg.return_value = {"provider": "claude", "api_key": "sk-x"}
        # 文章 0 和 2 缓存命中，文章 1 未命中
        self._call_count = 0

        def _side_effect(*args, **kwargs):
            self._call_count += 1
            # 前 2 次调用对应文章 0 和 2（已排序后 top_news 顺序）
            if self._call_count in (1, 3):
                return {"relevance": "高", "sentiment": "利好", "analysis": "缓存"}
            return None

        mock_cache_get.side_effect = _side_effect
        mock_call.return_value = (
            '[{"idx": 0, "relevance": "中", "sentiment": "中性", "analysis": "新鲜"}]',
            {"input_tokens": 50, "output_tokens": 25},
        )
        result, cached, usage = enhance_news_correlation(self.news, self.holdings)
        self.assertFalse(cached)  # 部分未缓存 → 整体 cached=False
        mock_call.assert_called_once()


# ═══════════════════════════════════════════════════════════
#  Pricing — _estimate_cost / _reload_pricing / _PRICING_MERGED
# ═══════════════════════════════════════════════════════════


class TestPricing(unittest.TestCase):
    """测试 LLM 费用估算和定价管理。"""

    def test_estimate_cost_known_model(self) -> None:
        """已知模型应返回正确的费用估算。"""
        cost = _estimate_cost("deepseek-v4-flash", 3000, 2000)
        # (3000/1M)*1 + (2000/1M)*2 = 0.003 + 0.004 = 0.007
        self.assertIn("0.007", cost)

    def test_estimate_cost_cache_hit(self) -> None:
        """缓存命中应降低费用。"""
        cost = _estimate_cost("deepseek-v4-flash", 3000, 2000, cache_hit_input_tokens=2000)
        cost_no = _estimate_cost("deepseek-v4-flash", 3000, 2000, cache_hit_input_tokens=0)
        self.assertNotEqual(cost, cost_no)

    def test_estimate_cost_unknown_model(self) -> None:
        """未知模型应返回 -。"""
        self.assertEqual(_estimate_cost("nonexistent-model", 100, 100), "-")

    def test_estimate_cost_zero_tokens(self) -> None:
        """零 token 应返回 -。"""
        self.assertEqual(_estimate_cost("deepseek-v4-flash", 0, 0), "-")

    def test_estimate_cost_model_prefix_match(self) -> None:
        """模型名前缀匹配应选择正确的定价。"""
        cost = _estimate_cost("claude-sonnet-4-6-20250514", 1000, 500)
        self.assertNotEqual(cost, "-")

    def test_pricing_merged_has_defaults(self) -> None:
        """_PRICING_MERGED 应包含所有内置模型。"""
        for model in ("deepseek-v4-flash", "claude-sonnet-4-6", "gpt-4o"):
            self.assertIn(model, _PRICING_MERGED)

    def test_currency_symbols(self) -> None:
        """货币符号映射应包含主要货币。"""
        self.assertIn("CNY", _CURRENCY_SYMBOLS)
        self.assertIn("USD", _CURRENCY_SYMBOLS)
        self.assertEqual(_CURRENCY_SYMBOLS["CNY"], "¥")
        self.assertEqual(_CURRENCY_SYMBOLS["USD"], "$")

    def test_reload_pricing_merge(self) -> None:
        """_reload_pricing 应合并不覆盖已有值。"""
        orig = dict(_PRICING_MERGED)
        _reload_pricing()
        self.assertEqual(_PRICING_MERGED.get("deepseek-v4-flash"),
                         orig.get("deepseek-v4-flash"))


# ═══════════════════════════════════════════════════════════
#  Session — _track_session_usage / format_session_usage / _record_per_module
# ═══════════════════════════════════════════════════════════


class TestSession(unittest.TestCase):
    """测试 LLM 会话统计模块。"""

    def setUp(self) -> None:
        reset_session_usage()

    def test_reset_clears_all(self) -> None:
        """reset_session_usage 应清零所有累计。"""
        _track_session_usage("claude", {"input_tokens": 100, "output_tokens": 50}, "claude-sonnet-4-6")
        reset_session_usage()
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 0)
        self.assertEqual(usage["output_tokens"], 0)
        self.assertEqual(usage["call_count"], 0)

    def test_track_claude_usage(self) -> None:
        """Claude 格式的用量应正确累计。"""
        _track_session_usage("claude", {"input_tokens": 200, "output_tokens": 100,
                                        "cache_read_input_tokens": 50}, "claude-sonnet-4-6")
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 200)
        self.assertEqual(usage["output_tokens"], 100)
        self.assertEqual(usage["cache_hit_tokens"], 50)
        self.assertEqual(usage["call_count"], 1)
        self.assertEqual(usage["model"], "claude-sonnet-4-6")

    def test_track_openai_usage(self) -> None:
        """OpenAI 格式的用量应正确累计。"""
        _track_session_usage("openai", {"prompt_tokens": 150, "completion_tokens": 75}, "gpt-4o")
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 150)
        self.assertEqual(usage["output_tokens"], 75)

    def test_track_none_usage_no_op(self) -> None:
        """None 用量不应改变累计值。"""
        _track_session_usage("claude", None)
        usage = get_session_usage()
        self.assertEqual(usage["call_count"], 0)

    def test_get_session_usage_returns_copy(self) -> None:
        """get_session_usage 应返回副本而非引用。"""
        usage = get_session_usage()
        usage["input_tokens"] = 999
        self.assertEqual(_session_usage["input_tokens"], 0)

    def test_track_multiple_calls_accumulate(self) -> None:
        """多次调用应正确累加。"""
        for _ in range(5):
            _track_session_usage("claude", {"input_tokens": 100, "output_tokens": 50})
        usage = get_session_usage()
        self.assertEqual(usage["input_tokens"], 500)
        self.assertEqual(usage["output_tokens"], 250)
        self.assertEqual(usage["call_count"], 5)

    def test_record_per_module(self) -> None:
        """_record_per_module 应记录模块级用量。"""
        _record_per_module("global_macro", "deepseek-v4-flash", inp=100, out=50)
        _record_per_module("expert_review", "deepseek-v4-flash", inp=200, out=100)
        usage = get_session_usage()
        self.assertIn("global_macro", usage["per_module"])
        self.assertIn("expert_review", usage["per_module"])
        self.assertEqual(usage["per_module"]["global_macro"]["input_tokens"], 100)
        self.assertEqual(usage["per_module"]["expert_review"]["output_tokens"], 100)

    def test_record_per_module_accumulate(self) -> None:
        """同一模块多次记录应累加 token。"""
        _record_per_module("global_macro", "deepseek-v4-flash", inp=100, out=50)
        _record_per_module("global_macro", "deepseek-v4-flash", inp=50, out=25)
        self.assertEqual(_session_usage["per_module"]["global_macro"]["input_tokens"], 150)

    def test_format_session_usage_no_data(self) -> None:
        """无数据时应返回 has_usage=False。"""
        result = format_session_usage(None)
        self.assertFalse(result["has_usage"])
        result = format_session_usage({})
        self.assertFalse(result["has_usage"])

    def test_format_session_usage_with_data(self) -> None:
        """有数据时应正确格式化。"""
        _track_session_usage("claude", {"input_tokens": 1000, "output_tokens": 500}, "deepseek-v4-flash")
        raw = get_session_usage()
        result = format_session_usage(raw)
        self.assertTrue(result["has_usage"])
        self.assertEqual(result["call_count"], 1)
        self.assertEqual(result["total_tokens"], 1500)
        self.assertIn("cost_display", result)

    def test_track_session_usage_models_dedup(self) -> None:
        """多次使用同一模型应去重。"""
        _track_session_usage("claude", {"input_tokens": 100, "output_tokens": 50}, "deepseek-v4-flash")
        _track_session_usage("claude", {"input_tokens": 200, "output_tokens": 100}, "deepseek-v4-flash")
        self.assertEqual(len(_session_usage["models"]), 1)


# ═══════════════════════════════════════════════════════════
#  Circuit Breaker — _cb_endpoint / _cb_record_failure / _cb_record_success / _cb_is_open
# ═══════════════════════════════════════════════════════════


class TestCircuitBreaker(unittest.TestCase):
    """测试 LLM 熔断器逻辑。"""

    def setUp(self) -> None:
        import src.python.llm.circuit_breaker as _cb
        _cb._circuit_failures.clear()
        _cb._circuit_open_until.clear()

    def test_cb_endpoint_normal(self) -> None:
        """应正确提取域名。"""
        self.assertEqual(_cb_endpoint("https://api.anthropic.com/v1/messages"), "api.anthropic.com")

    def test_cb_endpoint_empty(self) -> None:
        """空 URL 应返回 unknown。"""
        self.assertEqual(_cb_endpoint(""), "unknown")

    def test_cb_endpoint_invalid(self) -> None:
        """无效 URL 应返回 unknown。"""
        self.assertEqual(_cb_endpoint("not-a-url"), "unknown")

    def test_cb_record_failure_increment(self) -> None:
        """记录失败应递增计数。"""
        _cb_record_failure("https://api.anthropic.com/v1/messages")
        _cb_record_failure("https://api.anthropic.com/v1/messages")
        from src.python.llm.circuit_breaker import _circuit_failures
        self.assertEqual(_circuit_failures.get("api.anthropic.com"), 2)

    def test_cb_record_failure_opens_at_threshold(self) -> None:
        """达到阈值应开启熔断。"""
        url = "https://api.test.com/v1"
        for _ in range(_CIRCUIT_BREAKER_THRESHOLD):
            _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))

    def test_cb_record_success_resets(self) -> None:
        """成功应重置失败计数。"""
        url = "https://api.test.com/v1"
        _cb_record_failure(url)
        _cb_record_success(url)
        from src.python.llm.circuit_breaker import _circuit_failures
        self.assertNotIn("api.test.com", _circuit_failures)

    def test_cb_is_open_unknown_endpoint(self) -> None:
        """未知 endpoint 返回 False。"""
        self.assertFalse(_cb_is_open("https://api.unknown.com/v1"))

    def test_cb_record_success_after_opened(self) -> None:
        """熔断后成功应关闭熔断。"""
        url = "https://api.test.com/v1"
        for _ in range(_CIRCUIT_BREAKER_THRESHOLD):
            _cb_record_failure(url)
        self.assertTrue(_cb_is_open(url))
        _cb_record_success(url)
        self.assertFalse(_cb_is_open(url))


# ═══════════════════════════════════════════════════════════════
#  R-086: Provider 回退链路测试
# ═══════════════════════════════════════════════════════════════


class TestProviderFallback(unittest.TestCase):
    """测试 _call_llm 在主 provider 失败时回退到 fallback provider。"""

    @patch("src.python.llm.api._call_single_provider")
    def test_main_provider_success_no_fallback(self, mock_call):
        """主 provider 成功 → 不调用 fallback。"""
        mock_call.return_value = ("main result", {"input_tokens": 100})
        config = {
            "provider": "claude", "api_key": "sk-main",
            "fallback_provider": "openai", "fallback_api_key": "sk-fb",
        }
        content, usage = _call_llm("sys", "user", config)
        self.assertEqual(content, "main result")
        self.assertEqual(mock_call.call_count, 1)

    @patch("src.python.llm.api._call_single_provider")
    def test_main_failure_fallback_used(self, mock_call):
        """主 provider 返回 None → fallback 被调用。"""
        mock_call.side_effect = [
            (None, None),          # 主 provider 失败
            ("fb result", {"prompt_tokens": 50}),  # fallback 成功
        ]
        config = {
            "provider": "claude", "api_key": "sk-main",
            "fallback_provider": "openai", "fallback_api_key": "sk-fb",
            "fallback_endpoint": "https://api.openai.com/v1",
            "fallback_model": "gpt-4o",
        }
        content, usage = _call_llm("sys", "user", config)
        self.assertEqual(content, "fb result")
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api._call_single_provider")
    def test_main_and_fallback_both_fail(self, mock_call):
        """主 + fallback 均失败 → (None, None)。"""
        mock_call.return_value = (None, None)
        config = {
            "provider": "claude", "api_key": "sk-main",
            "fallback_provider": "openai", "fallback_api_key": "sk-fb",
        }
        content, usage = _call_llm("sys", "user", config)
        self.assertIsNone(content)
        self.assertIsNone(usage)
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api._call_single_provider")
    def test_no_fallback_configured(self, mock_call):
        """未配置 fallback → 不尝试 fallback。"""
        mock_call.return_value = (None, None)
        config = {"provider": "claude", "api_key": "sk-main"}
        content, usage = _call_llm("sys", "user", config)
        self.assertIsNone(content)
        self.assertEqual(mock_call.call_count, 1)

    @patch("src.python.llm.api._call_single_provider")
    def test_fallback_same_as_main_no_loop(self, mock_call):
        """fallback_provider == provider → 不重复调用。"""
        mock_call.return_value = (None, None)
        config = {
            "provider": "claude", "api_key": "sk-main",
            "fallback_provider": "claude", "fallback_api_key": "sk-fb",
        }
        content, usage = _call_llm("sys", "user", config)
        self.assertIsNone(content)
        self.assertEqual(mock_call.call_count, 1)


# ═══════════════════════════════════════════════════════════════
#  R-087: 熔断器冷却恢复测试（半开探测）
# ═══════════════════════════════════════════════════════════════


class TestCircuitBreakerRecovery(unittest.TestCase):
    """测试熔断器熔断 → 冷却 → 半开 → 恢复全流程。"""

    def setUp(self) -> None:
        import src.python.llm.circuit_breaker as _cb
        _cb._circuit_failures.clear()
        _cb._circuit_open_until.clear()

    def test_full_recovery_cycle(self):
        """熔断 → 冷却 → 半开(返回False) → 成功后关闭熔断。"""
        url = "https://api.test.com/v1/chat"
        from src.python.llm.circuit_breaker import (
            _CIRCUIT_BREAKER_RECOVERY,
            _cb_is_open, _cb_record_failure, _cb_record_success,
            _circuit_open_until,
        )

        # 所有 time.time 操作在同一 patch 下, 保证时间线一致
        with patch("src.python.llm.circuit_breaker.time.time") as mock_time:
            mock_time.return_value = 1000.0

            # 1. 连续失败 3 次 → 熔断开启
            for _ in range(3):
                _cb_record_failure(url)
            self.assertTrue(_cb_is_open(url))

            # 2. 快进到冷却结束后 → 半开（_cb_is_open 返回 False）
            mock_time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY + 1
            self.assertFalse(_cb_is_open(url))
            # 冷却结束 → _circuit_open_until 中已清除 key
            self.assertNotIn("api.test.com", _circuit_open_until)

            # 3. 半开后成功调用 → 熔断关闭
            _cb_record_success(url)
            self.assertFalse(_cb_is_open(url))

    def test_recovery_before_timeout_still_open(self):
        """冷却期内熔断仍开启。"""
        url = "https://api.test.com/v1"
        from src.python.llm.circuit_breaker import (
            _CIRCUIT_BREAKER_RECOVERY,
            _cb_is_open, _cb_record_failure,
        )

        with patch("src.python.llm.circuit_breaker.time.time") as mock_time:
            mock_time.return_value = 1000.0

            for _ in range(3):
                _cb_record_failure(url)

            # 冷却期内（快进 30s，不到 60s）
            mock_time.return_value = 1000.0 + 30
            self.assertTrue(_cb_is_open(url))

    def test_recovery_after_exact_timeout(self):
        """冷却时间刚好到达 → 半开（返回 False）。"""
        url = "https://api.test.com/v1"
        from src.python.llm.circuit_breaker import (
            _CIRCUIT_BREAKER_RECOVERY,
            _cb_is_open, _cb_record_failure,
        )

        with patch("src.python.llm.circuit_breaker.time.time") as mock_time:
            mock_time.return_value = 1000.0

            for _ in range(3):
                _cb_record_failure(url)

            # 刚好冷却期满
            mock_time.return_value = 1000.0 + _CIRCUIT_BREAKER_RECOVERY
            self.assertFalse(_cb_is_open(url))

    def test_multiple_endpoints_independent(self):
        """不同 endpoint 的熔断状态独立。"""
        url_a = "https://api.a.com/v1"
        url_b = "https://api.b.com/v1"
        from src.python.llm.circuit_breaker import (
            _cb_is_open, _cb_record_failure,
        )

        for _ in range(3):
            _cb_record_failure(url_a)

        self.assertTrue(_cb_is_open(url_a))
        self.assertFalse(_cb_is_open(url_b))


# ═══════════════════════════════════════════════════════════════
#  R-089: LLM content_filter 空返回安抚重试测试
# ═══════════════════════════════════════════════════════════════


class TestContentFilterRecovery(unittest.TestCase):
    """测试 _call_llm 在 API 返回空内容时的安抚重试机制。"""

    @patch("src.python.llm.api._call_single_provider")
    def test_empty_content_triggers_retry(self, mock_call):
        """API 返回空字符串 → 追加安抚指令重试一次。"""
        mock_call.side_effect = [
            ("", {"input_tokens": 100}),      # 第一次：空内容
            ("retry result", {"input_tokens": 200}),  # 第二次：安抚后成功
        ]
        config = {"provider": "claude", "api_key": "sk-test"}
        content, usage = _call_llm("system prompt", "user content", config)
        # 应返回安抚重试后的结果
        self.assertEqual(content, "retry result")
        self.assertEqual(mock_call.call_count, 2)

        # 验证第二次调用 system_prompt 包含安抚指令
        from src.python.llm.api import _CONTENT_FILTER_RECOVERY

        second_call_system = mock_call.call_args_list[1][0][1]  # system_prompt arg
        self.assertIn("注意：请确保你的回答包含实质性的分析内容", second_call_system)

    @patch("src.python.llm.api._call_single_provider")
    def test_empty_content_then_still_empty(self, mock_call):
        """安抚重试后仍为空 → 尝试 fallback provider。"""
        mock_call.side_effect = [
            ("", {"input_tokens": 10}),   # 主 provider 空
            ("", {"input_tokens": 20}),   # 安抚重试仍空
            ("fb ok", {"prompt_tokens": 5}),  # fallback 成功
        ]
        config = {
            "provider": "claude", "api_key": "sk-main",
            "fallback_provider": "openai", "fallback_api_key": "sk-fb",
        }
        content, usage = _call_llm("sys", "user", config)
        self.assertEqual(content, "fb ok")
        self.assertEqual(mock_call.call_count, 3)

    @patch("src.python.llm.api._call_single_provider")
    def test_empty_content_no_fallback_returns_none(self, mock_call):
        """安抚重试仍空且无 fallback → (None, None)。"""
        mock_call.return_value = ("", {"input_tokens": 10})
        config = {"provider": "claude", "api_key": "sk-test"}
        content, usage = _call_llm("sys", "user", config)
        self.assertIsNone(content)
        # 被调用 2 次（原始 + 安抚重试）
        self.assertEqual(mock_call.call_count, 2)

    @patch("src.python.llm.api._call_single_provider")
    def test_normal_content_no_retry(self, mock_call):
        """正常返回内容 → 不触发安抚重试。"""
        mock_call.return_value = ("正常内容", {"input_tokens": 100})
        config = {"provider": "claude", "api_key": "sk-test"}
        content, usage = _call_llm("sys", "user", config)
        self.assertEqual(content, "正常内容")
        self.assertEqual(mock_call.call_count, 1)

    @patch("src.python.llm.api._call_single_provider")
    def test_none_from_provider_triggers_fallback_not_retry(self, mock_call):
        """provider 返回 None（格式异常）→ 不触发安抚重试，直接走 fallback。"""
        mock_call.side_effect = [
            (None, None),           # 主 provider 格式异常
            ("fb result", None),    # fallback 成功
        ]
        config = {
            "provider": "claude", "api_key": "sk-main",
            "fallback_provider": "openai", "fallback_api_key": "sk-fb",
        }
        content, usage = _call_llm("sys", "user", config)
        self.assertEqual(content, "fb result")
        # 只调用了 2 次（主 + fallback），没有安抚重试
        self.assertEqual(mock_call.call_count, 2)


if __name__ == "__main__":
    unittest.main()
