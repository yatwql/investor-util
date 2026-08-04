"""行业 Beta 分析 — 纯计算层（行业暴露占比 + 各行业指数 Beta/相关性）。

职责：接收（行业市值聚合 + 组合日收益序列 + 各行业指数日收益序列）
      → 输出行业暴露占比 + 逐行业一元 OLS Beta / t 显著性 / 相关性。

- 无数据获取、无报告依赖，纯 pandas/numpy（C8：日志走 logging，不用 print）。
- Beta 复用 ``factor_exposure.compute_factor_exposure`` 的单因子调用，
  不重复实现 OLS（轮 12「复用 OLS 回归机制，无重复实现」约束）。
- 行业分类判定复用 ``core/code_utils.py``（C1）；指数 K 线由编排层
  （report/orchestrator.py）走 Chain + session_cache（C4/C6），本模块不联网。
- push2 行业分类不可用 / 指数 K 线不足 → available=False，绝不硬算
  （§1.4.5 数据降级治理）。

行业指数为近似代理：行业分类名来自东方财富 push2（东财三级行业），
指数采用中证行业指数（腾讯/新浪 K 线可用）。映射不精确的行业仅参与
暴露占比，Beta 子表不渲染该行业（有暴露但无映射 → unmapped_industries）。
"""

from __future__ import annotations

import logging

from src.python.analysis.factor_exposure import compute_factor_exposure

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  行业常量
# ═══════════════════════════════════════════════════════════════

# 行业名（东财 push2）→ 中证行业指数代码（probe 已验证 2026-08-04，腾讯/新浪 K 线可用）。
# 近似代理：覆盖常见行业；未覆盖行业仅计入暴露占比，不参与 Beta 回归。
INDUSTRY_INDEX_MAP: dict[str, str] = {
    "银行": "sh000986",  # 中证银行
    "证券": "sz399975",  # 证券公司
    "保险": "sz399983",  # 保险主题
    "白酒": "sz399997",  # 中证白酒（食品饮料代理）
    "食品饮料": "sz399997",  # 中证白酒（行业归并）
    "医药": "sz399989",  # 中证医药
    "医药生物": "sz399989",  # 中证医药（东财别名）
    "半导体": "sz399995",  # 中证半导体
    "电子": "sz399995",  # 中证半导体（电子大类代理）
    "有色金属": "sz399996",  # 中证有色金属
    "贵金属": "sz399996",  # 中证有色金属（贵金属归并）
    "煤炭": "sz399998",  # 中证煤炭
    "钢铁": "sz399994",  # 中证钢铁
    "房地产": "sh000980",  # 中证 300 地产
    "房地产开发": "sh000980",  # 中证 300 地产（东财别名）
    "能源": "sh000928",  # 中证能源
    "环保": "sz399973",  # 中证 300 环保
}

# 有效样本下限：低于此判数据不足，不接受硬算（与因子暴露一致）
MIN_INDUSTRY_SAMPLES: int = 36
# 默认回归窗口（交易日 ≈ 3 个月）
DEFAULT_WINDOW: int = 60


def industry_index_for(industry: str) -> str | None:
    """行业名 → 指数代码（无映射返回 None）。"""
    return INDUSTRY_INDEX_MAP.get(industry)


# ═══════════════════════════════════════════════════════════════
#  结果工厂
# ═══════════════════════════════════════════════════════════════


def unavailable_result(status: str, sample_count: int = 0) -> dict:
    """返回不可用结果（C19 子契约，available=False）。

    Args:
        status: "insufficient"（数据不足）或 "source_failed"（数据源故障）。
        sample_count: 对齐后有效样本数（数据不足时为实际值）。

    Returns:
        含全部行业 Beta 键的空结果字典。
    """
    return {
        "available": False,
        "status": status,
        "exposure": {},  # {industry: pct}
        "betas": {},  # {industry: beta}
        "alphas": {},  # {industry: alpha}
        "t_stats": {},  # {industry: t}
        "significant": {},  # {industry: bool}
        "correlations": {},  # {industry: r}
        "unmapped_industries": [],  # 有暴露但无指数映射的行业
        "window": DEFAULT_WINDOW,
        "sample_count": sample_count,
    }


# ═══════════════════════════════════════════════════════════════
#  行业暴露占比
# ═══════════════════════════════════════════════════════════════


def compute_industry_exposure(industry_cap: dict[str, float]) -> dict:
    """按市值加权计算行业暴露占比。

    Args:
        industry_cap: {industry: market_value}，市值 > 0 的行业。

    Returns:
        {"available": bool, "exposure": {industry: pct}, "total": float}
        exposure 按占比降序；无有效市值时 available=False。
    """
    positive = {k: float(v) for k, v in industry_cap.items() if v is not None and float(v) > 0}
    total = sum(positive.values())
    if total <= 0:
        return {"available": False, "exposure": {}, "total": 0.0}
    exposure = {k: round(v / total, 4) for k, v in positive.items()}
    exposure = dict(sorted(exposure.items(), key=lambda kv: -kv[1]))
    return {"available": True, "exposure": exposure, "total": total}


