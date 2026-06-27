"""东方财富 push2 API — 获取行业分类与概念板块归属。

主链路: push2.eastmoney.com/api/qt/stock/get
  - f127: 行业 ID
  - f128: 行业名称（三级行业）
  - f140: 概念板块 ID 列表（逗号分隔）
  - f141: 概念板块名称列表（逗号分隔）

secid 前缀规则：
  - 1.{code} — 上海（60xxxx）和深圳（00xxxx, 30xxxx）股票通用
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("invest")

_PUSH2_BASE = "https://push2.eastmoney.com/api/qt/stock/get"
_TIMEOUT = 10.0
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}


def _secid(code: str) -> str:
    """根据代码生成 secid 参数。

    上海股票 (60xxxx、68xxxx) 和 深圳股票 (00xxxx、30xxxx)
    统一使用 1. 前缀。基金代码 (如 000961、011506) 也使用 1. 前缀。
    """
    code = code.strip()
    return f"1.{code}"


def fetch_industry_and_concepts(code: str) -> dict[str, Any] | None:
    """获取一只证券的行业分类和概念板块归属。

    Args:
        code: 6 位证券代码

    Returns:
        {
            "code": "600900",
            "industry": "电力设备",       # 三级行业名称
            "industry_id": "BKxxxx",      # 行业 ID
            "concepts": ["CPO光模块", "人工智能", ...],  # 概念板块列表
            "concept_ids": ["BKxxxx", "BKxxxx", ...],    # 概念板块 ID
        }
        None: API 异常或解析失败
    """
    params = {
        "secid": _secid(code),
        "fields": "f57,f58,f128,f140,f141",
    }

    logger.debug("东方财富 push2 行业/概念请求: %s", code)

    try:
        with httpx.Client(timeout=_TIMEOUT, verify=False) as client:
            resp = client.get(_PUSH2_BASE, params=params, headers=_HEADERS)
            resp.encoding = "utf-8"
            text = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("东方财富 push2 请求失败 [%s]: %s", code, e)
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("东方财富 push2 JSON 解析失败 [%s]: %s", code, e)
        return None

    # push2 返回格式: {"data": {...}}
    inner = data.get("data")
    if not inner or not isinstance(inner, dict):
        logger.warning("东方财富 push2 返回空数据 [%s]", code)
        return None

    # f128 = 行业名称
    industry: str = (inner.get("f128") or "").strip()
    industry_id: str = (inner.get("f127") or "").strip()

    # f141 = 概念板块名称列表（逗号分隔）
    # f140 = 概念板块 ID 列表（逗号分隔）
    concepts_raw: str = (inner.get("f141") or "").strip()
    concept_ids_raw: str = (inner.get("f140") or "").strip()

    concepts: list[str] = []
    concept_ids: list[str] = []
    if concepts_raw:
        concepts = [c.strip() for c in concepts_raw.split(",") if c.strip()]
    if concept_ids_raw:
        concept_ids = [c.strip() for c in concept_ids_raw.split(",") if c.strip()]

    result: dict[str, Any] = {
        "code": code.strip(),
        "industry": industry,
        "industry_id": industry_id,
        "concepts": concepts,
        "concept_ids": concept_ids,
    }

    logger.debug("东方财富行业/概念 [%s]: 行业=%s, 概念=%d个",
                 code, industry or "无", len(concepts))
    return result


def fetch_industry(code: str) -> str | None:
    """仅获取行业名称（便捷接口）。

    Args:
        code: 6 位证券代码

    Returns:
        行业名称字符串（如 "电力设备"）；失败返回 None
    """
    result = fetch_industry_and_concepts(code)
    if result and result.get("industry"):
        return result["industry"]
    return None


def fetch_concepts(code: str) -> list[str]:
    """仅获取概念板块列表（便捷接口）。

    Args:
        code: 6 位证券代码

    Returns:
        概念板块名称列表；失败或无概念时返回空列表
    """
    result = fetch_industry_and_concepts(code)
    if result:
        return result.get("concepts", [])
    return []
