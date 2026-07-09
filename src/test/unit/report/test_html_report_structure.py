"""HTML 报告 UI/UX 结构测试 — 导航/锚点/换行/CSS 排序。

覆盖场景：
  - 导航链接 ↔ section 容器一一对应（无断链/无悬空锚点）
  - 所有 section 的 CSS order 值唯一且与 section_numbers 一致
  - 不可见模块不在导航中出现
  - 自定义 section_order 下的排序正确性
  - llm_usage 始终强制末位

边缘/异常测试见 test_html_report_structure_edge.py。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/report/test_html_report_structure.py -v
"""

from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ── 常量 ──────────────────────────────────────────────────────

_TEMPLATE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "python", "tmpl", "report_template.html"),
)

# 16 个模块的期望 key（按默认顺序）
_ALL_KEYS_DEFAULT = [
    "summary", "market_value", "category", "penetration",
    "fund_performance",
    "fund_manager", "fund_overlap", "fund_concentration", "fund_style",
    "news_correlation", "early_warning",
    "global_macro", "expert_review", "health_check", "penetration_deep",
    "llm_usage",
]

_ALWAYS_KEYS = {"summary", "market_value", "category", "penetration", "fund_performance"}
_B_SERIES_KEYS = {"fund_manager", "fund_overlap", "fund_concentration", "fund_style"}
_NEWS_KEYS = {"news_correlation", "early_warning"}
_LLM_KEYS = {"global_macro", "expert_review", "health_check", "penetration_deep", "llm_usage"}

_REPORT_SECTION_DEFAULT: list[dict] = [
    {"key": "summary",            "name": "投资分析汇总",                     "number": 1},
    {"key": "market_value",       "name": "市值核算明细表",                   "number": 2},
    {"key": "category",           "name": "持仓分类表",                       "number": 3},
    {"key": "penetration",        "name": "资产穿透TOP10",                    "number": 4},
    {"key": "fund_performance",   "name": "基金业绩分析",                     "number": 5},
    {"key": "fund_manager",       "name": "基金经理变更监控",                 "number": 6},
    {"key": "fund_overlap",       "name": "持仓重合度矩阵",                   "number": 7},
    {"key": "fund_concentration", "name": "持仓集中度监控",                   "number": 8},
    {"key": "fund_style",         "name": "基金风格分析",                     "number": 9},
    {"key": "news_correlation",   "name": "财经新闻热点与持仓关联分析",        "number": 10},
    {"key": "early_warning",      "name": "智能预警",                         "number": 11},
    {"key": "global_macro",       "name": "全球政经局势",                     "number": 12},
    {"key": "expert_review",      "name": "智囊团深度复盘",                   "number": 13},
    {"key": "health_check",       "name": "持仓体检报告",                     "number": 14},
    {"key": "penetration_deep",   "name": "穿透深度分析",                     "number": 15},
    {"key": "llm_usage",          "name": "LLM API 用量",                    "number": 16},
]


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════


