"""体检「数据源凭据」组单元测试（实验功能 `datasource_credential_ready`）。

覆盖：开关关闭 → 该组不产出（体检输出与现状一致）；开启 → 无声明报「均无需凭据」、
有缺失报失败项且 hint 为可执行修复建议、就绪时报通过；网络组不重复计失败。

运行：
  pytest src/test/unit/core/test_doctor_credential.py -v
"""

from __future__ import annotations

from unittest import mock

import pytest

from src.python.config import features
from src.python.core import doctor
from src.python.core.datasource_credential import CredentialSpec, register_credential_spec

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

_FLAG = "datasource_credential_ready"
_ENV_VAR = "INVESTOR_UTIL_DOCTOR_KEY"


class TestCredentialGroup:
    """凭据组：受开关约束，缺失时给可执行修复建议。"""

    def test_flag_off_produces_no_group(self, monkeypatch):
        """开关关闭 → 不产出该组（自检输出与未引入本机制时一致）。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, False)
        assert doctor._check_datasource_credentials() == []

    def test_no_declaration_reports_free_sources(self, monkeypatch):
        """开启且无任何声明 → 通过，说明当前全部免费源（现状如实呈现）。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)
        items = doctor._check_datasource_credentials()
        assert len(items) == 1
        assert items[0]["ok"] is True
        assert items[0]["group"] == doctor.GROUP_CREDENTIAL
        assert "均无需凭据" in items[0]["message"]

    def test_missing_credential_reports_failure_with_hint(self, monkeypatch):
        """声明了凭据但未配置 → 失败项，hint 指明变量名（错误即 UX）。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)
        monkeypatch.delenv(_ENV_VAR, raising=False)
        register_credential_spec(CredentialSpec("src_need", "示例财经", _ENV_VAR, "https://example.com/apply"))

        items = doctor._check_datasource_credentials()
        assert items[0]["ok"] is False
        assert "示例财经" in items[0]["message"]
        assert _ENV_VAR in items[0]["hint"]

    def test_ready_credential_reports_ok(self, monkeypatch):
        """凭据已配置 → 通过。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)
        monkeypatch.setenv(_ENV_VAR, "key-value")
        register_credential_spec(CredentialSpec("src_need", "示例财经", _ENV_VAR))

        items = doctor._check_datasource_credentials()
        assert items[0]["ok"] is True
        assert "已就绪" in items[0]["message"]

    def test_group_registered_in_order(self):
        """该组已登记进 GROUP_ORDER（渲染时不会落到末位兜底）。"""
        assert doctor.GROUP_CREDENTIAL in doctor.GROUP_ORDER

    def test_never_raises_on_broken_readiness(self, monkeypatch):
        """就绪矩阵读取失败 → 转成失败项而非抛出（自检永不抛异常）。"""
        monkeypatch.setitem(features.FEATURE_FLAGS, _FLAG, True)
        with mock.patch(
            "src.python.core.datasource_credential.credential_readiness",
            side_effect=RuntimeError("坏了"),
        ):
            items = doctor._check_datasource_credentials()
        assert items[0]["ok"] is False
        assert "坏了" in items[0]["message"]


class TestNetworkGroupSkipsCredentialSkips:
    """网络组：凭据未探测的源由凭据组专门报告，不在此重复计为失败。"""

    def test_skipped_items_filtered_out(self):
        raw = [
            {"name": "免费源", "label": "免费源", "ok": True, "latency_ms": 3.0, "message": "3ms 正常"},
            {
                "name": "需凭据源",
                "label": "需凭据源",
                "ok": False,
                "skipped": True,
                "latency_ms": 0.0,
                "message": "缺少凭据（数据源：示例财经）——请设置环境变量 X_KEY",
            },
        ]
        with mock.patch("src.python.core.check_sources.run_health_checks", return_value=raw):
            items = doctor._check_network(max_timeout=1.0)

        labels = [i["label"] for i in items]
        assert labels == ["免费源"]
