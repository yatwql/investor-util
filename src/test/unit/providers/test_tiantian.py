"""测试 tiantian_holdings / tiantian_ranking 数据解析辅助函数。"""

import unittest

from src.python.providers.tiantian_holdings import (
    _extract_fund_name,
    _extract_quarterly_meta,
    _find_holdings_table,
    _parse_holdings_rows,
    _parse_quarterly_holdings,
    fetch_fund_holdings,
    parse_feeder_target_etf,
)
from src.python.providers.tiantian_ranking import (
    _calc_rating_from_entry,
    _fund_type_hint_from_name,
    _parse_perf_evaluation,
    _parse_rank_entry,
    _parse_risk_analysis,
    _parse_syl_returns,
    fetch_fund_rankings,
)
from unittest.mock import patch
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


def _build_pingzhong_js(name: str, rank: int = 14, total: int = 100) -> str:
    """构造最小 pingzhongdata JS：含基金名、同类排名（rank/total）与百分位。"""
    return (
        f'var fS_name = "{name}";\n'
        f'var Data_rateInSimilarType = [{{"y": {rank}, "sc": {total}}}];\n'
        f"var Data_rateInSimilarPersent = [[1, {rank}.0]];\n"
        'var syl_1y = "2.1";\n'
    )


class TestFindHoldingsTable(unittest.TestCase):
    """_find_holdings_table — 从 HTML 中找出持仓表格。"""

    def test_finds_table_with_keywords(self):
        html = """
        <table><tr><td>股票名称</td><td>占净值比例</td></tr>
        <tr><td>贵州茅台</td><td>9.50%</td></tr>
        <tr><td>五粮液</td><td>5.20%</td></tr></table>
        """
        result = _find_holdings_table(html)
        self.assertIsNotNone(result)
        self.assertIn("贵州茅台", result)

    def test_finds_table_by_data_rows(self):
        html = """
        <table><tr><td>A</td><td>1.0%</td></tr>
        <tr><td>B</td><td>2.0%</td></tr>
        <tr><td>C</td><td>3.0%</td></tr>
        <tr><td>D</td><td>4.0%</td></tr>
        <tr><td>E</td><td>5.0%</td></tr></table>
        """
        result = _find_holdings_table(html)
        self.assertIsNotNone(result)
        self.assertIn("1.0%", result)

    def test_no_matching_table(self):
        html = "<table><tr><td>不相关</td></tr></table>"
        result = _find_holdings_table(html)
        self.assertIsNone(result)

    def test_empty_html(self):
        self.assertIsNone(_find_holdings_table(""))


class TestParseHoldingsRows(unittest.TestCase):
    """_parse_holdings_rows — 解析持仓表格行。"""

    def test_parse_single_row(self):
        table = """
        <tr><td><a stockcode="stock_600519">贵州茅台</a></td><td>9.50%</td></tr>
        """
        result = _parse_holdings_rows(table)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "贵州茅台")
        self.assertEqual(result[0]["code"], "600519")
        self.assertAlmostEqual(result[0]["ratio"], 9.50)

    def test_parse_multiple_rows(self):
        table = """
        <tr><td><a stockcode="stock_600519">贵州茅台</a></td><td>9.50%</td></tr>
        <tr><td><a stockcode="stock_000858">五粮液</a></td><td>5.20%</td></tr>
        """
        result = _parse_holdings_rows(table)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["name"], "五粮液")

    def test_code_from_href_fallback(self):
        table = """
        <tr><td><a href="//quote.eastmoney.com/unify/r/0.300604">东方财富</a></td><td>3.0%</td></tr>
        """
        result = _parse_holdings_rows(table)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["code"], "300604")

    def test_skip_rows_without_name(self):
        table = """
        <tr><td></td><td>3.0%</td></tr>
        """
        result = _parse_holdings_rows(table)
        self.assertEqual(len(result), 0)

    def test_skip_zero_ratio(self):
        table = """
        <tr><td><a>测试</a></td><td>0.00%</td></tr>
        """
        result = _parse_holdings_rows(table)
        self.assertEqual(len(result), 0)

    def test_empty_table(self):
        self.assertEqual(_parse_holdings_rows(""), [])


