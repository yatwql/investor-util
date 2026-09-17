"""链路凭据预检单元测试（常规开关 `datasource_credential_ready`，默认开启）。

覆盖：开关开启且凭据缺失 → **跳过该 provider 并落到下一链路**、可读原因进入
失败诊断、**不计入熔断失败计数**；补上凭据 → 该 provider 正常参与；开关关闭
→ 预检不发生（行为与未引入本机制时一致）；历史 chain 的遍历循环同样受控。

注：生产声明表为空（全部免费源），故用合成声明验证机制。

运行：
  pytest src/test/unit/fetcher/test_credential_gate.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.python.config import features
from src.python.core.datasource_credential import CredentialSpec, register_credential_spec
from src.python.fetcher.chain import (
    FailureDiagnostics,
    _try_providers,
    fetch_with_fallback,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

_ENV_VAR = "INVESTOR_UTIL_GATE_KEY"
_FLAG = "datasource_credential_ready"


def _fake_registry() -> MagicMock:
    """未被熔断的注册表替身（记录 record_failure 调用以便断言）。"""
    reg = MagicMock()
    reg.is_circuit_broken.return_value = False
    return reg


def _enabled(monkeypatch) -> None:
    monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)


class TestFallbackChainCredentialGate:
    """fetch_with_fallback：凭据缺失的 provider 主动跳过。"""

    def _run(self, monkeypatch, diagnostics=None, cache_key="_gate_test_1"):
        calls: list[str] = []

        def _tencent(**kwargs):
            calls.append("tencent")
            return {"name": "从腾讯取到"}

        def _eastmoney(**kwargs):
            calls.append("eastmoney")
            return {"name": "从东方财富取到"}

        provider_fn_map = {
            "tencent": ("腾讯财经", _tencent),
            "eastmoney": ("东方财富", _eastmoney),
        }
        with patch("src.python.fetcher.chain.get_registry", return_value=_fake_registry()):
            result = fetch_with_fallback("price", provider_fn_map, cache_key, 0.0, diagnostics=diagnostics)
        return result, calls

    def test_missing_credential_skips_provider_and_falls_through(self, monkeypatch):
        """缺凭据 → 不调用该 provider，落到下一链路，且不崩溃。"""
        _enabled(monkeypatch)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("tencent", "腾讯财经", _ENV_VAR, "https://example.com/apply"))

        diag = FailureDiagnostics()
        result, calls = self._run(monkeypatch, diag)

        assert calls == ["eastmoney"], "缺凭据的 provider 不应被调用"
        assert result == {"name": "从东方财富取到"}
        # 可读原因进入「错误即 UX」通道（供数据源可用性矩阵上屏）
        assert diag.has_failure
        assert "腾讯财经" in diag.summary()
        assert _ENV_VAR in diag.summary()

    def test_missing_credential_not_counted_as_circuit_failure(self, monkeypatch):
        """凭据缺失是配置级问题 → 不计入熔断失败计数。"""
        _enabled(monkeypatch)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("tencent", "腾讯财经", _ENV_VAR))

        reg = _fake_registry()
        provider_fn_map = {"tencent": ("腾讯财经", lambda **kw: {"ok": 1})}
        with patch("src.python.fetcher.chain.get_registry", return_value=reg):
            fetch_with_fallback("price", provider_fn_map, "_gate_test_2", 0.0)

        reg.record_failure.assert_not_called()

    def test_credential_present_provider_participates(self, monkeypatch):
        """补上凭据 → 该 provider 正常参与（预检不再触发）。"""
        _enabled(monkeypatch)
        monkeypatch.setenv(_ENV_VAR, "key-value")
        register_credential_spec(CredentialSpec("tencent", "腾讯财经", _ENV_VAR))

        result, calls = self._run(monkeypatch, cache_key="_gate_test_3")
        assert calls == ["tencent"]
        assert result == {"name": "从腾讯取到"}

    def test_flag_off_precheck_not_applied(self, monkeypatch):
        """开关关闭 → 缺凭据也照常尝试（行为与未引入本机制时一致）。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, False)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("tencent", "腾讯财经", _ENV_VAR))

        result, calls = self._run(monkeypatch, cache_key="_gate_test_4")
        assert calls == ["tencent"]
        assert result == {"name": "从腾讯取到"}

    def test_undeclared_source_probed_normally_when_enabled(self, monkeypatch):
        """开关开启但该源未声明凭据 → 不跳过（声明即数据，未声明即免费源）。"""
        _enabled(monkeypatch)
        result, calls = self._run(monkeypatch, cache_key="_gate_test_5")
        assert calls == ["tencent"]


class TestHistoryChainCredentialGate:
    """_try_providers（历史走势遍历）：同一判定，避免该路径漏网。"""

    def test_missing_credential_skips_in_history_loop(self, monkeypatch):
        """历史 chain 中缺凭据的 provider 同样跳过，不记录失败。"""
        _enabled(monkeypatch)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("tencent", "腾讯财经", _ENV_VAR))

        reg = _fake_registry()
        diag = FailureDiagnostics()
        with patch(
            "src.python.fetcher.chain._call_history_provider",
            return_value=[{"date": "2026-09-10", "close": 1.0}],
        ) as mock_call:
            data = _try_providers(["tencent", "sina"], reg, "history_index", "sh000001", 30, None, diagnostics=diag)

        assert data, "应落到下一链路并取到数据"
        assert mock_call.call_args[0][0] == "sina", "缺凭据的 tencent 不应被调用"
        reg.record_failure.assert_not_called()
        assert _ENV_VAR in diag.summary()

    def test_flag_off_history_loop_unchanged(self, monkeypatch):
        """开关关闭 → 历史 chain 首个 provider 照常被调用。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, False)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("tencent", "腾讯财经", _ENV_VAR))

        reg = _fake_registry()
        with patch("src.python.fetcher.chain._call_history_provider", return_value=[{"close": 1.0}]) as mock_call:
            data = _try_providers(["tencent", "sina"], reg, "history_index", "sh000001", 30, None)

        assert data
        assert mock_call.call_args[0][0] == "tencent"
