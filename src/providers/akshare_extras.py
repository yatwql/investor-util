"""akshare 扩展数据源 — 盈利预测 + 行业资金流向 + 分红历史。

通过 akshare 获取以下数据：
  1. stock_profit_forecast_em — 机构盈利预测（全量股票，含预测 EPS）
  2. stock_sector_fund_flow_rank — 行业资金流向排名（含主力净流入）
  3. stock_history_dividend — 个股历史分红

各函数独立，使用指数变化/代码列表指纹 + TTL 双因子缓存失效策略。
"""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Any

import threading as _threading
import time as _time

from src.cache import get as cache_get, set as cache_set

logger = logging.getLogger("invest")

# ── 进程级内存 TTL 缓存（位于文件缓存之上） ──
_MEMO_CACHE: dict[str, tuple[Any, float]] = {}
_MEMO_LOCK = _threading.Lock()
_MEMO_TTL: dict[str, float] = {
    "profit_forecast": 300,   # 5 min — 指纹驱动，短期 memo 足够
    "sector_flow": 60,        # 1 min — 行业资金流向变化快
    "dividend": 600,          # 10 min — 分红数据会话内极少变化
}


def _memo_key(name: str, *args_hashes: str) -> str:
    return f"{name}:{':'.join(args_hashes)}" if args_hashes else name


def _memo_get(key: str) -> Any:
    with _MEMO_LOCK:
        entry = _MEMO_CACHE.get(key)
        if entry is not None:
            age = _time.time() - entry[1]
            prefix = key.split(":")[0] if ":" in key else key
            ttl = _MEMO_TTL.get(prefix, 60)
            if age < ttl:
                return entry[0]
    return None


def _memo_set(key: str, value: Any) -> None:
    with _MEMO_LOCK:
        _MEMO_CACHE[key] = (value, _time.time())


def _memo_clear() -> None:
    """测试用：清空全部内存缓存。"""
    with _MEMO_LOCK:
        _MEMO_CACHE.clear()


# ── 指数数据内存缓存（避免重复文件读取） ──
_INDEX_MEMO: dict[str, tuple[Any, float]] = {}
_INDEX_MEMO_TTL = 60  # 60 秒
_INDEX_MEMO_LOCK = _threading.Lock()

_CACHE_PROFIT_PREFIX = "profit_forecast_"
_CACHE_FLOW_PREFIX = "sector_flow_"
_CACHE_DIVIDEND_PREFIX = "dividend_"
_TTL = 86400               # 盈利预测：1天
_SECTOR_FLOW_TTL = 900     # 行业资金流向：15分钟
_DIVIDEND_TTL = 2592000    # 分红：1个月
_TIMEOUT = 15.0            # akshare 调用超时（秒）


