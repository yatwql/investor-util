"""因子计算原语（语义名 factor_formulas）— 单因子逐日值纯函数集。

从门槛判定书的冻结评测实现逐行移植（滚动 / 嵌入 / 相关 / Beta 原语全量），
保持与判定书可复算的同一口径：改本模块等于改因子因子口径，须复算判定书
结论后同步。私有模块：仅供 analysis.factor_evaluator 消费。

纪律：纯计算——不取数、不写盘、不 import fetcher / report / llm。
"""

from __future__ import annotations


from src.python.analysis.correlation import _pearson_pvalue
from src.python.schemas.factor_catalog import (
    CATALOG,
    MIN_CODES_PER_DAY,
    value_present as _value_present,
)

__all__ = ["compute_factor_values", "cross_sectional_series"]

# ── 滚动/嵌入/相关原语（移植自判定书冻结实现，含内部工具函数） ──


def _closes(bars: list[dict]) -> list[float]:
    out = []
    for bar in bars:
        try:
            out.append(float(bar["close"]))
        except (KeyError, TypeError, ValueError):
            out.append(float("nan"))
    return out


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v == v]
    return sum(vals) / len(vals) if vals else None


def _std(values: list[float]) -> float | None:
    vals = [v for v in values if v == v]
    n = len(vals)
    if n < 2:
        return None
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return var**0.5


def _pearson(values_x: list[float], values_y: list[float]) -> float | None:
    """共享 Pearson（复用 correlation 原语，退化返回 0.0）。"""
    pairs = [(x, y) for x, y in zip(values_x, values_y) if x == x and y == y]
    if len(pairs) < 3:
        return None
    r, _p = _pearson_pvalue([p[0] for p in pairs], [p[1] for p in pairs])
    return r


def _ema(values: list[float], span: int) -> list[float | None]:
    alpha = 2.0 / (span + 1)
    out: list[float | None] = []
    prev: float | None = None
    for i, value in enumerate(values):
        if i == 0:
            prev = value
        elif prev is None:
            prev = value
        else:
            prev = alpha * value + (1 - alpha) * prev
        out.append(prev if i >= span - 1 else None)
    return out


def _rolling_beta(rets: list[float], mkt: list[float], window: int) -> list[float | None]:
    """滚动 Beta（协方差法，与 metrics_risk.portfolio_beta 同口径）。"""
    out: list[float | None] = [None] * len(rets)
    for i in range(window, len(rets) + 1):
        pr = rets[i - window : i]
        br = mkt[i - window : i]
        mp, mb = sum(pr) / window, sum(br) / window
        cov = sum((a - mp) * (b - mb) for a, b in zip(pr, br)) / (window - 1)
        var = sum((b - mb) ** 2 for b in br) / (window - 1)
        out[i - 1] = cov / var if var > 0 else None
    return out


def _daily_returns(closes: list[float]) -> list[float]:
    rets = [float("nan")]
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        rets.append((closes[i] / prev - 1) if prev == prev and prev else float("nan"))
    return rets


def _aligned_index_returns(bars: list[dict], index_bars: list[dict]) -> list[float]:
    """按 bars 日期对齐的指数日收益（缺日为 NaN，相关性成对剔除）。"""
    closes = _closes(index_bars)
    dates = [b.get("date") for b in index_bars]
    date_pos = {d: i for i, d in enumerate(dates)}
    out: list[float] = []
    for bar in bars:
        pos = date_pos.get(bar.get("date"))
        value = float("nan")
        if pos is not None and pos > 0 and closes[pos - 1]:
            value = closes[pos] / closes[pos - 1] - 1
        out.append(value)
    return out


# ── 单因子逐日值（bars + 指数 → 对齐日期的逐日值，None = 数据不足） ──


