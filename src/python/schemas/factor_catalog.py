"""因子目录契约（语义名 factor_catalog）— 25 因子五来源族唯一事实来源。

目录条目形状（与门槛判定书同源、逐条移植）：
    slug / family / label / fields ⊆ FIELD_TYPES / min_bars / window / formula
五来源族各 5 条：qlib158 / alpha101 / gtja191 / academic / fundamental。
装载与完整性校验在 fetcher.factor_catalog_loader（装载即校验，问题清单非空
即拒载、不进计算）；计算编排在 analysis.factor_evaluator。

中性点 NEUTRAL_POINTS：因子值的语义中枢（0 轴 / 50 轴等技术指标经典值），
供信号摘要与呈现面判「中性上方 / 下方」；None = 该因子无中性语义（恒正强度
类、纯量纲类、无可辩护中枢的基本面值），不计入中性口径分母。

分层：契约层只依赖标准库。目录随代码版本化——任何条目改动必须同步
CATALOG_VERSION（装载侧与信号 detail 均携带版本，保证账本记录可溯源）。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "BENCHMARK_INDEX",
    "CATALOG",
    "CATALOG_VERSION",
    "FAMILIES",
    "FAMILY_LABELS",
    "FIELD_BARS",
    "FIELD_FIN",
    "FIELD_INDEX",
    "FIELD_TYPES",
    "FIELD_VAL",
    "MIN_CODES_PER_DAY",
    "NEUTRAL_POINTS",
    "value_present",
]

CATALOG_VERSION = "2026.10.06.1"

# ── 目录条目字段需求的取值域（数据字段类型） ──
FIELD_BARS = "bars"
FIELD_INDEX = "index"
FIELD_VAL = "valuation"
FIELD_FIN = "fin_indicator"
FIELD_TYPES = (FIELD_BARS, FIELD_INDEX, FIELD_VAL, FIELD_FIN)

# 横截面有效成分数下限（与门槛判定书同口径：低于该值当期不出横截面值）
MIN_CODES_PER_DAY = 3

BENCHMARK_INDEX = "sh000300"  # 市场相对族与因子统一基准


def value_present(value: Any) -> bool:
    """数值存在且非 NaN（None / NaN 视为缺失；±inf 保留——强度类因子可合法发散）。"""
    return value is not None and not (isinstance(value, float) and value != value)


FAMILIES = ["qlib158", "alpha101", "gtja191", "academic", "fundamental"]
FAMILY_LABELS = {
    "qlib158": "qlib158 技术因子族",
    "alpha101": "alpha101 量价族",
    "gtja191": "gtja191 量价形态族",
    "academic": "academic 学术效应族",
    "fundamental": "fundamental 基本面族",
}

# ── 因子目录：五族 × 5（条目逐字移植自门槛判定书冻结清单） ──
# fields ⊆ FIELD_TYPES；min_bars = 因子所需最少日 K 线条数（交易日）
CATALOG: list[dict[str, Any]] = [
    # qlib158 族：经典技术因子
    {
        "slug": "qlib_ma_cross",
        "family": "qlib158",
        "label": "均线交叉（close vs MA20）",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "(close-MA20)/MA20",
    },
    {
        "slug": "qlib_macd_hist",
        "family": "qlib158",
        "label": "MACD 柱（EMA12/26 与信号 9）",
        "fields": [FIELD_BARS],
        "min_bars": 45,
        "window": 26,
        "formula": "(EMA12-EMA26)-EMA9(差值)",
    },
    {
        "slug": "qlib_rsi_14",
        "family": "qlib158",
        "label": "RSI 14",
        "fields": [FIELD_BARS],
        "min_bars": 20,
        "window": 14,
        "formula": "14 日涨跌幅强度比",
    },
    {
        "slug": "qlib_beta_60",
        "family": "qlib158",
        "label": "60 日 Beta vs 沪深300",
        "fields": [FIELD_BARS, FIELD_INDEX],
        "min_bars": 65,
        "window": 60,
        "formula": "Cov(r,rm)/Var(rm)，复用 portfolio_beta 口径",
    },
    {
        "slug": "qlib_aroon_25",
        "family": "qlib158",
        "label": "Aroon 25（高低点回望）",
        "fields": [FIELD_BARS],
        "min_bars": 30,
        "window": 25,
        "formula": "(aroon_up-aroon_down)/100",
    },
    # alpha101 族：量价关系
    {
        "slug": "alpha_corr_cv_10",
        "family": "alpha101",
        "label": "10 日收盘-成交量相关（反向）",
        "fields": [FIELD_BARS],
        "min_bars": 15,
        "window": 10,
        "formula": "-corr(close, volume, 10)",
    },
    {
        "slug": "alpha_rev_open_10",
        "family": "alpha101",
        "label": "10 日开盘-成交量相关（延迟反转代理）",
        "fields": [FIELD_BARS],
        "min_bars": 15,
        "window": 10,
        "formula": "-corr(open, volume, 10)",
    },
    {
        "slug": "alpha_pvt_10",
        "family": "alpha101",
        "label": "10 日价量趋势 PVT",
        "fields": [FIELD_BARS],
        "min_bars": 15,
        "window": 10,
        "formula": "Σ(Δclose×volume)/Σvolume（10 日）",
    },
    {
        "slug": "alpha_corr_cv_20",
        "family": "alpha101",
        "label": "20 日收盘-成交量相关（反向）",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "-corr(close, volume, 20)",
    },
    {
        "slug": "alpha_vwma_dev_20",
        "family": "alpha101",
        "label": "收盘价对 20 日成交量加权均价偏离",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "(close-VWMA20)/VWMA20",
    },
    # gtja191 族：量价形态（评测简化口径）
    {
        "slug": "gtja_mom_20",
        "family": "gtja191",
        "label": "20 日动量",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "close/close[-20]-1",
    },
    {
        "slug": "gtja_rsv_9",
        "family": "gtja191",
        "label": "KD-J RSV 9",
        "fields": [FIELD_BARS],
        "min_bars": 12,
        "window": 9,
        "formula": "(close-low9)/(high9-low9)",
    },
    {
        "slug": "gtja_bias_60",
        "family": "gtja191",
        "label": "60 日乖离率",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "(close-MA60)/MA60",
    },
    {
        "slug": "gtja_atr_14",
        "family": "gtja191",
        "label": "ATR14 波动归一",
        "fields": [FIELD_BARS],
        "min_bars": 20,
        "window": 14,
        "formula": "TR14 均值/close",
    },
    {
        "slug": "gtja_pv_divergence",
        "family": "gtja191",
        "label": "量价背离（动量 × 量能趋势符号）",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "-sign(mom20)×sign(volume10 斜率)",
    },
    # academic 族：经典学术效应（日线代理口径）
    {
        "slug": "acad_max_60",
        "family": "academic",
        "label": "MAX 效应（60 日日内最大涨幅代理）",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "max(high/open-1, 60 日)（分钟口径的日线代理）",
    },
    {
        "slug": "acad_idio_vol_60",
        "family": "academic",
        "label": "特质波动率 60 日",
        "fields": [FIELD_BARS, FIELD_INDEX],
        "min_bars": 65,
        "window": 60,
        "formula": "std(r-rm, 60)",
    },
    {
        "slug": "acad_amihud_proxy_60",
        "family": "academic",
        "label": "非流动性 60 日（成交量代理）",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "mean(|r|/volume, 60)（无成交额字段，用量代理）",
    },
    {
        "slug": "acad_low_vol_60",
        "family": "academic",
        "label": "低波动率 60 日",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "std(日收益, 60)",
    },
    {
        "slug": "acad_skew_60",
        "family": "academic",
        "label": "收益偏度 60 日",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "skewness(日收益, 60)",
    },
    # fundamental 族：基本面（当前报告期截面值，步进信号）
    {
        "slug": "fund_roe",
        "family": "fundamental",
        "label": "净资产收益率 ROE",
        "fields": [FIELD_FIN],
        "min_bars": 0,
        "window": 0,
        "formula": "最新报告期 roe",
    },
    {
        "slug": "fund_revenue_yoy",
        "family": "fundamental",
        "label": "营业总收入同比增长率",
        "fields": [FIELD_FIN],
        "min_bars": 0,
        "window": 0,
        "formula": "最新报告期 revenue_yoy",
    },
    {
        "slug": "fund_gross_margin",
        "family": "fundamental",
        "label": "毛利率",
        "fields": [FIELD_FIN],
        "min_bars": 0,
        "window": 0,
        "formula": "最新报告期 gross_margin",
    },
    {
        "slug": "fund_pb",
        "family": "fundamental",
        "label": "市净率 PB",
        "fields": [FIELD_VAL],
        "min_bars": 0,
        "window": 0,
        "formula": "push2 f23 当前 PB",
    },
    {
        "slug": "fund_size_log_cap",
        "family": "fundamental",
        "label": "市值规模（对数）",
        "fields": [FIELD_VAL],
        "min_bars": 0,
        "window": 0,
        "formula": "ln(market_cap)（push2 透传）",
    },
]


NEUTRAL_POINTS: dict[str, float | None] = {
    "qlib_ma_cross": 0.0,
    "qlib_macd_hist": 0.0,
    "qlib_rsi_14": 50.0,
    "qlib_beta_60": 1.0,
    "qlib_aroon_25": 0.0,
    "alpha_corr_cv_10": 0.0,
    "alpha_rev_open_10": 0.0,
    "alpha_pvt_10": 0.0,
    "alpha_corr_cv_20": 0.0,
    "alpha_vwma_dev_20": 0.0,
    "gtja_mom_20": 0.0,
    "gtja_rsv_9": 50.0,
    "gtja_bias_60": 0.0,
    "gtja_atr_14": None,
    "gtja_pv_divergence": 0.0,
    "acad_max_60": None,
    "acad_idio_vol_60": None,
    "acad_amihud_proxy_60": None,
    "acad_low_vol_60": None,
    "acad_skew_60": 0.0,
    "fund_roe": 0.0,
    "fund_revenue_yoy": 0.0,
    "fund_gross_margin": None,
    "fund_pb": 1.0,
    "fund_size_log_cap": None,
}
