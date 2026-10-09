"""测试 skeleton.py 辅助函数（纯逻辑函数，无 API 调用）。"""

import unittest

from src.python.llm.skeleton import is_llm_module_enabled
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


class TestIsLlmModuleEnabled(unittest.TestCase):
    """is_llm_module_enabled — 检查 LLM 模块启用状态。"""

    def test_none_config_disabled(self):
        self.assertFalse(is_llm_module_enabled(None, "global_macro"))

    def test_empty_enabled_map_default_true(self):
        config = {"enabled_llm": {}}
        self.assertTrue(is_llm_module_enabled(config, "global_macro"))

    def test_missing_enabled_llm_default_true(self):
        config = {"api_key": "sk-xxx"}
        self.assertTrue(is_llm_module_enabled(config, "global_macro"))

    def test_explicitly_enabled(self):
        config = {"enabled_llm": {"global_macro": True}}
        self.assertTrue(is_llm_module_enabled(config, "global_macro"))

    def test_explicitly_disabled(self):
        config = {"enabled_llm": {"global_macro": False}}
        self.assertFalse(is_llm_module_enabled(config, "global_macro"))

    def test_different_module_not_affected(self):
        config = {"enabled_llm": {"health_check": False}}
        self.assertTrue(is_llm_module_enabled(config, "global_macro"))
        self.assertFalse(is_llm_module_enabled(config, "health_check"))

    def test_unknown_module_defaults_true(self):
        config = {"enabled_llm": {"global_macro": True}}
        self.assertTrue(is_llm_module_enabled(config, "unknown_module"))

    def test_enabled_map_none(self):
        config = {"enabled_llm": None}
        self.assertTrue(is_llm_module_enabled(config, "global_macro"))


class TestHandleTruncation(unittest.TestCase):
    """_handle_truncation — 截断检测与 usage 传递。

    核心契约：非截断场景必须透传调用链的 usage dict，
    否则 _finalize_and_cache 无法记录 per_module 用量和页脚 Token 信息。
    """

    def test_not_truncated_preserves_usage(self):
        """结果不含截断标记 → 原样返回 (result, usage)。"""
        from src.python.llm.skeleton import _handle_truncation

        result = "正常内容"
        usage = {"input_tokens": 100, "output_tokens": 200}
        r, u = _handle_truncation(result, usage, 4096, "", "", {}, 60, None, "", None, "")
        self.assertEqual(r, result)
        self.assertIs(u, usage)  # 同一对象，非 None

    def test_none_result_preserves_usage(self):
        """result 为 None 时同样保留 usage（不走截断路径）。"""
        from src.python.llm.skeleton import _handle_truncation

        usage = {"input_tokens": 50, "output_tokens": 80}
        r, u = _handle_truncation(None, usage, 4096, "", "", {}, 60, None, "", None, "")
        self.assertIsNone(r)
        self.assertIs(u, usage)

    def test_empty_result_preserves_usage(self):
        """空白字符串不走截断路径，保留 usage。"""
        from src.python.llm.skeleton import _handle_truncation

        usage = {"input_tokens": 10, "output_tokens": 20}
        r, u = _handle_truncation("", usage, 4096, "", "", {}, 60, None, "", None, "")
        self.assertEqual(r, "")
        self.assertIs(u, usage)

    def test_exhausted_retry_log_names_config_field_and_both_values(self):
        """自动放大仍截断 → 日志点名 config_field 与「当前 → 已试」两个值。"""
        from unittest.mock import patch

        from src.python.llm.api_base import TRUNCATION_MARKER
        from src.python.llm.skeleton import _handle_truncation

        truncated = f"<p>{TRUNCATION_MARKER}</p>"
        with patch(
            "src.python.llm.skeleton.call_llm",
            return_value=(truncated, {"output_tokens": 9}, {"name": "kimi-main"}),
        ):
            with self.assertLogs(level="WARNING") as cm:
                _handle_truncation(
                    truncated,
                    {},
                    4096,
                    "sys",
                    "usr",
                    {},
                    60,
                    None,
                    "max_tokens_global_macro",
                    None,
                    "",
                )
        text = "\n".join(cm.output)
        self.assertIn("max_tokens_global_macro：当前 4096 → 已试 6144", text)
        self.assertIn("请手动增大 llm_settings.json 的 max_tokens_global_macro", text)


class TestHandleCacheHit(unittest.TestCase):
    """_handle_cache_hit — 缓存命中处理（通过 _generate_llm_content 间接测试）。

    注：此为集成验证的基础——_handle_cache_hit 内部依赖 _record_per_module /
    _strip_token_line / _extract_model_from_cached，这些在 test_llm.py 中有覆盖。
    """

    def test_module_imports_successfully(self):
        """验证 skeleton.py 模块导入正常，无语法/导入错误。"""
        from src.python.llm import skeleton

        self.assertTrue(hasattr(skeleton, "_handle_cache_hit"))
        self.assertTrue(hasattr(skeleton, "_finalize_and_cache"))
        self.assertTrue(hasattr(skeleton, "_handle_truncation"))


