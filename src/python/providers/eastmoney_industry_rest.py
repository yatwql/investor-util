"""东方财富 REST API — 行业分类备用链路（push2 不可用时使用）。

当 push2 接口（eastmoney_industry）因服务器断开连接等问题不可用时，
通过标准 HTTP GET 获取东方财富行情页面中的行业分类数据。

数据来源: quote.eastmoney.com/{prefix}{code}.html
  - 页面内嵌 JavaScript 变量 quotedata
  - bk_name: 行业名称（如"白酒Ⅱ"）
  - bk_id:   行业板块代码（如"BK1277"）

注意：概念板块数据在行情页中通过 XHR 动态加载，
本 fallback 无法获取，返回空列表，与 push2 的 concept_ids 行为一致。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from src.python.code_utils import get_exchange_prefix
from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_QUOTE_BASE = "https://quote.eastmoney.com/{prefix}{code}.html"
_TIMEOUT = 15.0
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# 会话级内存缓存 — 委托 DataSourceRegistry session_cache（C4 约束, domain="industry_rest"）


def _quote_prefix(code: str) -> str:
    """生成行情页面所需的交易所前缀（委托至 code_utils.get_exchange_prefix）。"""
    return get_exchange_prefix(code)


def _extract_quotedata(html: str) -> dict | None:
    """从 HTML 页面中提取 quotedata JavaScript 对象。

    Args:
        html: 完整的页面 HTML

    Returns:
        解析后的 quotedata 字典；未找到或解析失败返回 None
    """
    m = re.search(r'var\s+quotedata\s*=\s*({.*?})\s*;', html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def fetch_industry_and_concepts(code: str) -> dict[str, Any] | None:
    """通过行情页 REST API 获取一只证券的行业分类。

    会话级内存复用（C4）：同一代码在同一会话内仅首次发起 HTTP 请求，
    后续调用直接返回缓存结果。

    当 push2 不可用时作为 fallback 使用。
    仅返回行业名称和板块代码，概念板块列表留空。

    Args:
        code: 6 位证券代码

    Returns:
        dict:
            - code: 证券代码
            - industry: 行业名称（如"白酒Ⅱ"）
            - industry_id: 行业板块代码（如"BK1277"）
            - concepts: 空列表（概念板块数据需 push2 获取）
            - concept_ids: 空列表
        None: 页面请求失败或未找到行业数据
    """
    from src.python.provider_registry import get_registry, NOT_FOUND
    reg = get_registry()
    cached = reg.session_cache_get("industry_rest", code)
    if cached is not NOT_FOUND:
        return cached

    prefix = _quote_prefix(code)
    url = _QUOTE_BASE.format(prefix=prefix, code=code)

    logger.debug("东方财富 REST 行情页请求: %s", url)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers=_HEADERS, follow_redirects=True)
            html = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("东方财富 REST 行情页请求失败 [%s]: %s", code, e)
        reg.session_cache_set("industry_rest", code, None)
        return None

    qd = _extract_quotedata(html)
    if not qd:
        logger.warning("东方财富 REST 行情页未找到行业数据 [%s]", code)
        reg.session_cache_set("industry_rest", code, None)
        return None

    industry = qd.get("bk_name", "") or ""
    industry_id = qd.get("bk_id", "") or ""

    logger.debug("东方财富 REST 行业 [%s]: 行业=%s", code, industry or "无")

    result: dict[str, Any] = {
        "code": code.strip(),
        "industry": industry,
        "industry_id": industry_id,
        # 概念板块数据通过 XHR 动态加载，本 fallback 无法获取
        "concepts": [],
        "concept_ids": [],
    }
    reg.session_cache_set("industry_rest", code, result)
    return result
