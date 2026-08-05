"""风险类量化指标子模块 — 集中度/胜率/换手/风险贡献/波动率/Beta。

承载持仓分布与风险类指标的纯计算函数。每函数为纯计算函数，消费调用方传入的
数据，返回指标值或 None。

设计原则：
  - 纯函数：不依赖任何全局状态，不读写文件
  - 防御式：NaN/Inf/空列表/不足样本量 → None（配合截断保护）
  - 单向依赖：仅引用 analysis 层（metrics_returns 收益口径、_math_utils 统计辅助），
    不导入 report/ 下的任何模块

本模块被 metrics.py（聚合门面）引用。
"""

from __future__ import annotations

import logging
import math

from src.python.analysis._math_utils import (
    _beta_se,
    _t_cdf,
    _t_critical_95,
)
from src.python.analysis.metrics_returns import (
    _MIN_SAMPLE_DAYS,
    _TRADING_DAYS_PER_YEAR,
    sanitize_metric,
)

logger = logging.getLogger("invest")

__all__ = [
    "hhi",
    "win_rate",
    "turnover_rate",
    "risk_contribution",
    "get_dividend_yield",
    "individual_volatility",
    "portfolio_beta",
    "portfolio_beta_analysis",
]


# ── HHI 集中度指数 ──────────────────────────────


def hhi(weights: list[float]) -> float:
    """计算 Herfindahl-Hirschman 集中度指数。

    HHI = Σ(wi²)，其中 wi 为第 i 品种的市值权重（百分比小数，如 0.15=15%）。

    Args:
        weights: 各品种市值权重列表。不要求归一化（函数内部自动归一化）。

    Returns:
        HHI 值（0~1 之间），等效集中品种数可在调用方计算为 1/HHI。
        空列表时返回 0。
    """
    if not weights:
        return 0.0

    total = sum(abs(w) for w in weights)
    if total == 0:
        return 0.0

    normalized = [w / total for w in weights]
    hhi_val = sum(w * w for w in normalized)
    return sanitize_metric(hhi_val, 0.0)


# ── 持仓胜率 ────────────────────────────────────


def win_rate(holdings: list[dict]) -> dict:
    """计算持仓胜率——盈利品种占比。

    附盈利/亏损品种列表。

    Args:
        holdings: 持仓详情列表，每项至少含 "name", "code", "profit"（盈亏金额）键。
                profit > 0 表示盈利，profit < 0 表示亏损。

    Returns:
        {
            "win_rate": float,        # 胜率（盈利品种数/总品种数，0~1）
            "winning": [str, ...],     # 盈利品种名称列表
            "losing": [str, ...],      # 亏损品种名称列表
            "zero": [str, ...],        # 持平品种名称列表
        }
    """
    winning: list[str] = []
    losing: list[str] = []
    zero: list[str] = []

    for h in holdings:
        name = h.get("name", h.get("code", "未知"))
        profit = h.get("profit", 0)
        if profit is None:
            profit = 0
        try:
            profit = float(profit)
        except (ValueError, TypeError):
            profit = 0

        if profit > 0:
            winning.append(name)
        elif profit < 0:
            losing.append(name)
        else:
            zero.append(name)

    total = len(holdings)
    wr = len(winning) / total if total > 0 else 0.0

    return {
        "win_rate": sanitize_metric(wr, 0.0),
        "winning": winning,
        "losing": losing,
        "zero": zero,
    }


# ── 换手率 ──────────────────────────────────────


def turnover_rate(
    holdings_before: list[dict],
    holdings_after: list[dict],
) -> float | None:
    """估算组合换手率。

    基于两期持仓的变化量：
      turnover = Σ|w_new_i - w_old_i| / 2

    Args:
        holdings_before: 上期持仓详情列表，每项含 "code"、"market_value" 键
        holdings_after: 本期持仓详情列表，每项含 "code"、"market_value" 键

    Returns:
        换手率（0~1 之间），数据不足时返回 None
    """
    if not holdings_before or not holdings_after:
        return None

    # 计算两期总市值
    old_total = sum(abs(h.get("market_value", 0) or 0) for h in holdings_before)
    new_total = sum(abs(h.get("market_value", 0) or 0) for h in holdings_after)

    if old_total == 0 or new_total == 0:
        return None

    # 构造权重映射
    old_weights: dict[str, float] = {}
    for h in holdings_before:
        code = h.get("code", "")
        old_weights[code] = abs(h.get("market_value", 0) or 0) / old_total

    new_weights: dict[str, float] = {}
    for h in holdings_after:
        code = h.get("code", "")
        new_weights[code] = abs(h.get("market_value", 0) or 0) / new_total

    # 计算差异总和
    all_codes = set(old_weights.keys()) | set(new_weights.keys())
    total_diff = sum(abs(new_weights.get(code, 0) - old_weights.get(code, 0)) for code in all_codes)

    turnover = total_diff / 2.0
    return sanitize_metric(turnover)


