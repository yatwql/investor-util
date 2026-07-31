"""辅助数学函数 — Beta/t-分布统计函数。

提取自 ``analysis/metrics.py``，供 ``portfolio_beta_analysis`` 等函数使用。
所有函数均为纯数学计算，无外部依赖（仅标准库 ``math``）。

函数清单：
  _log_beta(a, b)              Beta 函数自然对数
  _incomplete_beta_series()    正则化不完全 Beta 函数（幂级数）
  _incomplete_beta_cf()        正则化不完全 Beta 函数（混合算法）
  _t_cdf(t, df)                t 分布 CDF
  _t_critical_95(df)           95% 双尾 t 临界值
  _beta_se(returns, bench, β)  Beta 标准误
"""

from __future__ import annotations

import math
from typing import Any

# ── 常量 ────────────────────────────────────────────────

_MIN_SAMPLE_DAYS = 20
"""最小样本天数（与 metrics.py 一致，供 _beta_se 使用）。"""


# ── t 分布辅助函数（纯 math，无 scipy 依赖） ──────


def _log_beta(a: float, b: float) -> float:
    """Beta 函数的自然对数：ln(B(a,b)) = ln(Γ(a)) + ln(Γ(b)) - ln(Γ(a+b))

    Args:
        a: 形状参数 > 0
        b: 形状参数 > 0

    Returns:
        ln(B(a,b))
    """
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _incomplete_beta_series(a: float, b: float, x: float) -> float:
    """使用幂级数展开计算正则化不完全 Beta 函数 I_x(a,b)。

    对 x 较小（x < (a+1)/(a+b+2)）时稳定收敛。
    级数：I_x(a,b) = x^a(1-x)^b / (a·B(a,b)) · Σ(d_k · x^k/(a+k))
    其中 d_0=1, d_k = d_{k-1}·(a+b+k-1)/(a+k)

    Args:
        a: 形状参数 > 0
        b: 形状参数 > 0
        x: [0, 1] 区间

    Returns:
        I_x(a, b) 值
    """
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - lbeta) / a

    # 幂级数求和
    total = 1.0
    term = 1.0
    for k in range(1, 501):
        term *= (a + b + k - 1.0) * x / (a + k)
        total += term
        if abs(term) < 1e-14 * abs(total):
            break

    return front * total


def _incomplete_beta_cf(a: float, b: float, x: float) -> float:
    """正则化不完全 Beta 函数 I_x(a,b) — 混合算法。

    当 x 较小（级数收敛快）时使用幂级数展开，
    当 x 较大时使用对称性 I_x(a,b) = 1 - I_(1-x)(b,a)。

    这避免了 Lentz 连分数法在 a < 1 时的不收敛问题。

    Args:
        a: 形状参数 > 0
        b: 形状参数 > 0
        x: [0, 1] 区间

    Returns:
        I_x(a, b) 值
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    # 对称性：确保级数中使用的 x 较小
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _incomplete_beta_series(b, a, 1.0 - x)
    return _incomplete_beta_series(a, b, x)


def _t_cdf(t: float, df: int) -> float:
    """t 分布的累积分布函数。

    P(T ≤ t) = 1 - 0.5 * I(df/(df+t²), df/2, 0.5)   for t >= 0

    Args:
        t: t 统计量
        df: 自由度

    Returns:
        累积概率 [0, 1]
    """
    if df <= 0:
        return 0.5

    x = df / (df + t * t)
    if x <= 0:
        return 1.0
    if x >= 1:
        return 0.0

    p = _incomplete_beta_cf(df / 2, 0.5, x)
    if t >= 0:
        return 1.0 - 0.5 * p
    else:
        return 0.5 * p


def _t_critical_95(df: int) -> float:
    """95% 置信水平的 t 临界值（双尾）。

    对常见自由度使用预计算表，对非常见值做线性插值。

    Args:
        df: 自由度

    Returns:
        双尾 95% 临界 t 值
    """
    # 预计算临界值表（双尾 α=0.05）
    _T95_TABLE: dict[int, float] = {
        1: 12.706,
        2: 4.303,
        3: 3.182,
        4: 2.776,
        5: 2.571,
        6: 2.447,
        7: 2.365,
        8: 2.306,
        9: 2.262,
        10: 2.228,
        11: 2.201,
        12: 2.179,
        13: 2.160,
        14: 2.145,
        15: 2.131,
        16: 2.120,
        17: 2.110,
        18: 2.101,
        19: 2.093,
        20: 2.086,
        21: 2.080,
        22: 2.074,
        23: 2.069,
        24: 2.064,
        25: 2.060,
        26: 2.056,
        27: 2.052,
        28: 2.048,
        29: 2.045,
        30: 2.042,
        35: 2.030,
        40: 2.021,
        45: 2.014,
        50: 2.009,
        60: 2.000,
        70: 1.994,
        80: 1.990,
        90: 1.987,
        100: 1.984,
        120: 1.980,
    }

    if df in _T95_TABLE:
        return _T95_TABLE[df]

    keys = sorted(_T95_TABLE.keys())
    if df < keys[0]:
        return _T95_TABLE[keys[0]]
    if df > keys[-1]:
        # 大样本近似标准正态临界值 1.96
        return 1.96

    # 线性插值
    for i in range(len(keys) - 1):
        if keys[i] < df < keys[i + 1]:
            x0, x1 = float(keys[i]), float(keys[i + 1])
            y0, y1 = _T95_TABLE[keys[i]], _T95_TABLE[keys[i + 1]]
            return y0 + (y1 - y0) * (df - x0) / (x1 - x0)

    return 1.96


def _beta_se(
    portfolio_returns: list[float],
    benchmark_returns: list[float],
    beta: float,
) -> tuple[float, int] | None:
    """计算 Beta 的标准误。

    基于 OLS 回归：SE(β̂) = sqrt(MSE / Σ(x_i - x̄)²)

    Args:
        portfolio_returns: 组合日收益率序列
        benchmark_returns: 基准日收益率序列
        beta: Beta 点估计值

    Returns:
        (标准误, 自由度) 元组，数据不足时返回 None
    """
    n = min(len(portfolio_returns), len(benchmark_returns))
    pr = portfolio_returns[-n:]
    br = benchmark_returns[-n:]

    if n < _MIN_SAMPLE_DAYS + 2:
        return None

    mean_pr = sum(pr) / n
    mean_br = sum(br) / n

    # OLS: alpha = mean_pr - beta * mean_br
    alpha = mean_pr - beta * mean_br

    # MSE = Σ(y_i - ŷ_i)² / (n - 2)
    sse = sum((pr[i] - (alpha + beta * br[i])) ** 2 for i in range(n))
    mse = sse / (n - 2)

    # Σ(x_i - x̄)²
    ssx = sum((br[i] - mean_br) ** 2 for i in range(n))

    if ssx == 0 or mse < 0:
        return None

    se = math.sqrt(mse / ssx)
    return (se, n - 2)