def _build_minimal_render_data(
    section_order: list[dict],
    section_numbers: dict[str, int],
    section_visible_dict: dict[str, bool],
) -> dict:
    """构建最小化模板渲染数据。

    根据 visible_set 自动填充 B 系列/新闻模块所需的 mock 数据结构，
    避免模板内 .get() 或 [] 操作因 None 值崩溃。

    Args:
        visible_set: 当前可见的模块 key 集合，用于决定哪些 mock 数据需要填充
    """
    visible_keys = {k for k, v in section_visible_dict.items() if v}

    data = {
        "now": "2026-07-05 12:00:00",
        "today": "2026-07-05",
        "trading_day": "2026-07-03",
        "total_mv": 0, "total_cost": 0, "total_profit": 0,
        "total_profit_rate": 0, "total_today_profit": 0, "today_profit_rate": 0,
        "categories": {}, "update_status": None,
        "a_indices": [], "us_indices": [],
        "accounts": {}, "account_totals": {},
        "cat_data": [], "penetration": None, "perf_data": [],
        "news_data": None, "news_llm_meta": None, "has_llm_analysis": False,
        "manager_analysis": None, "overlap_matrix": None,
        "concentration_analysis": None, "style_analysis": None,
        "llm_enabled": True,
        "global_macro": None, "expert_review": None,
        "health_check": None, "penetration_deep": None,
        "llm_session_usage": None, "early_warnings": None,
        "module_labels": {}, "module_disabled": {},
        "llm_module_info": [], "llm_endpoint": "",
        "cache_stats": None,
        "section_order": section_order,
        "section_numbers": section_numbers,
        "section_visible_dict": section_visible_dict,
    }

    # B 系列模块可见时，填充 mock 数据结构（模板内部 .get() 要求 dict 非 None）
    if visible_keys & _B_SERIES_KEYS:
        data["manager_analysis"] = {"first_check_summary": None, "results": []}
        data["overlap_matrix"] = {"fund_names": {}, "funds": [], "matrix": [], "pairs": []}
        data["concentration_analysis"] = {"results": []}
        data["style_analysis"] = {"results": []}

    # 新闻模块可见时，news_data 需为非 None list（模板隐式调用 |length）
    if visible_keys & _NEWS_KEYS:
        data["news_data"] = []
        data["early_warnings"] = None  # 模板内 is None 安全

    return data


def _render_template(render_data: dict) -> BeautifulSoup:
    """用 html_writer._ENV 渲染模板并返回 BeautifulSoup 对象。"""
    from src.python.report.html_jinja_env import _ENV

    # 注入 section_visible 闭包（与生产代码相同的 context 变量方式，不写入 _ENV.globals）
    _sv_dict = render_data.get("section_visible_dict", {})
    _sv_fn = lambda key, _d=_sv_dict: bool(_d.get(key, False))
    html = _ENV.get_template("report_template.html").render(
        **render_data, section_visible=_sv_fn)
    return BeautifulSoup(html, "html.parser")


def _get_section_id_from_href(href: str) -> str:
    """从 href="#sec-xxx" 提取 sec-xxx。"""
    if href.startswith("#"):
        return href[1:]
    return href


# ═══════════════════════════════════════════════════════════════
#  Test: Rendered Navigation Structure (default order)
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
#  Test: Rendered Navigation Structure (default order)
# ═══════════════════════════════════════════════════════════════


