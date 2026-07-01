"""东方财富 push2 API — 获取行业分类与概念板块归属。

主链路: push2.eastmoney.com/api/qt/stock/get
  - f127: 行业名称（三级行业，如"电力""白酒Ⅱ"）
  - f128: 地域板块（如"北京板块""广东板块"）
  - f129: 概念板块名称列表（逗号分隔，如"创投,参股银行,..."）
  - f198: 行业 BK 代码（如"BK0428"）
  - f140: 已变更为数值字段，不再包含概念 ID

secid 前缀规则：
  - 1.{code} — 上海（60xxxx, 68xxxx, 51xxxx, 56xxxx, 58xxxx）
  - 0.{code} — 深圳（00xxxx, 30xxxx, 15xxxx, 2xxxxx）
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_PUSH2_BASE = "https://push2.eastmoney.com/api/qt/stock/get"
_TIMEOUT = 10.0
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}


def _secid(code: str) -> str:
    """根据代码生成 secid 参数。

    上海股票 (60xxxx、68xxxx) 及沪市 ETF (51xxxx、56xxxx、58xxxx)
    使用 1.{code} 前缀。
    深圳股票 (00xxxx、30xxxx) 及深市 ETF (15xxxx、2xxxxx)
    使用 0.{code} 前缀。
    """
    code = code.strip()
    if code.startswith(("0", "1", "2", "3")):  # 深市
        return f"0.{code}"
    return f"1.{code}"  # 沪市（含 5/6/8/4 开头）


def _make_push2_request(code: str) -> dict | None:
    """执行 push2 行业/概念 API 请求，返回 data 内层字典或 None。"""
    params = {
        "secid": _secid(code),
        "fields": "f57,f58,f127,f128,f129,f198",
    }
    logger.debug("东方财富 push2 行业/概念请求: %s", code)

    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(_PUSH2_BASE, params=params, headers=_HEADERS)
            text = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("东方财富 push2 请求失败 [%s]: %s", code, e)
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("东方财富 push2 JSON 解析失败 [%s]: %s", code, e)
        return None

    inner = data.get("data")
    if not inner or not isinstance(inner, dict):
        logger.warning("东方财富 push2 返回空数据 [%s]", code)
        return None
    return inner


def _extract_concept_list(inner: dict) -> list[str]:
    """从 push2 响应中提取概念板块名称列表。"""
    concepts_raw = inner.get("f129")
    if concepts_raw is not None and isinstance(concepts_raw, str):
        concepts_str = concepts_raw.strip()
        if concepts_str and concepts_str != "-":
            return [c.strip() for c in concepts_str.split(",") if c.strip()]
    return []


def _extract_industry(inner: dict, key: str) -> str:
    """从 push2 响应中提取指定字段的行业/板块字符串。"""
    raw = inner.get(key)
    if isinstance(raw, str) and raw.strip() not in ("", "-"):
        return raw.strip()
    return ""


def fetch_industry_and_concepts(code: str) -> dict[str, Any] | None:
    """获取一只证券的行业分类和概念板块归属。

    Args:
        code: 6 位证券代码

    Returns:
        {...} 详见函数内结果字典定义；None: API 异常或解析失败
    """
    inner = _make_push2_request(code)
    if inner is None:
        return None

    result: dict[str, Any] = {
        "code": code.strip(),
        "industry": _extract_industry(inner, "f127"),
        "industry_id": _extract_industry(inner, "f198"),
        "concepts": _extract_concept_list(inner),
        "concept_ids": [],
    }

    logger.debug("东方财富行业/概念 [%s]: 行业=%s, 概念=%d个",
                 code, result["industry"] or "无", len(result["concepts"]))
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
