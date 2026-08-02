"""HTML 模板打印样式 & 条件分支测试。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/report/test_html_template.py -v
"""

from __future__ import annotations

import os
import re
import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestHtmlTemplatePrintStyles(unittest.TestCase):
    """@media print 样式规则完整性检测。"""

    def setUp(self):
        tmpl_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "python", "tmpl", "report_template.html",
        )
        self.tmpl_path = os.path.normpath(tmpl_path)
        with open(self.tmpl_path, encoding="utf-8") as f:
            self.html = f.read()

    def test_has_media_print_block(self):
        """模板包含 @media print 规则块。"""
        self.assertIn("@media print", self.html)

    def test_print_hides_section_nav(self):
        """打印时隐藏导航栏（含左侧目录 TOC）。"""
        # 选择器列表跨行合并为一条规则（.section-nav、.toc-sidebar、.toc-toggle-btn 等），
        # 匹配 `.section-nav → .toc-sidebar → .toc-toggle-btn { display: none !important }` 规则
        match = re.search(
            r"\.section-nav,\s*\.toc-sidebar,\s*\.toc-toggle-btn\s*\{\s*display:\s*none\s*!important\s*;\s*\}",
            self.html,
        )
        self.assertIsNotNone(match, "打印块中应存在同时隐藏 .section-nav/.toc-sidebar/.toc-toggle-btn 的规则")

    def test_print_hides_back_to_top(self):
        """打印时隐藏回到顶部按钮。"""
        self.assertIn(".back-to-top", self.html)

    def test_print_table_header_repeat(self):
        """打印时表头跨页重复。"""
        self.assertIn("table-header-group", self.html)

    def test_print_black_white_friendly(self):
        """黑白友好：颜色属性覆写为 black。"""
        self.assertIn("color: #000 !important", self.html)

    def test_print_page_break_avoid(self):
        """打印避免行/图片跨页断裂。"""
        self.assertIn("page-break-inside: avoid", self.html)

    def test_print_expand_collapsible(self):
        """打印展开全部可折叠内容。"""
        self.assertIn("display: block !important", self.html)

    def test_print_section_avoid_break(self):
        """大块内容避免跨页断裂。"""
        self.assertIn("page-break-inside: avoid;", self.html)

    def test_print_heatmap_bw_friendly(self):
        """热力图矩阵黑白友好覆盖。"""
        self.assertIn(".heatmap-matrix td[style*=\"background\"]", self.html)
