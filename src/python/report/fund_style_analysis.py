"""基金风格判定+漂移检测模块 — 报告第 16 页。

风格六宫格风格箱：大盘/中盘/小盘 × 成长/价值/混合。

判定依据（方案 A — 主路线）：
  - 使用东方财富 push2 API 扩展字段获取持仓个股市值+PE
  - size: >500亿=大盘, 100-500亿=中盘, <100亿=小盘
  - value/growth: PE vs 行业平均 PE

降级方案（方案 C — 兜底）：
  - 外部 API 数据不可用时按代码前缀估算规模
  - 估值方向统一标注"混合"，标注"估算风格"

设计：
  - 独立快照键 fund_style_snapshot（固定键，不受持仓指纹影响）
  - 首次运行记录基线，标注"基准确立中"
  - 漂移按网格距离判定：轻度(1格) / 中度(2格) / 严重(3格+)
"""

from __future__ import annotations

import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.code_utils import estimate_market_cap_by_prefix, is_a_share_code

logger = logging.getLogger("invest")

# 会话级扩展数据缓存 — 委托 DataSourceRegistry session_cache（C4 约束, domain="extended"）
# Tencent 二级降级熔断 — 委托 DataSourceRegistry 熔断器（provider="tencent_style"）
# 注：register_provider("tencent_style") 采用惰性注册（首次 use 时触发，见 _ensure_tencent_provider_registered）

_SNAPSHOT_KEY = "fund_style_snapshot"
_SNAPSHOT_TTL = 365 * 86400

# ── 六宫格风格定义 ──────────────────────────────────────────

_SIZE_ORDER = ["大盘", "中盘", "小盘"]
_STYLE_ORDER = ["价值", "混合", "成长"]

# 所有有效风格组合
_STYLE_BOXES: set[str] = {
    f"{size}{style}"
    for size in _SIZE_ORDER
    for style in _STYLE_ORDER
}


# ── 市值 / PE 阈值 ────────────────────────────────────────

_MARKET_CAP_LARGE = 500e8  # 500 亿
_MARKET_CAP_MID = 100e8    # 100 亿

# PE 相对行业平均的乘数阈值
_PE_VALUE_THRESHOLD = 0.7    # PE < 行业均值的 70% → 价值型
_PE_GROWTH_THRESHOLD = 1.3   # PE > 行业均值的 130% → 成长型


# ═══════════════════════════════════════════════════════════
#  快照管理
# ═══════════════════════════════════════════════════════════


_tencent_registered: bool = False


def _ensure_tencent_provider_registered() -> None:
    """惰性注册 Tencent 风格数据 Provider（避免模块导入时副作用）。"""
    global _tencent_registered
    if _tencent_registered:
        return
    from src.python.provider_registry import get_registry
    get_registry().register_provider("tencent_style", tier=4, timeout=15.0)
    _tencent_registered = True


def _load_snapshot() -> dict[str, Any] | None:
    """读取风格快照（固定键 fund_style_snapshot）。

    Returns:
        {code: {style, check_date, ...}} 或 None
    """
    return cache_get(_SNAPSHOT_KEY, _SNAPSHOT_TTL)


def _update_snapshot(current: dict[str, Any]) -> None:
    """更新风格快照（覆写）。

    快照格式：{code: {style: str, check_date: str}, ...}
    """
    cache_set(_SNAPSHOT_KEY, current)


# ═══════════════════════════════════════════════════════════
#  单只股票风格判定
# ═══════════════════════════════════════════════════════════


def _market_cap_to_size(market_cap: float) -> str:
    """根据总市值判断规模标签。"""
    if market_cap >= _MARKET_CAP_LARGE:
        return "大盘"
    elif market_cap >= _MARKET_CAP_MID:
        return "中盘"
    elif market_cap > 0:
        return "小盘"
    return "未知"


def _pe_to_style(pe: float, industry_avg_pe: float | None = None) -> str:
    """根据 PE 判断估值倾向。

    Args:
        pe: 个股动态市盈率（PE TTM）
        industry_avg_pe: 行业平均 PE，无行业数据时使用绝对值判定

    Returns:
        "价值" / "成长" / "混合"
    """
    if pe <= 0:
        return "混合"  # 负 PE 不参与方向判定

    if industry_avg_pe and industry_avg_pe > 0:
        ratio = pe / industry_avg_pe
        if ratio <= _PE_VALUE_THRESHOLD:
            return "价值"
        elif ratio >= _PE_GROWTH_THRESHOLD:
            return "成长"
        return "混合"
    else:
        # 无行业平均 PE 时，使用绝对值粗略判断
        if pe < 15:
            return "价值"
        elif pe > 30:
            return "成长"
        return "混合"


def _estimate_style_by_code(code: str) -> str:
    """按代码前缀粗略估算规模（降级方案 C，委托 code_utils 原语）。"""
    return estimate_market_cap_by_prefix(code)


