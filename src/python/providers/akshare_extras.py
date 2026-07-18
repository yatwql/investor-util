"""akshare 扩展数据源 — 盈利预测 + 行业资金流向 + 分红历史。

通过 akshare 获取以下数据：
  1. stock_profit_forecast_em — 机构盈利预测（全量股票，含预测 EPS）
  2. stock_sector_fund_flow_rank — 行业资金流向排名（含主力净流入）
  3. stock_history_dividend — 全量股票历史分红（akshare 1.18.64+ 无参调用，按代码过滤）

各函数独立，使用指数变化/代码列表指纹 + TTL 双因子缓存失效策略。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading as _threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.code_utils import is_a_share_code

logger = logging.getLogger("invest")

# akshare 是可选依赖，统一在模块级加载一次
try:
    import akshare as ak
except ImportError:
    ak = None
    logger.info("akshare 模块未安装，akshare_extras 功能将跳过")

# ── 进程级内存 TTL 缓存（位于文件缓存之上） ──
_MEMO_CACHE: dict[str, tuple[Any, float]] = {}
_MEMO_LOCK = _threading.Lock()
_MEMO_MAX = 100
_MEMO_TTL: dict[str, float] = {
    "profit_forecast": 300,  # 5 min — 指纹驱动，短期 memo 足够
    "sector_flow": 60,  # 1 min — 行业资金流向变化快
    "dividend": 600,  # 10 min — 分红数据会话内极少变化
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
            # 过期条目延迟删除
            del _MEMO_CACHE[key]
    return None


def _memo_set(key: str, value: Any) -> None:
    with _MEMO_LOCK:
        # LRU 淘汰：超过 _MEMO_MAX 条时删除最旧条目
        if len(_MEMO_CACHE) >= _MEMO_MAX and key not in _MEMO_CACHE:
            oldest_key = min(_MEMO_CACHE, key=lambda k: _MEMO_CACHE[k][1])
            del _MEMO_CACHE[oldest_key]
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
_TTL = 86400  # 盈利预测：1天
_SECTOR_FLOW_TTL = 900  # 行业资金流向：15分钟
_DIVIDEND_TTL = 2592000  # 分红：1个月
_TIMEOUT = 15.0  # akshare 调用超时（秒）


def _compute_index_fingerprint() -> str:
    """计算市场指数数据的指纹，用于缓存键。

    从 fetcher 获取 A 股 + 美股指数数据 → MD5 前 12 位。
    指数变化时指纹改变 → 缓存自动失效，无需等待 TTL 过期。

    使用进程级内存缓存避免同一会话内重复文件读取。

    Returns:
        12 字符十六进制指纹；获取失败时返回空字符串（降级到纯 TTL 缓存）
    """
    try:
        from src.python.fetcher.index import fetch_indices, fetch_us_indices

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
        logger.debug("指数指纹计算失败（降级到纯 TTL 缓存）", exc_info=True)
        return ""


def _cache_key(prefix: str, fingerprint: str) -> str:
    """生成缓存键：有指纹时使用前缀+指纹，否则使用前缀+fallback。"""
    if fingerprint:
        return f"{prefix}{fingerprint}"
    return f"{prefix}nofp"


def _run_with_timeout(fn, timeout: float = _TIMEOUT, retries: int = 1):
    """在线程中执行函数，超时或异常时重试，全部失败返回 None。

    Args:
        fn: 要执行的函数
        timeout: 每次调用的超时秒数
        retries: 失败后的重试次数（默认 1 次）
    """
    for attempt in range(1 + retries):
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            fut = pool.submit(fn)
            try:
                return fut.result(timeout=timeout)
            except TimeoutError:
                logger.warning("akshare 调用超时 (%.1fs, 第 %d/%d 次)", timeout, attempt + 1, 1 + retries)
                fut.cancel()
                if attempt < retries:
                    import time as _time

                    _time.sleep(1)
                continue
            except Exception as e:
                logger.warning("akshare 调用异常 (第 %d/%d 次): %s", attempt + 1, 1 + retries, e)
                fut.cancel()
                if attempt < retries:
                    import time as _time

                    _time.sleep(1)
                continue
        finally:
            pool.shutdown(wait=False)
    return None


def get_profit_forecast() -> dict[str, dict]:
    """获取全量机构盈利预测数据。

    调用 ak.stock_profit_forecast_em() 获取所有股票的
    研报覆盖、预测 EPS、机构评级等数据。

    缓存策略：指数指纹 + 1天 TTL 双因子失效。
      指数变化 → 指纹改变 → 缓存键不同 → 自动取新数据

    Returns:
        {code: {name, reports, eps_2026e, eps_2027e, buy, sell}, ...}
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
    if ak is None:
        logger.warning("akshare 模块未安装，跳过盈利预测")
        return {}

    def _fetch():
        return ak.stock_profit_forecast_em()

    df = _run_with_timeout(_fetch, timeout=30.0)
    if df is None:
        logger.warning("盈利预测获取失败（超时或网络错误）")
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


def get_profit_forecast_cache_key() -> str:
    """获取盈利预测数据的文件缓存键名（含指数指纹）。

    键名包含指数指纹，指数变化时指纹改变 → 缓存自动失效。
    供外部模块（如 fund_performance.py）获取正确键名后调 get_cache_age()。

    Returns:
        完整缓存键名（如 ``"profit_forecast_a1b2c3d4e5f6"``）
    """
    fp = _compute_index_fingerprint()
    return _cache_key(_CACHE_PROFIT_PREFIX, fp)


