"""基金风格判定 — 基金风格分类计算。

根据持仓个股的市值+PE 数据，按六宫格风格箱判定基金风格。
三级降级链路：push2（精确）→ Tencent（可靠）→ 代码段估算（兜底）。
"""

from __future__ import annotations

import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.code_utils import is_a_share_code
from src.python.report.fund_style_base import (
    _ensure_tencent_provider_registered,
    _get_size_from_code,
    _market_cap_to_size,
    _pe_to_style,
)

logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════
#  单只股票风格判定
# ═══════════════════════════════════════════════════════════


def _classify_stock(
    code: str,
    market_cap: float | None,
    pe: float | None,
    industry_avg_pe: float | None = None,
) -> dict[str, Any]:
    """对单只股票进行风格判定。

    方案 A（push2 数据可用）→ 精确判定
    方案 C（数据不可用）→ 代码段降级

    Returns:
        {"size": "大盘"/"中盘"/"小盘"/"--",
         "style": "价值"/"成长"/"混合"/"--",
         "is_estimated": bool}  # True 表示使用了降级方案
    """
    if market_cap is not None and market_cap > 0:
        size = _market_cap_to_size(market_cap)
    else:
        size = _get_size_from_code(code)
        return {"size": size, "style": "混合", "is_estimated": True}

    if pe is not None and pe > 0:
        style = _pe_to_style(pe, industry_avg_pe)
        return {"size": size, "style": style, "is_estimated": False}
    else:
        return {"size": size, "style": "混合", "is_estimated": True}


# ═══════════════════════════════════════════════════════════
#  基金风格判定
# ═══════════════════════════════════════════════════════════


def _push2_extended(code: str) -> dict[str, Any] | None:
    """从东方财富 push2 API 获取市值+PE 扩展数据。

    结果以全天 TTL 写入文件缓存，同一股票同日内跨进程不重复请求。

    Args:
        code: 6 位 A 股代码

    Returns:
        {"market_cap": float, "pe": float, "pb": float} 或 None
    """
    from src.python.cache import get as _cache_get
    from src.python.cache import set as _cache_set
    from src.python.constants import CACHE_DAILY

    _key = f"extended_{code}"
    _cached = _cache_get(_key, CACHE_DAILY)
    if _cached is not None:
        return _cached

    try:
        from src.python.fetcher.industry import make_push2_request

        inner = make_push2_request(code)
        if inner is None:
            return None

        market_cap = inner.get("f20")
        pe = inner.get("f9")
        pb = inner.get("f23")

        result: dict[str, Any] = {}
        if market_cap is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["market_cap"] = float(market_cap)
        if pe is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["pe"] = float(pe)
        if pb is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["pb"] = float(pb)

        if result:
            _cache_set(_key, result)
        return result if result else None
    except Exception:
        logger.warning("push2 扩展数据获取失败 [%s]", code, exc_info=True)
        return None


def _tencent_extended(code: str) -> dict[str, Any] | None:
    """从腾讯财经 API 获取市值+PE 扩展数据（二级降级）。

    结果以全天 TTL 写入文件缓存，同一股票同日内跨进程不重复请求。

    Args:
        code: 6 位 A 股代码

    Returns:
        {"market_cap": float, "pe": float} 或 None
    """
    from src.python.cache import get as _cache_get
    from src.python.cache import set as _cache_set
    from src.python.constants import CACHE_DAILY

    _key = f"extended_{code}"
    _cached = _cache_get(_key, CACHE_DAILY)
    if _cached is not None:
        return _cached

    from src.python.provider_registry import get_registry

    reg = get_registry()
    try:
        from src.python.fetcher.price import fetch_market_data

        data = fetch_market_data(code)
        if data is None:
            return None

        result: dict[str, Any] = {}
        # Tencent f46 总市值单位为亿，转换为元以与 push2 单位一致
        market_cap = data.get("market_cap")
        if market_cap is not None and market_cap > 0:
            result["market_cap"] = market_cap * 1e8  # 亿 → 元

        pe = data.get("pe")
        if pe is not None and pe > 0:
            result["pe"] = pe

        if result:
            reg.record_success("tencent_style")
            _cache_set(_key, result)
            return result
        return None
    except Exception:
        logger.warning("Tencent 扩展数据获取失败 [%s]", code, exc_info=True)
        reg.record_failure("tencent_style", f"extended:{code}")
        return None


