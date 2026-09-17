"""测试：test-runner.py 分阶段测试报告路径与汇总页链接。

回归背景（自审发现）：分阶段模式（dev-verify = Phase A 核心单元 + Phase B 基础场景）
两阶段都把 pytest-html 报告写到同一个 ``report.html``，后跑的 Phase B 覆盖 Phase A——
详细报告只剩 152 个场景用例，Phase A 的 2700+ 用例（真正的失败面）在报告里消失。
修法：每阶段一个报告文件（``report_phase_<tag>.html``），汇总页逐阶段给链接。

覆盖：
  - 报告路径：分阶段带阶段后缀、非分阶段维持 report.html（向后兼容）
  - 汇总页链接：仅有 report.html → 单链接；有分阶段文件 → 逐阶段链接；均无 → 占位

通过 import 方式复用 scripts/test-runner.py 的函数，不运行真实测试。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


def _load_runner():
    """按文件名加载 scripts/test-runner.py（规避 import 路径限制）。"""
    name = "test_runner_report_paths"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / "test-runner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestPhaseReportPath:
    def test_phased_gets_own_file(self):
        runner = _load_runner()
        path = runner._phase_report_path("dev-verify", "A")
        assert path.endswith("dev-verify/report_phase_A.html")
        assert runner._phase_report_path("dev-verify", "B").endswith("report_phase_B.html")

    def test_non_phased_keeps_plain_name(self):
        """非分阶段模式维持 report.html（既有文档/CI artifact 约定不变）。"""
        assert _load_runner()._phase_report_path("unit").endswith("unit/report.html")

    def test_build_args_uses_phase_path(self):
        runner = _load_runner()
        args = runner._build_pytest_args(
            {"marker": "unit", "parallel": False}, "dev-verify", True, False, None, phase_tag="A"
        )
        assert "--html" in args
        assert args[args.index("--html") + 1].endswith("report_phase_A.html")


class TestIndexLinks:
    def _make(self, runner, tmp_path, monkeypatch, files: list[str]):
        monkeypatch.setattr(runner, "_LATEST_DIR", str(tmp_path))
        mode_dir = tmp_path / "dev-verify"
        mode_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            (mode_dir / name).write_text("<html></html>", encoding="utf-8")
        return runner._report_links_html("dev-verify")

    def test_lists_every_phase(self, tmp_path, monkeypatch):
        html = self._make(_load_runner(), tmp_path, monkeypatch, ["report_phase_A.html", "report_phase_B.html"])
        assert "dev-verify/report_phase_A.html" in html
        assert "dev-verify/report_phase_B.html" in html
        assert "Phase A" in html and "Phase B" in html

    def test_plain_report_still_linked(self, tmp_path, monkeypatch):
        html = self._make(_load_runner(), tmp_path, monkeypatch, ["report.html"])
        assert 'href="dev-verify/report.html"' in html

    def test_no_report_shows_placeholder(self, tmp_path, monkeypatch):
        html = self._make(_load_runner(), tmp_path, monkeypatch, [])
        assert "无" in html