# 行业资金流向最近失败类型: "" / "connection" / "empty"
_SECTOR_FLOW_FAILURE: str = ""


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
    if ak is None:
        logger.warning("akshare 模块未安装，跳过行业资金流向")
        return []

    def _fetch():
        return ak.stock_sector_fund_flow_rank(
            indicator="今日",
            sector_type="行业资金流",
        )

    df = _run_with_timeout(_fetch)
    if df is None:
        _SECTOR_FLOW_FAILURE = "connection"
        logger.warning("行业资金流向获取失败")
        return []
    if df.empty:
        _SECTOR_FLOW_FAILURE = "empty"
        logger.debug("行业资金流向: 结果为空")
        return []

    # ── 结构化 ──
    result: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            result.append(
                {
                    "name": str(row.get("名称", "") or "").strip(),
                    "change_pct": _safe_float(row.get("今日涨跌幅")),
                    "main_net_inflow": _safe_float(row.get("今日主力净流入-净额")),
                    "main_net_inflow_pct": _safe_float(row.get("今日主力净流入-净占比")),
                    "top_stock": str(row.get("今日主力净流入最大股", "") or "").strip(),
                }
            )
        except (ValueError, TypeError):  # noqa: PERF203
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
        logger.debug("分红指纹计算失败，降级到无指纹缓存", exc_info=True)
        return "nofp"


def _calc_dividend_summary(df_data) -> dict | None:
    """从股票分红汇总 DataFrame 提取年度平均分红。

    akshare 1.18.64+ 的 stock_history_dividend() 返回聚合数据（每只股票一行），
    列包含：代码、名称、上市日期、累计股息、年均股息、分红次数 等。

    Args:
        df_data: ak.stock_history_dividend 返回的 DataFrame 子集（单只股票的一行）

    Returns:
        {avg_dividend: float, record_count: int} 或 None
    """
    if df_data is None or df_data.empty:
        return None

    try:
        # 定位"年均股息"列
        div_col = next((c for c in df_data.columns if "年均股息" in c or "每股股息" in c or "每股股利" in c), None)
        if not div_col:
            return None

        avg_div = _safe_float(df_data.iloc[0].get(div_col))
        if avg_div is None or avg_div <= 0:
            return None

        # 定位"分红次数"列
        cnt_col = next((c for c in df_data.columns if "分红次数" in c), None)
        record_count = int(df_data.iloc[0].get(cnt_col, 0)) if cnt_col else 0

        return {
            "avg_dividend": round(avg_div, 4),
            "record_count": record_count,
        }
    except Exception:
        logger.debug("分红数据解析失败", exc_info=True)
        return None


def _fetch_all_dividends(a_codes: list[str]) -> dict[str, dict]:
    """获取多只股票的分红数据，返回 {code: summary}。

    akshare 1.18.64+ 的 stock_history_dividend() 不接受参数，返回全量数据。
    改为一次拉取后按代码过滤，不再逐股并发请求。
    """
    result: dict[str, dict] = {}
    code_set = set(a_codes)

    try:
        full_df = ak.stock_history_dividend()
    except Exception as e:
        logger.warning("分红全量数据拉取失败: %s", e)
        return result

    if full_df is None or full_df.empty:
        logger.warning("分红全量数据为空")
        return result

    # 定位"代码"列（akshare 新版列名）
    code_col = next((c for c in full_df.columns if "代码" in c or c.lower() in ("code", "symbol")), None)
    name_col = next((c for c in full_df.columns if "名称" in c or "简称" in c), None)
    if code_col is None:
        logger.warning("分红数据缺少代码列，无法过滤")
        return result

    for code in a_codes:
        sub = full_df[full_df[code_col] == code]
        summary = _calc_dividend_summary(sub)
        if summary and name_col is not None:
            summary["name"] = str(sub.iloc[0].get(name_col, "")) if not sub.empty else ""
        if summary:
            result[code] = summary

    failed = len(a_codes) - len(result)
    logger.info("分红数据加载完成: %d 只成功, %d 只无数据", len(result), failed)
    return result


def get_dividend_data(codes: list[str]) -> dict[str, dict]:
    """获取股票历史分红数据，计算年均每股分红。

    调用 ak.stock_history_dividend()（全量拉取，akshare 1.18.64+ 无参数）
    获取所有股票历年分红记录，按代码过滤后汇总为年均每股股利。

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
    if ak is None:
        logger.warning("akshare 模块未安装，跳过分红数据")
        return {}

    # ── 只处理 A 股代码 ──
    a_codes = [c for c in codes if is_a_share_code(c)]
    if not a_codes:
        logger.debug("分红数据: 无 A 股代码，跳过")
        return {}

    logger.info("正在获取 %d 只股票的分红历史...", len(a_codes))

    def _fetch_div():
        return _fetch_all_dividends(a_codes)

    result = _run_with_timeout(_fetch_div, timeout=60.0) or {}
    if result:
        cache_set(_key, result)
    _memo_set(_memo_key_str, result)
    return result


def _safe_float(val: Any) -> float | None:
    """安全转 float，None/NaN/花式入参 → None。"""
    if val is None:
        return None
    try:
        v = float(val)
        if isinstance(v, float) and math.isnan(v):
            return None
        return v
    except (ValueError, TypeError):
        return None