class TestExtractFundName(unittest.TestCase):
    """_extract_fund_name — 只从 HTML 提取基金名称。

    报告期不在此处提取（页面无可靠来源），故本函数无第二返回值。按字节窗口
    盲扫日期实测 10 只基金 0 命中，且可能误抓导航控件里的当天日期——比空值
    更危险，不采用。
    """

    def test_extracts_name(self):
        html = "<title>易方达蓝筹精选混合(005827)</title>" + " " * 2000 + "2026-03-31"
        self.assertEqual(_extract_fund_name(html), "易方达蓝筹精选混合")

    def test_no_title(self):
        self.assertEqual(_extract_fund_name("无标题页面"), "")


class TestParseFeederTargetEtf(unittest.TestCase):
    """parse_feeder_target_etf — 解析联接基金的目标 ETF 锚点。

    两个方向的真实形态互为反向：联接基金页的锚点标签止于「ETF」、指向场内目标
    ETF；常规 ETF 页的锚点标签多「联接」二字、指向场外联接基金。
    """

    # 实测形态（016055 博时纳指联接）：标签止于「ETF」，指向场内 513390
    _ANCHOR = (
        "<div>博时纳斯达克100ETF发起式联接(QDII)A人民币"
        "<a style='float: right;' href=\"http://fund.eastmoney.com/513390.html\">查看相关ETF></a></div>"
    )
    # 实测形态（561910 电池ETF招商）：标签为「查看相关ETF联接」，指向场外 016019
    _REVERSE_ANCHOR = "<a style='float: right;' href=\"http://fund.eastmoney.com/016019.html\">查看相关ETF联接></a>"

    def test_extracts_target_code(self):
        self.assertEqual(parse_feeder_target_etf(self._ANCHOR, "016055"), "513390")

    def test_rejects_anchor_pointing_to_self(self):
        """锚点指向自身时不穿透（否则会自引用取数）。"""
        self.assertIsNone(parse_feeder_target_etf(self._ANCHOR, "513390"))

    def test_returns_none_without_anchor(self):
        self.assertIsNone(parse_feeder_target_etf("<div>无锚点页面</div>", "016055"))

    def test_rejects_non_exchange_target(self):
        """锚点指向非场内基金代码时不穿透（目标 ETF 必为场内品种）。"""
        html = '<a href="http://fund.eastmoney.com/005827.html">查看相关ETF></a>'
        self.assertIsNone(parse_feeder_target_etf(html, "016055"))

    def test_ignores_anchor_without_label(self):
        """无「查看相关ETF」标签的普通链接不算锚点。"""
        html = '<a href="http://fund.eastmoney.com/513390.html">查看更多</a>'
        self.assertIsNone(parse_feeder_target_etf(html, "016055"))

    def test_rejects_reverse_link_on_regular_etf_page(self):
        """常规 ETF 页的锚点是**反向**链接（回指其联接基金），不得当作目标 ETF。

        两类页面的锚点标签仅差「联接」二字，`查看相关ETF` 又是 `查看相关ETF联接`
        的前缀——不加否定前瞻会把 `561910` 的底层暴露错认成 `016019` 的持仓。
        """
        self.assertIsNone(parse_feeder_target_etf(self._REVERSE_ANCHOR, "561910"))

    def test_rejects_reverse_label_even_if_target_is_exchange_code(self):
        """标签规则独立成立：反向链接即便指向场内代码也不认。"""
        html = '<a href="http://fund.eastmoney.com/513390.html">查看相关ETF联接></a>'
        self.assertIsNone(parse_feeder_target_etf(html, "561910"))


