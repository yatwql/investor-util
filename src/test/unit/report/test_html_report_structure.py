"""HTML 报告结构测试 — 导航/章节可见性/自定义排序/锚点 + 折叠章节。

覆盖场景：
  - 导航链接 ↔ section 容器一一对应（无断链/无悬空锚点）
  - 所有 section 的 CSS order 值唯一且与 section_numbers 一致
  - 不可见模块不在导航中出现，且其 section 容器不渲染（含 LLM 关闭时的 llm_usage）
  - 自定义 section_order 下的排序正确性
  - 正文大块折叠（section-fold）的收起状态、锚点与逐章覆盖

兄弟分片：test_html_report_structure_toc.py（返回顶部/目录）、
test_html_report_structure_content.py（交互图表/主题/数据质量块/页脚/期间标注）；
边缘/异常测试见 test_html_report_structure_edge.py。

运行：
  pytest src/test/unit/report/test_html_report_structure.py -v
"""

from __future__ import annotations

import os
import re
import unittest

import pytest
from bs4 import BeautifulSoup

from src.python.core.registry import _REPORT_SECTION_DEFAULT as _REGISTRY_SECTION_DEFAULT

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ── 常量 ──────────────────────────────────────────────────────

_TEMPLATE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "tmpl", "report_template.html"),
)
_WHATIF_TEMPLATE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "tmpl", "whatif_template.html"),
)

# 默认注册表 key（按默认顺序，与 registry.py 对齐）
_ALL_KEYS_DEFAULT = [
    "summary",
    "holdings_detail",
    "penetration",
    "fund_performance",
    "position_structure",
    "style_factor",
    "news_correlation",
    "global_macro",
    "expert_review",
    "health_check",
    "penetration_deep",
    "portfolio_history_drawdown",
    "llm_usage",
]

_ALWAYS_KEYS = {"summary", "holdings_detail", "penetration", "fund_performance"}
_FUND_DEEP_ANALYSIS_KEYS = {"position_structure", "style_factor"}
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

# 场景章节序（真值取自 core/registry.py 章节注册表，nav_group/llm_supported/显示名
# 等字段同源）：裁剪到 _ALL_KEYS_DEFAULT 并重排号为可见连续序 1..N——模拟生产端
# 可见重编号；不再自持第二份字段字面量（注册表改名/改分组测试自动跟随）。
_REGISTRY_SECTION_BY_KEY = {sec["key"]: sec for sec in _REGISTRY_SECTION_DEFAULT}

