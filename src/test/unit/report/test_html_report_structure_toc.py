"""HTML 报告结构测试 — 返回顶部与目录（TOC）。

覆盖场景：
  - 返回顶部按钮结构与出现时机
  - TOC 侧栏结构、可见性开关、分组导航与跨组穿插顺序

运行：
  pytest src/test/unit/report/test_html_report_structure_toc.py -v
"""

from __future__ import annotations

import re
import unittest

import pytest
from bs4 import BeautifulSoup

from .test_html_report_structure import (
    _ALWAYS_KEYS,
    _FUND_DEEP_ANALYSIS_KEYS,
    _LLM_KEYS,
    _LLM_SUPPORTED_KEYS,
    _REPORT_SECTION_DEFAULT,
    _build_minimal_render_data,
    _render_template,
    _get_section_id_from_href,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


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
        """目录链接数量 = 可见模块数（全部可见 = 15）。"""
        links = self.soup.select("#toc-sidebar a[href^='#sec-']")
        self.assertEqual(len(links), 13, f"目录应有 13 个链接，实际 {len(links)}")

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
        """目录项按分组聚合且展开后报告号严格递增（按报告号线性序扫描、同组连续段聚块，无跳号回跳）。"""
        links = self.soup.select("#toc-sidebar a[href^='#sec-']")
        # 测试场景下组序（动态 min 排序）：基础信息 → 基金深度分析 → LLM → 历史 → 附录（LLM API 用量）
        expected_keys = [
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
        link_keys = [link.get("href").replace("#sec-", "") for link in links]
        self.assertEqual(link_keys, expected_keys, "目录顺序应为分组聚合顺序（组间按最小号、组内按号升序）")
        # 结构不变式：展开后的报告号严格 1..N 连续递增 —— 目录展开序必须等于正文线性序
        numbers = []
        for link in links:
            m = re.match(r"(\d+)、", link.get_text())
            assert m, f"目录项应带报告号前缀: {link.get_text()!r}"
            numbers.append(int(m.group(1)))
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)), "目录展开报告号应严格连续 1..N（无跳号回跳）")


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


