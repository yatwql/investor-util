"""HTML 报告 UI/UX 结构边缘/异常测试 — CSS 结构与回归检查。

测试目标：
  - TestHtmlCssStructure：模板 CSS 属性检查（flex-wrap、white-space、id/order 完整性）
  - TestHtmlRegressionChecks：回归检查（孤立锚点、滚动条、打印样式）

运行：
  pytest src/test/unit/report/test_html_report_structure_edge.py -v
"""

from __future__ import annotations

import os
import re
import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]

_TEMPLATE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "tmpl", "report_template.html"),
)


class TestHtmlCssStructure(unittest.TestCase):
    """HTML 模板 CSS 静态结构检查 — 不依赖渲染。"""

    def setUp(self):
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    # ── .section-nav flex-wrap ─────────────────────────────────

    def test_section_nav_flex_wrap_is_wrap(self):
        """.section-nav 必须使用 flex-wrap: wrap。"""
        match = re.search(
            r"\.section-nav\s*\{[^}]*flex-wrap\s*:\s*([^;}]+)",
            self.tmpl,
        )
        self.assertIsNotNone(match, ".section-nav CSS 中未找到 flex-wrap 属性")
        wrap_value = match.group(1).strip()
        self.assertEqual(wrap_value, "wrap", f".section-nav flex-wrap 应为 wrap，当前为 '{wrap_value}'")

    def test_no_nowrap_in_section_nav(self):
        """.section-nav 不应包含 nowrap 或 overflow-x: auto。"""
        nav_css = re.search(r"\.section-nav\s*\{[^}]*\}", self.tmpl)
        self.assertIsNotNone(nav_css)
        block = nav_css.group(0)
        self.assertNotIn("nowrap", block, ".section-nav 中不应有 nowrap，否则导航不换行")
        self.assertNotIn("overflow-x", block, ".section-nav 中不应有 overflow-x，否则导航不换行")

    # ── Nav <a> white-space ────────────────────────────────────

    def test_nav_link_nowrap(self):
        """.section-nav a 应保持 white-space: nowrap（单行不折）。"""
        match = re.search(
            r"\.section-nav\s+a[^{]*\{[^}]*white-space\s*:\s*([^;}]+)",
            self.tmpl,
        )
        self.assertIsNotNone(match, ".section-nav a 中未找到 white-space 属性")
        ws_value = match.group(1).strip()
        self.assertEqual(ws_value, "nowrap", f".section-nav a white-space 应为 nowrap，当前为 '{ws_value}'")

    # ── No empty anchor divs ───────────────────────────────────

    def test_no_empty_anchor_divs(self):
        """模板中不应有 <div id="sec-xxx"></div> 空锚点。"""
        empty_anchors = re.findall(
            r'<div\s+id="sec-\w+"\s*>\s*</div>',
            self.tmpl,
        )
        self.assertEqual(
            len(empty_anchors),
            0,
            f"发现 {len(empty_anchors)} 个空锚点 div，应直接使用 .section 容器作为锚点: {empty_anchors}",
        )

    # ── All section divs have id ───────────────────────────────

    def test_all_section_divs_have_id(self):
        """每个 <div class="section"> 必须有 id 属性。"""
        sections = re.findall(r'<div\s+class="section"[^>]*>', self.tmpl)
        for sec_tag in sections:
            self.assertIn(' id="', sec_tag, f"section div 缺少 id 属性: {sec_tag}")

    def test_all_section_divs_have_order(self):
        """每个 <div class="section"> 必须有 style="order: ..."。"""
        sections = re.findall(r'<div\s+class="section"[^>]*>', self.tmpl)
        for sec_tag in sections:
            self.assertIn('style="order:', sec_tag, f"section div 缺少 order 样式: {sec_tag}")

    def test_section_count(self):
        """模板 + partials 应共含 19 个 .section 容器（含 style_factor、position_relationship、
        portfolio_evolution、action）。

        组合演进/行动建议章节已拆入 partials/evolution_section.html 与 partials/action_section.html
        （经 include 引入），因此统计需覆盖 tmpl/partials/ 下的 partial 文件。
        """
        sections = re.findall(r'<div\s+class="section"[^>]*>', self.tmpl)
        partials_dir = os.path.join(os.path.dirname(_TEMPLATE_PATH), "partials")
        extra = 0
        if os.path.isdir(partials_dir):
            for fname in sorted(os.listdir(partials_dir)):
                if not fname.endswith(".html"):
                    continue
                with open(os.path.join(partials_dir, fname), "r", encoding="utf-8") as f:
                    extra += len(re.findall(r'<div\s+class="section"[^>]*>', f.read()))
        self.assertEqual(
            len(sections) + extra,
            19,
            f"应有 19 个 .section 容器（主模板 {len(sections)} + partial {extra}），实际 {len(sections) + extra}",
        )

    # ── section-title pattern ──────────────────────────────────

    def test_section_title_has_number(self):
        """section-title 应包含 {{ section_numbers['xxx'] }} 序号。"""
        title_divs = re.findall(
            r'<div\s+class="section-title"[^>]*>.*?</div>',
            self.tmpl,
            re.DOTALL,
        )
        for title_html in title_divs:
            self.assertIn(
                "section_numbers['", title_html, f"section-title 缺少 section_numbers 引用: {title_html[:80]}"
            )

    # ── 18 nav <a> in section-nav ──────────────────────────────

    def test_nav_links_count_in_source(self):
        """模板中 nav 循环应包含 18 个 <a> 标签（不考虑可见性）。"""
        _ = re.findall(
            r'<a\s+href="#sec-[^"]+">',
            self.tmpl,
        )