_REPORT_SECTION_DEFAULT: list[dict] = [
    {**_REGISTRY_SECTION_BY_KEY[key], "number": idx} for idx, key in enumerate(_ALL_KEYS_DEFAULT, start=1)
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

    def _sv_fn(key: str, _d: dict = _sv_dict) -> bool:
        return bool(_d.get(key, False))

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
        """导航链接数量应等于可见模块数（全部可见 = 13）。"""
        links = self.soup.select("nav.section-nav a")
        self.assertEqual(len(links), 13, f"导航应有 13 个链接，实际 {len(links)}")

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

    def test_titles_rendered_from_registry_names(self):
        """模板与 partials 章节标题一律 `section_names` 动态取名（改名收敛为注册表单点变更）。"""
        hard_re = re.compile(r"section_numbers\[['\"](\w+)['\"]\]\s*}}\s*、\s*([^\s{<]+)")
        tmpl_dir = os.path.dirname(_TEMPLATE_PATH)
        files = [os.path.join(tmpl_dir, "report_template.html")]
        partial_dir = os.path.join(tmpl_dir, "partials")
        files += [os.path.join(partial_dir, f) for f in sorted(os.listdir(partial_dir)) if f.endswith(".html")]
        violations: list[str] = []
        for path in files:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for m in hard_re.finditer(text):
                if not m.group(2).startswith("{"):
                    violations.append(f"{os.path.basename(path)}: …}}}}、{m.group(2)!r}（硬编码显示名）")
        assert not violations, "章节标题须用 {{ section_names[key] }} 取名：" + "; ".join(violations)

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
        """所有模块不可见 → 导航为空、只渲染无条件的 always 章。

        注：仅 4 个 always 模块（summary / holdings_detail / penetration /
        fund_performance）的 div 是无条件渲染的；其余章节（含 llm_usage）
        均包裹在 {% if section_visible() %} 内，不可见时完全不输出。
        """
        soup = self._render_with_visibility(set())
        links = soup.select("nav.section-nav a")
        self.assertEqual(len(links), 0, "全部不可见时导航应为空")
        rendered_ids = {sec.get("id", "") for sec in soup.select("div.section")}
        self.assertEqual(
            rendered_ids,
            {f"sec-{k}" for k in _ALWAYS_KEYS},
            "全部不可见时应只渲染 always 模块的 section 容器",
        )

    def test_llm_usage_hidden_when_not_visible(self):
        """llm_usage 不可见（LLM 关闭）时整章不渲染。

        回归：该章曾漏加 {% if section_visible("llm_usage") %} 守卫，LLM 关闭时
        仍渲染出「无序号标题 + style=\"order: ;\"」，而 order 空值被 CSS 忽略后
        回退为 0，使该章跳到所有章节之前。
        """
        soup = self._render_with_visibility(_ALWAYS_KEYS)
        self.assertIsNone(soup.find(id="sec-llm_usage"), "llm_usage 不可见时不应渲染 section 容器")
        self.assertNotIn("order: ;", str(soup), "不应输出空的 CSS order 声明（该章会被排到最前）")

    def test_llm_usage_rendered_last_when_visible(self):
        """llm_usage 可见时正常渲染，且 order 为其末位序号。"""
        soup = self._render_with_visibility(_ALWAYS_KEYS | {"llm_usage"})
        sec = soup.find(id="sec-llm_usage")
        self.assertIsNotNone(sec, "llm_usage 可见时应渲染 section 容器")
        self.assertIn(f"order: {self.numbers['llm_usage']}", sec.get("style", ""))


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
            {"key": "holdings_detail", "name": "持仓明细与分类", "number": 3},
            {"key": "penetration", "name": "资产穿透TOP10", "number": 4},
            # 基金深度分析保持默认
            {"key": "position_structure", "name": "持仓结构与集中度", "number": 5},
            {"key": "style_factor", "name": "风格与因子分析", "number": 6},
            # news 保持默认
            {"key": "news_correlation", "name": "财经新闻热点与持仓关联分析", "number": 7},
            # llm 保持默认
            {"key": "global_macro", "name": "全球政经局势", "number": 8},
            {"key": "expert_review", "name": "智囊团深度复盘", "number": 9},
            {"key": "health_check", "name": "持仓体检报告", "number": 10},
            {"key": "penetration_deep", "name": "穿透深度分析", "number": 11},
            {"key": "portfolio_history_drawdown", "name": "组合历史走势与回撤", "number": 12},
            {"key": "llm_usage", "name": "LLM API 用量", "number": 13},
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
        # llm_usage 的 order 应为 13（末位，合并章节后总条目 17）
        self.assertEqual(orders["sec-llm_usage"], 13, "llm_usage 的 order 应为 13（末位）")


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


class TestSectionFold(unittest.TestCase):
    """正文大块默认折叠（details.section-fold）— 包裹结构 / fold.js 交互钩子。"""

    @classmethod
    def setUpClass(cls):
        cls.order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        cls.numbers = {sec["key"]: sec["number"] for sec in cls.order}
        cls.sv_dict = {sec["key"]: True for sec in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )
        with open(_TEMPLATE_PATH, encoding="utf-8") as f:
            cls.template_src = f.read()

    def test_history_section_wrapped_by_fold_details(self):
        """历史走势章内容包在 details.section-fold 内且默认收起（无 open）。"""
        section = self.soup.select_one("#sec-portfolio_history_drawdown")
        self.assertIsNotNone(section, "历史走势章应存在")
        details = section.select_one("details.section-fold")
        self.assertIsNotNone(details, "历史走势章应含 details.section-fold 折叠块")
        self.assertIsNone(details.get("open"), "折叠块应默认收起（不带 open 属性）")
        summary = details.select_one(":scope > summary.section-fold-summary")
        self.assertIsNotNone(summary, "折叠块应有 summary 提示条")
        # summary 在内容之前（原生折叠结构：summary 为 details 首子元素）
        children = [c for c in details.children if getattr(c, "name", None)]
        self.assertEqual(children[0].name, "summary", "summary 应为折叠块第一个元素")

    def test_fold_block_uses_native_details_no_js_dependency_for_toggle(self):
        """折叠/展开用原生 details（键盘可达、无 JS 也能手动展开）。"""
        details = self.soup.select_one("details.section-fold")
        self.assertIsNotNone(details)
        # 未引入自绘开关类（折叠靠原生 summary 点击）
        self.assertIsNone(details.select_one(".fold-toggle-btn"))

    def test_template_references_fold_js_and_assets_registered(self):
        """模板引用 fold.js 且资产清单（单一事实来源）已登记。"""
        from src.python.report.html_writer_assets import JS_ASSETS

        self.assertIn('<script defer src="fold.js"></script>', self.template_src)
        self.assertIn("fold.js", JS_ASSETS, "fold.js 应登记进 JS_ASSETS 内嵌清单")

    def test_fold_js_interaction_hooks(self):
        """fold.js 含锚点展开 / 打印展开恢复 / 图表 resize 钩子（源码结构断言）。"""
        fold_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "fold.js"))
        with open(fold_path, encoding="utf-8") as f:
            fold_js = f.read()
        self.assertIn("hashchange", fold_js, "锚点定位应自动展开目标章节折叠块")
        self.assertIn("beforeprint", fold_js, "打印前应展开全部折叠块")
        self.assertRegex(
            fold_js,
            r"beforeprint[\s\S]{0,400}?\},\s*true\)",
            "beforeprint 应以捕获阶段注册（先于 chart-print 快照展开）",
        )
        self.assertIn("afterprint", fold_js, "打印后应恢复用户折叠状态")
        self.assertIn("toggle", fold_js, "手动展开应绑定 toggle 钩子（图表 resize 兜底）")
        self.assertIn("section-fold", fold_js, "钩子应作用于 details.section-fold")

    def test_fold_js_keeps_collapsed_on_initial_load(self) -> None:
        """打开报告（初始 load，含地址带 #锚点/浏览器恢复会话）缺省一律收起。

        回归：旧实现 init 时无条件执行锚点展开，浏览器恢复会话带 #sec-…
        打开报告会把目标章折叠块自动展开，违背「打开缺省收起」；
        会话内点击目录触发 hashchange 仍展开（跳转可见性不受影响）。
        """
        fold_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "fold.js"))
        with open(fold_path, encoding="utf-8") as f:
            fold_js = f.read()
        self.assertNotIn(
            "handleHash();",
            fold_js,
            "初始 load 不得执行锚点展开（打开报告时所有折叠块必须缺省收起）",
        )
        self.assertIn("addEventListener('hashchange'", fold_js, "会话内锚点跳转仍应自动展开目标章")


