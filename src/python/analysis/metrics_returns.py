"""收益类量化指标子模块 — 日收益率口径 + 数值清理 + 收益/回撤指标。

自 `metrics.py` 拆出（超限文件拆分重构），承载收益口径与收益类指标的纯计算函数，
每函数为纯计算函数，消费调用方传入的数据（形态为 list[float] 或 dict），
返回指标值或 None。

设计原则（继承自 metrics.py）：
  - 纯函数：不依赖任何全局状态，不读写文件
  - 防御式：NaN/Inf/空列表/不足样本量 → None（配合截断保护）
  - 单向依赖：不导入 report/ 下的任何模块（analysis 层约束）

本模块被 metrics.py（聚合门面）与 metrics_risk.py（风险类指标）引用。
"""

from __future__ import annotations

import math
from typing import Any

# ── 常量 ────────────────────────────────────────────────

_TRADING_DAYS_PER_YEAR = 252
"""A 股年化交易日数（用于年化波动率和夏普比率）。"""

_MIN_SAMPLE_DAYS = 20
"""最小样本天数：不足此天数的指标置信度降为 low 或返回 None。"""

_MAX_DRAWDOWN_EPSILON = 0.001
"""最大回撤下限：当 max_drawdown < 0.1% 时卡玛比率返回 None。"""

_RISK_FREE_RATE_DEFAULT = 0.015
"""无风险利率默认值（当传入的 rf 为 None 时使用，约 1.5%）。"""

__all__ = [
    "compute_daily_returns",
    "compute_portfolio_peak_mv",
    "sharpe_ratio",
    "calmar_ratio",
    "annualized_return",
    "max_drawdown_pct",
    "sanitize_metric",
    "truncate_extreme_values",
    "check_data_sufficiency",
    "get_confidence_level",
]


# ── 日收益率口径（统一源） ──────────────────────


def compute_daily_returns(bars: list[dict[str, Any]] | None) -> list[float]:
    """从组合时间线 bars 计算日收益率序列（口径统一源）。

    统一口径（tail_risk 与走势表同口径）：日收益 = (curr - prev) / prev，
    小数单位（0.01 = 1%）。仅当 prev 与 curr 市值均 > 0 才计入——缺失/占位/清仓
    （curr ≤ 0）不构成有效收益，跳过以避免伪 -100% 单日污染
    VaR/最大单日跌幅/年化波动率等指标。序号 i 对应 bars[i+1]
    （收益在 bars[i+1]["date"] 实现）。

    Args:
        bars: [{"date": ..., "total_value": float, ...}, ...] 按日期升序。
            None/空列表返回 []。

    Returns:
        日收益率序列（小数）。
    """
    returns: list[float] = []
    if not bars:
        return returns
    for i in range(1, len(bars)):
        prev = float(bars[i - 1].get("total_value") or 0.0)
        curr = float(bars[i].get("total_value") or 0.0)
        # 首尾任一 ≤0（缺失/占位/清仓）都不构成有效收益，跳过（避免伪 -100% 单日）
        if prev > 0 and curr > 0:
            returns.append((curr - prev) / prev)
    return returns


def compute_portfolio_peak_mv(bars: list[dict[str, Any]] | None) -> float | None:
    """从组合时间线 bars 计算组合历史峰值市值。

    回撤纪律（组合级回撤规则）以「历史峰值」为基准：峰值 = bars 中
    total_value 的最大值（含首日）。None/空序列/无正值 → None，调用方按
    「峰值未知」处理（组合回撤纪律不激活）。仅计 total_value > 0 的交易日，
    与日收益率口径一致——缺失/占位/清仓（≤0）不参与峰值。

    Args:
        bars: [{"date": ..., "total_value": float, ...}, ...] 按日期升序。

    Returns:
        组合历史峰值市值（float）或 None（无有效数据）。
    """
    if not bars:
        return None
    positive = [float(b.get("total_value") or 0.0) for b in bars if float(b.get("total_value") or 0.0) > 0]
    if not positive:
        return None
    return max(positive)


# ── 数值清理（截断保护） ──────────────────────────


def sanitize_metric(value: Any, default: Any = None) -> Any:
    """清理指标值：NaN/Inf → default。

    Args:
        value: 原始值
        default: 替换值（默认 None）

    Returns:
        清理后的值
    """
    if value is None:
        return default
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return default
    return value


def truncate_extreme_values(
    series: list[float],
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
) -> list[float]:
    """截断极端值：低于 lower_quantile 或高于 upper_quantile 的值被替换为边界值。

    Args:
        series: 输入序列
        lower_quantile: 下限分位数（默认 0.01）
        upper_quantile: 上限分位数（默认 0.99）

    Returns:
        截断后的新序列
    """
    if not series:
        return []
    sorted_s = sorted(series)
    n = len(sorted_s)
    lower_idx = max(0, int(n * lower_quantile))
    upper_idx = min(n - 1, int(n * upper_quantile))
    lower_bound = sorted_s[lower_idx]
    upper_bound = sorted_s[upper_idx]
    return [max(lower_bound, min(v, upper_bound)) for v in series]


