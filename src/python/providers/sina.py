"""新浪财经 API — 获取全球指数行情 + A 股/ETF 实时行情。

Endpoint（指数）: https://hq.sinajs.cn/list=code1,code2,...
Endpoint（个股）: https://hq.sinajs.cn/list=sh600900

支持的指数类型：
  - 美股指数（gb_* 前缀）：主链路
  - A 股指数（s_* 前缀）：作为 A 股指数的备用链路（主链路为 Tencent）
个股行情作为 Tencent 备用链路。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.python.core.code_utils import (
    get_exchange_prefix,
    is_a_share_code,
    is_exchange_fund_code,
    is_index_code,  # noqa: F401  # re-export，sina_kline lazy import + 测试 patch 引用
)
from src.python.core.http_client import make_http_client

logger = logging.getLogger("invest")

_BASE_URL = "https://hq.sinajs.cn/list="
_TIMEOUT = 15.0  # 普通行情超时


def _pf(parts: list[str], idx: int) -> float:
    """安全地按索引从 CSV 行中提取浮点数。"""
    try:
        return float(parts[idx].strip()) if parts[idx].strip() else 0.0
    except (ValueError, IndexError):
        return 0.0


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
    "s_sh000905": "中证500",
    "s_sh000012": "中证全债",
}

# ── 个股行情（作为 Tencent 备用链路）───────────────────────

# Sina 标准 A 股行情返回格式（逗号分隔，~46 字段）：
# var hq_str_sh600900="名称,开盘,昨收,现价,最高,最低,买价,卖价,成交量,成交额,...,日期,时间,00";
# 关键字段索引：
#   0=名称, 1=开盘, 2=昨收, 3=现价, 8=成交量(手), 9=成交额(元),
#   30=日期(YYYY-MM-DD), 31=时间


def _add_prefix(code: str) -> str:
    """根据代码前缀添加交易所标识。"""
    code = code.strip()
    if len(code) != 6:
        return code
    return get_exchange_prefix(code) + code


def _parse_price_response(text: str, code: str) -> dict[str, Any] | None:
    """解析 Sina 个股行情返回文本为结构化 dict。

    Returns:
        dict: {name, code, price, yesterday_close, price_date, ...}
        None: 解析失败
    """
    try:
        start = text.index('"') + 1
        end = text.rindex('"')
        body = text[start:end]
    except ValueError:
        logger.warning("Sina 行情格式异常: %s", text[:80])
        return None

    if not body:
        return None

    parts = body.split(",")
    if len(parts) < 32:
        logger.warning("Sina 行情字段不足(%d): %s", len(parts), body[:80])
        return None

    name = parts[0].strip() if parts[0] else ""
    price = _pf(parts, 3)
    yclose = _pf(parts, 2)
    raw_date = parts[30].strip() if len(parts) > 30 else ""
    price_date = raw_date.split(" ")[0] if raw_date else ""

    return {
        "name": name,
        "code": code,
        "price": price,
        "yesterday_close": yclose,
        "price_date": price_date,
        "open": _pf(parts, 1),
        "high": _pf(parts, 4),
        "low": _pf(parts, 5),
        "volume": _pf(parts, 8),
        "turnover": _pf(parts, 9),
        "source": "新浪财经",
    }


def fetch_price(code: str) -> dict[str, Any] | None:
    """获取单只 A 股/ETF 实时行情（Tencent 备用链路）。

    与 Tencent 相似的代码前缀策略：仅支持 A 股股票和场内基金/ETF。

    Args:
        code: 6 位证券代码（如 "600900"、"159222"）

    Returns:
        dict: {name, code, price, yesterday_close, price_date, ...}
        None: 网络异常/解析失败/不支持的类型
    """
    # 仅支持 A 股和场内基金/ETF（与 Tencent 策略一致）
    if not is_a_share_code(code) and not is_exchange_fund_code(code):
        logger.debug("Sina 跳过不支持的类型: %s", code)
        return None

    full_code = _add_prefix(code)
    url = _BASE_URL + full_code

    logger.debug("Sina 行情请求: %s", full_code)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers={"Referer": "https://finance.sina.com.cn"})
            resp.encoding = "gb18030"
            text = resp.text
    except httpx.TimeoutException:
        logger.warning("Sina 行情 API 超时: %s", full_code)
        return None
    except httpx.RequestError as e:
        logger.warning("Sina 行情 API 请求失败: %s", e)
        return None

    return _parse_price_response(text, code)


# ── A 股指数行情（Tencent 备用链路）─────────────────────────


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

    name = parts[0].strip() if parts[0] else ""
    price = _pf(parts, 1)
    change = _pf(parts, 2)

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

    name = parts[0].strip() if parts[0] else ""
    price = _pf(parts, 1)
    change = _pf(parts, 4)
    high = _pf(parts, 6)
    low = _pf(parts, 7)

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


# ── 从 sina_kline 子模块导入 K 线相关函数 ────────────────────────
from src.python.providers.sina_kline import (  # noqa: E402, F401
    fetch_kline,
    fetch_index_kline,
)
