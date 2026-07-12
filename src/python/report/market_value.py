"""市值核算模块 — 报告第 2 页。

15 列明细表，含分账户小计和总计。盈亏数值正数红色、负数绿色。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.python import cache
from src.python.code_utils import (
    is_a_share_code,
    is_etf_by_name,
    is_exchange_fund_code,
    is_offsite_fund,
    is_qdii_extended,
)
from src.python.fetcher.price import fetch_market_data
from src.python.market_hours import is_market_open as _mh_is_market_open
from src.python.provider_registry import FetchStrategy, get_registry
from src.python.market_hours import is_midday_break as _mh_is_midday_break
from src.python.models import Holding

logger = logging.getLogger("invest")

# 占位符 — 非 QDII 或无参考净值时使用
_FUND_PREMIUM_PLACEHOLDER = "--"

__all__ = [
    "DetailRow",
    "_FUND_PREMIUM_PLACEHOLDER",
    "_compute_premium",
    "_compute_detail_row",
    "_count_trading_days_back",
    "_determine_price_type",
    "_generate_details",
    "_get_trading_calendar",
    "_is_trading_day",
    "classify_holdings",
    "get_last_trading_day",
    "get_prev_trading_day",
    "price_update_status",
]


def _compute_premium(price: float, nav: float, name: str) -> str:
    """计算溢价率（百分比字符串），仅 QDII 基金显示。

    Args:
        price: 当前价格/净值
        nav:   参考净值（昨收 / 最近公布净值）
        name:  资产名称（用于判断是否 QDII）

    Returns:
        格式如 "+1.23%"、"-0.56%"，非 QDII 或无参考净值时返回 "--"。
    """
    if nav <= 0:
        return _FUND_PREMIUM_PLACEHOLDER
    if not is_qdii_extended(name):
        return _FUND_PREMIUM_PLACEHOLDER
    pct = (price - nav) / nav * 100
    return f"{pct:+.2f}%"


@dataclass
class DetailRow:
    """单条持仓估值明细（15 列对应字段）。"""
    account: str = ""
    name: str = ""
    code: str = ""
    price: float = 0.0
    nav_date: str = ""
    yesterday_close: float = 0.0
    price_type: str = ""
    premium: str = _FUND_PREMIUM_PLACEHOLDER
    shares: float = 0.0
    market_value: float = 0.0
    cost: float = 0.0
    profit: float = 0.0
    profit_rate: float | None = None
    today_profit: float = 0.0
    source: str = ""
    source_api: str = ""


def classify_holdings(holdings: list[Holding]) -> dict[str, list]:
    """按类型分类持仓。

    判断逻辑（按优先级）:
        1. 名称含 QDII → QDII
        2. 账户名为场外渠道（含基金/支付宝/微信/银行等）→ 国内场外
        3. 名称含 ETF 或代码 5/1 开头 → 场内ETF
        4. 代码 6/0/3 开头 → 场内股票
        5. 其余 → 国内场外

    用账户名做第一道区分是因为：
    - 6 位代码可能既是股票/ETF 也是场外基金（如 002943、530021）
    - 证券账户里的 5xxxxx 是 ETF，基金账户里的 5xxxxx 是场外基金
    先判断账户属性可以避免代码重叠导致的误分类。

    Returns:
        {type: [Holding, ...]}，type 取值:
        "场内股票", "场内ETF", "国内场外", "QDII"
    """
    categories: dict[str, list] = {
        "场内股票": [],
        "场内ETF": [],
        "国内场外": [],
        "QDII": [],
    }

    for h in holdings:
        code = h.code.strip()
        name = h.name.strip()
        account = h.account.strip()

        # 1) QDII（含显式+隐式海外基金识别）
        if is_qdii_extended(name):
            categories["QDII"].append(h)
        # 2) 场外渠道 → 国内场外（基金账户不会持有场内品种）
        elif is_offsite_fund(account):
            categories["国内场外"].append(h)
        # 3) 场内 ETF（名称含 ETF，或代码 5/1 开头的场内品种）
        elif is_etf_by_name(name) or is_exchange_fund_code(code):
            categories["场内ETF"].append(h)
        # 4) A 股股票
        elif is_a_share_code(code):
            categories["场内股票"].append(h)
        # 5) 其余归入场外
        else:
            categories["国内场外"].append(h)

    return categories


def price_update_status(details: list[DetailRow], trading_day: str) -> tuple[int, int, bool]:
    """检查今日价格更新状态。

    判断逻辑：
    - 场内资产（tencent）：nav_date == trading_day 视为已更新（本日已更新收市价格）
    - QDII（eastmoney + QDII）：nav_date == trading_day 或 nav_date == prev_trading_day
      视为已更新（本日已更新官方净值 T-1）
    - 国内场外（eastmoney + 非 QDII）：nav_date == trading_day 视为已更新
      （本日已更新官方净值 T）

    Args:
        details: 明细行列表
        trading_day: 最近交易日 YYYY-MM-DD

    Returns:
        (已更新数量, 总数, 是否全部更新)
    """
    total = len(details)
    updated = 0
    prev_td = get_prev_trading_day(trading_day)
    for d in details:
        if d.source_api == "tencent":
            # 场内资产：需已收市（非交易时段、非午间休市）且净值日期等于交易日
            # 才视为已更新收市价；盘中/午休只有实时价，不算已更新
            if not is_market_open() and not is_midday_break() and d.nav_date == trading_day:
                updated += 1
        elif d.source_api == "eastmoney" and is_qdii_extended(d.name):
            # QDII：净值日期等于交易日(T)或前一个交易日(T-1)即视为已更新
            if d.nav_date == trading_day or (prev_td and d.nav_date == prev_td):
                updated += 1
        elif d.source_api == "eastmoney" and d.nav_date == trading_day:
            # 国内场外：仅净值日期等于交易日(T)视为已更新
            updated += 1
    return updated, total, updated >= total


# ── A 股交易时段判断（委派 market_hours 实现） ──────────


def is_market_open() -> bool:
    """委派 market_hours.is_market_open（含 config/API/fallback 三层判断）。"""
    return _mh_is_market_open()


def is_midday_break() -> bool:
    """委派 market_hours.is_midday_break。"""
    return _mh_is_midday_break()


# ── 交易日历（节假日感知） ───────────────────────────────
_TRADING_CALENDAR_CACHE_KEY = "trading_calendar"


def _get_trading_calendar() -> set[str]:
    """获取 A 股交易日历（YYYY-MM-DD 字符串集合）。

    通过 akshare 获取全年交易日数据并缓存。若获取失败，返回空集合，
    由调用方（get_last_trading_day）回退到简易周度判断。

    Returns:
        交易日日期字符串集合
    """
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


def _determine_price_type(source_api: str, nav_date: str, trading_day: str) -> str:
    """判断取价方式。

    "T" 指"所属交易日"（而非自然日），由 get_last_trading_day() 确定。

    Tencent（场内股票/ETF）：
      - 交易时段 → "场内实时价"
      - 午间休市（11:30-13:00），nav_date == T → "场内午市收盘(T)"
      - 已收市，nav_date == T → "场内收盘价(T)"
      - 已收市，nav_date == T-1 → "场内收盘价(T-1)"

    East Money（场外基金）：
      - nav_date == T → "官方净值(T)"
      - nav_date == T-1 → "官方净值(T-1)"
      - nav_date 为 2~5 个交易日前 → "官方净值(T-N)"
      - nav_date 为 6 个交易日以上 → "官方净值(YYYY-MM-DD)"

    Args:
        source_api: "tencent"（场内）或 "eastmoney"（场外）
        nav_date: 净值日期（YYYY-MM-DD，可为空）
        trading_day: 所属交易日（YYYY-MM-DD）
        is_qdii: 是否为 QDII 基金

    Returns:
        取价方式标签字符串
    """
    if source_api == "tencent":
        if is_market_open():
            return "场内实时价"
        # 午间休市（11:30-13:00）：最新价为上午收盘，非全日收盘
        if nav_date == trading_day and is_midday_break():
            return "场内午市收盘(T)"
        # 已收市，用交易日作为 T
        if not nav_date:
            return "场内收盘价(--)"
        prev_td = get_prev_trading_day(trading_day)
        if nav_date == trading_day:
            return "场内收盘价(T)"
        elif prev_td and nav_date == prev_td:
            return "场内收盘价(T-1)"
        return f"场内收盘价({nav_date})"

    # 场外基金
    if not nav_date:
        return "官方净值(--)"

    prev_td = get_prev_trading_day(trading_day)
    if nav_date == trading_day:
        return "官方净值(T)"
    elif prev_td and nav_date == prev_td:
        return "官方净值(T-1)"

    # 未来净值日期（数据异常）→ 视为当日
    try:
        nav_dt = datetime.strptime(nav_date, "%Y-%m-%d")
        td_dt = datetime.strptime(trading_day, "%Y-%m-%d")
        if nav_dt > td_dt:
            return "官方净值(T)"
    except (ValueError, TypeError):
        pass

    # 以交易日（而非自然日）计算 N，正确处理周末/节假日跳越
    td_offset = _count_trading_days_back(trading_day, nav_date)
    if td_offset is not None and 2 <= td_offset <= 5:
        return f"官方净值(T-{td_offset})"
    elif td_offset is not None and td_offset > 5:
        return f"官方净值({nav_date})"
    return f"官方净值({nav_date})"


def _compute_detail_row(h: Holding, mkt: dict | None) -> DetailRow:
    """根据持仓对象和行情数据计算一条 DetailRow。"""
    if mkt is None:
        logger.warning("无法获取行情数据: %s (%s)", h.name, h.code)
        return DetailRow(
            account=h.account.strip(), name=h.name, code=h.code,
            price=0.0, nav_date="", yesterday_close=0.0,
            price_type="暂无行情", shares=h.shares,
            market_value=0.0, cost=round(h.cost_price * h.shares, 2),
            profit=0.0, profit_rate=None, today_profit=0.0,
            source="无数据", source_api="",
        )

    price = mkt.get("price", 0.0) or 0.0
    yclose = mkt.get("yesterday_close", 0.0) or 0.0
    nav_date = mkt.get("price_date", "")
    source = mkt.get("source", "--")
    source_api = mkt.get("source_api", "")
    price_type = _determine_price_type(source_api, nav_date, get_last_trading_day())

    cost = round(h.cost_price * h.shares, 2)
    mv = round(price * h.shares, 2)
    profit = round(mv - cost, 2)
    profit_rate = profit / cost if cost > 0 else None

        # 本日盈亏
    if source_api == "tencent":
        today_profit = round((price - yclose) * h.shares, 2)
    elif nav_date:
        trading_day = get_last_trading_day()
        today_profit = round((price - yclose) * h.shares, 2) if nav_date == trading_day else 0.0
    else:
        today_profit = 0.0

    # 溢价率 — (现价 - 参考净值) / 参考净值，仅 QDII 基金显示
    premium = _compute_premium(price, yclose, mkt.get("name", ""))

    return DetailRow(
        account=h.account.strip(), name=h.name, code=h.code,
        price=price, nav_date=nav_date, yesterday_close=yclose,
        price_type=price_type, premium=premium,
        shares=h.shares, market_value=mv, cost=cost,
        profit=profit, profit_rate=profit_rate, today_profit=today_profit,
        source=source, source_api=source_api,
    )


def _price_cache_key(code: str) -> str:
    """文件缓存键生成：价格数据的缓存键。"""
    return f"price_{code}"


def _generate_details(holdings: list[Holding], today_str: str = "") -> list[DetailRow]:
    """获取所有持仓的行情数据并生成明细行（策略感知：非交易时段/全链熔断时只读缓存）。"""
    details: list[DetailRow] = []
    today_str = today_str or datetime.now().strftime("%Y-%m-%d")

    # 1. 分类持仓，按类型决定获取策略
    categories = classify_holdings(holdings)
    registry = get_registry()
    market_open = is_market_open()

    # 类型 → (code_type, chain) 映射
    _TYPE_CONFIG: dict[str, tuple[str, list[str] | None]] = {
        "QDII": ("qdii", None),
        "场内股票": ("a_share", registry.get_chain("price")),
        "场内ETF": ("a_share", registry.get_chain("price")),
        "国内场外": ("a_share", registry.get_chain("price")),
    }

    # 2. 按策略分组：CACHE_ONLY 走缓存，LIVE_FETCH 走并行 HTTP
    cache_holdings: list[Holding] = []
    live_holdings: list[Holding] = []

    for cat_name, cat_holdings in categories.items():
        code_type, chain = _TYPE_CONFIG.get(cat_name, ("a_share", None))
        # 仅在有 chain 配置时启用策略选择（空 chain = 未注册 = 回退 LIVE_FETCH）
        if chain:
            strategy = registry.get_effective_strategy(code_type, chain, market_open)
            if strategy == FetchStrategy.CACHE_ONLY:
                cache_holdings.extend(cat_holdings)
                continue
        live_holdings.extend(cat_holdings)

    # 3. 缓存路径：session cache → file cache（零 HTTP）
    result_map: dict[tuple[str, str], dict | None] = {}
    for h in cache_holdings:
        mkt = registry.fetch_cached_only(h.code, "price", _price_cache_key)
        result_map[(h.account.strip(), h.code.strip())] = mkt

    # 3b. 缓存未命中 → 降级到 LIVE_FETCH（CACHE_ONLY 找不到缓存时逐条回退）
    #     典型场景：非交易时段首次运行/缓存已过期/新资产，CACHE_ONLY 不应让这些资产无数据
    cache_miss = [
        h for h in cache_holdings
        if result_map.get((h.account.strip(), h.code.strip())) is None
    ]
    if cache_miss:
        logger.info(
            "CACHE_ONLY 未命中 %d 个资产，降级到实时获取（原策略仅命中 %d 个）",
            len(cache_miss), len(cache_holdings) - len(cache_miss),
        )
        live_holdings.extend(cache_miss)

    # 4. 并行 HTTP 路径
    if live_holdings:
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_map = {}
            for h in live_holdings:
                future = executor.submit(fetch_market_data, h.code, h.name)
                future_map[future] = h
            for future in as_completed(future_map):
                h = future_map[future]
                try:
                    mkt = future.result()
                except Exception:
                    logger.warning("获取行情异常: %s (%s)", h.name, h.code, exc_info=True)
                    mkt = None
                result_map[(h.account.strip(), h.code.strip())] = mkt

    # 5. 按原始顺序构建 DetailRow
    for h in holdings:
        mkt = result_map.get((h.account.strip(), h.code.strip()))
        details.append(_compute_detail_row(h, mkt))

    # 6. 统计失败/成功数
    _ok_count = sum(1 for d in details if d.price > 0)
    _fail_count = len(details) - _ok_count
    if _fail_count > 0:
        logger.warning("市场行情获取：%d 成功，%d 失败（网络/非交易时段/限速），"
                       "报告部分数据将不可用", _ok_count, _fail_count)
        if _ok_count == 0:
            logger.warning("所有行情数据均获取失败，报告将显示占位文本 "
                           "'暂无行情' 而非实际数据")
    else:
        logger.info("市场行情获取：全部 %d 条成功", _ok_count)
    logger.info("市值核算明细数据生成完成，共 %d 条", len(details))
    return details
