"""情景分析模块 — 情景模拟与置信区间传播。

三张情景表：
  - 市场情景：基于 Beta 的市场涨跌 ±10%/±20%/±30% 六情景
  - 行业情景：基于行业集中度的行业冲击影响
  - 汇率情景：基于外汇敞口的人民币 ±5% 波动影响

置信区间传播：
  - Beta CI → 情景回撤 CI
  - 年化波动率 CI → 夏普比率 CI
  - 过宽时标注"预测可靠性有限"

严格保持与 report/ 层无依赖（analysis 层约束）。
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger("invest")

# 市场涨跌情景定义
_MARKET_SCENARIOS: list[float] = [-0.30, -0.20, -0.10, 0.10, 0.20, 0.30]

# 行业冲击情景（模拟特定行业下跌）
_INDUSTRY_SHOCK = -0.15

# 汇率情景
_FX_SCENARIOS: list[float] = [-0.05, 0.05]

# 置信区间宽度阈值（超过此值标记为不可靠）
_CI_WIDTH_THRESHOLD = 0.15

# 夏普比率置信区间计算的年化系数
_TRADING_DAYS = 252

__all__ = [
    "scenario_analysis",
    "industry_concentration_analysis",
    "fx_scenario_analysis",
    "sharpe_ci_propagation",
]


def scenario_analysis(
    portfolio_value: float,
    beta: float | None = None,
    beta_ci_lower: float | None = None,
    beta_ci_upper: float | None = None,
    beta_se: float | None = None,
    portfolio_volatility: float | None = None,
) -> dict[str, Any]:
    """基于 Beta 计算六种市场情景下的组合预期变动。

    线性推导 E(Rp) = β × Rm。
    含置信区间（Beta CI → 预期变动 CI）和 ±1σ/±2σ 波动率区间（当 portfolio_volatility 可用时）。

    Args:
        portfolio_value: 组合总市值（元）
        beta: 组合 Beta 点估计值，为 None 时情景列显示"--"
        beta_ci_lower: Beta 95% CI 下限，为 None 时不输出 CI
        beta_ci_upper: Beta 95% CI 上限
        beta_se: Beta 标准误，为 None 时不输出 ±1σ/±2σ
        portfolio_volatility: 组合年化波动率，为 None 时不输出波动率区间

    Returns:
        {
            "has_data": bool,          # Beta 是否有值
            "beta": float | None,
            "scenarios": [
                {
                    "market_change": float,   # 市场变动比例（-0.30 ~ 0.30）
                    "expected_change_pct": float | None,  # 组合预期变动比例
                    "expected_change_amt": float | None,  # 组合预期变动金额（元）
                    "ci_lower_pct": float | None,         # 预期变动 CI 下限比例
                    "ci_upper_pct": float | None,         # 预期变动 CI 上限比例
                    "ci_lower_amt": float | None,         # 预期变动 CI 下限金额
                    "ci_upper_amt": float | None,         # 预期变动 CI 上限金额
                    "vol_1sigma_pct": float | None,       # ±1σ 波动率区间下限比例
                    "vol_1sigma_upper_pct": float | None, # ±1σ 波动率区间上限比例
                    "vol_2sigma_pct": float | None,       # ±2σ 波动率区间下限比例
                    "vol_2sigma_upper_pct": float | None, # ±2σ 波动率区间上限比例
                },
                ...
            ],
        }
    """
    scenarios: list[dict[str, Any]] = []
    has_data = beta is not None

    # Beta CI 传播到情景变动
    ci_available = has_data and beta_ci_lower is not None and beta_ci_upper is not None
    se_available = has_data and beta_se is not None and beta_se > 0
    vol_available = has_data and portfolio_volatility is not None and portfolio_volatility > 0

    for market_chg in _MARKET_SCENARIOS:
        if not has_data or beta is None:
            scenarios.append({
                "market_change": market_chg,
                "expected_change_pct": None,
                "expected_change_amt": None,
                "ci_lower_pct": None,
                "ci_upper_pct": None,
                "ci_lower_amt": None,
                "ci_upper_amt": None,
                "vol_1sigma_pct": None,
                "vol_1sigma_upper_pct": None,
                "vol_2sigma_pct": None,
                "vol_2sigma_upper_pct": None,
            })
            continue

        expected_pct = beta * market_chg
        expected_amt = portfolio_value * expected_pct

        # Meta CI 传播：E(Rp) = β × Rm，CI 也线性缩放
        ci_lower_pct = None
        ci_upper_pct = None
        ci_lower_amt = None
        ci_upper_amt = None
        if ci_available and market_chg != 0:
            if market_chg > 0:
                ci_lower_pct = beta_ci_lower * market_chg
                ci_upper_pct = beta_ci_upper * market_chg
            else:
                # 市场下跌时 CI 反转：下限用 beta_upper（更悲观）
                ci_lower_pct = beta_ci_upper * market_chg
                ci_upper_pct = beta_ci_lower * market_chg
            ci_lower_amt = portfolio_value * ci_lower_pct
            ci_upper_amt = portfolio_value * ci_upper_pct

        # ±1σ/±2σ 波动率区间
        vol_1sigma_pct = None
        vol_1sigma_upper_pct = None
        vol_2sigma_pct = None
        vol_2sigma_upper_pct = None
        if se_available and beta_se is not None:
            # Beta 标准误传播到预期变动
            se_pct = beta_se * abs(market_chg)
            vol_1sigma_pct = expected_pct - se_pct
            vol_1sigma_upper_pct = expected_pct + se_pct
            vol_2sigma_pct = expected_pct - 2.0 * se_pct
            vol_2sigma_upper_pct = expected_pct + 2.0 * se_pct

        scenarios.append({
            "market_change": market_chg,
            "expected_change_pct": round(expected_pct, 4),
            "expected_change_amt": round(expected_amt, 2),
            "ci_lower_pct": round(ci_lower_pct, 4) if ci_lower_pct is not None else None,
            "ci_upper_pct": round(ci_upper_pct, 4) if ci_upper_pct is not None else None,
            "ci_lower_amt": round(ci_lower_amt, 2) if ci_lower_amt is not None else None,
            "ci_upper_amt": round(ci_upper_amt, 2) if ci_upper_amt is not None else None,
            "vol_1sigma_pct": round(vol_1sigma_pct, 4) if vol_1sigma_pct is not None else None,
            "vol_1sigma_upper_pct": round(vol_1sigma_upper_pct, 4) if vol_1sigma_upper_pct is not None else None,
            "vol_2sigma_pct": round(vol_2sigma_pct, 4) if vol_2sigma_pct is not None else None,
            "vol_2sigma_upper_pct": round(vol_2sigma_upper_pct, 4) if vol_2sigma_upper_pct is not None else None,
        })

    return {
        "has_data": has_data,
        "beta": beta,
        "scenarios": scenarios,
    }


# ── 行业集中度情景分析 ──────────────────────────


def industry_concentration_analysis(
    top_industry_pct: float | None,
    total_mv: float,
    industry_name: str | None = None,
) -> dict[str, Any]:
    """基于行业集中度估算行业冲击影响。

    当组合高度集中在单一行业（如 >30%）时，该行业若下跌 15%，
    组合将承受相应冲击。行业越分散，影响越小。

    Args:
        top_industry_pct: 第一大行业市值占比（0~1），None 表示无行业数据
        total_mv: 组合总市值（元）
        industry_name: 第一大行业名称，为 None 时显示"第一大行业"

    Returns:
        {
            "has_data": bool,
            "top_industry_pct": float | None,
            "industry_name": str,
            "shock_pct": float,        # 行业冲击幅度（固定 -15%）
            "impact_pct": float | None, # 对组合的影响比例
            "impact_amt": float | None, # 对组合的影响金额（元）
            "concentration_risk": str,  # high / medium / low
            "warning": str | None,      # 数据不足提示
        }
    """
    if top_industry_pct is None:
        return {
            "has_data": False,
            "top_industry_pct": None,
            "industry_name": industry_name or "第一大行业",
            "shock_pct": _INDUSTRY_SHOCK,
            "impact_pct": None,
            "impact_amt": None,
            "concentration_risk": "unknown",
            "warning": "行业分类数据不足，无法评估行业集中度风险",
        }

    # 影响 = 行业占比 × 行业冲击幅度
    impact_pct = top_industry_pct * _INDUSTRY_SHOCK
    impact_amt = total_mv * impact_pct

    # 集中度风险等级
    if top_industry_pct >= 0.50:
        concentration_risk = "high"
    elif top_industry_pct >= 0.30:
        concentration_risk = "medium"
    else:
        concentration_risk = "low"

    warning = None
    if top_industry_pct < 0.10:
        warning = "行业集中度低，行业冲击风险较小"

    return {
        "has_data": True,
        "top_industry_pct": round(top_industry_pct, 4),
        "industry_name": industry_name or "第一大行业",
        "shock_pct": _INDUSTRY_SHOCK,
        "impact_pct": round(impact_pct, 4),
        "impact_amt": round(impact_amt, 2),
        "concentration_risk": concentration_risk,
        "warning": warning,
    }


# ── 汇率情景分析 ────────────────────────────────


def fx_scenario_analysis(
    foreign_exposure_pct: float | None,
    total_mv: float,
) -> dict[str, Any]:
    """基于外汇敞口估算人民币 ±5% 情景影响。

    Args:
        foreign_exposure_pct: 外币资产占比（0~1），None 表示无外汇数据
        total_mv: 组合总市值（元）

    Returns:
        {
            "has_data": bool,
            "foreign_exposure_pct": float | None,
            "scenarios": [
                {
                    "fx_change": float,      # 汇率变动（-0.05 / 0.05）
                    "label": str,            # 人民币升值/贬值
                    "impact_pct": float | None,  # 对组合影响比例
                    "impact_amt": float | None,  # 对组合影响金额（元）
                },
            ],
            "warning": str | None,
        }
    """
    if foreign_exposure_pct is None:
        return {
            "has_data": False,
            "foreign_exposure_pct": None,
            "scenarios": [
                {"fx_change": fx, "label": "人民币升值" if fx < 0 else "人民币贬值",
                 "impact_pct": None, "impact_amt": None}
                for fx in _FX_SCENARIOS
            ],
            "warning": "外汇敞口数据不足，无法评估汇率变动影响",
        }

    # 汇率影响简化模型：外币资产按汇率变动比例直接换算
    scenarios = []
    for fx_chg in _FX_SCENARIOS:
        label = "人民币升值" if fx_chg < 0 else "人民币贬值"
        impact_pct = foreign_exposure_pct * fx_chg
        impact_amt = total_mv * impact_pct
        scenarios.append({
            "fx_change": fx_chg,
            "label": label,
            "impact_pct": round(impact_pct, 4),
            "impact_amt": round(impact_amt, 2),
        })

    warning = None
    if foreign_exposure_pct < 0.05:
        warning = "外汇敞口较低，汇率变动影响有限"

    return {
        "has_data": True,
        "foreign_exposure_pct": round(foreign_exposure_pct, 4),
        "scenarios": scenarios,
        "warning": warning,
    }


# ── 夏普比率置信区间传播 ────────────────────────


def sharpe_ci_propagation(
    sharpe_ratio: float | None,
    annual_volatility: float | None,
    years_of_data: float,
    n_observations: int = _TRADING_DAYS,
) -> dict[str, Any]:
    """从年化波动率传播夏普比率的置信区间。

    夏普比率的标准误近似：SE(SR) ≈ sqrt(1 + 0.5 * SR²) / sqrt(N)
    其中 N 为观测年数折算的独立观测数。

    Args:
        sharpe_ratio: 夏普比率值，None 时不计算
        annual_volatility: 年化波动率，用于辅助判断
        years_of_data: 数据覆盖年数
        n_observations: 日收益率观测数

    Returns:
        {
            "has_data": bool,
            "sharpe_ratio": float | None,
            "ci_lower": float | None,
            "ci_upper": float | None,
            "ci_width": float | None,
            "reliable": bool,
            "warning": str | None,
        }
    """
    if sharpe_ratio is None or years_of_data <= 0:
        return {
            "has_data": False,
            "sharpe_ratio": sharpe_ratio,
            "ci_lower": None,
            "ci_upper": None,
            "ci_width": None,
            "reliable": False,
            "warning": "数据不足，无法计算夏普比率置信区间",
        }

    # 标准误近似：Lo (2002) 方法
    se = math.sqrt((1.0 + 0.5 * sharpe_ratio ** 2) / n_observations) if n_observations > 0 else 1.0
    ci_half = 1.96 * se  # 95% CI
    ci_lower = sharpe_ratio - ci_half
    ci_upper = sharpe_ratio + ci_half
    ci_width = ci_upper - ci_lower

    reliable = ci_width <= _CI_WIDTH_THRESHOLD * 2  # 夏普 CI 宽度 ≤ 0.30
    warning = None
    if ci_width > _CI_WIDTH_THRESHOLD * 2:
        warning = "夏普比率置信区间过宽（宽度 {:.2f}），预测可靠性有限".format(ci_width)
    if years_of_data < 1:
        warning = "不足一年数据，夏普比率置信区间可能不准确"

    return {
        "has_data": True,
        "sharpe_ratio": round(sharpe_ratio, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "ci_width": round(ci_width, 4),
        "reliable": reliable,
        "warning": warning,
    }
