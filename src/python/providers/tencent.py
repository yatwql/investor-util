"""腾讯财经 API — 获取股票/ETF 实时行情。

Endpoint: qt.gtimg.cn
支持上海（sh）和深圳（sz）股票代码，自动添加前缀。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.python.code_utils import (
    get_exchange_prefix,
    is_a_share_code,
    is_exchange_fund_code,
    is_index_code,
)
from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_BASE_URL = "https://qt.gtimg.cn/q="
_TIMEOUT = 15.0  # 普通行情超时
_KLINE_TIMEOUT = 30.0  # K 线超时（需等待更多数据）


# Tencent 实际返回格式（~ 分隔）：
# v_sh561910="1~科创材料ETF~561910~0.853~0.901~...";
# ▲ 序号  名称     代码   最新价   昨收
# split("~") 后：parts[0]="1"(序号), parts[1]="科创材料ETF", parts[2]="561910", ...
# _get(idx) 读取 parts[idx-1]，所以 name=2 → parts[1] ✓
_FIELD_MAP: dict[str, int] = {
    "name": 2,  # 名称
    "code": 3,  # 代码
    "price": 4,  # 当前价格
    "yesterday_close": 5,  # 昨收
    "open": 6,  # 今开
    "volume": 7,  # 成交量（手）
    "turnover": 8,  # 成交额
    "price_date": 31,  # 日期时间 YYYYMMDDHHMMSS
    "high": 34,  # 最高价
    "low": 35,  # 最低价
    "market_cap": 46,  # 总市值（API 返回亿，内部保持原始值，下游按需转换）
    "pe": 40,  # 动态市盈率
}


def _add_prefix(code: str) -> str:
    """根据代码前缀添加交易所标识（委托至 code_utils.get_exchange_prefix）。"""
    code = code.strip()
    if len(code) != 6:
        return code
    return get_exchange_prefix(code) + code


def _parse_response(text: str) -> dict[str, Any] | None:
    """解析 Tencent API 返回文本为结构化 dict。

    Tencent 返回格式示例:
        v_sh561910="1~科创材料ETF~561910~0.853~0.901~...";
        字段 ~ 分隔，_get(idx) → parts[idx-1]，第 1 个字段为序号

    Returns:
        dict 或 None（解析失败时）
    """
    # 提取引号内的内容
    try:
        start = text.index('"') + 1
        end = text.rindex('"')
        body = text[start:end]
    except ValueError:
        logger.warning("Tencent API 返回格式异常: %s", text[:80])
        return None

    if not body:
        return None

    parts = body.split("~")
    if len(parts) < 10:
        logger.warning("Tencent API 字段不足: %s", body[:80])
        return None

    def _get(idx: int) -> str:
        """取第 idx 个字段的 = 号后面的值。"""
        raw = parts[idx - 1] if idx <= len(parts) else ""
        if "=" in raw:
            return raw.split("=", 1)[1]
        return raw

    price_str = _get(_FIELD_MAP["price"]).strip()
    yclose_str = _get(_FIELD_MAP["yesterday_close"]).strip()
    raw_date = _get(_FIELD_MAP["price_date"]).strip()

    # 价格可能为 "0.000"（停牌或无数据）
    price = _parse_float(price_str)
    yclose = _parse_float(yclose_str)

    # 提取日期（YYYYMMDDHHMMSS → YYYY-MM-DD）
    price_date = ""
    if len(raw_date) >= 8 and raw_date.isdigit():
        price_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

    return {
        "name": _get(_FIELD_MAP["name"]).strip(),
        "code": _get(_FIELD_MAP["code"]).strip(),
        "price": price,
        "yesterday_close": yclose,
        "price_date": price_date,
        "open": _parse_float(_get(_FIELD_MAP["open"])),
        "high": _parse_float(_get(_FIELD_MAP["high"])),
        "low": _parse_float(_get(_FIELD_MAP["low"])),
        "volume": _parse_float(_get(_FIELD_MAP["volume"])),
        "turnover": _parse_float(_get(_FIELD_MAP["turnover"])),
        "market_cap": _parse_float(_get(_FIELD_MAP["market_cap"])),
        "pe": _parse_float(_get(_FIELD_MAP["pe"])),
        "source": "腾讯财经",
    }


def _parse_float(s: str) -> float:
    """安全解析浮点数，失败返回 0.0。"""
    try:
        v = float(s)
    except (ValueError, TypeError):
        return 0.0
    return v if v > 0 else 0.0


def fetch_price(code: str) -> dict[str, Any] | None:
    """获取一只股票的实时行情。

    Args:
        code: 6 位股票/ETF 代码（如 "600900"）

    Returns:
        dict:
            - name: 名称
            - code: 代码
            - price: 当前价格（float，不可用时为 0.0）
            - yesterday_close: 昨收（float）
            - open / high / low / volume / turnover
            - source: "腾讯财经"
        None: 网络异常或解析失败
    """
    # Tencent 仅支持 A 股代码和场内 ETF/LOF/可转债，场外基金等直接跳过
    if not is_a_share_code(code) and not is_exchange_fund_code(code):
        logger.debug("Tencent 跳过不支持的类型: %s", code)
        return None

    full_code = _add_prefix(code)
    url = f"{_BASE_URL}{full_code}"

    logger.debug("Tencent API 请求: %s", full_code)

    # 超时/网络错误自动重试一次
    for attempt in (1, 2):
        try:
            with make_http_client(timeout=_TIMEOUT) as client:
                resp = client.get(url)
                resp.encoding = "gbk"  # qt.gtimg.cn 返回 GBK 编码
                text = resp.text
        except httpx.TimeoutException:
            logger.warning("Tencent API 超时: %s（第 %d 次）", full_code, attempt)
            if attempt == 1:
                continue
            return None
        except httpx.RequestError as e:
            logger.warning("Tencent API 请求失败: %s（第 %d 次）", e, attempt)
            if attempt == 1:
                continue
            return None
        break  # 成功 → 跳出重试循环

    result = _parse_response(text)
    if result is None:
        logger.warning("Tencent API 解析失败: %s", full_code)

    return result


def fetch_index_price(code: str) -> dict[str, Any] | None:
    """获取指数实时行情（A 股/美股通用），作为备用链路。

    与 fetch_price 的区别：不添加交易所前缀，直接使用原始代码（如 gb_dji）。
    Tencent API 对指数返回的 ~ 分隔格式与股票一致，使用同一解析器。

    Args:
        code: 指数代码（如 "sh000001"、"gb_dji"）

    Returns:
        dict（同 fetch_price）或 None
    """
    url = f"{_BASE_URL}{code.strip()}"

    logger.debug("Tencent 指数 API 请求: %s", code)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url)
            resp.encoding = "gbk"
            text = resp.text
    except httpx.TimeoutException:
        logger.warning("Tencent 指数 API 超时: %s", code)
        return None
    except httpx.RequestError as e:
        logger.warning("Tencent 指数 API 请求失败: %s", e)
        return None

    result = _parse_response(text)
    if result is None:
        logger.warning("Tencent 指数 API 解析失败: %s", code)

    return result


# ── 组合历史走势：历史 K 线数据 ─────────────────────────────────


def fetch_kline(code: str, days: int = 30, start_from: str | None = None) -> list[dict]:
    """获取股票/ETF 历史 K 线数据（前复权，纯获取，由 chain 层管理缓存）。

    Endpoint: web.ifzq.gtimg.cn/appstock/app/fqkline/get
    Tencent K 线 API 返回 JSON 格式，支持前复权（qfq）。

    参数约定（C6 约束）：
      - Provider 函数保持纯数据获取，不碰缓存层
      - 缓存合并由 chain 层的 fetch_with_incremental_fallback() 管理
      - ✅ C5：所有 HTTP 请求使用 make_http_client()

    Args:
        code: 6 位证券代码（如 "600900"）
        days: 获取天数（默认 30，最大 365）
        start_from: 起始日期（YYYY-MM-DD），用于增量获取。
                    为 None 时从头获取 days 天数据。

    Returns:
        list[dict]: [{date, open, close, high, low, volume}, ...]
        按日期升序排列。API 失败返回空列表。
    """
    if not is_a_share_code(code) and not is_exchange_fund_code(code):
        logger.debug("Tencent K 线跳过不支持的类型: %s", code)
        return []

    days = min(max(days, 5), 365)
    full_code = _add_prefix(code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    params: dict[str, str | int] = {
        "param": f"{full_code},day,{start_from or ''},,{days},qfq",
    }

    logger.debug("Tencent K 线请求: %s, days=%d", full_code, days)

    try:
        with make_http_client(timeout=_KLINE_TIMEOUT) as client:
            resp = client.get(url, params=params)
            resp.encoding = "utf-8"
            data = resp.json()
    except (httpx.TimeoutException, httpx.RequestError, ValueError) as e:
        logger.warning("Tencent K 线获取失败 %s: %s", full_code, e)
        return []

    return _parse_kline_response(data, full_code)


def _parse_kline_response(data: dict, code: str) -> list[dict]:
    """解析 Tencent K 线 JSON 响应。

    Tencent 返回格式：
    {
      "data": {
        "code": {
          "day": [["2026-07-01", "21.50", "22.00", "21.30", "21.80", "12345678"], ...],
          "qfqday": [["2026-07-01", "21.50", "22.00", "21.30", "21.80", "12345678"], ...],
        }
      }
    }

    优先使用 qfqday（前复权），回退到 day。
    """
    bars: list[dict] = []
    try:
        inner = data.get("data", {}).get(code, {})
        # 优先前复权
        kline = inner.get("qfqday") or inner.get("day", [])
        if not kline:
            return []

        for entry in kline:
            if not isinstance(entry, (list, tuple)) or len(entry) < 6:
                continue
            date_str = str(entry[0])
            values = [_parse_float_field(str(v)) for v in entry[1:6]]
            if not date_str or values[1] <= 0:
                continue  # 跳过停牌/无效数据
            bars.append(
                {
                    "date": date_str,
                    "open": values[0],
                    "close": values[1],
                    "high": values[2],
                    "low": values[3],
                    "volume": values[4],
                }
            )
    except (KeyError, TypeError, IndexError) as e:
        logger.warning("Tencent K 线解析异常: %s", e)
        return []

    return sorted(bars, key=lambda x: x["date"])


def fetch_index_kline(code: str, days: int = 30, start_from: str | None = None) -> list[dict]:
    """获取指数历史 K 线数据（前复权）。

    与 fetch_kline() 的区别：
      - 入口通过 code_utils.is_index_code() 校验（C1 约束）
      - 不检查 is_a_share_code/is_exchange_fund_code
      - 代码直接透传 API，不调用 _add_prefix（指数代码已含交易所前缀）
      - 复用 _parse_kline_response() 解析逻辑

    Args:
        code: 指数代码，如 "sh000300" / "gb_inx"
        days: 获取天数（默认 30，最大 3650）
        start_from: 起始日期 YYYY-MM-DD，为 None 时从头获取

    Returns:
        list[dict]: [{date, open, close, high, low, volume}, ...]
        按日期升序排列。API 失败返回空列表。
    """
    if not is_index_code(code):
        logger.debug("Tencent 跳过非指数代码: %s", code)
        return []

    days = min(max(days, 5), 3650)
    full_code = code.strip()
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    params: dict[str, str | int] = {
        "param": f"{full_code},day,{start_from or ''},,{days},qfq",
    }

    logger.debug("Tencent 指数 K 线请求: %s, days=%d", full_code, days)

    try:
        with make_http_client(timeout=_KLINE_TIMEOUT) as client:
            resp = client.get(url, params=params)
            resp.encoding = "utf-8"
            data = resp.json()
    except (httpx.TimeoutException, httpx.RequestError, ValueError) as e:
        logger.warning("Tencent 指数 K 线获取失败 %s: %s", full_code, e)
        return []

    return _parse_kline_response(data, full_code)


def _parse_float_field(s: str) -> float:
    """安全解析浮点数字段，失败返回 0.0。"""
    try:
        return float(s) if s else 0.0
    except (ValueError, TypeError):
        return 0.0
