"""HTML 模板打印样式 & 条件分支测试。

运行：
  pytest src/test/unit/report/test_html_template.py -v
"""

from __future__ import annotations

import os
import pathlib
import re
import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestHtmlTemplatePrintStyles(unittest.TestCase):
    """@media print 样式规则完整性检测。"""

    def setUp(self):
        tmpl_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "static",
            "tmpl",
            "report_template.html",
        )
        self.tmpl_path = os.path.normpath(tmpl_path)
        with open(self.tmpl_path, encoding="utf-8") as f:
            self.html = f.read()

    def test_has_media_print_block(self):
        """模板包含 @media print 规则块。"""
        self.assertIn("@media print", self.html)

    def test_print_hides_section_nav(self):
        """打印时隐藏导航栏（含左侧目录 TOC 与主题切换按钮）。"""
        # 选择器列表跨行合并为一条规则（.section-nav、.toc-sidebar、.toc-toggle-btn、
        # .theme-toggle-btn → 一条 display:none 规则）。主题切换按钮并入隐藏清单。
        match = re.search(
            r"\.section-nav,\s*\.toc-sidebar,\s*\.toc-toggle-btn,\s*\.theme-toggle-btn\s*\{\s*display:\s*none\s*!important\s*;\s*\}",
            self.html,
        )
        self.assertIsNotNone(
            match,
            "打印块中应存在同时隐藏 .section-nav/.toc-sidebar/.toc-toggle-btn/.theme-toggle-btn 的规则",
        )

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
        self.assertIn('.heatmap-matrix td[style*="background"]', self.html)


_TMPL_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "tmpl"))


class TestFundamentalSnapshotPlaceholderGuidance(unittest.TestCase):
    """持仓基本面章降级占位文案（真实模板渲染）。

    回归背景（两处曾同时出现）：
      1. 占位指引引用**已废弃的配置路径** ``report_submodules.financial_report_digest`` /
         ``.financial_indicator``——该路径在功能开关迁入 ``features.json`` 时已被移除
         （config.json 不再承载，Web/CLI 白名单亦不含），照着改配置**不生效**。
      2. 指引把“本次无数据”**归因成“需配置 key”**：即便用户已配好 DataSinking key
         （且能正常读取），也照旧显示“需在 … 配置 DataSinking API key”，让人以为配置丢了。
         占位应只呈现**真实原因**（契约 reason）+ 当前开关入口 + 取数所需条件的客观说明。
    """

    def _render_snapshot(self, **overrides) -> str:
        from src.python.report.html_jinja_env import _ENV

        path = os.path.join(_TMPL_DIR, "partials", "fundamental_snapshot_section.html")
        with open(path, encoding="utf-8") as f:
            tpl = _ENV.from_string(f.read())
        ctx = {
            "section_visible": lambda _key: True,
            "section_numbers": {"fundamental_snapshot": 16},
            "financial_indicator_data": None,
            "financial_report_digest_data": None,
        }
        ctx.update(overrides)
        return tpl.render(**ctx)

    def test_digest_placeholder_shows_reason_and_current_switch(self):
        """区块②不可用时：透传真实原因 + 指向当前开关与入口，且不再提废弃路径。"""
        html = self._render_snapshot(
            financial_report_digest_data={
                "available": False,
                "reason": "全部标的未取到财报",
                "failures": [],
                "entry_count": 0,
            }
        )
        assert "持仓个股财报摘要暂不可用" in html
        assert "全部标的未取到财报" in html
        assert "financial_report_digest" in html
        assert "report_submodules." not in html

    def test_indicator_placeholder_shows_reason_and_current_switch(self):
        """区块①不可用时同样透传原因并指向当前开关。"""
        html = self._render_snapshot(
            financial_indicator_data={
                "available": False,
                "reason": "暂无可用财务指标数据",
                "failures": [],
                "entry_count": 0,
            }
        )
        assert "财务指标暂不可用" in html
        assert "暂无可用财务指标数据" in html
        assert "financial_indicator" in html
        assert "report_submodules." not in html

    def test_no_legacy_report_submodules_path_anywhere_in_templates(self):
        """全模板树不得出现已废弃的 ``report_submodules.*`` 配置路径（含注释）。"""
        offenders = [
            os.path.relpath(str(p), _TMPL_DIR)
            for p in sorted(pathlib.Path(_TMPL_DIR).rglob("*.html"))
            if "report_submodules." in p.read_text(encoding="utf-8")
        ]
        assert offenders == []
