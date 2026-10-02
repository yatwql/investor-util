"""东方财富 API — 获取场外基金最新净值。

主链路: api.fund.eastmoney.com
备用链路: fundf10.eastmoney.com（天天基金）
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

import httpx

from src.python.core.code_utils import get_index_exchange_prefix, is_index_code, is_us_index_code
from src.python.core.http_client import make_http_client
from src.python.core.retry import STRATEGY_EXPONENTIAL, TRANSIENT_EXCEPTIONS, RetryPolicy, retry_transient
from src.python.core.throttle import RateLimiter  # 间隔节流唯一原语（数据/调度/LLM 三层共用）
from src.python.providers._utils import safe_float as _safe_float

logger = logging.getLogger("invest")

_FUND_API_URL = "https://api.fund.eastmoney.com/f10/lsjz"

#: 历史净值分页请求最小间隔（秒）——间隔节流走 core/throttle 唯一原语
_PAGER_LIMIT_KEY = "eastmoney_fund_pager"
_PAGER_MIN_INTERVAL = 0.3
_pager_limiter: RateLimiter | None = None
_pager_limiter_lock = threading.Lock()


def _get_pager_limiter() -> RateLimiter:
    """分页限速器（惰性单例，页间间隔统一走 RateLimiter 表达）。"""
    global _pager_limiter
    if _pager_limiter is None:
        with _pager_limiter_lock:
            if _pager_limiter is None:
                _pager_limiter = RateLimiter({_PAGER_LIMIT_KEY: _PAGER_MIN_INTERVAL})
    return _pager_limiter


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


def fetch_fund_nav_history(code: str) -> list[dict]:
    """获取场外基金历史净值（备用链路）。

    通过东方财富基金历史净值 API 分页获取全量历史净值数据，
    与 tiantian.fetch_fund_nav_history() 返回格式兼容。

    API 单页上限为 20 条（实测 pageSize 参数超过 200 返回 null，
    且无论 pageSize 多大都只返回 20 条）。使用 pageSize=20 逐页
    遍历，页间延时 0.3s 防限流，最多 10 页（200 条 ≈ 10 个月）。
    首次获取后缓存积累，后续增量请求只需第一页。

    Args:
        code: 6 位基金代码

    Returns:
        list[dict]: [{date, nav, acc_nav}, ...]
        按日期升序排列。API 失败或空数据返回空列表。
    """
    page_size = 20
    max_pages = 10
    all_records: list[dict] = []
    page_index = 1

    while page_index <= max_pages:
        params: dict[str, Any] = {
            "callback": "jQuery",
            "fundCode": code.strip(),
            "pageIndex": page_index,
            "pageSize": page_size,
        }

        try:
            with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(_FUND_API_URL, params=params, headers=_HEADERS)
                resp.raise_for_status()
                text = resp.text
        except httpx.HTTPStatusError:
            logger.warning("[eastmoney] 历史净值 API HTTP 错误（第%d页）: %s", page_index, code)
            if all_records:
                break
            return []
        except httpx.RequestError:
            logger.warning("[eastmoney] 历史净值 API 请求失败（第%d页）: %s", page_index, code)
            if all_records:
                break  # 已有数据时容忍单页失败
            return []

        json_str = _strip_jsonp(text)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("[eastmoney] 历史净值 JSON 解析失败（第%d页）: %s", page_index, code)
            if all_records:
                break
            return []

        records = (data.get("Data", {}) or {}).get("LSJZList", [])
        if not records:
            break  # 无更多数据

        all_records.extend(records)

        # 检查是否还有更多页
        total_count = data.get("TotalCount", 0) or 0
        if page_index * page_size >= total_count:
            break

        page_index += 1
        _get_pager_limiter().acquire(_PAGER_LIMIT_KEY)  # 页间最小间隔（限流防触顶）

    if not all_records:
        logger.warning("[eastmoney] 无历史净值数据: %s", code)
        return []

    result: list[dict] = []
    for r in all_records:
        date_str = (r.get("FSRQ") or "").strip()
        nav = _safe_float(r.get("DWJZ", "0"))
        acc_nav = _safe_float(r.get("LJJZ", "0"))
        if not date_str or (nav <= 0 and acc_nav <= 0):
            continue
        result.append(
            {
                "date": date_str,
                "nav": nav,
                "acc_nav": acc_nav,
            }
        )

    # API 返回最新在前，按日期升序排列
    result.sort(key=lambda x: x["date"])
    logger.info("[eastmoney] 基金 %s 历史净值: %d 条（%d 页）", code, len(result), page_index)
    return result


# ── 指数历史日 K（push2his；免 key 的独立厂商备源）────────────

_INDEX_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
#: 指数取数重试策略：总尝试 3 次、指数退避（与腾讯 K 线同一口径）；历史链无链级重试，
#: 故重试必须落在 provider 内。
_INDEX_RETRY_POLICY = RetryPolicy(attempts=3, strategy=STRATEGY_EXPONENTIAL, base_backoff=0.5, factor=2.0, jitter=0.2)
#: 无交易所前缀的指数代码 → 东方财富市场号（0=深市 / 1=沪市）：399/932 系深市，其余按沪市
_INDEX_BARE_MARKET: tuple[tuple[tuple[str, ...], str], ...] = ((("399", "932"), "0"),)


def _index_secid(code: str) -> str:
    """指数代码 → 东方财富 secid（``1.000300`` / ``0.399001``）；无法映射返回空串。

    非指数/美股指数一律返回空串（``is_index_code`` 门禁防止把 A 股个股代码
    映射成 ``1.6xxxxx`` 后误取个股日 K）。
    """
    raw = (code or "").strip().lower()
    if not is_index_code(raw) or is_us_index_code(raw):
        return ""
    prefix = get_index_exchange_prefix(raw)
    digits = raw[len(prefix) :] if prefix else raw
    if not digits.isdigit() or len(digits) != 6:
        return ""
    if prefix == "sh":
        market = "1"
    elif prefix == "sz":
        market = "0"
    else:
        market = next((m for heads, m in _INDEX_BARE_MARKET if digits.startswith(heads)), "1")
    return f"{market}.{digits}"


def _fetch_index_kline_json(secid: str, days: int) -> dict[str, Any] | None:
    """带传输级退避重试的 push2his 指数 K 线 JSON 拉取；重试耗尽/解析失败返回 None。"""
    params: dict[str, Any] = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": "101",  # 日线
        "fqt": "1",  # 前复权
        "beg": "0",
        "end": "20500101",
        "lmt": days,
    }

    def _attempt() -> dict:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(_INDEX_KLINE_URL, params=params, headers=_HEADERS)
            resp.raise_for_status()
            return resp.json()

    def _on_transient_retry(failed_attempt: int, delay: float, exc: BaseException | None) -> None:
        logger.warning(
            "[eastmoney] 指数 K 线 %s 传输级失败（%s），%.1fs 后同源重试 %d/%d",
            secid,
            type(exc).__name__ if exc is not None else "超时",
            delay,
            failed_attempt,
            _INDEX_RETRY_POLICY.attempts - 1,
        )

    try:
        return retry_transient(_attempt, policy=_INDEX_RETRY_POLICY, on_retry=_on_transient_retry)
    except (*TRANSIENT_EXCEPTIONS, httpx.HTTPStatusError, ValueError) as e:
        logger.warning("[eastmoney] 指数 K 线获取失败 %s（重试耗尽）: %s", secid, e)
        return None


def fetch_index_kline(code: str, days: int = 30, start_from: str | None = None) -> list[dict]:
    """指数历史日 K（前复权），形态对齐 ``providers/tencent.fetch_index_kline``。

    东方财富 push2his 日线接口：免 key、独立厂商，与腾讯/新浪故障域隔离，是
    ``history_index`` 链的独立备源（新浪指数端点实测不可用）。

    上游按请求窗口返回，``lmt`` 只是条数提示，故再由 ``days`` 截尾。美股指数
    （``gb_*``）无 A 股 secid 口径，返回空列表由链路继续降级。

    Args:
        code: 指数代码，如 ``sh000300`` / ``sz399001``
        days: 获取天数（默认 30，钳位 5~2000，与腾讯/新浪口径一致）
        start_from: 起始日期（YYYY-MM-DD），增量获取只保留其后数据

    Returns:
        ``[{date, open, close, high, low, volume}, ...]`` 按日期升序；失败返回空列表。
    """
    if is_us_index_code(code):
        return []
    secid = _index_secid(code)
    if not secid:
        logger.debug("[eastmoney] 跳过无法映射的指数代码: %s", code)
        return []
    days = min(max(days, 5), 2000)
    logger.debug("[eastmoney] 指数 K 线请求: %s, days=%d", secid, days)
    data = _fetch_index_kline_json(secid, days)
    klines = ((data or {}).get("data") or {}).get("klines") or []
    if not isinstance(klines, list):
        return []

    bars: list[dict] = []
    for row in klines:
        parts = str(row).split(",")
        if len(parts) < 6:
            continue
        date_str = parts[0].strip()
        close = _safe_float(parts[2])
        if not date_str or close <= 0:
            continue  # 跳过无效/停牌数据
        bars.append(
            {
                "date": date_str,
                "open": _safe_float(parts[1]),
                "close": close,
                "high": _safe_float(parts[3]),
                "low": _safe_float(parts[4]),
                "volume": _safe_float(parts[5]),
            }
        )
    bars.sort(key=lambda b: b["date"])
    if start_from:
        bars = [b for b in bars if b["date"] > str(start_from)]
    logger.info("[eastmoney] 指数 %s 历史日 K: %d 条", code, len(bars))
    return bars[-days:]