def compute_factor_values(
    slug: str, bars: list[dict], index_bars: list[dict], scalar: float | None = None
) -> list[float | None]:
    """单因子逐日值（对齐 bars 日期；步进型基本面传入 scalar 铺满）。"""
    closes = _closes(bars)
    n = len(bars)
    if n == 0:
        return []
    if scalar is not None:
        return [scalar if _value_present(scalar) else None] * n
    rets = _daily_returns(closes)
    idx_rets = _aligned_index_returns(bars, index_bars)
    item = next((c for c in CATALOG if c["slug"] == slug), None)
    window = int(item["window"]) if item else 20
    out: list[float | None] = [None] * n

    if slug == "qlib_ma_cross":
        for i in range(window, n):
            ma = _mean(closes[i - window : i])
            out[i] = (closes[i] - ma) / ma if ma else None
    elif slug == "qlib_macd_hist":
        ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
        diff = [a - b if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
        signal = _ema([d if d is not None else 0.0 for d in diff], 9)
        for i in range(n):
            if diff[i] is not None and signal[i] is not None:
                out[i] = diff[i] - signal[i]
    elif slug == "qlib_rsi_14":
        for i in range(window, n):
            seg = rets[i - window : i + 1][1:]
            gains = sum(r for r in seg if r == r and r > 0)
            losses = -sum(r for r in seg if r == r and r < 0)
            if gains + losses == 0:
                out[i] = 50.0
            else:
                out[i] = 100.0 * gains / (gains + losses)
    elif slug == "qlib_beta_60":
        for i, beta in enumerate(
            _rolling_beta(
                [r if r == r else 0.0 for r in rets],
                [r if r == r else 0.0 for r in idx_rets],
                window,
            )
        ):
            out[i] = beta
    elif slug == "qlib_aroon_25":
        for i in range(window, n):
            seg_h = [float(bars[j]["high"]) for j in range(i - window + 1, i + 1)]
            seg_l = [float(bars[j]["low"]) for j in range(i - window + 1, i + 1)]
            high_at = max(range(len(seg_h)), key=lambda k: seg_h[k])
            low_at = max(range(len(seg_l)), key=lambda k: -seg_l[k])
            up = 100.0 * (window - 1 - high_at) / (window - 1)
            down = 100.0 * (window - 1 - low_at) / (window - 1)
            out[i] = (up - down) / 100.0
    elif slug in ("alpha_corr_cv_10", "alpha_corr_cv_20", "alpha_rev_open_10"):
        open_prices = [float(b["open"]) for b in bars]
        for i in range(window, n):
            seg_c = closes[i - window : i + 1]
            seg_o = open_prices[i - window : i + 1]
            seg_v = [float(b["volume"]) for b in bars[i - window : i + 1]]
            xs = seg_o if slug == "alpha_rev_open_10" else seg_c
            r = _pearson(xs, seg_v)
            out[i] = -r if r is not None else None
    elif slug == "alpha_pvt_10":
        for i in range(window, n):
            acc, vol_sum = 0.0, 0.0
            for j in range(i - window + 1, i + 1):
                vol = float(bars[j]["volume"])
                acc += (closes[j] - closes[j - 1]) * vol
                vol_sum += vol
            out[i] = acc / vol_sum if vol_sum else None
    elif slug == "alpha_vwma_dev_20":
        for i in range(window, n):
            seg_c = closes[i - window : i + 1]
            seg_v = [float(b["volume"]) for b in bars[i - window : i + 1]]
            vol_sum = sum(seg_v)
            vwma = sum(c * v for c, v in zip(seg_c, seg_v)) / vol_sum if vol_sum else None
            out[i] = (closes[i] - vwma) / vwma if vwma else None
    elif slug == "gtja_mom_20":
        for i in range(window, n):
            prev = closes[i - window]
            out[i] = closes[i] / prev - 1 if prev else None
    elif slug == "gtja_rsv_9":
        for i in range(window, n):
            seg_h = [float(bars[j]["high"]) for j in range(i - window + 1, i + 1)]
            seg_l = [float(bars[j]["low"]) for j in range(i - window + 1, i + 1)]
            hi, lo = max(seg_h), min(seg_l)
            out[i] = (closes[i] - lo) / (hi - lo) if hi > lo else None
    elif slug == "gtja_bias_60":
        for i in range(window, n):
            ma = _mean(closes[i - window : i])
            out[i] = (closes[i] - ma) / ma if ma else None
    elif slug == "gtja_atr_14":
        trs: list[float] = []
        for i in range(1, n):
            high, low = float(bars[i]["high"]), float(bars[i]["low"])
            prev_close = closes[i - 1]
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        for i in range(window, n):
            atr = _mean(trs[i - window : i])
            out[i] = atr / closes[i] if atr and closes[i] else None
    elif slug == "gtja_pv_divergence":
        for i in range(window, n):
            mom = closes[i] / closes[i - window] - 1 if closes[i - window] else None
            seg_v = [float(bars[j]["volume"]) for j in range(i - 9, i + 1)]
            slope = _pearson(list(range(len(seg_v))), seg_v)
            if mom is None or slope is None or mom == 0 or slope == 0:
                out[i] = None
            else:
                out[i] = -1.0 if (mom > 0) == (slope > 0) else 1.0
    elif slug == "acad_max_60":
        for i in range(window, n):
            intraday = []
            for j in range(i - window + 1, i + 1):
                op = float(bars[j]["open"])
                intraday.append(float(bars[j]["high"]) / op - 1 if op else float("nan"))
            out[i] = max(v for v in intraday if v == v) if any(v == v for v in intraday) else None
    elif slug == "acad_idio_vol_60":
        resid = [(r - m) if r == r and m == m else float("nan") for r, m in zip(rets, idx_rets)]
        for i in range(window, n):
            out[i] = _std(resid[i - window + 1 : i + 1])
    elif slug == "acad_amihud_proxy_60":
        for i in range(window, n):
            accs = []
            for j in range(i - window + 1, i + 1):
                r, vol = rets[j], float(bars[j]["volume"])
                if r == r and vol > 0:
                    accs.append(abs(r) / vol * 1e9)  # 量纲归一（口径差异入判定书）
            out[i] = _mean(accs)
    elif slug == "acad_low_vol_60":
        for i in range(window, n):
            out[i] = _std(rets[i - window + 1 : i + 1])
    elif slug == "acad_skew_60":
        for i in range(window, n):
            seg = [r for r in rets[i - window + 1 : i + 1] if r == r]
            m, sd = _mean(seg), _std(seg)
            if m is None or not sd or len(seg) < 3:
                continue
            skew = sum(((v - m) / sd) ** 3 for v in seg) * len(seg) / ((len(seg) - 1) * (len(seg) - 2))
            out[i] = skew
    return out


# ── 横截面日均值（当日有效成分数 < MIN_CODES_PER_DAY 的日期剔除） ──


def cross_sectional_series(
    factor_values_by_code: dict[str, list[tuple[str, float | None]]],
) -> dict[str, float]:
    """横截面日均值：{date: mean(当日有效因子值)}（成分数 < MIN_CODES_PER_DAY 的日期剔除）。"""
    buckets: dict[str, list[float]] = {}
    for _code, pairs in factor_values_by_code.items():
        for date, value in pairs:
            if value is None or value != value:
                continue
            buckets.setdefault(date, []).append(value)
    series: dict[str, float] = {}
    for date in sorted(buckets):
        values = buckets[date]
        if len(values) >= MIN_CODES_PER_DAY:
            series[date] = sum(values) / len(values)
    return series
