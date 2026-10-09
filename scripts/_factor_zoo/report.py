"""判定书生成（三项指标汇总 judge + 判定书 Markdown 渲染）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import time

from _factor_zoo.catalog import (
    B_MIN_DENOM,
    CORR_LOW,
    FAMILY_NAMES,
    MIN_PAIRS,
    STEP_NONZERO_FRACTION,
    THRESH_A,
    THRESH_B,
    THRESH_C,
    TYPE_COVERAGE,
)
from _factor_zoo.metrics import (
    judge,
)
from _factor_zoo.stages import (
    _read_json,
    _write_json,
)


def stage_verdict(out_dir: Path) -> dict[str, Any]:
    print("[..] 阶段5：判定汇总（阈值与口径预注册）")
    fields_report = _read_json(out_dir / "fields_report.json")
    signals_report = _read_json(out_dir / "signals_report.json")
    timing_report = _read_json(out_dir / "timing_report.json")
    if fields_report is None or signals_report is None or timing_report is None:
        raise SystemExit("[ERR] 指标报告不齐，请先运行 fields/signals/timing 阶段")
    verdict = judge(
        fields_report if not fields_report.get("skipped") else fields_report,
        signals_report if not signals_report.get("skipped") else signals_report,
        timing_report,
    )
    verdict["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(out_dir / "verdict.json", verdict)
    _write_verdict_md(out_dir, verdict, fields_report, signals_report, timing_report)
    status = "[OK]" if verdict["approved"] else "[!]"
    print(
        f"    {status} 判定：{verdict['verdict']}"
        f"（A={verdict['metrics']['A']} B={verdict['metrics']['B']} "
        f"C={verdict['metrics']['C']}；未过: {'、'.join(verdict['failed']) or '无'}）"
    )
    return verdict


def _write_verdict_md(
    out_dir: Path, verdict: dict[str, Any], a: dict[str, Any], b: dict[str, Any], c: dict[str, Any]
) -> None:
    """判定书（结论入库用；数值与分子分母逐项落盘可复算）。"""
    lines = [
        "# 因子动物园目录评测判定书",
        "",
        f"- 判定：**{verdict['verdict']}**（A={verdict['metrics']['A']} / "
        f"B={verdict['metrics']['B']} / C={verdict['metrics']['C']}）",
        f"- 判定时间：{verdict['captured_at']}",
        f"- 未过项：{'、'.join(verdict['failed']) or '无'}",
        "",
        "## 预注册口径（判定前固定，复算须逐字段一致）",
        "",
        f"- **A 字段可得率** = 可完整计算因子数 ÷ 25 ≥ {THRESH_A:.0%}；每字段类型需池内 "
        f"≥{TYPE_COVERAGE:.0%} 代码有效（bars 按因子 min_bars 条数）；恰等算过；A 不过提前终态。",
        f"- **B 信号增量** = 可计算因子中 max|ρ|<{CORR_LOW}（四个日频信号族，一阶差分 Pearson，"
        f"共享 correlation 原语）占比 ≥{THRESH_B:.0%}；分母 <{B_MIN_DENOM} 判样本不足不通过；"
        f"对齐样本 <{MIN_PAIRS} 或序列为空按不通过计（fail-closed）；步进/常量型季频信号"
        f"（Δ 非零占比 <{STEP_NONZERO_FRACTION:.0%}）按结构性不相关 ρ=0（增量体现在横截面排序）。",
        f"- **C 耗时预算** = 冷启动全量计算 ÷ 基线报告耗时 ≤{THRESH_C:.0%}；基线 = perf_history "
        "近 5 次 full 报告 total_seconds 中位数（真实整机实测，含 LLM）；非 LLM 计算阶段中位数作"
        "保守副口径一并记录；基线缺失按不通过计（可复评）。",
        "- 快照域信号族（再平衡超限）无日频序列，按设计降级不参与（B 的信号族数如实记录）。",
        "",
        "## 指标 A：字段可得率",
        "",
        f"- {a.get('n_computable', 0)}/{a.get('total', 0)} = {a.get('ratio', 0):.1%}"
        f"（阈值 {THRESH_A:.0%}）→ {'过' if a.get('pass') else '不过'}",
        f"- 股票池 {a.get('pool_size', '?')} 只；字段类型耗时(s)：{json.dumps(a.get('timings') or {}, ensure_ascii=False)}",
        "",
        "| slug | 可计算 | 缺失字段 | 逐字段覆盖 |",
        "|---|---|---|---|",
    ]
    for slug, info in (a.get("per_factor") or {}).items():
        coverage = " / ".join(f"{ftype}:{meta['coverage']:.0%}" for ftype, meta in info["fields"].items())
        lines.append(f"| `{slug}` | {'✅' if info['ok'] else '❌'} | {'+'.join(info['missing']) or '—'} | {coverage} |")
    lines += ["", "## 指标 B：信号增量", ""]
    if b.get("skipped"):
        lines.append("- 未评估（指标 A 未过 → 提前终态）")
    else:
        lines += [
            f"- {b.get('n_low_corr', 0)}/{b.get('denom', 0)} = {b.get('ratio', 0):.1%}"
            f"（阈值 {THRESH_B:.0%}）→ {'过' if b.get('pass') else '不过'}"
            f"（样本门槛 ≥{B_MIN_DENOM}: {'满足' if b.get('sample_ok') else '不满足'}）",
            f"- 信号族序列长度：{json.dumps(b.get('family_series_sizes') or {}, ensure_ascii=False)}",
            f"- 降级信号族：{json.dumps(b.get('family_degraded') or {}, ensure_ascii=False)}",
            "",
            "| slug | max\\|ρ\\| | 最近族 | 低相关 | 步进型 |",
            "|---|---:|---|:---:|:---:|",
        ]
        for slug, info in (b.get("per_factor") or {}).items():
            if not info:
                continue
            lines.append(
                f"| `{slug}` | {info.get('max_abs_rho')} | "
                f"{FAMILY_NAMES.get(info.get('closest_family') or '', '—')} | "
                f"{'✅' if info.get('low_corr') else '❌'} | "
                f"{'是' if info.get('step_signal') else '否'} |"
            )
    lines += [
        "",
        "## 指标 C：耗时预算",
        "",
        f"- 冷启动 {c.get('cold_seconds', '?')}s / 温态计算 {c.get('warm_seconds', '?')}s ÷ "
        f"基线 {c.get('baseline_seconds', '—')}s = {c.get('ratio', '—')}"
        f"（阈值 {THRESH_C:.0%}）→ {'过' if c.get('pass') else '不过'}",
        f"- 冷启动口径：{c.get('cold_basis', '—')}；估算请求数 {c.get('estimated_requests', '—')}"
        f"（字段在跑耗时 {c.get('warm_probe_total_seconds', '—')}s 为暖态，不作冷判据）",
        f"- 逐字段阶段耗时(s)：{json.dumps(c.get('timings_by_field') or {}, ensure_ascii=False)}",
        f"- 基线样本：{json.dumps((c.get('baseline') or {}).get('samples') or [], ensure_ascii=False)}"
        f"，非 LLM 计算阶段中位数 {((c.get('baseline') or {}).get('compute_only_median_seconds'))}s（副口径，仅记录）",
        "",
        "## 复算说明",
        "",
        "判定输入（目录/股票池/字段快照/信号报告/耗时报告）冻结于本目录；"
        "`factor_zoo_eval.py all` 重跑后 A/B 的分子分母与判定须逐字段一致；"
        "C 的秒数为实测快照（网络波动允许漂移），复算以判定结论一致为准。",
    ]
    (out_dir / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"    [OK] 判定书 → {out_dir / 'verdict.md'}")