class TestHtmlNavStructure(unittest.TestCase):
    """HTML 报告导航结构测试 — 默认 ordering，全部可见。"""

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        # 所有模块可见（b_series 也给 True，因为我们要测结构完整性）
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    # ── Nav links ──────────────────────────────────────────────

    def test_nav_link_count(self):
        """导航链接数量应等于可见模块数（全部可见 = 16）。"""
        links = self.soup.select("nav.section-nav a")
        self.assertEqual(len(links), 16,
                         f"导航应有 16 个链接，实际 {len(links)}")

    def test_every_nav_link_has_corresponding_section(self):
        """每个导航链接的 href 指向一个存在的 section id。"""
        links = self.soup.select("nav.section-nav a")
        for link in links:
            href = link.get("href", "")
            section_id = _get_section_id_from_href(href)
            target = self.soup.find(id=section_id)
            self.assertIsNotNone(
                target,
                f"导航链接 href='{href}' 未找到对应的 section #{section_id}",
            )
            self.assertTrue(
                "section" in target.get("class", []),
                f"#{section_id} 不是 .section 容器（class={target.get('class')}）",
            )

    def test_no_duplicate_section_ids(self):
        """所有 section id 唯一，无重复。"""
        sections = self.soup.select("div.section")
        ids = [sec.get("id") for sec in sections if sec.get("id")]
        self.assertEqual(len(ids), len(set(ids)),
                         f"发现重复 section id: {set(i for i in ids if ids.count(i) > 1)}")

    # ── CSS order ──────────────────────────────────────────────

    def test_all_sections_have_unique_order(self):
        """所有 section 的 CSS order 值唯一。"""
        sections = self.soup.select("div.section")
        orders = []
        for sec in sections:
            style = sec.get("style", "")
            m = re.search(r"order:\s*(\d+)", style)
            self.assertIsNotNone(m, f"#{sec.get('id')} 缺少 order 样式: {style}")
            orders.append(int(m.group(1)))

        self.assertEqual(len(orders), len(set(orders)),
                         f"order 值不唯一: {set(o for o in orders if orders.count(o) > 1)}")

    def test_order_values_start_from_1(self):
        """order 值从 1 开始，无缺失。"""
        sections = self.soup.select("div.section")
        orders = set()
        for sec in sections:
            m = re.search(r"order:\s*(\d+)", sec.get("style", ""))
            if m:
                orders.add(int(m.group(1)))

        expected = set(range(1, len(sections) + 1))
        self.assertEqual(
            orders, expected,
            f"order 值不连续: 获得 {sorted(orders)}，期望 {sorted(expected)}",
        )

    def test_section_order_matches_numbers_dict(self):
        """section 的 order 值与 section_numbers 字典一致。"""
        sections = self.soup.select("div.section")
        for sec in sections:
            sec_id = sec.get("id", "")
            key = sec_id.replace("sec-", "")
            m = re.search(r"order:\s*(\d+)", sec.get("style", ""))
            self.assertIsNotNone(m, f"#{sec_id} 缺少 order")
            actual_order = int(m.group(1))
            expected_order = self.numbers.get(key)
            self.assertEqual(
                actual_order, expected_order,
                f"#{sec_id} order 为 {actual_order}，但 section_numbers['{key}'] = {expected_order}",
            )

    # ── Nav link text ──────────────────────────────────────────

    def test_nav_link_text_format(self):
        """导航链接文字格式：{number}、{name}。"""
        links = self.soup.select("nav.section-nav a")
        for link in links:
            href = link.get("href", "")
            key = href.replace("#sec-", "")
            expected = self.numbers.get(key)
            self.assertIsNotNone(expected, f"未知 key: {key}")
            # 文字应包含 "N、" 前缀
            text = link.get_text(strip=True)
            self.assertTrue(
                re.match(rf"^{expected}[、. ]", text),
                f"导航链接 '{text}' 格式异常，应为 '{expected}、...'",
            )

    def test_section_title_text_format(self):
        """section-title 文字格式：{number}、{name}。"""
        sections = self.soup.select("div.section")
        for sec in sections:
            sec_id = sec.get("id", "")
            key = sec_id.replace("sec-", "")
            title_div = sec.find("div", class_="section-title")
            if title_div is None:
                continue
            expected = self.numbers.get(key)
            text = title_div.get_text(strip=True)
            self.assertTrue(
                re.match(rf"^{expected}[、. ]", text),
                f"#{sec_id} 标题 '{text}' 格式异常，应为 '{expected}、...'",
            )

    # ── Nav as integer ─────────────────────────────────────────

    def test_all_default_keys_present(self):
        """默认配置下所有 16 个模块 key 都在导航中。"""
        links = self.soup.select("nav.section-nav a")
        link_keys = {link.get("href", "").replace("#sec-", "") for link in links}
        self.assertEqual(link_keys, set(_ALL_KEYS_DEFAULT),
                         f"导航缺失/多余 keys: 期望 {set(_ALL_KEYS_DEFAULT)}，实际 {link_keys}")


# ═══════════════════════════════════════════════════════════════
#  Test: Section Visibility
# ═══════════════════════════════════════════════════════════════


