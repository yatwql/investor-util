"""评测阶段编排（catalog/fields/signals/timing 落盘，产物进评测目录）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import time

from _factor_zoo import PROJECT_ROOT
from _factor_zoo.catalog import (
    COLD_SAMPLE_CODES,
    FAMILIES,
    FAMILY_LABELS,
    FAMILY_MARKET_TEMPERATURE,
    FAMILY_NAMES,
    FAMILY_REBALANCE,
    FAMILY_STYLE_BETA,
    FAMILY_TAIL_VAR,
    FAMILY_VALUATION_PERCENTILE,
    FIELD_BARS,
    FIELD_FIN,
    FIELD_VAL,
    MIN_CODES_PER_DAY,
    THRESH_A,
    THRESH_B,
    THRESH_C,
    build_catalog,
    validate_catalog,
)
from _factor_zoo.metrics import (
    build_family_series,
    compute_factor_values,
    cross_sectional_series,
    evaluate_factor_correlation,
    metric_a,
    metric_b,
    metric_c,
    read_report_baseline,
    _closes,
    _daily_returns,
)
from _factor_zoo.probe import (
    build_stock_pool,
    probe_bars,
    probe_fields,
    probe_fin_indicator,
    probe_index,
    probe_valuation,
    _value_present,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def stage_catalog(out_dir: Path) -> list[dict[str, Any]]:
    print("[..] 阶段1：因子目录冻结（五族 × 5）")
    catalog = build_catalog()
    problems = validate_catalog(catalog)
    if problems:
        for problem in problems:
            print(f"    [!] {problem}")
        raise SystemExit("[ERR] 因子目录校验未过")
    _write_json(
        out_dir / "factor_catalog.json",
        {
            "catalog": catalog,
            "families": FAMILIES,
            "family_labels": FAMILY_LABELS,
            "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": "评测简化口径（族内可追溯出处）；不移植源族算子代码，转正实施需按源族口径复核",
        },
    )
    lines = ["# 因子目录（25，五族 × 5）", ""]
    for family in FAMILIES:
        lines.append(f"## {FAMILY_LABELS[family]}（{family}）")
        lines.append("")
        lines.append("| slug | 因子 | 所需字段 | 最少 bars | 口径 |")
        lines.append("|---|---|---|---:|---|")
        for item in catalog:
            if item["family"] == family:
                lines.append(
                    f"| `{item['slug']}` | {item['label']} | "
                    f"{'+'.join(item['fields'])} | {item['min_bars']} | {item['formula']} |"
                )
        lines.append("")
    (out_dir / "_catalog.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"    [OK] 25 因子冻结 → {out_dir / 'factor_catalog.json'}")
    return catalog


def stage_fields(out_dir: Path, refresh_pool: bool = False) -> dict[str, Any]:
    print("[..] 阶段2：股票池冻结 + 字段可得性探测（经既有链路）")
    catalog = _read_json(out_dir / "factor_catalog.json")
    if not catalog:
        raise SystemExit("[ERR] 未找到目录，请先运行 catalog 阶段")
    catalog = catalog["catalog"]

    pool_path = out_dir / "stock_pool.json"
    pool = _read_json(pool_path) if not refresh_pool else None
    if not pool:
        from src.python.config import resolve_holdings_path

        holdings_path = resolve_holdings_path()
        print(f"    [..] 持仓: {holdings_path}")
        pool = build_stock_pool(holdings_path)
        _write_json(pool_path, pool)
    print(
        f"    [OK] 股票池 {len(pool['codes'])} 只"
        f"（直接 {len(pool.get('direct_stocks') or [])} + 穿透 "
        f"{len(pool.get('penetration_stocks') or [])}）"
        + (f" [{pool.get('penetration_note')}]" if pool.get("penetration_note") else "")
    )

    started = time.perf_counter()
    probe_out = probe_fields(catalog, pool)
    total_seconds = round(time.perf_counter() - started, 3)
    field_results = probe_out["field_results"]
    field_results["codes"] = pool["codes"]

    report = metric_a(catalog, field_results)
    report["timings"] = probe_out["timings"]
    report["probe_total_seconds"] = total_seconds
    report["pool_size"] = probe_out["pool_size"]
    report["captured_at"] = probe_out["built_at"]
    _write_json(out_dir / "fields_report.json", report)

    # 探测原始数据（bars/指数）落盘供 signals 阶段复用（避免重复打源）
    _write_json(
        out_dir / "probe_cache.json",
        {
            "bars_by_code": field_results.get("bars_by_code"),
            "index_bars": field_results.get("index_bars"),
            "valuation": field_results.get("per_code", {}).get(FIELD_VAL),
            "fin_indicator": field_results.get("per_code", {}).get(FIELD_FIN),
        },
    )
    status = "[OK]" if report["pass"] else "[!]"
    print(
        f"    {status} 指标 A：{report['n_computable']}/{report['total']} = "
        f"{report['ratio']:.1%}（阈值 {THRESH_A:.0%}）→ {'过' if report['pass'] else '不过'}"
    )
    if not report["pass"]:
        for slug, info in report["per_factor"].items():
            if not info["ok"]:
                print(f"      [!] {slug} 缺: {'+'.join(info['missing'])}")
    return report


def stage_signals(out_dir: Path) -> dict[str, Any]:
    print("[..] 阶段3：可计算因子信号 vs 既有信号族相关性")
    fields_report = _read_json(out_dir / "fields_report.json")
    if not fields_report:
        raise SystemExit("[ERR] 未找到 fields_report.json，请先运行 fields 阶段")
    if not fields_report.get("pass"):
        print("    [!] 指标 A 未过 → 按设计提前终态，不进阶段 3/4")
        _write_json(
            out_dir / "signals_report.json",
            {
                "metric": "B",
                "skipped": True,
                "reason": "指标 A 未过，提前终态",
                "pass": False,
                "denom": 0,
                "ratio": 0.0,
                "threshold": THRESH_B,
            },
        )
        return {"skipped": True, "pass": False}

    probe = _read_json(out_dir / "probe_cache.json")
    if not probe:
        raise SystemExit("[ERR] 未找到 probe_cache.json，请先运行 fields 阶段")
    bars_by_code = probe.get("bars_by_code") or {}
    index_bars = probe.get("index_bars") or []
    valuation = probe.get("valuation") or {}
    fin_indicator = probe.get("fin_indicator") or {}
    started = time.perf_counter()

    computable = fields_report["computable"]
    catalog = _read_json(out_dir / "factor_catalog.json")["catalog"]
    label_by_slug = {c["slug"]: c for c in catalog}

    # ── 因子横截面日均值序列 ──
    factor_series: dict[str, dict[str, float]] = {}
    for slug in computable:
        item = label_by_slug[slug]
        values_by_code: dict[str, list[tuple[str, float | None]]] = {}
        for code, bars in bars_by_code.items():
            if not bars:
                continue
            scalar: float | None = None
            if FIELD_FIN in item["fields"]:
                record = fin_indicator.get(code) or {}
                scalar = (
                    record.get("roe")
                    if slug == "fund_roe"
                    else (record.get("revenue_yoy") if slug == "fund_revenue_yoy" else record.get("gross_margin"))
                )
                if isinstance(scalar, str):
                    try:
                        scalar = float(scalar)
                    except ValueError:
                        scalar = None
            elif FIELD_VAL in item["fields"]:
                record = valuation.get(code) or {}
                if slug == "fund_pb":
                    scalar = record.get("pb")
                elif slug == "fund_size_log_cap":
                    scalar = json_cap_log(record.get("market_cap"))
            values = compute_factor_values(slug, bars, index_bars, scalar=scalar)
            dates = [b.get("date") for b in bars]
            values_by_code[code] = list(zip(dates, values))
        series = cross_sectional_series(values_by_code)
        if series:
            factor_series[slug] = series

    # ── 池均值日收益（风格族输入）与信号族序列 ──
    pool_mean = _pool_mean_returns(bars_by_code, index_bars)
    family_series: dict[str, dict[str, float]] = {}
    degraded: dict[str, str] = {}
    for family in (
        FAMILY_MARKET_TEMPERATURE,
        FAMILY_VALUATION_PERCENTILE,
        FAMILY_TAIL_VAR,
        FAMILY_STYLE_BETA,
        FAMILY_REBALANCE,
    ):
        try:
            series = build_family_series(family, index_bars, pool_mean)
            if series:
                family_series[family] = series
            else:
                degraded[family] = "序列为空（数据不足）"
        except ValueError as exc:
            degraded[family] = str(exc)

    corr_results = {slug: evaluate_factor_correlation(series, family_series) for slug, series in factor_series.items()}
    # 无可评估序列的可计算因子：fail-closed 记不可评估
    for slug in computable:
        corr_results.setdefault(
            slug,
            {
                "max_abs_rho": None,
                "closest_family": None,
                "low_corr": False,
                "step_signal": False,
                "per_family": {},
                "note": "因子序列为空，不可评估（fail-closed 按不通过计）",
            },
        )

    report = metric_b(catalog, computable, corr_results)
    report["skipped"] = False
    report["family_series_sizes"] = {k: len(v) for k, v in family_series.items()}
    report["family_degraded"] = degraded
    report["factor_series_sizes"] = {k: len(v) for k, v in factor_series.items()}
    report["compute_seconds"] = round(time.perf_counter() - started, 3)
    report["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(out_dir / "signals_report.json", report)
    status = "[OK]" if report["pass"] else "[!]"
    print(
        f"    {status} 指标 B：{report['n_low_corr']}/{report['denom']} = "
        f"{report['ratio']:.1%}（阈值 {THRESH_B:.0%}）→ {'过' if report['pass'] else '不过'}"
    )
    for family, reason in degraded.items():
        print(f"    [!] 信号族 {FAMILY_NAMES.get(family, family)} 降级: {reason}")
    return report


def json_cap_log(cap: Any) -> float | None:
    """log10(market_cap)×100（对数市值），非法/非有限值返回 None。"""
    import math

    if not _value_present(cap):
        return None
    try:
        value = float(cap)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return round(math.log10(value) * 100, 2)


def _pool_mean_returns(bars_by_code: dict[str, list[dict]], index_bars: list[dict]) -> dict[str, float]:
    """池内等权日收益（风格族滚动 Beta 的组合腿）。"""
    per_code: dict[str, dict[str, float]] = {}
    for code, bars in bars_by_code.items():
        closes = _closes(bars)
        rets = _daily_returns(closes)
        per_code[code] = {bars[i].get("date"): rets[i] for i in range(len(bars)) if rets[i] == rets[i]}
    dates = sorted({d for series in per_code.values() for d in series})
    mean: dict[str, float] = {}
    for date in dates:
        values = [series[date] for series in per_code.values() if date in series]
        if len(values) >= MIN_CODES_PER_DAY:
            mean[date] = sum(values) / len(values)
    return mean


def measure_cold_sample() -> dict[str, Any]:
    """池外样本测冷请求延迟（bars/估值/财务 + 指数）→ 冷启动估算均值。

    样本码若已缓存则如实标记（暖值不计入冷均值；全部暖 → 均值不可得）。
    """
    cache_dir = PROJECT_ROOT / "data" / "cache"
    samples: list[dict[str, Any]] = []
    cold_durations: list[float] = []

    def _cached(prefix: str, code: str) -> bool:
        return any(cache_dir.glob(f"{prefix}{code}*"))

    for code in COLD_SAMPLE_CODES:
        entry: dict[str, Any] = {"code": code}
        for ftype, prefix, fn in (
            (FIELD_BARS, "history_stock_", probe_bars),
            (FIELD_VAL, "price_stock_", probe_valuation),
            (FIELD_FIN, "fin_indicator_", probe_fin_indicator),
        ):
            cached = _cached(prefix, code)
            t0 = time.perf_counter()
            try:
                value = fn(code)
                ok = bool(value)
            except Exception as exc:  # 样本失败仅记录（冷均值按成功冷样本）
                value, ok = None, False
                entry[f"{ftype}_error"] = f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - t0
            entry[ftype] = {"cached": cached, "ok": ok, "seconds": round(elapsed, 3)}
            if ok and not cached:
                cold_durations.append(elapsed)
        samples.append(entry)

    t0 = time.perf_counter()
    try:
        index_ok = bool(probe_index())
    except Exception:
        index_ok = False
    index_seconds = time.perf_counter() - t0
    mean_cold = (sum(cold_durations) / len(cold_durations)) if cold_durations else None
    return {
        "samples": samples,
        "cold_request_count": len(cold_durations),
        "mean_cold_request_seconds": round(mean_cold, 4) if mean_cold else None,
        "index_probe_seconds": round(index_seconds, 3),
        "index_ok": index_ok,
    }


def stage_timing(out_dir: Path) -> dict[str, Any]:
    print("[..] 阶段4：耗时与基线（指标 C）")
    fields_report = _read_json(out_dir / "fields_report.json")
    signals_report = _read_json(out_dir / "signals_report.json")
    if not fields_report:
        raise SystemExit("[ERR] 未找到 fields_report.json，请先运行 fields 阶段")
    if signals_report is None:
        raise SystemExit("[ERR] 未找到 signals_report.json，请先运行 signals 阶段")

    warm = 0.0 if signals_report.get("skipped") else float(signals_report.get("compute_seconds") or 0.0)
    baseline = read_report_baseline()

    # 冷启动估算：池外冷样本均延迟 × 全量请求数（池码 × 三字段类型 + 指数一次）
    try:
        cold_info = measure_cold_sample()
    except Exception as exc:
        cold_info = {"samples": [], "error": f"{type(exc).__name__}: {exc}", "mean_cold_request_seconds": None}
    pool_size = int(fields_report.get("pool_size") or 0)
    requests = pool_size * 3 + 1
    mean_cold = cold_info.get("mean_cold_request_seconds")
    cold_estimate: float | None = None
    if mean_cold:
        cold_estimate = mean_cold * requests + float(cold_info.get("index_probe_seconds") or 0.0)

    report = metric_c(cold_estimate, warm, baseline)
    report["cold_basis"] = (
        f"池外冷样本均延迟 {mean_cold}s × {pool_size} 码 × 3 字段类型 + 指数探测"
        if mean_cold
        else "冷样本无有效冷请求（全部缓存命中或失败）"
    )
    report["cold_sample"] = cold_info
    report["estimated_requests"] = requests
    report["warm_probe_total_seconds"] = fields_report.get("probe_total_seconds")
    report["timings_by_field"] = fields_report.get("timings") or {}
    report["skipped_signals"] = bool(signals_report.get("skipped"))
    report["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(out_dir / "timing_report.json", report)
    status = "[OK]" if report.get("pass") else "[!]"
    if "ratio" in report:
        print(
            f"    {status} 指标 C：冷启动估算 {report.get('cold_seconds')}s ÷ "
            f"基线 {report.get('baseline_seconds')}s = {report.get('ratio'):.1%}"
            f"（阈值 {THRESH_C:.0%}）；温态在跑 {report.get('warm_seconds')}s"
        )
    else:
        print(f"    [!] 指标 C 不可判定: {report.get('reason')}")
    return report
