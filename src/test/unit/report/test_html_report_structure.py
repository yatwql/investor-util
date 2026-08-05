"""HTML 报告 UI/UX 结构测试 — 导航/锚点/换行/CSS 排序。

覆盖场景：
  - 导航链接 ↔ section 容器一一对应（无断链/无悬空锚点）
  - 所有 section 的 CSS order 值唯一且与 section_numbers 一致
  - 不可见模块不在导航中出现
  - 自定义 section_order 下的排序正确性
  - llm_usage 始终强制末位

边缘/异常测试见 test_html_report_structure_edge.py。

运行：
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
    "summary",
    "market_value",
    "category",
    "penetration",
    "fund_performance",
    "fund_manager",
    "position_relationship",
    "fund_concentration",
    "style_factor",
    "news_correlation",
    "global_macro",
    "expert_review",
    "health_check",
    "penetration_deep",
    "portfolio_history_drawdown",
    "llm_usage",
]

_ALWAYS_KEYS = {"summary", "market_value", "category", "penetration", "fund_performance"}
_FUND_DEEP_ANALYSIS_KEYS = {"fund_manager", "position_relationship", "fund_concentration", "style_factor"}
_NEWS_KEYS = {"news_correlation"}
_LLM_KEYS = {"global_macro", "expert_review", "health_check", "penetration_deep", "llm_usage"}
_HISTORY_KEYS = {"portfolio_history_drawdown"}

# LLM 支持章节（目录/导航橙色+🧠 标记）：与「LLM」导航组全部章节一致
# （news_correlation 注册表 type 为 news，但仍属 LLM 支持章；_LLM_SUPPORTED_SECTIONS 派生一致性测试防漂移）
_LLM_SUPPORTED_KEYS = {
    "news_correlation",
    "global_macro",
    "expert_review",
    "health_check",
    "penetration_deep",
    "llm_usage",
}

_REPORT_SECTION_DEFAULT: list[dict] = [
    {"key": "summary", "name": "投资分析汇总", "number": 1},
    {"key": "market_value", "name": "市值核算明细表", "number": 2},
    {"key": "category", "name": "持仓分类表", "number": 3},
    {"key": "penetration", "name": "资产穿透TOP10", "number": 4},
    {"key": "fund_performance", "name": "基金业绩分析", "number": 5},
    {"key": "fund_manager", "name": "基金经理变更监控", "number": 6},
    {"key": "position_relationship", "name": "持仓关系矩阵", "number": 7},
    {"key": "fund_concentration", "name": "持仓集中度监控", "number": 8},
    {"key": "style_factor", "name": "风格与因子分析", "number": 9},
    {"key": "news_correlation", "name": "财经新闻热点与持仓关联分析", "number": 10},
    {"key": "global_macro", "name": "全球政经局势", "number": 11},
    {"key": "expert_review", "name": "智囊团深度复盘", "number": 12},
    {"key": "health_check", "name": "持仓体检报告", "number": 13},
    {"key": "penetration_deep", "name": "穿透深度分析", "number": 14},
    {"key": "portfolio_history_drawdown", "name": "组合历史走势与回撤", "number": 15},
    {"key": "llm_usage", "name": "LLM API 用量", "number": 16},
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

    根据 visible_set 自动填充基金深度分析/新闻模块所需的 mock 数据结构，
    避免模板内 .get() 或 [] 操作因 None 值崩溃。

    Args:
        visible_set: 当前可见的模块 key 集合，用于决定哪些 mock 数据需要填充
    """
    visible_keys = {k for k, v in section_visible_dict.items() if v}

    data = {
        "now": "2026-07-05 12:00:00",
        "today": "2026-07-05",
        "trading_day": "2026-07-03",
        "total_mv": 0,
        "total_cost": 0,
        "total_profit": 0,
        "total_profit_rate": 0,
        "total_today_profit": 0,
        "today_profit_rate": 0,
        "categories": {},
        "update_status": None,
        "a_indices": [],
        "us_indices": [],
        "accounts": {},
        "account_totals": {},
        "cat_data": [],
        "penetration": None,
        "perf_data": [],
        "news_data": None,
        "news_llm_meta": None,
        "has_llm_analysis": False,
        "manager_analysis": None,
        "overlap_matrix": None,
        # 持仓关系矩阵：相关性区块数据契约（空 dict 触发模板内 .get() 默认值降级）
        "position_relationship_data": {},
        "concentration_analysis": None,
        "style_analysis": None,
        "llm_enabled": True,
        "global_macro": None,
        "expert_review": None,
        "health_check": None,
        "penetration_deep": None,
        "llm_session_usage": None,
        "module_labels": {},
        "module_disabled": {},
        "llm_module_info": [],
        "llm_endpoint": "",
        "cache_stats": None,
        "section_order": section_order,
        "section_numbers": section_numbers,
        "section_visible_dict": section_visible_dict,
        # Chart.js 交互图表：默认关闭，模板走基础绘图路径
        "chart_datasets": {},
        "enable_interactive_charts": False,
    }

    # 基金深度分析模块可见时，填充 mock 数据结构（模板内部 .get() 要求 dict 非 None）
    if visible_keys & _FUND_DEEP_ANALYSIS_KEYS:
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
    from src.python.report.html_writer import _LLM_SUPPORTED_SECTIONS, _build_section_nav_groups

    # 注入 section_visible 闭包 + section_groups 分组导航（与生产代码相同的 context 变量方式，不写入 _ENV.globals）
    _sv_dict = render_data.get("section_visible_dict", {})
    _sv_fn = lambda key, _d=_sv_dict: bool(_d.get(key, False))
    section_groups = _build_section_nav_groups(
        render_data.get("section_order", []),
        _sv_fn,
        render_data.get("section_numbers", {}),
    )
    html = _ENV.get_template("report_template.html").render(
        **render_data,
        section_visible=_sv_fn,
        section_groups=section_groups,
        llm_supported_sections=_LLM_SUPPORTED_SECTIONS,
    )
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
        # 所有模块可见（基金深度分析也给 True，因为我们要测结构完整性）
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    # ── Nav links ──────────────────────────────────────────────

    def test_nav_link_count(self):
        """导航链接数量应等于可见模块数（全部可见 = 16）。"""
        links = self.soup.select("nav.section-nav a")
        self.assertEqual(len(links), 16, f"导航应有 16 个链接，实际 {len(links)}")

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
        self.assertEqual(len(ids), len(set(ids)), f"发现重复 section id: {set(i for i in ids if ids.count(i) > 1)}")

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

        self.assertEqual(
            len(orders), len(set(orders)), f"order 值不唯一: {set(o for o in orders if orders.count(o) > 1)}"
        )

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
            orders,
            expected,
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
                actual_order,
                expected_order,
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
        self.assertEqual(
            link_keys, set(_ALL_KEYS_DEFAULT), f"导航缺失/多余 keys: 期望 {set(_ALL_KEYS_DEFAULT)}，实际 {link_keys}"
        )


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
        self.assertEqual(link_keys, _ALWAYS_KEYS, f"应只有 always 模块: {_ALWAYS_KEYS}，实际 {link_keys}")

    def test_always_plus_fund_deep_analysis(self):
        """always + 基金深度分析可见（通常基金深度分析由数据驱动）。"""
        visible = _ALWAYS_KEYS | _FUND_DEEP_ANALYSIS_KEYS
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
            {"key": "fund_performance", "name": "基金业绩分析", "number": 1},
            {"key": "summary", "name": "投资分析汇总", "number": 2},
            {"key": "market_value", "name": "市值核算明细表", "number": 3},
            {"key": "category", "name": "持仓分类表", "number": 4},
            {"key": "penetration", "name": "资产穿透TOP10", "number": 5},
            # 基金深度分析保持默认
            {"key": "fund_manager", "name": "基金经理变更监控", "number": 6},
            {"key": "position_relationship", "name": "持仓关系矩阵", "number": 7},
            {"key": "fund_concentration", "name": "持仓集中度监控", "number": 8},
            {"key": "style_factor", "name": "风格与因子分析", "number": 9},
            # news 保持默认
            {"key": "news_correlation", "name": "财经新闻热点与持仓关联分析", "number": 10},
            # llm 保持默认
            {"key": "global_macro", "name": "全球政经局势", "number": 11},
            {"key": "expert_review", "name": "智囊团深度复盘", "number": 12},
            {"key": "health_check", "name": "持仓体检报告", "number": 13},
            {"key": "penetration_deep", "name": "穿透深度分析", "number": 14},
            {"key": "portfolio_history_drawdown", "name": "组合历史走势与回撤", "number": 15},
            {"key": "llm_usage", "name": "LLM API 用量", "number": 16},
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
        self.assertEqual(actual_keys, expected_keys, f"导航顺序不正确\n  期望: {expected_keys}\n  实际: {actual_keys}")

    def test_custom_fund_performance_first(self):
        """自定义配置下 fund_performance 应排第 1 位。"""
        links = self.soup.select("nav.section-nav a")
        first_key = links[0].get("href", "").replace("#sec-", "")
        self.assertEqual(first_key, "fund_performance", f"第一位应为 fund_performance，实际为 {first_key}")
        first_text = links[0].get_text(strip=True)
        self.assertTrue(first_text.startswith("1"), f"第一位标题应以 1 开头，实际为 '{first_text}'")

    def test_nav_section_title_text_consistency(self):
        """导航文字与 section-title 文字一致（LLM 章节先剔除 🧠 图标）。"""
        links = self.soup.select("nav.section-nav a")
        for link in links:
            key = link.get("href", "").replace("#sec-", "")
            nav_text = link.get_text(strip=True)
            if key in _LLM_SUPPORTED_KEYS:
                nav_text = nav_text.replace("🧠", "", 1).strip()
            section = self.soup.find(id=f"sec-{key}")
            if section:
                title_div = section.find("div", class_="section-title")
                if title_div:
                    title_text = title_div.get_text(strip=True)
                    self.assertEqual(
                        nav_text,
                        title_text,
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
        self.assertEqual(orders["sec-llm_usage"], 16, "llm_usage 的 order 应为 16（末位）")


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
        visible_sections = {sec.get("id") for sec in sections if sec.get("id") in link_ids}
        self.assertEqual(len(visible_sections), len(sections), "部分 section 不在导航中")

    def test_nav_link_ids_are_unique(self):
        """导航链接 href 无重复。"""
        links = self.soup.select("nav.section-nav a")
        hrefs = [link.get("href", "") for link in links]
        self.assertEqual(len(hrefs), len(set(hrefs)), f"导航 href 重复: {set(h for h in hrefs if hrefs.count(h) > 1)}")


# ═══════════════════════════════════════════════════════════════
#  Test: Interactive Charts mode
# ═══════════════════════════════════════════════════════════════


class TestHtmlInteractiveCharts(unittest.TestCase):
    """交互图表模式下模板结构测试。"""

    _HISTORY = {
        "status": "ok",
        "bars": [{"date": "2026-01-01", "total_value": 100.0, "drawdown_pct": 0.0}],
        "total_return_pct": 0.1,
        "total_return": 1000.0,
        "data_start": "2026-01-01",
        "data_end": "2026-01-01",
        "max_drawdown_pct": -0.05,
        "max_drawdown": -500.0,
        "drawdown_start": "2026-01-01",
        "drawdown_end": "2026-01-01",
        "annualized_volatility": 0.18,
        "drawdown_available": True,  # 有效交易日 ≥ MIN_SPAN 才渲染回撤明细（上游计算）
        "drawdown_events": [
            {
                "peak_date": "2026-01-01",
                "trough_date": "2026-01-01",
                "recovery_date": "",
                "drawdown_pct": 5.0,
                "duration_days": 0,
                "recovery_days": None,
                "recovered": False,
            }
        ],
        "warnings": None,
        "failed_holdings": None,
        "successful_holdings": None,
    }

    _DATASET_KEYS = (
        "portfolio_line",
        "drawdown",
        "category_doughnut",
        "industry_bar",
        "penetration_bar",
        "radar",
    )

    # 最小穿透数据：触发 sec-penetration 渲染图表容器
    _PENETRATION = {
        "top10": [
            {
                "rank": 1,
                "name": "贵州茅台",
                "codes": ["600519"],
                "mv": 10000.0,
                "ratio_pct": 12.5,
                "sector": "白酒",
                "concepts": ["白酒"],
                "eps_text": "58",
                "dividend_text": "25.3",
                "sources": ["基金A"],
            },
            {
                "rank": 2,
                "name": "宁德时代",
                "codes": ["300750"],
                "mv": 8000.0,
                "ratio_pct": 10.0,
                "sector": "电池",
                "concepts": ["新能源"],
                "eps_text": "--",
                "dividend_text": "--",
                "sources": ["基金B"],
            },
        ],
        "summary": {
            "total_mv": 18000.0,
            "unknown_mv": 0,
            "total_funds": 2,
            "failed_funds": 0,
            "fund_breakdown": "2/2",
            "total_stocks": 0,
            "merged_count": 2,
            "top10_coverage_pct": 100.0,
            "failed_fund_details": [],
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
            "chart_portfolio_line",
            "chart_drawdown",
            "chart_category_doughnut",
            "chart_industry_bar",
            "chart_penetration_bar",
        ):
            self.assertIn(key, canvas_ids)
        # 行业分布 Vertical Bar 与穿透 TOP10 容器处于同一章节
        section = soup.find(id="sec-penetration")
        self.assertIsNotNone(section)
        section_canvases = {c.get("id") for c in section.select("canvas")}
        self.assertIn("chart_industry_bar", section_canvases)
        self.assertIn("chart_penetration_bar", section_canvases)

    def test_industry_and_penetration_bars_both_vertical(self) -> None:
        """行业分布与穿透 TOP10 柱状图风格统一为垂直（竖桩）。

        穿透模块两图并排：行业分布原为 indexAxis:'y' 水平条，穿透 TOP10 为
        垂直条，风格不一致。统一后两图 aria-label 均应描述"垂直柱状图"、
        不含"水平"字样。
        """
        overrides = {
            "industry_bar": {"labels": ["白酒", "电池"], "datasets": [{"data": [10000.0, 8000.0]}]},
            "penetration_bar": {"labels": ["贵州茅台", "宁德时代"], "datasets": [{"data": [10000.0, 8000.0]}]},
        }
        soup = self._render_interactive(chart_overrides=overrides, penetration=self._PENETRATION)
        for key in ("chart_industry_bar", "chart_penetration_bar"):
            label = soup.find(id=key).get("aria-label")
            self.assertIn("垂直柱状图", label, f"{key} aria-label 应描述垂直柱状图")
            self.assertNotIn("水平", label, f"{key} aria-label 不应残留「水平柱状图」描述")

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

    def test_all_charts_have_captions(self) -> None:
        """6 张图均在下方渲染图下说明（.chart-caption），标注该图是什么图表。

        用户需求：报告中每个图表下方标注图表说明（如「TOP 10 持仓资产」）。
        说明置于 .chart-box 容器外（避免固定高度溢出），跟随 canvas 渲染分支。
        """
        overrides = {
            "category_doughnut": {"labels": ["股票"], "datasets": [{"data": [1.0]}]},
            "industry_bar": {"labels": ["白酒", "电池"], "datasets": [{"data": [10000.0, 8000.0]}]},
            "penetration_bar": {"labels": ["贵州茅台", "宁德时代"], "datasets": [{"data": [10000.0, 8000.0]}]},
            "radar": {"labels": ["夏普比率"], "datasets": [{"label": "量化指标", "data": [1.2]}]},
        }
        soup = self._render_interactive(chart_overrides=overrides, penetration=self._PENETRATION)
        captions = soup.select(".chart-caption")
        self.assertEqual(len(captions), 6, "6 张图应恰好渲染 6 个图下说明")
        texts = [c.get_text(strip=True) for c in captions]
        for expected in (
            "组合净值走势",
            "历史回撤走势",
            "资产构成分布",
            "持仓行业分布",
            "TOP 10 持仓资产",
            "组合量化指标画像",
        ):
            self.assertIn(expected, texts, f"图下说明应包含「{expected}」")
        # 穿透 TOP10 图注位于其 canvas 之后
        pen_caption = soup.find("div", class_="chart-caption", string="TOP 10 持仓资产")
        self.assertIsNotNone(pen_caption)
        pen_canvas = soup.find(id="chart_penetration_bar")
        pen_box = pen_canvas.parent  # .chart-box
        box_next = pen_box.find_next_sibling()
        self.assertEqual(box_next, pen_caption, "穿透 TOP10 图注应紧跟其图表容器")

    def test_caption_not_rendered_when_chart_empty(self) -> None:
        """图表数据为空时对应图注不渲染（说明跟随 canvas 渲染分支）。

        净值/回撤 canvas 无条件渲染（无 labels 守卫）→ 图注仍出现；
        Doughnut/行业/穿透/Radar 空数据 → 渲染占位而非图注。
        """
        soup = self._render_interactive()  # chart_datasets 全空
        captions = soup.select(".chart-caption")
        texts = [c.get_text(strip=True) for c in captions]
        self.assertEqual(len(captions), 2, "仅净值+回撤两图有图注（其余四图空数据）")
        self.assertIn("组合净值走势", texts)
        self.assertIn("历史回撤走势", texts)
        for absent in ("资产构成分布", "持仓行业分布", "TOP 10 持仓资产", "组合量化指标画像"):
            self.assertNotIn(absent, texts, f"空数据时不应渲染图注「{absent}」")

    def test_radar_chart_rendered_when_labels(self) -> None:
        """量化指标 radar 有 labels 时渲染 canvas。"""
        overrides = {
            "radar": {
                "labels": ["夏普比率", "卡玛比率"],
                "datasets": [{"label": "量化指标", "data": [1.2, 0.8]}],
            },
        }
        soup = self._render_interactive(chart_overrides=overrides)
        section = soup.find(id="sec-portfolio_history_drawdown")
        self.assertIsNotNone(section)
        radar_canvas = section.find(id="chart_radar")
        self.assertIsNotNone(radar_canvas)
        # canvas 的直接父级即 .chart-box 容器
        self.assertIn("chart-box", radar_canvas.parent.get("class", []))

    def test_radar_empty_note_when_no_labels(self) -> None:
        """radar 无 labels 时显示"量化指标数据不足"占位，不渲染 canvas。"""
        soup = self._render_interactive()
        section = soup.find(id="sec-portfolio_history_drawdown")
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
        section = soup.find(id="sec-portfolio_history_drawdown")
        note = section.select_one(".chart-empty-note")
        self.assertIsNotNone(note)
        self.assertIn("持仓市值数据不可用，量化指标暂停计算", note.get_text())
        self.assertIsNone(section.find(id="chart_radar"))

    def test_all_chart_canvases_have_a11y_attrs(self) -> None:
        """6 个 Chart.js canvas 均含可访问性属性（§4.8）。

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
        """加载顺序：chart-print → chart-config → chart-export → chart-common → chart-init（登记/导出/公共 helper 先于初始化）。"""
        soup = self._render_interactive()
        chart_scripts = [s.get("src") for s in soup.select("script[src]") if (s.get("src") or "").startswith("chart-")]
        for fname in ("chart-print.js", "chart-config.js", "chart-export.js", "chart-common.js", "chart-init.js"):
            self.assertIn(fname, chart_scripts, f"{fname} 应被模板引用")
        self.assertLess(
            chart_scripts.index("chart-print.js"),
            chart_scripts.index("chart-config.js"),
            "chart-print.js 必须在 chart-config.js 之前加载",
        )
        self.assertLess(
            chart_scripts.index("chart-config.js"),
            chart_scripts.index("chart-export.js"),
            "chart-config.js 必须在 chart-export.js 之前加载",
        )
        self.assertLess(
            chart_scripts.index("chart-export.js"),
            chart_scripts.index("chart-common.js"),
            "chart-export.js 必须在 chart-common.js 之前加载",
        )
        self.assertLess(
            chart_scripts.index("chart-common.js"),
            chart_scripts.index("chart-init.js"),
            "chart-common.js 必须在 chart-init.js 之前加载（chart-init 依赖 ChartCommon）",
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

        for key in (
            "chart_portfolio_line",
            "chart_drawdown",
            "chart_category_doughnut",
            "chart_industry_bar",
            "chart_penetration_bar",
            "chart_radar",
        ):
            self.assertIsNone(soup.find(id=key), f"Flag OFF 时不应输出 {key} canvas")
        self.assertIsNotNone(soup.find(id="portfolioChart"), "Flag OFF 时应保留旧净值 Canvas")
        self.assertIsNotNone(soup.find(id="drawdownChart"), "Flag OFF 时应保留旧回撤 Canvas")
        self.assertIn("drawSimpleChart", str(soup), "Flag OFF 时应保留旧绘图函数")


# ═══════════════════════════════════════════════════════════════
#  Test: 暗色模式（主题切换）
# ═══════════════════════════════════════════════════════════════


class TestHtmlTheme(unittest.TestCase):
    """HTML 暗色模式（主题切换）结构测试 — 按钮/脚本/CSS 变量/打印隐藏。

    主题元素为模板静态结构（不受章节可见性影响），用 _render_interactive
    渲染完整页面后断言：
      - 浮动切换按钮存在且带 aria-label
      - theme.js 脚本被引用
      - :root 页面级 CSS 变量（--bg/--surface/--text）
      - [data-theme="dark"] 深色覆盖块
      - @media print 隐藏切换按钮
    """

    def _render_theme_soup(self) -> BeautifulSoup:
        """渲染完整交互模板（主题元素为静态结构，与章节可见性无关）。"""
        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: True for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["enable_interactive_charts"] = True
        data["chart_datasets"] = {k: {"labels": [], "datasets": []} for k in TestHtmlInteractiveCharts._DATASET_KEYS}
        return _render_template(data)

    def test_theme_toggle_button_present(self) -> None:
        """浮动右上角切换按钮存在，含 aria-label 与 title（可访问性）。"""
        soup = self._render_theme_soup()
        btn = soup.select_one("button.theme-toggle-btn")
        self.assertIsNotNone(btn, "应存在 theme-toggle-btn 浮动切换按钮")
        self.assertEqual(btn.get("aria-label"), "切换深色模式", "按钮 aria-label 应描述主题切换")
        self.assertIsNotNone(btn.get("title"), "按钮应含 title 提示")
        self.assertIn("🌙", btn.get_text(), "浅色默认态按钮应显示 🌙 图标（可切深色）")

    def test_theme_js_loaded(self) -> None:
        """模板引用 theme.js（主题切换 主题切换脚本）。"""
        soup = self._render_theme_soup()
        scripts = [s.get("src") for s in soup.select("script[src]")]
        self.assertIn("theme.js", scripts, "模板应加载 theme.js")

    def test_theme_js_loaded_after_toc(self) -> None:
        """theme.js 在 toc.js 之后加载（保证按钮可访问性逻辑不与 toc 冲突）。"""
        soup = self._render_theme_soup()
        srcs = [s.get("src") for s in soup.select("script[src]")]
        toc_idx = srcs.index("toc.js")
        theme_idx = srcs.index("theme.js")
        self.assertLess(toc_idx, theme_idx, "toc.js 应早于 theme.js 加载")

    def test_root_css_variables(self) -> None:
        """:root 定义页面级 CSS 变量（--bg/--surface/--text 等）。"""
        soup = self._render_theme_soup()
        style = soup.find("style").get_text()
        for var_name in ("--bg:", "--surface:", "--text:", "--profit:", "--loss:"):
            self.assertIn(var_name, style, f":root 应定义 {var_name} 页面级变量")

    def test_dark_theme_override_block(self) -> None:
        """存在 [data-theme="dark"] 深色覆盖块（含深色背景/提亮语义色）。"""
        soup = self._render_theme_soup()
        style = soup.find("style").get_text()
        self.assertIn('[data-theme="dark"]', style, 'style 应含 [data-theme="dark"] 覆盖块')
        self.assertIn("--bg: #121212", style, "深色块应定义深色背景")
        self.assertIn("--surface: #1e1e1e", style, "深色块应定义深色卡片表面")

    def test_theme_button_hidden_in_print(self) -> None:
        """@media print 隐藏切换按钮（打印不出现浮动控件）。"""
        soup = self._render_theme_soup()
        style = soup.find("style").get_text()
        self.assertIn("@media print", style, "模板应含打印媒体查询")
        self.assertIn(".theme-toggle-btn { display: none", style, "打印时应隐藏主题切换按钮")

    def test_css_variables_used_for_theme_aware_colors(self) -> None:
        """语义色使用 var(--xxx) 而非硬编码（暗色下自动适配）。"""
        soup = self._render_theme_soup()
        html = str(soup)
        # 盈利/亏损色应通过变量引用；不应再出现旧硬编码红绿
        self.assertNotIn("color: #CC0000", html, "盈利色不应硬编码 #CC0000")
        self.assertNotIn("color: #009900", html, "亏损色不应硬编码 #009900")


# ═══════════════════════════════════════════════════════════════
#  Test: 章节底部"回到顶部"链接
# ═══════════════════════════════════════════════════════════════


class TestHtmlBackToTop(unittest.TestCase):
    """每个章节底部都应有一个回到顶部链接，点击跳转 #report-top。

    用户需求：HTML 报告中每个章节底部提供链接，快速回到报告头部。
    """

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    def test_report_top_anchor_exists(self):
        """报告头部存在唯一 #report-top 锚点。"""
        anchors = self.soup.find_all(id="report-top")
        self.assertEqual(len(anchors), 1, f"应恰好存在 1 个 #report-top 锚点，实际 {len(anchors)}")
        self.assertIn(
            "report-header",
            anchors[0].get("class", []),
            "#report-top 锚点应位于报告头部",
        )

    def test_every_section_has_exactly_one_back_to_top_link(self):
        """每个 .section 底部都有且仅有一个指向 #report-top 的链接。"""
        sections = self.soup.select("div.section")
        self.assertGreaterEqual(len(sections), 1, "模板应渲染至少一个章节")
        for sec in sections:
            links = sec.select('.back-to-top-link a[href="#report-top"]')
            self.assertEqual(
                len(links),
                1,
                f"#{sec.get('id')} 应恰好有 1 个指向 #report-top 的链接，实际 {len(links)}",
            )

    def test_back_to_top_link_has_visible_text(self):
        """回到顶部链接含可读文字（标题 + 箭头）。"""
        first = self.soup.select_one("div.section .back-to-top-link a[href='#report-top']")
        self.assertIsNotNone(first, "应至少渲染一个回到顶部链接")
        text = first.get_text(strip=True)
        self.assertIn("回到顶部", text, f"链接文字应含「回到顶部」，实际为「{text}」")

    def test_back_to_top_is_last_child_of_section(self):
        """回到顶部链接是每个章节的最后一个子元素（紧贴章节底部）。"""
        sections = self.soup.select("div.section")
        for sec in sections:
            children = sec.find_all(recursive=False)
            self.assertTrue(children, f"#{sec.get('id')} 应有子元素")
            last = children[-1]
            self.assertTrue(
                last.name == "div" and "back-to-top-link" in last.get("class", []),
                f"#{sec.get('id')} 最后一个子元素应为 .back-to-top-link，实际 <{last.name}> class={last.get('class')}",
            )


class TestHtmlTocSidebar(unittest.TestCase):
    """左侧目录 TOC 结构测试 — 可展开/收起的章节快速定位栏。

    用户需求：HTML 报告左侧提供 TOC，点击快速定位到具体章节，且可展开/收起。
    渲染侧校验：目录项 ↔ section 一一对应、折叠/展开按钮存在、JS 加载。
    """

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    # ── TOC sidebar 本体 ──────────────────────────────────────

    def test_toc_sidebar_present(self):
        """存在唯一的 #toc-sidebar 左侧栏，且带章节 aria-label。"""
        sidebars = self.soup.find_all(id="toc-sidebar")
        self.assertEqual(len(sidebars), 1, f"应恰好 1 个 #toc-sidebar，实际 {len(sidebars)}")
        self.assertEqual(sidebars[0].name, "aside", "#toc-sidebar 应为 <aside> 语义元素")
        self.assertEqual(sidebars[0].get("aria-label"), "章节目录")

    def test_toc_link_count_matches_sections(self):
        """目录链接数量 = 可见模块数（全部可见 = 16）。"""
        links = self.soup.select("#toc-sidebar a[href^='#sec-']")
        self.assertEqual(len(links), 16, f"目录应有 16 个链接，实际 {len(links)}")

    def test_every_toc_link_has_corresponding_section(self):
        """每个目录链接的 href 指向一个存在的 section id。"""
        links = self.soup.select("#toc-sidebar a[href^='#sec-']")
        for link in links:
            href = link.get("href", "")
            section_id = _get_section_id_from_href(href)
            target = self.soup.find(id=section_id)
            self.assertIsNotNone(target, f"目录链接 {href} 无对应 section")
            self.assertTrue("section" in target.get("class", []), f"{href} 对应元素应带 .section 类")

    def test_toc_link_text_shows_number_and_name(self):
        """目录链接文字含「编号、章节名」（LLM 章节尾附 🧠 图标）。"""
        for sec in self.order:
            link = self.soup.select_one(f"#toc-sidebar a[href='#sec-{sec['key']}']")
            self.assertIsNotNone(link, f"目录缺少章节 {sec['key']}")
            text = link.get_text(strip=True)
            expected = f"{sec['number']}、{sec['name']}"
            if sec["key"] in _LLM_SUPPORTED_KEYS:
                self.assertTrue(
                    text.startswith(expected),
                    f"{sec['key']} 目录文案应以「{expected}」开头，实际「{text}」",
                )
                self.assertIn("🧠", text, f"{sec['key']} 目录文案应含 🧠 图标")
            else:
                self.assertEqual(text, expected, f"{sec['key']} 目录文案应为「{expected}」，实际「{text}」")

    # ── 折叠/展开控件 ─────────────────────────────────────────

    def test_collapse_button_in_header(self):
        """目录头部含「收起」按钮（折叠 TOC 用）。"""
        btn = self.soup.select_one("#toc-sidebar .toc-collapse-btn")
        self.assertIsNotNone(btn, "目录头部应有收起按钮")
        self.assertIn("收起", btn.get_text(strip=True))
        self.assertEqual(btn.get("aria-label"), "收起目录")

    def test_expand_toggle_button_present(self):
        """存在独立的展开按钮 #toc-toggle-btn（收起后悬浮显示）。"""
        btn = self.soup.select_one("button#toc-toggle-btn")
        self.assertIsNotNone(btn, "应有展开目录的悬浮按钮")
        self.assertEqual(btn.get("aria-label"), "展开目录")

    def test_toc_js_loaded(self):
        """模板引用 toc.js（本地 bundle 加载）。"""
        self.assertIn("toc.js", str(self.soup), "模板应加载 toc.js")

    def test_toc_links_follow_grouped_order(self):
        """目录项按「基础信息/基金深度分析/行动建议/历史/LLM」分组顺序，组内按报告序号升序。"""
        links = self.soup.select("#toc-sidebar a[href^='#sec-']")
        # 预期分组顺序（测试常量）：基础信息 → 基金深度分析 → 历史 → LLM（行动建议组空，跳过）
        expected_keys = [
            "summary",
            "market_value",
            "category",
            "penetration",
            "fund_performance",
            "fund_manager",
            "position_relationship",
            "fund_concentration",
            "style_factor",
            "portfolio_history_drawdown",
            "news_correlation",
            "global_macro",
            "expert_review",
            "health_check",
            "penetration_deep",
            "llm_usage",
        ]
        link_keys = [link.get("href").replace("#sec-", "") for link in links]
        self.assertEqual(link_keys, expected_keys, "目录顺序应为五组分组顺序（组内按序号升序）")


class TestHtmlTocVisibility(unittest.TestCase):
    """左侧目录 TOC 可见性测试 — 不可见模块不出现在目录中。"""

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}

    def _render_with_visibility(self, visible_keys: set[str]) -> BeautifulSoup:
        sv_dict = {sec["key"]: sec["key"] in visible_keys for sec in self.order}
        return _render_template(
            _build_minimal_render_data(self.order, self.numbers, sv_dict),
        )

    def test_toc_only_always_visible(self):
        """仅 always 模块可见时，目录也只有对应链接。"""
        soup = self._render_with_visibility(_ALWAYS_KEYS)
        links = soup.select("#toc-sidebar a[href^='#sec-']")
        link_keys = {link.get("href", "").replace("#sec-", "") for link in links}
        self.assertEqual(link_keys, _ALWAYS_KEYS, f"目录应只含 always 模块: {_ALWAYS_KEYS}")

    def test_toc_tracks_nav_when_subset(self):
        """部分模块可见时，目录链接集合 = 横向 section-nav 链接集合。"""
        visible = _ALWAYS_KEYS | _FUND_DEEP_ANALYSIS_KEYS | _LLM_KEYS
        soup = self._render_with_visibility(visible)
        toc_keys = {a.get("href") for a in soup.select("#toc-sidebar a[href^='#sec-']")}
        nav_keys = {a.get("href") for a in soup.select("nav.section-nav a")}
        self.assertEqual(toc_keys, nav_keys, "目录与横向导航的链接集合应一致")


class TestSummaryDateTimeValueStyles(unittest.TestCase):
    """投资分析汇总：统计时间/所属交易日 值单元格样式（加粗 / 加粗+加大+蓝色）。"""

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    def _value_td_style(self, label: str) -> str:
        """在投资分析汇总中按标签名找对应行的值单元格（第2列）内联 style。"""
        summary = self.soup.find(id="sec-summary")
        self.assertIsNotNone(summary, "未找到 #sec-summary")
        for tr in summary.select("table.kv-table tr"):
            tds = tr.find_all("td")
            if len(tds) == 2 and tds[0].get_text(strip=True) == label:
                return tds[1].get("style", "")
        self.fail(f"未找到「{label}」行")

    def test_stat_time_value_bold(self):
        """统计时间值加粗。"""
        style = self._value_td_style("统计时间")
        self.assertRegex(
            style,
            r"font-weight:\s*(?:700|bold)",
            f"统计时间值应加粗，style={style!r}",
        )

    def test_trading_day_value_bold_larger_blue(self):
        """所属交易日值加粗+加大+蓝色。"""
        style = self._value_td_style("所属交易日")
        self.assertRegex(
            style,
            r"font-weight:\s*(?:700|bold)",
            f"所属交易日值应加粗，style={style!r}",
        )
        self.assertRegex(
            style,
            r"font-size:\s*1[5-9]px",
            f"所属交易日字号应加大，style={style!r}",
        )
        self.assertRegex(
            style,
            r"color:\s*#2E75B6",
            f"所属交易日值应为蓝色 2E75B6，style={style!r}",
        )

    def test_kv_label_style_unaffected(self):
        """标签列不新增内联样式（仅值列加样式）。"""
        summary = self.soup.find(id="sec-summary")
        for tr in summary.select("table.kv-table tr"):
            tds = tr.find_all("td")
            if len(tds) == 2 and tds[0].get_text(strip=True) in ("统计时间", "所属交易日"):
                self.assertEqual(
                    tds[0].get("style", ""),
                    "",
                    "标签列不应新增内联样式",
                )


class TestHtmlTocGroupedNav(unittest.TestCase):
    """目录分组导航测试 — 「基础信息/基金深度分析/行动建议/历史/LLM」五组折叠。

    覆盖导航收尾验收：分组渲染 / 折叠交互 / 移动端不溢出 / 键盘可达。
    左侧目录（toc-sidebar）按五组折叠；窄屏横向 section-nav 保持扁平兜底。
    """

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    # ── 分组渲染 ──────────────────────────────────────────────

    def test_four_nonempty_group_details_rendered(self):
        """目录按五组渲染 <details class='toc-group'>，非空组默认 open（展开）。"""
        details = self.soup.select("#toc-sidebar details.toc-group")
        # 测试常量下：基础信息/基金深度分析/历史/LLM 四组有章节，行动建议组空跳过
        self.assertEqual(len(details), 4, f"应有 4 个非空分组，实际 {len(details)}")
        for d in details:
            self.assertIsNotNone(d.get("open"), "非空分组应默认展开（open 属性）")

    def test_group_renders_correct_sections(self):
        """各组内渲染正确章节链接（组序固定，组内按报告序号升序）。"""

        def _group_keys(group_key: str) -> list[str]:
            d = self.soup.select_one(f"#toc-sidebar details.toc-group[data-group='{group_key}']")
            if d is None:
                return []
            return [a.get("href", "").replace("#sec-", "") for a in d.select("a[href^='#sec-']")]

        self.assertEqual(
            _group_keys("basic"),
            ["summary", "market_value", "category", "penetration"],
            "「基础信息」组应含 4 个基础章节",
        )
        self.assertEqual(
            _group_keys("fund_deep"),
            [
                "fund_performance",
                "fund_manager",
                "position_relationship",
                "fund_concentration",
                "style_factor",
            ],
            "「基金深度分析」组应含基金业绩 + 基金深度分析四章（含持仓关系矩阵/风格与因子分析）",
        )
        self.assertEqual(
            _group_keys("history"),
            ["portfolio_history_drawdown"],
            "「历史」组应含组合历史走势与回撤章",
        )
        self.assertEqual(
            _group_keys("llm"),
            [
                "news_correlation",
                "global_macro",
                "expert_review",
                "health_check",
                "penetration_deep",
                "llm_usage",
            ],
            "「LLM」组应含新闻关联 + LLM 文本章 + API 用量",
        )

    def test_group_title_shows_name_and_count(self):
        """分组标题显示组名 + 章节数徽标（徽标数 = 组内链接数）。"""
        for d in self.soup.select("#toc-sidebar details.toc-group"):
            summary = d.select_one("summary.toc-group-title")
            self.assertIsNotNone(summary, "每组应有 <summary> 标题")
            badge = summary.select_one(".toc-group-count")
            self.assertIsNotNone(badge, "分组标题应含章节数徽标")
            self.assertEqual(
                int(badge.get_text(strip=True)),
                len(d.select("a[href^='#sec-']")),
                f"组 {d.get('data-group')} 徽标数应等于组内章节数",
            )

    def test_real_registry_group_mapping(self):
        """真实注册表分组映射正确（含数据源可用性/组合演进/行动建议）。"""
        from src.python.core.registry import get_report_section_order
        from src.python.report.html_writer import _build_section_nav_groups

        order = get_report_section_order()
        numbers = {s["key"]: s["number"] for s in order}
        groups = _build_section_nav_groups(order, lambda key: True, numbers)
        by_key = {g["key"]: [s["key"] for s in g["sections"]] for g in groups}

        self.assertEqual(
            by_key["basic"],
            ["summary", "market_value", "category", "penetration", "data_source_status"],
            "「基础信息」组应含数据源可用性矩阵",
        )
        self.assertEqual(
            by_key["fund_deep"],
            [
                "fund_performance",
                "fund_manager",
                "position_relationship",
                "fund_concentration",
                "style_factor",
            ],
        )
        self.assertEqual(by_key["action"], ["action"], "「行动建议」组应含行动建议章")
        self.assertEqual(
            by_key["history"],
            ["portfolio_history_drawdown", "portfolio_evolution"],
            "「历史」组应含组合历史走势与回撤 + 组合演进",
        )
        self.assertEqual(
            by_key["llm"],
            [
                "news_correlation",
                "global_macro",
                "expert_review",
                "health_check",
                "penetration_deep",
                "llm_usage",
            ],
        )

    # ── 折叠交互 ──────────────────────────────────────────────

    def test_group_collapse_toggleable(self):
        """分组折叠经 <details>/<summary> 原生交互（点击 summary 展开/收起，无需 JS）。"""
        details = self.soup.select("#toc-sidebar details.toc-group")
        self.assertGreaterEqual(len(details), 1, "应至少渲染一个分组")
        for d in details:
            summary = d.select_one("summary")
            self.assertEqual(summary.name, "summary", "每组折叠开关应为 <summary>")
            self.assertIsNotNone(d.get("open"), "渲染侧默认 open 保证全量可见")

    def test_empty_group_skipped(self):
        """无可见章节的分组不渲染 <details>（测试常量下行动建议组空 → 跳过）。"""
        self.assertIsNone(
            self.soup.select_one("#toc-sidebar details.toc-group[data-group='action']"),
            "行动建议组无可见章节时不应渲染 <details>",
        )

    def test_action_visible_adds_action_group(self):
        """enable_action 开启（action 可见）时，「行动建议」组出现且含行动建议章。"""
        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        order.append({"key": "action", "name": "行动建议", "number": 17})
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: True for sec in order}
        soup = _render_template(_build_minimal_render_data(order, numbers, sv_dict))
        action = soup.select_one("#toc-sidebar details.toc-group[data-group='action']")
        self.assertIsNotNone(action, "enable_action 开启时「行动建议」组应渲染")
        keys = [a.get("href", "").replace("#sec-", "") for a in action.select("a[href^='#sec-']")]
        self.assertEqual(keys, ["action"], "「行动建议」组应含行动建议章")

    # ── 键盘可达 ──────────────────────────────────────────────

    def test_group_summary_keyboard_focusable(self):
        """每组折叠开关为 <summary>（原生可聚焦，Enter/Space 切换），满足键盘可达。"""
        for d in self.soup.select("#toc-sidebar details.toc-group"):
            summary = d.select_one("summary")
            self.assertIsNotNone(summary, "每组应有 <summary> 折叠开关（原生可聚焦）")
            self.assertNotEqual(
                summary.get("tabindex"),
                "-1",
                "分组标题不应被移出键盘焦点序列",
            )

    # ── 移动端不溢出 ──────────────────────────────────────────

    def test_mobile_fallback_nav_complete(self):
        """窄屏横向 section-nav 保持扁平并包含全部可见章节（移动端导航不因分组丢失章节）。"""
        links = self.soup.select("nav.section-nav a")
        self.assertEqual(len(links), len(self.sv_dict), "section-nav 应包含全部可见章节")
        self.assertGreaterEqual(len(links), 1)

    def test_section_nav_wraps_not_overflow(self):
        """section-nav 采用 flex-wrap（换行而非横向溢出）。"""
        self.assertIn("flex-wrap: wrap", self._template_css(), "section-nav 应允许换行避免横向溢出")

    def test_toc_hidden_on_narrow_screen(self):
        """窄屏（≤899px）隐藏左侧目录，移动端不因目录溢出。"""
        css = self._template_css()
        self.assertRegex(css, r"@media \(max-width: 899px\)", "应存在窄屏断点样式")
        self.assertRegex(
            css,
            r"\.toc-sidebar[\s,]*\.toc-toggle-btn\s*\{[^}]*display:\s*none",
            "窄屏应隐藏 .toc-sidebar 与悬浮展开按钮",
        )

    # ── LLM 章节标记 ──────────────────────────────────────────

    def test_llm_supported_sections_constant_matches_group(self):
        """_LLM_SUPPORTED_SECTIONS 与测试常量 _LLM_SUPPORTED_KEYS 一致（单一数据源防漂移）。"""
        from src.python.report.html_writer import _LLM_SUPPORTED_SECTIONS

        self.assertEqual(set(_LLM_SUPPORTED_SECTIONS), _LLM_SUPPORTED_KEYS)

    def test_llm_toc_links_marked(self):
        """LLM 章节目录链接带 toc-llm class + 🧠 图标（aria-hidden、文本 🧠）。"""
        for key in _LLM_SUPPORTED_KEYS:
            link = self.soup.select_one(f"#toc-sidebar a[href='#sec-{key}']")
            self.assertIsNotNone(link, f"目录缺少 LLM 章节 {key}")
            self.assertIn("toc-llm", link.get("class", []), f"LLM 章节 {key} 目录链接应带 toc-llm class")
            icon = link.select_one("span.toc-llm-icon")
            self.assertIsNotNone(icon, f"LLM 章节 {key} 目录链接应含 🧠 图标")
            self.assertEqual(icon.get("aria-hidden"), "true", f"LLM 章节 {key} 图标应 aria-hidden")
            self.assertIn("🧠", icon.get_text(strip=True), f"LLM 章节 {key} 图标文本应为 🧠")

    def test_non_llm_toc_links_unmarked(self):
        """非 LLM 章节目录链接不带 toc-llm class 与 🧠 图标。"""
        for link in self.soup.select("#toc-sidebar a[href^='#sec-']"):
            key = link.get("href", "").replace("#sec-", "")
            if key in _LLM_SUPPORTED_KEYS:
                continue
            self.assertNotIn("toc-llm", link.get("class", []), f"非 LLM 章节 {key} 不应带 toc-llm class")
            self.assertIsNone(
                link.select_one("span.toc-llm-icon"),
                f"非 LLM 章节 {key} 不应含 🧠 图标",
            )

    def test_section_nav_llm_links_marked(self):
        """section-nav 横向导航 LLM 章节带 class+图标，非 LLM 不带。"""
        for link in self.soup.select("nav.section-nav a"):
            key = link.get("href", "").replace("#sec-", "")
            if key in _LLM_SUPPORTED_KEYS:
                self.assertIn(
                    "toc-llm", link.get("class", []),
                    f"LLM 章节 {key} section-nav 应带 toc-llm class",
                )
                icon = link.select_one("span.toc-llm-icon")
                self.assertIsNotNone(icon, f"LLM 章节 {key} section-nav 应含 🧠 图标")
                self.assertIn("🧠", icon.get_text(strip=True), f"LLM 章节 {key} 图标文本应为 🧠")
            else:
                self.assertNotIn(
                    "toc-llm", link.get("class", []),
                    f"非 LLM 章节 {key} section-nav 不应带 toc-llm class",
                )
                self.assertIsNone(
                    link.select_one("span.toc-llm-icon"),
                    f"非 LLM 章节 {key} section-nav 不应含 🧠 图标",
                )

    def test_section_groups_carry_llm_supported_flag(self):
        """_build_section_nav_groups 输出 section dict 含 llm_supported 且值与集合一致。"""
        from src.python.report.html_writer import _build_section_nav_groups

        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        numbers = {sec["key"]: sec["number"] for sec in order}
        groups = _build_section_nav_groups(order, lambda key: True, numbers)
        for group in groups:
            for sec in group["sections"]:
                self.assertIn("llm_supported", sec, f"section {sec['key']} 应含 llm_supported 字段")
                self.assertEqual(
                    sec["llm_supported"],
                    sec["key"] in _LLM_SUPPORTED_KEYS,
                    f"section {sec['key']} llm_supported 值不正确",
                )

    def test_toc_llm_css_rules_defined(self):
        """模板 CSS 定义 toc-llm 相关规则（目录/横向导航/图标/active 态）。"""
        css = self._template_css()
        for rule in (
            ".toc-list a.toc-llm",
            ".toc-list a.toc-llm.active",
            ".section-nav a.toc-llm",
            ".toc-llm-icon",
        ):
            self.assertIn(rule, css, f"CSS 应包含规则「{rule}」")

    def test_llm_mark_color_reuses_dual_defined_variable(self):
        """LLM 标记复用双定义变量 --orange-text（浅/深主题均可读）。"""
        css = self._template_css()
        self.assertIn("--orange-text: #E65100", css, "浅色主题应定义 --orange-text: #E65100")
        self.assertIn("--orange-text: #ff8a50", css, "深色主题应定义 --orange-text: #ff8a50")
        self.assertIn("var(--orange-text)", css, "toc-llm 规则应引用 var(--orange-text)")

    def _template_css(self) -> str:
        """读取渲染后 HTML 中全部 <style> 文本。"""
        return "\n".join(s.get_text() for s in self.soup.select("style"))


