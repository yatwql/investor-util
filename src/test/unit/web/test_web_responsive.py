# -*- coding: utf-8 -*-
"""Web 工作台窄屏（375px）横向滚动回归：style.css 收缩/断词约束静态断言。

缺陷形态（无浏览器的静态载体）：窄屏列布局下 flex 行线宽取子项假定宽
（fit-content），不受容器列宽封顶——单个无断词机会的持仓绝对路径文案
（min-content 高达 369px，overflow-wrap:break-word 不参与 min-content 计算）
或固有宽控件（select 选项文案、原生 file 输入内在宽 347px）会把整行撑出
视口，documentElement.scrollWidth 超过视口宽产生横向滚动。

约束同源（与 style.css 注释一致）：
- ``.radio-label span``      overflow-wrap:anywhere + min-width:0（断词压 min-content）
- ``.generate-form > *``     min-width:0 + max-width:100%（行线宽按容器列宽封顶）
- ``select`` / ``.file-input-plain``  min-width:0 + max-width:100%（收缩钳制）
- 含路径的 radio 文案必须落在 ``.radio-label > span`` 内（选择器可达）
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]

REPO_ROOT = Path(__file__).resolve().parents[4]
STYLE_CSS = REPO_ROOT / "src/static/web/style.css"
INDEX_HTML = REPO_ROOT / "src/static/web/index.html"

#: 窄屏列布局下必须带收缩钳制的表单子项规则（选择器 → 必须具备的声明）
SHRINK_RULES = {
    ".generate-form > *": {"min-width": "0", "max-width": "100%"},
    "select": {"min-width": "0", "max-width": "100%"},
    ".file-input-plain": {"min-width": "0", "max-width": "100%"},
}


def _rule_bodies(css: str) -> dict[str, str]:
    """选择器（去注释、逗号拆分、空白归一）→ 声明块文本。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: dict[str, str] = {}
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for one in sel.split(","):
            one = " ".join(one.split())
            if one:
                out.setdefault(one, body)
    return out


def _decl(body: str, prop: str) -> str | None:
    m = re.search(rf"(?:^|;)\s*{re.escape(prop)}\s*:\s*([^;]+)", body)
    return m.group(1).strip() if m else None


class TestShrinkConstraints:
    """固有宽控件与表单子项的收缩钳制（防整行撑出视口）。"""

    def test_expected_rules_present(self):
        rules = _rule_bodies(STYLE_CSS.read_text(encoding="utf-8"))
        missing = [sel for sel in SHRINK_RULES if sel not in rules]
        assert not missing, f"收缩规则选择器缺失: {missing}"

    def test_shrink_declarations_in_place(self):
        rules = _rule_bodies(STYLE_CSS.read_text(encoding="utf-8"))
        for sel, expected in SHRINK_RULES.items():
            assert sel in rules, f"规则缺失: {sel}"
            for prop, value in expected.items():
                actual = _decl(rules[sel], prop)
                assert actual == value, f"{sel} 的 {prop} 应为 {value}，实为 {actual}"

    def test_path_label_breaks_anywhere(self):
        """路径文案断词必须用 anywhere（break-word 不参与 min-content 计算，压不下来）。"""
        rules = _rule_bodies(STYLE_CSS.read_text(encoding="utf-8"))
        body = rules.get(".radio-label span")
        assert body is not None, "缺 .radio-label span 断词规则"
        assert _decl(body, "overflow-wrap") == "anywhere"
        assert _decl(body, "min-width") == "0"


class TestPathLabelMarkupCovered:
    """含持仓路径的 radio 文案必须落在断词规则可达的 ``.radio-label > span`` 内。"""

    #: 含路径的单选（页签内定位锚点，非可增长集合）
    _PATH_RADIOS = (("input_mode", "formal"), ("whatif_base", "existing"))

    @staticmethod
    def _radio_labels(html: str) -> list[str]:
        return re.findall(r'<label class="radio-label">(.*?)</label>', html, flags=re.S)

    def test_path_radios_wrapped_in_breakable_span(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        labels = self._radio_labels(html)
        assert labels, "index.html 未找到 radio-label 文案块，断言前提失效"
        for name, value in self._PATH_RADIOS:
            hits = [b for b in labels if f'name="{name}"' in b and f'value="{value}"' in b]
            assert hits, f"缺含路径单选: name={name} value={value}"
            span = re.search(r"<span>[^<]*\{\{\s*system_info\.holdings_dir\s*\}\}", hits[0])
            assert span, f"路径文案须在 .radio-label 的 <span> 内: name={name} value={value}"

    def test_whatif_file_inputs_carry_shrink_class(self):
        """whatif 两个 file 输入须带 .file-input-plain（收缩规则按类命中）。"""
        html = INDEX_HTML.read_text(encoding="utf-8")
        for elem_id in ("whatif-base-input", "whatif-cand-input"):
            tag = re.search(rf"<input[^>]*id=\"{elem_id}\"[^>]*>", html)
            assert tag, f"缺 file 输入: {elem_id}"
            assert "file-input-plain" in tag.group(0), f"{elem_id} 须带 file-input-plain 类"
