"""测试 tiantian.py 数据解析辅助函数（纯函数，无网络请求）。"""

import json
import unittest

from src.python.providers.tiantian import (
    _calc_rating_from_entry,
    _extract_fund_meta,
    _extract_quarterly_meta,
    _find_holdings_table,
    _parse_holdings_rows,
    _parse_perf_evaluation,
    _parse_quarterly_holdings,
    _parse_rank_entry,
    _parse_risk_analysis,
    _parse_syl_returns,
    _pct_to_rating,
    _get_rating_thresholds,
    _RATING_THRESHOLDS,
    _KNOWN_RATING_TYPES,
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


class TestExtractFundMeta(unittest.TestCase):
    """_extract_fund_meta — 从 HTML 提取基金名称和报告日期。"""

    def test_extracts_name_and_date(self):
        html = "<title>易方达蓝筹精选混合(005827)</title>" + " " * 2000 + "2026-03-31"
        name, date = _extract_fund_meta(html)
        self.assertEqual(name, "易方达蓝筹精选混合")
        self.assertEqual(date, "2026-03-31")

    def test_no_title(self):
        html = "无标题页面"
        name, date = _extract_fund_meta(html)
        self.assertEqual(name, "")
        self.assertEqual(date, "")


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
    """_parse_syl_returns — 解析 JS 中的区间收益率变量（P0：长周期 + -- 防御）。"""

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
        """P0 新增：解析 2 年/3 年/5 年长周期收益率。"""
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
        """P0 修复：'--' 应跳过而非解析为 0。"""
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
        js = 'var syl_1y = 2.5;'
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
    """_calc_rating_from_entry — 5 级评级 + 类型差异化阈值（P2）。"""

    def test_excellent_top_10pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "5.0"}), "优秀")

    def test_good_10_to_30pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "20.0"}), "良好")

    def test_stable_30_to_50pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "40.0"}), "稳定")

    def test_poor_50_to_75pct(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "60.0"}), "偏差")

    def test_worst_bottom_25pct(self):
        """新增 5 级：较差（后 25%）。"""
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
        """百分位与排名矛盾时，以排名/总数为准（回归：159222 bug）。"""
        # 百分位=3.33(top 3.3%)→优秀，但排名=4823/4985(bottom 3.3%)→较差
        self.assertEqual(
            _calc_rating_from_entry({
                "percentile": "3.33", "rank": "4823", "total": "4985",
            }),
            "较差",
        )

    def test_rank_outranks_percentile_good_rank(self):
        """排名好于百分位时，以排名为准。"""
        self.assertEqual(
            _calc_rating_from_entry({
                "percentile": "60.0", "rank": "10", "total": "100",
            }),
            "优秀",
        )

    def test_no_conflict_both_good(self):
        """百分位和排名一致时，返回一致的评级。"""
        self.assertEqual(
            _calc_rating_from_entry({
                "percentile": "5.0", "rank": "10", "total": "100",
            }),
            "优秀",
        )

    def test_no_conflict_both_poor(self):
        """百分位和排名都差时，返回较差。"""
        self.assertEqual(
            _calc_rating_from_entry({
                "percentile": "60.0", "rank": "80", "total": "100",
            }),
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
        js = 'var Data_performanceEvaluation = {broken};'
        self.assertIsNone(_parse_perf_evaluation(js))


class TestParseRiskAnalysis(unittest.TestCase):
    """_parse_risk_analysis — 解析风险分析数据（P1 新增）。"""

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
        js = 'var Data_riskAnalysis = {broken};'
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
