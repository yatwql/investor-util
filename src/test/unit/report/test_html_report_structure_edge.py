"""HTML 报告 UI/UX 结构边缘/异常测试 — CSS 结构与回归检查。

测试目标：
  - TestHtmlCssStructure：模板 CSS 属性检查（flex-wrap、white-space、id/order 完整性）
  - TestHtmlRegressionChecks：旧 bug 回归检查（孤立锚点、滚动条、打印样式）

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/report/test_html_report_structure_edge.py -v
"""

from __future__ import annotations

import os
import re
import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]

_TEMPLATE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "python", "tmpl", "report_template.html"),
)


class TestHtmlCssStructure(unittest.TestCase):
    """HTML 模板 CSS 静态结构检查 — 不依赖渲染。"""

    def setUp(self):
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    # ── .section-nav flex-wrap ─────────────────────────────────

    def test_section_nav_flex_wrap_is_wrap(self):
        """.section-nav 必须使用 flex-wrap: wrap（R-168 修复）。"""
        match = re.search(
            r"\.section-nav\s*\{[^}]*flex-wrap\s*:\s*([^;}]+)",
            self.tmpl,
        )
        self.assertIsNotNone(match, ".section-nav CSS 中未找到 flex-wrap 属性")
        wrap_value = match.group(1).strip()
        self.assertEqual(wrap_value, "wrap",
                         f".section-nav flex-wrap 应为 wrap，当前为 '{wrap_value}'")

    def test_no_nowrap_in_section_nav(self):
        """.section-nav 不应包含 nowrap 或 overflow-x: auto。"""
        nav_css = re.search(r"\.section-nav\s*\{[^}]*\}", self.tmpl)
        self.assertIsNotNone(nav_css)
        block = nav_css.group(0)
        self.assertNotIn("nowrap", block,
                         ".section-nav 中不应有 nowrap，否则导航不换行")
        self.assertNotIn("overflow-x", block,
                         ".section-nav 中不应有 overflow-x，否则导航不换行")

    # ── Nav <a> white-space ────────────────────────────────────

    def test_nav_link_nowrap(self):
        """.section-nav a 应保持 white-space: nowrap（单行不折）。"""
        match = re.search(
            r"\.section-nav\s+a[^{]*\{[^}]*white-space\s*:\s*([^;}]+)",
            self.tmpl,
        )
        self.assertIsNotNone(match, ".section-nav a 中未找到 white-space 属性")
        ws_value = match.group(1).strip()
        self.assertEqual(ws_value, "nowrap",
                         f".section-nav a white-space 应为 nowrap，当前为 '{ws_value}'")

    # ── No empty anchor divs ───────────────────────────────────

    def test_no_empty_anchor_divs(self):
        """模板中不应有 <div id="sec-xxx"></div> 空锚点（R-168）。"""
        empty_anchors = re.findall(
            r'<div\s+id="sec-\w+"\s*>\s*</div>',
            self.tmpl,
        )
        self.assertEqual(
            len(empty_anchors), 0,
            f"发现 {len(empty_anchors)} 个空锚点 div，应直接使用 .section 容器作为锚点: {empty_anchors}",
        )

    # ── All section divs have id ───────────────────────────────

    def test_all_section_divs_have_id(self):
        """每个 <div class="section"> 必须有 id 属性。"""
        sections = re.findall(r'<div\s+class="section"[^>]*>', self.tmpl)
        for sec_tag in sections:
            self.assertIn(" id=\"", sec_tag,
                          f"section div 缺少 id 属性: {sec_tag}")

    def test_all_section_divs_have_order(self):
        """每个 <div class="section"> 必须有 style="order: ..."。"""
        sections = re.findall(r'<div\s+class="section"[^>]*>', self.tmpl)
        for sec_tag in sections:
            self.assertIn("style=\"order:", sec_tag,
                          f"section div 缺少 order 样式: {sec_tag}")

    def test_section_count(self):
        """模板应包含 18 个 .section 容器。"""
        sections = re.findall(r'<div\s+class="section"[^>]*>', self.tmpl)
        self.assertEqual(len(sections), 18,
                         f"应有 18 个 .section 容器，实际 {len(sections)}")

    # ── section-title pattern ──────────────────────────────────

    def test_section_title_has_number(self):
        """section-title 应包含 {{ section_numbers['xxx'] }} 序号。"""
        title_divs = re.findall(
            r'<div\s+class="section-title"[^>]*>.*?</div>',
            self.tmpl,
            re.DOTALL,
        )
        for title_html in title_divs:
            self.assertIn("section_numbers['", title_html,
                          f"section-title 缺少 section_numbers 引用: {title_html[:80]}")

    # ── 18 nav <a> in section-nav ──────────────────────────────

    def test_nav_links_count_in_source(self):
        """模板中 nav 循环应包含 18 个 <a> 标签（不考虑可见性）。"""
        _ = re.findall(
            r'<a\s+href="#sec-[^"]+">',
            self.tmpl,
        )


class TestHtmlRegressionChecks(unittest.TestCase):
    """旧 bug 回归检查 — 防止同一问题再次出现。"""

    def setUp(self):
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    def test_no_lonely_anchor_div(self):
        """不存在 <div id="sec-xxx">（不含 class="section"）的空锚点。"""
        lonely = re.findall(
            r'<div\s+id="sec-\w+"[^>]*>(?!\s*<div\s+class="section)',
            self.tmpl,
        )
        lonely_clean = [
            d for d in lonely
            if 'class="section"' not in d
        ]
        self.assertEqual(
            len(lonely_clean), 0,
            f"发现孤立锚点 div（无 section class）: {lonely_clean}",
        )

    def test_section_nav_scrollbar_hidden(self):
        """.section-nav 有 scrollbar-width: none（隐藏滚动条不占空间）。"""
        match = re.search(
            r"\.section-nav\s*\{[^}]*scrollbar-width\s*:\s*none",
            self.tmpl,
        )
        self.assertIsNotNone(match,
                             ".section-nav 应设置 scrollbar-width: none 以避免滚动条占位")

    def test_print_hides_nav(self):
        """打印样式应隐藏导航栏（.section-nav { display: none }）。"""
        self.assertIn(".section-nav", self.tmpl,
                       "模板中应有 .section-nav 选择器")
        self.assertIn("display: none", self.tmpl,
                      "打印样式应包含 display: none")
        print_pos = self.tmpl.find("@media print")
        self.assertGreater(print_pos, -1, "模板中缺少 @media print")
        block = self.tmpl[print_pos:print_pos + 800]
        self.assertIn(".section-nav", block,
                      ".section-nav 应出现在 @media print 块中")
        self.assertIn("display: none", block,
                      "display: none 应出现在 @media print 块中")


if __name__ == "__main__":
    unittest.main()
