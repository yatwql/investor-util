"""check-sources 凭据预检与就绪摘要单元测试（常规开关 `datasource_credential_ready`，默认开启）。

覆盖：缺凭据的检查项**不发起探测**、产出跳过态（`⏭️`/`_SKIP`）并可读原因上屏、
**不影响退出码**；开关关闭时输出与未引入本机制时一致；就绪摘要行随开关与声明表变化。

运行：
  pytest src/test/unit/core/test_check_sources_credential.py -v
"""

from __future__ import annotations

from unittest import mock

import pytest

import src.python.core.check_sources as cs
from src.python.config import features
from src.python.core.datasource_credential import CredentialSpec, register_credential_spec

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

_FLAG = "datasource_credential_ready"
_ENV_VAR = "INVESTOR_UTIL_CHECK_KEY"


def _checks_with_probe(probe_calls: list[str]):
    """两个检查项：其一（src_need）由用例声明凭据，其二（src_free）始终免费。"""

    def _need():
        probe_calls.append("need")
        return cs._OK, 5.0, "5ms 正常"

    def _free():
        probe_calls.append("free")
        return cs._OK, 6.0, "6ms 正常"

    return [
        ("src_need", "需凭据源", "行情", _need),
        ("src_free", "免费源", "新闻", _free),
    ]


class TestCredentialPrecheck:
    """凭据缺失的检查项不发探测，直接产出跳过态。"""

    def test_missing_credential_skips_probe(self, monkeypatch):
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("src_need", "需凭据源", _ENV_VAR, "https://example.com/apply"))

        probe_calls: list[str] = []
        with mock.patch.object(cs, "_checks", _checks_with_probe(probe_calls)):
            results = cs.run_health_checks(max_timeout=5.0)

        assert probe_calls == ["free"], "缺凭据的源不应被探测"
        by_name = {r["name"]: r for r in results}
        assert by_name["需凭据源"]["skipped"] is True
        assert by_name["需凭据源"]["ok"] is False
        assert _ENV_VAR in by_name["需凭据源"]["message"]
        assert "免费源" not in by_name["需凭据源"]["message"]
        assert "skipped" not in by_name["免费源"]

    def test_present_credential_probes_normally(self, monkeypatch):
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)
        monkeypatch.setenv(_ENV_VAR, "key-value")
        register_credential_spec(CredentialSpec("src_need", "需凭据源", _ENV_VAR))

        probe_calls: list[str] = []
        with mock.patch.object(cs, "_checks", _checks_with_probe(probe_calls)):
            results = cs.run_health_checks(max_timeout=5.0)

        assert sorted(probe_calls) == ["free", "need"]
        assert all(r["ok"] for r in results)

    def test_flag_off_output_identical_to_baseline(self, monkeypatch):
        """开关关闭 → 预检不发生，输出与未引入本机制时逐字一致。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, False)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("src_need", "需凭据源", _ENV_VAR))

        probe_calls: list[str] = []
        with mock.patch.object(cs, "_checks", _checks_with_probe(probe_calls)):
            results = cs.run_health_checks(max_timeout=5.0)

        assert sorted(probe_calls) == ["free", "need"]
        assert all("skipped" not in r for r in results)


class TestExitCodeUnaffected:
    """跳过项是配置级问题 → 不计入 err/warn，退出码不受影响。"""

    def _run_cli(self, monkeypatch, capsys):
        probe_calls: list[str] = []
        with mock.patch.object(cs, "_checks", _checks_with_probe(probe_calls)):
            with pytest.raises(SystemExit) as exc:
                cs.run_check_sources()
        return exc.value.code, capsys.readouterr().out

    def test_all_skipped_exits_zero(self, monkeypatch, capsys):
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("src_need", "需凭据源", _ENV_VAR))

        code, out = self._run_cli(monkeypatch, capsys)
        assert code == 0, "凭据跳过不得让 check-sources 判失败"
        assert cs._SKIP in out
        assert "凭据就绪" in out

    def test_flag_off_no_readiness_line(self, monkeypatch, capsys):
        """开关关闭 → 不追加就绪摘要行（输出面与现状一致）。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, False)
        code, out = self._run_cli(monkeypatch, capsys)
        assert code == 0
        assert "凭据就绪" not in out


class TestCredentialSummary:
    """就绪摘要行：无声明报「均无需凭据」，有声明报就绪比例。"""

    def test_summary_without_declarations(self):
        assert "均无需凭据" in cs._credential_summary()
        assert str(len(cs._checks)) in cs._credential_summary()

    def test_summary_with_declaration(self, monkeypatch):
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("src_need", "需凭据源", _ENV_VAR))
        summary = cs._credential_summary()
        assert "1 个数据源需凭据" in summary
        assert "0 个已就绪" in summary