class TestFetchFundHoldingsLadder(unittest.TestCase):
    """fetch_fund_holdings — 三跳取数阶梯的**次序**（次序即陈年数据隔离）。

    次序不变量：
      第 1 跳命中即返回，不再请求主页面；
      第 3 跳（无年份兜底，通常已陈旧）仅在「主页面无持仓且无目标 ETF 锚点」时到达。
    回归防线：若把兜底提回与年份域并列，联接基金会被最早可得报告遮蔽
    （其季报股票表按构造为空、抓到的却是陈年分区），本组用例会立刻失败。
    """

    _DATED = {"code": "110022", "name": "易方达消费行业", "date": "2026-06-30", "holdings": [{"name": "贵州茅台"}]}
    _LEGACY = {"code": "016055", "name": "博时纳指联接", "date": "2023-09-30", "holdings": [{"name": "旧持仓"}]}
    _FEEDER_HTML = (
        "<title>博时纳斯达克100ETF发起式联接(QDII)A人民币(016055)</title>"
        '<a href="http://fund.eastmoney.com/513390.html">查看相关ETF></a>'
    )
    # 常规 ETF 页的「相关」链接是**反向**的：指向其场外联接基金（实测 561910 → 016019）
    _NORMAL_ETF_HTML = (
        "<title>华夏上证50ETF(510050)</title>"
        '<a href="http://fund.eastmoney.com/016019.html">查看相关ETF联接></a>'
        "<table><tr><td>股票名称</td><td>占净值比例</td></tr>"
        '<tr><td><a stockcode="stock_600519">贵州茅台</a></td><td>9.50%</td></tr>'
        '<tr><td><a stockcode="stock_000858">五粮液</a></td><td>5.20%</td></tr>'
        '<tr><td><a stockcode="stock_601318">中国平安</a></td><td>4.10%</td></tr></table>'
    )

    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=_DATED)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_hop1_hit_skips_main_page(self, mock_html, _mock_dated):
        """第 1 跳（年份域季报）命中：不请求主页面。"""
        result = fetch_fund_holdings("110022")
        self.assertEqual(result["date"], "2026-06-30")
        mock_html.assert_not_called()

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=_LEGACY)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html", return_value=None)
    def test_hop3_skipped_when_main_page_request_fails(self, _m1, _m2, _m3):
        """主页面请求失败即返回 None，不落到第 3 跳。"""
        self.assertIsNone(fetch_fund_holdings("016055"))

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=_LEGACY)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_feeder_returns_target_and_skips_hop3(self, mock_html, _dated, mock_legacy):
        """联接基金：带回目标 ETF，且绝不落到第 3 跳的陈年报告。"""
        mock_html.return_value = self._FEEDER_HTML
        result = fetch_fund_holdings("016055")
        self.assertEqual(result["feeder_target_code"], "513390")
        self.assertEqual(result["holdings"], [])
        mock_legacy.assert_not_called()

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=_LEGACY)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_regular_etf_reverse_link_not_treated_as_feeder(self, mock_html, _dated, mock_legacy):
        """误判防线：常规 ETF 页也有「相关」链接，但它是反向的（回指联接基金）。

        两重独立防线各自都能拦下——名称不含「联接」故不进穿透分支；即便进入，
        ``(?!联)`` 前瞻也会拒绝「查看相关ETF联接」这一标签形态。
        """
        mock_html.return_value = self._NORMAL_ETF_HTML
        result = fetch_fund_holdings("510050")
        self.assertNotIn("feeder_target_code", result)
        self.assertEqual(len(result["holdings"]), 3)
        mock_legacy.assert_not_called()

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=_LEGACY)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_hop2_holdings_win_over_hop3(self, mock_html, _dated, mock_legacy):
        """主页面取到前十大即返回，不再落到无年份兜底。"""
        mock_html.return_value = self._NORMAL_ETF_HTML
        result = fetch_fund_holdings("510050")
        self.assertEqual(result["holdings"][0]["name"], "贵州茅台")
        mock_legacy.assert_not_called()

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=_LEGACY)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_hop3_reached_only_when_hop2_yields_nothing(self, mock_html, _dated, mock_legacy):
        """主页面无持仓且无锚点：退回无年份兜底（其陈旧性由报告层时效闸门裁决）。"""
        mock_html.return_value = "<title>某基金(016055)</title><div>无持仓表</div>"
        result = fetch_fund_holdings("016055")
        self.assertEqual(result["date"], "2023-09-30")
        mock_legacy.assert_called_once()

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_all_hops_empty_returns_named_empty_result(self, mock_html, _dated, _legacy):
        """三跳皆空：返回带名称的空持仓（供报告层判「持仓不可用」）。"""
        mock_html.return_value = "<title>某基金(016055)</title><div>无持仓表</div>"
        result = fetch_fund_holdings("016055")
        self.assertEqual(result["name"], "某基金")
        self.assertEqual(result["holdings"], [])


class TestParseQuarterlyHoldings(unittest.TestCase):
    """_parse_quarterly_holdings — 解析季报 API 返回的 HTML。"""

    def test_parse_holdings(self):
        html = """
        <table>
        <tr><td>序号</td><td>代码</td><td>名称</td><td>占比</td></tr>
        <tr><td>1</td><td><a>600519</a></td><td><a>贵州茅台</a></td><td>9.50%</td></tr>
        </table>
        """
        result = _parse_quarterly_holdings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "贵州茅台")
        self.assertEqual(result[0]["code"], "600519")

    def test_no_table(self):
        self.assertEqual(_parse_quarterly_holdings("无表格"), [])

    def test_skip_invalid_rows(self):
        html = """
        <table>
        <tr><td>1</td><td></td><td></td><td></td></tr>
        </table>
        """
        result = _parse_quarterly_holdings(html)
        self.assertEqual(len(result), 0)


