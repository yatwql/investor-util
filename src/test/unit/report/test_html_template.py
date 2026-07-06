"""HTML 模板条件分支巡检 — 确保模板包含所有必要条件判断分支。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/report/test_html_template.py -v
"""

from __future__ import annotations

import os
import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestHtmlTemplateBranchAudit(unittest.TestCase):
    """HTML 模板缺失条件分支检测。

    检查 report_template.html 中是否包含所有必要的条件判断分支，
    避免"较差"评级漏写等问题再次发生（R-148）。
    """

    def setUp(self):
        tmpl_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "python", "tmpl", "report_template.html",
        )
        self.tmpl_path = os.path.normpath(tmpl_path)
        with open(self.tmpl_path, "r", encoding="utf-8") as f:
            self.tmpl = f.read()

    def test_all_five_rating_colors_present(self):
        """基金业绩 5 级评级颜色条件全部存在。

        "良好"使用默认黑色（#000000），无显式 color 样式。
        """
        rating_colors = {
            "优秀": "#CC0000",
            "稳定": "#0066CC",
            "偏差": "#009900",
            "较差": "#006400",
        }
        for rating, color in rating_colors.items():
            color_pattern = f"color: {color}"
            self.assertIn(
                color_pattern, self.tmpl,
                f"评级 '{rating}' 的颜色 {color} 在模板中缺失",
            )
        # 良好使用默认色，不应有特殊 color 样式
        self.assertIn("良好", self.tmpl)

    def test_rating_tag_branches(self):
        """所有 5 个 p['rating_tag'] 条件分支存在。"""
        for rating in ["优秀", "良好", "稳定", "偏差", "较差"]:
            self.assertIn(
                rating, self.tmpl,
                f"评级条件分支 '{rating}' 在模板中缺失",
            )

    def test_disabled_module_comment(self):
        """模板包含禁用模块的跳过注释。"""
        self.assertIn("模块已禁用，完全跳过", self.tmpl)

    def test_llm_module_disabled_check(self):
        """LLM 模块禁用检查在模板中存在。"""
        self.assertIn("module_disabled", self.tmpl,
                       "模板应包含 module_disabled 条件渲染")

    def test_llm_enabled_guard(self):
        """LLM 启用/禁用守卫在模板中存在。"""
        self.assertIn("llm_enabled", self.tmpl,
                       "模板应包含 llm_enabled 条件守卫")

    def test_news_section_guard(self):
        """新闻章节守卫在模板中存在。"""
        self.assertIn("news_data", self.tmpl,
                       "模板应包含 news_data 条件守卫")

    def test_footer_version_and_time(self):
        """页脚含版本号和生成时间占位符。"""
        self.assertIn("app_version", self.tmpl,
                       "模板页脚应包含 app_version 变量")
        self.assertIn("{{ now }}", self.tmpl,
                       "模板页脚应包含生成时间 now 变量")


if __name__ == "__main__":
    unittest.main()
