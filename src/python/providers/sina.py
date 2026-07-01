"""新浪财经 API — 获取全球指数行情（美股指数 + A 股指数备用）。

Endpoint: https://hq.sinajs.cn/list=code1,code2,...

支持的指数类型：
  - 美股指数（gb_* 前缀）：主链路
  - A 股指数（s_* 前缀）：作为 A 股指数的备用链路（主链路为 Tencent）
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_BASE_URL = "https://hq.sinajs.cn/list="
_TIMEOUT = 15.0

# 美股指数代码 (gb_* 前缀为新浪全球指数代码)
_US_INDICES: dict[str, str] = {
    "gb_dji": "道琼斯",
    "gb_ixic": "纳斯达克",
    "gb_inx": "标普500",
}

# A 股指数代码（s_* 前缀，作为 Tencent 备用链路）
# 与 fetcher/index.py 中 _A_INDICES 的代码一一对应，仅前缀不同
_A_INDICES_SINA: dict[str, str] = {
    "s_sh000001": "上证指数",
    "s_sz399001": "深证成指",
    "s_sh000300": "沪深300",
    "s_sh000688": "科创板50",
    "s_sz399006": "创业板指",
}


def _parse_a_index(text: str) -> dict[str, Any] | None:
    """解析 Sina A 股指数返回文本（s_* 格式）。

    Sina A 股指数返回格式:
        var hq_str_s_sh000001="上证指数,当前价,涨跌额,涨跌幅%,成交量,成交额,日期时间";

    关键字段索引:
        [0]: 名称
        [1]: 当前价
        [2]: 涨跌额（绝对点数）
        [3]: 涨跌幅%
        [4]: 成交量（手）
        [5]: 成交额（元）
        [6]: 日期时间

    昨收盘由 price - change 计算得出。
    """
    try:
        start = text.index('"') + 1
        end = text.rindex('"')
        body = text[start:end]
    except ValueError:
        return None

    if not body:
        return None

    parts = body.split(",")
    if len(parts) < 7:
        return None

    def _pf(idx: int) -> float:
        try:
            return float(parts[idx].strip()) if parts[idx].strip() else 0.0
        except (ValueError, IndexError):
            return 0.0

    name = parts[0].strip() if parts[0] else ""
    price = _pf(1)
    change = _pf(2)

    # 昨收盘 = 当前价 - 涨跌额
    yclose = round(price - change, 2) if price > 0 else 0.0
    change_pct = round(change / yclose * 100, 2) if yclose > 0 else 0.0

    raw_datetime = parts[6].strip() if len(parts) > 6 else ""
    price_date = raw_datetime.split(" ")[0].replace("/", "-") if raw_datetime else ""

    return {
        "name": name,
        "price": price,
        "yesterday_close": yclose,
        "price_date": price_date,
        "change": change,
        "change_pct": change_pct,
        "source": "新浪财经",
    }


def fetch_a_indices() -> dict[str, dict[str, Any]]:
    """通过新浪财经获取 A 股主要指数行情（Tencent 主链路的备用）。

    Returns:
        {code: {name, price, yesterday_close, price_date, change, change_pct}}
    """
    codes = list(_A_INDICES_SINA.keys())
    url = _BASE_URL + ",".join(codes)

    logger.debug("Sina A 股指数请求: %s", codes)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers={"Referer": "https://finance.sina.com.cn"})
            resp.encoding = "gb18030"
            text = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("Sina A 股指数 API 请求失败: %s", e)
        return {}

    results: dict[str, dict[str, Any]] = {}
    lines = text.strip().split("\n")
    for line in lines:
        if not line.startswith("var hq_str_"):
            continue
        if "=" not in line:
            continue
        var_part = line.split("=", 1)[0]
        code = var_part.replace("var hq_str_", "").strip()
        if code not in codes:
            continue

        parsed = _parse_a_index(line)
        if parsed and parsed["price"] > 0:
            results[code] = {
                "name": _A_INDICES_SINA.get(code, parsed.get("name", "")),
                "code": code,
                "price": parsed["price"],
                "yesterday_close": parsed["yesterday_close"],
                "price_date": parsed["price_date"],
                "change": parsed["change"],
                "change_pct": parsed["change_pct"],
            }

    return results


def _parse_us_index(text: str) -> dict[str, Any] | None:
    """解析 Sina US 指数返回文本 (gb_* 格式)。

    Sina 返回格式:
        var hq_str_gb_dji="name,price,change_pct,datetime,change,...";

    关键字段索引:
        [0]: 名称
        [1]: 当前价
        [2]: 涨跌幅%
        [3]: 日期时间 (YYYY-MM-DD HH:MM:SS)
        [4]: 涨跌额（绝对点数）
        [6]: 最高
        [7]: 最低

    昨收盘由 price - change 计算得出，比精确字段位置更可靠。
    """
    try:
        start = text.index('"') + 1
        end = text.rindex('"')
        body = text[start:end]
    except ValueError:
        return None

    if not body:
        return None

    parts = body.split(",")
    if len(parts) < 5:
        return None

    def _pf(idx: int) -> float:
        try:
            return float(parts[idx].strip()) if parts[idx].strip() else 0.0
        except (ValueError, IndexError):
            return 0.0

    name = parts[0].strip() if parts[0] else ""
    price = _pf(1)
    change = _pf(4)
    high = _pf(6)
    low = _pf(7)

    # 昨收盘 = 当前价 - 涨跌额
    yclose = round(price - change, 2) if price > 0 else 0.0
    change_pct = round(change / yclose * 100, 2) if yclose > 0 else 0.0

    # 日期（从 parts[3] 提取 YYYY-MM-DD 部分）
    raw_datetime = parts[3].strip() if len(parts) > 3 else ""
    price_date = raw_datetime.split(" ")[0] if raw_datetime else ""

    return {
        "name": name,
        "price": price,
        "yesterday_close": yclose,
        "high": high,
        "low": low,
        "price_date": price_date,
        "change": change,
        "change_pct": change_pct,
        "source": "新浪财经",
    }


def fetch_us_indices() -> dict[str, dict[str, Any]]:
    """获取美股三大指数行情。

    Returns:
        {code: {name, price, yesterday_close, price_date, change, change_pct}}
    """
    codes = list(_US_INDICES.keys())
    url = _BASE_URL + ",".join(codes)

    logger.debug("Sina US 指数请求: %s", codes)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers={"Referer": "https://finance.sina.com.cn"})
            resp.encoding = "gb18030"  # Sina 返回 GB18030 编码
            text = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("Sina API 请求失败: %s", e)
        return {}

    # 每行一条指数，用换行分隔
    results: dict[str, dict[str, Any]] = {}
    lines = text.strip().split("\n")
    for line in lines:
        if not line.startswith("var hq_str_"):
            logger.warning("Sina 格式异常: %s", line[:60])
            continue
        if "=" not in line:
            continue
        var_part = line.split("=", 1)[0]
        # 提取代码 (hq_str_int_dji → int_dji)
        code = var_part.replace("var hq_str_", "").strip()
        if code not in codes:
            continue

        parsed = _parse_us_index(line)
        if parsed and parsed["price"] > 0:
            results[code] = {
                "name": _US_INDICES.get(code, parsed.get("name", "")),
                "code": code,
                "price": parsed["price"],
                "yesterday_close": parsed["yesterday_close"],
                "price_date": parsed["price_date"],
                "change": parsed["change"],
                "change_pct": parsed["change_pct"],
            }

    return results
