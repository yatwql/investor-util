"""指标 A/B/C 计算与三态判定（字段可得率 / 信号增量相关性 / 耗时比）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

#: 仓库根：scripts/_factor_zoo/<mod>.py → parents[2]（层级固定，勿改浅——改浅会静默扫错目录）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

from _factor_zoo.catalog import (
    BETA_WINDOW,
    B_MIN_DENOM,
    CATALOG,
    CORR_LOW,
    FAMILY_DEGRADED,
    FAMILY_MARKET_TEMPERATURE,
    FAMILY_REBALANCE,
    FAMILY_STYLE_BETA,
    FAMILY_TAIL_VAR,
    FAMILY_VALUATION_PERCENTILE,
    MIN_CODES_PER_DAY,
    MIN_PAIRS,
    STEP_NONZERO_FRACTION,
    TEMPERATURE_SLICE,
    THRESH_A,
    THRESH_B,
    THRESH_C,
    TYPE_COVERAGE,
)
from _factor_zoo.probe import (
    _field_coverage,
    _value_present,
)
from src.python.analysis.correlation import _pearson_pvalue  # 共享 Pearson + p 值


def metric_a(catalog: list[dict[str, Any]], field_results: dict[str, Any]) -> dict[str, Any]:
    """指标 A：可完整计算因子数 ÷ 25 ≥ 80%（每字段类型覆盖 ≥80% 池）。"""
    per_factor: dict[str, Any] = {}
    computable: list[str] = []
    for item in catalog:
        detail = _field_coverage(item, field_results)
        missing = [ftype for ftype, info in detail.items() if not info["ok"]]
        ok = not missing
        per_factor[item["slug"]] = {"ok": ok, "fields": detail, "missing": missing}
        if ok:
            computable.append(item["slug"])
    n = len(catalog) or 1
    ratio = len(computable) / n
    return {
        "metric": "A",
        "name": "字段可得率",
        "total": len(catalog),
        "computable": computable,
        "n_computable": len(computable),
        "ratio": round(ratio, 4),
        "threshold": THRESH_A,
        "pass": ratio >= THRESH_A,
        "per_factor": per_factor,
        "rule": f"每字段类型池内覆盖 ≥{TYPE_COVERAGE:.0%}；恰等算过；A 不过 → 提前终态不进 B/C",
    }


# ═══════════════════════════════════════════════════════════════
#  因子值计算（纯函数：bars + 指数 → 逐日值，None = 数据不足）
# ═══════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════
#  阶段 3：信号相关性（横截面日均值 vs 既有信号族日频序列）
# ═══════════════════════════════════════════════════════════════


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


def build_family_series(
    family: str, index_bars: list[dict], pool_mean_rets: dict[str, float] | None = None
) -> dict[str, float]:
    """既有信号族日频序列（复用 analysis 原语，快照域族抛 ValueError 表示降级）。"""
    if family == FAMILY_REBALANCE:
        raise ValueError(FAMILY_DEGRADED[FAMILY_REBALANCE])
    closes = _closes(index_bars)
    dates = [b.get("date") for b in index_bars]
    series: dict[str, float] = {}

    if family == FAMILY_MARKET_TEMPERATURE:
        from src.python.analysis.market_temperature import compute_temperature

        for i in range(TEMPERATURE_SLICE - 1, len(index_bars)):
            result = compute_temperature(index_bars[max(0, i - TEMPERATURE_SLICE + 1) : i + 1])
            if result.get("available") and _value_present(result.get("score")):
                series[dates[i]] = float(result["score"])
    elif family == FAMILY_VALUATION_PERCENTILE:
        from src.python.analysis.valuation_percentile import price_percentile

        for i in range(59, len(index_bars)):
            pct = price_percentile(closes[: i + 1])
            if pct is not None:
                series[dates[i]] = float(pct)
    elif family == FAMILY_TAIL_VAR:
        from src.python.analysis.tail_risk import compute_tail_risk

        for i in range(29, len(index_bars)):
            window_bars = [{"date": dates[j], "total_value": closes[j]} for j in range(max(0, i - 59), i + 1)]
            result = compute_tail_risk(window_bars)
            if result.get("available") and _value_present(result.get("var95")):
                series[dates[i]] = float(result["var95"])
    elif family == FAMILY_STYLE_BETA:
        from src.python.analysis.metrics_risk import portfolio_beta

        if not pool_mean_rets:
            raise ValueError("风格族需要池均值收益序列")
        idx_rets = _daily_returns(closes)
        for i in range(BETA_WINDOW, len(index_bars)):
            pr = [pool_mean_rets.get(d, 0.0) for d in dates[i - BETA_WINDOW : i]]
            br = [r if r == r else 0.0 for r in idx_rets[i - BETA_WINDOW : i]]
            beta = portfolio_beta(pr, br)
            if beta is not None:
                series[dates[i]] = float(beta)
    else:
        raise ValueError(f"未知信号族: {family}")
    return series


def _delta(series: dict[str, float]) -> dict[str, float]:
    """一阶差分（去趋势口径，预注册于判定书）。"""
    dates = sorted(series)
    return {dates[i]: series[dates[i]] - series[dates[i - 1]] for i in range(1, len(dates))}


def _is_step_signal(delta_values: list[float]) -> bool:
    """步进/常量型信号：Δ 非零占比 < STEP_NONZERO_FRACTION（季频基本面等）。"""
    if not delta_values:
        return True
    nonzero = sum(1 for v in delta_values if abs(v) > 1e-12)
    return nonzero / len(delta_values) < STEP_NONZERO_FRACTION


def evaluate_factor_correlation(
    factor_series: dict[str, float],
    family_series: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """单因子 vs 各信号族：Δ Pearson（共享原语），返回 max|ρ| 与逐族明细。"""
    factor_delta = _delta(factor_series)
    f_dates = sorted(factor_delta)
    f_vals = [factor_delta[d] for d in f_dates]
    step_signal = _is_step_signal(f_vals)
    per_family: dict[str, Any] = {}
    max_abs: float | None = None
    closest: str | None = None
    for family, series in family_series.items():
        if not series:
            per_family[family] = {"rho": None, "note": "信号族序列为空"}
            continue
        fam_delta = _delta(series)
        shared = [d for d in f_dates if d in fam_delta]
        if len(shared) < MIN_PAIRS:
            per_family[family] = {"rho": None, "note": f"对齐样本 {len(shared)} < {MIN_PAIRS}"}
            continue
        if step_signal:
            rho = 0.0
            note = "步进/常量型信号（季频值），日频 Δ 结构性不相关，按预注册口径 ρ=0"
        else:
            rho, _p = _pearson_pvalue(
                [factor_delta[d] for d in shared],
                [fam_delta[d] for d in shared],
            )
            note = ""
        per_family[family] = {"rho": round(rho, 4), "note": note}
        abs_rho = abs(rho)
        if max_abs is None or abs_rho > max_abs:
            max_abs, closest = abs_rho, family
    low_corr = max_abs is not None and max_abs < CORR_LOW
    return {
        "max_abs_rho": round(max_abs, 4) if max_abs is not None else None,
        "closest_family": closest,
        "low_corr": bool(low_corr),
        "step_signal": step_signal,
        "per_family": per_family,
        "note": "无可评估信号族时按不通过计（fail-closed）" if max_abs is None else "",
    }


def metric_b(catalog: list[dict[str, Any]], computable: list[str], corr_results: dict[str, Any]) -> dict[str, Any]:
    """指标 B：低相关（增量）因子 ÷ 可计算因子 ≥30%，分母 <10 判样本不足不通过。"""
    denom = len(computable)
    low = [slug for slug in computable if (corr_results.get(slug) or {}).get("low_corr")]
    ratio = (len(low) / denom) if denom else 0.0
    sample_ok = denom >= B_MIN_DENOM
    return {
        "metric": "B",
        "name": "信号增量（低相关占比）",
        "denom": denom,
        "n_low_corr": len(low),
        "low_corr_factors": low,
        "ratio": round(ratio, 4),
        "threshold": THRESH_B,
        "sample_ok": sample_ok,
        "pass": sample_ok and ratio >= THRESH_B,
        "per_factor": {slug: corr_results.get(slug) for slug in computable},
        "rule": (
            f"可计算因子中 max|ρ|<{CORR_LOW}（跨四个日频信号族，Δ Pearson，"
            f"共享原语）占比 ≥{THRESH_B:.0%}；分母 <{B_MIN_DENOM} 判样本不足；恰等算过"
        ),
        "catalog_labels": {c["slug"]: c["label"] for c in catalog},
    }


# ═══════════════════════════════════════════════════════════════
#  指标 C：耗时与基线
# ═══════════════════════════════════════════════════════════════


def read_report_baseline(perf_path: Path | None = None) -> dict[str, Any]:
    """真实报告耗时基线：perf_history 近 5 次 full 报告 total_seconds 中位数。"""
    path = perf_path or (_PROJECT_ROOT / "data" / "state" / "perf_history.jsonl")
    totals: list[float] = []
    compute_totals: list[float] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"available": False, "reason": f"基线文件不可读: {path}", "n": 0}
    for line in lines[-10:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("report_type") != "full":
            continue
        if _value_present(entry.get("total_seconds")):
            totals.append(float(entry["total_seconds"]))
        phases = entry.get("phases") or {}
        non_llm = sum(float(v) for k, v in phases.items() if k != "LLM+新闻" and _value_present(v))
        compute_totals.append(non_llm)
    if not totals:
        return {"available": False, "reason": "近 10 行无 full 报告记录", "n": 0}
    recent = totals[-5:]
    recent_compute = compute_totals[-5:]
    median = sorted(recent)[len(recent) // 2]
    return {
        "available": True,
        "n": len(recent),
        "samples": recent,
        "median_seconds": round(median, 3),
        "compute_only_median_seconds": round(sorted(recent_compute)[len(recent_compute) // 2], 3),
        "source": str(path),
        "rule": "基线 = 近 5 次 full 报告 total_seconds 中位数（含 LLM，真实整机实测）；"
        "非 LLM 计算阶段中位数作保守副口径一并记录",
    }


def metric_c(cold_seconds: float | None, warm_seconds: float, baseline: dict[str, Any]) -> dict[str, Any]:
    """指标 C：冷启动全量计算耗时 ÷ 基线报告耗时 ≤20%（恰等算过；冷/基线缺失判不通过）。"""
    if cold_seconds is None:
        return {
            "metric": "C",
            "name": "耗时预算",
            "pass": False,
            "threshold": THRESH_C,
            "warm_seconds": warm_seconds,
            "reason": "冷启动延迟不可实测（冷样本无有效冷请求或全部异常）",
            "rule": "冷启动不可测 → 不可判定 → 按不通过计（fail-closed，可复评）",
        }
    if not baseline.get("available") or not baseline.get("median_seconds"):
        return {
            "metric": "C",
            "name": "耗时预算",
            "pass": False,
            "threshold": THRESH_C,
            "cold_seconds": cold_seconds,
            "warm_seconds": warm_seconds,
            "reason": baseline.get("reason", "基线不可用"),
            "rule": "基线缺失 → 不可判定 → 按不通过计（fail-closed，可复评）",
        }
    baseline_s = float(baseline["median_seconds"])
    ratio = cold_seconds / baseline_s if baseline_s else float("inf")
    return {
        "metric": "C",
        "name": "耗时预算",
        "cold_seconds": round(cold_seconds, 3),
        "warm_seconds": round(warm_seconds, 3),
        "baseline_seconds": baseline_s,
        "ratio": round(ratio, 4),
        "threshold": THRESH_C,
        "pass": ratio <= THRESH_C,
        "baseline": baseline,
        "rule": "冷启动（冷样本均延迟 × 全量请求数 + 指数探测）÷ 基线中位数 ≤20%；恰等算过；"
        "冷/基线不可测按不通过计（可复评）",
    }


def judge(
    metric_a_res: dict[str, Any] | None, metric_b_res: dict[str, Any] | None, metric_c_res: dict[str, Any] | None
) -> dict[str, Any]:
    """终态判定：A/B/C 全过 → 立项；任一不过/缺失 → 归档未采纳（A 不过则 B/C 终态跳过）。"""
    results = {"A": metric_a_res, "B": metric_b_res, "C": metric_c_res}
    failed: list[str] = []
    for key in ("A", "B", "C"):
        res = results[key]
        if res is None:
            failed.append(f"{key}未评估")
        elif not res.get("pass"):
            failed.append(f"{key}未过")
    approved = not failed
    return {
        "verdict": "转正立项" if approved else "已评估未采纳",
        "approved": approved,
        "failed": failed,
        "metrics": {k: (v or {}).get("pass") for k, v in results.items()},
    }


# ═══════════════════════════════════════════════════════════════
#  阶段执行与产物落盘
# ═══════════════════════════════════════════════════════════════
