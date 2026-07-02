"""LLM 内容 Excel 写入模块单元测试。

测试目标：
  - _strip_html — HTML 标签剥离
  - _write_content_sheet — 段落分行、wrap_text、行高、列宽、footer 提取
  - write_llm_sheets — 多页签写入 + 禁用模块处理

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_llm_content -v
"""

from __future__ import annotations

import unittest
from math import ceil

from openpyxl import Workbook

from src.python.report.llm_content import (
    _ROW_HEIGHT_MIN,
    _ROW_HEIGHT_PER_LINE,
    _CHARS_PER_LINE,
    _calc_row_height,
    _strip_html,
    _extract_footer_text,
    _write_content_sheet,
    write_llm_sheets,
)
from src.python.report.styles import CONTENT_FONT, TITLE_FILL, TITLE_FONT
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]



# ═══════════════════════════════════════════════════════════
#  _calc_row_height
# ═══════════════════════════════════════════════════════════


class TestCalcRowHeight(unittest.TestCase):
    """测试行高估算函数。"""

    def test_empty(self) -> None:
        self.assertEqual(_calc_row_height(""), _ROW_HEIGHT_MIN)

    def test_short_text(self) -> None:
        """短文本 → 最小行高。"""
        text = "短文本"
        self.assertEqual(_calc_row_height(text), _ROW_HEIGHT_MIN)

    def test_long_text(self) -> None:
        """超长文本 → 行高按行数倍乘。"""
        text = "中" * 120  # 120 中文字符 ≈ 3 行
        expected = ceil(120 / _CHARS_PER_LINE) * _ROW_HEIGHT_PER_LINE
        self.assertEqual(_calc_row_height(text), expected)

    def test_boundary(self) -> None:
        """正好 _CHARS_PER_LINE 个字符 → 最小行高。"""
        text = "中" * _CHARS_PER_LINE
        self.assertEqual(_calc_row_height(text), _ROW_HEIGHT_MIN)


# ═══════════════════════════════════════════════════════════
#  _strip_html
# ═══════════════════════════════════════════════════════════


class TestStripHtml(unittest.TestCase):
    """测试 HTML 标签剥离。"""

    def test_plain_text(self) -> None:
        self.assertEqual(_strip_html("hello"), "hello")

    def test_strip_p_tag(self) -> None:
        self.assertEqual(_strip_html("<p>内容</p>"), "内容")

    def test_strip_strong(self) -> None:
        self.assertEqual(_strip_html("<strong>粗体</strong>"), "粗体")

    def test_strip_nested(self) -> None:
        html = "<p>这是 <strong>粗体</strong> 和 <em>斜体</em></p>"
        self.assertEqual(_strip_html(html), "这是 粗体 和 斜体")

    def test_html_entity_unchanged(self) -> None:
        """HTML 实体（如 &amp;）保留原样——已知行为。"""
        self.assertEqual(_strip_html("A &amp; B"), "A &amp; B")

    def test_none_input(self) -> None:
        self.assertEqual(_strip_html(None), "")

    def test_empty_string(self) -> None:
        self.assertEqual(_strip_html(""), "")


# ═══════════════════════════════════════════════════════════
#  _write_content_sheet
# ═══════════════════════════════════════════════════════════