class TestExtractQuarterlyMeta(unittest.TestCase):
    """_extract_quarterly_meta — 从季报 HTML 提取名称和日期。"""

    def test_extracts_name_from_title_attr(self):
        html = '<a title="易方达蓝筹精选混合" href="#">基金</a>截止至：2026-03-31'
        name, date = _extract_quarterly_meta(html)
        self.assertEqual(name, "易方达蓝筹精选混合")
        self.assertEqual(date, "2026-03-31")

    def test_extracts_name_from_link_text(self):
        html = '<a href="#">易方达蓝筹</a>截止至：2026-06-30'
        name, date = _extract_quarterly_meta(html)
        self.assertEqual(name, "易方达蓝筹")
        self.assertEqual(date, "2026-06-30")

    def test_no_meta_found(self):
        html = "无信息"
        name, date = _extract_quarterly_meta(html)
        self.assertEqual(name, "")
        self.assertEqual(date, "")


class TestParseSylReturns(unittest.TestCase):
    """_parse_syl_returns — 解析 JS 中的区间收益率变量（长周期 + -- 防御）。"""

    def test_parses_all_short_periods(self):
        js = """
        var syl_1y = "1.23";
        var syl_3y = "3.45";
        var syl_6y = "-0.56";
        var syl_1n = "12.34";
        """
        result = _parse_syl_returns(js)
        self.assertIn("近1月", result)
        self.assertAlmostEqual(result["近1月"]["return"], 1.23)
        self.assertAlmostEqual(result["近3月"]["return"], 3.45)
        self.assertAlmostEqual(result["近6月"]["return"], -0.56)
        self.assertAlmostEqual(result["近1年"]["return"], 12.34)

    def test_parses_long_periods(self):
        """解析 2 年/3 年/5 年长周期收益率。"""
        js = """
        var syl_2n = "8.50";
        var syl_3n = "18.20";
        var syl_5n = "25.00";
        """
        result = _parse_syl_returns(js)
        self.assertIn("近2年", result)
        self.assertAlmostEqual(result["近2年"]["return"], 8.50)
        self.assertIn("近3年", result)
        self.assertAlmostEqual(result["近3年"]["return"], 18.20)
        self.assertIn("近5年", result)
        self.assertAlmostEqual(result["近5年"]["return"], 25.00)

    def test_skips_dash_placeholder(self):
        """'--' 应跳过而非解析为 0。"""
        js = 'var syl_1y = "--";'
        result = _parse_syl_returns(js)
        self.assertNotIn("近1月", result)

    def test_mixed_dash_and_value(self):
        """短周期有值、长周期为 -- 时正确混合。"""
        js = """
        var syl_1y = "1.23";
        var syl_2n = "--";
        var syl_3n = "18.20";
        """
        result = _parse_syl_returns(js)
        self.assertIn("近1月", result)
        self.assertNotIn("近2年", result)  # -- 跳过
        self.assertIn("近3年", result)

    def test_missing_variables(self):
        js = "var silly = 1.0;"
        result = _parse_syl_returns(js)
        self.assertEqual(result, {})

    def test_handles_numeric_value(self):
        js = "var syl_1y = 2.5;"
        result = _parse_syl_returns(js)
        self.assertAlmostEqual(result["近1月"]["return"], 2.5)

    def test_empty_text(self):
        self.assertEqual(_parse_syl_returns(""), {})


class TestParseRankEntry(unittest.TestCase):
    """_parse_rank_entry — 解析同类排名 JS 变量。"""

    def test_parses_rank_and_percentile(self):
        js = """
        var Data_rateInSimilarType = [{"y": "45", "sc": "800"}];
        var Data_rateInSimilarPersent = [[1, 6.25], [2, 5.50]];
        """
        result = _parse_rank_entry(js)
        self.assertEqual(result["rank"], "45")
        self.assertEqual(result["total"], "800")
        self.assertEqual(result["percentile"], "5.5")

    def test_no_rank_data(self):
        js = "var nothing = 1;"
        result = _parse_rank_entry(js)
        self.assertEqual(result["rank"], "--")
        self.assertEqual(result["total"], "--")
        self.assertEqual(result["percentile"], "--")

    def test_empty_rank_array(self):
        js = "var Data_rateInSimilarType = [];"
        result = _parse_rank_entry(js)
        self.assertEqual(result["rank"], "--")
        self.assertEqual(result["total"], "--")


