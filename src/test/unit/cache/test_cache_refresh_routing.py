"""缓存刷新路由测试 —— 00 重叠区场外基金不按 A 股取行业/分红/扩展数据。

回归：`cache/operations.py` 的刷新函数曾只按代码前缀（`is_a_share_code`）过滤
持仓，把场外基金 `002943`（广发多因子）当作深市股票「宇晶股份」取行业分类 /
历史分红 / 扩展行情。现统一经 `is_a_share_stock(name, code)` 判定。

运行：
  pytest src/test/unit/cache/test_cache_refresh_routing.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.core.models import Holding

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

_HOLDINGS = [
    Holding(account="证券", name="长江电力", code="600900", shares=100, cost_price=10.0),
    Holding(account="支付宝-场外基金账户", name="广发多因子灵活配置混合", code="002943", shares=2000, cost_price=3.6),
]


class TestCacheRefreshRouting:
    """刷新缓存的目标过滤：场外基金代码不得进入个股数据链路。"""

    def test_industry_cache_skips_otc_fund(self):
        """002943 场外基金不进入行业分类取数，真实 A 股保留。"""
        from src.python.cache.operations import _refresh_industry_cache

        with patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}) as mock_batch:
            _refresh_industry_cache(_HOLDINGS)

        codes = mock_batch.call_args.args[0]
        assert "600900" in codes
        assert "002943" not in codes

    def test_dividend_cache_skips_otc_fund(self):
        """002943 场外基金不进入分红取数，真实 A 股保留。"""
        from src.python.cache.operations import _refresh_dividend_cache

        with patch("src.python.fetcher.akshare.get_dividend_data", return_value={}) as mock_div:
            _refresh_dividend_cache(_HOLDINGS)

        codes = mock_div.call_args.args[0]
        assert "600900" in codes
        assert "002943" not in codes

    def test_extended_cache_counts_only_a_share_stocks(self):
        """扩展数据预取的 A 股计数排除场外基金（002943 不计入）。"""
        from src.python.cache.operations import _refresh_extended_cache

        with patch("src.python.report.fund_style_classify._prefetch_extended_data"):
            count = _refresh_extended_cache(_HOLDINGS)

        assert count == 1