class TestWriteContentSheet(unittest.TestCase):
    """测试单个 LLM 分析章节的写入行为。"""

    def setUp(self):
        self.wb = Workbook()

    def _write_and_get_sheet(self, content=None):
        """写入内容并返回 worksheet 对象。"""
        ws = self.wb.create_sheet()
        _write_content_sheet(ws, "测试页签", content)
        return ws

    def test_title_row(self):
        """第 1 行标题 — 合并 A1:B1，使用 TITLE_FONT 和 TITLE_FILL。"""
        ws = self._write_and_get_sheet(content="一段落")
        cell = ws.cell(row=1, column=1)
        self.assertEqual(cell.value, "测试页签")
        self.assertEqual(cell.font.name, TITLE_FONT.name)
        self.assertEqual(cell.fill.fgColor.rgb, TITLE_FILL.fgColor.rgb)

    def test_single_paragraph(self):
        """单段落 → 写入第 2 行，wrap_text=True。"""
        ws = self._write_and_get_sheet(content="单段落内容")
        cell = ws.cell(row=2, column=1)
        self.assertEqual(cell.value, "单段落内容")
        self.assertTrue(cell.alignment.wrap_text)

    def test_multi_paragraphs(self):
        """三个段落 → A2/A4/A6 各一段（A3/A5 空行间距），A7 无内容。"""
        content = "<p>第一段</p>\n\n<p>第二段</p>\n\n<p>第三段</p>"
        ws = self._write_and_get_sheet(content=content)

        self.assertEqual(ws.cell(row=2, column=1).value, "第一段")
        self.assertEqual(ws.cell(row=4, column=1).value, "第二段")
        self.assertEqual(ws.cell(row=6, column=1).value, "第三段")
        # 空行无值
        self.assertIsNone(ws.cell(row=3, column=1).value)
        self.assertIsNone(ws.cell(row=5, column=1).value)

    def test_content_none_placeholder(self):
        """content=None → A2 写入占位符。"""
        ws = self._write_and_get_sheet(content=None)
        cell = ws.cell(row=2, column=1)
        self.assertIn("LLM API Key", str(cell.value))

    def test_wrap_text_enabled(self):
        """每行内容单元格启用文本换行。"""
        ws = self._write_and_get_sheet(content="段落一\n\n段落二")
        for r in (2, 4):
            cell = ws.cell(row=r, column=1)
            self.assertTrue(cell.alignment.wrap_text,
                            f"Row {r} wrap_text should be True")

    def test_paragraph_font(self):
        """段落使用 CONTENT_FONT。"""
        ws = self._write_and_get_sheet(content="测试内容")
        cell = ws.cell(row=2, column=1)
        self.assertEqual(cell.font.size, CONTENT_FONT.size)
        self.assertEqual(cell.font.color.rgb, CONTENT_FONT.color.rgb)

    def test_row_height_short(self):
        """短段落行高 = 最小行高。"""
        ws = self._write_and_get_sheet(content="短")
        self.assertGreaterEqual(
            ws.row_dimensions[2].height, _ROW_HEIGHT_MIN)

    def test_column_width_fixed(self):
        """A 列宽度固定。"""
        ws = self._write_and_get_sheet(content="测试内容")
        # 默认 openpyxl 宽度约 8.43，此处应被设为固定值 80
        width = ws.column_dimensions["A"].width
        self.assertIsNotNone(width)
        self.assertEqual(width, 80)

    def test_freeze_panes(self):
        """冻结首行。"""
        ws = self._write_and_get_sheet(content="测试")
        self.assertEqual(ws.freeze_panes, "A2")


# ═══════════════════════════════════════════════════════════
#  write_llm_sheets
# ═══════════════════════════════════════════════════════════


class TestWriteLlmSheets(unittest.TestCase):
    """测试 write_llm_sheets 集成行为。"""

    def setUp(self):
        self.wb = Workbook()

    def _get_llm_sheets(self):
        """返回 write_llm_sheets 创建的四个 sheet（跳过 Workbook 默认 sheet）。"""
        return self.wb.worksheets[-4:]

    def test_sheet_titles(self):
        """四个 sheet 标题正确。"""
        write_llm_sheets(self.wb, ("<p>宏观</p>", "<p>复盘</p>", None, None))
        sheet_names = [ws.title for ws in self.wb.worksheets]
        self.assertIn("8.全球政经局势", sheet_names)
        self.assertIn("9.智囊团深度复盘", sheet_names)
        self.assertIn("10.持仓体检报告", sheet_names)
        self.assertIn("11.穿透深度分析", sheet_names)

    def test_return_text_quad(self):
        """返回 (text7, text8, text9, textA) 纯文本四元组。"""
        text7, text8, text9, textA = write_llm_sheets(
            self.wb, ("<p>全球政经局势</p>", "<p>复盘内容</p>", "<p>持仓体检报告</p>", "<p>穿透深度分析</p>"))
        self.assertEqual(text7, "全球政经局势")
        self.assertEqual(text8, "复盘内容")
        self.assertEqual(text9, "持仓体检报告")
        self.assertEqual(textA, "穿透深度分析")

    def test_content_none(self):
        """content=(None, None, None, None) → 占位符，不崩溃。"""
        text7, text8, text9, textA = write_llm_sheets(self.wb, (None, None, None, None))
        self.assertEqual(text7, "")
        self.assertEqual(text8, "")
        self.assertEqual(text9, "")
        self.assertEqual(textA, "")
        ws7, ws8, ws9, wsA = self._get_llm_sheets()
        self.assertIn("LLM API Key", str(ws7.cell(row=2, column=1).value or ""))
        self.assertIn("LLM API Key", str(ws8.cell(row=2, column=1).value or ""))


