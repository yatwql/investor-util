"""分析计算模块 — 与 report/ 无依赖的业务计算层。

所有分析计算逻辑收敛于此包，严格禁止导入 report/ 下的任何模块。
仅消费调用方传入的数据（holdings_details / total_mv 等），
保持与报告层的完全解耦。

已实现：
  - rebalance: 再平衡信号计算（单品超限 + 目标偏离 + 权益/固收偏离）
  - metrics: 量化指标计算（夏普/卡玛/HHI/胜率/换手率/风险贡献/波动率/Beta）
  - circuit_breaker_wrapper: 指标级断路包装器
  - drawdown_warning: 回撤历史分位预警（滚动窗口 + 全历史）
  - liquidity: 流动性风险评估（场内品种变现天数计算）
"""

from __future__ import annotations

from src.python.analysis.simple_rebalance import compute_rebalance_signals  # noqa: F401
from src.python.analysis.metrics import (  # noqa: F401
    sharpe_ratio,
    calmar_ratio,
    hhi,
    win_rate,
    turnover_rate,
    risk_contribution,
    get_dividend_yield,
    compute_all_metrics,
    sanitize_metric,
    individual_volatility,
    portfolio_beta,
    portfolio_beta_analysis,
    truncate_extreme_values,
    check_data_sufficiency,
    get_confidence_level,
)
from src.python.analysis.drawdown_warning import (  # noqa: F401
    compute_drawdown_warning,
    rolling_max_drawdown,
    current_drawdown_percentile,
)
from src.python.analysis.liquidity import check_liquidity  # noqa: F401
from src.python.analysis.fx_exposure import fx_exposure  # noqa: F401
from src.python.analysis.scenario import (  # noqa: F401
    scenario_analysis,
    industry_concentration_analysis,
    fx_scenario_analysis,
    sharpe_ci_propagation,
)
from src.python.analysis.alignment_correction import (  # noqa: F401
    portfolio_fee_estimation,
    cash_stripping,
    twr_calculation,
    compute_alignment_factors,
)

__all__ = [
    "compute_rebalance_signals",
    "sharpe_ratio",
    "calmar_ratio",
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
    "truncate_extreme_values",
    "check_data_sufficiency",
    "get_confidence_level",
    "compute_drawdown_warning",
    "rolling_max_drawdown",
    "current_drawdown_percentile",
    "check_liquidity",
    "fx_exposure",
    "scenario_analysis",
    "industry_concentration_analysis",
    "fx_scenario_analysis",
    "sharpe_ci_propagation",
    "portfolio_fee_estimation",
    "cash_stripping",
    "twr_calculation",
    "compute_alignment_factors",
]
