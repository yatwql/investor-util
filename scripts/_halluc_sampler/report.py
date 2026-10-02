"""幻觉率评估报告生成（Markdown 汇总）。"""

from __future__ import annotations


import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("hallucination_sampler")

# ── 报告生成 ─────────────────────────────────────────────────────


def _generate_report(
    module_name: str,
    all_results: list[dict],
    dry_run: bool = False,
) -> str:
    """生成幻觉率采样报告 Markdown。"""
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    # 汇总统计（建议提及不计入幻觉率）
    total_checks = sum(r["fact_check"]["total_checks"] for r in all_results)
    total_suggestions = sum(r["fact_check"].get("sym_suggestion_count", 0) for r in all_results)
    total_issues_numerical = sum(len(r["fact_check"]["issues"]["numerical"]) for r in all_results)
    total_issues_symbol = sum(len(r["fact_check"]["issues"]["symbol"]) for r in all_results)
    total_issues_rank = sum(len(r["fact_check"]["issues"]["rank"]) for r in all_results)
    total_issues = total_issues_numerical + total_issues_symbol + total_issues_rank
    overall_rate = total_issues / total_checks if total_checks > 0 else 0.0
    target_met = overall_rate < 0.05

    lines: list[str] = []
    lines.append("# LLM 幻觉率采样报告")
    lines.append("")
    lines.append(f"- **生成时间**: {now_bj}")
    lines.append(f"- **LLM 模块**: {module_name}")
    lines.append(f"- **Dry-Run**: {'是（未调用 LLM API）' if dry_run else '否'}")
    lines.append(f"- **数据集数**: {len(all_results)}")
    lines.append("")

    # ── 汇总表 ──
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|------|----|")
    lines.append(f"| 总事实校验项 | {total_checks} |")
    lines.append(f"| ❌ 疑似幻觉 — 数值一致性 | {total_issues_numerical} |")
    lines.append(f"| ❌ 疑似幻觉 — 品种存在性（声称持有） | {total_issues_symbol} |")
    lines.append(f"| ❌ 疑似幻觉 — 排名正确性 | {total_issues_rank} |")
    lines.append(f"| ℹ️ 建议提及（非幻觉，不计入率） | {total_suggestions} |")
    lines.append(f"| **幻觉率** | **{overall_rate:.2%}** |")
    lines.append("| 目标 | < 5% |")
    lines.append(f"| **达标** | **{'✅ 是' if target_met else '❌ 否'}** |")
    lines.append("")

    lines.append("> **说明**：")
    lines.append('> - 品种存在性告警分为"声称持有"（幻觉）和"建议提及"（非幻觉），')
    lines.append(">   建议提及不计入幻觉率（如 LLM 推荐买入的品种不在持仓中）。")
    lines.append("> - 数值一致性告警可能包含误报——仓位占比（如 52.4%）、")
    lines.append(">   情景假设百分比等非收益率数值会被标记为偏差。")
    lines.append(">   建议人工复核后确认实际幻觉率。")
    lines.append("")

    # ── 各数据集详情 ──
    lines.append("## 各数据集详情")
    lines.append("")

    for i, r in enumerate(all_results, 1):
        ds = r["dataset"]
        fc = r["fact_check"]
        name = ds["name"]
        ds_rate = fc["hallucination_rate"]
        sym_sug_count = fc.get("sym_suggestion_count", 0)

        lines.append(f"### 数据集 {i}: {name}")
        lines.append("")
        lines.append(f"- **描述**: {ds.get('description', '')}")
        lines.append(f"- **品种数**: {len(ds['holdings_details'])}")
        lines.append(f"- **LLM 输出**: {'%d 字符' % len(r['llm_output']) if r.get('llm_output') else '空'}")
        lines.append(f"- **校验项**: {fc['total_checks']} | **幻觉率**: {ds_rate:.2%}")
        if sym_sug_count:
            lines.append(f"- **建议提及**（不计入幻觉率）: {sym_sug_count} 项")
        lines.append("")

        # 汇总每个检查器
        sym_issues_count = len(fc["issues"]["symbol"])
        sym_sug_local = len(fc["issues"].get("symbol_suggestion", []))
        lines.append("#### 检查器明细")
        lines.append("")
        lines.append("| 检查器 | 校验项 | 告警（幻觉） | 建议提及 |")
        lines.append("|--------|:------:|:-----------:|:--------:|")
        lines.append(f"| 数值一致性 | {fc.get('num_checked', 0)} | {len(fc['issues']['numerical'])} | -- |")
        lines.append(f"| 品种存在性 | {fc.get('sym_checked', 0)} | {sym_issues_count} | {sym_sug_local} |")
        lines.append(f"| 排名正确性 | {fc.get('rank_checked', 0)} | {len(fc['issues']['rank'])} | -- |")
        lines.append("")

        # 告警详情
        has_any_issue = any(fc["issues"][k] for k in ("numerical", "symbol", "rank"))
        has_suggestion = bool(sym_sug_local)
        if has_any_issue or has_suggestion:
            if has_any_issue:
                lines.append("#### 告警详情")
                lines.append("")
                for cat, cat_label in [
                    ("numerical", "数值一致性"),
                    ("symbol", "品种存在性（幻觉）"),
                    ("rank", "排名正确性"),
                ]:
                    if fc["issues"][cat]:
                        lines.append(f"**{cat_label}**：")
                        for issue in fc["issues"][cat]:
                            lines.append(f"- ❌ {issue}")
                        lines.append("")
            if has_suggestion:
                lines.append("**品种存在性（建议提及 — 不计入幻觉率）**：")
                for issue in fc["issues"].get("symbol_suggestion", []):
                    lines.append(f"- ℹ️ {issue}")
                lines.append("")
        else:
            lines.append("✅ 无告警 —— 全部通过")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*由 `scripts/llm-hallucination-sampler.py` 自动生成*")

    return "\n".join(lines)