class TestSectionFoldMoreChapters(unittest.TestCase):
    """正文默认折叠的扩展章（财经新闻关联 / 组合演进 / 持仓基本面 / 持仓结构与集中度 /
    风格与因子分析 / 数据源可用性矩阵）。

    与「组合历史走势与回撤」同构：章标题常显于折叠块外，内容包在
    ``details.section-fold`` 内且默认收起（无 ``open``），``summary`` 为折叠块
    首子元素并携带关键摘要；「回到顶部」留在折叠块外（收起态仍可点）。
    锚点定位/打印展开由 fold.js 统一处理（对全部 ``details.section-fold`` 生效），
    打开报告（含带 #锚点）缺省一律收起（初始 load 不执行锚点展开）。
    """

    _FOLD_KEYS = (
        "news_correlation",
        "portfolio_evolution",
        "fundamental_snapshot",
        "position_structure",
        "style_factor",
        "data_source_status",
        "holding_change",
        "schedule_replay",
    )

    @classmethod
    def setUpClass(cls):
        from src.python.core.registry import get_report_section_order

        order = [dict(sec) for sec in get_report_section_order()]
        numbers = {sec["key"]: sec["number"] for sec in order}
        # 全部章节可见（行动建议章的呈现由 test_action_html 覆盖，不在本用例范围）
        sv_dict = {sec["key"]: True for sec in order}
        sv_dict["action"] = False
        data = _build_minimal_render_data(order, numbers, sv_dict)
        data["evolution_data"] = {
            "available": True,
            "snapshot_count": 5,
            "min_snapshots": 3,
            "periods": ["07-01", "07-02"],
            "total_value": [100000.0, 110000.0],
            "total_cost": [90000.0, 90000.0],
            "total_pnl": [10000.0, 20000.0],
            "holding_counts": [2, 2],
            "account_flows": {"账户A": [60.0, 40.0]},
            "hhi": [0.52, 0.58],
            "top_holdings": [],
        }
        data["financial_indicator_data"] = {
            "available": True,
            "entry_count": 8,
            "rows": [],
            "failures": [],
        }
        data["financial_report_digest_data"] = {
            "available": True,
            "entry_count": 3,
            "rows": [],
            "failures": [],
        }
        # 非空新闻列表：空表会被模板判为「暂无新闻」分支（无 .section-content）
        data["news_data"] = [
            {
                "url": "https://example.com/n1",
                "title": "示例新闻",
                "intro": "摘要",
                "media_name": "示例媒体",
                "ctime": "2026-10-04 09:00:00",
                "matched_keywords": ["示例关键词"],
            }
        ]
        # 持仓变动/调仓回放两章需视图 truthy 才渲染（局部缺省均可 .get 兜底）
        data["holding_change_view"] = {
            "available": True,
            "title_summary": "2 起变动事件",
            "window_lines": ["窗口：2026-09-01 ~ 2026-10-06"],
            "event_header": ["日期", "名称", "方向", "数量", "金额"],
            "event_rows": [],
            "limitations_note": "区间净额推断，非逐笔",
        }
        data["schedule_replay_view"] = {
            "available": True,
            "title_summary": "回放窗口 8 个调仓日",
            "summary_lines": ["纪律回放 vs 买入持有"],
            "metric_header": ["策略", "区间收益"],
            "metric_rows": [],
        }
        cls.soup = _render_template(data)

    def _fold_of(self, key: str):
        """取章节的折叠块，顺带断言章节与折叠块存在（供各用例复用）。"""
        section = self.soup.select_one(f"#sec-{key}")
        self.assertIsNotNone(section, f"{key} 章应存在")
        details = section.select_one("details.section-fold")
        self.assertIsNotNone(details, f"{key} 章内容应包在 details.section-fold 内")
        return section, details

    def test_content_wrapped_and_collapsed_by_default(self):
        """各章内容均包在 details.section-fold 内且默认收起（无 open 属性）。"""
        for key in self._FOLD_KEYS:
            with self.subTest(section=key):
                _section, details = self._fold_of(key)
                self.assertIsNone(details.get("open"), f"{key} 章折叠块应默认收起")
                self.assertIsNotNone(
                    details.select_one(".section-content"),
                    f"{key} 章内容区应在折叠块内（收起即隐藏正文）",
                )

    def test_summary_is_first_child_and_tells_how_to_toggle(self):
        """summary 为折叠块首子元素，且文案自带展开/收起指引（原生可键盘操作）。"""
        for key in self._FOLD_KEYS:
            with self.subTest(section=key):
                _section, details = self._fold_of(key)
                summary = details.select_one(":scope > summary.section-fold-summary")
                self.assertIsNotNone(summary, f"{key} 章折叠块应有 summary 提示条")
                children = [c for c in details.children if getattr(c, "name", None)]
                self.assertEqual(
                    children[0].name,
                    "summary",
                    f"{key} 章 summary 应为折叠块第一个元素（原生折叠结构）",
                )
                self.assertIn("展开", summary.get_text(), "提示条应说明点击可展开")
                self.assertIn("收起", summary.get_text(), "提示条应说明点击可收起")

    def test_section_title_and_back_to_top_stay_outside_fold(self):
        """章标题与「回到顶部」在折叠块外——收起态下标题常显、仍可回顶。"""
        for key in self._FOLD_KEYS:
            with self.subTest(section=key):
                section, details = self._fold_of(key)
                title = section.select_one(".section-title")
                self.assertIsNotNone(title, f"{key} 章应有标题")
                self.assertIsNot(title.parent, details, f"{key} 章标题应在折叠块外")
                back = section.select_one(".back-to-top-link")
                self.assertIsNotNone(back, f"{key} 章应有「回到顶部」")
                self.assertNotIn(details, back.parents, f"{key} 章「回到顶部」应在折叠块外")

    def test_summary_carries_headline_stats(self):
        """提示条带该章关键摘要（条数/快照数/区块标的数/矩阵行数），收起态也有信息量。"""
        expectations = {
            "news_correlation": "条关联新闻",
            "portfolio_evolution": "份快照",
            "fundamental_snapshot": "财务指标",
            "position_structure": "只基金",
            "style_factor": "只基金风格",
            "data_source_status": "个数据源",
            "holding_change": "事件清单与结构演变",
            "schedule_replay": "回放对照",
        }
        for key, needle in expectations.items():
            with self.subTest(section=key):
                _section, details = self._fold_of(key)
                text = details.select_one("summary").get_text()
                self.assertIn(needle, text, f"{key} 章提示条应携带关键摘要")


