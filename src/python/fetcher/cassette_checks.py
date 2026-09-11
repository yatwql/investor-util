"""cassette 解析校验绑定 — 录制名 → 当前解析器调用（语义名 datasource_cassette）。

`core/cassette.py` 的 ``verify_cassettes()`` 只负责「离线回放 + 判定结果是否
为空」，**不认识任何数据源**；「哪份录制该由哪个解析器吃」这张表放在 fetcher
层（本层本就 import providers），使 core 层不反向依赖数据源实现。

维护约定：**新增或重命名 cassette 时同步登记于此**，否则 ``cassettes --verify``
会把该条报为 ``skipped``（而非伪造通过）——这是刻意的：让「未登记」在维护命令
的输出里可见。

用途：
    - CLI ``cassettes --verify``：逐条离线回放并交给当前解析器；
    - 录制用例：录制后立即自检「刚录的内容当前解析器能解析」。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.python.providers import eastmoney, tencent
from src.python.providers import sina as sina_provider
from src.python.providers import tiantian_holdings

# 录制中使用的标的（与 src/test/data/cassettes/ 内的实际请求一致）
_STOCK_CODE = "600519"
_ETF_CODE = "510300"
_FUND_CODE = "110022"
_FEEDER_FUND_CODE = "016055"
"""ETF 联接基金标的——其季报股票表按构造为空，取数会走到主页面锚点那一步。

``fund_holdings`` 录制取它而非 ``_FUND_CODE``：普通基金的年份域季报通常直接命中
（第 1 跳），不会请求主页面，录下来与 ``fund_quarterly_holdings`` 重复；联接基金
才会走到「主页面 → 目标 ETF 锚点」，那正是本录制要盯的路径。
"""
_KLINE_DAYS = 5

CASSETTE_CHECKS: dict[str, Callable[[], Any]] = {
    "tencent_quote": lambda: tencent.fetch_price(_STOCK_CODE),
    "sina_quote": lambda: sina_provider.fetch_price(_STOCK_CODE),
    "tencent_kline": lambda: tencent.fetch_kline(_STOCK_CODE, days=_KLINE_DAYS),
    "fund_nav": lambda: eastmoney.fetch_nav(_FUND_CODE),
    "fund_holdings": lambda: tiantian_holdings.fetch_fund_holdings(_FEEDER_FUND_CODE),
    "fund_quarterly_holdings": lambda: tiantian_holdings.fetch_quarterly_holdings(_FUND_CODE),
}


def parser_for(name: str) -> Callable[[], Any] | None:
    """取某 cassette 的解析器调用；未登记返回 ``None``。"""
    return CASSETTE_CHECKS.get(name)


__all__ = ["CASSETTE_CHECKS", "parser_for"]
