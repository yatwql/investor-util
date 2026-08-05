"""code_utils 指数代码判定函数单元测试。

覆盖：is_index_code / is_us_index_code / get_index_exchange_prefix /
      is_otc_fund_by_name / is_a_share_code（00 重叠区场外基金辅助判定与 A 股代码判定）。
"""

from __future__ import annotations

import pytest

from src.python.core.code_utils import (
    get_index_exchange_prefix,
    is_a_share_code,
    is_index_code,
    is_otc_fund_by_name,
    is_us_index_code,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


class TestIsIndexCode:
    """is_index_code 判定测试。"""

    def test_a_share_index_with_prefix_sh(self) -> None:
        """sh000300（沪深300）应识别为指数。"""
        assert is_index_code("sh000300") is True

    def test_a_share_index_with_prefix_sz(self) -> None:
        """sz399001（深证成指）应识别为指数。"""
        assert is_index_code("sz399001") is True

    def test_a_share_index_raw_no_prefix(self) -> None:
        """000300（无前缀）也应识别为指数。"""
        assert is_index_code("000300") is True

    def test_a_share_index_932_prefix(self) -> None:
        """932xxx（中证指数系列）应识别为指数。"""
        assert is_index_code("932100") is True

    def test_stock_code_not_index(self) -> None:
        """600900（A 股股票代码）不应识别为指数。"""
        assert is_index_code("600900") is False

    def test_etf_fund_code_not_index(self) -> None:
        """510050（上证50 ETF）不应识别为指数。"""
        assert is_index_code("510050") is False

    def test_hk_stock_code_not_index(self) -> None:
        """00700（港股）不应识别为指数。"""
        assert is_index_code("00700") is False

    def test_us_index_gb_inx(self) -> None:
        """gb_inx（标普500）应识别为指数。"""
        assert is_index_code("gb_inx") is True

    def test_us_index_gb_dji(self) -> None:
        """gb_dji（道琼斯）应识别为指数。"""
        assert is_index_code("gb_dji") is True

    def test_empty_code(self) -> None:
        """空字符串不应识别为指数。"""
        assert is_index_code("") is False


class TestIsUsIndexCode:
    """is_us_index_code 判定测试。"""

    def test_us_index_true(self) -> None:
        """gb_inx 应识别为美股指数。"""
        assert is_us_index_code("gb_inx") is True

    def test_a_share_index_false(self) -> None:
        """sh000300 不应识别为美股指数。"""
        assert is_us_index_code("sh000300") is False

    def test_empty_code(self) -> None:
        """空字符串不应识别为美股指数。"""
        assert is_us_index_code("") is False


class TestGetIndexExchangePrefix:
    """get_index_exchange_prefix 交易所前缀获取测试。"""

    def test_sh_prefix(self) -> None:
        """sh000300 返回 sh。"""
        assert get_index_exchange_prefix("sh000300") == "sh"

    def test_sz_prefix(self) -> None:
        """sz399001 返回 sz。"""
        assert get_index_exchange_prefix("sz399001") == "sz"

    def test_us_index_no_prefix(self) -> None:
        """gb_inx（美股指数）返回空字符串。"""
        assert get_index_exchange_prefix("gb_inx") == ""

    def test_raw_code_no_prefix(self) -> None:
        """000300（无前缀）返回空字符串。"""
        assert get_index_exchange_prefix("000300") == ""

    def test_empty_code(self) -> None:
        """空字符串返回空字符串。"""
        assert get_index_exchange_prefix("") == ""


class TestIsOtcFundByName:
    """is_otc_fund_by_name 00 重叠区场外基金辅助判定测试。

    覆盖 00 前缀 + 基金特征关键词（含债券/指数/股票等细分）→ 判定为场外基金；
    00 前缀 + 股票名（无基金特征词）或非 00 前缀 → 判定为非场外基金。
    """

    def test_bond_fund_with_bare_bond_keyword(self) -> None:
        """00 前缀 + 名称含"债券"（无细分词）→ 场外基金（如 000311 景顺长城景颐双利债券A）。"""
        assert is_otc_fund_by_name("景顺长城景颐双利债券A", "000311") is True

    def test_index_fund_with_index_keyword(self) -> None:
        """00 前缀 + 名称含"指数" → 场外基金（如 001552 天弘中证证券保险指数A）。"""
        assert is_otc_fund_by_name("天弘中证证券保险指数A", "001552") is True

    def test_stock_fund_with_stock_keyword(self) -> None:
        """00 前缀 + 名称含"股票" → 场外基金（如 004851 广发医疗保健股票A）。"""
        assert is_otc_fund_by_name("广发医疗保健股票A", "004851") is True

    def test_a_share_stock_00_prefix_not_fund(self) -> None:
        """00 前缀 + 深市股票名（无基金特征词）→ 非场外基金（如 000651 格力电器）。"""
        assert is_otc_fund_by_name("格力电器", "000651") is False

    def test_non_00_prefix_returns_false(self) -> None:
        """非 00 前缀（A 股/场内基金/港股）→ 非场外基金，与名称无关。"""
        assert is_otc_fund_by_name("招商中证白酒指数A", "161725") is False
        assert is_otc_fund_by_name("沪深300ETF", "510300") is False
        assert is_otc_fund_by_name("腾讯控股", "00700") is False

    def test_empty_name_or_code_returns_false(self) -> None:
        """名称或代码缺失 → 非场外基金（防御性，不抛异常）。"""
        assert is_otc_fund_by_name("", "000311") is False
        assert is_otc_fund_by_name("景顺长城景颐双利债券A", "") is False


class TestIsAShareCode:
    """is_a_share_code A 股代码判定测试。"""

    def test_normal_sh(self) -> None:
        """sh 前缀 A 股代码 → True。"""
        assert is_a_share_code("sh600000") is True

    def test_normal_sz(self) -> None:
        """sz 前缀 A 股代码 → True。"""
        assert is_a_share_code("sz000001") is True

    def test_normal_bj(self) -> None:
        """bj 前缀 A 股代码 → True。"""
        assert is_a_share_code("bj830001") is True

    def test_raw_six_digit(self) -> None:
        """纯 6 位数字 → True。"""
        assert is_a_share_code("600900") is True

    def test_us_stock(self) -> None:
        """美股字母代码 → False。"""
        assert is_a_share_code("AAPL") is False

    def test_us_stock_numeric(self) -> None:
        """美股数字代码（无前缀非 6 位）→ False。"""
        assert is_a_share_code("BRK.B") is False

    def test_hk_stock(self) -> None:
        """港股 5 位 → False。"""
        assert is_a_share_code("00700") is False

    def test_empty(self) -> None:
        """空字符串 → False。"""
        assert is_a_share_code("") is False

    def test_whitespace(self) -> None:
        """空格 → False。"""
        assert is_a_share_code("  ") is False

    def test_prefix_is_a_share(self) -> None:
        """带 sh/sz/bj 前缀的 6 位码 → True。"""
        for prefix in ("sh", "sz", "bj"):
            assert is_a_share_code(f"{prefix}600000") is True

    def test_prefix_not_a_share(self) -> None:
        """带 sh/sz/bj 前缀但非 6 位 → False。"""
        assert is_a_share_code("sh60000") is False
