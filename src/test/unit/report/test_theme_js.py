"""暗色模式 theme.js 静态断言测试（主题切换）。

直接读取 src/static/theme.js 源文本，断言关键机制存在：
  - localStorage 存储键 investor-theme-dark（持久化范式）
  - beforeprint/afterprint 捕获阶段监听（先于 chart-print.js 冒泡快照执行）
  - Chart.getChart 全局 API 收集已有图表（无需改动 chart-print/chart-common）
  - window.ThemeSwitcher 对外暴露（测试/调试）
  - ES5 保守语法（兼容微信 X5：var/function，无箭头函数）

运行：
  cd D:/codebase/zoo/investor-util
  python -m pytest src/test/unit/report/test_theme_js.py -v
"""

from __future__ import annotations

import os
import unittest

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_THEME_JS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "theme.js"),
)


def _read_theme_js() -> str:
    """读取 theme.js 源码（UTF-8）。"""
    with open(_THEME_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


class TestThemeJsStatic(unittest.TestCase):
    """theme.js 关键机制静态断言（文本层校验，无需浏览器）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.src = _read_theme_js()

    def test_storage_key_defined(self) -> None:
        """localStorage 存储键为 investor-theme-dark（与 toc.js 同款命名范式）。"""
        self.assertIn("investor-theme-dark", self.src, "应定义主题持久化存储键")

    def test_storage_key_docstring_consistent(self) -> None:
        """文件头注释应说明存储键用途（文档与代码一致性）。"""
        self.assertIn("localStorage", self.src, "文件头应说明 localStorage 持久化")

    def test_beforeprint_capture_phase(self) -> None:
        """beforeprint 以捕获阶段监听（addEventListener 第 3 参 true）。

        关键：捕获阶段先于 chart-print.js 的冒泡阶段快照执行，
        深色下可先切浅色并同步重绘，使 toBase64Image 抓到浅色像素。
        """
        # 找到 beforeprint 的 addEventListener 调用（多行），断言整段以 `}, true);` 结尾（捕获阶段）
        marker = "window.addEventListener('beforeprint', function () {"
        start = self.src.find(marker)
        self.assertGreater(start, -1, "应存在 beforeprint 的 addEventListener 监听")
        # 从监听起点向后取 300 字符（覆盖函数体 + `}, true);` 收尾）
        segment = self.src[start : start + 300]
        self.assertIn("}, true);", segment, "beforeprint 监听应使用捕获阶段（第 3 参 true）")
        # 存在 afterprint 恢复监听
        self.assertIn("afterprint", self.src, "应存在 afterprint 恢复监听（打印后恢复深色）")

    def test_chart_getchart_collection(self) -> None:
        """用 Chart.getChart 收集已有图表实例（Chart.js v4 全局 API）。

        相比遍历内部实例数组，getChart 无需改动 chart-print.js/chart-common.js，
        对 report（经 ChartPrint 注册）与 whatif（未加载 chart-print.js）通用。
        """
        self.assertIn("Chart.getChart", self.src, "应使用 Chart.getChart 收集图表")
        self.assertIn("querySelectorAll('canvas')", self.src, "应遍历全部 canvas")

    def test_theme_switcher_exposed(self) -> None:
        """对外暴露 window.ThemeSwitcher（供测试/调试/扩展）。"""
        self.assertIn("window.ThemeSwitcher", self.src, "应暴露 ThemeSwitcher 命名空间")
        self.assertIn("setTheme", self.src, "ThemeSwitcher 应含 setTheme 方法")

    def test_es5_conservative_syntax(self) -> None:
        """ES5 保守语法：无箭头函数、无 const/let（兼容微信 X5 内核）。"""
        self.assertNotIn("=>", self.src, "不应使用箭头函数（ES6）")
        self.assertNotIn("const ", self.src, "不应使用 const（ES6）")
        self.assertNotIn("let ", self.src, "不应使用 let（ES6）")

    def test_guard_for_chart_absent(self) -> None:
        """window.Chart 缺失时安全降级（打印协调不崩溃）。"""
        self.assertIn("typeof window.Chart === 'undefined'", self.src, "应守卫 window.Chart 缺失")


if __name__ == "__main__":
    unittest.main()
