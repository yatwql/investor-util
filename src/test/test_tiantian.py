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
    _parse_syl_returns,
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
    """_parse_syl_returns — 解析 JS 中的区间收益率变量。"""

    def test_parses_all_periods(self):
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
    """_calc_rating_from_entry — 根据排名百分位计算评级。"""

    def test_excellent(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "10.0"}), "优秀")

    def test_good(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "25.0"}), "良好")

    def test_stable(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "40.0"}), "稳定")

    def test_poor(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "60.0"}), "偏差")

    def test_boundary_20(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "20.0"}), "优秀")

    def test_boundary_30(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "30.0"}), "良好")

    def test_boundary_50(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "50.0"}), "稳定")

    def test_fallback_rank_ratio(self):
        self.assertEqual(_calc_rating_from_entry({"rank": "10", "total": "100"}), "优秀")
        self.assertEqual(_calc_rating_from_entry({"rank": "40", "total": "100"}), "稳定")
        self.assertEqual(_calc_rating_from_entry({"rank": "60", "total": "100"}), "偏差")
        self.assertEqual(_calc_rating_from_entry({"rank": "80", "total": "100"}), "偏差")

    def test_empty_entry(self):
        self.assertEqual(_calc_rating_from_entry({}), "")

    def test_invalid_percentile(self):
        self.assertEqual(_calc_rating_from_entry({"percentile": "abc"}), "")

    def test_zero_division(self):
        self.assertEqual(_calc_rating_from_entry({"rank": "5", "total": "0"}), "")

    def test_rank_outranks_percentile_when_conflict(self):
        """百分位与排名矛盾时，以排名/总数为准（回归：159222 bug）。"""
        # 百分位=3.33(top 3.3%)→优秀，但排名=4823/4985(bottom 3.3%)→偏差
        self.assertEqual(
            _calc_rating_from_entry({
                "percentile": "3.33", "rank": "4823", "total": "4985",
            }),
            "偏差",
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
                "percentile": "10.0", "rank": "10", "total": "100",
            }),
            "优秀",
        )

    def test_no_conflict_both_poor(self):
        """百分位和排名都差时，返回偏差。"""
        self.assertEqual(
            _calc_rating_from_entry({
                "percentile": "60.0", "rank": "80", "total": "100",
            }),
            "偏差",
        )

    def test_percentile_only_fallback(self):
        """仅有百分位时，以百分位为准。"""
        self.assertEqual(
            _calc_rating_from_entry({"percentile": "10.0"}),
            "优秀",
        )

    def test_rank_only_fallback(self):
        """仅有排名时，以排名为准。"""
        self.assertEqual(
            _calc_rating_from_entry({"rank": "60", "total": "100"}),
            "偏差",
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


if __name__ == "__main__":
    unittest.main()
