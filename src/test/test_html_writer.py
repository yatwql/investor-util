"""HTML 报告生成模块单元测试。

测试目标：
  - write_html_report 中 a_indices/us_indices 以 dict 类型传入 generate_all_llm
  - 模板渲染使用独立 list 变量（不因 .values() 缺失崩溃）

运行：
  cd D:/codebase/zoo/investor-util
  python -m unittest src.test_html_writer -v
"""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from src.python.models import Holding


# ============================================================
#  Template rendering — LLM 新闻关联分析
# ============================================================


class TestJinjaFilters(unittest.TestCase):
    """Jinja2 自定义过滤器测试。"""

    def setUp(self):
        from src.python.report.html_writer import _jinja_price_type_color, _jinja_thousands
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
        """场内收盘价(T) → #0066CC"""
        self.assertEqual(self.price_type_fn("场内收盘价(T)"), "#0066CC")

    def test_price_type_color_nav_today(self):
        """官方净值(T) → #0066CC"""
        self.assertEqual(self.price_type_fn("官方净值(T)"), "#0066CC")

    def test_price_type_color_qdii_t_minus_1(self):
        """QDII 官方净值(T-1) → #0066CC"""
        self.assertEqual(self.price_type_fn("官方净值(T-1)", "标普500(QDII)"), "#0066CC")

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

    def _render_news_section(self, news_data: list, news_llm_meta: dict | None = None, has_llm_analysis: bool = False) -> str:
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
        return template.render(news_data=news_data, news_llm_meta=news_llm_meta or {}, has_llm_analysis=has_llm_analysis)

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
                "llm_enabled": True, "llm_cached": False,
                "token_usage": {"input_tokens": 2000, "output_tokens": 500, "total_tokens": 2500},
            },
            has_llm_analysis=True,
        )
        self.assertIn("Token消耗：2500", html)
        self.assertNotIn("使用了LLM缓存", html)
        self.assertNotIn("未依赖于LLM服务", html)


# ============================================================
#  write_html_report — news_llm_meta 参数透传
# ============================================================


class TestWriteHtmlReportNewsLlmMeta(unittest.TestCase):
    """验证 write_html_report 将 news_llm_meta 传给模板。"""

    def setUp(self):
        self.holdings = [Holding("证券账户", "长江电力", "600900", 100, 50.0)]
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

    def test_news_llm_meta_passed_to_template(self):
        """外部传入 news_data+news_llm_meta → 模板收到正确参数。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_writer._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_writer.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_writer._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_writer.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_writer._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {"sh000001": {"name": "上证指数", "price": 3120, "change": 10, "change_pct": 0.32}}
            mock_us_idx.return_value = {"gb_dji": {"name": "道琼斯", "price": 35000, "change": 100, "change_pct": 0.29}}
            mock_penetration.return_value = {}
            mock_cat.return_value = {}
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            write_html_report(
                self.holdings,
                output_dir="reports",
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
            mock_details = stack.enter_context(patch("src.python.report.html_writer._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_writer.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_writer._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_writer.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_writer._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {}
            mock_us_idx.return_value = {}
            mock_penetration.return_value = {}
            mock_cat.return_value = {}
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            write_html_report(
                self.holdings,
                output_dir="reports",
                include_news=True,
                news_data=[{"title": "新闻A", "matched_keywords": ["茅台"]}],
            )

        _, kwargs = tmpl.render.call_args
        self.assertFalse(kwargs["has_llm_analysis"])

    def test_has_llm_analysis_true_with_analysis(self):
        """新闻有 llm_analysis → has_llm_analysis=True。"""
        from src.python.report.html_writer import write_html_report

        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_writer._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_writer.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_writer._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_writer.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_writer._build_perf_data"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.detail]
            mock_a_idx.return_value = {}
            mock_us_idx.return_value = {}
            mock_penetration.return_value = {}
            mock_cat.return_value = {}
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            write_html_report(
                self.holdings,
                output_dir="reports",
                include_news=True,
                news_data=[{"title": "新闻A", "matched_keywords": ["茅台"], "llm_analysis": "[高] 利好"}],
            )

        _, kwargs = tmpl.render.call_args
        self.assertTrue(kwargs["has_llm_analysis"])


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

    def _run_with_mocks(self, enable_llm=True):
        """用 ExitStack 统一管理 9 个补丁，调用 write_html_report 并返回 mock_llm。"""
        with ExitStack() as stack:
            mock_details = stack.enter_context(patch("src.python.report.html_writer._generate_details"))
            mock_a_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_indices"))
            mock_us_idx = stack.enter_context(patch("src.python.report.html_writer.fetch_us_indices"))
            mock_penetration = stack.enter_context(patch("src.python.report.html_writer.compute_penetration_top10"))
            mock_cat = stack.enter_context(patch("src.python.report.html_writer._build_category_data"))
            mock_status = stack.enter_context(patch("src.python.report.html_writer.price_update_status"))
            mock_perf = stack.enter_context(patch("src.python.report.html_writer._build_perf_data"))
            mock_llm = stack.enter_context(patch("src.python.llm_client.generate_all_llm"))
            mock_template = stack.enter_context(patch("src.python.report.html_writer._ENV.get_template"))

            mock_details.return_value = [self.mock_detail]
            mock_a_idx.return_value = {
                "sh000001": {"name": "上证指数", "price": 3120, "change": 10, "change_pct": 0.32},
            }
            mock_us_idx.return_value = {
                "gb_dji": {"name": "道琼斯", "price": 35000, "change": 100, "change_pct": 0.29},
            }
            mock_penetration.return_value = {}
            mock_cat.return_value = {}
            mock_status.return_value = (0, 0, True)
            mock_perf.return_value = {}
            mock_llm.return_value = ("<p>宏观</p>", "<p>复盘</p>", False, False)
            tmpl = MagicMock()
            tmpl.render.return_value = "<html>ok</html>"
            mock_template.return_value = tmpl

            from src.python.report.html_writer import write_html_report

            write_html_report(
                self.holdings,
                output_dir="reports",
                enable_llm=enable_llm,
                llm_content=None,
                include_news=False,
                sector_flow=[],
            )

        return mock_llm

    def test_generate_all_llm_receives_dict_indices(self):
        """LLM 内部调用路径：generate_all_llm 收到 dict 类型指数数据。"""
        mock_llm = self._run_with_mocks()

        mock_llm.assert_called_once()
        args, kwargs = mock_llm.call_args
        a_indices, us_indices = args[0], args[1]

        self.assertIsInstance(a_indices, dict,
                              "a_indices 应为 dict 类型（非 list）")
        self.assertIsInstance(us_indices, dict,
                              "us_indices 应为 dict 类型（非 list）")

        # 验证 .values() 安全运行
        self.assertIsNotNone(list(a_indices.values()))
        self.assertIsNotNone(list(us_indices.values()))

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


if __name__ == "__main__":
    unittest.main()