class TestHtmlDataQualityBlocks(unittest.TestCase):
    """数据质量仪表盘「品种覆盖/可信度」区块渲染回归测试。

    回归场景：`position_status.items` / `data_freshness.items` 若在模板中按属性访问，
    会命中 dict 内置 `items` 方法（bound method）而非契约键 `"items"`——
    `data_quality` 子模块开启且契约有数据时迭代 bound method 崩溃
    （TypeError: 'builtin_function_or_method' object is not iterable）。
    修复采用 `.get("items")`（与生产代码一致）。本类回归断言正常渲染不再崩溃且行内容正确。
    """

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        cls.sv_dict = {sec["key"]: True for sec in cls.order}

    def _render_dq(self, position_status, data_freshness, enabled=True):
        render_data = _build_minimal_render_data(self.order, self.numbers, self.sv_dict)
        # 数据质量区块嵌套于「数据源可用性矩阵」章节（registry 中 data_source_status
        # 为 always 类型，number=18）——渲染需使其可见
        render_data["section_visible_dict"] = {**self.sv_dict, "data_source_status": True}
        render_data["section_numbers"] = {**self.numbers, "data_source_status": 18}
        render_data["data_quality_enabled"] = enabled
        render_data["position_status"] = position_status
        render_data["data_freshness"] = data_freshness
        return _render_template(render_data)

    def test_position_status_items_rendered(self):
        """品种覆盖区块 items 正常渲染（逐品种行输出，不崩溃）。"""
        soup = self._render_dq(
            {
                "available": True,
                "items": [
                    {"code": "000001", "name": "平安银行", "account": "全部", "status": "ok", "status_label": "正常", "reason": ""},
                    {"code": "510300", "name": "沪深300ETF", "account": "全部", "status": "stale", "status_label": "过期", "reason": "行情未更新"},
                ],
            },
            None,
        )
        text = soup.get_text()
        self.assertIn("品种覆盖（逐品种数据状态）", text)
        self.assertIn("平安银行", text)
        self.assertIn("沪深300ETF", text)
        self.assertIn("过期", text)

    def test_data_freshness_items_rendered(self):
        """可信度区块 items 正常渲染（新鲜度 + 单日跳变列）。"""
        soup = self._render_dq(
            None,
            {
                "available": True,
                "abnormal_count": 0,
                "summary": "",
                "items": [
                    {"code": "600519", "name": "贵州茅台", "account": "全部", "freshness": "ok", "freshness_label": "新鲜", "change_pct": 0.5, "jump": False, "jump_label": None},
                    {"code": "601318", "name": "中国平安", "account": "全部", "freshness": "stale", "freshness_label": "过期", "change_pct": 23.4, "jump": True, "jump_label": "跳变"},
                ],
            },
        )
        text = soup.get_text()
        self.assertIn("可信度（数据新鲜度 + 单日跳变）", text)
        self.assertIn("贵州茅台", text)
        self.assertIn("中国平安", text)
        self.assertIn("跳变", text)

    def test_empty_items_shows_fallback(self):
        """available=True 但 items 为空列表 → 显示降级占位而非崩溃。"""
        soup = self._render_dq(
            {"available": True, "items": []},
            {"available": True, "items": [], "abnormal_count": 0, "summary": ""},
        )
        text = soup.get_text()
        self.assertIn("未获取行情数据，品种覆盖无法判定", text)

    def test_data_quality_disabled_skips_blocks(self):
        """data_quality_enabled=False → 两区块均不渲染。"""
        soup = self._render_dq(
            {
                "available": True,
                "items": [{"code": "000001", "name": "平安银行", "account": "全部", "status": "ok", "status_label": "正常", "reason": ""}],
            },
            {
                "available": True,
                "items": [{"code": "600519", "name": "贵州茅台", "account": "全部", "freshness": "ok", "freshness_label": "新鲜", "change_pct": 0.5, "jump": False, "jump_label": None}],
                "abnormal_count": 0,
                "summary": "",
            },
            enabled=False,
        )
        text = soup.get_text()
        self.assertNotIn("品种覆盖（逐品种数据状态）", text)
        self.assertNotIn("可信度（数据新鲜度 + 单日跳变）", text)


if __name__ == "__main__":
    unittest.main()