class TestHtmlTocGroupedNav(unittest.TestCase):
    """目录分组导航测试 — 「基础信息/基金深度分析/行动建议/历史/LLM/附录」六组折叠。

    覆盖导航收尾验收：分组渲染 / 折叠交互 / 移动端不溢出 / 键盘可达。
    左侧目录（toc-sidebar）按六组折叠；窄屏横向 section-nav 保持扁平兜底。
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
        """目录按分组渲染 <details class='toc-group'>，非空组默认 open（展开）。"""
        details = self.soup.select("#toc-sidebar details.toc-group")
        # 测试场景下：6 组中基础信息/基金深度分析/LLM/历史/附录五组非空（附录组仅 LLM API 用量），行动建议组空跳过
        self.assertEqual(len(details), 5, f"应有 5 个非空分组，实际 {len(details)}")
        for d in details:
            self.assertIsNotNone(d.get("open"), "非空分组应默认展开（open 属性）")

    def test_group_renders_correct_sections(self):
        """各组内渲染正确章节链接（组间按最小号动态排序，组内按报告号升序）。"""

        def _group_keys(group_key: str) -> list[str]:
            d = self.soup.select_one(f"#toc-sidebar details.toc-group[data-group='{group_key}']")
            if d is None:
                return []
            return [a.get("href", "").replace("#sec-", "") for a in d.select("a[href^='#sec-']")]

        self.assertEqual(
            _group_keys("basic"),
            ["summary", "holdings_detail", "penetration"],
            "「基础信息」组应含 3 个基础章节",
        )
        self.assertEqual(
            _group_keys("fund_deep"),
            [
                "fund_performance",
                "position_structure",
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
            ],
            "「LLM」组应含新闻关联 + LLM 文本四章（API 用量归附录组）",
        )
        self.assertEqual(
            _group_keys("appendix"),
            ["llm_usage"],
            "「附录」组在本场景下含 LLM API 用量章",
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
        """真实注册表分组映射正确（含附录组：数据源可用性/持仓基本面/API 用量）。"""
        from src.python.core.registry import get_report_section_order
        from src.python.report.html_writer import _build_section_nav_groups

        order = get_report_section_order()
        numbers = {s["key"]: s["number"] for s in order}
        groups = _build_section_nav_groups(order, lambda key: True, numbers)
        by_key = {g["key"]: [s["key"] for s in g["sections"]] for g in groups}

        self.assertEqual(
            by_key["basic"],
            ["summary", "holdings_detail", "penetration"],
            "「基础信息」组应含汇总/持仓明细/穿透三章",
        )
        self.assertEqual(
            by_key["fund_deep"],
            [
                "fund_performance",
                "position_structure",
                "style_factor",
            ],
        )
        self.assertEqual(by_key["action"], ["action"], "「行动建议」组应含行动建议章")
        self.assertEqual(
            by_key["history"],
            ["portfolio_history_drawdown", "portfolio_evolution", "holding_change", "event_impact", "schedule_replay"],
            "「历史」组应含组合历史走势与回撤 + 组合演进 + 持仓变动复盘 + 事件窗量化对照 + 调仓纪律回放",
        )
        self.assertEqual(
            by_key["llm"],
            [
                "news_correlation",
                "global_macro",
                "expert_review",
                "health_check",
                "penetration_deep",
            ],
            "「LLM」组应含新闻关联 + LLM 文本四章（API 用量归附录组）",
        )
        self.assertEqual(
            by_key["appendix"],
            ["data_source_status", "fundamental_snapshot", "llm_usage"],
            "「附录」组应含数据源可用性矩阵/持仓基本面/API 用量",
        )
        # 结构不变式：全部可见章节分组覆盖（每章恰属一组，无遗漏无重复）
        flat = [s["key"] for g in groups for s in g["sections"]]
        self.assertEqual(len(flat), len(set(flat)), "章节不应在多个分组中重复出现")
        self.assertEqual(set(flat), set(numbers), "分组应覆盖全部章节")
        # 结构不变式：默认注册序下展开报告号严格 1..N（目录展开序 == 正文线性序，无跳号回跳）
        flat_numbers = [s["number"] for g in groups for s in g["sections"]]
        self.assertEqual(flat_numbers, list(range(1, len(flat_numbers) + 1)), "展开报告号应严格连续 1..N")

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
                    "toc-llm",
                    link.get("class", []),
                    f"LLM 章节 {key} section-nav 应带 toc-llm class",
                )
                icon = link.select_one("span.toc-llm-icon")
                self.assertIsNotNone(icon, f"LLM 章节 {key} section-nav 应含 🧠 图标")
                self.assertIn("🧠", icon.get_text(strip=True), f"LLM 章节 {key} 图标文本应为 🧠")
            else:
                self.assertNotIn(
                    "toc-llm",
                    link.get("class", []),
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


class TestTocCrossGroupInterleave(unittest.TestCase):
    """跨组交错回归：附录章插号段中间时目录展开仍严格线性 1..N（rf-561）。

    分组投影按报告号线性连续段分块——组在号序断点处拆块、同组可出现多块，
    展开序恒等于正文线性序（正文/Excel/锚点跳转不受分组影响）。
    """

    @classmethod
    def setUpClass(cls):
        from src.python.core.registry import get_report_section_order

        # 生产真值全集（文件内本地常量是 13 章最小场景，不含附录章）
        cls.order = [dict(sec) for sec in get_report_section_order()]
        # 数据源可用性矩阵（附录组）从尾部插到第 5 位（劈开基金深度分析号段），按配置序重编号
        data_source = next(s for s in cls.order if s["key"] == "data_source_status")
        cls.order.remove(data_source)
        cls.order.insert(4, data_source)
        for i, sec in enumerate(cls.order, 1):
            sec["number"] = i
        cls.numbers = {s["key"]: s["number"] for s in cls.order}
        cls.sv_dict = {s["key"]: True for s in cls.order}
        cls.soup = _render_template(
            _build_minimal_render_data(cls.order, cls.numbers, cls.sv_dict),
        )

    def test_toc_expands_strictly_linear_after_interleave(self):
        """展开序 = 正文线性序（key 逐位）且报告号严格 1..N——跨组插号无跳号回跳。"""
        links = self.soup.select("#toc-sidebar a[href^='#sec-']")
        link_keys = [a.get("href").replace("#sec-", "") for a in links]
        self.assertEqual(
            link_keys,
            [s["key"] for s in self.order],
            "目录展开序应等于正文线性序（配置序）",
        )
        numbers = []
        for a in links:
            m = re.match(r"(\d+)、", a.get_text())
            assert m, f"目录项应带报告号前缀: {a.get_text()!r}"
            numbers.append(int(m.group(1)))
        self.assertEqual(
            numbers,
            list(range(1, len(numbers) + 1)),
            "展开报告号应严格连续 1..N（无跳号回跳）",
        )

    def test_interleaved_groups_split_at_breakpoints(self):
        """被插入点劈开的组拆为多块（同组可重复），块内拼接覆盖全部章节。"""
        details = self.soup.select("#toc-sidebar details.toc-group")
        block_keys = [d.get("data-group") for d in details]
        # 插入点两侧：附录组尾部（基本面/API 用量）与基金深度组余部各自成块
        self.assertGreaterEqual(block_keys.count("appendix"), 2, "附录组被插入点劈开应拆为多块")
        self.assertGreaterEqual(block_keys.count("fund_deep"), 2, "基金深度分析组号段被楔入应拆为多块")
        # 块拼接 = 线性序全覆盖（无遗漏、无重复）
        flat = [a.get("href").replace("#sec-", "") for d in details for a in d.select("a[href^='#sec-']")]
        self.assertEqual(
            flat,
            [s["key"] for s in self.order],
            "分组块拼接应覆盖全部章节且顺序 = 线性序",
        )


if __name__ == "__main__":
    unittest.main()
