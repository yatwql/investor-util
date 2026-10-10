"""持仓相关性 — 纯计算层（静态矩阵 + 滚动趋势）。

职责：接收各品种日收益序列 → 按日期对齐 → 逐对 Pearson 相关 + 双侧 p 值
      → 输出 N×N 下三角相关矩阵 + 配对明细（识别"伪分散"）；
      滚动趋势层：60/120 端点窗的组合平均相关性 + 重点品对滚动相关
      （历史不足时端点窗按可得区间截断并在 notes 标注口径）。

- 无数据获取、无报告依赖，纯标准库 math（日志走 logging，不用 print）。
- 显著性用 _math_utils._t_cdf 手算（scipy/statsmodels 均未安装）。
- 品种历史数据不足窗口 → 对应格为 None（灰色 N/A），绝不硬算（§1.4.5 数据降级治理）。
- 数据不足（<MIN_HOLDINGS 或无可配对样本）→ available=false，status="insufficient"。
"""

from __future__ import annotations

import logging
import math

from src.python.analysis._math_utils import _t_cdf

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════════════════════════

# 计算窗口（交易日 ≈ 3 个月）
DEFAULT_WINDOW: int = 60
# 对齐后有效样本下限：低于此判数据不足（灰色 N/A）
MIN_SAMPLES: int = 60
# 有效品种下限：< 2 只无法成对
MIN_HOLDINGS: int = 2
# 显著性阈值（双侧 p < 0.05）
SIGNIFICANCE_LEVEL: float = 0.05
# 滚动趋势端点窗（交易日）：60 ≈ 一季度、120 ≈ 半年；历史不足时按可得区间截断
ROLLING_WINDOWS: tuple[int, ...] = (60, 120)
# 滚动趋势重点品对输出数量（取静态矩阵 |r| 降序前 N 对）
ROLLING_FOCUS_COUNT: int = 3
# 拉取条数（编排层使用：静态矩阵窗 60 + 滚动 60/120 端点趋势底座，预留对齐损耗）
FETCH_DAYS: int = 260
# 常数序列检测阈值：标准差低于此值视为方差为 0（常数/近常数序列），
# 返回 (0.0, 1.0) 绝不硬算。用容差而非精确 == 0——均值舍入误差可能使
# 常数序列的标准差算出 ~1e-17 的极小非零值（CPython sum 实现差异），
# 精确相等会绕过保护导致虚假近零相关
_CONSTANT_EPS: float = 1e-12


def _is_valid_return(value) -> bool:
    """收益值是否可参与相关计算：排除 None 与 NaN/Inf（后者会使 Pearson 产生虚假相关）。

    Args:
        value: 收益率字段原始值（int/float/str/None）。

    Returns:
        True 表示可参与计算。
    """
    if value is None:
        return False
    try:
        return not math.isinf(float(value)) and not math.isnan(float(value))
    except (TypeError, ValueError):
        return False


# ═══════════════════════════════════════════════════════════════
#  结果工厂
# ═══════════════════════════════════════════════════════════════


def unavailable_result(
    status: str,
    sample_count: int = 0,
    insufficient_codes: list[str] | None = None,
) -> dict:
    """返回不可用结果（数据契约，available=False）。

    Args:
        status: "insufficient"（数据不足）或 "source_failed"（数据源故障）。
        sample_count: 对齐后有效样本数（数据不足时为实际值）。
        insufficient_codes: 历史数据不足计算窗口的品种代码列表。

    Returns:
        含全部数据契约键的空结果字典。
    """
    return {
        "available": False,
        "status": status,
        "window": DEFAULT_WINDOW,
        "sample_count": sample_count,
        "codes": [],
        "names": {},
        "matrix": [],
        "p_values": [],
        "pairs": [],
        "insufficient_codes": insufficient_codes or [],
        "note": "",
    }


# ═══════════════════════════════════════════════════════════════
#  Pearson 相关 + p 值
# ═══════════════════════════════════════════════════════════════


def _pearson_pvalue(x: list[float], y: list[float]) -> tuple[float, float]:
    """Pearson 相关系数 + 双侧 p 值（t 分布，复用 _math_utils._t_cdf）。

    t = r·sqrt((n-2)/(1-r²))，df = n-2，p = 2·(1 - CDF(|t|))。

    Args:
        x, y: 对齐后的日收益序列。

    Returns:
        (r, p)：r ∈ [-1, 1]，p ∈ [0, 1]。
        序列过短（<3）或任一方常数（方差为 0）时返回 (0.0, 1.0)，
        表示无法判定线性关系（渲染为"不显著"白色格）。
    """
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx < _CONSTANT_EPS or sy < _CONSTANT_EPS:
        return 0.0, 1.0
    r = max(-1.0, min(1.0, num / (sx * sy)))
    if abs(r) >= 1.0:
        return r, 0.0
    df = n - 2
    t = r * math.sqrt(df / (1.0 - r * r))
    p = 2.0 * (1.0 - _t_cdf(abs(t), df))
    return r, max(0.0, min(1.0, p))