class TestHtmlSectionVisibility(unittest.TestCase):
    """HTML 报告可见性测试 — 不可见模块不应出现在导航中。"""

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}

    def _render_with_visibility(self, visible_keys: set[str]) -> BeautifulSoup:
        """用指定可见 keys 渲染模板。"""
        sv_dict = {sec["key"]: sec["key"] in visible_keys for sec in self.order}
        return _render_template(
            _build_minimal_render_data(self.order, self.numbers, sv_dict),
        )

    def test_only_always_visible(self):
        """仅 always 类型可见时，导航只有 5 个链接。"""
        soup = self._render_with_visibility(_ALWAYS_KEYS)
        links = soup.select("nav.section-nav a")
        link_keys = {link.get("href", "").replace("#sec-", "") for link in links}
        self.assertEqual(link_keys, _ALWAYS_KEYS,
                         f"应只有 always 模块: {_ALWAYS_KEYS}，实际 {link_keys}")

    def test_always_plus_b_series(self):
        """always + b_series 可见（通常 b_series 由数据驱动）。"""
        visible = _ALWAYS_KEYS | _B_SERIES_KEYS
        soup = self._render_with_visibility(visible)
        links = soup.select("nav.section-nav a")
        link_keys = {link.get("href", "").replace("#sec-", "") for link in links}
        self.assertEqual(link_keys, visible)

    def test_always_plus_news(self):
        """always + news 可见。"""
        visible = _ALWAYS_KEYS | _NEWS_KEYS
        soup = self._render_with_visibility(visible)
        links = soup.select("nav.section-nav a")
        link_keys = {link.get("href", "").replace("#sec-", "") for link in links}
        self.assertEqual(link_keys, visible)

    def test_all_invisible(self):
        """所有模块不可见 → 导航为空但页面不崩溃。

        注：仅 6 个始终显示模块（summary → fund_performance + llm_usage）
        的 div 是无条件渲染的，其余 10 个模块 div 包裹在
        {% if section_visible() %} 内，不可见时完全不输出。
        """
        soup = self._render_with_visibility(set())
        links = soup.select("nav.section-nav a")
        self.assertEqual(len(links), 0, "全部不可见时导航应为空")
        # 无条件渲染的 section 容器
        sections = soup.select("div.section")
        self.assertGreaterEqual(len(sections), 5, "至少 5 个 always 模块应无条件渲染")
        self.assertLess(len(sections), 16, "不可见模块的 div 不应渲染")


# ═══════════════════════════════════════════════════════════════
#  Test: Custom Section Order
# ═══════════════════════════════════════════════════════════════


