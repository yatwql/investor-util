"""交易日历原语（节假日感知）。

统一的 A 股交易日判定与「距今多少个交易日」计算，供各层复用——
数据新鲜度、持仓时长、数据缺口、因子停更等判定均须以**交易日**为基准，
不得用自然日差（自然日差在周末与长假会被放大，据此判定会误报延迟/停更）。

本模块是交易日判定与计数的唯一实现，落在 `core/` 以便 `fetcher/`、`analysis/`、
`report/` 各层共用且不产生跨层反向依赖。

交易日历来源为 akshare `tool_trade_date_hist_sina()`，经 `cache` 统一缓存
（缓存键 `trading_calendar`，组 `calendar`）；获取失败时全部判定回退为
「排除周六日」的近似口径，保证降级可用而非报错。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from src.python import cache

logger = logging.getLogger("invest")

# 缓存键 — 组 `calendar` 注册于 core/registry.py（统一缓存管理）
_TRADING_CALENDAR_CACHE_KEY = "trading_calendar"

# akshare 交易日历调用串行锁：tool_trade_date_hist_sina() 内部使用
# py_mini_racer(V8) 解密新浪接口，而 V8 初始化不是线程安全的——多线程并发首次
# 初始化会触发 [FATAL:partition_address_space.cc(243)] Check failed:
# !IsConfigurablePoolInitialized() 直接 abort 整个进程（try/except 无法捕获）。
# 菜单 2 并行价格抓取 / 报告生成的并发路径可能多线程同时命中本缓存未命中分支，
# 必须在此串行化（V8 顺序初始化是安全的）。
_TRADING_CALENDAR_AKSHARE_LOCK = threading.Lock()

__all__ = [
    "_count_trading_days_back",
    "_get_trading_calendar",
    "_is_trading_day",
    "count_trading_days_elapsed",
    "get_last_trading_day",
    "get_prev_trading_day",
]


def _get_trading_calendar() -> set[str]:
    """获取 A 股交易日历（YYYY-MM-DD 字符串集合）。

    通过 akshare 获取全年交易日数据并缓存。若获取失败，返回空集合，
    由调用方（get_last_trading_day）回退到简易周度判断。

    线程安全：缓存未命中分支用模块级锁串行化 akshare(V8) 调用（见
    _TRADING_CALENDAR_AKSHARE_LOCK），避免并发初始化 py_mini_racer 触发
    进程级 FATAL 崩溃。

    Returns:
        交易日日期字符串集合
    """
    cached = cache.get(_TRADING_CALENDAR_CACHE_KEY, cache.get_ttl("calendar"))
    if cached is not None and isinstance(cached, list):
        return set(cached)

    with _TRADING_CALENDAR_AKSHARE_LOCK:
        # 双重检查：等待锁期间其他线程可能已写入缓存
        cached = cache.get(_TRADING_CALENDAR_CACHE_KEY, cache.get_ttl("calendar"))
        if cached is not None and isinstance(cached, list):
            return set(cached)
        try:
            import akshare as ak

            df = ak.tool_trade_date_hist_sina()
            dates: set[str] = set(df["trade_date"].dropna().astype(str).tolist())
            if dates:
                cache.set(_TRADING_CALENDAR_CACHE_KEY, sorted(dates))
                logger.info("交易日历已更新（%d 个交易日）", len(dates))
                return dates
        except Exception as exc:
            logger.warning("获取交易日历失败: %s，使用简易节假日判断回退", exc)

        return set()


def _is_trading_day(date: datetime) -> bool:
    """判断给定日期是否为 A 股交易日。

    优先使用 akshare 日历，失败时回退到简易判断（非周六日即为交易日）。

    Args:
        date: 待判断的日期

    Returns:
        True 表示为交易日
    """
    calendar = _get_trading_calendar()
    date_str = date.strftime("%Y-%m-%d")
    if calendar:
        return date_str in calendar
    # 回退：仅排除周六日
    return date.weekday() < 5


def get_last_trading_day() -> str:
    """获取最近一个交易日（YYYY-MM-DD），含节假日感知。

    判断逻辑：
    1. 使用 akshare 交易日历判定节假日（端午、中秋、国庆等）
    2. A 股盘前（< 9:30）退回上一交易日
    3. 盘中/盘后（≥ 9:30）且当天为交易日 → 返回当天
    4. 非交易日则向前查找最近一个交易日

    Returns:
        YYYY-MM-DD 格式的交易日字符串
    """
    now = datetime.now(timezone(timedelta(hours=8)))
    # 若盘前（< 9:30），基准日设为昨天
    check = now - timedelta(days=1) if now.hour < 9 or now.hour == 9 and now.minute < 30 else now

    # 从基准日起向前查找最近一个交易日
    for _ in range(14):  # 最多回溯 14 天（覆盖长假）
        if _is_trading_day(check):
            return check.strftime("%Y-%m-%d")
        check -= timedelta(days=1)

    # 极端回退（不应到达）
    return now.strftime("%Y-%m-%d")


def get_prev_trading_day(trading_day: str = "") -> str:
    """获取指定交易日的前一个交易日，含节假日感知。

    使用 akshare 交易日历向前查找，找不到时回退到简易周度判断。

    Args:
        trading_day: YYYY-MM-DD 格式的交易日，默认取最近交易日

    Returns:
        前一个交易日 YYYY-MM-DD
    """
    if not trading_day:
        trading_day = get_last_trading_day()
    try:
        dt = datetime.strptime(trading_day, "%Y-%m-%d")
        # 从 trading_day - 1 起向前查找最近一个交易日
        check = dt - timedelta(days=1)
        for _ in range(14):
            if _is_trading_day(check):
                return check.strftime("%Y-%m-%d")
            check -= timedelta(days=1)
        return (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


def count_trading_days_elapsed(start: str, end: str) -> int | None:
    """统计 start 到 end 之间经过的交易日数（不含 start，含 end）。

    用于「距今多少个交易日」类判定（持仓时长、数据缺口、因子停更等），
    替代自然日差值——自然日差在周末与长假会被放大（如国庆假期前后相邻的
    两个交易日相差 10 个自然日，交易日差仅 1），据此判定会误报延迟/停更。

    例：start=周五、end=下周一 → 返回 1（中间经过 1 个交易日）。

    交易日历可用时按日历精确计数；不可用时回退为「排除周六日」的近似计数，
    与 `_is_trading_day` 的回退口径一致。

    Args:
        start: 起始日期（YYYY-MM-DD）
        end: 结束日期（YYYY-MM-DD）

    Returns:
        经过的交易日数；start >= end 时返回 0；日期格式非法返回 None
    """
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    if start_dt >= end_dt:
        return 0

    calendar = _get_trading_calendar()
    if calendar:
        # 日历为 YYYY-MM-DD 字符串集合，直接按字典序区间计数（半开区间 (start, end]）
        return sum(1 for d in calendar if start < d <= end)

    # 回退：仅排除周六日
    span = (end_dt - start_dt).days
    return sum(1 for i in range(1, span + 1) if (start_dt + timedelta(days=i)).weekday() < 5)


def _count_trading_days_back(trading_day: str, nav_date: str) -> int | None:
    """计算 nav_date 比 trading_day 早多少个交易日。

    用于场外基金净值日期的 T-N 判定，替代简单的自然日差值。
    例如：T=周一，nav_date=上周四 → 返回 2（上周五为 T-1）。

    Args:
        trading_day: 基准交易日（YYYY-MM-DD）
        nav_date: 目标日期（YYYY-MM-DD）

    Returns:
        交易日数差（T-1 返回 1，T-2 返回 2...），
        nav_date >= trading_day 时返回 None，
        超出 60 个自然日查找范围时返回 None
    """
    try:
        td_dt = datetime.strptime(trading_day, "%Y-%m-%d")
        nav_dt = datetime.strptime(nav_date, "%Y-%m-%d")
        if nav_dt >= td_dt:
            return None
        check = td_dt - timedelta(days=1)
        count = 0
        for _ in range(60):
            if _is_trading_day(check):
                count += 1
                if check.strftime("%Y-%m-%d") == nav_date:
                    return count
            check -= timedelta(days=1)
        return None
    except (ValueError, TypeError):
        return None