class TestWriteLlmSheetsDisabled(unittest.TestCase):
    """测试 write_llm_sheets 在模块禁用时的行为。"""

    def setUp(self):
        self.wb = Workbook()

    def _get_llm_sheets(self):
        return self.wb.worksheets

    def test_disabled_global_macro_skips_sheet(self):
        """global_macro 禁用 → 不创建该页签，其他页签正常。"""
        from src.python.llm.prompts import _LLM_MODULE_FAILURE, FAIL_REASON_DISABLED
        # 清除可能残留的状态
        _LLM_MODULE_FAILURE.clear()
        _LLM_MODULE_FAILURE["global_macro"] = FAIL_REASON_DISABLED
        try:
            text7, text8, text9, textA = write_llm_sheets(
                self.wb, ("<p>宏观</p>", "<p>复盘</p>", "<p>体检</p>", "<p>穿透</p>"))
            # 禁用模块返回空文本
            self.assertEqual(text7, "")
            self.assertNotEqual(text8, "")
            # 只创建了 3 个新 sheet（默认 sheet + 3 个非禁用）
            sheets = self._get_llm_sheets()
            sheet_titles = [s.title for s in sheets]
            self.assertNotIn("8.全球政经局势", sheet_titles)
            self.assertIn("9.智囊团深度复盘", sheet_titles)
            self.assertIn("10.持仓体检报告", sheet_titles)
            self.assertIn("11.穿透深度分析", sheet_titles)
        finally:
            _LLM_MODULE_FAILURE.clear()

    def test_all_disabled_no_sheets_created(self):
        """所有 4 个模块都禁用 → 不创建任何 LLM sheet。"""
        from src.python.llm.prompts import _LLM_MODULE_FAILURE, FAIL_REASON_DISABLED

        _LLM_MODULE_FAILURE.clear()
        _LLM_MODULE_FAILURE.update(
            global_macro=FAIL_REASON_DISABLED,
            expert_review=FAIL_REASON_DISABLED,
            health_check=FAIL_REASON_DISABLED,
            penetration_deep=FAIL_REASON_DISABLED,
        )
        try:
            text7, text8, text9, textA = write_llm_sheets(
                self.wb, (None, None, None, None))
            # 全部返回空文本
            self.assertEqual(text7, "")
            self.assertEqual(text8, "")
            self.assertEqual(text9, "")
            self.assertEqual(textA, "")
            # 只有默认 sheet，没有新创建的 LLM sheet
            sheets = self._get_llm_sheets()
            sheet_titles = [s.title for s in sheets]
            for title in ["8.全球政经局势", "9.智囊团深度复盘",
                          "10.持仓体检报告", "11.穿透深度分析"]:
                self.assertNotIn(title, sheet_titles)
        finally:
            _LLM_MODULE_FAILURE.clear()


# ═══════════════════════════════════════════════════════════
#  _extract_footer_text
# ═══════════════════════════════════════════════════════════


class TestExtractFooterText(unittest.TestCase):
    """测试从 HTML 中提取底部 LLM 标识行。"""

    def test_none_input(self) -> None:
        self.assertEqual(_extract_footer_text(None), "")

    def test_empty_input(self) -> None:
        self.assertEqual(_extract_footer_text(""), "")

    def test_no_footer(self) -> None:
        """无 footer 标签 → 空字符串。"""
        html = "<p>纯内容</p>\n\n<p>更多内容</p>"
        self.assertEqual(_extract_footer_text(html), "")

    def test_extract_token_footer(self) -> None:
        """提取包含模型和 Token 用量的 footer。"""
        html = (
            '<p>全球政经局势</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '模型：gpt-4o | Token 用量：输入 1,234 / 输出 567 = 1,801'
            '</p>'
        )
        self.assertEqual(
            _extract_footer_text(html),
            "模型：gpt-4o | Token 用量：输入 1,234 / 输出 567 = 1,801",
        )

    def test_extract_footer_with_cost(self) -> None:
        """提取含估算费用和 Extended Thinking 的 footer。"""
        html = (
            '<p>内容</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '模型：claude-sonnet-4 | Token 用量：输入 5,000 / 输出 1,000 = 6,000 | '
            '估算费用：$0.015 | Extended Thinking'
            '</p>'
        )
        result = _extract_footer_text(html)
        self.assertIn("模型：claude-sonnet-4", result)
        self.assertIn("Token 用量：输入 5,000 / 输出 1,000 = 6,000", result)
        self.assertIn("估算费用：$0.015", result)
        self.assertIn("Extended Thinking", result)

    def test_extract_cache_footer(self) -> None:
        """提取缓存 footer。"""
        html = (
            '<p>内容</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '本次使用LLM缓存，未直接使用LLM服务能力'
            '</p>'
        )
        self.assertEqual(
            _extract_footer_text(html),
            "本次使用LLM缓存，未直接使用LLM服务能力",
        )

    def test_extract_cache_footer_with_thinking(self) -> None:
        """提取含 Extended Thinking 的缓存 footer。"""
        html = (
            '<p>内容</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '本次使用LLM缓存（原始模型：claude-sonnet-4） | Extended Thinking'
            '</p>'
        )
        result = _extract_footer_text(html)
        self.assertIn("本次使用LLM缓存", result)
        self.assertIn("Extended Thinking", result)

    def test_extract_last_of_multiple_footers(self) -> None:
        """多个 <p style='color:#888;font-size:12px'> 标签 → 提取最后一条（缓存提示）。"""
        html = (
            '<p>正文内容</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '模型：DeepSeek-V4-Flash | Token 用量：输入 3,200 / 输出 1,321 = 4,521 | '
            '估算费用：¥0.0063'
            '</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '本次使用LLM缓存（原始模型：DeepSeek-V4-Flash）'
            '</p>'
        )
        result = _extract_footer_text(html)
        self.assertIn("本次使用LLM缓存", result)
        self.assertNotIn("Token 用量", result)