# ── 持仓风险贡献 ────────────────────────────────


def risk_contribution(
    weights: list[float],
    volatilities: list[float],
) -> list[dict]:
    """计算各品种对组合的总风险贡献（简化版，非 Euler 分解）。

    使用 Risk Contribution = wi × σi / Σ(wj × σj)

    Args:
        weights: 各品种市值权重列表（需归一化的 0~1 值）
        volatilities: 各品种年化波动率列表（与 weights 等长）

    Returns:
        [{name: str, weight: float, volatility: float, contribution: float, rank: int}, ...]
        按 contribution 降序排列。空列表表示输入异常。
    """
    if len(weights) != len(volatilities) or not weights:
        return []

    # 清理数据
    clean_pairs: list[tuple[float, float]] = []
    for w, v in zip(weights, volatilities):
        cw = sanitize_metric(w, 0.0)
        cv = sanitize_metric(v, 0.0)
        if cw is None or cv is None:
            cw, cv = 0.0, 0.0
        clean_pairs.append((cw, cv))

    total_risk = sum(w * v for w, v in clean_pairs)
    if total_risk == 0:
        # 所有波动率为零 → 无法计算贡献度
        return []

    result = []
    for i, (w, v) in enumerate(clean_pairs):
        contribution = (w * v) / total_risk
        result.append(
            {
                "index": i,
                "weight": round(w, 4),
                "volatility": round(v, 4),
                "contribution": round(contribution, 4),
                "rank": 0,  # 排序后填充
            }
        )

    # 按贡献降序排列
    result.sort(key=lambda x: x["contribution"], reverse=True)
    for rank, item in enumerate(result, 1):
        item["rank"] = rank

    return result


# ── 分红数据 ────────────────────────────────────


def get_dividend_yield(code: str) -> float | None:
    """获取指定品种的年均股息率。

    从缓存读取股票历史分红数据，计算年均每股分红 / 当前价格。

    Args:
        code: 证券代码

    Returns:
        股息率（如 0.03=3%），数据不可用时返回 None
    """
    try:
        from src.python import cache as _cache

        data = _cache.get(f"dividend_{code}", ttl=86400 * 30)
        if not data or not isinstance(data, list):
            return None

        # 计算年均每股分红
        total_dividend = 0.0
        years: set[str] = set()
        for item in data:
            year = item.get("year", "") or item.get("date", "")[:4]
            amount = item.get("dividend", 0) or item.get("amount", 0) or item.get("cash_dividend", 0)
            try:
                total_dividend += float(amount)
                years.add(str(year))
            except (ValueError, TypeError):
                continue

        if not years:
            return None

        avg_annual = total_dividend / len(years) if years else 0.0
        if avg_annual <= 0:
            return None

        # 获取当前价格
        price_data = _cache.get(f"price_{code}", ttl=86400)
        if not price_data:
            return None

        if isinstance(price_data, dict):
            current_price = price_data.get("price", 0) or price_data.get("close", 0)
        elif isinstance(price_data, (int, float)):
            current_price = float(price_data)
        else:
            return None

        if current_price and current_price > 0:
            return sanitize_metric(avg_annual / current_price)

        return None
    except Exception:
        logger.warning("[metrics] 获取 %s 股息率失败", code, exc_info=True)
        return None


# ── 个股波动率 ──────────────────────────────────


def individual_volatility(
    individual_daily_returns: dict[str, list[float]],
    annualize: bool = True,
    trading_days: int = _TRADING_DAYS_PER_YEAR,
) -> dict[str, float | None]:
    """计算各品种的年化波动率。

    Args:
        individual_daily_returns: {code: [daily_return, ...]} 字典
        annualize: 是否年化（默认 True）
        trading_days: 年化交易日数

    Returns:
        {code: 年化波动率 or None（数据不足）}
    """
    result: dict[str, float | None] = {}
    for code, returns in individual_daily_returns.items():
        if not returns or len(returns) < _MIN_SAMPLE_DAYS:
            result[code] = None
            continue

        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        # 使用 epsilon 容差避免 Linux/Windows 浮点精度差异
        _VAR_EPS = 1e-15
        if variance < _VAR_EPS:
            result[code] = 0.0
            continue

        daily_vol = math.sqrt(variance)
        if annualize:
            result[code] = sanitize_metric(daily_vol * math.sqrt(trading_days))
        else:
            result[code] = sanitize_metric(daily_vol)

    return result