def _compute_index_fingerprint() -> str:
    """计算市场指数数据的指纹，用于缓存键。

    从 fetcher 获取 A 股 + 美股指数数据 → MD5 前 12 位。
    指数变化时指纹改变 → 缓存自动失效，无需等待 TTL 过期。

    使用进程级内存缓存避免同一会话内重复文件读取。

    Returns:
        12 字符十六进制指纹；获取失败时返回空字符串（降级到纯 TTL 缓存）
    """
    try:
        from src.fetcher import fetch_indices, fetch_us_indices

        with _INDEX_MEMO_LOCK:
            cached = _INDEX_MEMO.get("indices")
            if cached is not None and _time.time() - cached[1] < _INDEX_MEMO_TTL:
                a_indices, us_indices = cached[0]
            else:
                a_indices = fetch_indices()
                us_indices = fetch_us_indices()
                _INDEX_MEMO["indices"] = ((a_indices, us_indices), _time.time())

        raw = json.dumps([a_indices, us_indices], ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()[:12]
    except Exception:
        logger.debug("指数指纹计算失败（降级到纯 TTL 缓存）")
        return ""


def _cache_key(prefix: str, fingerprint: str) -> str:
    """生成缓存键：有指纹时使用前缀+指纹，否则使用前缀+fallback。"""
    if fingerprint:
        return f"{prefix}{fingerprint}"
    return f"{prefix}nofp"


def _run_with_timeout(fn, timeout: float = _TIMEOUT):
    """在线程中执行函数，超时返回 None。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn)
        try:
            return fut.result(timeout=timeout)
        except TimeoutError:
            logger.warning("akshare 调用超时 (%.1fs)", timeout)
            fut.cancel()
            return None


def get_profit_forecast() -> dict[str, dict]:
    """获取全量机构盈利预测数据。

    调用 ak.stock_profit_forecast_em() 获取所有股票的
    研报覆盖、预测 EPS、机构评级等数据。

    缓存策略：指数指纹 + 1天 TTL 双因子失效。
      指数变化 → 指纹改变 → 缓存键不同 → 自动取新数据

    Returns:
        {code: {name, reports, eps_2025e, eps_2026e, buy, sell}, ...}
        失败时返回空 dict
    """
    # ── 内存缓存 ──
    _memo_key_str = _memo_key("profit_forecast")
    _memo_val = _memo_get(_memo_key_str)
    if _memo_val is not None:
        return _memo_val

    # ── 指纹 + 读文件缓存 ──
    _fp = _compute_index_fingerprint()
    _key = _cache_key(_CACHE_PROFIT_PREFIX, _fp)
    cached = cache_get(_key, _TTL)
    if cached is not None:
        _memo_set(_memo_key_str, cached)
        return cached

    # ── 取数 ──
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 模块未安装，跳过盈利预测")
        return {}

    def _fetch():
        return ak.stock_profit_forecast_em()

    df = _run_with_timeout(_fetch)
    if df is None:
        logger.warning("盈利预测获取失败: 超时")
        return {}
    if df.empty:
        logger.debug("盈利预测: 结果为空")
        return {}

    # ── 转为 code→data 字典 ──
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        code = str(row.get("代码", "")).strip()
        if not code:
            continue
        try:
            result[code] = {
                "name": str(row.get("名称", "") or "").strip(),
                "reports": int(row.get("研报数", 0) or 0),
                "eps_2025e": _safe_float(row.get("2025预测每股收益")),
                "eps_2026e": _safe_float(row.get("2026预测每股收益")),
                "eps_2027e": _safe_float(row.get("2027预测每股收益")),
                "buy": int(row.get("机构投资评级(近六个月)-买入", 0) or 0),
                "sell": int(row.get("机构投资评级(近六个月)-卖出", 0) or 0),
                "hold": int(row.get("机构投资评级(近六个月)-中性", 0) or 0),
            }
        except (ValueError, TypeError):
            continue

    logger.info("盈利预测加载完成: %d 只股票", len(result))
    cache_set(_key, result)
    _memo_set(_memo_key_str, result)
    return result


def get_sector_fund_flow() -> list[dict[str, Any]]:
    """获取行业资金流向排名（今日）。

    调用 ak.stock_sector_fund_flow_rank() 获取行业资金流向，
    含主力净流入/净额、涨跌幅等。

    缓存策略：指数指纹 + 1天 TTL 双因子失效。
      指数变化 → 指纹改变 → 缓存键不同 → 自动取新数据

    Returns:
        [{name, change_pct, main_net_inflow, main_net_inflow_pct, top_stock}, ...]
        失败时返回空列表
    """
    # ── 内存缓存 ──
    _memo_key_str = _memo_key("sector_flow")
    _memo_val = _memo_get(_memo_key_str)
    if _memo_val is not None:
        return _memo_val

    # ── 指纹 + 读文件缓存 ──
    _fp = _compute_index_fingerprint()
    _key = _cache_key(_CACHE_FLOW_PREFIX, _fp)
    cached = cache_get(_key, _SECTOR_FLOW_TTL)
    if cached is not None:
        _memo_set(_memo_key_str, cached)
        return cached

    # ── 取数 ──
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 模块未安装，跳过行业资金流向")
        return []

    def _fetch():
        return ak.stock_sector_fund_flow_rank(
            indicator="今日", sector_type="行业资金流",
        )

    df = _run_with_timeout(_fetch)
    if df is None:
        logger.warning("行业资金流向获取失败: 超时")
        return []
    if df.empty:
        logger.debug("行业资金流向: 结果为空")
        return []

    # ── 结构化 ──
    result: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            result.append({
                "name": str(row.get("名称", "") or "").strip(),
                "change_pct": _safe_float(row.get("今日涨跌幅")),
                "main_net_inflow": _safe_float(row.get("今日主力净流入-净额")),
                "main_net_inflow_pct": _safe_float(row.get("今日主力净流入-净占比")),
                "top_stock": str(row.get("今日主力净流入最大股", "") or "").strip(),
            })
        except (ValueError, TypeError):
            continue

    logger.info("行业资金流向加载完成: %d 个行业", len(result))
    cache_set(_key, result)
    _memo_set(_memo_key_str, result)
    return result


def _compute_dividend_fingerprint(codes: list[str]) -> str:
    """计算股票代码列表的指纹，用于分红数据缓存键。

    Args:
        codes: 要查询的股票代码列表

    Returns:
        12 字符十六进制指纹；空列表时返回 "empty"
    """
    if not codes:
        return "empty"
    try:
        raw = json.dumps(sorted(set(codes)), ensure_ascii=False, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()[:12]
    except Exception:
        logger.debug("分红指纹计算失败，降级到无指纹缓存")
        return "nofp"


def _calc_dividend_summary(df_data) -> dict | None:
    """从单只股票的分红历史 DataFrame 计算年均分红汇总。

    提取每年每股股利，计算年均值。

    Args:
        df_data: akshare.stock_history_dividend 返回的 DataFrame 或 None

    Returns:
        {avg_dividend: float, years: int, record_count: int} 或 None
    """
    if df_data is None or df_data.empty:
        return None

    try:
        # 定位"除权除息日"列
        date_col = next((c for c in df_data.columns if "除权除息" in c), None)
        if not date_col:
            return None

        # 定位"每股股利(税前)"列，回退到任意"每股股利"列
        div_col = next((c for c in df_data.columns if "每股股利" in c and "税前" in c), None)
        if not div_col:
            div_col = next((c for c in df_data.columns if "每股股利" in c), None)
        if not div_col:
            return None

        yearly: dict[int, float] = {}
        for _, row in df_data.iterrows():
            date_str = str(row.get(date_col, "") or "")
            if len(date_str) < 4:
                continue
            try:
                year = int(date_str[:4])
                div_val = _safe_float(row.get(div_col))
                if div_val is not None:
                    yearly[year] = yearly.get(year, 0.0) + div_val
            except (ValueError, TypeError):
                continue

        if not yearly:
            return None

        total = sum(yearly.values())
        return {
            "avg_dividend": round(total / len(yearly), 4),
            "years": len(yearly),
            "record_count": len(df_data),
        }
    except Exception:
        logger.debug("分红数据解析失败")
        return None


def get_dividend_data(codes: list[str]) -> dict[str, dict]:
    """获取股票历史分红数据，计算年均每股分红。

    调用 ak.stock_history_dividend(symbol, indicator="分红") 获取每只股票
    的历年分红记录，汇总为年均每股股利。

    缓存策略：代码列表指纹 + 1 月 TTL 双因子失效。
      持仓/穿透代码变更 → 指纹改变 → 缓存自动失效

    Args:
        codes: 要查询的股票代码列表

    Returns:
        {code: {name: str, avg_dividend: float, years: int, record_count: int}, ...}
        失败时返回空 dict

    注意：
        - 仅对 A 股（6/0/3 开头）有意义，基金/债券代码会跳过
        - akshare 未安装或 API 超时时自动降级返回空 dict
    """
    # ── 内存缓存 ──
    _codes_hash = hashlib.md5(json.dumps(sorted(codes), ensure_ascii=False).encode()).hexdigest()[:12]
    _memo_key_str = _memo_key("dividend", _codes_hash)
    _memo_val = _memo_get(_memo_key_str)
    if _memo_val is not None:
        return _memo_val

    # ── 指纹 + 读文件缓存 ──
    _fp = _compute_dividend_fingerprint(codes)
    _key = _cache_key(_CACHE_DIVIDEND_PREFIX, _fp)
    cached = cache_get(_key, _DIVIDEND_TTL)
    if cached is not None:
        _memo_set(_memo_key_str, cached)
        return cached

    # ── lazily import akshare ──
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 模块未安装，跳过分红数据")
        return {}

    # ── 只处理 A 股代码 ──
    a_codes = [c for c in codes if c.startswith(("6", "0", "3"))]
    if not a_codes:
        logger.debug("分红数据: 无 A 股代码，跳过")
        return {}

    logger.info("正在获取 %d 只股票的分红历史...", len(a_codes))
    result: dict[str, dict] = {}
    failed = 0

    def _fetch_one(code: str) -> tuple[str, dict | None]:
        """获取单只股票分红并计算汇总。"""
        try:
            df = ak.stock_history_dividend(symbol=code, indicator="分红")
            summary = _calc_dividend_summary(df)
            if summary:
                # 提取股票简称（从 df 第一行）
                name_col = next((c for c in (df or {}).columns if "简称" in c or "名称" in c), None)
                name = str(df.iloc[0].get(name_col, "")) if name_col and df is not None and not df.empty else ""
                summary["name"] = name
            return (code, summary)
        except Exception as e:
            logger.debug("股票 %s 分红获取失败: %s", code, e)
            return (code, None)

    # 用线程池并行获取（最多 5 路）
    with ThreadPoolExecutor(max_workers=5) as pool:
        fut_map = {pool.submit(_fetch_one, code): code for code in a_codes}
        for future in as_completed(fut_map):
            code, summary = future.result()
            if summary:
                result[code] = summary
            else:
                failed += 1

    logger.info("分红数据加载完成: %d 只成功, %d 只无数据", len(result), failed)
    cache_set(_key, result)
    _memo_set(_memo_key_str, result)
    return result


def _safe_float(val: Any) -> float | None:
    """安全转 float，None/NaN/花式入参 → None。"""
    if val is None:
        return None
    try:
        v = float(val)
        return v
    except (ValueError, TypeError):
        return None
