# -*- coding: utf-8 -*-
"""Web 工作台暗色主题与组件状态矩阵静态断言（DESIGN.md 同款契约）。

读取 src/static/web 三件套源文本（无浏览器）：
- style.css 暗色变量块覆盖共享角色 + 状态矩阵选择器就位
- index.html 主题防闪脚本先于样式表 + 切换按钮
- main.js 存储键与报告 theme.js 动态对表（偏好跨页共享）、data-theme 读写闭环
- 空态挂点全部带 empty-note 类（status-busy 裸类为零）
"""

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]

REPO_ROOT = Path(__file__).resolve().parents[4]
WEB = REPO_ROOT / "src/static/web"
STYLE_CSS = WEB / "style.css"
INDEX_HTML = WEB / "index.html"
MAIN_JS = WEB / "main.js"
REPORT_THEME_JS = REPO_ROOT / "src/static/theme.js"

# 暗色块必须覆盖的共享角色（子集断言，不锁总数）
REQUIRED_DARK_ROLES = [
    "bg",
    "surface",
    "border",
    "text",
    "text-secondary",
    "ok",
    "warn",
    "error",
]

# 状态矩阵必须就位的选择器（子集断言）
REQUIRED_MATRIX_SELECTORS = [
    '[data-theme="dark"]',
    ".theme-toggle[aria-pressed=",
    ":focus-visible",
    '.btn[aria-busy="true"]',
    ".has-error",
    ".field-error",
    ".empty-note",
    "a:hover",
]


def _dark_block(css: str) -> str:
    m = re.search(r'\[data-theme="dark"\]\s*\{(.*?)\}', css, re.S)
    assert m, "style.css 缺暗色变量块"
    return m.group(1)


class TestDarkThemeVariables:
    def test_dark_block_covers_shared_roles(self):
        css = STYLE_CSS.read_text(encoding="utf-8")
        block = _dark_block(css)
        defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", block))
        missing = [r for r in REQUIRED_DARK_ROLES if f"--{r}" not in defined]
        assert not missing, f"暗色块缺共享角色: {missing}"

    def test_dark_component_overrides_present(self):
        css = STYLE_CSS.read_text(encoding="utf-8")
        for sel in ('[data-theme="dark"] .upload-zone', '[data-theme="dark"] .formal-warning'):
            assert sel in css, f"暗色组件适配缺失: {sel}"


class TestStateMatrixSelectors:
    def test_matrix_selectors_present(self):
        css = STYLE_CSS.read_text(encoding="utf-8")
        missing = [s for s in REQUIRED_MATRIX_SELECTORS if s not in css]
        assert not missing, f"状态矩阵选择器缺失: {missing}"


class TestThemeSwitchMarkup:
    def test_anti_flash_before_stylesheet(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        flash = html.find("investor-theme-dark")
        sheet = html.find('rel="stylesheet"')
        assert 0 < flash < sheet, "防闪脚本须先于样式表加载"

    def test_toggle_button_present(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        assert 'id="theme-toggle"' in html
        assert 'aria-pressed="false"' in html

    def test_toggle_button_inside_tab_bar(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        inner = html.split('class="tab-bar-inner"', 1)[1]
        assert "theme-toggle" in inner.split("</nav>", 1)[0], "切换钮应在 tab-bar-inner 内（粘顶常驻）"


class TestThemeJsParity:
    """main.js 与报告 theme.js 存储键同源（偏好跨页共享）。"""

    @staticmethod
    def _report_key() -> str:
        m = re.search(
            r"STORAGE_KEY\s*=\s*'([^']+)'",
            REPORT_THEME_JS.read_text(encoding="utf-8"),
        )
        assert m, "报告 theme.js 缺 STORAGE_KEY"
        return m.group(1)

    def test_storage_key_shared_with_report(self):
        report_key = self._report_key()
        main_js = MAIN_JS.read_text(encoding="utf-8")
        assert f"var KEY = '{report_key}';" in main_js, f"工作台存储键须与报告 theme.js 同值: {report_key}"

    def test_data_theme_write_and_persist(self):
        main_js = MAIN_JS.read_text(encoding="utf-8")
        assert "setAttribute('data-theme', 'dark')" in main_js
        assert "removeAttribute('data-theme')" in main_js
        assert re.search(r"localStorage\.setItem\(KEY, dark \? '1' : '0'\)", main_js)

    def test_aria_busy_closed_loop(self):
        main_js = MAIN_JS.read_text(encoding="utf-8")
        assert "setAttribute('aria-busy', 'true')" in main_js
        assert "removeAttribute('aria-busy')" in main_js


class TestEmptyStateHooks:
    def test_status_busy_points_carry_empty_note(self):
        """所有 p 空态挂点必须带 empty-note 类（裸类为零；busy 进行中态用独立变量不在此列）。"""
        main_js = MAIN_JS.read_text(encoding="utf-8")
        bare = [m for m in re.findall(r"p\.className = '([^']*status-busy[^']*)'", main_js) if "empty-note" not in m]
        assert bare == [], f"空态挂点缺 empty-note 类: {bare}"
        assert "empty-note" in main_js, "空态挂点为空"