if __name__ == "__main__":
    unittest.main()


# ═══════════════════════════════════════════════════════════════
#  Test: 因子目录区块（风格与因子分析区，实验性功能 factor_catalog）
# ═══════════════════════════════════════════════════════════════


class TestFactorCatalogSection(unittest.TestCase):
    """HTML 端区块四（R-FCT-04 载体）：关态无感 / 可用渲染 / 占位。"""

    _FC_DATA = {
        "available": True,
        "reason": None,
        "version": "2026.10.06.1",
        "catalog_size": 2,
        "computed": 1,
        "neutral_above": 1,
        "neutral_total": 1,
        "rating": "1/1 中性上方",
        "pool_size": 4,
        "factors": [
            {
                "slug": "qlib_rsi_14",
                "family": "qlib158",
                "family_label": "qlib158 技术因子族",
                "label": "RSI(14)",
                "value": 61.2,
                "neutral": 50.0,
                "above": True,
                "codes_ok": 4,
                "computable": True,
                "reason": None,
            },
            {
                "slug": "amihud_20",
                "family": "academic",
                "family_label": "学术因子族",
                "label": "Amihud 非流动性",
                "value": None,
                "neutral": None,
                "above": None,
                "codes_ok": 0,
                "computable": False,
                "reason": "日K不可得",
            },
        ],
    }

    @staticmethod
    def _render(fc_data=None, inject=True):
        order = [dict(sec) for sec in _REPORT_SECTION_DEFAULT]
        numbers = {sec["key"]: sec["number"] for sec in order}
        sv_dict = {sec["key"]: True for sec in order}
        data = _build_minimal_render_data(order, numbers, sv_dict)
        if inject:
            data["factor_catalog_data"] = fc_data
        return _render_template(data)

    def test_absent_key_no_block(self):
        """键缺失（旧管线/关态透传前）→ 区块不渲染，不报错。"""
        soup = self._render(inject=False)
        assert "四、因子目录" not in soup.get_text()

    def test_none_data_no_block(self):
        """数据为 None（开关关闭）→ 区块不渲染。"""
        soup = self._render(fc_data=None)
        assert "四、因子目录" not in soup.get_text()

    def test_available_renders_block(self):
        """可用数据 → 标题/摘要/因子行/相对中性全渲染。"""
        soup = self._render(fc_data=dict(self._FC_DATA))
        text = soup.get_text()
        assert "四、因子目录" in text
        assert "RSI(14)" in text
        assert "中性上方" in text
        assert "（日K不可得）" in text

    def test_unavailable_shows_placeholder(self):
        """available=False → 占位文案含具体原因。"""
        soup = self._render(fc_data={"available": False, "reason": "股票池为空", "factors": []})
        text = soup.get_text()
        assert "四、因子目录" in text
        assert "因子目录数据不足（股票池为空）" in text
        assert "RSI(14)" not in text


class TestFaviconInline:
    """报告 tab 图标内联 data URI（单文件产物零外链纪律）。"""

    @staticmethod
    def _icon_href(path: str) -> str:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        m = re.search(r'<link rel="icon" href="([^"]+)"', content)
        assert m, f"模板应声明标签页图标: {path}"
        return m.group(1)

    def test_report_template_inline_icon(self):
        """主报告模板图标须内联 data URI 且用报告侧品牌蓝（外链会破坏单文件产物）。"""
        href = self._icon_href(_TEMPLATE_PATH)
        assert href.startswith("data:image/svg+xml,"), "图标须内联 data URI，报告单文件零外链"
        assert "%232E75B6" in href, "报告侧图标底色须为报告品牌蓝（DESIGN.md Colors 双面各系）"

    def test_whatif_template_inline_icon(self):
        """What-if 模板同样内联声明（与主报告同款图标）。"""
        href = self._icon_href(_WHATIF_TEMPLATE_PATH)
        assert href.startswith("data:image/svg+xml,"), "What-if 页图标须内联 data URI"
        assert "%232E75B6" in href, "What-if 页与报告同侧品牌蓝"
