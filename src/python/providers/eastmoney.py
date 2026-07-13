"""东方财富 API — 获取场外基金最新净值。

主链路: api.fund.eastmoney.com
备用链路: fundf10.eastmoney.com（天天基金）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_FUND_API_URL = "https://api.fund.eastmoney.com/f10/lsjz"
_TIMEOUT = 15.0
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}


def _strip_jsonp(text: str) -> str:
    """剥离 JSONP 回调包裹，提取纯 JSON。"""
    # 匹配 `jQueryXXXXXX({...})` 或 `jsonpCallback({...})`
    m = re.search(r"\(({.*})\)\s*$", text, re.DOTALL)
    if m:
        return m.group(1)
    # 也可能是纯 JSON 返回
    return text


def fetch_nav(code: str) -> dict[str, Any] | None:
    """获取一只场外基金的最新单位净值。

    通过东方财富基金数据 API 获取最新一条净值记录。

    Args:
        code: 6 位基金代码（如 "011506"）

    Returns:
        dict:
            - name: 基金名称（可能为空）
            - code: 基金代码
            - nav: 最新单位净值（float）
            - acc_nav: 累计净值（float）
            - nav_date: 净值日期（如 "2026-06-25"）
            - yesterday_nav: 前一日单位净值（float）
            - source: "东方财富" 或 "天天基金"
        None: 网络异常或解析失败
    """
    params: dict[str, Any] = {
        "callback": "jQuery",
        "fundCode": code.strip(),
        "pageIndex": 1,
        "pageSize": 3,  # 取 3 条以获得前一日净值
    }

    logger.debug("东方财富 API 请求基金: %s", code)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(_FUND_API_URL, params=params, headers=_HEADERS)
            text = resp.text
    except httpx.TimeoutException:
        logger.warning("东方财富 API 超时: %s", code)
        return _fallback_fundf10(code)
    except httpx.RequestError as e:
        logger.warning("东方财富 API 请求失败: %s", e)
        return _fallback_fundf10(code)

    json_str = _strip_jsonp(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning("东方财富 JSON 解析失败: %s", e)
        return _fallback_fundf10(code)

    records = (data.get("Data", {}) or {}).get("LSJZList", [])
    if not records:
        logger.warning("东方财富无净值数据: %s", code)
        return _fallback_fundf10(code)

    # 取最新一条
    latest = records[0]
    nav = _safe_float(latest.get("DWJZ", "0"))
    nav_date = latest.get("FSRQ", "")

    # 前一日净值（第二条）
    yesterday_nav = 0.0
    if len(records) > 1:
        yesterday_nav = _safe_float(records[1].get("DWJZ", "0"))
    elif nav_date:
        # 只有一条记录，无法确定前日净值
        yesterday_nav = nav

    name = (data.get("Data", {}) or {}).get("FundName", "")

    return {
        "name": name,
        "code": code.strip(),
        "nav": nav,
        "acc_nav": _safe_float(latest.get("LJJZ", "0")),
        "nav_date": nav_date,
        "yesterday_nav": yesterday_nav,
        "source": "东方财富",
    }


def _fallback_fundf10(code: str) -> dict[str, Any] | None:
    """备用链路：通过天天基金 fundf10 页面解析最新净值。"""
    url = f"https://fundf10.eastmoney.com/jjjz_{code.strip()}.html"
    logger.info("切换备用链路: %s", url)

    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            html = resp.text
    except httpx.RequestError:
        logger.warning("备用链路也失败: %s", code)
        return None

    # 从 HTML 中提取最新净值
    # 典型模式：<td class='bold'>1.2345</td>
    nav_match = re.search(
        r'<td\s+class="[^"]*bold[^"]*">\s*(\d+\.\d+)\s*</td>',
        html,
    )
    date_match = re.search(
        r'<td\s+class="[^"]*">\s*(\d{4}-\d{2}-\d{2})\s*</td>',
        html,
    )

    if not nav_match:
        logger.warning("备用链路解析失败: %s", code)
        return None

    nav = _safe_float(nav_match.group(1))
    nav_date = date_match.group(1) if date_match else ""

    return {
        "name": "",
        "code": code.strip(),
        "nav": nav,
        "acc_nav": 0.0,
        "nav_date": nav_date,
        "yesterday_nav": nav,  # 备用链路无前日净值，使用 nav 确保 today_profit=0
        "source": "天天基金(备用链路)",
    }


def _safe_float(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def fetch_fund_nav_history(code: str) -> list[dict]:
    """获取场外基金历史净值（备用链路）。

    通过东方财富基金历史净值 API 获取全量历史净值数据，
    与 tiantian.fetch_fund_nav_history() 返回格式兼容。

    Args:
        code: 6 位基金代码

    Returns:
        list[dict]: [{date, nav, acc_nav}, ...]
        按日期升序排列。API 失败返回空列表。
    """
    params: dict[str, Any] = {
        "callback": "jQuery",
        "fundCode": code.strip(),
        "pageIndex": 1,
        "pageSize": 365,
    }

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(_FUND_API_URL, params=params, headers=_HEADERS)
            text = resp.text
    except httpx.RequestError:
        logger.warning("[eastmoney] 历史净值 API 请求失败: %s", code)
        return []

    json_str = _strip_jsonp(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("[eastmoney] 历史净值 JSON 解析失败: %s", code)
        return []

    records = (data.get("Data", {}) or {}).get("LSJZList", [])
    if not records:
        logger.warning("[eastmoney] 无历史净值数据: %s", code)
        return []

    result: list[dict] = []
    for r in records:
        date_str = (r.get("FSRQ") or "").strip()
        nav = _safe_float(r.get("DWJZ", "0"))
        acc_nav = _safe_float(r.get("LJJZ", "0"))
        if not date_str or (nav <= 0 and acc_nav <= 0):
            continue
        result.append({
            "date": date_str,
            "nav": nav,
            "acc_nav": acc_nav,
        })

    # API 返回最新在前，按日期升序排列
    result.sort(key=lambda x: x["date"])
    return result
