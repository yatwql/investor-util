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
  --output FILE       报告输出路径（默认 docs/tmp/hallucination-report.md）

每次 prompt 重大修改后应重新运行此脚本，确保幻觉率 < 5%。

本文件为薄 CLI：实现均在 `scripts/_halluc_sampler/` 包（holdings /
llm_call / fact_check / report 四模块），main() 下方 re-export 保持原面。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 同目录共享包（_halluc_sampler）
from _halluc_sampler import (  # noqa: E402
    _MODULE_FNS,
    _call_llm_module,
    _compute_categories,
    _compute_portfolio_values,
    _generate_report,
    _load_datasets,
    _run_fact_check,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("hallucination_sampler")


def main():
    parser = argparse.ArgumentParser(description="LLM 幻觉率采样测试")
    parser.add_argument(
        "--module", default="expert_review", choices=list(_MODULE_FNS.keys()), help="LLM 模块（默认 expert_review）"
    )
    parser.add_argument("--dataset", type=str, default=None, help="仅测试指定数据集，逗号分隔（如 1,3,5）")
    parser.add_argument("--dry-run", action="store_true", help="不调用 LLM，只构建 prompt 验证结构")
    parser.add_argument("--force", action="store_true", help="跳过缓存强制重新生成")
    parser.add_argument(
        "--output", type=str, default=None, help="报告输出路径（默认 docs/tmp/hallucination-report.md）"
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
        output_path = os.path.join(_PROJECT_ROOT, "docs", "tmp", "hallucination-report.md")
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
        prompt_dir = os.path.join(_PROJECT_ROOT, "docs", "tmp")
        os.makedirs(prompt_dir, exist_ok=True)
        prompt_path = os.path.join(prompt_dir, f"hallucination-prompts-{module_name}.md")
        prompt_lines: list[str] = [
            f"# LLM 幻觉率采样 — 构建的 Prompt（{module_name}）",
            "",
            f"生成时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}",
            "Dry-Run: 是",
            "",
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
            prompt_lines.append("---")
            prompt_lines.append(f"## 数据集 {idx}: {name}")
            prompt_lines.append("")
            prompt_lines.append("```")
            # 截取前 2000 字符
            if len(llm_output) > 2000:
                prompt_lines.append(llm_output[:2000] + "\n...（截断）")
            else:
                prompt_lines.append(llm_output)
            prompt_lines.append("```")
            prompt_lines.append("")

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
