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

# 默认注册表 key（按默认顺序，与 registry.py 对齐）
_ALL_KEYS_DEFAULT = [
    "summary", "market_value", "category", "penetration",
    "fund_performance",
    "fund_manager", "fund_overlap", "fund_concentration", "fund_style",
    "news_correlation",
    "global_macro", "expert_review", "health_check", "penetration_deep",
    "portfolio_history", "drawdown_analysis",
    "llm_usage",
]

_ALWAYS_KEYS = {"summary", "market_value", "category", "penetration", "fund_performance"}
_B_SERIES_KEYS = {"fund_manager", "fund_overlap", "fund_concentration", "fund_style"}
_NEWS_KEYS = {"news_correlation"}
_LLM_KEYS = {"global_macro", "expert_review", "health_check", "penetration_deep", "llm_usage"}
_HISTORY_KEYS = {"portfolio_history", "drawdown_analysis"}

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
    {"key": "global_macro",       "name": "全球政经局势",                     "number": 11},
    {"key": "expert_review",      "name": "智囊团深度复盘",                   "number": 12},
    {"key": "health_check",       "name": "持仓体检报告",                     "number": 13},
    {"key": "penetration_deep",   "name": "穿透深度分析",                     "number": 14},
    {"key": "portfolio_history",  "name": "组合历史走势",                     "number": 15},
    {"key": "drawdown_analysis",  "name": "历史回撤分析",                     "number": 16},
    {"key": "llm_usage",          "name": "LLM API 用量",                    "number": 17},
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
        "llm_session_usage": None,
        "module_labels": {}, "module_disabled": {},
        "llm_module_info": [], "llm_endpoint": "",
        "cache_stats": None,
        "section_order": section_order,
        "section_numbers": section_numbers,
        "section_visible_dict": section_visible_dict,
        # Chart.js 交互图表：默认关闭，模板走基础绘图路径
        "chart_datasets": {},
        "enable_interactive_charts": False,
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
        """导航链接数量应等于可见模块数（全部可见 = 17）。"""
        links = self.soup.select("nav.section-nav a")
        self.assertEqual(len(links), 17,
                         f"导航应有 17 个链接，实际 {len(links)}")

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
        self.assertLess(len(sections), 17, "不可见模块的 div 不应渲染")


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
            # llm 保持默认
            {"key": "global_macro",       "name": "全球政经局势",                     "number": 11},
            {"key": "expert_review",      "name": "智囊团深度复盘",                   "number": 12},
            {"key": "health_check",       "name": "持仓体检报告",                     "number": 13},
            {"key": "penetration_deep",   "name": "穿透深度分析",                     "number": 14},
            {"key": "portfolio_history",  "name": "组合历史走势",                     "number": 15},
            {"key": "drawdown_analysis",  "name": "历史回撤分析",                     "number": 16},
            {"key": "llm_usage",          "name": "LLM API 用量",                    "number": 17},
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
        # llm_usage 的 order 应为 17（默认值，未配置时保持）
        self.assertEqual(orders["sec-llm_usage"], 17,
                         "llm_usage 的 order 应为 17（末位）")


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


# ═══════════════════════════════════════════════════════════════
#  Test: Interactive Charts mode
# ═══════════════════════════════════════════════════════════════