class TestCalcRatingFromEntry(unittest.TestCase):
    """_calc_rating_from_entry — 5 级评级 + 类型差异化阈值。"""

    def test_excellent_top_10pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "5.0"}), "优秀")

    def test_good_10_to_30pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "20.0"}), "良好")

    def test_stable_30_to_50pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "40.0"}), "稳定")

    def test_poor_50_to_75pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "60.0"}), "偏差")

    def test_worst_bottom_25pct(self):
        """5 级：较差（后 25%）。"""
        self.assertEqual(_calc_rating_from_entry({"percentile": "80.0"}), "较差")

    def test_boundary_10(self):
        """10% 为优秀/良好分界线（优秀）。"""
        self.assertEqual(_calc_rating_from_entry({"percentile": "10.0"}), "优秀")

    def test_boundary_10_exact_11(self):
        """10% 以上为良好。"""
        self.assertEqual(_calc_rating_from_entry({"percentile": "10.01"}), "良好")

    def test_boundary_30(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "30.0"}), "良好")

    def test_boundary_50(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "50.0"}), "稳定")

    def test_boundary_75(self):
        """75% 为稳定/偏差分界线。"""
        self.assertEqual(_calc_rating_from_entry({"percentile": "75.0"}), "偏差")

    def test_fallback_rank_ratio(self):
        self.assertEqual(_calc_rating_from_entry({"rank": "10", "total": "100"}), "优秀")
        self.assertEqual(_calc_rating_from_entry({"rank": "40", "total": "100"}), "稳定")
        self.assertEqual(_calc_rating_from_entry({"rank": "60", "total": "100"}), "偏差")
        self.assertEqual(_calc_rating_from_entry({"rank": "80", "total": "100"}), "较差")

    def test_empty_entry(self):
        self.assertEqual(_calc_rating_from_entry({}), "")

    def test_invalid_percentile(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "abc"}), "")

    def test_zero_division(self):
        self.assertEqual(_calc_rating_from_entry({"rank": "5", "total": "0"}), "")

    def test_rank_outranks_percentile_when_conflict(self):
        """百分位与排名矛盾时，以排名/总数为准。"""
        # 百分位=3.33(top 3.3%)→优秀，但排名=4823/4985(bottom 3.3%)→较差
        self.assertEqual(
            _calc_rating_from_entry(
                {
                    "percentile": "3.33",
                    "rank": "4823",
                    "total": "4985",
                }
            ),
            "较差",
        )

    def test_rank_outranks_percentile_good_rank(self):
        """排名好于百分位时，以排名为准。"""
        self.assertEqual(
            _calc_rating_from_entry(
                {
                    "percentile": "60.0",
                    "rank": "10",
                    "total": "100",
                }
            ),
            "优秀",
        )

    def test_no_conflict_both_good(self):
        """百分位和排名一致时，返回一致的评级。"""
        self.assertEqual(
            _calc_rating_from_entry(
                {
                    "percentile": "5.0",
                    "rank": "10",
                    "total": "100",
                }
            ),
            "优秀",
        )

    def test_no_conflict_both_poor(self):
        """百分位和排名都差时，返回较差。"""
        self.assertEqual(
            _calc_rating_from_entry(
                {
                    "percentile": "60.0",
                    "rank": "80",
                    "total": "100",
                }
            ),
            "较差",
        )

    def test_percentile_only_fallback(self):
        self.assertEqual(
            _calc_rating_from_entry({"percentile": "5.0"}),
            "优秀",
        )

    def test_rank_only_fallback(self):
        self.assertEqual(
            _calc_rating_from_entry({"rank": "60", "total": "100"}),
            "偏差",
        )

    # ── 类型差异化阈值 ──

    def test_bond_looser_threshold(self):
        """债券型：15%/35%/55%/80%，10% 仍为优秀。"""
        e = {"percentile": "10.0", "rank": "10", "total": "100"}
        self.assertEqual(_calc_rating_from_entry(e, "bond"), "优秀")

    def test_bond_14pct_is_excellent(self):
        """债券型 14% < 15% 优秀阈值。"""
        self.assertEqual(
            _calc_rating_from_entry({"rank": "14", "total": "100"}, "bond"),
            "优秀",
        )

    def test_bond_16pct_is_good(self):
        """债券型 16% > 15% 为良好。"""
        self.assertEqual(
            _calc_rating_from_entry({"rank": "16", "total": "100"}, "bond"),
            "良好",
        )

    def test_qdii_same_as_bond(self):
        """QDII 与债券型共用宽松阈值。"""
        self.assertEqual(
            _calc_rating_from_entry({"rank": "14", "total": "100"}, "qdii"),
            "优秀",
        )

    def test_index_stricter_threshold(self):
        """指数型：10%/25%/45%/70%，25% 为良好。"""
        self.assertEqual(
            _calc_rating_from_entry({"rank": "25", "total": "100"}, "index"),
            "良好",
        )

    def test_index_26pct_is_stable(self):
        """指数型 26% > 25% -> 稳定。"""
        self.assertEqual(
            _calc_rating_from_entry({"rank": "26", "total": "100"}, "index"),
            "稳定",
        )

    def test_default_threshold_unknown_type(self):
        """未知类型回退到 default。"""
        self.assertEqual(
            _calc_rating_from_entry({"rank": "10", "total": "100"}, "unknown_type"),
            "优秀",
        )