class TestHtmlCustomOrder(unittest.TestCase):
    """自定义 section_order 下的排序正确性。"""

    @classmethod
    def setUpClass(cls):
        # 用户配置：调整 3 个模块顺序
        cls.custom_order: list[dict] = [
            {"key": "fund_performance", "name": "基金业绩分析",                     "number": 1},
            {"key": "summary",          "name": "投资分析汇总",                     "number": 2},
            {"key": "market_value",     "name": "市值核算明细表",                   "number": 3},
            {"key": "category",         "name": "持仓分类表",                       "number": 4},
            {"key": "penetration",      "name": "资产穿透TOP10",                    "number": 5},
            # b_series 保持默认
            {"key": "fund_manager",       "name": "基金经理变更监控",                 "number": 6},
            {"key": "fund_overlap",       "name": "持仓重合度矩阵",                   "number": 7},
            {"key": "fund_concentration", "name": "持仓集中度监控",                   "number": 8},
            {"key": "fund_style",         "name": "基金风格分析",                     "number": 9},
            # news 保持默认
            {"key": "news_correlation",   "name": "财经新闻热点与持仓关联分析",        "number": 10},
            {"key": "early_warning",      "name": "智能预警",                         "number": 11},
            # llm 保持默认
            {"key": "global_macro",       "name": "全球政经局势",                     "number": 12},
            {"key": "expert_review",      "name": "智囊团深度复盘",                   "number": 13},
            {"key": "health_check",       "name": "持仓体检报告",                     "number": 14},
            {"key": "penetration_deep",   "name": "穿透深度分析",                     "number": 15},
            {"key": "llm_usage",          "name": "LLM API 用量",                    "number": 16},
        ]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.custom_order}
        cls.sv_dict = {sec["key"]: True for sec in cls.custom_order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.custom_order, cls.numbers, cls.sv_dict),
        )

    def test_nav_links_in_custom_order(self):
        """导航链接顺序应与 section_order 一致。"""
        links = self.soup.select("nav.section-nav a")
        expected_keys = [sec["key"] for sec in self.custom_order]
        actual_keys = [link.get("href", "").replace("#sec-", "") for link in links]
        self.assertEqual(actual_keys, expected_keys,
                         f"导航顺序不正确\n  期望: {expected_keys}\n  实际: {actual_keys}")

    def test_custom_fund_performance_first(self):
        """自定义配置下 fund_performance 应排第 1 位。"""
        links = self.soup.select("nav.section-nav a")
        first_key = links[0].get("href", "").replace("#sec-", "")
        self.assertEqual(first_key, "fund_performance",
                         f"第一位应为 fund_performance，实际为 {first_key}")
        first_text = links[0].get_text(strip=True)
        self.assertTrue(first_text.startswith("1"),
                        f"第一位标题应以 1 开头，实际为 '{first_text}'")

    def test_nav_section_title_text_consistency(self):
        """导航文字与 section-title 文字一致。"""
        links = self.soup.select("nav.section-nav a")
        for link in links:
            key = link.get("href", "").replace("#sec-", "")
            nav_text = link.get_text(strip=True)
            section = self.soup.find(id=f"sec-{key}")
            if section:
                title_div = section.find("div", class_="section-title")
                if title_div:
                    title_text = title_div.get_text(strip=True)
                    self.assertEqual(
                        nav_text, title_text,
                        f"#{key} 导航文字 '{nav_text}' 与标题 '{title_text}' 不一致",
                    )

    def test_llm_usage_still_last_in_order(self):
        """llm_usage 的 order 值仍然最大（末位）。"""
        sections = self.soup.select("div.section")
        orders = {}
        for sec in sections:
            sec_id = sec.get("id", "")
            m = re.search(r"order:\s*(\d+)", sec.get("style", ""))
            if m and sec_id == "sec-llm_usage":
                orders[sec_id] = int(m.group(1))

        self.assertIn("sec-llm_usage", orders)
        # llm_usage 的 order 应为 16（默认值，未配置时保持）
        self.assertEqual(orders["sec-llm_usage"], 16,
                         "llm_usage 的 order 应为 16（末位）")


# ═══════════════════════════════════════════════════════════════
#  Test: Nav link anchor validity
# ═══════════════════════════════════════════════════════════════


class TestHtmlAnchorValidity(unittest.TestCase):
    """锚点有效性测试 — href="#sec-X" 必须能真实定位到页面内元素。"""

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    def test_all_hrefs_point_to_valid_sections(self):
        """所有 href 指向的 id 存在于页面中。"""
        links = self.soup.select("nav.section-nav a")
        for link in links:
            href = link.get("href", "")
            self.assertTrue(href.startswith("#"), f"href 不是锚点: {href}")
            target_id = href[1:]
            target = self.soup.find(id=target_id)
            self.assertIsNotNone(target, f"锚点 {href} 找不到对应元素")

    def test_all_sections_reachable_from_nav(self):
        """每个 section 都可以从导航中到达。"""
        sections = self.soup.select("div.section")
        links = self.soup.select("nav.section-nav a")
        link_ids = {link.get("href", "").replace("#", "") for link in links}

        # 可见 section 的 id 应在 link_ids 中
        visible_sections = {sec.get("id") for sec in sections
                           if sec.get("id") in link_ids}
        self.assertEqual(len(visible_sections), len(sections),
                         "部分 section 不在导航中")

    def test_nav_link_ids_are_unique(self):
        """导航链接 href 无重复。"""
        links = self.soup.select("nav.section-nav a")
        hrefs = [link.get("href", "") for link in links]
        self.assertEqual(len(hrefs), len(set(hrefs)),
                         f"导航 href 重复: {set(h for h in hrefs if hrefs.count(h) > 1)}")


if __name__ == "__main__":
    unittest.main()