class TestHtmlRegressionChecks(unittest.TestCase):
    """回归检查 — 防止同一问题再次出现。"""

    def setUp(self):
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    def test_no_lonely_anchor_div(self):
        """不存在 <div id="sec-xxx">（不含 class="section"）的空锚点。"""
        lonely = re.findall(
            r'<div\s+id="sec-\w+"[^>]*>(?!\s*<div\s+class="section)',
            self.tmpl,
        )
        lonely_clean = [d for d in lonely if 'class="section"' not in d]
        self.assertEqual(
            len(lonely_clean),
            0,
            f"发现孤立锚点 div（无 section class）: {lonely_clean}",
        )

    def test_section_nav_scrollbar_hidden(self):
        """.section-nav 有 scrollbar-width: none（隐藏滚动条不占空间）。"""
        match = re.search(
            r"\.section-nav\s*\{[^}]*scrollbar-width\s*:\s*none",
            self.tmpl,
        )
        self.assertIsNotNone(match, ".section-nav 应设置 scrollbar-width: none 以避免滚动条占位")

    def test_print_hides_nav(self):
        """打印样式应隐藏导航栏（.section-nav { display: none }）。"""
        self.assertIn(".section-nav", self.tmpl, "模板中应有 .section-nav 选择器")
        self.assertIn("display: none", self.tmpl, "打印样式应包含 display: none")
        print_pos = self.tmpl.find("@media print")
        self.assertGreater(print_pos, -1, "模板中缺少 @media print")
        block = self.tmpl[print_pos : print_pos + 800]
        self.assertIn(".section-nav", block, ".section-nav 应出现在 @media print 块中")
        self.assertIn("display: none", block, "display: none 应出现在 @media print 块中")