# ── 组合 Beta（协方差法） ───────────────────────


def portfolio_beta(
    portfolio_returns: list[float],
    benchmark_returns: list[float],
    trading_days: int = _TRADING_DAYS_PER_YEAR,
) -> float | None:
    """计算组合 Beta（协方差法）。

    Beta = Cov(Rp, Rm) / Var(Rm)

    使用 252 日窗口，不足 20 日返回 None。

    Args:
        portfolio_returns: 组合日收益率序列
        benchmark_returns: 基准（沪深300）日收益率序列
        trading_days: 年化交易日数（用于日志，不影响计算）

    Returns:
        Beta 值，数据不足时返回 None
    """
    if len(portfolio_returns) < _MIN_SAMPLE_DAYS or len(benchmark_returns) < _MIN_SAMPLE_DAYS:
        return None

    # 对齐长度
    n = min(len(portfolio_returns), len(benchmark_returns))
    pr = portfolio_returns[-n:]
    br = benchmark_returns[-n:]

    if n < _MIN_SAMPLE_DAYS:
        return None

    mean_pr = sum(pr) / n
    mean_br = sum(br) / n

    cov = sum((pr[i] - mean_pr) * (br[i] - mean_br) for i in range(n)) / (n - 1)
    var_br = sum((br[i] - mean_br) ** 2 for i in range(n)) / (n - 1)

    if var_br == 0:
        return None

    beta = cov / var_br
    return sanitize_metric(beta)


# ── 组合 Beta 置信区间与统计检验 ──────────────


def portfolio_beta_analysis(
    portfolio_returns: list[float],
    benchmark_returns: list[float],
) -> dict | None:
    """组合 Beta 置信区间 + 统计检验。

    在 portfolio_beta 的点估计基础上增加：
      - 95% 置信区间（基于 OLS 标准误 + t 分布）
      - t 统计量 + p 值（判断 Beta 是否显著 ≠ 0）
      - 置信区间过宽（> 1.5）时标记为不可靠

    Args:
        portfolio_returns: 组合日收益率序列
        benchmark_returns: 基准日收益率序列

    Returns:
        {beta, ci_lower, ci_upper, t_stat, p_value, reliable, df}
        数据不足时返回 None
    """
    beta = portfolio_beta(portfolio_returns, benchmark_returns)
    if beta is None:
        return None

    se_result = _beta_se(portfolio_returns, benchmark_returns, beta)
    if se_result is None:
        return {
            "beta": beta,
            "ci_lower": None,
            "ci_upper": None,
            "t_stat": None,
            "p_value": None,
            "reliable": False,
            "df": 0,
        }

    se, df = se_result
    if se <= 0:
        if beta is not None and se == 0.0:
            # 完美预测：t 统计量无穷大，CI 为零宽度
            return {
                "beta": sanitize_metric(beta),
                "ci_lower": sanitize_metric(beta),
                "ci_upper": sanitize_metric(beta),
                "t_stat": None,
                "p_value": 0.0,
                "reliable": True,
                "df": df,
            }
        return {
            "beta": beta,
            "ci_lower": None,
            "ci_upper": None,
            "t_stat": None,
            "p_value": None,
            "reliable": False,
            "df": df,
        }

    t_stat = beta / se if se > 0 else None
    p_value = _t_cdf(-abs(t_stat), df) * 2 if t_stat is not None else None

    t_crit = _t_critical_95(df)
    ci_half = t_crit * se
    ci_lower = sanitize_metric(beta - ci_half)
    ci_upper = sanitize_metric(beta + ci_half)

    ci_width = (ci_upper or 0) - (ci_lower or 0)
    reliable = ci_width <= 1.5 and beta is not None

    return {
        "beta": sanitize_metric(beta),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "t_stat": sanitize_metric(t_stat),
        "p_value": sanitize_metric(p_value),
        "reliable": reliable,
        "df": df,
    }
