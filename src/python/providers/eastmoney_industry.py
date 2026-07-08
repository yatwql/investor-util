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
import random
import time
from typing import Any

import httpx

from src.python.code_utils import get_push2_secid
from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_PUSH2_BASE = "https://push2.eastmoney.com/api/qt/stock/get"
_TIMEOUT = 5.0
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}
# 最大重试次数（总请求数 = _MAX_RETRIES + 1）
# fund_style 等降级场景可容忍偶尔失败，减少重试加快 fallback
_MAX_RETRIES = 1

# ── 熔断器（含冷却恢复） ────────────────────────────────────
# 连续 _PUSH2_CIRCUIT_THRESHOLD 次失败后熔断，
# 冷却 _PUSH2_COOLDOWN_SECS 秒后自动放行一次试探请求。
_PUSH2_CIRCUIT_OPEN = False     # 是否已熔断
_PUSH2_CIRCUIT_OPEN_TIME = 0.0  # 熔断开启时的时间戳
_PUSH2_FAILURE_COUNT = 0        # 连续失败计数
_PUSH2_CIRCUIT_THRESHOLD = 3    # 连续失败 N 次后熔断
_PUSH2_COOLDOWN_SECS = 300      # 冷却期（秒）

# 查询字段（行业分类 + 扩展行情，供 fund_style 等模块使用）
#   f9=动态市盈率(PE), f20=总市值, f23=市净率(PB)
#   f57=代码, f58=名称, f127=行业, f128=地域, f129=概念, f198=行业BK
_FIELDS = "f57,f58,f127,f128,f129,f198,f9,f20,f23"


# 会话级内存缓存 — 同一代码在会话内不重复 HTTP 请求（C4 约束）
_ext_memo: dict[str, dict[str, Any] | None] = {}


def _ext_memo_clear() -> None:
    """测试用：清空会话级内存缓存。"""
    _ext_memo.clear()


def _secid(code: str) -> str:
    """根据代码生成 secid 参数（委托至 code_utils.get_push2_secid）。"""
    return get_push2_secid(code)


def _circuit_breaker_record_failure() -> None:
    """累加连续失败计数，达到阈值时打开熔断并记录时间戳。"""
    global _PUSH2_FAILURE_COUNT, _PUSH2_CIRCUIT_OPEN, _PUSH2_CIRCUIT_OPEN_TIME
    _PUSH2_FAILURE_COUNT += 1
    if _PUSH2_FAILURE_COUNT >= _PUSH2_CIRCUIT_THRESHOLD:
        _PUSH2_CIRCUIT_OPEN = True
        _PUSH2_CIRCUIT_OPEN_TIME = time.time()
        logger.warning("东方财富 push2 连续 %d 次失败，触发熔断，本运行周期跳过",
                        _PUSH2_CIRCUIT_THRESHOLD)


def _circuit_breaker_reset() -> None:
    """请求成功时重置熔断计数。"""
    global _PUSH2_FAILURE_COUNT, _PUSH2_CIRCUIT_OPEN
    _PUSH2_FAILURE_COUNT = 0
    _PUSH2_CIRCUIT_OPEN = False


def _make_push2_request(code: str, retries: int = _MAX_RETRIES) -> dict | None:
    """执行 push2 行业/概念 API 请求，返回 data 内层字典或 None。

    支持自动重试：对连接断开等瞬态错误，使用指数退避 + 随机抖动重试。
    支持熔断：连续 `_PUSH2_CIRCUIT_THRESHOLD` 次失败后本进程周期跳过。

    Args:
        code: 6 位证券代码
        retries: 失败重试次数（默认 3 次，总请求数 = retries + 1）

    Returns:
        data 内层字典；全部失败返回 None
    """
    global _PUSH2_CIRCUIT_OPEN
    if _PUSH2_CIRCUIT_OPEN:
        # 冷却期满 → 放行一次试探请求
        if time.time() - _PUSH2_CIRCUIT_OPEN_TIME >= _PUSH2_COOLDOWN_SECS:
            _PUSH2_CIRCUIT_OPEN = False
            _PUSH2_FAILURE_COUNT = 0
            logger.info("东方财富 push2 冷却期满，允许试探请求 [%s]", code)
        else:
            logger.debug("东方财富 push2 熔断已开启，跳过 [%s]", code)
            return None

    params = {
        "secid": _secid(code),
        "fields": _FIELDS,
    }
    logger.debug("东方财富 push2 请求: %s", code)

    for attempt in range(retries + 1):
        try:
            with make_http_client(timeout=_TIMEOUT) as client:
                resp = client.get(_PUSH2_BASE, params=params, headers=_HEADERS)
                text = resp.text
        except (httpx.TimeoutException, httpx.RequestError) as e:
            if attempt < retries:
                delay = (0.5 * (2 ** attempt)) + random.uniform(0, 0.3)
                logger.debug("东方财富 push2 请求失败 [%s]（第 %d 次重试，%.1fs 后）: %s",
                             code, attempt + 1, delay, e)
                time.sleep(delay)
                continue
            logger.warning("东方财富 push2 请求失败 [%s]: %s", code, e)
            _circuit_breaker_record_failure()
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

        _circuit_breaker_reset()
        return inner

    return None  # 所有重试耗尽（理论上不会执行到）


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

    会话级内存复用（C4）：同一代码在同一会话内仅首次发起 HTTP 请求，
    后续调用直接返回缓存结果，避免重复网络/文件 I/O。

    Args:
        code: 6 位证券代码

    Returns:
        {...} 详见函数内结果字典定义；None: API 异常或解析失败
    """
    if code in _ext_memo:
        return _ext_memo[code]

    inner = _make_push2_request(code)
    if inner is None:
        _ext_memo[code] = None
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
    _ext_memo[code] = result
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
