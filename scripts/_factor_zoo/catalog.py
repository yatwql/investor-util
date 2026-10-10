"""预注册判定口径与冻结因子目录（门槛常量 + 五族×5 目录 + 冻结校验）。

改本文件 = 改评测门槛：THRESH/CORR/口径常量与目录条目均在判定书中预注册。
"""

from __future__ import annotations

from typing import Any

from _factor_zoo import PROJECT_ROOT


# ── 常量（门槛与口径在判定书中预注册，改这里等于改门槛） ──────────────
OUT_DIR_DEFAULT = PROJECT_ROOT / "docs" / "tmp" / "factor-zoo"
THRESH_A = 0.80  # 字段可得率 ≥80%（≥20/25）
THRESH_B = 0.30  # 低相关（增量）因子占比 ≥30%
THRESH_C = 0.20  # 耗时增量 ≤20%
CORR_LOW = 0.5  # |ρ| < 0.5 计「低相关」
B_MIN_DENOM = 10  # 指标 B 分母下限（样本不足判不通过）
TYPE_COVERAGE = 0.80  # 字段类型可得 = 池内 ≥80% 代码有效
MIN_PAIRS = 30  # 相关性评估最少对齐样本（Δ 后）
MIN_CODES_PER_DAY = 3  # 横截面日均值最少成分数
STEP_NONZERO_FRACTION = 0.05  # Δ 非零占比低于此 = 步进/常量型信号（结构性不相关）
LOOKBACK_DAYS = 365  # 回看窗口（自然日，K 线链路按此折算交易日）
DAYS_PER_YEAR_TD = 250  # 「N 年」标签的交易日折算（保守口径，与成本模型同源）

FIELD_BARS = "bars"
FIELD_INDEX = "index"
FIELD_VAL = "valuation"
FIELD_FIN = "fin_indicator"
FIELD_TYPES = (FIELD_BARS, FIELD_INDEX, FIELD_VAL, FIELD_FIN)

FAMILY_MARKET_TEMPERATURE = "market_temperature"
FAMILY_VALUATION_PERCENTILE = "valuation_percentile"
FAMILY_TAIL_VAR = "tail_risk_var95"
FAMILY_STYLE_BETA = "style_beta"
FAMILY_REBALANCE = "rebalance_overflow"  # 快照域信号族（非日频）→ 降级不参与
FAMILY_DEGRADED = {
    FAMILY_REBALANCE: "再平衡超限为持仓快照域（非日频）信号族，无法构造日频序列，按设计降级不参与相关性评估"
}

BETA_WINDOW = 60  # 风格族滚动 Beta 窗口（交易日）
TEMPERATURE_SLICE = 120  # 温度族滚动窗口切片（覆盖 MIN_SAMPLES=60 + 缓冲）

FAMILY_NAMES = {
    FAMILY_MARKET_TEMPERATURE: "市场温度",
    FAMILY_VALUATION_PERCENTILE: "估值/价格分位（代理）",
    FAMILY_TAIL_VAR: "尾部风险 VaR95",
    FAMILY_STYLE_BETA: "风格 Beta",
    FAMILY_REBALANCE: "再平衡超限",
}

# ── 因子目录：五族 × 5（评测简化口径，族内可追溯到出处；不移植算子代码） ──
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

FAMILIES = ["qlib158", "alpha101", "gtja191", "academic", "fundamental"]
FAMILY_LABELS = {
    "qlib158": "qlib158 技术因子族",
    "alpha101": "alpha101 量价族",
    "gtja191": "gtja191 量价形态族",
    "academic": "academic 学术效应族",
    "fundamental": "fundamental 基本面族",
}

BENCHMARK_INDEX = "sh000300"  # 市场相对族与因子统一基准

# 冷启动延迟样本（池外大盘股，仅测冷请求延迟，不入池；有缓存命中则标记）
COLD_SAMPLE_CODES = ["600519", "000858", "300750"]


# ═══════════════════════════════════════════════════════════════
#  阶段 1：目录构建与校验（纯逻辑，无 I/O 副作用）
# ═══════════════════════════════════════════════════════════════


def build_catalog() -> list[dict[str, Any]]:
    """返回冻结因子目录（五族 × 5，确定性：同输入同输出）。"""
    return [dict(item) for item in CATALOG]


def validate_catalog(catalog: list[dict[str, Any]]) -> list[str]:
    """目录完整性校验：25 条、五族各 5、slug 唯一、字段类型合法、族名合法。"""
    problems: list[str] = []
    if len(catalog) != 25:
        problems.append(f"目录条数 {len(catalog)} != 25")
    slugs = [item.get("slug") for item in catalog]
    if len(set(slugs)) != len(slugs):
        problems.append("slug 存在重复")
    for family in FAMILIES:
        n = sum(1 for item in catalog if item.get("family") == family)
        if n != 5:
            problems.append(f"族 {family} 条数 {n} != 5")
    for item in catalog:
        fields = item.get("fields") or []
        if not fields:
            problems.append(f"{item.get('slug')}: fields 为空")
        for field in fields:
            if field not in FIELD_TYPES:
                problems.append(f"{item.get('slug')}: 未知字段类型 {field}")
        if not item.get("label") or not item.get("formula"):
            problems.append(f"{item.get('slug')}: 缺 label/formula")
    return problems


# ═══════════════════════════════════════════════════════════════
#  阶段 2：股票池与字段可得性（经既有链路取数；网络层可注入替换）
# ═══════════════════════════════════════════════════════════════
