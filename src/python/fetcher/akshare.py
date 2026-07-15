"""akshare 数据获取封装层 — 提供统一的数据获取接口。

职责：
  封装 ``providers/akshare_extras`` 的底层实现，为报告层提供
  整洁的数据获取接口。报告模块应从此模块而非直接导入
  ``providers/akshare_extras``，遵循 fetcher 层 → provider 层的
  架构分层约束。

当前封装函数：
  - get_dividend_data — 股票历史分红数据
  - get_profit_forecast — 机构盈利预测
  - get_profit_forecast_cache_key — 盈利预测缓存键
  - get_sector_fund_flow — 行业资金流向排名
"""

from __future__ import annotations

from typing import Any

from src.python.providers.akshare_extras import (
    get_dividend_data as _get_dividend_data,
    get_profit_forecast as _get_profit_forecast,
    get_profit_forecast_cache_key as _get_profit_forecast_cache_key,
    get_sector_fund_flow as _get_sector_fund_flow,
)

__all__ = [
    "get_dividend_data",
    "get_profit_forecast",
    "get_profit_forecast_cache_key",
    "get_sector_fund_flow",
]


def get_dividend_data(codes: list[str]) -> dict[str, dict]:
    """获取股票历史分红数据。

    委托给 ``providers.akshare_extras.get_dividend_data``。

    Args:
        codes: 股票代码列表

    Returns:
        {code: {"avg_dividend": float, "years": int, ...}}
    """
    return _get_dividend_data(codes)


def get_profit_forecast() -> dict[str, dict]:
    """获取全量机构盈利预测数据。

    委托给 ``providers.akshare_extras.get_profit_forecast``。

    Returns:
        {code: {"eps": float, "peg": float, ...}}
    """
    return _get_profit_forecast()


def get_profit_forecast_cache_key() -> str:
    """获取盈利预测数据的文件缓存键名（含指数指纹）。

    委托给 ``providers.akshare_extras.get_profit_forecast_cache_key``。

    Returns:
        缓存键字符串
    """
    return _get_profit_forecast_cache_key()


def get_sector_fund_flow() -> list[dict[str, Any]]:
    """获取行业资金流向排名（今日）。

    委托给 ``providers.akshare_extras.get_sector_fund_flow``。

    Returns:
        行业资金流向列表
    """
    return _get_sector_fund_flow()
