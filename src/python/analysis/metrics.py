"""量化指标计算模块 — 组合风险/收益指标算法全集（聚合门面）。

本模块是 `analysis` 层量化指标的统一入口：
  - 收益类指标（日收益率口径 / 数值清理 / 收益回撤）→ `metrics_returns.py`
  - 风险类指标（集中度 / 胜率 / 换手 / 风险贡献 / 波动率 / Beta）→ `metrics_risk.py`
  - 本模块保留 `compute_all_metrics` 聚合入口 + `__all__` 公开清单，
    并 re-export 全部子模块符号。

设计原则：
  - 纯函数：不依赖任何全局状态，不读写文件
  - 防御式：NaN/Inf/空列表/不足样本量 → None（配合截断保护）
  - 单向依赖：不导入 report/ 下的任何模块（analysis 层约束）

指标清单：
  sharpe_ratio(portfolio_daily_returns, rf_annual) → float | None
  compute_daily_returns(bars) → list[float]
  compute_portfolio_peak_mv(bars) → float | None
  sharpe_ratio(portfolio_daily_returns, rf_annual) → float | None
  calmar_ratio(portfolio_daily_returns) → float | None
  annualized_return(daily_returns) → float | None
  max_drawdown_pct(daily_returns) → float | None
  hhi(weights) → float
  win_rate(holdings) -> dict
  turnover_rate(holdings_before, holdings_after) → float | None
  risk_contribution(weights, volatilities) → list[dict]
  get_dividend_yield(code) → float | None
  compute_all_metrics(...) → dict
  sanitize_metric(value) → float | None
  truncate_extreme_values(series) → list[float]
  check_data_sufficiency(daily_returns) → int
  get_confidence_level(daily_returns) → str
  individual_volatility(individual_daily_returns) → dict[str, float | None]
  portfolio_beta(portfolio_returns, benchmark_returns) → float | None
"""

from __future__ import annotations

from typing import Any

from src.python.analysis._math_utils import (
    _beta_se,
    _incomplete_beta_cf,
    _incomplete_beta_series,
    _log_beta,
    _t_cdf,
    _t_critical_95,
)
from src.python.analysis.metrics_returns import (  # noqa: F401
    _MAX_DRAWDOWN_EPSILON,
    _MIN_SAMPLE_DAYS,
    _RISK_FREE_RATE_DEFAULT,
    _TRADING_DAYS_PER_YEAR,
    annualized_return,
    calmar_ratio,
    check_data_sufficiency,
    compute_daily_returns,
    compute_portfolio_peak_mv,
    get_confidence_level,
    max_drawdown_pct,
    sanitize_metric,
    sharpe_ratio,
    truncate_extreme_values,
)
from src.python.analysis.metrics_risk import (  # noqa: F401
    get_dividend_yield,
    hhi,
    individual_volatility,
    portfolio_beta,
    portfolio_beta_analysis,
    risk_contribution,
    turnover_rate,
    win_rate,
)

__all__ = [
    # 日收益率口径（统一源）
    "compute_daily_returns",
    "compute_portfolio_peak_mv",
    # 指标算法
    "sharpe_ratio",
    "calmar_ratio",
    "annualized_return",
    "max_drawdown_pct",
    "hhi",
    "win_rate",
    "turnover_rate",
    "risk_contribution",
    "get_dividend_yield",
    "compute_all_metrics",
    "sanitize_metric",
    "individual_volatility",
    "portfolio_beta",
    "portfolio_beta_analysis",
    # 清理辅助函数
    "truncate_extreme_values",
    "check_data_sufficiency",
    "get_confidence_level",
]

# ── 常量（兼容外部直接引用，实现以 metrics_returns/metrics_risk 为准）──

_TRADING_DAYS_PER_YEAR = 252
"""A 股年化交易日数（用于年化波动率和夏普比率）。"""

_MIN_SAMPLE_DAYS = 20
"""最小样本天数：不足此天数的指标置信度降为 low 或返回 None。"""

_MAX_DRAWDOWN_EPSILON = 0.001
"""最大回撤下限：当 max_drawdown < 0.1% 时卡玛比率返回 None。"""

_RISK_FREE_RATE_DEFAULT = 0.015
"""无风险利率默认值（当传入的 rf 为 None 时使用，约 1.5%）。"""