def _get_size_from_code(code: str) -> str:
    """从代码前缀提取规模类别（用于降级）。"""
    est = _estimate_style_by_code(code)
    # 标准化
    if est in ("大盘", "中大盘"):
        return "大盘"
    elif est in ("中盘",):
        return "中盘"
    elif est in ("中小盘", "小盘"):
        return "小盘"
    return "其他"


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
    from src.python.cache import get as _cache_get, set as _cache_set
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
    from src.python.cache import get as _cache_get, set as _cache_set
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
        return {code: industry_avg[ind] for code, ind in code_industry.items()
                if ind in industry_avg}
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
    from src.python.provider_registry import get_registry, NOT_FOUND
    reg = get_registry()

    if not holdings:
        return {"code": fund_code, "style": "--", "is_estimated": False, "details": []}

    # 获取所有持仓股票代码
    stock_codes = [h.get("code", "").strip() for h in holdings if h.get("code")]
    stock_codes = [c for c in stock_codes if c]

    # 获取行业平均 PE（当前为空）
    industry_avg_pe_map = _get_industry_avg_pe(stock_codes) if stock_codes else {}

    # ── 预取阶段：并行填充 registry session_cache ──────────────────
    # 三级降级：push2（精确）→ Tencent 批量并发（可靠）→ 代码段估算（兜底）
    # 非 A 股（美股/港股/基金等）跳过 API 调用，直接估算
    _codes_to_fetch = [
        c for h in holdings if (c := (h.get("code") or "").strip())
        and c and is_a_share_code(c)
    ]
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
    # 并发批量腾讯回退（push2 熔断时效果明显，~60s → ~8s）
    if _need_tencent and not reg.is_circuit_broken("tencent_style"):
        _batch_tencent_extended(_need_tencent)

    # ── 判定阶段：逐只股票读取 registry session_cache 判定风格 ──
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

        stock_styles.append({
            "name": name, "code": code, "ratio": ratio,
            "size": size, "style": style,
            "is_estimated": result.get("is_estimated", False),
        })

        if size in size_weights:
            size_weights[size] += ratio
        if style in style_weights:
            style_weights[style] += ratio
        total_weight += ratio

    if total_weight <= 0:
        return {"code": fund_code, "style": "--", "is_estimated": False, "details": []}

    # 按权重确定最终风格
    dominant_size = max(size_weights, key=lambda k: size_weights[k])
    dominant_style = max(style_weights, key=lambda k: style_weights[k])

    style_label = f"{dominant_size}{dominant_style}"

    return {
        "code": fund_code,
        "style": style_label,
        "is_estimated": has_estimated,
        "details": stock_styles,
    }


# ═══════════════════════════════════════════════════════════
#  漂移检测
# ═══════════════════════════════════════════════════════════


def _grid_distance(style_a: str, style_b: str) -> int:
    """计算两种风格在六宫格网格上的距离。

    距离定义：size 差 + style 差的绝对值。
    例：大盘成长→小盘成长 = 2（size差2格，style差0格）
        大盘成长→中盘价值 = 2（size差1格，style差1格）
        大盘成长→小盘价值 = 4（size差2格，style差2格）

    Returns:
        0-4 的网格距离（0=相同，4=完全相反）
    """
    if style_a == style_b or style_a == "--" or style_b == "--":
        return 0

    size_a = style_a[:2] if len(style_a) >= 2 else ""
    size_b = style_b[:2] if len(style_b) >= 2 else ""
    style_type_a = style_a[2:] if len(style_a) > 2 else ""
    style_type_b = style_b[2:] if len(style_b) > 2 else ""

    size_dist = abs(_SIZE_ORDER.index(size_a) - _SIZE_ORDER.index(size_b)) if size_a in _SIZE_ORDER and size_b in _SIZE_ORDER else 0
    style_dist = abs(_STYLE_ORDER.index(style_type_a) - _STYLE_ORDER.index(style_type_b)) if style_type_a in _STYLE_ORDER and style_type_b in _STYLE_ORDER else 0

    return size_dist + style_dist


def _drift_level(distance: int) -> str:
    """根据网格距离返回漂移等级。"""
    if distance >= 3:
        return "严重"
    elif distance >= 2:
        return "中度"
    elif distance >= 1:
        return "轻度"
    return "无"


def analyze_style_for_all_funds(
    fund_holdings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """对所有基金进行风格判定和漂移检测。

    Args:
        fund_holdings: {fund_code: {name, holdings: [{name, code, ratio}, ...]}, ...}

    Returns:
        {"results": [{code, name, current_style, prev_style, drift_level,
                      drift_score, is_estimated, is_first_check, ...}, ...],
         "snapshot_updated": bool}
    """
    snapshot = _load_snapshot() or {}
    is_first_run = not bool(snapshot)
    new_snapshot: dict[str, Any] = {}
    results: list[dict[str, Any]] = []

    _total = len(fund_holdings)
    for idx, (code, info) in enumerate(fund_holdings.items(), 1):
        name = info.get("name", code)
        holdings = info.get("holdings", [])
        logger.info("基金风格分析 [%d/%d]: %s (%s)", idx, _total, name, code)
        if not holdings:
            continue

        # 风格判定
        style_result = classify_fund_style(code, holdings)
        current_style = style_result.get("style", "--")
        is_estimated = style_result.get("is_estimated", False)

        # 漂移检测
        prev_entry = snapshot.get(code)
        prev_style = prev_entry.get("style") if prev_entry else None
        is_first_check = is_first_run or prev_style is None

        # 生成备注
        remark_parts = []
        if is_first_check:
            remark = "基准确立中"
        else:
            if is_estimated:
                remark_parts.append("估算风格")
            remark = "；".join(remark_parts) if remark_parts else ""

        if is_first_check:
            drift_level = "基准确立中" if current_style != "--" else "--"
            drift_score = None
        else:
            distance = _grid_distance(str(prev_style), current_style)
            drift_level = _drift_level(distance)
            drift_score = distance

        results.append({
            "code": code,
            "name": name,
            "current_style": current_style,
            "prev_style": prev_style or "--",
            "drift_level": drift_level,
            "drift_score": drift_score,
            "is_estimated": is_estimated,
            "is_first_check": is_first_check,
            "remark": remark,
            "details": style_result.get("details", []),
        })

        if current_style != "--":
            new_snapshot[code] = {
                "style": current_style,
                "is_estimated": is_estimated,
                "check_date": datetime.now().strftime("%Y-%m-%d"),
            }

    if new_snapshot:
        _update_snapshot(new_snapshot)

    return {"results": results, "snapshot_updated": bool(new_snapshot)}
