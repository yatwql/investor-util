"""天天基金 API — 公共 HTTP 请求与解析工具。

包含 _safe_float、HTTP 请求函数等跨模块公用工具。
由 tiantian_holdings / tiantian_ranking / tiantian_nav 共享。
"""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any

import httpx

from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_TIMEOUT = 15.0


def _safe_float(s: Any) -> float:
    try:
        return float(s) if s is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _request_fund_html(code: str) -> str | None:
    """请求基金主页面 HTML。"""
    url = f"https://fund.eastmoney.com/{code.strip()}.html"
    logger.debug("请求基金持仓页面: %s", url)
    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            return resp.text
    except httpx.TimeoutException:
        logger.warning("基金持仓页面超时: %s", code)
        return None
    except httpx.RequestError as e:
        logger.warning("基金持仓页面请求失败 %s: %s", code, e)
        return None


def _request_pingzhong_data(code: str) -> str | None:
    """请求基金业绩数据 JS 文件。"""
    url = f"https://fund.eastmoney.com/pingzhongdata/{code.strip()}.js"
    logger.debug("请求基金业绩数据: %s", url)
    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
    except httpx.TimeoutException:
        logger.warning("基金业绩 API 请求超时: %s", code)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("基金业绩 API 返回异常状态 %s: %s", code, e.response.status_code)
        return None
    except httpx.RequestError as e:
        logger.warning("基金业绩 API 请求失败 %s: %s", code, e)
        return None


def _request_quarterly_api(code: str, api_type: str, year: int | None = None, month: int | None = None) -> str | None:
    """请求季报 API 并解析 JS 字符串内容。"""
    url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://fundf10.eastmoney.com/",
    }
    params: dict[str, Any] = {
        "type": api_type,
        "code": code.strip(),
        "topline": 10,
        "year": str(year) if year is not None else "",
        "month": str(month) if month is not None else "",
        "rt": str(random.random()),
    }
    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.encoding = "utf-8"
            text = resp.text
    except httpx.RequestError as e:
        logger.warning("基金持仓 API (%s) 请求失败 %s: %s", api_type, code, e)
        return None

    m = re.search(r'content\s*:\s*"(.+?)"\s*,\s*arryear', text, re.DOTALL)
    if not m:
        logger.debug("基金持仓 API (%s) 未找到 content 字段: %s", api_type, code)
        return None

    raw_content = m.group(1)
    if not raw_content or raw_content.isspace():
        logger.debug("基金持仓 API (%s) 内容为空: %s", api_type, code)
        return None

    try:
        return json.loads('"' + raw_content + '"')
    except json.JSONDecodeError:
        logger.warning("基金持仓 API (%s) JS 字符串解析失败: %s", api_type, code)
        return None
