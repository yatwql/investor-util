"""终端文本宽度与盒线面板排版单元测试。

缺陷场景：面板行原以 `len()` 按码点补白，中文/全角字符占 2 列却只算 1，
含中文的行因此比含英文的行短，盒线右边框参差不齐；同一面板的上下边框、
分隔线、内容行又各写各的补白数，右边框对不到同一列。本文件锁定
`text_layout` 的宽度口径与「一个面板内所有行等宽」这条不变式。
"""

from __future__ import annotations

import pytest

from src.python.tui.text_layout import (
    MIN_FIELD_WIDTH,
    display_width,
    pad_right,
    render_panel,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_ui]


class TestDisplayWidth:
    """display_width: 按东亚宽度计列，而非码点数。"""

    def test_ascii_counts_one_column_per_char(self):
        """半角字符每字符 1 列。"""
        assert display_width("abc123") == 6

    def test_cjk_counts_two_columns_per_char(self):
        """中文每字 2 列——`len()` 在此处会少算一半。"""
        assert display_width("配置") == 4
        assert display_width("配置支持") == 8

    def test_mixed_width(self):
        """中英混排按各自宽度累加。"""
        assert display_width("配置LLM章节") == 4 + 3 + 4

    def test_ansi_color_sequences_are_not_counted(self):
        """ANSI 颜色序列不占显示列（着色开启时若按可见字符计会把宽度算多）。"""
        assert display_width("\033[92m开启\033[0m") == 4

    def test_combining_marks_are_not_counted(self):
        """组合字符附着在前一字符上，不额外占列。"""
        assert display_width("é") == 1

    def test_empty_string(self):
        """空串宽度为 0。"""
        assert display_width("") == 0


class TestPadRight:
    """pad_right: 按显示宽度补白。"""

    def test_pads_cjk_to_column(self):
        """中文按 2 列计，补到 10 列时补 6 个空格。"""
        assert pad_right("中文", 10) == "中文" + " " * 6

    def test_does_not_truncate_overlong_text(self):
        """已超宽原样返回，不截断内容。"""
        assert pad_right("超长内容超长内容", 4) == "超长内容超长内容"

    def test_exact_fit_adds_nothing(self):
        """正好等宽时不补白。"""
        assert pad_right("中文", 4) == "中文"


class TestRenderPanel:
    """render_panel: 一个面板内所有行等宽，右边框对齐同一列。"""

    @staticmethod
    def _widths(lines: list[str]) -> set[int]:
        return {display_width(line) for line in lines}

    def test_all_lines_share_one_width(self):
        """上下边框、分隔线、内容行（含中文行与英文行）宽度一致。"""
        lines = render_panel(
            "配置报告可选章节",
            [
                "1. 基金深度分析 [启用]",
                "2. 市场新闻 [禁用]",
                None,
                "6. 报告增强子模块（数据质量/行业Beta）",
                "0. 返回主菜单",
            ],
        )
        assert len(self._widths(lines)) == 1, f"面板各行宽度不一致：{self._widths(lines)}"

    def test_short_panel_still_uniform(self):
        """内容很短时面板不缩到标题以下，各行仍等宽。"""
        lines = render_panel("配置持仓匿名化", ["► 1. 关闭"])
        assert len(self._widths(lines)) == 1
        assert display_width(lines[0]) >= MIN_FIELD_WIDTH

    def test_field_grows_to_fit_longest_row(self):
        """最长行决定面板宽度——超宽行不被截断，也不撑破右边框。"""
        long_row = "6. " + "很长的章节说明" * 8
        lines = render_panel("配置报告可选章节", [long_row])
        assert len(self._widths(lines)) == 1
        assert display_width(lines[0]) > MIN_FIELD_WIDTH

    def test_none_row_renders_full_width_divider(self):
        """None 渲染为一条撑满内区的分隔线。"""
        lines = render_panel("标题", ["内容", None])
        divider = lines[2]
        assert divider.startswith("  │─") and divider.endswith("─│")
        assert len(self._widths(lines)) == 1

    def test_empty_row_pads_to_full_width(self):
        """空串渲染为空白内文行（左右边框仍在原位）。"""
        lines = render_panel("标题", ["内容", ""])
        blank = lines[2]
        assert blank.strip(" │") == ""
        assert display_width(blank) == display_width(lines[0])

    def test_title_alone_without_rows(self):
        """无内容行时只渲染上下边框。"""
        lines = render_panel("空面板")
        assert len(lines) == 2
        assert len(self._widths(lines)) == 1

    def test_every_line_is_box_shaped(self):
        """每行都以左边框起、右边框收（无半截行）。"""
        for line in render_panel("配置持仓匿名化", ["当前模式: off", None, "► 1. 关闭", "0. 返回主菜单"]):
            assert line.startswith("  ┌") or line.startswith("  │") or line.startswith("  └")
            assert line.endswith("┐") or line.endswith("│") or line.endswith("┘")