class TestMaxTokensOverride(unittest.TestCase):
    """max_tokens_override — 显式覆盖优先于模块级 max_tokens_{module_key} 配置。

    辩论模式 per_call_max_tokens 若仅以 max_tokens_default 传入，会被
    _run_standard_mode 的 ``llm_config.get("max_tokens_{module_key}")`` 覆盖
    （继承 expert_review 宽松上限），显式 override 才能限定每阶段输出上限。
    """

    def _capture_max_tokens(self, llm_config: dict, override: int | None, module_max: int):
        """调用 _run_standard_mode，返回 generate_llm_content 实际收到的 max_tokens。"""
        from unittest.mock import patch

        from src.python.llm import skeleton

        captured: dict = {}

        def fake_generate_llm_content(*args, **kwargs):
            captured["max_tokens"] = kwargs.get("max_tokens")
            return (None, False)

        with patch.object(skeleton, "generate_llm_content", side_effect=fake_generate_llm_content):
            skeleton._run_standard_mode(
                llm_config=llm_config,
                module_key="expert_review",
                force=True,
                http_client=None,
                fingerprint_fn=lambda: "fp",
                system_prompt_default="sys",
                prompt_builder=lambda: "user",
                max_tokens_default=8192,
                max_tokens_override=override,
                timeout_default=90,
                output_brief_limit=300,
            )
        return captured.get("max_tokens")

    def test_override_wins_over_module_level_config(self):
        """显式 override 存在时优先使用（辩论 per_call_max_tokens 生效）。"""
        result = self._capture_max_tokens(
            llm_config={"max_tokens_expert_review": 24000},
            override=4096,
            module_max=24000,
        )
        self.assertEqual(result, 4096)

    def test_override_none_falls_back_to_module_config(self):
        """无 override 时回退模块级 max_tokens_{module_key}（兼容既有行为）。"""
        result = self._capture_max_tokens(
            llm_config={"max_tokens_expert_review": 24000},
            override=None,
            module_max=24000,
        )
        self.assertEqual(result, 24000)

    def test_override_none_falls_back_to_default_when_config_missing(self):
        """无 override 且模块级配置缺失时回退 max_tokens_default。"""
        result = self._capture_max_tokens(
            llm_config={},
            override=None,
            module_max=8192,
        )
        self.assertEqual(result, 8192)


class TestFullFailRetry(unittest.TestCase):
    """全链路失败后的延迟整链重试（瞬时故障自愈，终态失败不重试）。"""

    @staticmethod
    def _run(llm_config, call_llm_mock, get_reason_mock, sleep_mock):
        from unittest.mock import patch

        from src.python.llm import skeleton

        with (
            patch.object(skeleton, "call_llm", call_llm_mock),
            patch.object(skeleton, "_get_last_llm_failure", get_reason_mock),
            patch.object(skeleton, "_handle_truncation", side_effect=lambda r, u, *a, **k: (r, u)),
            patch.object(skeleton, "_finalize_and_cache", return_value=("OUT", True)),
            patch.object(skeleton.time, "sleep", sleep_mock),
        ):
            return skeleton._execute_llm_with_finalize(
                "sys",
                "usr",
                llm_config,
                60,
                None,
                4096,
                "cfg_field",
                None,
                None,
                "ut_full_fail_key",
                "",
                False,
            )

    def test_transient_failure_retries_once_after_delay_and_succeeds(self):
        """网络类全挂 → 延迟 llm_full_fail_retry_delay 后整链重试一次并成功。"""
        from unittest.mock import Mock

        from src.python.llm.api_base import FAIL_REASON_NETWORK_ERROR

        calls = Mock(side_effect=[(None, None, None), ("好", {}, {"name": "p", "model": "m"})])
        reason = Mock(return_value=FAIL_REASON_NETWORK_ERROR)
        sleep = Mock()

        result, ok = self._run({"llm_full_fail_retry_delay": 5}, calls, reason, sleep)

        self.assertEqual(result, "OUT")
        self.assertTrue(ok)
        self.assertEqual(calls.call_count, 2)
        sleep.assert_called_once_with(5.0)

    def test_quota_failure_does_not_retry(self):
        """配额耗尽属终态（窗口滚动）→ 不进入延迟重试，单次即返回失败。"""
        from unittest.mock import Mock

        from src.python.llm.api_base import FAIL_REASON_QUOTA_EXCEEDED

        calls = Mock(return_value=(None, None, None))
        reason = Mock(return_value=FAIL_REASON_QUOTA_EXCEEDED)
        sleep = Mock()

        result, ok = self._run({"llm_full_fail_retry_delay": 5}, calls, reason, sleep)

        self.assertIsNone(result)
        self.assertFalse(ok)
        self.assertEqual(calls.call_count, 1)
        sleep.assert_not_called()

    def test_zero_delay_retries_immediately_without_sleep(self):
        """llm_full_fail_retry_delay=0（显式关闭等待）→ 重试但不 sleep。"""
        from unittest.mock import Mock

        from src.python.llm.api_base import FAIL_REASON_TIMEOUT

        calls = Mock(side_effect=[(None, None, None), ("好", {}, {"name": "p", "model": "m"})])
        reason = Mock(return_value=FAIL_REASON_TIMEOUT)
        sleep = Mock()

        result, ok = self._run({"llm_full_fail_retry_delay": 0}, calls, reason, sleep)

        self.assertEqual(result, "OUT")
        self.assertTrue(ok)
        self.assertEqual(calls.call_count, 2)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
