"""新浪财经 API — 历史 K 线数据。

使用 sina 模块中的 make_http_client 和 is_index_code（lazy import），
确保现有测试的 patch("src.python.providers.sina.make_http_client") 和
patch("src.python.providers.sina.is_index_code") 继续生效。

Endpoint: money.finance.sina.com.cn/getKLineData
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.python.core.code_utils import (
    get_exchange_prefix,
    is_a_share_code,
    is_exchange_fund_code,
)

logger = logging.getLogger("invest")

_KLINE_TIMEOUT = 30.0  # K 线超时（需等待更多数据）


def _add_prefix(code: str) -> str:
    """根据代码前缀添加交易所标识。"""
    code = code.strip()
    if len(code) != 6:
        return code
    return get_exchange_prefix(code) + code


def fetch_kline(code: str, days: int = 30, start_from: str | None = None) -> list[dict]:
    """获取股票/ETF 历史 K 线数据（纯获取，Tencent 备用链路）。

    Endpoint: money.finance.sina.com.cn/getKLineData
    Sina K 线 API 返回 JSON 格式。

    ✅ 使用 make_http_client()。
    Provider 函数保持纯数据获取，不碰缓存层。

    Args:
        code: 6 位证券代码
        days: 获取天数（默认 30，最大 365）
        start_from: 起始日期（该参数由 chain 层使用，provider 侧按 days 获取）

    Returns:
        list[dict]: [{date, open, close, high, low, volume}, ...]
        按日期升序排列。API 失败返回空列表。
    """
    if not is_a_share_code(code) and not is_exchange_fund_code(code):
        logger.debug("Sina K 线跳过不支持的类型: %s", code)
        return []

    days = min(max(days, 5), 365)
    full_code = _add_prefix(code)
    url = "https://money.finance.sina.com.cn/getKLineData"

    params: dict[str, str | int] = {
        "symbol": full_code,
        "datalen": days,
        "scale": 240,
        "ma": "no",
    }

    logger.debug("Sina K 线请求: %s, days=%d", full_code, days)

    # lazy import: 通过 sina 模块引用 make_http_client, 使现有测试 patch 生效
    from src.python.providers import sina as _sina_mod  # noqa: E402

    try:
        with _sina_mod.make_http_client(timeout=_KLINE_TIMEOUT) as client:
            resp = client.get(url, params=params, headers={"Referer": "https://finance.sina.com.cn"})
            resp.encoding = "utf-8"
            data = resp.json()
    except (httpx.TimeoutException, httpx.RequestError, ValueError) as e:
        logger.warning("Sina K 线获取失败 %s: %s", full_code, e)
        return []

    return _parse_kline_json(data)


def fetch_index_kline(code: str, days: int = 30, start_from: str | None = None) -> list[dict]:
    """获取指数历史 K 线数据（备用链路）。

    与 fetch_kline() 的区别：
      - 入口通过 code_utils.is_index_code() 校验（代码类型判定）
      - 不检查 is_a_share_code/is_exchange_fund_code
      - 不调用 _add_prefix（指数代码直接透传）
      - 复用 _parse_kline_json() 解析逻辑
      - is_index_code 通过 sina 模块引用，使现有测试 patch 生效

    Args:
        code: 指数代码，如 "sh000300" / "gb_inx"
        days: 获取天数（默认 30，最大 2000。与 Tencent 对齐钳位到 2000，
              避免超限响应引发解析问题）
        start_from: 起始日期（由 chain 层使用，provider 侧按 days 获取）

    Returns:
        list[dict]: [{date, open, close, high, low, volume}, ...]
        API 失败返回空列表。

    Note:
        当前环境 `getKLineData` 端点对所有代码返回 404/空（备用链路暂不可用），
        保留此实现作为代码级备用；环境恢复后自动生效。
    """
    # lazy import: 通过 sina 模块引用 is_index_code, 使现有测试 spy 生效
    from src.python.providers import sina as _sina_mod  # noqa: E402

    if not _sina_mod.is_index_code(code):
        logger.debug("Sina 跳过非指数代码: %s", code)
        return []

    days = min(max(days, 5), 2000)  # 与 Tencent 对齐钳位 2000
    symbol = code.strip()
    url = "https://money.finance.sina.com.cn/getKLineData"

    params: dict[str, str | int] = {
        "symbol": symbol,
        "datalen": days,
        "scale": 240,
        "ma": "no",
    }

    logger.debug("Sina 指数 K 线请求: %s, days=%d", symbol, days)

    try:
        with _sina_mod.make_http_client(timeout=_KLINE_TIMEOUT) as client:
            resp = client.get(url, params=params, headers={"Referer": "https://finance.sina.com.cn"})
            resp.encoding = "utf-8"
            data = resp.json()
    except (httpx.TimeoutException, httpx.RequestError, ValueError) as e:
        logger.warning("Sina 指数 K 线获取失败 %s: %s", symbol, e)
        return []

    return _parse_kline_json(data)


def _parse_kline_json(data: list | dict | None) -> list[dict]:
    """解析 Sina K 线 JSON 响应。

    Sina 返回 JSON 数组：
    [
      {"day": "2026-07-01", "open": "21.50", "high": "22.00",
       "low": "21.30", "close": "21.80", "volume": "12345678"},
      ...
    ]
    """
    if not isinstance(data, list):
        logger.warning("Sina K 线格式异常: 非列表")
        return []

    bars: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        date_str = str(entry.get("day", "") or "")
        close_val = _parse_sina_kline_float(entry.get("close"))
        if not date_str or close_val <= 0:
            continue
        bars.append(
            {
                "date": date_str,
                "open": _parse_sina_kline_float(entry.get("open")),
                "close": close_val,
                "high": _parse_sina_kline_float(entry.get("high")),
                "low": _parse_sina_kline_float(entry.get("low")),
                "volume": _parse_sina_kline_float(entry.get("volume")),
            }
        )

    return sorted(bars, key=lambda x: x["date"])


def _parse_sina_kline_float(v: Any) -> float:
    """安全解析 Sina K 线浮点数字段。"""
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0
