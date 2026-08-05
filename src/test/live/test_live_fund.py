"""真实基金数据源连通性验证（opt-in live 套件，不入门禁）。

运行：`python scripts/test_runner.py --mode live` 或 `pytest -m live`。

断言原则：只校验返回「结构」（字段存在、类型、非空），不校验具体数值。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live]

# 稳定存在的场外基金代码
_FUND = "110022"   # 易方达消费行业


@pytest.mark.live
def test_fund_nav_history():
    """场外基金历史净值：返回 [{date, nav, acc_nav}] 结构。"""
    from src.python.providers.eastmoney import fetch_fund_nav_history

    history = fetch_fund_nav_history(_FUND)
    assert isinstance(history, list)
    assert len(history) > 0, "基金历史净值接口不可达或返回空"
    for bar in history[:5]:
        assert isinstance(bar, dict)
        assert bar.get("date")
        assert isinstance(bar.get("nav"), (int, float))
        assert isinstance(bar.get("acc_nav"), (int, float))


@pytest.mark.live
def test_fund_rankings():
    """基金排名（天天基金）：返回结构校验。"""
    from src.python.fetcher.fund import fetch_fund_rankings

    rankings = fetch_fund_rankings(_FUND)
    assert rankings is not None, "天天基金排名接口不可达"
    assert isinstance(rankings, dict)
    assert rankings.get("name")


@pytest.mark.live
def test_fund_benchmark_api():
    """基金业绩基准 API 解析链路：返回基准名称或 '--'。"""
    from src.python.fetcher.fund import fetch_fund_benchmark

    benchmark = fetch_fund_benchmark(_FUND)
    assert isinstance(benchmark, str)
