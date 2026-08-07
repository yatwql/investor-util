"""HTML 报告生成模块单元测试。

测试目标：
  - write_html_report 中 a_indices/us_indices 以 dict 类型传入 generate_all_llm
  - 模板渲染使用独立 list 变量（不因 .values() 缺失崩溃）

运行：
  pytest src/test/unit/report/test_html_writer.py -v
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from src.python.core.models import Holding
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


# ============================================================
#  Template rendering — 财经新闻热点与持仓关联分析
# ============================================================


class TestJinjaFilters(unittest.TestCase):
    """Jinja2 自定义过滤器测试。"""

    def setUp(self):
        from src.python.report.html_jinja_env import _jinja_price_type_color, _jinja_thousands

        self.fn = _jinja_thousands
        self.price_type_fn = _jinja_price_type_color

    def test_thousands_formats_integer(self):
        self.assertEqual(self.fn(2500), "2,500")

    def test_thousands_formats_large(self):
        self.assertEqual(self.fn(1234567), "1,234,567")

    def test_thousands_handles_none(self):
        self.assertEqual(self.fn(None), "None")

    def test_thousands_handles_string(self):
        self.assertEqual(self.fn("abc"), "abc")

    # ── price_type_color 过滤器 ─────────────────────────────────

    def test_price_type_color_onchange(self):
        """场内收盘价(T) → var(--rating-stable)（主题切换 主题 CSS 变量）"""
        self.assertEqual(self.price_type_fn("场内收盘价(T)"), "var(--rating-stable)")

    def test_price_type_color_nav_today(self):
        """官方净值(T) → var(--rating-stable)（主题切换 主题 CSS 变量）"""
        self.assertEqual(self.price_type_fn("官方净值(T)"), "var(--rating-stable)")

    def test_price_type_color_qdii_t_minus_1(self):
        """QDII 官方净值(T-1) → var(--rating-stable)（主题切换 主题 CSS 变量）"""
        self.assertEqual(self.price_type_fn("官方净值(T-1)", "标普500(QDII)"), "var(--rating-stable)")

    def test_price_type_color_non_qdii_t_minus_1(self):
        """非 QDII 官方净值(T-1) → 不蓝"""
        self.assertEqual(self.price_type_fn("官方净值(T-1)", "易方达中小盘"), "")

    def test_price_type_color_t_minus_1_no_name(self):
        """官方净值(T-1) 无名称 → 不蓝"""
        self.assertEqual(self.price_type_fn("官方净值(T-1)"), "")

    def test_price_type_color_intraday(self):
        """场内实时价 → 不蓝"""
        self.assertEqual(self.price_type_fn("场内实时价"), "")

    def test_price_type_color_unknown(self):
        """未知取价方式 → 不蓝"""
        self.assertEqual(self.price_type_fn("场内收盘价(T-2)"), "")


class TestNewsLlmMetaTemplate(unittest.TestCase):
    """验证 news_llm_meta 传入模板时的渲染结果。"""

    def setUp(self):
        from jinja2 import Environment

        self.env = Environment()

    def _render_news_section(
        self, news_data: list, news_llm_meta: dict | None = None, has_llm_analysis: bool = False
    ) -> str:
        """渲染新闻 section 的 Jinja2 模板片段。"""
        template_str = """{% if news_data %}
        <table>
            <thead>
                <tr>
                    <th>序号</th><th>新闻标题</th>
                    {% if has_llm_analysis %}<th>LLM 关联分析</th>{% endif %}
                </tr>
            </thead>
            <tbody>
                {% for item in news_data %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td>{{ item.title }}</td>
                    {% if has_llm_analysis %}
                    <td>{% if item.llm_analysis %}{{ item.llm_analysis }}{% else %}—{% endif %}</td>
                    {% endif %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="notes">
            {% set ns = namespace(llm_notes=[]) %}
            {% set _ = ns.llm_notes.append("共 " ~ (news_data | length) ~ " 条") %}
            {% if news_llm_meta and news_llm_meta.get("llm_enabled") %}
                {% if news_llm_meta.get("llm_cached") %}
                    {% set _ = ns.llm_notes.append("使用了LLM缓存") %}
                {% else %}
                    {% set _tu = news_llm_meta.get("token_usage", {}) %}
                    {% if _tu.get("total_tokens") %}
                        {% set _ = ns.llm_notes.append("Token消耗：" ~ (_tu.get("total_tokens", 0))) %}
                    {% endif %}
                {% endif %}
            {% else %}
                {% set _ = ns.llm_notes.append("未依赖于LLM服务") %}
            {% endif %}
            {% for note in ns.llm_notes %}
            <div>{{ note }}</div>
            {% endfor %}
        </div>
        {% endif %}"""
        template = self.env.from_string(template_str)
        return template.render(
            news_data=news_data, news_llm_meta=news_llm_meta or {}, has_llm_analysis=has_llm_analysis
        )

    def test_llm_analysis_column_rendered(self):
        """has_llm_analysis=True → 渲染 LLM 关联分析 列。"""
        html = self._render_news_section(
            [{"title": "新闻A", "llm_analysis": "[高] 利好"}],
            has_llm_analysis=True,
        )
        self.assertIn("LLM 关联分析", html)
        self.assertIn("[高] 利好", html)

    def test_llm_analysis_column_hidden(self):
        """has_llm_analysis=False → 不渲染 LLM 关联分析 列。"""
        html = self._render_news_section(
            [{"title": "新闻A"}],
            has_llm_analysis=False,
        )
        self.assertNotIn("LLM 关联分析", html)

    def test_llm_disabled_footnote(self):
        """LLM 未启用 → 显示'未依赖于LLM服务'。"""
        html = self._render_news_section(
            [{"title": "新闻A"}],
            news_llm_meta={"llm_enabled": False},
        )
        self.assertIn("未依赖于LLM服务", html)

    def test_llm_cache_hit_footnote(self):
        """LLM 缓存命中 → 显示'使用了LLM缓存'。"""
        html = self._render_news_section(
            [{"title": "新闻A", "llm_analysis": "[高] 利好"}],
            news_llm_meta={"llm_enabled": True, "llm_cached": True, "token_usage": {}},
            has_llm_analysis=True,
        )
        self.assertIn("使用了LLM缓存", html)
        self.assertNotIn("未依赖于LLM服务", html)
        self.assertNotIn("Token消耗", html)

    def test_llm_token_usage_footnote(self):
        """LLM 启用+非缓存 → 显示 Token 消耗。"""
        html = self._render_news_section(
            [{"title": "新闻A", "llm_analysis": "[高] 利好"}],
            news_llm_meta={
                "llm_enabled": True,
                "llm_cached": False,
                "token_usage": {"input_tokens": 2000, "output_tokens": 500, "total_tokens": 2500},
            },
            has_llm_analysis=True,
        )
        self.assertIn("Token消耗：2500", html)
        self.assertNotIn("使用了LLM缓存", html)
        self.assertNotIn("未依赖于LLM服务", html)


# ============================================================
#  候选基金比较子表 —「基金业绩分析」章模板区块
# ============================================================


class TestCandidateCompareTemplate(unittest.TestCase):
    """验证候选基金比较子表在真实模板中的渲染结果。

    行为断言（对应「基金业绩分析」章候选基金比较增强验收标准）：
      - 开关默认关（candidate_data 为空/不可用）→「基金业绩分析」章无比较子表
      - 开关开启且 available → 正确渲染 11 列比较表
      - 单候选获取失败 → 该行显示"数据获取失败"占位
      - 候选 >10 / 存在无效代码 → 渲染提示行
    """

    def setUp(self):
        from jinja2 import Environment

        self.env = Environment()
        tmpl_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "static",
            "tmpl",
            "report_template.html",
        )
        self.tmpl_path = os.path.normpath(tmpl_path)

    def _extract_candidate_block(self) -> str:
        """从真实模板中提取候选基金比较区块（按 if/endif 配平截取）。"""
        with open(self.tmpl_path, encoding="utf-8") as f:
            html = f.read()
        start_marker = "{% if candidate_data %}"
        start = html.find(start_marker)
        self.assertNotEqual(start, -1, "模板中未找到候选基金比较区块起点")
        depth = 0
        pos = start
        while True:
            nxt_if = html.find("{% if", pos)
            nxt_endif = html.find("{% endif %}", pos)
            self.assertNotEqual(nxt_endif, -1, "模板中候选基金比较区块未闭合")
            if nxt_if != -1 and nxt_if < nxt_endif:
                depth += 1
                pos = nxt_if + len("{% if")
            else:
                depth -= 1
                pos = nxt_endif + len("{% endif %}")
                if depth == 0:
                    return html[start:pos]

    def _render_candidate_block(self, candidate_data: dict | None) -> str:
        """渲染真实模板的候选比较区块。"""
        tpl = self.env.from_string(self._extract_candidate_block())
        return tpl.render(candidate_data=candidate_data or {})

    def test_switch_off_no_candidate_block(self):
        """开关默认关（candidate_data=None）→ 无比较子表、无提示。"""
        html = self._render_candidate_block(None)
        self.assertEqual(html.strip(), "", "candidate_data=None 不应渲染候选区块")

    def test_switch_on_no_valid_candidate_shows_notice(self):
        """开关开启但无有效候选（available=False）→ 渲染「未配置候选基金」提示。"""
        data = {"available": False, "reason": "no_valid_candidate", "invalid": [], "rows": []}
        html = self._render_candidate_block(data)
        self.assertIn("候选基金比较", html)
        self.assertIn("未配置候选基金", html)
        self.assertIn("comparison_candidates", html)

    def test_notice_lists_invalid_codes(self):
        """无有效候选且存在非法代码 → 提示中列出被忽略代码。"""
        data = {"available": False, "reason": "no_valid_candidate", "invalid": ["abc123"], "rows": []}
        html = self._render_candidate_block(data)
        self.assertIn("未配置候选基金", html)
        self.assertIn("abc123", html)

    def test_available_renders_table_headers(self):
        """开启且 available → 渲染 11 列比较表。"""
        candidate_data = {
            "available": True,
            "exceed_limit": False,
            "invalid": [],
            "rows": [self._sample_row()],
        }
        html = self._render_candidate_block(candidate_data)
        self.assertIn("候选基金比较", html)
        for header in (
            "候选基金",
            "代码",
            "评级",
            "近1月",
            "近3月",
            "近6月",
            "近1年",
            "同类排名",
            "最大回撤",
            "风格",
            "与持仓重合",
        ):
            self.assertIn(f"<th>{header}</th>", html)

    def test_available_renders_row_values(self):
        """候选行各维度数值正确渲染（收益/排名/回撤/风格/重合度）。"""
        candidate_data = {
            "available": True,
            "exceed_limit": False,
            "invalid": [],
            "rows": [self._sample_row()],
        }
        html = self._render_candidate_block(candidate_data)
        self.assertIn("候选基金A", html)
        self.assertIn("000001", html)
        self.assertIn("优秀", html)
        self.assertIn("1.23%", html)
        self.assertIn("159/358", html)
        self.assertIn("-18.50%", html)
        self.assertIn("大盘成长", html)
        self.assertIn("50.00%（现有基金X）", html)

    def test_failed_row_shows_placeholder(self):
        """单候选获取失败 → 显示'数据获取失败'占位行。"""
        row = self._sample_row()
        row["available"] = False
        row["reason"] = "rank_unavailable"
        candidate_data = {"available": True, "exceed_limit": False, "invalid": [], "rows": [row]}
        html = self._render_candidate_block(candidate_data)
        self.assertIn("数据获取失败", html)

    def test_exceed_limit_footnote_rendered(self):
        """候选 >10 只截断 → 渲染超限提示。"""
        candidate_data = {
            "available": True,
            "exceed_limit": True,
            "invalid": [],
            "rows": [self._sample_row()],
        }
        html = self._render_candidate_block(candidate_data)
        self.assertIn("候选基金超过 10 只", html)

    def test_invalid_codes_footnote_rendered(self):
        """存在无效候选代码 → 渲染忽略提示。"""
        candidate_data = {
            "available": True,
            "exceed_limit": False,
            "invalid": ["abc123", "123"],
            "rows": [self._sample_row()],
        }
        html = self._render_candidate_block(candidate_data)
        self.assertIn("无效候选代码（忽略）", html)
        self.assertIn("abc123、123", html)

    def test_candidate_block_present_in_template(self):
        """模板确实包含候选基金比较区块（结构性自检）。"""
        block = self._extract_candidate_block()
        self.assertIn("候选基金比较", block)
        self.assertIn("comparison_candidates", block)

    @staticmethod
    def _sample_row() -> dict:
        """构造一个 available 候选行样例。"""
        return {
            "code": "000001",
            "name": "候选基金A",
            "rating": "优秀",
            "syl_近1月": "1.23%",
            "syl_近1月_raw": 0.0123,
            "syl_近3月": "5.67%",
            "syl_近3月_raw": 0.0567,
            "syl_近6月": "11.01%",
            "syl_近6月_raw": 0.1101,
            "syl_近1年": "-2.01%",
            "syl_近1年_raw": -0.0201,
            "rank_text": "159/358",
            "max_drawdown": "-18.50%",
            "max_drawdown_raw": -0.185,
            "style": "大盘成长",
            "overlap_name": "现有基金X",
            "overlap_jaccard": "50.00%",
            "overlap_jaccard_raw": 0.5,
            "available": True,
            "reason": "",
        }


# ============================================================
#  Template rendering — 成本流水（fund_flow_data）三处渲染
# ============================================================


class TestFundFlowTemplate(unittest.TestCase):
    """验证成本流水数据在真实模板三处的渲染结果。

    行为断言（对应「成本流水」HTML 渲染补齐验收标准）：
      - 开关关闭（flow_display=None）→ 汇总无 XIRR 卡、市值无加权成本列、分类无分档/分红列
      - 开关开启且数据可用 → XIRR 用 pct、加权成本用 price、分档/分红用文本/金额正确渲染
      - 数据缺失时占位（加权成本 "--"、分档 "--"、分红 0.00）
    """

    def setUp(self):
        from jinja2 import Environment

        from src.python.report.html_jinja_env import (
            _jinja_money,
            _jinja_pct,
            _jinja_price,
            _jinja_profit_color,
        )

        self.env = Environment(autoescape=True)
        self.env.filters.update(
            {
                "money": _jinja_money,
                "pct": _jinja_pct,
                "price": _jinja_price,
                "profit_color": _jinja_profit_color,
            }
        )
        tmpl_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "static", "tmpl", "report_template.html")
        )
        with open(tmpl_path, encoding="utf-8") as f:
            self.html = f.read()

    def _extract_balanced_from(self, start: int) -> str:
        """按 if/endif 配平从 start 起截取一段（含起点标记本身）。"""
        depth = 0
        pos = start
        while True:
            nxt_if = self.html.find("{% if", pos)
            nxt_endif = self.html.find("{% endif %}", pos)
            self.assertNotEqual(nxt_endif, -1, "模板中该区块未闭合（if/endif 不配平）")
            if nxt_if != -1 and nxt_if < nxt_endif:
                depth += 1
                pos = nxt_if + len("{% if")
            else:
                depth -= 1
                pos = nxt_endif + len("{% endif %}")
                if depth == 0:
                    return self.html[start:pos]

    def _extract_balanced(self, start_marker: str) -> str:
        """按 if/endif 配平从 start_marker 起截取一段（含 marker 本身）。"""
        start = self.html.find(start_marker)
        self.assertNotEqual(start, -1, f"模板中未找到起点: {start_marker}")
        return self._extract_balanced_from(start)

    def _extract_flow_block(self, inner_marker: str) -> str:
        """定位含 inner_marker 的最近前驱 {% if flow_display %} 块并配平截取。"""
        inner = self.html.find(inner_marker)
        self.assertNotEqual(inner, -1, f"模板中未找到内容: {inner_marker}")
        if_start = self.html.rfind("{% if flow_display %}", 0, inner)
        self.assertNotEqual(if_start, -1, "未找到前驱 {% if flow_display %}")
        return self._extract_balanced_from(if_start)

    def _render(self, fragment: str, flow_display, **extra) -> str:
        return self.env.from_string(fragment).render(flow_display=flow_display, **extra)

    # ── 1. 盈亏汇总 XIRR 卡 ──
    def test_summary_xirr_card_hidden_when_disabled(self):
        """开关关闭（flow_display=None/无 xirr_rate）→ 盈亏汇总无 XIRR 卡。"""
        frag = self._extract_balanced("{% if flow_display and flow_display.xirr_rate is not none %}")
        for data in (None, {}, {"xirr_rate": None}):
            self.assertEqual(self._render(frag, data).strip(), "", f"flow_display={data!r} 不应渲染 XIRR 卡")

    def test_summary_xirr_card_rendered_when_available(self):
        """xirr_rate 可用 → 渲染「资金加权收益率 (XIRR)」卡，值经 pct 过滤器（×100）。"""
        frag = self._extract_balanced("{% if flow_display and flow_display.xirr_rate is not none %}")
        html = self._render(frag, {"xirr_rate": 0.1035})
        self.assertIn("资金加权收益率 (XIRR)", html)
        self.assertIn("10.35%", html)

    def test_summary_xirr_card_approximate_label(self):
        """快照近似（approximate=True）→ XIRR 卡标签加注「，近似」；真实模式不加注。"""
        frag = self._extract_balanced("{% if flow_display and flow_display.xirr_rate is not none %}")
        html_approx = self._render(frag, {"xirr_rate": 0.1, "approximate": True})
        self.assertIn("资金加权收益率 (XIRR，近似)", html_approx)
        html_real = self._render(frag, {"xirr_rate": 0.1})
        self.assertIn("资金加权收益率 (XIRR)", html_real)
        self.assertNotIn("，近似", html_real)

    # ── 2. 市值核算明细表 资金加权成本列 ──
    def test_market_value_wac_header_hidden_when_disabled(self):
        """开关关闭 → 市值核算表无「资金加权成本」表头列。"""
        frag = self._extract_balanced("{% if flow_display %}<th>资金加权成本</th>")
        self.assertEqual(self._render(frag, None).strip(), "")
        self.assertEqual(self._render(frag, {}).strip(), "")

    def test_market_value_wac_header_rendered_when_enabled(self):
        """开关开启 → 市值核算表追加「资金加权成本」表头列。"""
        frag = self._extract_balanced("{% if flow_display %}<th>资金加权成本</th>")
        html = self._render(frag, {"cost_map": {}})
        self.assertIn("<th>资金加权成本</th>", html)

    def test_market_value_wac_cell_value(self):
        """加权成本可用 → 明细行按 price 过滤器渲染；缺码时占位 "--"。"""
        frag = self._extract_flow_block("{% set wac = flow_display.cost_map.get(d.code) %}")
        html = self._render(frag, {"cost_map": {"600900": 52.5}}, d={"code": "600900"})
        self.assertIn("52.500", html)
        html_missing = self._render(frag, {"cost_map": {}}, d={"code": "600900"})
        self.assertIn("--", html_missing)

    # ── 3. 持仓分类表 成本分档/分红累计列 ──
    def test_category_flow_headers_hidden_when_disabled(self):
        """开关关闭 → 分类表无「成本分档」「分红累计」表头列。"""
        frag = self._extract_balanced("{% if flow_display %}<th>成本分档</th><th>分红累计</th>")
        self.assertEqual(self._render(frag, None).strip(), "")
        self.assertEqual(self._render(frag, {}).strip(), "")

    def test_category_flow_headers_rendered_when_enabled(self):
        """开关开启 → 分类表追加「成本分档」「分红累计」表头列。"""
        frag = self._extract_balanced("{% if flow_display %}<th>成本分档</th><th>分红累计</th>")
        html = self._render(frag, {"tier_map": {}})
        self.assertIn("<th>成本分档</th>", html)
        self.assertIn("<th>分红累计</th>", html)

    def test_category_flow_cell_values(self):
        """分档标签 + 分红累计金额正确渲染；缺码时占位 "--"/0.00。"""
        frag = self._extract_flow_block('flow_display.tier_map.get(item["code"]')
        flow = {"tier_map": {"600900": "低成本"}, "div_map": {"600900": 120.5}}
        html = self._render(frag, flow, item={"code": "600900"})
        self.assertIn("低成本", html)
        self.assertIn("120.50", html)
        html_missing = self._render(frag, {"tier_map": {}, "div_map": {}}, item={"code": "600900"})
        self.assertIn("--", html_missing)
        self.assertIn("0.00", html_missing)

    def test_fund_flow_blocks_present_in_template(self):
        """模板确实包含成本流水三处条件渲染（结构性自检）。"""
        self.assertIn("{% if flow_display and flow_display.xirr_rate is not none %}", self.html)
        self.assertIn("<th>资金加权成本</th>", self.html)
        self.assertIn("<th>成本分档</th>", self.html)
        self.assertIn("<th>分红累计</th>", self.html)

    # ── 4. 成本流水说明：快照近似（可选进阶增强）与无数据兜底 ──
    def test_flow_approximate_shows_optional_note(self):
        """快照近似（approximate=True）→ 渲染「可选进阶增强」说明（非压力文案）。"""
        frag = self._extract_balanced("{% if flow_display and flow_display.approximate %}")
        flow = {
            "approximate": True,
            "available": True,
            "xirr_rate": None,
            "cost_map": {},
            "tier_map": {},
            "div_map": {},
        }
        html = self._render(frag, flow)
        self.assertIn("成本流水为可选进阶增强", html)
        self.assertIn("已用持仓快照近似计算", html)
        self.assertIn("未配置建仓日期", html)

    def test_flow_approximate_with_rate_omits_start_date_hint(self):
        """快照近似且已配置建仓日期（xirr_rate 可用）→ 说明不含「未配置建仓日期」。"""
        frag = self._extract_balanced("{% if flow_display and flow_display.approximate %}")
        flow = {
            "approximate": True,
            "available": True,
            "xirr_rate": 0.1,
            "cost_map": {},
            "tier_map": {},
            "div_map": {},
        }
        html = self._render(frag, flow)
        self.assertIn("成本流水为可选进阶增强", html)
        self.assertNotIn("未配置建仓日期", html)

    def test_flow_unavailable_fallback_note(self):
        """真实流水模式无数据（available=False，无 approximate）→ 保留原空态说明。"""
        frag = self._extract_balanced("{% if flow_display and flow_display.approximate %}")
        flow = {"available": False, "xirr_rate": None, "cost_map": {}, "tier_map": {}, "div_map": {}}
        html = self._render(frag, flow)
        self.assertIn("成本流水子模块已开启", html)
        self.assertIn("未录入交易/分红流水", html)

    def test_flow_none_no_note(self):
        """开关关闭（flow_display=None）→ 不渲染任何成本流水说明。"""
        frag = self._extract_balanced("{% if flow_display and flow_display.approximate %}")
        self.assertEqual(self._render(frag, None).strip(), "")


class TestBuildFlowDisplay(unittest.TestCase):
    """验证 html_writer._build_flow_display 的展示映射组装。

    行为断言：
      - 开关关闭/无数据（None）→ 返回 None（模板不渲染成本流水列）
      - 完整契约 → cost_map 复用加权成本、tier_map 复用分档标签、div_map/div_total 正确
      - 契约键缺失 → 降级为空映射（cost_map/tier_map/div_map 空 dict，div_total 0.0）
    """

    def test_none_input_returns_none(self):
        """None（开关关闭）→ 返回 None。"""
        from src.python.report.html_writer import _build_flow_display

        self.assertIsNone(_build_flow_display(None))
        self.assertIsNone(_build_flow_display({}))

    def test_full_contract_maps_values(self):
        """完整契约 → 加权成本/分档标签/分红映射正确组装。"""
        from src.python.report.html_writer import _build_flow_display

        contract = {
            "available": True,
            "xirr": {"rate": 0.1035},
            "cost_tiers": {
                "per_code": {
                    "600900": {
                        "low": {"shares": 100.0, "cost": 5000.0},
                        "high": {"shares": 0.0, "cost": 0.0},
                        "unpriced": {"shares": 0.0, "cost": 0.0},
                    }
                }
            },
            "dividends": {"per_code": {"600900": 120.5}, "total": 120.5},
        }
        display = _build_flow_display(contract)
        self.assertIsNotNone(display)
        self.assertIs(display["available"], True)
        self.assertAlmostEqual(display["xirr_rate"], 0.1035)
        self.assertAlmostEqual(display["cost_map"]["600900"], 50.0)  # 5000/100
        self.assertEqual(display["tier_map"]["600900"], "低成本")
        self.assertAlmostEqual(display["div_map"]["600900"], 120.5)
        self.assertAlmostEqual(display["div_total"], 120.5)

    def test_partial_contract_degrades(self):
        """契约键缺失 → cost_map/tier_map/div_map 空 dict、div_total 0.0、xirr_rate None。"""
        from src.python.report.html_writer import _build_flow_display

        display = _build_flow_display({"available": False})
        self.assertIsNotNone(display)
        self.assertIs(display["available"], False)
        self.assertIsNone(display["xirr_rate"])
        self.assertEqual(display["cost_map"], {})
        self.assertEqual(display["tier_map"], {})
        self.assertEqual(display["div_map"], {})
        self.assertEqual(display["div_total"], 0.0)


# ============================================================
#  write_html_report — news_llm_meta 参数透传
# ============================================================


class TestWriteHtmlReportNewsLlmMeta(unittest.TestCase):
    """验证 write_html_report 将 news_llm_meta 传给模板。"""

    def setUp(self):
        self.holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]
        self._tmp = tempfile.mkdtemp(prefix="test_html_")
        self.detail = MagicMock()
        self.detail.market_value = 1000.0
        self.detail.cost = 500.0
        self.detail.profit = 500.0
        self.detail.today_profit = 50.0
        self.detail.name = "长江电力"
        self.detail.code = "600900"
        self.detail.price = 55.0
        self.detail.yesterday_close = 54.0
        self.detail.profit_rate = 1.0
        self.detail.source = "腾讯"
        self.detail.price_type = "实时"
        self.detail.premium = ""
        self.detail.shares = 100
        self.detail.cost_price = 50.0
        self.detail.nav_date = ""

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_news_llm_meta_passed_to_template(self):
        """外部传入 news_data+news_llm_meta → 模板收到正确参数。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_renderers._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {
                "sh000001": {"name": "上证指数", "price": 3120, "change": 10, "change_pct": 0.32}
            }
            mock_us_idx.return_value = {"gb_dji": {"name": "道琼斯", "price": 35000, "change": 100, "change_pct": 0.29}}
            mock_penetration.return_value = {}
            mock_cat.return_value = ([], True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            write_html_report(
                self.holdings,
                output_dir=self._tmp,
                include_news=True,
                news_data=[{"title": "新闻A", "matched_keywords": ["茅台"]}],
                news_llm_meta={"llm_enabled": True, "llm_cached": True, "token_usage": {}},
            )

        tmpl.render.assert_called_once()
        _, kwargs = tmpl.render.call_args
        self.assertIn("news_llm_meta", kwargs)
        self.assertTrue(kwargs["news_llm_meta"]["llm_enabled"])
        self.assertTrue(kwargs["news_llm_meta"]["llm_cached"])
        self.assertIn("has_llm_analysis", kwargs)

    def test_has_llm_analysis_false_without_analysis(self):
        """新闻无 llm_analysis 字段 → has_llm_analysis=False。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_renderers._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {}
            mock_us_idx.return_value = {}
            mock_penetration.return_value = {}
            mock_cat.return_value = ([], True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            write_html_report(
                self.holdings,
                output_dir=self._tmp,
                include_news=True,
                news_data=[{"title": "新闻A", "matched_keywords": ["茅台"]}],
            )

        _, kwargs = tmpl.render.call_args
        self.assertFalse(kwargs["has_llm_analysis"])

    def test_has_llm_analysis_true_with_analysis(self):
        """新闻有 llm_analysis → has_llm_analysis=True。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_renderers._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {}
            mock_us_idx.return_value = {}
            mock_penetration.return_value = {}
            mock_cat.return_value = ([], True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            write_html_report(
                self.holdings,
                output_dir=self._tmp,
                include_news=True,
                news_data=[{"title": "新闻A", "matched_keywords": ["茅台"], "llm_analysis": "[高] 利好"}],
            )

        _, kwargs = tmpl.render.call_args
        self.assertTrue(kwargs["has_llm_analysis"])


# ============================================================
#  write_html_report — Chart.js 数据集补齐（cat_data / penetration）
# ============================================================


class TestWriteHtmlReportChartMerge(unittest.TestCase):
    """write_html_report 内补齐 category_doughnut / industry_bar / penetration_bar。

    场景：调用侧 `_build_chart_datasets_for_report` 拿不到 cat_data / penetration，
    传入的 chart_datasets 缺这三张图 → 模板误显示"暂不可用"。merge 逻辑用
    write_html_report 内计算的权威数据重建并覆盖，保证图表与表格同源。
    """

    def setUp(self):
        self.holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]
        self._tmp = tempfile.mkdtemp(prefix="test_html_chart_")
        self.detail = MagicMock()
        self.detail.market_value = 1000.0
        self.detail.cost = 500.0
        self.detail.profit = 500.0
        self.detail.today_profit = 50.0
        self.detail.name = "长江电力"
        self.detail.code = "600900"
        self.detail.price = 55.0
        self.detail.yesterday_close = 54.0
        self.detail.profit_rate = 1.0
        self.detail.source = "腾讯"
        self.detail.price_type = "实时"
        self.detail.premium = ""
        self.detail.shares = 100
        self.detail.cost_price = 50.0
        self.detail.nav_date = ""

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _cat_data(self) -> list[dict]:
        """持仓分类表数据（_build_category_data 输出，含 property / sub_mv）。"""
        return [
            {"property": "股票", "sub_category": "A股", "sub_mv": 8000.0},
            {"property": "基金", "sub_category": "被动", "sub_mv": 4000.0},
        ]

    def _penetration(self) -> dict:
        """穿透数据：top10 有数据 + summary 含 1 只失败基金（部分失败场景）。"""
        return {
            "top10": [
                {"rank": 1, "name": "贵州茅台", "codes": ["600519"], "sector": "白酒", "mv": 5000.0},
                {"rank": 2, "name": "宁德时代", "codes": ["300750"], "sector": "新能源", "mv": 3000.0},
            ],
            "summary": {
                "unknown_mv": 7589.70,
                "failed_funds": ["华安黄金ETF"],
                "failed_fund_details": [{"name": "华安黄金ETF", "code": "518880"}],
            },
        }

    def _render_kwargs(self, mock_template):
        tmpl = MagicMock()
        tmpl.render.return_value = "<html>ok</html>"
        mock_template.return_value = tmpl
        return tmpl

    def _call_write_html_report(self, *, chart_datasets=None, enable_interactive_charts=False):
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_renderers._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {}
            mock_us_idx.return_value = {}
            mock_penetration.return_value = self._penetration()
            mock_cat.return_value = (self._cat_data(), True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = self._render_kwargs(mock_template)

            write_html_report(
                self.holdings,
                output_dir=self._tmp,
                include_news=False,  # 图表补齐与新闻无关，跳过新闻获取避免真实抓取
                chart_datasets=chart_datasets,
                enable_interactive_charts=enable_interactive_charts,
            )

        _, kwargs = tmpl.render.call_args
        return kwargs

    def test_chart_merge_fills_category_doughnut(self):
        """分类饼图由 cat_data 补齐，不显示 100% 其他/暂不可用。"""
        chart_datasets = {"portfolio_line": {}, "drawdown": {}, "radar": {}}
        kwargs = self._call_write_html_report(chart_datasets=chart_datasets, enable_interactive_charts=True)
        merged = kwargs["chart_datasets"]
        self.assertEqual(merged["category_doughnut"]["labels"], ["股票", "基金"])
        self.assertEqual(merged["category_doughnut"]["datasets"][0]["data"], [8000.0, 4000.0])
        # 原图（净值/回撤/雷达）不受影响
        self.assertIn("portfolio_line", merged)
        self.assertIn("radar", merged)

    def test_chart_merge_fills_penetration_charts(self):
        """行业分布 + 穿透 TOP10 图由 penetration 补齐，不误报"暂不可用"。"""
        chart_datasets = {"portfolio_line": {}, "drawdown": {}, "radar": {}}
        kwargs = self._call_write_html_report(chart_datasets=chart_datasets, enable_interactive_charts=True)
        merged = kwargs["chart_datasets"]
        self.assertEqual(merged["industry_bar"]["labels"], ["白酒", "新能源"])
        self.assertEqual(merged["penetration_bar"]["labels"], ["贵州茅台", "宁德时代"])

    def test_chart_merge_partial_penetration_still_renders(self):
        """12 只基金中 1 只无法获取穿透数据 → 图表仍渲染（非全量失败）。

        场景：top10 有数据，summary 有 failed_funds（部分失败），
        章节开头不得显示"行业数据暂不可用/穿透数据暂不可用"。
        """
        chart_datasets = {"portfolio_line": {}, "drawdown": {}, "radar": {}}
        kwargs = self._call_write_html_report(chart_datasets=chart_datasets, enable_interactive_charts=True)
        merged = kwargs["chart_datasets"]
        self.assertTrue(merged["industry_bar"]["labels"], "部分失败时行业图不应为空")
        self.assertTrue(merged["penetration_bar"]["labels"], "部分失败时穿透图不应为空")

    def test_chart_merge_skipped_when_flag_off(self):
        """Flag 关闭（enable_interactive_charts=False）→ 不触发补齐，模板不渲染图表。"""
        chart_datasets = {"portfolio_line": {}, "drawdown": {}, "radar": {}}
        kwargs = self._call_write_html_report(chart_datasets=chart_datasets, enable_interactive_charts=False)
        merged = kwargs["chart_datasets"]
        self.assertNotIn("category_doughnut", merged)
        self.assertNotIn("industry_bar", merged)

    def test_chart_merge_skipped_when_datasets_none(self):
        """chart_datasets=None → 补齐逻辑跳过（保持默认不渲染 Chart.js）。"""
        kwargs = self._call_write_html_report(chart_datasets=None, enable_interactive_charts=True)
        self.assertIsNone(kwargs["chart_datasets"])


# ============================================================
#  write_html_report — LLM 内部调用路径 (Modules 7/8)
# ============================================================


class TestWriteHtmlReportLlmType(unittest.TestCase):
    """验证 enable_llm=True 且 llm_content=None 时 generate_all_llm 收到 dict。"""

    def setUp(self):
        self.holdings = [
            Holding("证券账户", "长江电力", "600900", 100, 50.0),
        ]
        self.mock_detail = MagicMock()
        self.mock_detail.market_value = 1000.0
        self.mock_detail.cost = 500.0
        self.mock_detail.profit = 500.0
        self.mock_detail.today_profit = 50.0
        self.mock_detail.name = "长江电力"
        self.mock_detail.code = "600900"
        self.mock_detail.price = 55.0
        self.mock_detail.yesterday_close = 54.0
        self.mock_detail.profit_rate = 1.0
        self._tmp = tempfile.mkdtemp(prefix="test_html_")
        # 清理前序测试在 LLM_MODULE_FAILURE 中残留的状态
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        self._saved_llm_failure = dict(LLM_MODULE_FAILURE)
        LLM_MODULE_FAILURE.clear()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        # 恢复 LLM_MODULE_FAILURE 原始状态
        from src.python.llm.prompts import LLM_MODULE_FAILURE

        LLM_MODULE_FAILURE.clear()
        LLM_MODULE_FAILURE.update(self._saved_llm_failure)

    def _run_with_mocks(self, enable_llm=True):
        """用 ExitStack 统一管理 9 个补丁，调用 write_html_report 并返回 mock_llm。"""
        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_renderers._build_perf_data"))
            mock_llm = stack.enter_context(patch("src.python.llm.generate_all_llm"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.mock_detail]
            mock_a_idx.return_value = {
                "sh000001": {"name": "上证指数", "price": 3120, "change": 10, "change_pct": 0.32},
            }
            mock_us_idx.return_value = {
                "gb_dji": {"name": "道琼斯", "price": 35000, "change": 100, "change_pct": 0.29},
            }
            mock_penetration.return_value = {}
            mock_cat.return_value = ([], True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            mock_llm.return_value = ("<p>宏观</p>", "<p>复盘</p>", None, None, False, False, False, False)
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            from src.python.report.html_writer import write_html_report

            write_html_report(
                self.holdings,
                output_dir=self._tmp,
                enable_llm=enable_llm,
                llm_content=None,
                include_news=False,
                sector_flow=[],
            )

        return mock_llm

    def test_generate_all_llm_receives_dict_indices(self):
        """LLM 内容由 orchestrator 预生成后传入 html_writer，html_writer 自身不调用 generate_all_llm。"""
        mock_llm = self._run_with_mocks()

        # generate_all_llm 位于 orchestrator._fetch_llm_and_news，
        # html_writer 不直接调用
        mock_llm.assert_not_called()

    def test_llm_path_no_crash_on_dict_values(self):
        """LLM 路径不会因 dict/list 类型不匹配崩溃。"""
        try:
            self._run_with_mocks()
        except AttributeError as e:
            if ".values" in str(e) or ".get" in str(e):
                self.fail(f"类型不匹配导致崩溃: {e}")
            raise

    def test_llm_path_not_called_when_disabled(self):
        """enable_llm=False → generate_all_llm 不被调用。"""
        mock_llm = self._run_with_mocks(enable_llm=False)
        mock_llm.assert_not_called()

    def _run_with_mocks_and_template(self, enable_llm=True):
        """类似 _run_with_mocks，额外返回 template mock 用于断言模板数据。"""
        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_renderers._build_perf_data"))
            mock_llm = stack.enter_context(patch("src.python.llm.generate_all_llm"))
            mock_template_call = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.mock_detail]
            mock_a_idx.return_value = {
                "sh000001": {"name": "上证指数", "price": 3120, "change": 10, "change_pct": 0.32}
            }
            mock_us_idx.return_value = {"gb_dji": {"name": "道琼斯", "price": 35000, "change": 100, "change_pct": 0.29}}
            mock_penetration.return_value = {}
            mock_cat.return_value = ([], True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            mock_llm.return_value = ("<p>宏观</p>", "<p>复盘</p>", None, None, False, False, False, False)
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template_call.return_value = tmpl

            from src.python.report.html_writer import write_html_report

            write_html_report(
                self.holdings,
                output_dir=self._tmp,
                enable_llm=enable_llm,
                llm_content=None,
                include_news=False,
                sector_flow=[],
            )

            # 捕获模板渲染参数
            _, render_kwargs = tmpl.render.call_args

        return render_kwargs

    def test_llm_disabled_template_data(self):
        """enable_llm=False → 模板收到 llm_enabled=False，module 内容为 None。"""
        kwargs = self._run_with_mocks_and_template(enable_llm=False)
        self.assertFalse(kwargs["llm_enabled"])
        # 各模块内容为 None（未生成）
        self.assertIsNone(kwargs["global_macro"])
        self.assertIsNone(kwargs["expert_review"])
        self.assertIsNone(kwargs["health_check"])
        self.assertIsNone(kwargs["penetration_deep"])
        # llm_session_usage 为 None（未获取用量）
        self.assertIsNone(kwargs["llm_session_usage"])
        # llm_module_info 仍有默认的5条记录（状态为 unknown，含 news_correlation）
        self.assertEqual(len(kwargs["llm_module_info"]), 5)
        for mi in kwargs["llm_module_info"]:
            self.assertEqual(mi["status"], "unknown")
            self.assertEqual(mi["status_label"], "")


# ============================================================
#  _build_module_info_list — LLM 模块状态列表
# ============================================================


class TestBuildModuleInfoList(unittest.TestCase):
    """测试 build_llm_module_info 的状态判定逻辑。"""

    def test_cache_hit(self):
        """per_module 缓存命中 → status='cached', status_label='缓存'。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "global_macro": {
                "model": "deepseek-v4-flash",
                "cached": True,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_hit_tokens": 500,
                "cost": 0.0,
                "thinking": False,
                "endpoint": "",
            },
        }
        result = build_llm_module_info({}, per_module)
        gm = next(m for m in result if m["key"] == "global_macro")
        self.assertEqual(gm["status"], "cached")
        self.assertEqual(gm["status_label"], "缓存")
        self.assertEqual(gm["cache_hit_tokens"], 500)
        self.assertTrue(gm["cached"])
        self.assertEqual(gm["total_tokens"], 0)

    def test_success_call(self):
        """per_module 非缓存 → status='success', status_label='成功'。"""
        from src.python.report.llm_module_info import build_llm_module_info

        per_module = {
            "expert_review": {
                "model": "deepseek-v4-flash",
                "cached": False,
                "input_tokens": 500,
                "output_tokens": 300,
                "cache_hit_tokens": 0,
                "cost": 0.001,
                "thinking": True,
                "endpoint": "",
            },
        }
        result = build_llm_module_info({}, per_module)
        er = next(m for m in result if m["key"] == "expert_review")
        self.assertEqual(er["status"], "success")
        self.assertEqual(er["status_label"], "成功")
        self.assertEqual(er["input_tokens"], 500)
        self.assertEqual(er["output_tokens"], 300)
        self.assertEqual(er["total_tokens"], 800)
        self.assertTrue(er["thinking"])

    def test_disabled(self):
        """FAIL_REASON_DISABLED → status='disabled', status_label='已禁用'。"""
        from src.python.llm import FAIL_REASON_DISABLED
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {"global_macro": FAIL_REASON_DISABLED}
        result = build_llm_module_info(failure, {})
        gm = next(m for m in result if m["key"] == "global_macro")
        self.assertEqual(gm["status"], "disabled")
        self.assertEqual(gm["status_label"], "已禁用")
        self.assertEqual(gm["model"], "")
        self.assertEqual(gm["cost"], 0.0)

    def test_failed(self):
        """FAIL_REASON_API_ERROR → status='failed', status_label 含错误描述。"""
        from src.python.llm import FAIL_REASON_API_ERROR
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {"health_check": FAIL_REASON_API_ERROR}
        result = build_llm_module_info(failure, {})
        hc = next(m for m in result if m["key"] == "health_check")
        self.assertEqual(hc["status"], "failed")
        self.assertEqual(hc["status_label"], "LLM API 调用失败")

    def test_failed_all_reasons(self):
        """各失败原因 → 对应的中文描述。"""
        from src.python.llm import (
            FAIL_REASON_NOT_CONFIGURED,
            FAIL_REASON_API_ERROR,
            FAIL_REASON_NETWORK_ERROR,
            FAIL_REASON_TIMEOUT,
            FAIL_REASON_CIRCUIT_OPEN,
        )
        from src.python.report.llm_module_info import build_llm_module_info

        cases = [
            (FAIL_REASON_NOT_CONFIGURED, "LLM 未配置"),
            (FAIL_REASON_API_ERROR, "LLM API 调用失败"),
            (FAIL_REASON_NETWORK_ERROR, "LLM API 网络连接失败"),
            (FAIL_REASON_TIMEOUT, "LLM API 请求超时"),
            (FAIL_REASON_CIRCUIT_OPEN, "LLM API 暂时不可用（熔断冷却中）"),
        ]
        _MODULE_KEYS = ["global_macro", "expert_review", "health_check", "penetration_deep"]
        for idx, (reason, expected) in enumerate(cases):
            with self.subTest(reason=reason):
                mk = _MODULE_KEYS[idx % len(_MODULE_KEYS)]
                result = build_llm_module_info({mk: reason}, {})
                entry = next(m for m in result if m["key"] == mk)
                self.assertEqual(entry["status"], "failed")
                self.assertEqual(entry["status_label"], expected)

    def test_unknown(self):
        """无 per_module 且无 failure → status='unknown', status_label=''。"""
        from src.python.report.llm_module_info import build_llm_module_info

        result = build_llm_module_info({}, {})
        for mk in ["global_macro", "expert_review", "health_check", "penetration_deep"]:
            m = next(entry for entry in result if entry["key"] == mk)
            self.assertEqual(m["status"], "unknown", f"{mk} should be unknown")
            self.assertEqual(m["status_label"], "", f"{mk} status_label should be empty")

    def test_mixed_states(self):
        """混合状态：禁用、失败、缓存、成功同时存在。"""
        from src.python.llm import FAIL_REASON_DISABLED, FAIL_REASON_TIMEOUT
        from src.python.report.llm_module_info import build_llm_module_info

        failure = {
            "global_macro": FAIL_REASON_DISABLED,
            "health_check": FAIL_REASON_TIMEOUT,
        }
        per_module = {
            "expert_review": {
                "model": "claude-sonnet-4",
                "cached": True,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_hit_tokens": 1000,
                "cost": 0.0,
                "thinking": False,
                "endpoint": "",
            },
            "penetration_deep": {
                "model": "deepseek-v4-flash",
                "cached": False,
                "input_tokens": 300,
                "output_tokens": 200,
                "cache_hit_tokens": 0,
                "cost": 0.002,
                "thinking": True,
                "endpoint": "https://api.test.com",
            },
        }
        result = build_llm_module_info(failure, per_module)
        by_key = {m["key"]: m for m in result}

        self.assertEqual(by_key["global_macro"]["status"], "disabled")
        self.assertEqual(by_key["health_check"]["status"], "failed")
        self.assertEqual(by_key["expert_review"]["status"], "cached")
        self.assertEqual(by_key["penetration_deep"]["status"], "success")
        self.assertEqual(by_key["penetration_deep"]["endpoint"], "https://api.test.com")


# ============================================================
#  _render_llm_module_info — HTML 报告模块状态收集
# ============================================================


class TestRenderLlmModuleInfo(unittest.TestCase):
    """测试 _render_llm_module_info 的使能分支和数据聚合。"""

    def _call(self, llm_enabled_flag=False, session_usage=None, module_failure=None):
        """调用 _render_llm_module_info，返回结果四元组。"""
        from contextlib import ExitStack

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts.LLM_MODULE_FAILURE", module_failure or {}))
            if session_usage is not None:
                stack.enter_context(patch("src.python.llm.get_session_usage", return_value=session_usage))
                stack.enter_context(patch("src.python.llm.format_session_usage", return_value=session_usage))
            from src.python.report.html_renderers import _render_llm_module_info

            return _render_llm_module_info(llm_enabled_flag)

    def test_not_enabled_returns_unknown(self):
        """llm_enabled_flag=False → 所有模块状态为 unknown，无用量数据。"""
        llm_module_info, llm_endpoint, module_disabled, llm_session_usage = self._call(llm_enabled_flag=False)
        self.assertEqual(len(llm_module_info), 5)
        for mi in llm_module_info:
            self.assertEqual(mi["status"], "unknown")
        self.assertEqual(llm_endpoint, "")
        self.assertIsNone(llm_session_usage)
        self.assertFalse(any(module_disabled.values()))

    def test_enabled_with_cache_hit(self):
        """llm_enabled_flag=True + 全缓存 → 所有模块状态为 cached。"""
        session_usage = {
            "has_usage": True,
            "call_count": 0,
            "per_module": {
                "global_macro": {
                    "model": "ds",
                    "cached": True,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_hit_tokens": 500,
                    "cost": 0.0,
                    "thinking": False,
                    "endpoint": "",
                },
                "expert_review": {
                    "model": "ds",
                    "cached": True,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_hit_tokens": 300,
                    "cost": 0.0,
                    "thinking": True,
                    "endpoint": "",
                },
                "health_check": {
                    "model": "ds",
                    "cached": True,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_hit_tokens": 200,
                    "cost": 0.0,
                    "thinking": False,
                    "endpoint": "",
                },
                "penetration_deep": {
                    "model": "claude",
                    "cached": True,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_hit_tokens": 400,
                    "cost": 0.0,
                    "thinking": False,
                    "endpoint": "https://api.test.com",
                },
            },
        }
        llm_module_info, llm_endpoint, module_disabled, llm_session_usage = self._call(
            llm_enabled_flag=True, session_usage=session_usage
        )
        by_key = {m["key"]: m for m in llm_module_info}
        for mk in ["global_macro", "expert_review", "health_check", "penetration_deep"]:
            self.assertEqual(by_key[mk]["status"], "cached")
        self.assertEqual(llm_endpoint, "https://api.test.com")
        self.assertIsNotNone(llm_session_usage)
        self.assertTrue(by_key["expert_review"]["thinking"])

    def test_enabled_with_mixed_states(self):
        """llm_enabled_flag=True + 混合 + failure → 正确状态分发。"""
        from src.python.llm import FAIL_REASON_DISABLED, FAIL_REASON_API_ERROR

        session_usage = {
            "has_usage": True,
            "call_count": 2,
            "per_module": {
                "global_macro": {
                    "model": "ds",
                    "cached": False,
                    "input_tokens": 500,
                    "output_tokens": 300,
                    "cache_hit_tokens": 0,
                    "cost": 0.002,
                    "thinking": False,
                    "endpoint": "",
                },
                "expert_review": {
                    "model": "claude",
                    "cached": True,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_hit_tokens": 1000,
                    "cost": 0.0,
                    "thinking": False,
                    "endpoint": "",
                },
            },
        }
        module_failure = {
            "health_check": FAIL_REASON_DISABLED,
            "penetration_deep": FAIL_REASON_API_ERROR,
        }
        llm_module_info, llm_endpoint, module_disabled, _ = self._call(
            llm_enabled_flag=True, session_usage=session_usage, module_failure=module_failure
        )
        by_key = {m["key"]: m for m in llm_module_info}
        self.assertEqual(by_key["global_macro"]["status"], "success")
        self.assertEqual(by_key["expert_review"]["status"], "cached")
        self.assertEqual(by_key["health_check"]["status"], "disabled")
        self.assertEqual(by_key["penetration_deep"]["status"], "failed")
        # module_disabled 字典
        self.assertTrue(module_disabled["health_check"])
        self.assertFalse(module_disabled["global_macro"])
        self.assertFalse(module_disabled["expert_review"])
        self.assertFalse(module_disabled["penetration_deep"])

    def test_enabled_import_failure_returns_unknown(self):
        """llm_enabled_flag=True 但 format_session_usage 异常 → 返回 unknown + 无 session_usage。"""
        from contextlib import ExitStack

        with ExitStack() as stack:
            stack.enter_context(patch("src.python.llm.prompts.LLM_MODULE_FAILURE", {}))
            # 模拟 format_session_usage / get_session_usage 抛出 TypeError
            # （与 _render_llm_module_info 中 except (ImportError, TypeError, AttributeError) 匹配）
            stack.enter_context(patch("src.python.llm.get_session_usage", side_effect=TypeError("模拟错误")))
            stack.enter_context(patch("src.python.llm.format_session_usage", side_effect=TypeError("模拟错误")))
            from src.python.report.html_renderers import _render_llm_module_info

            llm_module_info, llm_endpoint, _, llm_session_usage = _render_llm_module_info(True)
        for mi in llm_module_info:
            self.assertEqual(mi["status"], "unknown")
        self.assertIsNone(llm_session_usage)


if __name__ == "__main__":
    unittest.main()


# ============================================================
#  报告序号可配置 → 模板渲染测试
# ============================================================


class TestSectionOrderTemplateRendering(unittest.TestCase):
    """验证 section_order / section_visible / section_numbers 在 Jinja2 模板中的渲染结果。

    测试目标：
      - section_visible 正确过滤导航链接
      - CSS order 属性值正确
      - 章节标题序号正确显示
      - 导航仅显示可见模块
    """

    def setUp(self):
        from jinja2 import Environment
        from src.python.report.html_jinja_env import _ENV

        self.env = Environment()
        self._module_env = _ENV
        # 注册 section_visible 全局函数（与 html_writer 中一致）
        self._visible_dict: dict[str, bool] = {}
        self.env.globals["section_visible"] = lambda key: self._visible_dict.get(key, False)

    def tearDown(self):
        pass

    def _set_visible_dict(self, visible: dict[str, bool]) -> None:
        """设置 section_visible_dict。"""
        self._visible_dict.clear()
        self._visible_dict.update(visible)

    def _render_nav(self, section_order: list[dict]) -> str:
        """渲染导航栏片段。"""
        tpl = self.env.from_string(
            "{% for sec in section_order %}"
            "{% if section_visible(sec['key']) %}"
            '<a href="#sec-{{ sec[\'key\'] }}">{{ sec["number"] }}、{{ sec["name"] }}</a>\n'
            "{% endif %}"
            "{% endfor %}"
        )
        return tpl.render(section_order=section_order)

    def test_nav_shows_only_visible_sections(self):
        """导航只显示 visible=True 的模块。"""
        section_order = [
            {"key": "summary", "name": "投资分析汇总", "number": 1},
            {"key": "fund_manager", "name": "基金经理变更监控", "number": 6},
            {"key": "llm_usage", "name": "LLM API 用量", "number": 16},
        ]
        self._set_visible_dict({"summary": True, "fund_manager": False, "llm_usage": True})
        html = self._render_nav(section_order)
        self.assertIn("#sec-summary", html)
        self.assertNotIn("#sec-fund_manager", html)
        self.assertIn("#sec-llm_usage", html)

    def test_nav_renders_numbers(self):
        """导航链接显示正确的序号。"""
        section_order = [
            {"key": "fund_performance", "name": "基金业绩分析", "number": 5},
            {"key": "category", "name": "持仓分类表", "number": 3},
        ]
        self._set_visible_dict({"fund_performance": True, "category": True})
        html = self._render_nav(section_order)
        self.assertIn("5、基金业绩分析", html)
        self.assertIn("3、持仓分类表", html)

    def test_nav_all_hidden_shows_nothing(self):
        """所有模块不可见 → 导航为空。"""
        section_order = [
            {"key": "summary", "name": "投资分析汇总", "number": 1},
            {"key": "fund_performance", "name": "基金业绩分析", "number": 5},
        ]
        self._set_visible_dict({"summary": False, "fund_performance": False})
        html = self._render_nav(section_order)
        self.assertEqual(html.strip(), "")

    def test_section_visible_default_true(self):
        """未在 visible_dict 中的 key → section_visible 返回 False（安全兜底）。"""
        section_order = [
            {"key": "unknown_module", "name": "未知模块", "number": 99},
        ]
        self._set_visible_dict({})  # 无任何可见性记录
        html = self._render_nav(section_order)
        self.assertEqual(html.strip(), "")

    # ── CSS order 渲染 ─────────────────────────────────

    def _render_section_order_attr(self, key: str, number: int) -> str:
        """渲染单个 section 的 order 属性。"""
        tpl = self.env.from_string('<div class="section" style="order: {{ section_numbers[\'%s\'] }};">' % key)
        return tpl.render(section_numbers={key: number})

    def test_order_attribute_correct(self):
        """CSS order 属性值等于配置序号。"""
        html = self._render_section_order_attr("summary", 1)
        self.assertIn("order: 1", html)
        html = self._render_section_order_attr("fund_manager", 6)
        self.assertIn("order: 6", html)

    def test_order_attribute_large_number(self):
        """大序号时 CSS order 正确渲染。"""
        html = self._render_section_order_attr("llm_usage", 99)
        self.assertIn("order: 99", html)

    # ── 章节标题序号渲染 ───────────────────────────────

    def _render_section_title(self, section_numbers: dict, key: str, name: str) -> str:
        """渲染章节标题。"""
        tpl = self.env.from_string("<h2 class=\"section-title\">{{ section_numbers['%s'] }}、%s</h2>" % (key, name))
        return tpl.render(section_numbers=section_numbers)

    def test_section_title_renders_custom_number(self):
        """章节标题使用 section_numbers 中的序号。"""
        html = self._render_section_title({"fund_manager": 1}, "fund_manager", "基金经理变更监控")
        self.assertIn("1、基金经理变更监控", html)

    def test_section_title_reordered_number(self):
        """章节标题展示重新排序后的序号。"""
        html = self._render_section_title({"summary": 5}, "summary", "投资分析汇总")
        self.assertIn("5、投资分析汇总", html)
        self.assertNotIn("1、投资分析汇总", html)

    # ── section_visible_dict 联动 ──────────────────────

    def test_visible_dict_true_renders_content(self):
        """visible=True → 内容块可见。"""
        tpl = self.env.from_string("{% if section_visible('summary') %}内容可见{% endif %}")
        self._set_visible_dict({"summary": True})
        html = tpl.render()
        self.assertIn("内容可见", html)

    def test_visible_dict_false_hides_content(self):
        """visible=False → 内容块隐藏。"""
        tpl = self.env.from_string("{% if section_visible('fund_manager') %}内容可见{% endif %}")
        self._set_visible_dict({"fund_manager": False})
        html = tpl.render()
        self.assertEqual(html.strip(), "")

    def test_visible_dict_missing_key_false(self):
        """字典中缺少的 key → section_visible 返回 False。"""
        tpl = self.env.from_string("{% if section_visible('unknown') %}内容可见{% endif %}")
        self._set_visible_dict({})
        html = tpl.render()
        self.assertEqual(html.strip(), "")


# ============================================================
#  组合演进可见性 — enable_portfolio_evolution board 层开关
# ============================================================


class TestComputeSectionVisibilityEvolution(unittest.TestCase):
    """_compute_section_visibility 对组合演进章节的 board 层门控。"""

    def _compute(self, enable_portfolio_evolution: bool, evolution_data: dict | None) -> dict:
        from src.python.core.registry import get_report_section_order
        from src.python.report.html_writer import _compute_section_visibility

        order = get_report_section_order({})
        _, svis, _ = _compute_section_visibility(
            order,
            None,
            None,
            None,
            None,
            include_news=True,
            llm_enabled_flag=False,
            enable_news=True,
            enable_fund_deep_analysis=True,
            enable_history=True,
            enable_portfolio_evolution=enable_portfolio_evolution,
            enable_llm=False,
            style_factor_data=None,
            position_relationship_data=None,
            evolution_data=evolution_data,
        )
        return svis

    def test_disabled_hides_section_even_with_data(self):
        """enable_portfolio_evolution=False → 即使 evolution_data 可用章节也隐藏。"""
        svis = self._compute(False, {"available": True, "periods": []})
        self.assertFalse(svis.get("portfolio_evolution"), "关闭组合演进开关时章节应隐藏")

    def test_enabled_with_data_shows_section(self):
        """enable_portfolio_evolution=True + evolution_data 可用 → 章节可见。"""
        svis = self._compute(True, {"available": True, "periods": []})
        self.assertTrue(svis.get("portfolio_evolution"), "开启组合演进且数据可用时章节应可见")

    def test_enabled_no_data_hides_section(self):
        """enable_portfolio_evolution=True + evolution_data=None → 章节隐藏（data 层）。"""
        svis = self._compute(True, None)
        self.assertFalse(svis.get("portfolio_evolution"), "无组合演进数据时章节应隐藏")

    def test_disabled_does_not_affect_other_sections(self):
        """关闭组合演进不影响其他 always 章节（如 summary / data_source_status）。"""
        svis = self._compute(False, None)
        self.assertTrue(svis.get("summary"), "summary 应始终可见")
        self.assertTrue(svis.get("data_source_status"), "数据源可用性矩阵应始终可见")


# ============================================================
#  app_version 页脚 — 版本号透传测试
# ============================================================


class TestAppVersionInTemplate(unittest.TestCase):
    """验证 app_version 从 html_writer 透传到模板。"""

    def setUp(self):
        self.holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]
        self._tmp = tempfile.mkdtemp(prefix="test_html_appver_")
        self.detail = MagicMock()
        self.detail.market_value = 1000.0
        self.detail.cost = 500.0
        self.detail.profit = 500.0
        self.detail.today_profit = 50.0
        self.detail.name = "长江电力"
        self.detail.code = "600900"
        self.detail.price = 55.0
        self.detail.yesterday_close = 54.0
        self.detail.profit_rate = 1.0
        self.detail.source = "腾讯"
        self.detail.price_type = "实时"
        self.detail.premium = ""
        self.detail.shares = 100
        self.detail.cost_price = 50.0
        self.detail.nav_date = ""

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_app_version_passed_to_template(self):
        """write_html_report → 模板渲染参数含 app_version（字符串非空）。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_renderers._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_renderers.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_renderers.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_renderers._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_renderers.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_renderers._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {
                "sh000001": {"name": "上证指数", "price": 3120, "change": 10, "change_pct": 0.32}
            }
            mock_us_idx.return_value = {"gb_dji": {"name": "道琼斯", "price": 35000, "change": 100, "change_pct": 0.29}}
            mock_penetration.return_value = {}
            mock_cat.return_value = ([], True)
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            write_html_report(self.holdings, output_dir=self._tmp, include_news=False)

        _, kwargs = tmpl.render.call_args
        self.assertIn("app_version", kwargs)
        self.assertIsInstance(kwargs["app_version"], str)
        self.assertIn("app_name", kwargs)
        self.assertIsInstance(kwargs["app_name"], str)
        self.assertGreater(len(kwargs["app_version"]), 0)