class TestFundTypeHintFromName(unittest.TestCase):
    """_fund_type_hint_from_name — 名称 → 评级阈值类型键。"""

    def test_qdii_explicit(self):
        """名称含 QDII → qdii。"""
        self.assertEqual(_fund_type_hint_from_name("南方原油(QDII)"), "qdii")

    def test_qdii_implicit_oversea(self):
        """隐式海外（纳斯达克）→ qdii。"""
        self.assertEqual(_fund_type_hint_from_name("广发纳斯达克100指数A"), "qdii")

    def test_bond(self):
        """债券型 → bond。"""
        self.assertEqual(_fund_type_hint_from_name("招商产业债券A"), "bond")

    def test_index_link(self):
        """指数联接 → index。"""
        self.assertEqual(_fund_type_hint_from_name("易方达上证50ETF联接A"), "index")

    def test_etf(self):
        """纯 ETF → index。"""
        self.assertEqual(_fund_type_hint_from_name("华夏上证50ETF"), "index")

    def test_otc_index_fund(self):
        """场外指数基金（含中证关键词）→ index。"""
        self.assertEqual(_fund_type_hint_from_name("天弘中证500指数A"), "index")

    def test_active_equity_default(self):
        """主动权益 → 默认（空串）。"""
        self.assertEqual(_fund_type_hint_from_name("华夏成长混合A"), "")

    def test_empty_name(self):
        """空名 → 默认（空串）。"""
        self.assertEqual(_fund_type_hint_from_name(""), "")

    def test_none_name(self):
        """None → 默认（空串）。"""
        self.assertEqual(_fund_type_hint_from_name(None), "")