def check_data_sufficiency(daily_returns: list[float], min_days: int = _MIN_SAMPLE_DAYS) -> int:
    """检查数据充分性。

    Args:
        daily_returns: 日收益率序列
        min_days: 最少所需天数

    Returns:
        0 = 数据不足（返回 None），1 = 低置信度，2 = 高置信度
    """
    if not daily_returns or len(daily_returns) < min_days:
        return 0
    if len(daily_returns) < _TRADING_DAYS_PER_YEAR:
        return 1  # low confidence
    return 2  # high confidence


def get_confidence_level(daily_returns: list[float] | None, min_days: int = _MIN_SAMPLE_DAYS) -> str:
    """获取置信度等级描述。

    Args:
        daily_returns: 日收益率序列
        min_days: 最少所需天数

    Returns:
        "insufficient" / "low" / "high"
    """
    level = check_data_sufficiency(daily_returns or [], min_days)
    return {0: "insufficient", 1: "low", 2: "high"}.get(level, "insufficient")


# ── 夏普比率 ────────────────────────────────────


def sharpe_ratio(
    portfolio_daily_returns: list[float],
    rf_annual: float | None = None,
    trading_days: int = _TRADING_DAYS_PER_YEAR,
) -> float | None:
    """计算年化夏普比率。

    Sharpe = (Rp - Rf) / σp

    Args:
        portfolio_daily_returns: 组合日收益率序列（百分比小数，如 0.01=1%）
        rf_annual: 年化无风险利率（如 0.0175=1.75%），None 时使用默认值
        trading_days: 年化交易日数

    Returns:
        年化夏普比率，数据不足时返回 None
    """
    if check_data_sufficiency(portfolio_daily_returns) == 0:
        return None

    rf = rf_annual if rf_annual is not None else _RISK_FREE_RATE_DEFAULT
    rf_daily = rf / trading_days

    mean_daily_return = sum(portfolio_daily_returns) / len(portfolio_daily_returns)
    excess_daily = mean_daily_return - rf_daily

    # 计算日收益率标准差
    if len(portfolio_daily_returns) < 2:
        return None
    variance = sum((r - mean_daily_return) ** 2 for r in portfolio_daily_returns) / (len(portfolio_daily_returns) - 1)
    # 使用 epsilon 容差避免 Linux/Windows 浮点精度差异
    _VARIANCE_EPSILON = 1e-15
    if variance < _VARIANCE_EPSILON:
        return None  # 波动率为零 → 夏普无意义
    daily_vol = math.sqrt(variance)

    # 年化
    annual_excess = excess_daily * trading_days
    annual_vol = daily_vol * math.sqrt(trading_days)

    if annual_vol == 0:
        return None

    result = annual_excess / annual_vol
    return sanitize_metric(result)


# ── 卡玛比率 ────────────────────────────────────


def calmar_ratio(
    portfolio_daily_returns: list[float],
    trading_days: int = _TRADING_DAYS_PER_YEAR,
) -> float | None:
    """计算卡玛比率（年化收益率 / 最大回撤）。

    Calmar = 年化收益率 / 最大回撤（绝对值）

    Args:
        portfolio_daily_returns: 组合日收益率序列（百分比小数）
        trading_days: 年化交易日数

    Returns:
        卡玛比率，数据不足或最大回撤接近 0 时返回 None
    """
    annual_return = annualized_return(portfolio_daily_returns, trading_days)
    max_dd = max_drawdown_pct(portfolio_daily_returns)
    if annual_return is None or max_dd is None:
        return None

    max_dd_abs = abs(max_dd)
    if max_dd_abs < _MAX_DRAWDOWN_EPSILON:
        return None

    result = annual_return / max_dd_abs
    return sanitize_metric(result)


# ── 年化收益 / 最大回撤 ─────────────────────────


def annualized_return(
    daily_returns: list[float],
    trading_days: int = _TRADING_DAYS_PER_YEAR,
) -> float | None:
    """计算年化收益率（几何年化）。

    annualized = (Π(1+r_i))^(trading_days/n) - 1

    Args:
        daily_returns: 日收益率序列（百分比小数，如 0.01=1%）
        trading_days: 年化交易日数

    Returns:
        年化收益率（小数），数据不足时返回 None
    """
    if check_data_sufficiency(daily_returns) == 0:
        return None

    total = 1.0
    for r in daily_returns:
        total *= 1.0 + r
    result = total ** (trading_days / len(daily_returns)) - 1.0
    return sanitize_metric(result)


def max_drawdown_pct(daily_returns: list[float]) -> float | None:
    """计算最大回撤幅度（返回正数，如 0.123 = 12.3%）。

    Args:
        daily_returns: 日收益率序列（百分比小数，如 0.01=1%）

    Returns:
        最大回撤幅度（正数），数据不足时返回 None
    """
    if check_data_sufficiency(daily_returns) == 0:
        return None

    peak = 1.0
    max_dd = 0.0
    cumulative = 1.0
    for r in daily_returns:
        cumulative *= 1.0 + r
        if cumulative > peak:
            peak = cumulative
        dd = (cumulative - peak) / peak  # 负值（回撤）
        if dd < max_dd:
            max_dd = dd
    return sanitize_metric(-max_dd)