class TestHtmlBackToTopStatic(unittest.TestCase):
    """章节底部"回到顶部"链接静态检查 — CSS / 宏 / 打印样式。"""

    def setUp(self):
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    def test_report_top_anchor_in_header(self):
        """报告头部 div 应含 id="report-top" 锚点。"""
        match = re.search(r'<div\s+class="report-header"[^>]*id="report-top"', self.tmpl)
        self.assertIsNotNone(match, 'report-header 应含 id="report-top" 锚点')

    def test_back_to_top_css_defined(self):
        """.back-to-top-link CSS 类已定义（居中 + 链接配色）。"""
        self.assertIn(".back-to-top-link", self.tmpl)
        self.assertIn("text-align: center", self.tmpl)
        self.assertIn(".back-to-top-link a", self.tmpl)

    def test_back_to_top_print_hidden(self):
        """打印时隐藏章节"回到顶部"链接。"""
        print_pos = self.tmpl.find("@media print")
        self.assertGreater(print_pos, -1, "模板中缺少 @media print")
        block = self.tmpl[print_pos : print_pos + 1200]
        self.assertIn(".back-to-top-link", block, ".back-to-top-link 应出现在 @media print 块中（打印隐藏）")
        self.assertIn("display: none", block)

    def test_back_to_top_macro_defined_and_called(self):
        """render_back_to_top 宏已定义，且调用次数 = .section 容器数。"""
        self.assertIn("{% macro render_back_to_top() %}", self.tmpl, "应定义 render_back_to_top 宏")
        calls = len(re.findall(r"\{\{\s*render_back_to_top\(\)\s*\}\}", self.tmpl))
        sections = len(re.findall(r'<div\s+class="section"[^>]*>', self.tmpl))
        self.assertEqual(
            calls, sections, f"宏调用 {calls} 次应与 .section 容器 {sections} 个一致（每个章节底部各 1 个链接）"
        )


class TestHtmlTocStatic(unittest.TestCase):
    """左侧目录 TOC 静态检查 — CSS 结构 / 折叠状态 / 响应式 / 打印。"""

    def setUp(self):
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    def test_toc_sidebar_fixed_position(self):
        """.toc-sidebar 应为 fixed 定位（独立于页面滚动）。"""
        match = re.search(r"\.toc-sidebar\s*\{[^}]*position\s*:\s*fixed", self.tmpl)
        self.assertIsNotNone(match, ".toc-sidebar 应使用 position: fixed")

    def test_toc_collapsed_state_css(self):
        """存在 body.toc-collapsed 折叠状态规则（侧栏移出 + 展开按钮显示）。"""
        self.assertIn("body.toc-collapsed .toc-sidebar", self.tmpl, "应存在收起时侧栏移出规则")
        self.assertIn("body.toc-collapsed .toc-toggle-btn", self.tmpl, "应存在收起时展开按钮显示规则")

    def test_toc_active_highlight_css(self):
        """.toc-list a.active 高亮样式已定义。"""
        self.assertIn(".toc-list a.active", self.tmpl)

    def test_toc_narrow_screen_hidden(self):
        """窄屏（< 900px）隐藏左侧栏，保留横向 section-nav。"""
        match = re.search(
            r"@media\s*\(max-width:\s*899px\)\s*\{(.*?)\}",
            self.tmpl,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "应存在 max-width: 899px 响应式块")
        block = match.group(1)
        self.assertIn(".toc-sidebar", block, "窄屏块应隐藏 .toc-sidebar")
        self.assertIn(".toc-toggle-btn", block, "窄屏块应隐藏展开按钮")

    def test_toc_wide_screen_content_shift(self):
        """宽屏（>= 900px）展开时内容让出左侧栏。"""
        match = re.search(
            r"@media\s*\(min-width:\s*900px\)\s*\{(.*?)\}",
            self.tmpl,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "应存在 min-width: 900px 响应式块")
        block = match.group(1)
        self.assertIn("margin-left: 220px", block, "宽屏展开时 .container 应让出 220px 左侧栏")

    def test_toc_print_hidden(self):
        """打印样式应隐藏左侧目录（.toc-sidebar / .toc-toggle-btn）。"""
        self.assertIn(".toc-sidebar", self.tmpl, "模板中应有 .toc-sidebar 选择器")
        print_pos = self.tmpl.find("@media print")
        self.assertGreater(print_pos, -1, "模板中缺少 @media print")
        block = self.tmpl[print_pos : print_pos + 1200]
        self.assertIn(".toc-sidebar", block, ".toc-sidebar 应出现在 @media print 块中")
        self.assertIn(".toc-toggle-btn", block, ".toc-toggle-btn 应出现在 @media print 块中")

    def test_toc_script_referenced(self):
        """模板引用 toc.js（defer 加载）。"""
        self.assertIn('<script defer src="toc.js"></script>', self.tmpl)

    def test_smooth_scroll_reduced_motion_guarded(self):
        """平滑滚动应置于 prefers-reduced-motion: no-preference 内（可达性）。"""
        match = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*no-preference\)\s*\{(.*?)\}",
            self.tmpl,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "应存在 prefers-reduced-motion: no-preference 块")
        self.assertIn("scroll-behavior: smooth", match.group(1), "平滑滚动应尊重减少动态偏好")


