"""响应式断点与触控契约（DESIGN.md Responsive 四档；移动阅读为一等场景）。

验收边界：报告面向手机浏览器阅读（安卓 Chrome / iOS Safari / 微信内置浏览器），
三面（主报告 / What-if / Web 工作台）断点必须收敛在契约四档族内，
触屏档（≤768）交互目标 ≥44px，移动阅读基础防护就位。
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]

_ROOT = pathlib.Path(__file__).resolve().parents[4]
_REPORT = _ROOT / "src/static/tmpl/report_template.html"
_WHATIF = _ROOT / "src/static/tmpl/whatif_template.html"
_WORKBENCH = _ROOT / "src/static/web/style.css"
_DESIGN = _ROOT / "DESIGN.md"
_SCRIPTS_DIR = _ROOT / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的模块（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_checklib = _load_script("_checklib.py")


def _css(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _breakpoint_values(css: str) -> set[int]:
    """提取全部 max/min-width 断点像素值（配对边界 1023 属 1024 档）。"""
    vals = re.findall(r"@media\s*\((?:max|min)-width:\s*(\d+)px\)", css)
    return {int(v) for v in vals}


def _design_breakpoints() -> set[int]:
    """DESIGN.md Responsive 断点表中的档位值（≥ 形式）。"""
    text = _DESIGN.read_text(encoding="utf-8")
    vals = re.findall(r"≥\s*(\d+)px", text)
    return {int(v) for v in vals}


class TestBreakpointContract:
    """四档断点契约：实现 ⊆ 契约族，主报告四档齐全，旧值零残留。"""

    def test_report_breakpoints_within_contract(self) -> str:
        vals = _breakpoint_values(_css(_REPORT))
        assert vals, "主报告应存在断点"
        # 合法族 = DESIGN 档位值 ∪ 各档左边界（1024 档的补集边界 1023）
        legal = _design_breakpoints() | {v - 1 for v in _design_breakpoints()}
        assert vals <= legal, f"越界断点: {vals - legal}"

    def test_report_has_narrow_and_touch_tiers(self) -> None:
        vals = _breakpoint_values(_css(_REPORT))
        assert {1024, 768, 480} <= vals, f"主报告缺档: {vals}"

    def test_whatif_and_workbench_within_contract(self) -> None:
        for path in (_WHATIF, _WORKBENCH):
            vals = _breakpoint_values(_css(path))
            assert vals, f"{path.name} 应存在断点"
            legal = _design_breakpoints() | {v - 1 for v in _design_breakpoints()}
            assert vals <= legal, f"{path.name} 越界断点: {vals - legal}"

    def test_legacy_breakpoints_absent(self) -> None:
        """旧经验值断点（899/900/375）零残留。"""
        for path in (_REPORT, _WHATIF, _WORKBENCH):
            css = _css(path)
            for legacy in ("899px", "900px", "375px"):
                assert legacy not in css, f"{path.name} 残留旧断点 {legacy}"

    def test_design_breakpoint_table_present(self) -> None:
        """DESIGN.md 断点表覆盖四档（≥1280/≥1024/≥768/≥480）。"""
        assert {1280, 1024, 768, 480} <= _design_breakpoints()


class TestMobileReadingGuard:
    """移动阅读基础防护：字号放大禁令 + 宽表首列冻结。"""

    def test_text_size_adjust_both_reports(self) -> None:
        for path in (_REPORT, _WHATIF):
            css = _css(path)
            assert "text-size-adjust: 100%" in css, f"{path.name} 缺 text-size-adjust"
            assert "-webkit-text-size-adjust" in css

    def test_frozen_first_column_both_reports(self) -> None:
        for path in (_REPORT, _WHATIF):
            css = _css(path)
            assert "thead th:first-child" in css, f"{path.name} 缺首列冻结"
            assert "position: sticky; left: 0" in css, f"{path.name} 缺 sticky 定位"

    def test_frozen_first_column_disabled_in_print(self) -> None:
        """打印归位：print 块内首列静态定位（防打印分页错位）。"""
        for path in (_REPORT, _WHATIF):
            hit = any(
                "thead th:first-child" in blk and "position: static" in blk
                for blk in _checklib.extract_at_rule_blocks(_css(path), "media print")
            )
            assert hit, f"{path.name} print 未归位首列冻结"


class TestTouchTargets:
    """触控目标 ≥44px（触屏档 ≤768 强制；浮动钮全局拉齐）。"""

    def test_floating_toggles_are_44(self) -> None:
        """目录/主题浮动钮全局 44×44（触控友好）。"""
        for path in (_REPORT, _WHATIF):
            css = _css(path)
            m = re.search(r"\.theme-toggle-btn \{[^}]*width: (\d+)px", css)
            assert m, f"{path.name} 缺 theme-toggle-btn"
            assert int(m.group(1)) >= 44, f"{path.name} theme-toggle {m.group(1)}px < 44"
        m = re.search(r"\.toc-toggle-btn \{[^}]*width: (\d+)px", _css(_REPORT))
        assert m and int(m.group(1)) >= 44, "toc-toggle 未达 44px"

    def test_touch_tier_min_height_rules(self) -> None:
        """≤768 触屏档存在 min-height: 44px 触控规则。"""
        m = re.search(
            r"@media \(max-width: 768px\) \{([^@]*?min-height: 44px[^@]*?)\}",
            _css(_REPORT),
            re.S,
        )
        assert m, "主报告缺 ≤768 触控档 44px 规则"
        m = re.search(r"@media \(max-width: 768px\) \{(.*?min-height: 44px.*?)\}", _css(_WORKBENCH), re.S)
        assert m, "工作台缺 ≤768 触控档 44px 规则"
        assert "min-height: 44px" in _css(_WHATIF), "What-if 缺 44px 触控规则"

    def test_fold_summary_touch_target(self) -> None:
        """折叠组头（主交互）全局触控目标 ≥44px。"""
        css = _css(_REPORT)
        m = re.search(r"\.section-fold-summary \{([^}]*)\}", css)
        assert m, "缺折叠组头规则"
        h = re.search(r"min-height: (\d+)px", m.group(1))
        assert h and int(h.group(1)) >= 44

    def test_workbench_form_controls_touch_target(self) -> None:
        """工作台表单控件在触屏档 ≥44px（输入/文件/选择器）。"""
        css = _css(_WORKBENCH)
        m = re.search(r"@media \(max-width: 768px\) \{(.*?)\}", css, re.S)
        assert m and "min-height: 44px" in m.group(1)
        block = m.group(1)
        for sel in ("input[type='text']", "select", ".tab-btn", ".btn"):
            assert sel in block, f"触控档缺 {sel}"
