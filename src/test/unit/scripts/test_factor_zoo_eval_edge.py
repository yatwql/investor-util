"""factor_zoo_eval 评测脚本边缘场景（空输入/退化数据/极端值），全部离线。"""

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
    pytest.mark.edge,
]


def test_metric_a_empty_pool_results_no_crash(ev):
    """field_results 只有空 codes（无 bars/估值键）→ 不崩，全因子不可算、判不过。"""
    res = ev.metric_a(ev.build_catalog(), {"codes": []})
    assert res["n_computable"] == 0
    assert res["ratio"] == 0.0
    assert res["pass"] is False
    assert all(not info["ok"] for info in res["per_factor"].values())


def test_metric_a_missing_probe_keys_no_crash(ev):
    """探测产物缺 index/bars/per_code 各键 → 覆盖判定按不可得处理不崩。"""
    res = ev.metric_a(ev.build_catalog(), {"codes": ["600000"]})
    assert res["pass"] is False
    assert all(info["missing"] for info in res["per_factor"].values())


def test_metric_b_empty_computable_fails_closed(ev):
    """分母为 0：占比 0、样本不足、判不过（无除零）。"""
    res = ev.metric_b([{"slug": "f0", "label": "F0", "family": "t"}], [], {})
    assert res["denom"] == 0
    assert res["ratio"] == 0.0
    assert res["sample_ok"] is False
    assert res["pass"] is False


def test_evaluate_all_families_too_small_fails_closed(ev):
    """所有族样本对数 < MIN_PAIRS → 族被剔除 → 不计低相关（fail-closed）。"""
    family = {"market_temperature": {f"d{i}": float(i) for i in range(10)}}
    factor = {f"d{i}": float(i) * 0.5 for i in range(10)}
    res = ev.evaluate_factor_correlation(factor, family)
    assert res["max_abs_rho"] is None
    assert res["low_corr"] is False


def test_evaluate_empty_factor_series_fails_closed(ev):
    """因子序列为空 → 无可对齐数据 → fail-closed 不计低相关。"""
    family = {"market_temperature": {f"d{i}": float(i * i) for i in range(40)}}
    res = ev.evaluate_factor_correlation({}, family)
    assert res["max_abs_rho"] is None
    assert res["low_corr"] is False


def test_judge_all_missing_metrics_fails_closed(ev):
    """三门槛结果全缺（None）→ 已评估未采纳，绝不误批。"""
    res = ev.judge(None, None, None)
    assert res["approved"] is False
    assert res["verdict"] == "已评估未采纳"


def test_read_report_baseline_malformed_lines(tmp_path, ev):
    """坏 JSON 行逐行跳过；全为坏行 → 不可用。"""
    path = tmp_path / "perf_history.jsonl"
    path.write_text('not-json\n{"report_type": "full"}\n{{{\n', encoding="utf-8")
    res = ev.read_report_baseline(path)
    assert res["available"] is False


def test_cross_sectional_series_empty_returns_empty(ev):
    """空输入 → 空序列（不崩、不回填）。"""
    assert ev.cross_sectional_series({}) == {}


def test_json_cap_log_invalid_and_nonfinite(ev):
    """极端/非法市值一律 None：非正、None、非数、±inf、nan。"""
    for bad in (0, -1, None, "abc", float("inf"), float("-inf"), float("nan")):
        assert ev.json_cap_log(bad) is None, bad


def test_stage_verdict_missing_reports_exits(ev, tmp_path):
    """判定阶段缺前置报告 → SystemExit 提示先跑前置阶段（不写半成品）。"""
    with pytest.raises(SystemExit):
        ev.stage_verdict(tmp_path)


def test_metric_c_zero_baseline_denominator_fails_closed(ev):
    """基线中位数为 0（分母退化）→ 按不通过计，不产生 inf 比值。"""
    res = ev.metric_c(1.0, 0.1, {"available": True, "median_seconds": 0, "n": 1})
    assert res["pass"] is False