# ── 全量指标聚合 ────────────────────────────────


def compute_all_metrics(
    portfolio_daily_returns: list[float],
    portfolio_weights: list[float] | None = None,
    individual_vols: dict[str, float | None] | None = None,
    benchmark_daily_returns: list[float] | None = None,
    rf_annual: float | None = None,
    holdings_details: list[dict] | None = None,
    holdings_before: list[dict] | None = None,
    holdings_after: list[dict] | None = None,
) -> dict[str, Any]:
    """计算全量量化指标。

    整合所有指标计算，返回结构化字典。
    每个指标均带置信度标记和清理后的值。

    Args:
        portfolio_daily_returns: 组合日收益率序列
        portfolio_weights: 各品种市值权重列表
        individual_vols: {code: 波动率} 字典
        benchmark_daily_returns: 基准日收益率序列
        rf_annual: 年化无风险利率
        holdings_details: 持仓详情列表（用于胜率、分红等）
        holdings_before: 上期持仓详情（用于换手率）
        holdings_after: 本期持仓详情（用于换手率）

    Returns:
        {
            "sharpe_ratio": float | None,
            "sharpe_confidence": str,
            "calmar_ratio": float | None,
            "calmar_confidence": str,
            "hhi": float | None,
            "hhi_equivalent": float | None,  # 1/HHI
            "win_rate": ...,                   # win_rate() 输出的字典
            "turnover_rate": float | None,
            "individual_volatility": dict | None,
            "portfolio_beta": float | None,
            "beta_confidence": str,
            "risk_contributions": list[dict],
        }
    """
    confidence = get_confidence_level(portfolio_daily_returns)
    data_sufficient = confidence != "insufficient"

    # 01 夏普比率
    sharpe_val = None
    if data_sufficient:
        sharpe_val = sharpe_ratio(portfolio_daily_returns, rf_annual)

    # 02 卡玛比率
    calmar_val = None
    if data_sufficient:
        calmar_val = calmar_ratio(portfolio_daily_returns)

    # 03 HHI
    hhi_val = None
    hhi_equiv = None
    if portfolio_weights:
        hhi_val = hhi(portfolio_weights)
        if hhi_val and hhi_val > 0:
            hhi_equiv = round(1.0 / hhi_val, 1)

    # 04 胜率
    wr_result = win_rate(holdings_details or [])

    # 05 换手率
    turnover_val = None
    if holdings_before is not None and holdings_after is not None:
        turnover_val = turnover_rate(holdings_before, holdings_after)

    # 10 个股波动率
    ind_vol = individual_vols or None

    # 11a 组合 Beta
    beta_val = None
    beta_conf = "insufficient"
    beta_analysis = None
    if benchmark_daily_returns is not None and data_sufficient:
        beta_val = portfolio_beta(portfolio_daily_returns, benchmark_daily_returns)
        beta_conf = get_confidence_level(portfolio_daily_returns)
        beta_analysis = portfolio_beta_analysis(portfolio_daily_returns, benchmark_daily_returns)

    # 06 风险贡献
    rc_result: list[dict] = []
    if portfolio_weights and individual_vols:
        vol_list: list[float] = []
        weight_list: list[float] = []
        for i, w in enumerate(portfolio_weights):
            vol_list.append(list(individual_vols.values())[i] if i < len(individual_vols) else 0.0)
            weight_list.append(w)
        rc_result = risk_contribution(weight_list, vol_list)

    return {
        "sharpe_ratio": sanitize_metric(sharpe_val),
        "sharpe_confidence": confidence if data_sufficient else "insufficient",
        "calmar_ratio": sanitize_metric(calmar_val),
        "calmar_confidence": confidence if data_sufficient else "insufficient",
        "hhi": sanitize_metric(hhi_val),
        "hhi_equivalent": hhi_equiv,
        "win_rate": wr_result,
        "turnover_rate": sanitize_metric(turnover_val),
        "individual_volatility": ind_vol,
        "portfolio_beta": sanitize_metric(beta_val),
        "beta_confidence": beta_conf,
        "risk_contributions": rc_result,
        # Beta 统计检验
        "beta_analysis": beta_analysis,
    }
