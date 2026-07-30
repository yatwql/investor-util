#!/usr/bin/env python3
"""性能历史趋势查看工具 — Layer 3：跨版本耗时趋势可视化。

读取 data/state/perf_history.jsonl，按版本和报告类型分组统计，
输出版本间性能趋势对比 Markdown 表格。

用法：
  python scripts/perf_view.py                          # 输出到 stdout
  python scripts/perf_view.py --save                   # 同时写入 docs-stm/tmp/perf_trend.md
  python scripts/perf_view.py --report-type full       # 仅查看 full 类型
  python scripts/perf_view.py --last 30                # 仅查看最近 30 条记录
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import logging

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")

from src.python.perf import load_history

_TMP_DIR = os.path.join(_PROJECT_ROOT, "docs-stm", "tmp")
_TREND_REPORT_PATH = os.path.join(_TMP_DIR, "perf_trend.md")


# ── 统计工具 ──


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _min_max(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    return min(values), max(values)


def _merge_phase_stats(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """合并所有记录中的阶段统计。

    Returns:
        {phase_name: {avg, min, max, count}}
    """
    phase_values: dict[str, list[float]] = defaultdict(list)
    for r in records:
        phases = r.get("phases", {})
        if isinstance(phases, dict):
            for name, sec in phases.items():
                phase_values[name].append(sec)
    result: dict[str, dict[str, float]] = {}
    for name, vals in sorted(phase_values.items()):
        result[name] = {
            "avg": round(_mean(vals), 2),
            "min": round(_min_max(vals)[0], 2),
            "max": round(_min_max(vals)[1], 2),
            "count": len(vals),
        }
    return result


def _group_records(
    records: list[dict[str, Any]],
    report_type: str | None,
    last_n: int | None,
) -> dict[str, list[dict[str, Any]]]:
    """按 version+report_type 分组。

    Returns:
        {group_key: [records]}
    """
    filtered = records
    if report_type:
        filtered = [r for r in filtered if r.get("report_type") == report_type]
    if last_n:
        filtered = filtered[-last_n:]

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in filtered:
        key = f"{r.get('version', '?')} / {r.get('report_type', '?')}"
        groups[key].append(r)
    # 按时间排序
    for g in groups:
        groups[g].sort(key=lambda x: x.get("timestamp", ""))
    return dict(sorted(groups.items()))


# ── 报告生成 ──


def build_trend_report(
    records: list[dict[str, Any]],
    report_type: str | None = None,
    last_n: int | None = None,
) -> str:
    """生成性能趋势 Markdown 报告字符串。"""
    groups = _group_records(records, report_type, last_n)

    lines: list[str] = [
        "# 报告生成性能趋势",
        "",
        f"**数据来源**：`data/state/perf_history.jsonl`",
        f"**总记录数**：{len(records)} 条",
        f"**分组数**：{len(groups)} 组",
        "",
    ]

    if not groups:
        lines.append("_暂无性能历史数据。_")
        lines.append("")
        return "\n".join(lines)

    # ── 按组输出详情 ──
    for group_key, group_records in groups.items():
        lines.append(f"## {group_key}")
        lines.append("")
        lines.append(f"运行次数：**{len(group_records)}**")
        lines.append("")

        totals = [r.get("total_seconds", 0) for r in group_records]
        lines.append(f"- 总耗时范围：{_min_max(totals)[0]:.1f}s ~ {_min_max(totals)[1]:.1f}s")
        lines.append(f"- 平均总耗时：**{_mean(totals):.1f}s**")
        lines.append("")

        # ── 各阶段平均耗时 ──
        phase_stats = _merge_phase_stats(group_records)
        if phase_stats:
            lines.append("| 阶段 | 平均耗时 | 最短 | 最长 | 次数 |")
            lines.append("|:-----|--------:|----:|----:|-----:|")
            for name, stat in phase_stats.items():
                lines.append(
                    f"| {name} | {stat['avg']:.2f}s | {stat['min']:.2f}s | {stat['max']:.2f}s | {stat['count']} |"
                )
            lines.append("")

        # ── 最近 5 次运行明细 ──
        lines.append("**最近 5 次运行明细：**")
        lines.append("")
        lines.append("| 时间 | 总耗时 | 持仓数 | 阶段数 | 错误 |")
        lines.append("|:-----|------:|------:|------:|-----:|")
        for r in group_records[-5:]:
            ts = r.get("timestamp", "?")[-16:]  # 简化为 HH:MM
            lines.append(
                f"| {ts} | {r.get('total_seconds', 0):.1f}s | "
                f"{r.get('holdings_count', '?')} | "
                f"{len(r.get('phases', {}))} | "
                f"{len(r.get('errors', []))} |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("")
    return "\n".join(lines)


# ── CLI ──


def main() -> int:
    parser = argparse.ArgumentParser(description="查看性能历史趋势")
    parser.add_argument("--report-type", choices=["basic", "both", "full"], help="仅查看指定报告类型")
    parser.add_argument("--last", type=int, default=None, help="仅查看最近 N 条记录")
    parser.add_argument("--save", action="store_true", help="同时写入 docs-stm/tmp/perf_trend.md")
    args = parser.parse_args()

    records = load_history()
    if not records:
        print("[!] 暂无性能历史数据（data/state/perf_history.jsonl 不存在或为空）")
        return 1

    report = build_trend_report(records, report_type=args.report_type, last_n=args.last)
    print(report)

    if args.save:
        os.makedirs(_TMP_DIR, exist_ok=True)
        with open(_TREND_REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[OK] 已写入: {_TREND_REPORT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
