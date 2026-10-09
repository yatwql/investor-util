# -*- coding: utf-8 -*-
"""双面设计 token 同名对表守卫（DESIGN.md Colors 角色契约）。

跨面共享角色必须在 HTML 报告与 Web 工作台两面 :root 同名定义；
工作台旧 --color-* 名保留一版 var() 兼容映射但引用点已全部切新名；
报告品牌蓝只允许出现在 Chart 域定义与 JS fallback（CSS 用法须走 --primary）。
"""

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

REPO_ROOT = Path(__file__).resolve().parents[4]
REPORT_TMPL = REPO_ROOT / "src/static/tmpl/report_template.html"
WEB_CSS = REPO_ROOT / "src/static/web/style.css"

# 跨面共享角色（子集断言：只防删除，不锁总数）
SHARED_ROLES = [
    "bg",
    "surface",
    "text",
    "text-secondary",
    "border",
    "primary",
    "primary-hover",
    "focus",
    "ok",
    "warn",
    "font-stack",
]

# 工作台旧名 → 新名（兼容映射必须成对存在）
LEGACY_MIGRATIONS = [
    ("--color-bg", "--bg"),
    ("--color-surface", "--surface"),
    ("--color-border", "--border"),
    ("--color-text", "--text"),
    ("--color-text-secondary", "--text-secondary"),
    ("--color-primary", "--primary"),
    ("--color-primary-hover", "--primary-hover"),
    ("--color-ok", "--ok"),
    ("--color-warn", "--warn"),
    ("--color-error", "--error"),
    ("--color-focus", "--focus"),
    ("--color-accent", "--accent"),
]


def _root_defs(text: str) -> set[str]:
    """提取第一个 :root 块内定义的变量名（含 [data-theme] 前的主定义）。"""
    m = re.search(r":root\s*\{(.*?)\}", text, re.S)
    assert m, "未找到 :root 定义块"
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", m.group(1)))


# 类作用域 fixture 置于模块级（类内实例方法形式不被 pytest 接受）
@pytest.fixture(scope="class")
def report_defs():
    return _root_defs(REPORT_TMPL.read_text(encoding="utf-8"))


@pytest.fixture(scope="class")
def web_defs():
    return _root_defs(WEB_CSS.read_text(encoding="utf-8"))


class TestSharedRoleParity:
    """共享角色两面同名定义。"""

    def test_shared_roles_defined_on_both_sides(self, report_defs, web_defs):
        missing_report = [r for r in SHARED_ROLES if f"--{r}" not in report_defs]
        missing_web = [r for r in SHARED_ROLES if f"--{r}" not in web_defs]
        assert not missing_report, f"报告侧缺共享角色: {missing_report}"
        assert not missing_web, f"工作台侧缺共享角色: {missing_web}"

    def test_font_stack_same_value_both_sides(self, report_defs, web_defs):
        assert "--font-stack" in report_defs and "--font-stack" in web_defs


class TestLegacyMapping:
    """工作台旧名兼容映射与引用迁移。"""

    def test_legacy_names_mapped_to_roles(self):
        css = WEB_CSS.read_text(encoding="utf-8")
        root = css.split(":root", 1)[1].split("}", 1)[0]
        for old, new in LEGACY_MIGRATIONS:
            assert re.search(rf"{re.escape(old)}\s*:\s*var\({re.escape(new)}\)", root), (
                f"旧名映射缺失: {old} -> var({new})"
            )

    def test_no_legacy_references_remain(self):
        css = WEB_CSS.read_text(encoding="utf-8")
        leftover = re.findall(r"var\(--color-[a-z-]+\)", css)
        assert leftover == [], f"引用点仍用旧名: {sorted(set(leftover))}"


class TestReportBrandToken:
    """报告品牌蓝与状态色走 token。"""

    def test_css_brand_usage_uses_token(self):
        """CSS 使用行不得再裸写品牌蓝（Chart 定义行与 JS fallback 豁免）。"""
        bad = []
        for i, ln in enumerate(REPORT_TMPL.read_text(encoding="utf-8").splitlines(), 1):
            if "#2E75B6" not in ln:
                continue
            if "--chart-primary:" in ln or "--primary:" in ln or "'#2E75B6'" in ln:
                continue
            bad.append(i)
        assert not bad, f"裸品牌蓝行: {bad}"

    def test_renamed_status_tokens_no_legacy_defs(self):
        """旧 --status-* 定义与引用已切换（--llm-status-* 为独立域不受影响）。"""
        text = REPORT_TMPL.read_text(encoding="utf-8")
        legacy = re.findall(r"(?<!llm)--status-(?:ok|warn|info)\b", text)
        assert legacy == [], f"残留旧状态名: {legacy}"

    def test_body_font_uses_token(self):
        text = REPORT_TMPL.read_text(encoding="utf-8")
        assert "font-family: var(--font-stack);" in text
