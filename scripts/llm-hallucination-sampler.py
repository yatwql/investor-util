#!/usr/bin/env python3
"""LLM 幻觉率采样测试 — 对标准持仓数据调用 LLM 生成报告，统计幻觉率。

用法:
  python scripts/llm-hallucination-sampler.py
  python scripts/llm-hallucination-sampler.py --module expert_review --dry-run
  python scripts/llm-hallucination-sampler.py --dataset 1,2,3 --force

选项:
  --module MODULE     LLM 模块名: expert_review（默认）, global_macro, health_check, penetration_deep
  --dataset N[,N...]  仅测试指定数据集（序号从 1 开始，默认全部）
  --dry-run           不调用 LLM，只构建 prompt 并输出到 tmp 目录
  --force             跳过缓存，强制重新生成 LLM 输出
  --output FILE       报告输出路径（默认 docs-stm/tmp/hallucination-report.md）

每次 prompt 重大修改后应重新运行此脚本，确保幻觉率 < 5%。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

# ── 项目根目录 ──────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("hallucination_sampler")

# ── 晚导入（sys.path 就绪后） ───────────────────────────────────
_HTTP_CLIENT: Any = None


def _get_http_client():
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        from src.python.core.http_client import make_http_client

        _HTTP_CLIENT = make_http_client(timeout=120.0, http2=False)
    return _HTTP_CLIENT


# ── 基金代码白名单（用于分类） ──────────────────────────────────
_FUND_CODES: set[str] = {"005827", "006113", "110011", "008286", "007207"}


def _compute_categories(holdings_details: list[dict]) -> dict[str, int]:
    """从持仓明细计算品种分类计数。"""
    cat_counts: dict[str, int] = {}
    for h in holdings_details:
        code = h.get("code", "")
        if code in _FUND_CODES:
            cat = "基金"
        elif code.startswith(("51", "15", "16")):
            cat = "ETF"
        elif code.startswith(("00", "30", "60", "68", "002", "003")):
            cat = "股票"
        else:
            cat = "其他"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    return cat_counts


def _compute_portfolio_values(holdings_details: list[dict]) -> dict[str, float]:
    """计算组合核心数值，委托给 fact_checker 保持一致。"""
    from src.python.llm.fact_checker import _calc_portfolio_values

    vals = _calc_portfolio_values(holdings_details)
    vals["total_today_profit"] = 0.0
    return vals


def _load_datasets(dataset_filter: list[int] | None = None) -> list[dict]:
    """加载数据集，可选按序号过滤。"""
    from src.test.data.hallucination.datasets import HALLUCINATION_DATASETS

    datasets = list(HALLUCINATION_DATASETS)
    if dataset_filter:
        datasets = [ds for i, ds in enumerate(datasets, 1) if i in dataset_filter]
    return datasets


# ── LLM 模块调用映射 ─────────────────────────────────────────────

_MODULE_FNS: dict[str, str] = {
    "expert_review": "generate_expert_review",
    "global_macro": "generate_global_macro",
    "health_check": "generate_health_check",
    "penetration_deep": "generate_penetration_deep_analysis",
}


def _call_llm_module(
    module_name: str,
    holdings_details: list[dict],
    values: dict[str, float],
    categories: dict[str, int],
    dry_run: bool = False,
    force: bool = False,
) -> tuple[str | None, dict | None]:
    """调用指定 LLM 模块生成分析文本。

    Args:
        module_name: LLM 模块名。
        holdings_details: 持仓明细。
        values: 组合核心数值（total_mv 等）。
        categories: 品种分类计数。
        dry_run: 仅构建 prompt 不调用 LLM。
        force: 跳过缓存强制重新生成。

    Returns:
        (llm_output_text, usage_or_prompt_dict)
        — 正常调用返回 (content, usage)；dry_run 返回 (prompt_str, {"dry_run": True})
    """
    from src.python.config import get_llm_config
    from src.python.llm.generators import (
        generate_expert_review,
        generate_global_macro,
        generate_health_check,
        generate_penetration_deep_analysis,
    )

    fn_name = _MODULE_FNS.get(module_name)
    if not fn_name:
        logger.error("未知模块: %s，可选: %s", module_name, ", ".join(_MODULE_FNS))
        return None, None

    llm_config = get_llm_config()
    if not llm_config and not dry_run:
        logger.warning("LLM 配置不存在，可使用 --dry-run 仅验证 prompt 构建")
        return None, None

    total_mv = values["total_mv"]
    total_cost = values["total_cost"]
    total_profit = values["total_profit"]
    total_today_profit = values["total_today_profit"]
    holdings_count = len(holdings_details)

    if dry_run:
        # 仅构建 prompt 不调用 API
        if module_name == "expert_review":
            from src.python.llm.prompts import _build_expert_review_prompt, _SYSTEM_EXPERT_REVIEW

            prompt = _build_expert_review_prompt(
                total_mv,
                total_cost,
                total_profit,
                total_today_profit,
                holdings_count,
                categories,
                holdings_details=holdings_details,
            )
            return f"[SYSTEM]\n{_SYSTEM_EXPERT_REVIEW}\n\n[USER]\n{prompt}", {"dry_run": True}
        elif module_name == "global_macro":
            from src.python.llm.prompts import _build_global_macro_prompt, _SYSTEM_GLOBAL_MACRO

            prompt = _build_global_macro_prompt(
                {},
                {},
                total_mv,
                total_profit,
                categories,
            )
            return f"[SYSTEM]\n{_SYSTEM_GLOBAL_MACRO}\n\n[USER]\n{prompt}", {"dry_run": True}
        elif module_name == "health_check":
            from src.python.llm.prompts import _build_health_check_prompt, _SYSTEM_HEALTH_CHECK

            prompt = _build_health_check_prompt(
                total_mv,
                total_cost,
                total_profit,
                total_today_profit,
                holdings_count,
                categories,
                holdings_details=holdings_details,
            )
            return f"[SYSTEM]\n{_SYSTEM_HEALTH_CHECK}\n\n[USER]\n{prompt}", {"dry_run": True}
        elif module_name == "penetration_deep":
            from src.python.llm.prompts import _build_penetration_deep_prompt, _SYSTEM_PENETRATION_DEEP

            prompt = _build_penetration_deep_prompt(
                total_mv,
                total_cost,
                total_profit,
                holdings_count,
                categories,
                holdings_details=holdings_details,
            )
            return f"[SYSTEM]\n{_SYSTEM_PENETRATION_DEEP}\n\n[USER]\n{prompt}", {"dry_run": True}
        return None, None

    # ── 真实 LLM 调用 ──
    http_client = _get_http_client()
    try:
        if module_name == "expert_review":
            content, cached = generate_expert_review(
                total_mv,
                total_cost,
                total_profit,
                total_today_profit,
                holdings_count,
                categories,
                holdings_details=holdings_details,
                force=force,
                http_client=http_client,
                llm_config=llm_config,
            )
        elif module_name == "global_macro":
            a_indices = {}
            us_indices = {}
            content, cached = generate_global_macro(
                a_indices,
                us_indices,
                total_mv,
                total_profit,
                categories,
                force=force,
                http_client=http_client,
                llm_config=llm_config,
            )
        elif module_name == "health_check":
            content, cached = generate_health_check(
                total_mv,
                total_cost,
                total_profit,
                total_today_profit,
                holdings_count,
                categories,
                holdings_details=holdings_details,
                force=force,
                http_client=http_client,
                llm_config=llm_config,
            )
        elif module_name == "penetration_deep":
            content, cached = generate_penetration_deep_analysis(
                total_mv,
                total_cost,
                total_profit,
                total_today_profit,
                holdings_count,
                categories,
                holdings_details=holdings_details,
                force=force,
                http_client=http_client,
                llm_config=llm_config,
            )
        else:
            content = None
        return content, {"cached": cached if content else False}
    except Exception as e:
        logger.error("模块 %s 调用失败: %s", module_name, e)
        return None, {"error": str(e)}


# ── 事实校验（使用独立检查器，精准分类） ────────────────────────


def _run_fact_check(
    llm_output: str,
    holdings_details: list[dict],
    module_label: str,
    extra_valid_codes: set[str] | None = None,
    is_penetration_module: bool = False,
) -> dict[str, Any]:
    """对 LLM 输出执行全量事实校验（使用独立检查器）。

    直接调用 fact_checker 的三个独立检查器，精确统计。

    Returns:
        {"issues": {...}, "total_checks": int, "hallucination_rate": float, ...}
    """
    from src.python.llm.fact_checker import (
        _strip_html as _fc_strip_html,
        check_numerical_consistency,
        check_ranking_correctness,
        check_symbol_existence,
    )

    text = _fc_strip_html(llm_output)

    # 检查器 1：数值一致性
    num_issues, num_checked, num_passed = check_numerical_consistency(text, holdings_details)

    # 检查器 2：品种存在性（建议语境已在内部处理）
    sym_issues, sym_checked, sym_passed, sym_suggestions = check_symbol_existence(
        text,
        holdings_details,
        extra_valid_codes,
    )

    # 检查器 3：排名正确性
    rank_issues, rank_checked, rank_passed = check_ranking_correctness(
        text,
        holdings_details,
        is_penetration_module,
    )

    total_checks = num_checked + sym_checked + rank_checked
    total_issues = len(num_issues) + len(sym_issues) + len(rank_issues)
    hallucination_rate = total_issues / total_checks if total_checks > 0 else 0.0

    return {
        "issues": {
            "numerical": num_issues,
            "symbol": sym_issues,
            "rank": rank_issues,
            "symbol_suggestion": sym_suggestions,
        },
        "total_checks": total_checks,
        "num_checked": num_checked,
        "sym_checked": sym_checked,
        "rank_checked": rank_checked,
        "sym_suggestion_count": len(sym_suggestions),
        "hallucination_rate": hallucination_rate,
    }


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
    lines.append(f"# LLM 幻觉率采样报告")
    lines.append(f"")
    lines.append(f"- **生成时间**: {now_bj}")
    lines.append(f"- **LLM 模块**: {module_name}")
    lines.append(f"- **Dry-Run**: {'是（未调用 LLM API）' if dry_run else '否'}")
    lines.append(f"- **数据集数**: {len(all_results)}")
    lines.append(f"")

    # ── 汇总表 ──
    lines.append(f"## 汇总")
    lines.append(f"")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 总事实校验项 | {total_checks} |")
    lines.append(f"| ❌ 疑似幻觉 — 数值一致性 | {total_issues_numerical} |")
    lines.append(f"| ❌ 疑似幻觉 — 品种存在性（声称持有） | {total_issues_symbol} |")
    lines.append(f"| ❌ 疑似幻觉 — 排名正确性 | {total_issues_rank} |")
    lines.append(f"| ℹ️ 建议提及（非幻觉，不计入率） | {total_suggestions} |")
    lines.append(f"| **幻觉率** | **{overall_rate:.2%}** |")
    lines.append(f"| 目标 | < 5% |")
    lines.append(f"| **达标** | **{'✅ 是' if target_met else '❌ 否'}** |")
    lines.append(f"")

    lines.append("> **说明**：")
    lines.append('> - 品种存在性告警分为"声称持有"（幻觉）和"建议提及"（非幻觉），')
    lines.append(">   建议提及不计入幻觉率（如 LLM 推荐买入的品种不在持仓中）。")
    lines.append("> - 数值一致性告警可能包含误报——仓位占比（如 52.4%）、")
    lines.append(">   情景假设百分比等非收益率数值会被标记为偏差。")
    lines.append(">   建议人工复核后确认实际幻觉率。")
    lines.append(f"")

    # ── 各数据集详情 ──
    lines.append(f"## 各数据集详情")
    lines.append(f"")

    for i, r in enumerate(all_results, 1):
        ds = r["dataset"]
        fc = r["fact_check"]
        name = ds["name"]
        ds_rate = fc["hallucination_rate"]
        sym_sug_count = fc.get("sym_suggestion_count", 0)

        lines.append(f"### 数据集 {i}: {name}")
        lines.append(f"")
        lines.append(f"- **描述**: {ds.get('description', '')}")
        lines.append(f"- **品种数**: {len(ds['holdings_details'])}")
        lines.append(f"- **LLM 输出**: {'%d 字符' % len(r['llm_output']) if r.get('llm_output') else '空'}")
        lines.append(f"- **校验项**: {fc['total_checks']} | **幻觉率**: {ds_rate:.2%}")
        if sym_sug_count:
            lines.append(f"- **建议提及**（不计入幻觉率）: {sym_sug_count} 项")
        lines.append(f"")

        # 汇总每个检查器
        sym_issues_count = len(fc["issues"]["symbol"])
        sym_sug_local = len(fc["issues"].get("symbol_suggestion", []))
        lines.append(f"#### 检查器明细")
        lines.append(f"")
        lines.append(f"| 检查器 | 校验项 | 告警（幻觉） | 建议提及 |")
        lines.append(f"|--------|:------:|:-----------:|:--------:|")
        lines.append(f"| 数值一致性 | {fc.get('num_checked', 0)} | {len(fc['issues']['numerical'])} | -- |")
        lines.append(f"| 品种存在性 | {fc.get('sym_checked', 0)} | {sym_issues_count} | {sym_sug_local} |")
        lines.append(f"| 排名正确性 | {fc.get('rank_checked', 0)} | {len(fc['issues']['rank'])} | -- |")
        lines.append(f"")

        # 告警详情
        has_any_issue = any(fc["issues"][k] for k in ("numerical", "symbol", "rank"))
        has_suggestion = bool(sym_sug_local)
        if has_any_issue or has_suggestion:
            if has_any_issue:
                lines.append(f"#### 告警详情")
                lines.append(f"")
                for cat, cat_label in [
                    ("numerical", "数值一致性"),
                    ("symbol", "品种存在性（幻觉）"),
                    ("rank", "排名正确性"),
                ]:
                    if fc["issues"][cat]:
                        lines.append(f"**{cat_label}**：")
                        for issue in fc["issues"][cat]:
                            lines.append(f"- ❌ {issue}")
                        lines.append(f"")
            if has_suggestion:
                lines.append(f"**品种存在性（建议提及 — 不计入幻觉率）**：")
                for issue in fc["issues"].get("symbol_suggestion", []):
                    lines.append(f"- ℹ️ {issue}")
                lines.append(f"")
        else:
            lines.append(f"✅ 无告警 —— 全部通过")
            lines.append(f"")

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*由 `scripts/llm-hallucination-sampler.py` 自动生成*")

    return "\n".join(lines)


# ── 主流程 ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="LLM 幻觉率采样测试")
    parser.add_argument(
        "--module", default="expert_review", choices=list(_MODULE_FNS.keys()), help="LLM 模块（默认 expert_review）"
    )
    parser.add_argument("--dataset", type=str, default=None, help="仅测试指定数据集，逗号分隔（如 1,3,5）")
    parser.add_argument("--dry-run", action="store_true", help="不调用 LLM，只构建 prompt 验证结构")
    parser.add_argument("--force", action="store_true", help="跳过缓存强制重新生成")
    parser.add_argument(
        "--output", type=str, default=None, help="报告输出路径（默认 docs-stm/tmp/hallucination-report.md）"
    )
    args = parser.parse_args()

    module_name = args.module
    dry_run = args.dry_run
    force = args.force

    # 数据集过滤
    dataset_filter: list[int] | None = None
    if args.dataset:
        dataset_filter = [int(x.strip()) for x in args.dataset.split(",")]
        logger.info("过滤数据集: %s", dataset_filter)

    # 报告路径
    output_path = args.output
    if not output_path:
        output_path = os.path.join(_PROJECT_ROOT, "docs-stm", "tmp", "hallucination-report.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ── 1. 加载数据集 ──
    logger.info("=" * 60)
    logger.info("LLM 幻觉率采样测试")
    logger.info("模块: %s | Dry-Run: %s | Force: %s", module_name, dry_run, force)
    logger.info("=" * 60)

    datasets = _load_datasets(dataset_filter)
    logger.info("已加载 %d 个数据集", len(datasets))

    # ── Dry-Run：保存 prompt 到 tmp ──
    if dry_run:
        prompt_dir = os.path.join(_PROJECT_ROOT, "docs-stm", "tmp")
        os.makedirs(prompt_dir, exist_ok=True)
        prompt_path = os.path.join(prompt_dir, f"hallucination-prompts-{module_name}.md")
        prompt_lines: list[str] = [
            f"# LLM 幻觉率采样 — 构建的 Prompt（{module_name}）",
            f"",
            f"生成时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}",
            f"Dry-Run: 是",
            f"",
        ]

    # ── 2. 逐个数据集执行 ──
    all_results: list[dict] = []

    for idx, ds in enumerate(datasets, 1):
        name = ds["name"]
        holdings = ds["holdings_details"]
        values = _compute_portfolio_values(holdings)
        categories = _compute_categories(holdings)

        logger.info("[%d/%d] %s (%d 品种, 市值 %.0f)", idx, len(datasets), name, len(holdings), values["total_mv"])

        # ── 2a. 调用 LLM ──
        start_ts = time.time()
        llm_output, usage = _call_llm_module(
            module_name,
            holdings,
            values,
            categories,
            dry_run=dry_run,
            force=force,
        )
        elapsed = time.time() - start_ts

        if dry_run and llm_output:
            prompt_lines.append(f"---")
            prompt_lines.append(f"## 数据集 {idx}: {name}")
            prompt_lines.append(f"")
            prompt_lines.append("```")
            # 截取前 2000 字符
            if len(llm_output) > 2000:
                prompt_lines.append(llm_output[:2000] + "\n...（截断）")
            else:
                prompt_lines.append(llm_output)
            prompt_lines.append("```")
            prompt_lines.append(f"")

        if not llm_output and not dry_run:
            logger.warning("  [%d/%d] %s → LLM 返回空（跳过事实校验）", idx, len(datasets), name)
            all_results.append(
                {
                    "dataset": ds,
                    "llm_output": None,
                    "usage": usage,
                    "fact_check": {
                        "issues": {"numerical": [], "symbol": [], "rank": [], "symbol_suggestion": []},
                        "total_checks": 0,
                        "num_checked": 0,
                        "sym_checked": 0,
                        "rank_checked": 0,
                        "sym_suggestion_count": 0,
                        "hallucination_rate": 0.0,
                    },
                    "elapsed": elapsed,
                }
            )
            continue

        # ── 2b. 事实校验 ──
        module_label = {
            "expert_review": "智囊团深度复盘",
            "global_macro": "全球政经局势",
            "health_check": "持仓体检报告",
            "penetration_deep": "穿透深度分析",
        }.get(module_name, module_name)

        # 提取穿透代码（如适用）
        extra_codes: set[str] | None = None

        fact_check_result = _run_fact_check(
            llm_output or "",
            holdings,
            module_label=module_label,
            extra_valid_codes=extra_codes,
        )

        rate_str = f"{fact_check_result['hallucination_rate']:.2%}"
        logger.info(
            "  [%d/%d] %s → 校验 %d 项 / 告警 %d / 幻觉率 %s (%.1fs)",
            idx,
            len(datasets),
            name,
            fact_check_result["total_checks"],
            sum(len(v) for v in fact_check_result["issues"].values()),
            rate_str,
            elapsed,
        )

        all_results.append(
            {
                "dataset": ds,
                "llm_output": llm_output,
                "usage": usage,
                "fact_check": fact_check_result,
                "elapsed": elapsed,
            }
        )

    # ── Dry-Run 保存 Prompt ──
    if dry_run:
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(prompt_lines))
        logger.info("Prompt 已保存到: %s", prompt_path)

    # ── 3. 生成报告 ──
    report = _generate_report(module_name, all_results, dry_run=dry_run)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("报告已生成: %s", output_path)

    # ── 汇总输出 ──
    total_checks = sum(r["fact_check"]["total_checks"] for r in all_results)
    total_issues = sum(
        len(r["fact_check"]["issues"].get("numerical", []))
        + len(r["fact_check"]["issues"].get("symbol", []))
        + len(r["fact_check"]["issues"].get("rank", []))
        for r in all_results
    )
    overall_rate = total_issues / total_checks if total_checks > 0 else 0.0
    passed_datasets = sum(1 for r in all_results if r["fact_check"]["hallucination_rate"] < 0.05)
    logger.info("")
    logger.info("=" * 60)
    logger.info("采样完成！")
    logger.info(
        "总校验项: %d | 告警: %d | 幻觉率: %.2f%% | 达标数据集: %d/%d",
        total_checks,
        total_issues,
        overall_rate * 100,
        passed_datasets,
        len(all_results),
    )
    logger.info("目标 < 5%%: %s", "✅ 达标" if overall_rate < 0.05 else "❌ 未达标")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