# ═══════════════════════════════════════════════════════════════
#  行业 Beta 主计算
# ═══════════════════════════════════════════════════════════════


def compute_industry_beta_analysis(
    portfolio_returns: list[dict],
    industry_returns: dict[str, list[dict]],
    window: int = DEFAULT_WINDOW,
    min_samples: int = MIN_INDUSTRY_SAMPLES,
) -> dict:
    """计算组合对各行业指数的 Beta（逐行业一元 OLS）。

    每个行业独立回归：y = 组合日收益，x = 该行业指数日收益（含常数项）。
    复用 ``factor_exposure.compute_factor_exposure`` 的单因子调用，
    避免重复实现 OLS。相关系数 r 为对齐后「组合 vs 行业」的 Pearson 相关。

    Args:
        portfolio_returns: 组合日收益序列 [{"date", "return"}]（小数）。
        industry_returns: {industry: [{"date", "return"}]}，行业指数日收益序列。
        window: 回归窗口（取对齐序列最近 N 期）。
        min_samples: 有效样本下限，低于此判数据不足（available=false）。

    Returns:
        C19 子契约 dict：
        {"available", "status", "exposure", "betas", "alphas", "t_stats",
         "significant", "correlations", "unmapped_industries",
         "window", "sample_count"}
    """
    active = {ind: bars for ind, bars in industry_returns.items() if bars}
    if not active:
        return unavailable_result("insufficient", sample_count=0)

    import numpy as np

    betas: dict[str, float] = {}
    alphas: dict[str, float] = {}
    t_stats: dict[str, float] = {}
    significant: dict[str, bool] = {}
    correlations: dict[str, float] = {}
    sample_count = 0

    for ind, bars in active.items():
        # 单因子调用：完整复用 OLS 回归/显著性/样本下限逻辑（无重复实现）
        result = compute_factor_exposure(
            portfolio_returns,
            {ind: bars},
            baseline_returns=None,
            window=window,
            min_samples=min_samples,
        )
        sample_count = max(sample_count, result.get("sample_count", 0))
        if not result.get("available") or ind not in result.get("betas", {}):
            logger.info("[industry_beta] 行业 %s 数据不足（样本 %s），跳过回归", ind, result.get("sample_count", 0))
            continue

        sample_count = max(sample_count, result.get("sample_count", 0))
        betas[ind] = result["betas"][ind]
        alphas[ind] = result.get("alpha", 0.0)
        t_stats[ind] = result["t_stats"].get(ind, 0.0)
        significant[ind] = bool(result["significant"].get(ind, False))

        # 组合 vs 行业的 Pearson 相关（对齐同一窗口）
        r = _portfolio_industry_corr(portfolio_returns, bars, window)
        if r is not None:
            correlations[ind] = round(float(r), 4)

    if not betas:
        return unavailable_result("insufficient", sample_count=sample_count)

    return {
        "available": True,
        "status": "ok",
        "exposure": {},  # 暴露占比由编排层合并（本模块无市值输入）
        "betas": betas,
        "alphas": alphas,
        "t_stats": t_stats,
        "significant": significant,
        "correlations": correlations,
        "unmapped_industries": [],
        "window": window,
        "sample_count": sample_count,
    }


def _portfolio_industry_corr(
    portfolio_returns: list[dict],
    industry_bars: list[dict],
    window: int,
) -> float | None:
    """对齐组合与行业指数收益，计算最近 window 期 Pearson 相关。"""
    import numpy as np
    import pandas as pd

    pdf = pd.DataFrame(portfolio_returns)
    if pdf.empty or "date" not in pdf.columns or "return" not in pdf.columns:
        return None
    ps = pdf.dropna(subset=["return"]).set_index("date")["return"].ffill().dropna()

    ib = pd.DataFrame(industry_bars)
    if ib.empty or "date" not in ib.columns or "return" not in ib.columns:
        return None
    ind_s = ib.dropna(subset=["return"]).set_index("date")["return"]

    merged = pd.concat([ps.rename("p"), ind_s.rename("i")], axis=1, join="inner").dropna()
    if len(merged) < 2:
        return None
    _win = min(window, len(merged))
    tail = merged.iloc[-_win:]
    if tail["p"].std() <= 1e-12 or tail["i"].std() <= 1e-12:
        return None
    return float(np.corrcoef(tail["p"].to_numpy(), tail["i"].to_numpy())[0, 1])