def _get_industry_avg_pe(codes: list[str]) -> dict[str, float]:
    """获取每只股票对应行业的平均 PE。

    利用 push2 API 获取持仓各股的行业归属和 PE 数据，
    按行业分组后以 **中位数** 作为行业平均 PE 基准（抗离群值）。

    副作用：同时填充 registry session_cache（domain="extended"），
    使 ``classify_fund_style`` 主循环直接命中缓存，不会重复请求。

    Args:
        codes: 6 位 A 股代码列表

    Returns:
        {code: industry_avg_pe, ...} 映射；
        仅包含有行业分类且 PE > 0 的股票；
        当无可用数据时返回 ``{}``（方案 C 降级走代码段估算）。
    """
    try:
        from src.python.fetcher.industry import fetch_industry_data
    except ImportError:
        logger.warning("行业数据 fetcher 模块不可用，行业平均 PE 功能降级")
        return {}

    if not codes:
        return {}

    try:
        # ── 第一遍：获取行业归属 + PE 数据 ──────────────────────
        code_industry: dict[str, str] = {}
        industry_pes: dict[str, list[float]] = {}

        for code in codes:
            if not is_a_share_code(code):
                continue

            # push2 行业分类（通过 fetcher → chain → provider 路径）
            industry_data = fetch_industry_data(code)
            industry = industry_data.get("industry", "") if industry_data else ""
            if not industry:
                continue

            # push2 扩展行情 PE（同时填充 registry session_cache，主循环复用）
            ext = _push2_extended(code)
            if ext is None:
                continue
            pe = ext.get("pe")
            if pe is None or pe <= 0:
                continue

            code_industry[code] = industry
            if industry not in industry_pes:
                industry_pes[industry] = []
            industry_pes[industry].append(pe)

        if not industry_pes:
            return {}

        # ── 第二遍：计算各行业 PE 中位数 ────────────────────────
        industry_avg: dict[str, float] = {}
        for ind, pe_list in industry_pes.items():
            sorted_pe = sorted(pe_list)
            n = len(sorted_pe)
            if n == 1:
                industry_avg[ind] = sorted_pe[0]
            elif n % 2 == 1:
                industry_avg[ind] = sorted_pe[n // 2]
            else:
                industry_avg[ind] = (sorted_pe[n // 2 - 1] + sorted_pe[n // 2]) / 2.0

        # ── 第三遍：代码 → 行业平均 PE 映射 ─────────────────────
        return {code: industry_avg[ind] for code, ind in code_industry.items() if ind in industry_avg}
    except Exception:
        logger.warning("行业平均 PE 获取异常", exc_info=True)
        return {}


def _batch_tencent_extended(codes: list[str]) -> dict[str, dict[str, Any]]:
    """并发批量通过腾讯 API 获取多只股票的扩展数据。

    当 push2 熔断时作为批量降级方案，避免逐个串行请求。
    结果同时写入 registry session_cache（domain="extended"）供主循环复用。

    Args:
        codes: 6 位 A 股代码列表

    Returns:
        {code: {"market_cap": float, "pe": float}, ...} —
        仅包含有成功返回的股票代码
    """
    if not codes:
        return {}
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut_map = {ex.submit(_tencent_extended, c): c for c in codes}
        for fut in as_completed(fut_map):
            c = fut_map[fut]
            try:
                data = fut.result()
            except Exception:
                logger.warning("Tencent 批量并发获取失败 [%s]", c, exc_info=True)
                data = None
            if data is not None:
                results[c] = data
    # 同步写入 registry session_cache（主循环不会重复请求）
    if results:
        from src.python.provider_registry import get_registry

        reg = get_registry()
        for c, d in results.items():
            reg.session_cache_set("extended", c, d)
    return results


def _prefetch_extended_data(
    holdings: list[dict],
    reg: Any,
) -> None:
    """预取各持仓股票的扩展数据（三级降级：push2 → Tencent → 代码段估算）。"""
    _codes_to_fetch = [c for h in holdings if (c := (h.get("code") or "").strip()) and c and is_a_share_code(c)]
    # 去重：同一股票跨基金不重复请求
    _seen: set[str] = set()
    _unique_codes = [c for c in _codes_to_fetch if not (c in _seen or _seen.add(c))]
    # 仅处理尚未缓存到 registry session_cache 的代码
    _need_tencent: list[str] = []
    for code in _unique_codes:
        if reg.session_cache_contains("extended", code):
            continue
        ext_data = _push2_extended(code)
        if ext_data is None:
            _need_tencent.append(code)
        else:
            reg.session_cache_set("extended", code, ext_data)
    # 并发批量腾讯回退（push2 熔断时的降级方案）
    if _need_tencent and not reg.is_circuit_broken("tencent_style"):
        _batch_tencent_extended(_need_tencent)


def _classify_stock_styles(
    holdings: list[dict],
    reg: Any,
    industry_avg_pe_map: dict[str, float],
) -> tuple[list[dict], dict[str, float], dict[str, float], float, bool]:
    """逐只股票读取缓存数据并判定风格。

    Returns:
        (stock_styles, size_weights, style_weights, total_weight, has_estimated)
    """
    from src.python.provider_registry import NOT_FOUND

    stock_styles: list[dict[str, Any]] = []
    total_weight = 0.0
    size_weights: dict[str, float] = {"大盘": 0.0, "中盘": 0.0, "小盘": 0.0}
    style_weights: dict[str, float] = {"价值": 0.0, "成长": 0.0, "混合": 0.0}
    has_estimated = False

    for h in holdings:
        code = (h.get("code") or "").strip()
        name = h.get("name", "")
        ratio = abs(h.get("ratio", 0) or 0)
        if ratio <= 0:
            continue

        _cached = reg.session_cache_get("extended", code) if code and is_a_share_code(code) else NOT_FOUND
        ext_data = _cached if _cached is not NOT_FOUND else None
        industry_avg_pe = industry_avg_pe_map.get(code)

        if ext_data:
            mc = ext_data.get("market_cap")
            pe = ext_data.get("pe")
            result = _classify_stock(code, mc, pe, industry_avg_pe)
        else:
            result = _classify_stock(code, None, None)
            result["is_estimated"] = True

        if result["is_estimated"]:
            has_estimated = True

        size = result.get("size", "--")
        style = result.get("style", "混合")

        stock_styles.append(
            {
                "name": name,
                "code": code,
                "ratio": ratio,
                "size": size,
                "style": style,
                "is_estimated": result.get("is_estimated", False),
            }
        )

        if size in size_weights:
            size_weights[size] += ratio
        if style in style_weights:
            style_weights[style] += ratio
        total_weight += ratio

    return stock_styles, size_weights, style_weights, total_weight, has_estimated


def _finalize_fund_style(
    fund_code: str,
    stock_styles: list[dict],
    total_weight: float,
    size_weights: dict[str, float],
    style_weights: dict[str, float],
    has_estimated: bool,
) -> dict[str, Any]:
    """按权重确定最终风格并组装结果。"""
    if total_weight <= 0:
        return {"code": fund_code, "style": "--", "is_estimated": False, "details": []}

    dominant_size = max(size_weights, key=lambda k: size_weights[k])
    dominant_style = max(style_weights, key=lambda k: style_weights[k])
    style_label = f"{dominant_size}{dominant_style}"

    return {
        "code": fund_code,
        "style": style_label,
        "is_estimated": has_estimated,
        "details": stock_styles,
    }


def classify_fund_style(
    fund_code: str,
    holdings: list[dict[str, Any]],
) -> dict[str, Any]:
    """判定一只基金的风格。

    Args:
        fund_code: 基金代码（仅用于日志/索引）
        holdings: [{name, code, ratio}, ...] 该基金的前 N 大持仓

    Returns:
        {"code": fund_code,
         "style": "大盘成长"/"--",
         "is_estimated": bool,
         "details": [{"name", "code", "size", "style", "ratio", "is_estimated"}, ...]}
    """
    _ensure_tencent_provider_registered()  # 惰性注册（避免模块级副作用）
    from src.python.provider_registry import get_registry

    reg = get_registry()

    if not holdings:
        return {"code": fund_code, "style": "--", "is_estimated": False, "details": []}

    # 获取所有持仓股票代码
    stock_codes = [h.get("code", "").strip() for h in holdings if h.get("code")]
    stock_codes = [c for c in stock_codes if c]

    # 获取行业平均 PE
    industry_avg_pe_map = _get_industry_avg_pe(stock_codes) if stock_codes else {}

    # ── 预取阶段：并行填充 registry session_cache ──
    _prefetch_extended_data(holdings, reg)

    # ── 判定阶段：逐只股票读取缓存数据判定风格 ──
    stock_styles, size_weights, style_weights, total_weight, has_estimated = _classify_stock_styles(
        holdings, reg, industry_avg_pe_map,
    )

    # ── 按权重确定最终风格 ──
    return _finalize_fund_style(
        fund_code, stock_styles, total_weight, size_weights, style_weights, has_estimated,
    )
