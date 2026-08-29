"""真实行情/指数连通性验证（opt-in live 套件，不入门禁）。

运行：`python scripts/test-runner.py --mode live` 或 `pytest -m live`。

断言原则：只校验返回「结构」（字段存在、类型、非空），不校验具体数值，
容忍真实行情波动（休市、指数涨跌、数据源改字段等）。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live]

# 选稳定、流通性好的标的做连通性验证
_A_STOCK = "600900"      # 长江电力
_ETF = "510300"          # 沪深300ETF
_FUND = "110022"         # 易方达消费行业（场外基金）
_INDEX = "sh000001"      # 上证指数


@pytest.mark.live
def test_a_share_stock_quote():
    """A 股个股实时行情：返回结构完整。"""
    from src.python.fetcher.price import fetch_market_data

    data = fetch_market_data(_A_STOCK)
    assert data is not None, "A 股行情接口不可达（腾讯/新浪均失败）"
    assert isinstance(data, dict)
    assert data.get("name")
    assert data.get("code") == _A_STOCK
    assert isinstance(data.get("price"), (int, float))
    assert isinstance(data.get("yesterday_close"), (int, float))
    assert data.get("price_date")
    assert data.get("source_api") in ("tencent", "sina")


@pytest.mark.live
def test_etf_quote():
    """ETF 实时行情：返回结构完整。"""
    from src.python.fetcher.price import fetch_market_data

    data = fetch_market_data(_ETF)
    assert data is not None, "ETF 行情接口不可达"
    assert isinstance(data, dict)
    assert data.get("code") == _ETF
    assert isinstance(data.get("price"), (int, float))


@pytest.mark.live
def test_otc_fund_quote():
    """场外基金净值行情：返回结构完整。"""
    from src.python.fetcher.price import fetch_market_data

    data = fetch_market_data(_FUND)
    assert data is not None, "场外基金净值接口不可达"
    assert isinstance(data, dict)
    assert data.get("code") == _FUND
    assert isinstance(data.get("price"), (int, float))
    assert data.get("price_date")


@pytest.mark.live
def test_a_indices():
    """A 股主要指数：7 个全部可达。"""
    from src.python.fetcher.index import _A_INDICES, fetch_indices

    result = fetch_indices()
    assert isinstance(result, dict)
    # 至少上证/沪深300 两个核心指数可达
    for code in ("sh000001", "sh000300"):
        assert code in result, f"指数 {code} 缺失（腾讯/新浪均失败）"
        assert isinstance(result[code].get("price"), (int, float))
    # 返回键均来自 _A_INDICES 合法集合
    assert set(result.keys()).issubset(set(_A_INDICES.keys()))


@pytest.mark.live
def test_us_indices():
    """美股指数：三大指数结构校验。"""
    from src.python.fetcher.index import fetch_us_indices

    result = fetch_us_indices()
    assert isinstance(result, dict)
    assert len(result) > 0, "美股指数全部不可达（腾讯/新浪均失败）"
    for code, data in result.items():
        assert data.get("name")
        assert isinstance(data.get("price"), (int, float))
        assert isinstance(data.get("change_pct"), (int, float))