# ═══════════════════════════════════════════════════════════
#  _write_content_sheet — unified footer
# ═══════════════════════════════════════════════════════════


class TestWriteContentSheetUnifiedFooter(unittest.TestCase):
    """测试 _write_content_sheet 中统一 footer 的行为。"""

    def setUp(self):
        self.wb = Workbook()

    def test_footer_extracted_from_html(self) -> None:
        """HTML 含 footer → 最后一行为 footer 纯文本。"""
        html = (
            '<p>全球政经局势</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '模型：gpt-4o | Token 用量：输入 1,234 / 输出 567 = 1,801 | '
            '估算费用：$0.005 | Extended Thinking'
            '</p>'
        )
        ws = self.wb.create_sheet()
        _write_content_sheet(ws, "测试", html)
        footer_cell = ws.cell(row=4, column=1)
        self.assertIn("模型：gpt-4o", str(footer_cell.value or ""))
        self.assertIn("Token 用量", str(footer_cell.value or ""))
        self.assertIn("估算费用：$0.005", str(footer_cell.value or ""))
        self.assertIn("Extended Thinking", str(footer_cell.value or ""))

    def test_footer_not_repeated_in_content(self) -> None:
        """footer 被排除在正文之外，避免重复。"""
        html = (
            '<p>内容段落</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '模型：gpt-4o | Token 用量：输入 100 / 输出 50 = 150'
            '</p>'
        )
        ws = self.wb.create_sheet()
        _write_content_sheet(ws, "测试", html)
        content_cell = ws.cell(row=2, column=1)
        self.assertEqual(content_cell.value, "内容段落")
        self.assertNotIn("模型", str(content_cell.value or ""))

    def test_cached_with_embedded_footer_uses_it(self) -> None:
        """缓存内容含嵌入式 footer → footer 正确展示。"""
        html = (
            '<p>缓存内容</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '本次使用LLM缓存，未直接使用LLM服务能力'
            '</p>'
        )
        ws = self.wb.create_sheet()
        _write_content_sheet(ws, "测试", html)
        footer_cell = ws.cell(row=4, column=1)
        self.assertIn("LLM缓存", str(footer_cell.value or ""))
        # 不应再有额外行
        self.assertIsNone(ws.cell(row=5, column=1).value)

    def test_dual_footer_cache_line_shown(self) -> None:
        """模型/Token footer + 缓存 footer 并存 → 缓存 footer 为末尾标识行。"""
        html = (
            '<p>正文段落</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '模型：DeepSeek-V4-Flash | Token 用量：输入 100 / 输出 50 = 150'
            '</p>\n\n'
            '<p style="color:#888;font-size:12px">'
            '本次使用LLM缓存（原始模型：DeepSeek-V4-Flash）'
            '</p>'
        )
        ws = self.wb.create_sheet()
        _write_content_sheet(ws, "测试", html)
        # 模型/Token 行在正文中（不会被排除，因为不是最后一段）
        content_cell_after_token = ws.cell(row=4, column=1)
        self.assertIn("模型：DeepSeek-V4-Flash", str(content_cell_after_token.value or ""))
        # 缓存提示为末尾 footer
        footer_cell = ws.cell(row=6, column=1)
        self.assertIn("本次使用LLM缓存", str(footer_cell.value or ""))
        self.assertNotIn("Token 用量", str(footer_cell.value or ""))


if __name__ == "__main__":
    unittest.main()