class TestFetchFundRankingsTypeAwareRating(unittest.TestCase):
    """fetch_fund_rankings 接线：按名称推导类型差异化阈值计算评级。"""

    @patch("src.python.providers.tiantian_ranking._request_pingzhong_data")
    def test_bond_name_uses_looser_threshold(self, mock_req):
        """债券型 14%：默认阈值下为良好，债券宽松阈值下为优秀。"""
        mock_req.return_value = _build_pingzhong_js("招商产业债券A", rank=14)
        result = fetch_fund_rankings("110003")
        self.assertEqual(result["type"], "bond")
        self.assertEqual(result["rating"], "优秀")

    @patch("src.python.providers.tiantian_ranking._request_pingzhong_data")
    def test_index_name_uses_stricter_threshold(self, mock_req):
        """指数型 27%：默认阈值下为良好，指数严格阈值下为稳定。"""
        mock_req.return_value = _build_pingzhong_js("华泰柏瑞沪深300ETF联接A", rank=27)
        result = fetch_fund_rankings("000961")
        self.assertEqual(result["type"], "index")
        self.assertEqual(result["rating"], "稳定")

    @patch("src.python.providers.tiantian_ranking._request_pingzhong_data")
    def test_qdii_name_uses_looser_threshold(self, mock_req):
        """QDII 14%：宽松阈值下为优秀。"""
        mock_req.return_value = _build_pingzhong_js("广发纳斯达克100指数A", rank=14)
        result = fetch_fund_rankings("270042")
        self.assertEqual(result["type"], "qdii")
        self.assertEqual(result["rating"], "优秀")

    @patch("src.python.providers.tiantian_ranking._request_pingzhong_data")
    def test_active_equity_uses_default_threshold(self, mock_req):
        """主动权益 14%：默认阈值下为良好。"""
        mock_req.return_value = _build_pingzhong_js("华夏成长混合A", rank=14)
        result = fetch_fund_rankings("000001")
        self.assertEqual(result["type"], "")
        self.assertEqual(result["rating"], "良好")

    @patch("src.python.providers.tiantian_ranking._request_pingzhong_data")
    def test_name_and_type_in_result(self, mock_req):
        """返回结构包含 name 与 type 字段。"""
        mock_req.return_value = _build_pingzhong_js("南方原油(QDII)", rank=14)
        result = fetch_fund_rankings("501018")
        self.assertEqual(result["name"], "南方原油(QDII)")
        self.assertEqual(result["type"], "qdii")

    @patch("src.python.providers.tiantian_ranking._request_pingzhong_data")
    def test_no_rank_data_rating_empty(self, mock_req):
        """无排名/百分位数据 → 评级为空，但类型键仍按名称推导。"""
        js = 'var fS_name = "招商产业债券A";\nvar syl_1y = "2.1";\n'
        mock_req.return_value = js
        result = fetch_fund_rankings("110003")
        self.assertEqual(result["type"], "bond")
        self.assertEqual(result["rating"], "")


class TestParsePerfEvaluation(unittest.TestCase):
    """_parse_perf_evaluation — 解析业绩评价 JSON 变量。"""

    def test_parse_valid_json(self):
        js = 'var Data_performanceEvaluation = {"categories": ["超额收益"], "data": [85]};'
        result = _parse_perf_evaluation(js)
        self.assertIsNotNone(result)
        self.assertEqual(result["categories"], ["超额收益"])
        self.assertEqual(result["data"], [85])

    def test_no_match_returns_none(self):
        js = "var nothing = 1;"
        self.assertIsNone(_parse_perf_evaluation(js))

    def test_invalid_json_returns_none(self):
        js = "var Data_performanceEvaluation = {broken};"
        self.assertIsNone(_parse_perf_evaluation(js))


class TestParseRiskAnalysis(unittest.TestCase):
    """_parse_risk_analysis — 解析风险分析数据。"""

    def test_dict_with_categories_and_data(self):
        """JSON 对象格式：categories + data 双数组。"""
        js = 'var Data_riskAnalysis = {"categories": ["年化波动率","最大回撤","夏普比率"],"data": [15.2,-18.5,0.85]};'
        result = _parse_risk_analysis(js)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["年化波动率"], 15.2)
        self.assertAlmostEqual(result["最大回撤"], -18.5)
        self.assertAlmostEqual(result["夏普比率"], 0.85)

    def test_array_format(self):
        """数组格式：[["名称", 值], ...]。"""
        js = 'var Data_riskAnalysis = [["最大回撤", -25.3], ["夏普比率", 1.2], ["年化波动率", 18.5]];'
        result = _parse_risk_analysis(js)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["最大回撤"], -25.3)
        self.assertAlmostEqual(result["夏普比率"], 1.2)
        self.assertAlmostEqual(result["年化波动率"], 18.5)

    def test_missing_variable(self):
        """JS 中无 Data_riskAnalysis → None。"""
        self.assertIsNone(_parse_risk_analysis("var foo = 1;"))

    def test_invalid_json(self):
        """无效 JSON → None。"""
        js = "var Data_riskAnalysis = {broken};"
        self.assertIsNone(_parse_risk_analysis(js))

    def test_empty_result(self):
        """空数组 → None（无有效条目）。"""
        js = "var Data_riskAnalysis = [];"
        self.assertIsNone(_parse_risk_analysis(js))

    def test_partial_nulls(self):
        """categories 或 data 为 null → 按格式回退处理。"""
        js = 'var Data_riskAnalysis = {"categories": null, "data": null};'
        result = _parse_risk_analysis(js)
        self.assertIsNone(result)

    def test_mismatched_lengths(self):
        """categories 与 data 长度不一致 → None（格式1无效，尝试格式2失败）。"""
        js = 'var Data_riskAnalysis = {"categories": ["a","b"], "data": [1.0]};'
        result = _parse_risk_analysis(js)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
