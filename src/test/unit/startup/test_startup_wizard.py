"""首次运行引导模块测试。

测试策略：
  - is_first_run / mark_wizard_shown — 配置标记键读写（测试隔离下用 tmp config）
  - _detect_startup_state — 持仓目录 / LLM 凭据 / 降级三态检测
  - _write_llm_key_flat — 原子写 flat llm_key.json（原子写 + 凭据分离，llm_key 路径被
    _isolate_sensitive_paths 重定向到 tmp_path）
  - _is_non_interactive — CI / NON_INTERACTIVE / force 跳过
  - show_startup_wizard_if_needed — 非首次/非交互静默、交互引导打印、标记已读

注意：pytest 环境 stdin 非 TTY，交互路径测试必须显式 mock _is_non_interactive。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_ui]

from src.python import startup_wizard
from src.python.config._llm_providers import (
    _get_llm_key_path,
    _get_llm_providers_path,
    _load_llm_key_credentials,
)
from src.python.startup_wizard import (
    _detect_startup_state,
    _is_non_interactive,
    _llm_key_present,
    _write_llm_key_flat,
    is_first_run,
    mark_wizard_shown,
    show_startup_wizard_if_needed,
)


def _key_path() -> Path:
    """llm_key.json 路径（隔离环境指向 tmp_path）。"""
    return Path(_get_llm_key_path())


def _config(holdings_dir: str | None = None) -> dict:
    cfg = {}
    if holdings_dir is not None:
        cfg["holdings_dir"] = holdings_dir
    return cfg


# ── 首次运行标记 ─────────────────────────────────────────────


class TestFirstRunFlag:
    """is_first_run / mark_wizard_shown 测试。"""

    def test_first_run_true_when_flag_missing(self):
        """标记键缺失 → 首次运行。"""
        assert is_first_run() is True

    def test_mark_wizard_shown_then_not_first_run(self):
        """标记后 → 不再视为首次运行。"""
        mark_wizard_shown()
        assert is_first_run() is False

    def test_mark_wizard_shown_idempotent(self):
        """重复标记不报错。"""
        mark_wizard_shown()
        mark_wizard_shown()
        assert is_first_run() is False


# ── 状态检测 ─────────────────────────────────────────────────


class TestDetectStartupState:
    """_detect_startup_state 三态检测测试。"""

    def test_all_ready(self, tmp_path):
        """持仓 + LLM 凭据齐全 → holdings_ok/llm_key_ok True，非降级。"""
        holdings = tmp_path / "holdings"
        holdings.mkdir()
        (holdings / "账户1.xlsx").write_bytes(b"x")

        # 手工创建 llm_key.json（_isolate_sensitive_paths 已将路径指向 tmp）
        key_path = _key_path()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(json.dumps({"provider": "claude", "api_key": "sk-test"}), encoding="utf-8")

        state = _detect_startup_state(_config(holdings_dir=str(holdings)))
        assert state["holdings_ok"] is True
        assert state["llm_key_ok"] is True
        assert state["llm_degraded"] is False

    def test_no_holdings_no_key(self, tmp_path):
        """持仓为空 + 无凭据 → 均 False，降级 True（LLM 默认启用）。"""
        state = _detect_startup_state(_config(holdings_dir=str(tmp_path / "empty")))
        assert state["holdings_ok"] is False
        assert state["llm_key_ok"] is False
        assert state["llm_degraded"] is True

    def test_holdings_present_key_missing(self, tmp_path):
        """有持仓但无凭据 → 降级 True。"""
        holdings = tmp_path / "holdings"
        holdings.mkdir()
        (holdings / "a.xlsx").write_bytes(b"x")
        state = _detect_startup_state(_config(holdings_dir=str(holdings)))
        assert state["holdings_ok"] is True
        assert state["llm_key_ok"] is False
        assert state["llm_degraded"] is True

    def test_key_missing_but_providers_chain(self, tmp_path):
        """无 llm_key.json 但 llm_providers.json 有 providers → 链模式视为就绪。"""
        prov_path = Path(_get_llm_providers_path())
        prov_path.parent.mkdir(parents=True, exist_ok=True)
        prov_path.write_text(
            json.dumps({"providers": [{"name": "claude", "api_key_ref": "k1"}]}),
            encoding="utf-8",
        )
        assert _llm_key_present() is True


# ── llm_key 写入 ─────────────────────────────────────────────


class TestWriteLlmKeyFlat:
    """_write_llm_key_flat 原子写 flat llm_key.json 测试。"""

    def test_writes_flat_key_file(self):
        """写入 provider/api_key，可被 _load_llm_key_credentials 读回（自动升级）。"""
        _write_llm_key_flat("sk-test", provider="claude")
        assert _key_path().exists()
        creds = _load_llm_key_credentials()
        assert creds is not None
        assert creds["_default"]["api_key"] == "sk-test"
        assert creds["_default"]["provider"] == "claude"

    def test_writes_model_and_endpoint(self):
        """带 model/endpoint → 一并写入。"""
        _write_llm_key_flat("sk-x", provider="claude", model="claude-sonnet-4-6",
                            endpoint="https://api.deepseek.com/anthropic")
        creds = _load_llm_key_credentials()["_default"]
        assert creds["model"] == "claude-sonnet-4-6"
        assert creds["endpoint"] == "https://api.deepseek.com/anthropic"


# ── 非交互检测 ───────────────────────────────────────────────


class TestNonInteractive:
    """_is_non_interactive 环境检测测试。"""

    def test_force_flag(self):
        """force=True → 非交互。"""
        assert _is_non_interactive(force=True) is True

    def test_ci_env(self, monkeypatch):
        """CI 环境变量 → 非交互。"""
        monkeypatch.setenv("CI", "1")
        assert _is_non_interactive() is True

    def test_non_interactive_env(self, monkeypatch):
        """NON_INTERACTIVE 环境变量 → 非交互。"""
        monkeypatch.setenv("NON_INTERACTIVE", "1")
        assert _is_non_interactive() is True


# ── 交互式引导 ───────────────────────────────────────────────


class TestShowStartupWizard:
    """show_startup_wizard_if_needed 交互引导测试。"""

    def _interactive(self, monkeypatch):
        """pytest 下 stdin 非 TTY，强制交互路径。"""
        monkeypatch.setattr(startup_wizard, "_is_non_interactive", lambda force=False: False)

    def test_non_first_run_silent(self, monkeypatch, capsys):
        """非首次运行 → 静默返回 False。"""
        mark_wizard_shown()
        assert show_startup_wizard_if_needed() is False
        assert capsys.readouterr().out == ""

    def test_non_interactive_skips(self, monkeypatch, capsys):
        """非交互环境 → 跳过，返回 False，无输出。"""
        monkeypatch.setattr(startup_wizard, "_is_non_interactive", lambda force=False: True)
        assert show_startup_wizard_if_needed() is False
        assert capsys.readouterr().out == ""

    def test_first_run_interactive_prints_and_marks(self, monkeypatch, capsys):
        """首次 + 交互 → 打印引导并标记已读。"""
        self._interactive(monkeypatch)
        # 隔离环境下无 llm_key.json → 引导会询问是否输入 Key；
        # 该测试聚焦"打印+标记"，故 mock input 选择跳过（n）
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        result = show_startup_wizard_if_needed()
        assert result is True
        out = capsys.readouterr().out
        assert "首次运行引导" in out
        assert "持仓文件" in out
        assert "LLM 配置" in out
        assert is_first_run() is False  # 已标记

    def test_all_ready_prints_ready(self, monkeypatch, capsys):
        """全部就绪 → 打印"一切就绪"。"""
        self._interactive(monkeypatch)
        monkeypatch.setattr(
            startup_wizard, "_detect_startup_state",
            lambda config: {"holdings_ok": True, "llm_key_ok": True, "llm_degraded": False},
        )
        show_startup_wizard_if_needed()
        assert "一切就绪" in capsys.readouterr().out

    def test_user_enters_key(self, monkeypatch, capsys, tmp_path):
        """交互输入 Key → 原子写入 llm_key.json。"""
        self._interactive(monkeypatch)
        # 无持仓、无凭据 → 降级提示路径；用户选择 y 并输入 key
        monkeypatch.setattr(startup_wizard, "_detect_startup_state",
                            lambda config: {"holdings_ok": False, "llm_key_ok": False,
                                            "llm_degraded": True})
        answers = iter(["y", "sk-interactive"])  # 先答 y，再输入 key
        monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
        show_startup_wizard_if_needed()
        out = capsys.readouterr().out
        assert "已保存 llm_key.json" in out
        # 校验写入内容
        assert _key_path().exists()
        raw = json.loads(_key_path().read_text(encoding="utf-8"))
        assert raw["api_key"] == "sk-interactive"

    def test_user_skips_key(self, monkeypatch, capsys):
        """用户选择跳过 Key 输入 → 不写文件。"""
        self._interactive(monkeypatch)
        monkeypatch.setattr(startup_wizard, "_detect_startup_state",
                            lambda config: {"holdings_ok": True, "llm_key_ok": False,
                                            "llm_degraded": True})
        # 第一次 input 是"现在配置 LLM Key?[y/N]" → n；第二次不会再触发
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        show_startup_wizard_if_needed()
        assert "已保存 llm_key.json" not in capsys.readouterr().out
        assert not _key_path().exists()