# ═══════════════════════════════════════════════════════════════
#  主计算入口
# ═══════════════════════════════════════════════════════════════


def compute_correlation_matrix(
    returns_by_code: dict[str, list[dict]],
    names_by_code: dict[str, str] | None = None,
    window: int = DEFAULT_WINDOW,
    min_samples: int = MIN_SAMPLES,
) -> dict:
    """计算各品种收益率两两相关矩阵（数据契约）。

    Args:
        returns_by_code: {code: [{"date": str, "return": float}, ...]}，日收益升序。
        names_by_code: {code: name}，缺失时回退 code 本身。
        window: 计算窗口（每对取对齐后最近 N 期重叠样本）。
        min_samples: 对齐后有效样本下限，低于此判数据不足（格为 None）。

    Returns:
        数据契约 dict：
        {"available", "status", "window", "sample_count", "codes", "names",
         "matrix", "p_values", "pairs", "insufficient_codes", "note"}

        matrix/p_values 为 N×N 下三角（row>col 有值，对角=1.0/None，其余 None）。
    """
    names = {c: (names_by_code or {}).get(c, c) for c in returns_by_code}
    active: dict[str, list[dict]] = {}
    for c, seq in returns_by_code.items():
        _clean = [r for r in seq if _is_valid_return(r.get("return"))]
        if _clean:
            active[c] = _clean

    if len(active) < MIN_HOLDINGS:
        return unavailable_result(
            "insufficient",
            sample_count=0,
            insufficient_codes=sorted(active.keys()),
        )

    codes = list(active.keys())
    n = len(codes)
    # 预建 日期→位置 索引，避免逐对重复查找
    idx_maps: dict[str, dict[str, int]] = {}
    date_lists: dict[str, list[str]] = {}
    return_lists: dict[str, list[float]] = {}
    for c in codes:
        dates = [r["date"] for r in active[c]]
        idx_maps[c] = {d: i for i, d in enumerate(dates)}
        date_lists[c] = dates
        return_lists[c] = [float(r["return"]) for r in active[c]]

    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]
    p_values: list[list[float | None]] = [[None] * n for _ in range(n)]
    pairs: list[dict] = []
    insufficient_codes: set[str] = set()
    max_samples = 0

    for i in range(n):
        matrix[i][i] = 1.0  # 对角线 = 自相关
        ci = codes[i]
        for j in range(i + 1, n):
            cj = codes[j]
            common = sorted(set(date_lists[ci]) & set(date_lists[cj]))
            win_dates = common[-window:]
            if len(win_dates) < min_samples:
                insufficient_codes.add(ci)
                insufficient_codes.add(cj)
                continue
            xi = [return_lists[ci][idx_maps[ci][d]] for d in win_dates]
            xj = [return_lists[cj][idx_maps[cj][d]] for d in win_dates]
            r, p = _pearson_pvalue(xi, xj)
            # 下三角：matrix[行=后序][列=前序] 存 r
            matrix[j][i] = round(r, 4)
            p_values[j][i] = round(p, 6)
            max_samples = max(max_samples, len(win_dates))
            pairs.append(
                {
                    "code_a": cj,
                    "name_a": names.get(cj, cj),
                    "code_b": ci,
                    "name_b": names.get(ci, ci),
                    "pearson": round(r, 4),
                    "p_value": round(p, 6),
                    "significant": p < SIGNIFICANCE_LEVEL,
                    "samples": len(win_dates),
                }
            )

    if not pairs:
        return unavailable_result(
            "insufficient",
            sample_count=max_samples,
            insufficient_codes=sorted(insufficient_codes),
        )

    pairs.sort(key=lambda x: abs(x["pearson"]), reverse=True)
    return {
        "available": True,
        "status": "ok",
        "window": min(window, max_samples) if max_samples else window,
        "sample_count": max_samples,
        "codes": codes,
        "names": names,
        "matrix": matrix,
        "p_values": p_values,
        "pairs": pairs,
        "insufficient_codes": sorted(insufficient_codes),
        "note": "",
    }


# ═══════════════════════════════════════════════════════════════
#  滚动趋势：组合平均相关性 + 重点品对滚动相关
# ═══════════════════════════════════════════════════════════════


