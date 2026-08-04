"""持仓相关性矩阵 — 纯计算层。

职责：接收各品种日收益序列 → 按日期对齐 → 逐对 Pearson 相关 + 双侧 p 值
      → 输出 N×N 下三角相关矩阵 + 配对明细（识别"伪分散"）。

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
# 拉取条数（编排层使用，预留对齐/dropna 头部损耗，与 factor_exposure 一致）
FETCH_DAYS: int = 90
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
