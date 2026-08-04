"""风格因子回归 — 纯计算层（MVP 3 因子，风格与因子分析章·风格因子回归区块）。

职责：接收（组合日收益序列 + 因子收益序列 + 基准收益序列）→ OLS 回归
      → 输出风格暴露 β / t 显著性 / 风格归属占比 / 基准对照。

- 无数据获取、无报告依赖，纯 pandas/numpy（日志走 logging，不用 print）。
- 因子代理指数代码与新鲜度常量在本模块定义，供编排层（report/orchestrator.py）引用。
- 数据不足/因子停更 → available=false，绝不硬算（§1.4.5 数据降级治理）。
- 代码类型判定：因子指数不注册 _A_INDICES（避免污染实时指数行情循环 fetch_indices），
  此处以模块内常量集合定义。
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.python.analysis._math_utils import _t_critical_95

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  因子常量（MVP 固定 3 因子）
# ═══════════════════════════════════════════════════════════════

# 因子 → 代理指数代码（probe 已验证 2026-08-01；300成长 sh000920 停更由 500成长替代）
FACTOR_INDICES: dict[str, str] = {
    "value": "sh000919",  # 300 价值（大盘价值代理）
    "growth": "sh000925",  # 500 成长（中盘成长代理，替代停更的 300 成长）
    "quality": "sh000930",  # 300 质量（全指质量代理）
}

# 因子 → 中文名
FACTOR_NAMES: dict[str, str] = {
    "value": "价值",
    "growth": "成长",
    "quality": "质量",
}

# 因子指数末根 K 线距今超此天数视为停更，本次回归剔除
FACTOR_STALE_DAYS: int = 120

# 基准指数（沪深300）——风格漂移对照用
BASELINE_INDEX: str = "sh000300"
BASELINE_NAME: str = "沪深300"

# 有效样本下限：低于此判数据不足，不接受硬算
MIN_SAMPLES: int = 36
# 默认回归窗口（交易日 ≈ 3 个月）
DEFAULT_WINDOW: int = 60
# 剩余有效因子少于 2 → 数据不足分支
MIN_FACTORS: int = 2


# ═══════════════════════════════════════════════════════════════
#  结果工厂
# ═══════════════════════════════════════════════════════════════


def unavailable_result(status: str, sample_count: int = 0, stale_factors: list[str] | None = None) -> dict:
    """返回不可用结果（数据契约，available=False）。

    Args:
        status: "insufficient"（数据不足）或 "source_failed"（数据源故障）。
        sample_count: 对齐后有效样本数（数据不足时为实际值）。
        stale_factors: 本次剔除的停更/不可用因子。

    Returns:
        含全部数据契约键的空结果字典。
    """
    return {
        "available": False,
        "status": status,
        "betas": {},
        "t_stats": {},
        "significant": {},
        "style_allocation": {},
        "baseline_betas": {},
        "factor_correlations": {},
        "correlation_note": "",
        "alpha": 0.0,
        "window": DEFAULT_WINDOW,
        "sample_count": sample_count,
        "stale_factors": stale_factors or [],
    }


# ═══════════════════════════════════════════════════════════════
#  as-if 组合日收益（口径与 portfolio_history 一致）
# ═══════════════════════════════════════════════════════════════


def asif_portfolio_daily_returns(
    holdings_bars: dict[str, dict],
) -> list[dict]:
    """按 as-if 语义计算组合日收益序列（口径与 portfolio_history 一致）。

    as-if：假设当前持仓份额在过去 N 天不变，用历史价格 × 当前份额。
    LOCF：净值未更新的标的沿用上次已知值（同日去重，与 _merge_locf 一致）。
    收益率输出为小数（非百分比），且仅在前值 > 0 时计算（与 _compute_daily_returns 一致）。

    Args:
        holdings_bars: {code: {"shares": float, "bars": [{"date": str, "close": float, ...}, ...]}}
            bars 按日期升序；场外基金 bar 可含 "nav" 字段。

    Returns:
        [{"date": str, "return": float}, ...] 按日期升序。
        无可计算样本时返回 []。
    """
    all_dates: set[str] = set()
    series_by_code: dict[str, dict[str, float]] = {}

    for code, info in holdings_bars.items():
        shares = float(info.get("shares", 0))
        bars = info.get("bars", [])
        if shares <= 0 or not bars:
            continue
        sd: dict[str, float] = {}
        for b in bars:
            close = b.get("close") or b.get("nav", 0)
            if close and close > 0:
                sd[b["date"]] = close * shares
        if sd:
            series_by_code[code] = sd
            all_dates.update(sd.keys())

    if not series_by_code:
        return []

    sorted_dates = sorted(all_dates)

    # LOCF 合并（与 portfolio_history._merge_locf 口径一致）
    date_map: dict[str, float] = {d: 0.0 for d in sorted_dates}
    for sd in series_by_code.values():
        last_val = 0.0
        for d in sorted_dates:
            if d in sd:
                last_val = sd[d]
            if last_val > 0:
                date_map[d] += last_val

    # 日收益率（小数），前值 > 0 才计算
    result: list[dict] = []
    prev_val = 0.0
    for d in sorted_dates:
        tv = date_map[d]
        if prev_val > 0:
            result.append({"date": d, "return": (tv - prev_val) / prev_val})
        prev_val = tv
    return result


# ═══════════════════════════════════════════════════════════════
#  K 线 → 日收益率
# ═══════════════════════════════════════════════════════════════


def klines_to_returns(bars: list[dict]) -> list[dict]:
    """指数/证券 K 线 → 日收益率序列（小数，按日期升序）。

    Args:
        bars: [{"date", "close", ...}, ...] 升序；场外基金可含 "nav"。

    Returns:
        [{"date", "return"}, ...]；bar 不足 2 条或全无效时返回 []。

    无效日（close/nav ≤ 0）不产出收益，但保留上次有效值继续链式计算
    （LOCF 语义，与 _align_series 的 ffill 口径一致，避免单日缺失损后续收益）。
    """
    result: list[dict] = []
    prev_close: float | None = None
    for b in bars:
        close = b.get("close") or b.get("nav", 0)
        if not close or close <= 0:
            continue  # 无效日不产出收益，prev_close 保留上次有效值
        if prev_close is not None and prev_close > 0:
            result.append({"date": b["date"], "return": (close - prev_close) / prev_close})
        prev_close = close
    return result


# ═══════════════════════════════════════════════════════════════
#  新鲜度校验（停更因子剔除）
# ═══════════════════════════════════════════════════════════════


def filter_stale_factor_klines(
    factor_klines: dict[str, list[dict]],
    today_str: str,
    stale_days: int = FACTOR_STALE_DAYS,
) -> tuple[dict[str, list[dict]], list[str]]:
    """剔除停更因子（末根 K 线距今超过 stale_days）。

    Args:
        factor_klines: {factor: [{"date", "close"}, ...]}（bars 升序）。
        today_str: 参考日期 "YYYY-MM-DD"。
        stale_days: 停更判定阈值（天）。

    Returns:
        (fresh_factors, stale_factors)：fresh 为未停更因子，stale 列出剔除因子。
    """
    if not factor_klines:
        return {}, []
    try:
        today = pd.Timestamp(today_str)
    except (ValueError, TypeError):
        today = pd.Timestamp.now()

    fresh: dict[str, list[dict]] = {}
    stale: list[str] = []
    for factor, bars in factor_klines.items():
        last_date = ""
        if bars:
            last_date = str(bars[-1].get("date", ""))
        if not last_date:
            stale.append(factor)
            continue
        try:
            age_days = (today - pd.Timestamp(last_date)).days
        except (ValueError, TypeError):
            age_days = 0
        if age_days > stale_days:
            stale.append(factor)
            logger.warning(
                "[factor] 因子 %s（%s）已停更（末根 K 线距今 %d 天），本次回归剔除",
                FACTOR_NAMES.get(factor, factor),
                FACTOR_INDICES.get(factor, ""),
                age_days,
            )
        else:
            fresh[factor] = bars
    return fresh, stale


# ═══════════════════════════════════════════════════════════════
#  OLS 回归
# ═══════════════════════════════════════════════════════════════


def _ols_regression(y: np.ndarray, x: np.ndarray) -> dict:
    """OLS 回归 y = Xβ + ε（X 含常数项列）。

    用 numpy.linalg.lstsq 手写（statsmodels 未安装，复用 _math_utils 的 t 分布辅助）。

    Args:
        y: 因变量向量 (n,)。
        x: 设计矩阵 (n, k)，第一列为常数项。

    Returns:
        {"beta": list, "t_stats": list, "df": int}；数据不足时 beta/t_stats 为 None。
    """
    n, k = x.shape
    if n < k + 1:
        return {"beta": None, "t_stats": None, "df": n - k}

    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    residuals = y - x @ coef
    df = n - k
    mse = float(residuals @ residuals) / df if df > 0 else 0.0

    try:
        xtx_inv = np.linalg.pinv(x.T @ x)
        se = np.sqrt(np.clip(mse * np.diag(xtx_inv), a_min=1e-12, a_max=None))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)

    with np.errstate(divide="ignore", invalid="ignore"):
        t_stats = np.where(np.abs(se) > 1e-12, coef / se, 0.0)
    return {"beta": coef.tolist(), "t_stats": t_stats.tolist(), "df": df}


def _align_series(
    portfolio_returns: list[dict],
    factor_returns: dict[str, list[dict]],
    baseline_returns: list[dict] | None,
) -> pd.DataFrame:
    """将组合/因子/基准收益序列按日期对齐。

    对齐策略（§计算方案 回归序列对齐）：
      - 组合 R_p：先 ffill() 补单日缺口，再 dropna() 剔除无效日（长期缺失贡献失真）。
      - 因子/基准：直接由指数 K 线 pct_change 得到，天然带日期索引。
      - 组合 × 因子 inner join；基准 left join（允许基准缺少数日，不丢失样本）。

    Returns:
        DataFrame，index 为日期，列为因子 + "portfolio"（+ 可选 "baseline"）。
    """
    pdf = pd.DataFrame(portfolio_returns)
    if pdf.empty or "date" not in pdf.columns or "return" not in pdf.columns:
        return pd.DataFrame()
    pdf = pdf.dropna(subset=["return"]).set_index("date")["return"]
    pdf = pdf.ffill().dropna()  # 单日缺口前向填充；无效日（首部）剔除

    frames: list[pd.Series] = []
    for factor, bars in factor_returns.items():
        if not bars:
            continue
        s = pd.DataFrame(bars).dropna(subset=["return"]).set_index("date")["return"]
        if not s.empty:
            frames.append(s.rename(factor))
    if not frames:
        return pd.DataFrame()

    factor_df = pd.concat(frames, axis=1, join="inner")
    merged = factor_df.join(pdf.rename("portfolio"), how="inner")

    if baseline_returns:
        bs = pd.DataFrame(baseline_returns)
        if not bs.empty and "date" in bs.columns and "return" in bs.columns:
            bs = bs.dropna(subset=["return"]).set_index("date")["return"]
            merged = merged.join(bs.rename("baseline"), how="left")
    return merged


# ═══════════════════════════════════════════════════════════════
#  主计算入口
# ═══════════════════════════════════════════════════════════════


def compute_factor_exposure(
    portfolio_returns: list[dict],
    factor_returns: dict[str, list[dict]],
    baseline_returns: list[dict] | None = None,
    window: int = DEFAULT_WINDOW,
    min_samples: int = MIN_SAMPLES,
) -> dict:
    """计算组合因子暴露（时间序列 OLS 回归）。

    Args:
        portfolio_returns: 组合日收益序列 [{"date", "return"}]（小数）。
        factor_returns: {factor: [{"date", "return"}]}，因子日收益序列。
        baseline_returns: 基准（沪深300）日收益序列，用于对照回归；可为 None。
        window: 回归窗口（取对齐序列最近 N 期）。
        min_samples: 有效样本下限，低于此判数据不足（available=false）。

    Returns:
        数据契约 dict：
        {"available", "status", "betas", "t_stats", "significant",
         "style_allocation", "baseline_betas", "factor_correlations",
         "correlation_note", "alpha", "window", "sample_count", "stale_factors"}
    """
    active_factors = {f: bars for f, bars in factor_returns.items() if bars}
    if not active_factors:
        return unavailable_result("insufficient", sample_count=0)

    df = _align_series(portfolio_returns, active_factors, baseline_returns)
    sample_count = len(df)
    if sample_count < min_samples:
        return unavailable_result("insufficient", sample_count=sample_count)

    factors = list(active_factors.keys())
    _win = min(window, sample_count)
    df_win = df.iloc[-_win:].reset_index(drop=True)

    x_mat = df_win[factors].to_numpy(dtype=float)
    y = df_win["portfolio"].to_numpy(dtype=float)
    x_const = np.column_stack([np.ones(len(x_mat)), x_mat])

    ols = _ols_regression(y, x_const)
    beta = ols["beta"]
    t_stats = ols["t_stats"]
    df_eff = ols["df"]
    if beta is None:
        return unavailable_result("insufficient", sample_count=sample_count)

    betas = {f: round(float(beta[i + 1]), 4) for i, f in enumerate(factors)}
    alpha = round(float(beta[0]), 4)
    tvals = {f: round(float(t_stats[i + 1]), 3) for i, f in enumerate(factors)}
    # 95% 双尾显著性（复用 _math_utils 的 t 临界值）
    _t_crit = _t_critical_95(df_eff)
    significant = {f: abs(tvals[f]) >= _t_crit for f in factors}

    # 风格归属占比（|β| 归一化）——"组合风格画像"柱状图高度
    abs_betas = {f: abs(betas[f]) for f in factors}
    total_abs = sum(abs_betas.values())
    style_allocation = {f: round(abs_betas[f] / total_abs, 4) if total_abs > 0 else 0.0 for f in factors}

    # 因子相关矩阵（诊断展示，替代 VIF；MVP 不做正交化）
    corr = df_win[factors].corr()
    factor_correlations: dict[str, float] = {}
    for i in range(len(factors)):
        for j in range(i + 1, len(factors)):
            pair = f"{FACTOR_NAMES.get(factors[i], factors[i])}-{FACTOR_NAMES.get(factors[j], factors[j])}"
            v = corr.iloc[i, j]
            factor_correlations[pair] = round(float(v), 3) if not pd.isna(v) else 0.0
    high_pairs = [p for p, v in factor_correlations.items() if abs(v) >= 0.9]
    corr_note = ""
    if high_pairs:
        corr_note = f"因子 {'、'.join(high_pairs)} 高度相关（|r|≥0.9），β 系数解释需谨慎"

    # 基准（沪深300）同窗口对照回归——风格漂移判断
    baseline_betas: dict[str, float] = {}
    if baseline_returns is not None and "baseline" in df_win.columns:
        base_y = df_win["baseline"].to_numpy(dtype=float)
        mask = ~np.isnan(base_y)
        if mask.sum() >= min_samples:
            b_ols = _ols_regression(base_y[mask], x_const[mask])
            if b_ols["beta"] is not None:
                baseline_betas = {f: round(float(b_ols["beta"][i + 1]), 4) for i, f in enumerate(factors)}

    return {
        "available": True,
        "status": "ok",
        "betas": betas,
        "t_stats": tvals,
        "significant": significant,
        "style_allocation": style_allocation,
        "baseline_betas": baseline_betas,
        "factor_correlations": factor_correlations,
        "correlation_note": corr_note,
        "alpha": alpha,
        "window": _win,
        "sample_count": sample_count,
        "stale_factors": [],
    }
