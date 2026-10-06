"""factor_zoo_eval（因子动物园目录评测）脚本单元测试。

覆盖：目录冻结校验与结构关系、指标 A/B/C 阈值边界（恰等过 / 差一点不过 /
fail-closed）、判定书三态、报告耗时基线读取、相关性口径（比例同向不计低相关 /
独立计低相关 / 阶跃口径 / 空族不通过）、截面序列降维、对数市值字段、注入探针
（网络无关）。边界/异常场景见 test_factor_zoo_eval_edge.py。
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # 仓库根目录
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的评测脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / name
    mod_name = name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ev():
    return _load_script("factor_zoo_eval.py")


pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
]


# ── 目录冻结与结构关系 ──────────────────────────────────────────


def test_catalog_frozen_valid_and_deterministic(ev):
    """目录可复现（两次构造逐字段一致）且通过冻结校验。"""
    first = ev.build_catalog()
    second = ev.build_catalog()
    assert first == second
    assert ev.validate_catalog(first) == []


def test_catalog_structure_relations(ev):
    """目录结构关系：slug 全局唯一、族域与 FAMILIES 双向一致、条目必备键齐全。"""
    catalog = ev.build_catalog()
    slugs = [item["slug"] for item in catalog]
    assert len(slugs) == len(set(slugs))
    assert {item["family"] for item in catalog} == set(ev.FAMILIES)
    for item in catalog:
        assert {"slug", "family", "label", "fields", "min_bars"} <= set(item)
        assert item["fields"]  # 每因子至少声明一个字段类型
        assert item["label"]


def test_validate_catalog_catches_mutations(ev):
    """冻结校验能抓住结构破坏：删条目 / slug 重复 / 族不全 均产生问题。"""
    base = ev.build_catalog()

    missing = base[:-1]
    assert ev.validate_catalog(missing)

    duplicated = [dict(item) for item in base]
    duplicated[-1] = dict(duplicated[0])
    assert ev.validate_catalog(duplicated)

    wrong_family = [dict(item) for item in base]
    wrong_family[0]["family"] = "not_a_family"
    assert ev.validate_catalog(wrong_family)


# ── 指标 A：字段可得率（阈值边界） ─────────────────────────────


def _cat(n_index: int, n_val: int) -> list[dict]:
    items = [
        {"slug": f"ix{i}", "family": "t", "label": f"IX{i}", "fields": ["index"], "min_bars": 0} for i in range(n_index)
    ]
    items += [
        {"slug": f"vl{i}", "family": "t", "label": f"VL{i}", "fields": ["valuation"], "min_bars": 0}
        for i in range(n_val)
    ]
    return items


def _fr_val_none(n_codes: int = 10) -> dict:
    codes = [f"c{i}" for i in range(n_codes)]
    return {
        "codes": codes,
        "index_ok": True,
        "bars_by_code": {},
        "per_code": {"valuation": {c: {"pb": None, "market_cap": None} for c in codes}},
    }


def test_metric_a_exact_threshold_passes(ev):
    """20/25 = 80% 恰等 → 通过（预注册：恰等算过）。"""
    res = ev.metric_a(_cat(20, 5), _fr_val_none())
    assert res["n_computable"] == 20
    assert res["ratio"] == ev.THRESH_A
    assert res["pass"] is True
    assert res["per_factor"]["ix0"]["ok"] is True
    assert res["per_factor"]["vl0"]["missing"] == [ev.FIELD_VAL]


def test_metric_a_below_threshold_fails(ev):
    """19/25 = 76% < 80% → 不通过。"""
    res = ev.metric_a(_cat(19, 6), _fr_val_none())
    assert res["n_computable"] == 19
    assert res["ratio"] < ev.THRESH_A
    assert res["pass"] is False


def test_metric_a_type_coverage_boundary(ev):
    """单字段类型池内覆盖恰等 8/10=80% → 过；7/10=70% → 该因子不可算。"""
    catalog = [{"slug": "fund_pb", "family": "fundamental", "label": "PB", "fields": [ev.FIELD_VAL], "min_bars": 0}]
    codes = [f"c{i}" for i in range(10)]
    for n_ok, expect_ok in ((8, True), (7, False)):
        per_code = {c: {"pb": float(i) if i < n_ok else None} for i, c in enumerate(codes)}
        res = ev.metric_a(
            catalog, {"codes": codes, "index_ok": True, "bars_by_code": {}, "per_code": {"valuation": per_code}}
        )
        detail = res["per_factor"]["fund_pb"]["fields"][ev.FIELD_VAL]
        assert detail["ok"] is expect_ok
        assert res["pass"] is expect_ok


def test_metric_a_bars_min_bars_coverage(ev):
    """bars 按 min_bars 条数口径：4/5=80% 过、3/5=60% 不过。"""
    catalog = [{"slug": "qlib_ma_cross", "family": "qlib158", "label": "MA", "fields": [ev.FIELD_BARS], "min_bars": 25}]
    codes = [f"c{i}" for i in range(5)]

    def bars(n_ok: int) -> dict:
        return {
            c: [{"date": f"d{i}", "close": 1.0} for i in range(30 if i < n_ok else 10)] for i, c in enumerate(codes)
        }

    for n_ok, expect_ok in ((4, True), (3, False)):
        res = ev.metric_a(catalog, {"codes": codes, "index_ok": True, "bars_by_code": bars(n_ok), "per_code": {}})
        assert res["per_factor"]["qlib_ma_cross"]["ok"] is expect_ok


# ── 指标 B：低相关占比（阈值边界 + 样本量） ────────────────────


def _cb(n: int) -> list[dict]:
    return [{"slug": f"f{i}", "label": f"F{i}", "family": "t"} for i in range(n)]


def _corr(n_low: int, n_total: int) -> dict:
    """扁平 corr_results：前 n_low 个为低相关。"""
    return {f"f{i}": {"max_abs_rho": 0.7 if i < n_low else 0.1, "low_corr": i < n_low} for i in range(n_total)}


def test_metric_b_exact_threshold_passes(ev):
    """3/10 = 30% 恰等 → 通过；分母 10 ≥ 下限。"""
    res = ev.metric_b(_cb(10), [f"f{i}" for i in range(10)], _corr(3, 10))
    assert res["denom"] == 10
    assert res["n_low_corr"] == 3
    assert res["ratio"] == ev.THRESH_B
    assert res["sample_ok"] is True
    assert res["pass"] is True


def test_metric_b_below_threshold_fails(ev):
    """2/10 = 20% < 30% → 不通过。"""
    res = ev.metric_b(_cb(10), [f"f{i}" for i in range(10)], _corr(2, 10))
    assert res["ratio"] < ev.THRESH_B
    assert res["pass"] is False


def test_metric_b_sample_insufficient_fails(ev):
    """分母 9 < 10 → 样本不足，即使低相关占比 100% 也不通过。"""
    res = ev.metric_b(_cb(9), [f"f{i}" for i in range(9)], _corr(9, 9))
    assert res["sample_ok"] is False
    assert res["pass"] is False


# ── 指标 C：耗时预算（阈值边界 + fail-closed） ─────────────────


def _baseline(median: float = 400.0) -> dict:
    return {"available": True, "median_seconds": median, "n": 5}


def test_metric_c_exact_threshold_passes(ev):
    """80/400 = 20% 恰等 → 通过。"""
    res = ev.metric_c(80.0, 0.1, _baseline())
    assert res["ratio"] == ev.THRESH_C
    assert res["pass"] is True


def test_metric_c_above_threshold_fails(ev):
    """80.1/400 > 20% → 不通过。"""
    res = ev.metric_c(80.1, 0.1, _baseline())
    assert res["pass"] is False


def test_metric_c_unmeasurable_fails_closed(ev):
    """冷启动不可实测 → 不可判定 → 按不通过计。"""
    res = ev.metric_c(None, 0.1, _baseline())
    assert res["pass"] is False
    assert "不可实测" in res["reason"]


def test_metric_c_missing_baseline_fails_closed(ev):
    """基线缺失 → 不可判定 → 按不通过计。"""
    res = ev.metric_c(1.0, 0.1, {"available": False, "reason": "无历史记录"})
    assert res["pass"] is False
    assert res["reason"] == "无历史记录"


# ── 判定书 ─────────────────────────────────────────────────────


def test_judge_all_pass_approves(ev):
    """三门槛全过 → 转正立项。"""
    res = ev.judge({"pass": True, "ratio": 0.92}, {"pass": True, "ratio": 0.826}, {"pass": True, "ratio": 0.029})
    assert res["approved"] is True
    assert res["verdict"] == "转正立项"
    assert res["failed"] == []
    assert res["metrics"] == {"A": True, "B": True, "C": True}


@pytest.mark.parametrize("which", ["A", "B", "C"])
def test_judge_any_fail_rejects(ev, which):
    """任一门槛不过 → 已评估未采纳，且失败项指名到门槛。"""
    parts = {
        "A": {"pass": True, "ratio": 0.92},
        "B": {"pass": True, "ratio": 0.826},
        "C": {"pass": True, "ratio": 0.029},
    }
    parts[which] = {"pass": False, "ratio": 0.0}
    res = ev.judge(parts["A"], parts["B"], parts["C"])
    assert res["approved"] is False
    assert res["verdict"] == "已评估未采纳"
    assert res["failed"] == [f"{which}未过"]
    assert res["metrics"][which] is False


# ── 报告耗时基线 ───────────────────────────────────────────────


def test_read_report_baseline_median(tmp_path, ev):
    """近 10 行取 full、末 5 个取中位数；partial 行与坏行被排除。"""
    import json

    rows = [
        {"report_type": "partial", "total_seconds": 9999},
        {"report_type": "full", "total_seconds": 100, "phases": {"数据准备": 10, "LLM+新闻": 80}},
        {"report_type": "full", "total_seconds": 200, "phases": {"数据准备": 20, "LLM+新闻": 70}},
        {"report_type": "full", "total_seconds": 300, "phases": {"数据准备": 30, "LLM+新闻": 60}},
        {"report_type": "full", "total_seconds": 400, "phases": {"数据准备": 40, "LLM+新闻": 50}},
        {"report_type": "full", "total_seconds": 500, "phases": {"数据准备": 50, "LLM+新闻": 40}},
        {"report_type": "partial", "total_seconds": 9999},
    ]
    path = tmp_path / "perf_history.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    res = ev.read_report_baseline(path)
    assert res["available"] is True
    assert res["n"] == 5
    assert res["median_seconds"] == 300.0
    assert res["samples"] == [100.0, 200.0, 300.0, 400.0, 500.0]
    assert res["compute_only_median_seconds"] == 30.0


def test_read_report_baseline_no_full_rows(tmp_path, ev):
    """无 full 记录 → 不可用并给出原因。"""
    path = tmp_path / "perf_history.jsonl"
    path.write_text('{"report_type": "partial", "total_seconds": 50}\n', encoding="utf-8")
    res = ev.read_report_baseline(path)
    assert res["available"] is False
    assert "full" in res["reason"]


def test_read_report_baseline_missing_file(ev):
    """文件缺失 → 不可用（fail-closed，C 阶段据此判不过）。"""
    res = ev.read_report_baseline(Path("/nonexistent/perf_history.jsonl"))
    assert res["available"] is False
    assert "不可读" in res["reason"]


# ── 相关性口径（共享 Pearson 原语的上层规则） ──────────────────


def _ramp_family(n: int = 40) -> dict[str, float]:
    """二次递增族序列（Δ 线性增长，非退化）。"""
    return {f"d{i}": (i * i) * 0.001 for i in range(n)}


def test_evaluate_proportional_series_is_high_corr(ev):
    """因子与族成比例 → |ρ|=1 ≥ 0.5 → 不计低相关。"""
    family = {"market_temperature": _ramp_family()}
    factor = {d: v * 2 for d, v in family["market_temperature"].items()}
    res = ev.evaluate_factor_correlation(factor, family)
    assert res["max_abs_rho"] == pytest.approx(1.0)
    assert res["low_corr"] is False
    assert res["closest_family"] == "market_temperature"


def test_evaluate_independent_series_is_low_corr(ev):
    """振荡因子 vs 递增族 → |ρ| < 0.5 → 计入低相关。"""
    family = {"market_temperature": _ramp_family()}
    factor = {f"d{i}": (1 if i % 2 == 0 else -1) for i in range(40)}
    res = ev.evaluate_factor_correlation(factor, family)
    assert res["max_abs_rho"] is not None
    assert res["max_abs_rho"] < ev.CORR_LOW
    assert res["low_corr"] is True


def test_evaluate_step_signal_gets_structural_zero(ev):
    """季频/阶跃信号（Δ 非零占比 <5%）→ 结构性不相关口径 ρ=0 并标注。"""
    family = {"market_temperature": _ramp_family()}
    factor = {f"d{i}": 5.0 for i in range(40)}
    res = ev.evaluate_factor_correlation(factor, family)
    assert res["step_signal"] is True
    assert res["max_abs_rho"] == 0.0
    assert res["low_corr"] is True
    note = res["per_family"]["market_temperature"]["note"]
    assert "步进" in note and "结构性不相关" in note


def test_evaluate_empty_family_fails_closed(ev):
    """无任何信号族可评估 → fail-closed（max=None、不计低相关）。"""
    factor = {f"d{i}": float(i) for i in range(40)}
    res = ev.evaluate_factor_correlation(factor, {})
    assert res["max_abs_rho"] is None
    assert res["low_corr"] is False
    assert "fail-closed" in res["note"]


# ── 截面序列 / 因子值 / 字段注入探针 ────────────────────────────


def test_cross_sectional_series_mean_and_min_codes(ev):
    """逐日截面：≥3 只才入序列取等权均值，不足当日剔除。"""
    res = ev.cross_sectional_series(
        {
            "s1": [("2026-10-01", 1.0), ("2026-10-02", 3.0)],
            "s2": [("2026-10-01", 2.0), ("2026-10-02", 5.0)],
            "s3": [("2026-10-01", 3.0)],
        }
    )
    assert res == {"2026-10-01": 2.0}


def test_compute_factor_values_unknown_slug_returns_empty(ev):
    """未知 slug / 空 bars → 空序列（不抛异常）。"""
    assert ev.compute_factor_values("no_such_factor", [], []) == []
    assert ev.compute_factor_values("qlib_ma_cross", [], []) == []


def test_json_cap_log_normal(ev):
    """对数市值：1e9 → 900（log10×100 口径）。"""
    assert ev.json_cap_log(1e9) == 900.0
    assert ev.json_cap_log(1e6) == 600.0


def test_probe_fields_injected_probes_no_network(ev):
    """注入替身后 probe_fields 完全离线：结构、耗时键与池规模正确。"""
    bars = [{"date": f"2026-09-{i:02d}", "close": 10.0 + i} for i in range(1, 21)]
    probes = {
        ev.FIELD_BARS: lambda code: bars,
        ev.FIELD_INDEX: lambda *_: bars,
        ev.FIELD_VAL: lambda code: {"pe": 10.0, "pb": 1.2},
        ev.FIELD_FIN: lambda code: {"roe": 8.0},
    }
    pool = {"codes": ["600000", "600001"]}
    res = ev.probe_fields(ev.build_catalog(), pool, probes=probes)

    assert res["pool_size"] == 2
    assert set(res["timings"]) == set(ev.FIELD_TYPES)
    fr = res["field_results"]
    assert fr["index_ok"] is True
    assert set(fr["bars_by_code"]) == set(pool["codes"])
    assert set(fr["per_code"][ev.FIELD_VAL]) == set(pool["codes"])
    assert set(fr["per_code"][ev.FIELD_FIN]) == set(pool["codes"])
    assert len(fr["index_bars"]) == len(bars)
