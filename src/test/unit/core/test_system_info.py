"""核心状态组装 core.system_info：展示原语单源 + build_system_info 结构。

覆盖：endpoint 简化 / 熔断展示（含「默认」语义差异）/ 策略与优先级标签 /
匿名化中文标签 / credentials_ref 回填 / 模型路由行 / build 的键结构与
配置读取失败兜底（就绪保守置 False）。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.core.system_info import (
    anon_mode_label,
    build_system_info,
    circuit_display,
    model_route_labels,
    priority_display,
    resolve_provider_credentials,
    simplify_endpoint,
    strategy_label,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestDisplayPrimitives:
    """曾在渠道各持一份的展示规则，现为单点实现。"""

    def test_simplify_endpoint_takes_host(self):
        assert simplify_endpoint("https://api.anthropic.com/v1/messages") == "api.anthropic.com"

    def test_simplify_endpoint_passthrough(self):
        assert simplify_endpoint("默认") == "默认"
        assert simplify_endpoint("") == "默认"
        assert simplify_endpoint("not-a-url") == "not-a-url"

    def test_circuit_display_default_semantics(self):
        # flat 模式：字面「默认」视为无端点；多链模式：仍查熔断状态
        assert circuit_display("默认", default_as_none=True) == "—"
        assert circuit_display("", default_as_none=True) == "—"
        assert circuit_display("") == "—"
        with patch("src.python.llm.circuit_breaker.get_circuit_status", return_value="熔断中"):
            assert circuit_display("默认") == "熔断中"
            assert circuit_display("https://x/y") == "熔断中"

    def test_labels(self):
        assert strategy_label("priority") == "优先级排序"
        assert strategy_label("unknown_raw") == "unknown_raw"
        assert priority_display(1) == "1"
        assert priority_display(None) == "99（默认）"
        assert anon_mode_label("off") == "关闭"
        assert anon_mode_label("full_anonymous") == "完全匿名"
        assert anon_mode_label("x") == "x"

    def test_resolve_provider_credentials_backfills(self):
        creds = {"ref-1": {"model": "gpt-4o", "endpoint": "https://api.openai.com/v1"}}
        model, endpoint = resolve_provider_credentials({"credentials_ref": "ref-1"}, creds)
        assert model == "gpt-4o"
        assert endpoint == "https://api.openai.com/v1"
        # entry 内联优先，不被凭据表覆盖
        model, endpoint = resolve_provider_credentials(
            {"credentials_ref": "ref-1", "model": "inline", "endpoint": "https://e"}, creds
        )
        assert (model, endpoint) == ("inline", "https://e")

    def test_model_route_labels_use_effective_model(self):
        labels = model_route_labels({"model": "base-model", "model_news_correlation": "special-model"})
        # 每个可见模块一行「显示名=生效模型」（覆盖与模块清单一致，不写死条数）
        from src.python.core.registry import visible_llm_module_names

        assert len(labels) == len(visible_llm_module_names())
        assert any(label.startswith("财经新闻热点与持仓关联分析=special-model") for label in labels)


class TestBuildSystemInfo:
    """build：键结构稳定、未配置兜底、配置读取失败保守呈现。"""

    def test_unconfigured_defaults(self, monkeypatch):
        monkeypatch.setattr("src.python.config.get_config", lambda: {})
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: None)
        info = build_system_info()
        assert info["llm"] == {"configured": False}
        assert info["app_version"]
        assert info["anonymization"] == "关闭"
        expected_keys = {
            "app_version",
            "machine_ip",
            "holdings_dir",
            "holdings_filename",
            "output_dir",
            "news_top_count",
            "holdings_ready",
            "holdings_mtime",
            "anonymization",
            "privacy_shown",
            "doctor_enabled",
            "llm",
        }
        assert expected_keys <= set(info)

    def test_config_read_failure_keeps_not_ready(self, monkeypatch):
        def _boom():
            raise RuntimeError("config read failed")

        monkeypatch.setattr("src.python.config.get_config", _boom)
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: None)
        info = build_system_info()
        assert info["holdings_dir"] == "未设置"
        assert info["holdings_ready"] is False
        assert info["llm"] == {"configured": False}

    def test_flat_mode_structure(self, monkeypatch):
        monkeypatch.setattr("src.python.config.get_config", lambda: {})
        monkeypatch.setattr(
            "src.python.config.get_llm_config",
            lambda: {
                "provider": "claude",
                "api_key": "sk-test",
                "model": "claude-sonnet-4-6",
                "endpoint": "https://api.x/v1",
            },
        )
        monkeypatch.setattr("src.python.core.registry.get_llm_module_names", lambda: {"global_macro": "全球政经局势"})
        with patch("src.python.llm.circuit_breaker.get_circuit_status", return_value="正常"):
            info = build_system_info()
        llm = info["llm"]
        assert llm["configured"] is True
        assert llm["mode"] == "flat"
        assert llm["endpoint_display"] == "api.x"
        assert llm["circuit"] == "正常"
        assert isinstance(llm["route"], list)


class TestLlmStatusSingleSource:
    """llm_status — LLM 配置状态单源（三渠道状态展示共用判定树）。"""

    def test_none_config_reports_unconfigured(self, monkeypatch):
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: None)
        from src.python.core.system_info import llm_status

        assert llm_status() == {"configured": False}

    def test_incomplete_flat_reports_unconfigured(self, monkeypatch):
        """有 api_key 但缺 provider（flat 不完整）→ 未配置。"""
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: {"api_key": "sk-x"})
        from src.python.core.system_info import llm_status

        assert llm_status()["configured"] is False

    def test_flat_configured_contract_keys(self, monkeypatch):
        monkeypatch.setattr(
            "src.python.config.get_llm_config",
            lambda: {"api_key": "sk-x", "provider": "claude", "model": "m", "endpoint": "https://api.x/v1"},
        )
        from src.python.core.system_info import llm_status

        llm = llm_status()
        assert llm["configured"] is True
        assert llm["mode"] == "flat"
        assert {"provider", "model", "endpoint", "endpoint_display", "circuit", "route"} <= set(llm)

    def test_multi_chain_contract(self, monkeypatch):
        monkeypatch.setattr(
            "src.python.config.get_llm_config",
            lambda: {"_provider_list": [{"name": "a", "provider": "claude", "priority": 10}], "_strategy": "priority"},
        )
        from src.python.core.system_info import llm_status

        llm = llm_status()
        assert llm["configured"] is True
        assert llm["mode"] == "multi"
        assert len(llm["providers"]) == 1
        assert {"strategy", "providers", "preferred"} <= set(llm)

    def test_build_embeds_same_status(self, monkeypatch):
        """build_system_info 的 llm 段与 llm_status() 逐字相等（单源关系，非镜像组装）。"""
        monkeypatch.setattr("src.python.config.get_llm_config", lambda: {"api_key": "sk-x", "provider": "claude"})
        from src.python.core.system_info import build_system_info, llm_status

        assert build_system_info()["llm"] == llm_status()
