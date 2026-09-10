"""数据源凭据声明与就绪判定单元测试（实验功能 `datasource_credential_ready`）。

覆盖：声明注册、就绪判定（未声明 / 未设 / 空白 / 已设）、可读指引措辞、
就绪矩阵结构、开关判定、凭据值不外泄。

注：本模块当前**没有真实需要凭据的数据源**（全部免费源），故测试用**合成声明**
证明机制可用——不为了演示而把假数据源写进生产注册表。

运行：
  pytest src/test/unit/core/test_datasource_credential.py -v
"""

from __future__ import annotations

import pytest

from src.python.config import features
from src.python.core.datasource_credential import (
    CREDENTIAL_SPECS,
    CredentialSpec,
    credential_hint,
    credential_readiness,
    credential_ready_enabled,
    missing_credential,
    register_credential_spec,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

_ENV_VAR = "INVESTOR_UTIL_TEST_SOURCE_KEY"


def _spec(**overrides) -> CredentialSpec:
    base = {
        "source_id": "example",
        "display_name": "示例财经",
        "env_var": _ENV_VAR,
        "apply_url": "https://example.com/apply",
    }
    base.update(overrides)
    return CredentialSpec(**base)


class TestDeclarationRegistry:
    """声明表：生产环境为空（全部免费源），登记后可查。"""

    def test_production_registry_is_empty(self):
        """如实呈现：当前无任何数据源需要凭据。"""
        assert CREDENTIAL_SPECS == {}

    def test_register_then_lookup(self):
        """登记后可按 source_id 查到同一条声明。"""
        spec = _spec()
        register_credential_spec(spec)
        assert CREDENTIAL_SPECS["example"] is spec

    def test_register_same_id_last_wins(self):
        """同 source_id 重复登记以最后一次为准（不静默留两条）。"""
        register_credential_spec(_spec(display_name="旧名"))
        register_credential_spec(_spec(display_name="新名"))
        assert CREDENTIAL_SPECS["example"].display_name == "新名"
        assert len(CREDENTIAL_SPECS) == 1


class TestMissingCredential:
    """就绪判定：只有「已声明需凭据且当前缺失」才返回声明。"""

    def test_undeclared_source_needs_no_credential(self):
        """未声明 → None（无需凭据，调用方照常尝试）。"""
        assert missing_credential("tencent") is None

    def test_declared_but_env_unset_is_missing(self, monkeypatch):
        """已声明且环境变量未设 → 返回声明（调用方据此跳过）。"""
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(_spec())
        assert missing_credential("example") is not None

    def test_blank_env_counts_as_missing(self, monkeypatch):
        """空白串视为缺失 —— 防「设了空值以为配好了」。"""
        monkeypatch.setenv(_ENV_VAR, "   ")
        register_credential_spec(_spec())
        assert missing_credential("example") is not None

    def test_set_env_is_ready(self, monkeypatch):
        """环境变量已设 → None（就绪，不跳过）。"""
        monkeypatch.setenv(_ENV_VAR, "abc123")
        register_credential_spec(_spec())
        assert missing_credential("example") is None


class TestCredentialHint:
    """可读指引：含数据源名、变量名与申请地址（错误即 UX）。"""

    def test_hint_contains_name_var_and_url(self):
        hint = credential_hint(_spec())
        assert "示例财经" in hint
        assert _ENV_VAR in hint
        assert "https://example.com/apply" in hint

    def test_hint_without_url_or_note(self):
        """无申请地址/备注时不出现空占位（不产生「申请地址：」空尾巴）。"""
        hint = credential_hint(_spec(apply_url="", note=""))
        assert "申请地址" not in hint
        assert _ENV_VAR in hint


class TestCredentialReadiness:
    """就绪矩阵：供体检与健康检查复用的结构化输出。"""

    def test_empty_registry_gives_empty_matrix(self):
        assert credential_readiness() == []

    def test_missing_row_carries_hint_not_value(self, monkeypatch):
        """缺失行：ready=False、message 为可读指引；**不含凭据值**。"""
        monkeypatch.setenv(_ENV_VAR, "super-secret-value")
        register_credential_spec(_spec())
        # 先就绪（值已设），再清空以复现缺失
        assert credential_readiness()[0]["ready"] is True
        monkeypatch.delenv(_ENV_VAR, raising=False)

        row = credential_readiness()[0]
        assert row["source_id"] == "example"
        assert row["display_name"] == "示例财经"
        assert row["required"] is True
        assert row["ready"] is False
        assert row["env_var"] == _ENV_VAR
        assert _ENV_VAR in row["message"]

    def test_secret_value_never_appears_in_matrix(self, monkeypatch):
        """即便凭据已设，输出也只报「变量名 + 已就绪」，绝不回显值。"""
        monkeypatch.setenv(_ENV_VAR, "super-secret-value")
        register_credential_spec(_spec())
        for row in credential_readiness():
            assert "super-secret-value" not in str(row)

    def test_matrix_sorted_by_source_id(self):
        """矩阵按 source_id 排序，两次调用输出稳定。"""
        for sid in ("zeta", "alpha", "mid"):
            register_credential_spec(_spec(source_id=sid, display_name=sid))
        assert [r["source_id"] for r in credential_readiness()] == ["alpha", "mid", "zeta"]


class TestReadyEnabled:
    """开关判定：开关名收敛在模块内，默认关闭。"""

    def test_default_disabled(self):
        assert credential_ready_enabled() is False

    def test_enabled_when_flag_set(self, monkeypatch):
        monkeypatch.setitem(features.FEATURE_FLAGS, "datasource_credential_ready", True)
        assert credential_ready_enabled() is True