def _pearson_r(x: list[float], y: list[float]) -> float | None:
    """Pearson r（滚动趋势专用，不算 p 值——端点量大，省 t 分布开销）。

    Args:
        x, y: 对齐后的日收益序列（同长）。

    Returns:
        r ∈ [-1, 1]；序列过短或任一方常数（方差为 0）时返回 None（该端点不计入）。
    """
    n = len(x)
    if n < 3:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx < _CONSTANT_EPS or sy < _CONSTANT_EPS:
        return None
    return max(-1.0, min(1.0, num / (sx * sy)))


def _rolling_unavailable(status: str) -> dict:
    """滚动趋势不可用结果（数据契约，全键在位、结构空壳）。"""
    return {
        "available": False,
        "status": status,
        "windows": list(ROLLING_WINDOWS),
        "min_samples": MIN_SAMPLES,
        "portfolio": {str(w): [] for w in ROLLING_WINDOWS},
        "focus_pairs": [],
        "coverage": {"dates": 0, "first_date": "", "last_date": "", "full_window_from": {}},
        "notes": [],
    }


def compute_rolling_correlations(
    returns_by_code: dict[str, list[dict]],
    names_by_code: dict[str, str] | None = None,
    windows: tuple[int, ...] = ROLLING_WINDOWS,
    min_samples: int = MIN_SAMPLES,
    focus_pairs: list[tuple[str, str]] | None = None,
    max_focus: int = 3,
) -> dict:
    """滚动相关性趋势（数据契约）：组合平均相关性 + 重点品对滚动相关。

    口径（notes 单源外送，渲染层只引用不复述）：

    - **端点轴** = 全品种日期并集（升序）；所有序列共享同一条 dates 轴，
      重点品对在自有重叠日期上算 r 后 LOCF（前值结转）对齐到端点轴。
    - **组合平均** = 每个端点上「已可算」的全部两两 Pearson r 的均值；
      参与对需重叠样本 ≥ min_samples，n_pairs 记录该端点参与对数。
    - **端点窗** = min(窗口, 该对可得重叠期数)——历史长度不足时按可得
      区间截断计算（而非整段缺席），coverage.full_window_from 记录每个
      窗口达到完整窗的起始端点（None = 全程未达），notes 标注截断口径。
    - 重点品对由调用方给定（通常取静态矩阵 |r| 降序前 N），非法代码对跳过。
    - 纯计算：不碰数据获取、不依赖 report 层；序列降采样（downsample）
      由编排层负责，本函数返回原始端点序列。

    Args:
        returns_by_code: 同 `compute_correlation_matrix`（日收益升序）。
        names_by_code: {code: name}，缺失回退 code。
        windows: 滚动端点窗集合（默认 60/120）。
        min_samples: 单对计入所需的最小重叠样本（不足则该对端点跳过）。
        focus_pairs: 重点品对 [(code_a, code_b), ...]（可空 = 不输出品对序列）。
        max_focus: 重点品对输出上限（截断给定列表）。

    Returns:
        数据契约 dict：
        {"available", "status", "windows", "min_samples", "portfolio",
         "focus_pairs", "coverage", "notes"}

        portfolio: {str(w): [{"date", "value", "n_pairs"}, ...]}
        focus_pairs: [{"code_a", "name_a", "code_b", "name_b",
                       "series": {str(w): [{"date", "value"}, ...]}}]
        coverage: {"dates", "first_date", "last_date",
                   "full_window_from": {str(w): date|None}}
        数据不足（品种 <2 或无日期）→ available=False、status="insufficient"，
        结构键仍在（渲染层无需分支判空）。
    """
    names = {c: (names_by_code or {}).get(c, c) for c in returns_by_code}
    active: dict[str, list[dict]] = {}
    for c, seq in returns_by_code.items():
        clean = [r for r in seq if _is_valid_return(r.get("return"))]
        if clean:
            active[c] = clean

    if len(active) < MIN_HOLDINGS:
        return _rolling_unavailable("insufficient")

    value_by_code: dict[str, dict[str, float]] = {
        c: {r["date"]: float(r["return"]) for r in seq} for c, seq in active.items()
    }
    all_dates = sorted(set().union(*(v.keys() for v in value_by_code.values())))
    if not all_dates:
        return _rolling_unavailable("insufficient")

    codes = list(active.keys())

    # ── 逐对：自有重叠日期上的滚动 r（每窗一条 (date, r) 序列） ──
    pair_entries: dict[tuple[str, str], dict] = {}
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            ca, cb = codes[i], codes[j]
            common = sorted(value_by_code[ca].keys() & value_by_code[cb].keys())
            if len(common) < min_samples:
                continue
            xs = [value_by_code[ca][d] for d in common]
            ys = [value_by_code[cb][d] for d in common]
            series: dict[str, list[tuple[str, float]]] = {}
            full_from: dict[str, str | None] = {}
            for w in windows:
                pts: list[tuple[str, float]] = []
                first_full: str | None = None
                for t in range(min_samples - 1, len(common)):
                    span = min(w, t + 1)
                    r = _pearson_r(xs[t - span + 1 : t + 1], ys[t - span + 1 : t + 1])
                    if r is None:
                        continue
                    pts.append((common[t], round(r, 4)))
                    if span >= w and first_full is None:
                        first_full = common[t]
                series[str(w)] = pts
                full_from[str(w)] = first_full
            pair_entries[(ca, cb)] = {
                "series": series,
                "full_from": full_from,
                "count": len(common),
            }

    if not pair_entries:
        return _rolling_unavailable("insufficient")

    # ── 组合平均：端点轴上逐窗聚合（LOCF 取各对 ≤ 端点的最新 r） ──
    portfolio: dict[str, list[dict]] = {}
    full_window_from: dict[str, str | None] = {}
    for w in windows:
        wk = str(w)
        pointers = {key: 0 for key in pair_entries}
        points: list[dict] = []
        first_full_date: str | None = None
        for d in all_dates:
            total = 0.0
            n_pairs = 0
            has_full = False
            for key, entry in pair_entries.items():
                pts = entry["series"][wk]
                ptr = pointers[key]
                if ptr < len(pts) and pts[ptr][0] <= d:
                    # 前进到 ≤ d 的最后一条（每端点最多前进若干步）
                    while ptr + 1 < len(pts) and pts[ptr + 1][0] <= d:
                        ptr += 1
                    pointers[key] = ptr
                    total += pts[ptr][1]
                    n_pairs += 1
                    if entry["full_from"][wk] is not None and entry["full_from"][wk] <= d:
                        has_full = True
            if n_pairs == 0:
                continue
            points.append({"date": d, "value": round(total / n_pairs, 4), "n_pairs": n_pairs})
            if has_full and first_full_date is None:
                first_full_date = d
        portfolio[wk] = points
        full_window_from[wk] = first_full_date

    if not any(portfolio.values()):
        return _rolling_unavailable("insufficient")

    # ── 重点品对：给定列表过滤非法，截断到上限，LOCF 对齐端点轴 ──
    focus_out: list[dict] = []
    for ca, cb in (focus_pairs or [])[:max_focus]:
        key = (ca, cb) if (ca, cb) in pair_entries else ((cb, ca) if (cb, ca) in pair_entries else None)
        if key is None:
            continue
        entry = pair_entries[key]
        focus_series: dict[str, list[dict]] = {}
        for w in windows:
            wk = str(w)
            pts = entry["series"][wk]
            aligned: list[dict] = []
            ptr = 0
            last_value: float | None = None
            # 与组合平均同一端点网格：从组合首个有效端点起 LOCF 前值结转
            for p in portfolio[wk]:
                while ptr < len(pts) and pts[ptr][0] <= p["date"]:
                    last_value = pts[ptr][1]
                    ptr += 1
                if last_value is not None:
                    aligned.append({"date": p["date"], "value": last_value})
            focus_series[wk] = aligned
        focus_out.append(
            {
                "code_a": key[0],
                "name_a": names.get(key[0], key[0]),
                "code_b": key[1],
                "name_b": names.get(key[1], key[1]),
                "series": focus_series,
            }
        )

    # ── 口径与截断标注（notes 单源，渲染层原样列出） ──
    notes = [
        "组合平均相关性 = 每个滚动端点上全部两两 Pearson r 的均值"
        f"（参与对重叠样本 ≥ {min_samples} 期才计入，n_pairs 见序列）；"
        "端点窗 = min(窗口, 该对可得重叠期数)",
    ]
    max_common = max(e["count"] for e in pair_entries.values())
    for w in windows:
        wk = str(w)
        if max_common < w:
            notes.append(f"历史仅 {max_common} 期重叠 < {w} 日窗，该窗全程按可得区间截断计算")
        elif full_window_from.get(wk) and full_window_from[wk] != portfolio[wk][0]["date"]:
            notes.append(f"{w} 日窗完整重叠自 {full_window_from[wk]} 起，此前端点按可得区间（<{w} 期）计算")
    if not focus_out:
        notes.append("重点品对：无可计算对（重叠样本不足），仅输出组合平均趋势")

    return {
        "available": True,
        "status": "ok",
        "windows": list(windows),
        "min_samples": min_samples,
        "portfolio": portfolio,
        "focus_pairs": focus_out,
        "coverage": {
            "dates": len(all_dates),
            "first_date": all_dates[0],
            "last_date": all_dates[-1],
            "full_window_from": full_window_from,
        },
        "notes": notes,
    }