class TestHtmlInteractiveCharts(unittest.TestCase):
    """交互图表模式下模板结构测试。"""

    _HISTORY = {
        "status": "ok",
        "bars": [{"date": "2026-01-01", "total_value": 100.0, "drawdown_pct": 0.0}],
        "total_return_pct": 0.1, "total_return": 1000.0,
        "data_start": "2026-01-01", "data_end": "2026-01-01",
        "max_drawdown_pct": -0.05, "max_drawdown": -500.0,
        "drawdown_start": "2026-01-01", "drawdown_end": "2026-01-01",
        "annualized_volatility": 0.18,
        "warnings": None, "failed_holdings": None, "successful_holdings": None,
    }

    _DATASET_KEYS = (
        "portfolio_line", "drawdown", "category_doughnut",
        "industry_bar", "penetration_bar", "radar",
    )

    # 最小穿透数据：触发 sec-penetration 渲染图表容器
    _PENETRATION = {
        "top10": [
            {"rank": 1, "name": "贵州茅台", "codes": ["600519"], "mv": 10000.0,
             "ratio_pct": 12.5, "sector": "白酒", "concepts": ["白酒"],
             "eps_text": "58", "dividend_text": "25.3", "sources": ["基金A"]},
            {"rank": 2, "name": "宁德时代", "codes": ["300750"], "mv": 8000.0,
             "ratio_pct": 10.0, "sector": "电池", "concepts": ["新能源"],
             "eps_text": "--", "dividend_text": "--", "sources": ["基金B"]},
        ],
        "summary": {
            "total_mv": 18000.0, "unknown_mv": 0, "total_funds": 2, "failed_funds": 0,
            "fund_breakdown": "2/2", "total_stocks": 0, "merged_count": 2,
            "top10_coverage_pct": 100.0, "failed_fund_details": [],
        },
    }

    def _render_interactive(
        self,
        chart_overrides: dict | None = None,
        penetration: dict | None = None,
    ) -> BeautifulSoup:
        """渲染 enable_interactive_charts=True 的模板。

        chart_overrides：覆盖默认空 dataset，用于验证各图 canvas 是否渲染。
        penetration：传入时 sec-penetration 章节渲染图表容器。
        """
        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: True for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["enable_interactive_charts"] = True
        data["chart_datasets"] = {k: {"labels": [], "datasets": []} for k in self._DATASET_KEYS}
        if chart_overrides:
            data["chart_datasets"].update(chart_overrides)
        if penetration is not None:
            data["penetration"] = penetration
        data["history_data"] = self._HISTORY
        return _render_template(data)

    def test_chart_box_wraps_canvases(self) -> None:
        """各图 canvas 被 .chart-box 包裹（§4.5 打印不跨页）。

        净值+回撤 + 资产构成 Doughnut 共 3 张图表。
        无穿透数据时，sec-penetration 不渲染图表容器（占位）。
        """
        overrides = {
            "category_doughnut": {"labels": ["股票"], "datasets": [{"data": [1.0]}]},
        }
        soup = self._render_interactive(chart_overrides=overrides)
        boxes = soup.select(".chart-box")
        # 净值+回撤+Doughnut+Radar 共 4 个 .chart-box（Radar 无 labels 时渲染占位容器）
        self.assertEqual(len(boxes), 4, "应恰好 4 个 .chart-box（净值+回撤+Doughnut+Radar）")
        canvas_ids = {c.get("id") for b in boxes for c in b.select("canvas")}
        self.assertIn("chart_portfolio_line", canvas_ids)
        self.assertIn("chart_drawdown", canvas_ids)
        self.assertIn("chart_category_doughnut", canvas_ids)

    def test_penetration_charts_rendered_when_data(self) -> None:
        """穿透数据存在时渲染行业分布 + 穿透 TOP10 两图。

        计划 §4.9：行业分布与穿透 TOP10 同属 sec-penetration 章节，
        有数据时图表容器渲染 canvas；穿透章节共 2 个 .chart-box。
        """
        overrides = {
            "category_doughnut": {"labels": ["股票"], "datasets": [{"data": [1.0]}]},
            "industry_bar": {"labels": ["白酒", "电池"], "datasets": [{"data": [10000.0, 8000.0]}]},
            "penetration_bar": {"labels": ["贵州茅台", "宁德时代"], "datasets": [{"data": [10000.0, 8000.0]}]},
        }
        soup = self._render_interactive(chart_overrides=overrides, penetration=self._PENETRATION)
        boxes = soup.select(".chart-box")
        # 净值+回撤+Doughnut+行业+穿透+Radar 共 6 个 .chart-box（Radar 无 labels 时渲染占位容器）
        self.assertEqual(len(boxes), 6, "应恰好 6 个 .chart-box（净值+回撤+Doughnut+行业+穿透+Radar）")
        canvas_ids = {c.get("id") for b in boxes for c in b.select("canvas")}
        for key in (
            "chart_portfolio_line", "chart_drawdown", "chart_category_doughnut",
            "chart_industry_bar", "chart_penetration_bar",
        ):
            self.assertIn(key, canvas_ids)
        # 行业分布 Horizontal Bar 与穿透 TOP10 容器处于同一章节
        section = soup.find(id="sec-penetration")
        self.assertIsNotNone(section)
        section_canvases = {c.get("id") for c in section.select("canvas")}
        self.assertIn("chart_industry_bar", section_canvases)
        self.assertIn("chart_penetration_bar", section_canvases)

    def test_industry_empty_note_when_no_data(self) -> None:
        """行业数据全不可用时显示"行业数据暂不可用"。

        §4.12 空值语义：dataset 无 labels 时模板渲染占位提示，不输出空 canvas。
        """
        overrides = {
            "category_doughnut": {"labels": ["股票"], "datasets": [{"data": [1.0]}]},
            "penetration_bar": {"labels": ["贵州茅台"], "datasets": [{"data": [10000.0]}]},
        }
        soup = self._render_interactive(chart_overrides=overrides, penetration=self._PENETRATION)
        section = soup.find(id="sec-penetration")
        note = section.select_one(".chart-empty-note")
        self.assertIsNotNone(note, "行业数据为空时应渲染占位提示")
        self.assertIn("行业数据暂不可用", note.get_text())
        self.assertIsNone(section.find(id="chart_industry_bar"), "空数据时不应输出 industry canvas")

    def test_penetration_none_shows_placeholder(self) -> None:
        """penetration=None 时显示"暂无穿透数据"占位，不渲染图表容器。"""
        soup = self._render_interactive()
        section = soup.find(id="sec-penetration")
        self.assertIsNotNone(section)
        self.assertIsNotNone(section.select_one(".empty-note"))
        self.assertIsNone(section.find(id="chart_industry_bar"))
        self.assertIsNone(section.find(id="chart_penetration_bar"))

    def test_radar_chart_rendered_when_labels(self) -> None:
        """量化指标 radar 有 labels 时渲染 canvas。"""
        overrides = {
            "radar": {
                "labels": ["夏普比率", "卡玛比率"],
                "datasets": [{"label": "量化指标", "data": [1.2, 0.8]}],
            },
        }
        soup = self._render_interactive(chart_overrides=overrides)
        section = soup.find(id="sec-portfolio_history")
        self.assertIsNotNone(section)
        radar_canvas = section.find(id="chart_radar")
        self.assertIsNotNone(radar_canvas)
        # canvas 的直接父级即 .chart-box 容器
        self.assertIn("chart-box", radar_canvas.parent.get("class", []))

    def test_radar_empty_note_when_no_labels(self) -> None:
        """radar 无 labels 时显示"量化指标数据不足"占位，不渲染 canvas。"""
        soup = self._render_interactive()
        section = soup.find(id="sec-portfolio_history")
        note = section.select_one(".chart-empty-note")
        self.assertIsNotNone(note)
        self.assertIn("量化指标数据不足", note.get_text())
        self.assertIsNone(section.find(id="chart_radar"))

    def test_radar_data_unavailable_placeholder(self) -> None:
        """data_unavailable=True 时显示"持仓市值数据不可用，量化指标暂停计算"。"""
        overrides = {"radar": {"labels": ["夏普比率"], "datasets": [{"data": [1.2]}]}}
        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: True for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["enable_interactive_charts"] = True
        data["data_unavailable"] = True  # 持仓有成本但市值全 0
        data["chart_datasets"] = {k: {"labels": [], "datasets": []} for k in self._DATASET_KEYS}
        data["chart_datasets"].update(overrides)
        data["history_data"] = self._HISTORY
        soup = _render_template(data)
        section = soup.find(id="sec-portfolio_history")
        note = section.select_one(".chart-empty-note")
        self.assertIsNotNone(note)
        self.assertIn("持仓市值数据不可用，量化指标暂停计算", note.get_text())
        self.assertIsNone(section.find(id="chart_radar"))

    def test_all_chart_canvases_have_a11y_attrs(self) -> None:
        """6 个 Chart.js canvas 均含 A1 可访问性属性（§4.8 A1）。

        模板 6 处 canvas 补 aria-label + role="img" + 内嵌 fallback 文本：
        屏幕阅读器读出图表含义，降级环境（Canvas/JS 不可用）读 fallback
        指引用户看明细表格——与 test-chart.html 示范写法对齐。
        """
        overrides = {
            "category_doughnut": {"labels": ["股票"], "datasets": [{"data": [1.0]}]},
            "industry_bar": {"labels": ["白酒"], "datasets": [{"data": [10000.0]}]},
            "penetration_bar": {"labels": ["贵州茅台"], "datasets": [{"data": [10000.0]}]},
            "radar": {"labels": ["夏普比率"], "datasets": [{"data": [1.2]}]},
        }
        soup = self._render_interactive(chart_overrides=overrides, penetration=self._PENETRATION)
        for key in self._DATASET_KEYS:
            canvas = soup.find(id=f"chart_{key}")
            self.assertIsNotNone(canvas, f"{key} canvas 应渲染（Flag ON + 数据存在）")
            label = canvas.get("aria-label")
            self.assertTrue(label, f"{key} canvas 应含 aria-label")
            self.assertIn("悬停查看", label, f"{key} aria-label 应描述图表含义")
            self.assertEqual(canvas.get("role"), "img", f"{key} canvas role 应为 img")
            self.assertTrue(
                canvas.get_text().strip(),
                f"{key} canvas 应含内嵌 fallback 文本（降级环境指引）",
            )

    def test_chart_scripts_loaded_in_order(self) -> None:
        """chart-print.js 先于 chart-config.js，再 chart-init.js（登记先于初始化）。"""
        soup = self._render_interactive()
        chart_scripts = [
            s.get("src") for s in soup.select("script[src]")
            if (s.get("src") or "").startswith("chart-")
        ]
        self.assertIn("chart-print.js", chart_scripts)
        self.assertLess(
            chart_scripts.index("chart-print.js"),
            chart_scripts.index("chart-config.js"),
            "chart-print.js 必须在 chart-config.js 之前加载",
        )
        self.assertLess(
            chart_scripts.index("chart-config.js"),
            chart_scripts.index("chart-init.js"),
            "chart-config.js 必须在 chart-init.js 之前加载",
        )

    def test_print_css_forces_light_theme(self) -> None:
        """/media print 覆盖 --chart-* 为浅色 + .chart-box break-inside（§4.5）。"""
        soup = self._render_interactive()
        style = soup.find("style").get_text()
        # 打印覆盖只在 @media print 内出现（主 :root 是 #333333，这里是 #000）
        self.assertIn("--chart-text: #000", style)
        self.assertIn("--chart-grid", style)
        self.assertIn(".chart-box", style)
        self.assertIn("break-inside: avoid", style)

    def test_old_canvas_path_absent(self) -> None:
        """交互模式下旧 Canvas 兜底路径不输出。"""
        soup = self._render_interactive()
        self.assertIsNone(soup.find(id="portfolioChart"))
        self.assertIsNone(soup.find(id="drawdownChart"))

    def test_flag_off_legacy_canvas_regression(self) -> None:
        """Flag OFF 时报告与基础版一致（Canvas + 表格）。

        enable_interactive_charts=False（默认渲染路径）：
          - 6 个 Chart.js canvas 均不输出（无空 div / 空 canvas 残留）
          - Canvas（portfolioChart / drawdownChart）正常保留
          - drawSimpleChart 定义保留（绘图函数可用）
        """
        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: True for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["history_data"] = self._HISTORY
        # 显式置 False（默认值即 False，此处防御性声明）
        data["enable_interactive_charts"] = False
        soup = _render_template(data)

        for key in ("chart_portfolio_line", "chart_drawdown", "chart_category_doughnut",
                    "chart_industry_bar", "chart_penetration_bar", "chart_radar"):
            self.assertIsNone(soup.find(id=key), f"Flag OFF 时不应输出 {key} canvas")
        self.assertIsNotNone(soup.find(id="portfolioChart"), "Flag OFF 时应保留旧净值 Canvas")
        self.assertIsNotNone(soup.find(id="drawdownChart"), "Flag OFF 时应保留旧回撤 Canvas")
        self.assertIn("drawSimpleChart", str(soup), "Flag OFF 时应保留旧绘图函数")


if __name__ == "__main__":
    unittest.main()
