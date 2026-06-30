"""A 股交易时段判断模块。

从 cache.py 提取，提供多层判断机制（config → API → fallback）来确定
A 股市场当前是否在交易时段。

用法::

    from src.python.market_hours import is_market_open

    if is_market_open():
        # 盘中，使用短 TTL
    else:
        # 盘后，使用长 TTL
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("invest")

# ── A 股交易时段（内置默认值，用于 fallback） ───────────
# 早盘 09:30 (570min) – 11:30 (690min)
# 午盘 13:00 (780min) – 15:00 (900min)
_MORNING_START = 570   # 09:30
_MORNING_END = 690     # 11:30
_AFTERNOON_START = 780  # 13:00
_AFTERNOON_END = 900    # 15:00
_DEFAULT_START = "09:30"
_DEFAULT_END = "15:00"

# ── 官方交易状态缓存 ───────────────────────────────────
_CACHE_KEY_MARKET_HOURS = "market_hours"
_PUSH2_BASE = "https://push2.eastmoney.com/api/qt/stock/get"
_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}


def _parse_time_to_minutes(time_str: str) -> int | None:
    """将 ``HH:MM`` 字符串转换为当日分钟数。

    Args:
        time_str: 如 ``"09:30"``、``"15:00"``

    Returns:
        当日分钟数（如 570），解析失败返回 None
    """
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def _fetch_trading_status_from_official() -> int | None:
    """从东方财富 push2 API 获取上证指数实时交易状态。

    f100 字段含义：
        - 0 = 未开盘（盘前）
        - 1 = 交易中
        - 2 = 已收盘（盘后）
        - 3 = 午间休市

    Returns:
        交易状态码（0-3），API 失败返回 None
    """
    from src.python.http_client import make_http_client


    params = {"secid": "1.000001", "fields": "f100,f169"}
    try:
        with make_http_client(timeout=5.0) as client:
            resp = client.get(_PUSH2_BASE, params=params, headers=_EM_HEADERS)
            data = resp.json()
            inner = data.get("data")
            if inner and isinstance(inner, dict):
                status = inner.get("f100")
                if status is not None:
                    return int(status)
    except Exception as e:
        logger.debug("获取东方财富交易状态失败: %s", e)
    return None


def _is_market_open_config(current_min: int) -> bool | None:
    """第 1 层：从 config.json 手动覆盖判断市场是否开盘。

    Returns:
        True 开市 / False 闭市 / None 未配置，继续下一层
    """
    from src.python.config import get_config

    config = get_config()
    mh_config = config.get("market_hours") or {}
    start_str = mh_config.get("start")
    end_str = mh_config.get("end")
    if not start_str or not end_str:
        return None
    start_min = _parse_time_to_minutes(start_str)
    end_min = _parse_time_to_minutes(end_str)
    if start_min is None or end_min is None:
        return None
    now = datetime.now(timezone(timedelta(hours=8)))
    if now.weekday() >= 5:
        return False
    in_range = start_min <= current_min <= end_min
    lunch = _MORNING_END < current_min < _AFTERNOON_START
    result = in_range and not lunch
    logger.debug("市场时段(配置 %s-%s): %s", start_str, end_str, result)
    return result


def _is_market_open_official(current_min: int) -> bool | None:
    """第 2 层：从东方财富 push2 API 实时交易状态判断。

    Returns:
        True 开市 / False 收盘 / None API 不可用
    """
    from src.python.cache import get, set
    from src.python.config import get_config

    config = get_config()
    mh_config = config.get("market_hours") or {}
    use_official = mh_config.get("official_source", True)
    if not use_official:
        return None
    now = datetime.now(timezone(timedelta(hours=8)))
    if now.weekday() >= 5:
        return None  # 周末 return None 让 fallback 处理
    official_ttl = 60 if _MORNING_START <= current_min <= _AFTERNOON_END else 86400 * 7
    cached = get(_CACHE_KEY_MARKET_HOURS, official_ttl)
    if cached is not None and isinstance(cached, dict):
        status = cached.get("status")
        logger.debug("市场时段(API缓存): status=%s", status)
        if status == 1:
            return True
        if status == 2:
            return False
    status = _fetch_trading_status_from_official()
    if status is not None:
        set(_CACHE_KEY_MARKET_HOURS, {"status": status})
        logger.debug("市场时段(API实时): status=%s", status)
        if status == 1:
            return True
        if status == 2:
            return False
    return None


def _is_market_open_fallback(current_min: int) -> bool:
    """第 3 层：根据内置默认值判断市场是否开盘。

    北京时区工作日 09:30–11:30 + 13:00–15:00，自动排除午餐和周末。
    """
    now = datetime.now(timezone(timedelta(hours=8)))
    if now.weekday() >= 5:
        return False
    in_morning = _MORNING_START <= current_min <= _MORNING_END
    in_afternoon = _AFTERNOON_START <= current_min <= _AFTERNOON_END
    return in_morning or in_afternoon


def is_market_open() -> bool:
    """多渠道判断 A 股市场当前是否在交易时段。

    优先级：
    1. **config.json** ``market_hours.start`` / ``market_hours.end`` 手动覆盖
    2. **东方财富 push2 API** 实时交易状态（缓存 TTL：盘中 60s，盘后 7 天）
    3. **内置默认值**（北京时区工作日 09:30–11:30 + 13:00–15:00，自动排除午餐）

    非交易时段返回 ``False``，让 price / index 缓存使用长 TTL 保持收盘价。

    Returns:
        是否在交易时段内
    """
    try:
        now = datetime.now(timezone(timedelta(hours=8)))
        current_min = now.hour * 60 + now.minute

        # 第 1 层：config.json 手动覆盖
        result = _is_market_open_config(current_min)
        if result is not None:
            return result

        # 第 2 层：官方 API 实时状态
        result = _is_market_open_official(current_min)
        if result is not None:
            return result

        # 第 3 层：内置默认值
        return _is_market_open_fallback(current_min)

    except Exception:
        return False  # 异常时保守处理：视为非交易时段
