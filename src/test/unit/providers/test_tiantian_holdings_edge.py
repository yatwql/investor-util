"""tiantian_holdings 取数阶梯与目标 ETF 锚点的边缘场景测试。

必须放在 *_edge.py 文件中（边缘测试文件隔离）。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from src.python.providers.tiantian_holdings import (
    _extract_fund_name,
    fetch_fund_holdings,
    parse_feeder_target_etf,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_providers, pytest.mark.edge]


class TestParseFeederTargetEtfEdge(unittest.TestCase):
    """parse_feeder_target_etf 异常/畸形页面场景。"""

    def test_single_quoted_https_href(self):
        """单引号 + https 的等价写法同样识别。"""
        html = "<a href='https://fund.eastmoney.com/513390.html'>查看相关ETF></a>"
        self.assertEqual(parse_feeder_target_etf(html, "016055"), "513390")

    def test_self_code_with_surrounding_whitespace(self):
        """self_code 带空白时仍能识别为「指向自身」而拒绝。"""
        html = '<a href="http://fund.eastmoney.com/513390.html">查看相关ETF></a>'
        self.assertIsNone(parse_feeder_target_etf(html, " 513390 "))

    def test_first_anchor_wins_when_multiple(self):
        """页面含多个同形锚点时取首个（页面首现即主标的，推荐位在后）。"""
        html = (
            '<a href="http://fund.eastmoney.com/513390.html">查看相关ETF></a>'
            '<a href="http://fund.eastmoney.com/159632.html">查看相关ETF></a>'
        )
        self.assertEqual(parse_feeder_target_etf(html, "016055"), "513390")

    def test_empty_html(self):
        self.assertIsNone(parse_feeder_target_etf("", "016055"))

    def test_anchor_with_self_closing_extra_attributes(self):
        """锚点携带额外属性（class/target）时仍匹配。"""
        html = '<a class="x" target="_blank" style=\'float: right;\' href="http://fund.eastmoney.com/513390.html">查看相关ETF></a>'
        self.assertEqual(parse_feeder_target_etf(html, "016055"), "513390")

    def test_code_not_six_digits_not_matched(self):
        """非 6 位数字的 href 不匹配（排除详情页等其它链接形态）。"""
        html = '<a href="http://fund.eastmoney.com/513390_xx.html">查看相关ETF></a>'
        self.assertIsNone(parse_feeder_target_etf(html, "016055"))


class TestExtractFundNameEdge(unittest.TestCase):
    """_extract_fund_name 畸形标题场景。"""

    def test_title_without_code_suffix_returns_empty(self):
        """标题不含括号代码 → 视为名称未知（返回空串）。

        主页面标题实测恒为「名称(代码)」，无括号即说明页面结构非预期；此时
        返回空串让名称判定退化（不识别联接、不进穿透），较之截取整段标题更
        安全——错误名称会被 :func:`is_index_link_by_name` 当真。
        """
        self.assertEqual(_extract_fund_name("<title>某基金</title>"), "")

    def test_title_with_fullwidth_paren(self):
        """全角括号同样作为名称边界。"""
        self.assertEqual(_extract_fund_name("<title>某基金（016055）</title>"), "某基金")

    def test_empty_title(self):
        self.assertEqual(_extract_fund_name("<title></title>"), "")

    def test_no_title_tag(self):
        self.assertEqual(_extract_fund_name("<div>无标题</div>"), "")

    def test_never_returns_report_date(self):
        """页面里的日期不会被当作报告期带回。

        回归防线：按字节窗口盲扫日期实测 10 只基金 0 命中，且可能命中导航/日历
        控件里的「当天」——比空值更危险（报告期缺失不判陈旧，会静默放行）。
        本函数只返回名称。
        """
        html = "<title>某基金(016055)</title>" + "<span>2026-09-11</span>" * 50
        self.assertEqual(_extract_fund_name(html), "某基金")


class TestFetchFundHoldingsLadderEdge(unittest.TestCase):
    """fetch_fund_holdings 阶梯异常场景。"""

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_feeder_without_anchor_falls_through_to_hop3(self, mock_html, _dated, mock_legacy):
        """联接基金页面缺锚点：不误判为目标 ETF，走完既有兜底链路。

        锚点缺失（页面改版/接口变更）时不应抛错或凭空猜测标的，须退回
        既有路径由报告层判「持仓不可用」。
        """
        mock_html.return_value = "<title>某ETF联接A(016055)</title><div>无锚点</div>"
        result = fetch_fund_holdings("016055")
        self.assertNotIn("feeder_target_code", result)
        mock_legacy.assert_called_once()

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch("src.python.providers.tiantian_holdings._request_fund_html")
    def test_feeder_anchor_pointing_to_self_falls_through(self, mock_html, _dated, mock_legacy):
        """锚点指向自身：不穿透（否则会自引用取数），退回既有兜底。"""
        mock_html.return_value = (
            '<title>某联接A(016055)</title><a href="http://fund.eastmoney.com/016055.html">查看相关ETF></a>'
        )
        result = fetch_fund_holdings("016055")
        self.assertNotIn("feeder_target_code", result)
        mock_legacy.assert_called_once()

    @patch("src.python.providers.tiantian_holdings._request_fund_html", return_value="")
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    def test_empty_html_page_falls_through_to_hop3(self, _dated, _mock_html):
        """空 HTML（非 None，即请求成功但内容为空）不当作页面失败。"""
        with patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly", return_value=None) as mock_legacy:
            result = fetch_fund_holdings("016055")
        mock_legacy.assert_called_once()
        self.assertEqual(result["holdings"], [])

    @patch("src.python.providers.tiantian_holdings._fetch_legacy_quarterly")
    @patch("src.python.providers.tiantian_holdings._fetch_dated_quarterly", return_value=None)
    @patch(
        "src.python.providers.tiantian_holdings._request_fund_html",
        return_value="<title>博时纳指100ETF发起式联接(QDII)A人民币(016055)</title>"
        '<a href="http://fund.eastmoney.com/513390.html">查看相关ETF></a>',
    )
    def test_feeder_hop3_not_called_even_when_available(self, _html, _dated, mock_legacy):
        """联接基金即使第 3 跳可得也必须不走——那是陈年分区，会遮蔽真实底层暴露。"""
        result = fetch_fund_holdings("016055")
        self.assertEqual(result["feeder_target_code"], "513390")
        mock_legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
