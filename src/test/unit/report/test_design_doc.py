# -*- coding: utf-8 -*-
"""设计语言契约（仓库根 DESIGN.md）结构守卫。

契约是 UI 改动的首个读取入口，断言其骨架不漂移：
必需节子集存在、护栏条目连续编号且 DO/DON'T 对偶、角色族覆盖、
文内引用的实现文件真实存在。新增节/新增护栏不破坏断言（子集关系）。
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

REPO_ROOT = Path(__file__).resolve().parents[4]
DESIGN_DOC = REPO_ROOT / "DESIGN.md"

# 契约必需节（子集断言：只防删除/改名，不锁总数）
REQUIRED_SECTIONS = [
    "Overview",
    "Colors",
    "Typography",
    "Components",
    "Layout",
    "Elevation",
    "Responsive",
    "Data States",
    "Do's and Don'ts",
    "Iteration Guide",
    "Known Gaps",
]

# 颜色角色族必须覆盖的语义域（子集断言）
REQUIRED_COLOR_FAMILIES = [
    "Surface 阶梯",
    "Ink 层级",
    "Border 阶",
    "状态语义",
    "涨跌语义",
    "Chart 专用",
]

# 字阶类别（子集断言）
REQUIRED_TYPE_SCALE = ["章节标题", "正文", "表格", "脚注"]


def _read() -> str:
    assert DESIGN_DOC.exists(), f"设计契约缺失: {DESIGN_DOC}"
    return DESIGN_DOC.read_text(encoding="utf-8")


class TestDesignDocStructure:
    """骨架与内容契约。"""

    def test_required_sections_present(self):
        text = _read()
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        missing = [s for s in REQUIRED_SECTIONS if not any(s in h for h in headings)]
        assert not missing, f"DESIGN.md 缺契约节: {missing}"

    def test_color_families_covered(self):
        text = _read()
        for family in REQUIRED_COLOR_FAMILIES:
            assert family in text, f"Colors 角色族缺失: {family}"

    def test_type_scale_categories_covered(self):
        text = _read()
        for cat in REQUIRED_TYPE_SCALE:
            assert cat in text, f"Typography 字阶类别缺失: {cat}"


class TestGuardrailEntries:
    """Do/Don't 护栏条目结构（与样式机检同源）。"""

    @staticmethod
    def _guardrail_items(text: str) -> list[str]:
        section = text.split("## Do's and Don'ts", 1)[1].split("\n## ", 1)[0]
        return [ln for ln in section.splitlines() if ln and ln[0].isdigit() and ". **DO**" in ln]

    def test_guardrail_numbering_contiguous(self):
        items = self._guardrail_items(_read())
        assert items, "护栏条目为空"
        numbers = [int(ln.split(".", 1)[0]) for ln in items]
        assert numbers == list(range(1, len(numbers) + 1)), f"护栏编号不连续: {numbers}"

    def test_guardrail_do_dont_pairs(self):
        for ln in self._guardrail_items(_read()):
            assert "**DO**" in ln and "**DON'T**" in ln, f"护栏缺 DO/DON'T 对偶: {ln[:60]}"


class TestReferencedFilesExist:
    """文内引用的实现文件真实存在（防文档腐烂）。"""

    REFS = [
        "src/static/tmpl/report_template.html",
        "src/static/web/style.css",
        "src/static/theme.js",
        "docs/managements/plan.md",
    ]

    def test_referenced_paths_exist(self):
        for rel in self.REFS:
            assert (REPO_ROOT / rel).exists(), f"DESIGN.md 引用路径不存在: {rel}"
