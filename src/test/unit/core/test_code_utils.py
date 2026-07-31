"""code_utils 指数代码判定函数单元测试。

覆盖：is_index_code / is_us_index_code / get_index_exchange_prefix。
"""

from __future__ import annotations

import pytest

from src.python.core.code_utils import (
    get_index_exchange_prefix,
    is_index_code,
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