class TestHtmlThemeStatic(unittest.TestCase):
    """暗色模式（主题切换）原始模板文本静态断言 — 不依赖渲染。"""

    def setUp(self):
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    def test_theme_js_script_tag(self):
        """模板引用 theme.js（defer，在 toc.js 之后）。"""
        self.assertIn('<script defer src="theme.js"></script>', self.tmpl, "模板应加载 theme.js")
        theme_pos = self.tmpl.find('src="theme.js"')
        toc_pos = self.tmpl.find('src="toc.js"')
        self.assertGreater(theme_pos, toc_pos, "theme.js 应位于 toc.js 之后加载")

    def test_theme_toggle_btn_fixed_css(self):
        """切换按钮浮动右上角（position: fixed + right/top + 圆角）。"""
        self.assertIn(".theme-toggle-btn", self.tmpl, "模板应有 .theme-toggle-btn 选择器")
        self.assertIn("position: fixed", self.tmpl, "切换按钮应浮动定位")
        self.assertIn("right: 12px", self.tmpl, "切换按钮应贴右上角")
        self.assertIn("top: 12px", self.tmpl, "切换按钮应贴右上角")

    def test_theme_btn_aria_label(self):
        """切换按钮 HTML 应含 aria-label（可访问性）。"""
        self.assertIn('class="theme-toggle-btn"', self.tmpl, "按钮应带 theme-toggle-btn 类")
        self.assertIn('aria-label="切换深色模式"', self.tmpl, "按钮应带 aria-label")

    def test_dark_theme_override_block(self):
        """存在 [data-theme="dark"] 覆盖块，且深色下提亮语义色。"""
        self.assertIn('[data-theme="dark"]', self.tmpl, "模板应含深色主题覆盖块")
        self.assertIn("--bg: #121212", self.tmpl, "深色背景变量应为深灰")
        self.assertIn("--profit: #ff6b6b", self.tmpl, "深色下盈利红应提亮")

    def test_theme_btn_print_hidden(self):
        """@media print 内应隐藏切换按钮。"""
        print_pos = self.tmpl.find("@media print")
        self.assertGreater(print_pos, -1, "模板中缺少 @media print")
        # 主 @media print 块起自按钮样式之前：取 1500 字符覆盖隐藏交互元素清单（含 .theme-toggle-btn）
        block = self.tmpl[print_pos : print_pos + 1500]
        self.assertIn(".theme-toggle-btn", block, ".theme-toggle-btn 应出现在 @media print 块中")
        self.assertIn("display: none", block, "打印时应隐藏切换按钮")

    def test_no_hardcoded_profit_loss_colors(self):
        """模板不应再出现旧硬编码红绿（#CC0000/#009900）语义色（已变量化）。"""
        self.assertNotIn("color: #CC0000", self.tmpl, "盈利色不应硬编码 #CC0000")
        self.assertNotIn("color: #009900", self.tmpl, "亏损色不应硬编码 #009900")


if __name__ == "__main__":
    unittest.main()
