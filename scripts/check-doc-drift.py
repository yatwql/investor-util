#!/usr/bin/env python3
"""文档与实现一致性检查（doc-code drift check）—— 文档里写死的「事实」与代码/配置文件/文件系统逐条对账。

背景：文档中的**计数、清单、默认值、目录树、统计表**是易漂移的「事实断言」——
代码里加了开关/章节/文件，文档数字不动就静默失真。本脚本把这类断言与权威源绑定，
逐条比对，使漂移在提交前暴露（与 check-doc-traces 的「历史痕迹」检查互补：
那边管「不该写的内容」，这边管「写了但与实现不符的内容」）。

十四项检查（权威源 → 受检文档）：
  1.  报告章节表        core/registry.py `_REPORT_SECTION_DEFAULT`      → manuals/reports-instruction.md
  2.  章节数量断言      同上（`页签编号 1~N` / `默认顺序（N 项` / `返回 result（N 项` / `N 个报告章节`）→ 全库文档
  3.  功能开关表        config/features.py `feature_switch_registry`    → manuals/how-to-config.md
  4.  开关分组计数断言  同上（`⚗实验 A / 常规 B / 报告章节与增强 C`、`实验组（A 项`、`共 N 项开关` 等）→ 全库文档
  5.  开关默认值断言    同上（`` `flag` `` 后紧随「默认开/关」）          → 全库文档
  6.  配置标量默认值表   config/_config_defaults.py `_DEFAULT_CONFIG`   → manuals/how-to-config.md
  7.  LLM 默认参数表     config/_llm_settings_defaults.py + 缓存 TTL 注册表 → managements/llm-technical.md
  8.  TUI 面板编号       `tui/handlers_config.py` 的派生规则（LLM 可见模块 + 三组顺序连续编号）→ manuals/how-to-use-tui-menu.md
  9.  目录树           文件系统实测（src/、scripts/、docs-stm/{managements,manuals,plan}）→ managements/folders.md
  10. 项目统计表        文件系统实测（文件数/行数）+ 可选 pytest 收集数 → managements/folders.md
  11. 测试覆盖计数表    `scripts/collect-test-coverage.py` 快照 → managements/test-coverage.md（仅 `--with-test-count`）
  12. 归档索引完整性    changelog / plan / review-findings 的「归档」索引 ↔ 归档目录 `archived_*` 文件（双向）
  13. 管理文档分区纪律  未完成/已解决/已归档三分区互斥；现行 changelog 只允许一个 `-dev` 段头
  14. Extended Thinking 支持矩阵  手册对比表/「仅」式枚举/默认开思考提示 ↔ `llm/api_base` 前缀名单

按设计豁免的历史记录文档：`changelog.md` / `review-findings.md`（会如实引用旧数字作为变更记录）
与 `docs-stm/archive/**`（版本快照）不参与第 2/4/5 项扫描。

用法：
  python scripts/check-doc-drift.py                  # 十四项全查
  python scripts/check-doc-drift.py -v               # 详细输出（打印解析明细）
  python scripts/check-doc-drift.py --ci             # CI 模式：仅输出 文件:描述，退出码 2
  python scripts/check-doc-drift.py --with-test-count # 附带 pytest 收集，核对「测试用例数」与 test-coverage.md 计数表

退出码：
  0 — 全部一致
  2 — 发现不一致（逐条列出 文件:描述，可直接按提示改）

本文件为入口：仅保留 CLI 与编排（`run_checks` / `main`），检查实现分置于
`_doc_drift/` 包内四个子模块（共享设施 / 文档格式族 / 目录树与统计 / 台账族），
并在下方**原面 re-export** 全部检查函数与常量——调用方（含按路径加载本模块的单测）
零改动。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, rel, report  # noqa: E402,F401  # rel：单测直接访问 drift.rel

if str(REPO_ROOT) not in sys.path:  # 允许任意 cwd 下运行
    sys.path.insert(0, str(REPO_ROOT))

# 原面 re-export：实现层用到的外部符号（单测直接访问 drift.<name>，故在此保留绑定）
from src.python.config.features import feature_switch_registry, switches_in_group  # noqa: E402,F401
from src.python.core.registry import _REPORT_SECTION_DEFAULT, get_llm_module_names  # noqa: E402,F401
from src.python.tui.tui_menu import filter_menu_llm_modules  # noqa: E402,F401
from _doc_drift import (  # noqa: E402,F401  # 原面 re-export（实现见 _doc_drift/）
    _README,
    _MANUALS,
    _MANAGEMENTS,
    _FOLDERS_MD,
    _HOW_TO_CONFIG_MD,
    _REPORTS_MD,
    _TUI_MENU_MD,
    _LLM_TECHNICAL_MD,
    _TEST_COVERAGE_MD,
    _PLAN_MD,
    _CHANGELOG_MD,
    _REVIEW_FINDINGS_MD,
    _HISTORY_DOCS,
    _TREE_ROOTS,
    _GENERATED_DIRS,
    _GENERATED_SUFFIXES,
    _GENERATED_FILES,
    _GENERATED_PREFIXES,
    _is_generated,
    _scan_docs,
    _doc_section,
    _split_table_row,
    _first_number,
    _count,
    _values_equal,
    _collect_test_count,
    _collect_test_snapshot,
    _SECTION_COUNT_PATTERNS,
    parse_section_rows,
    check_section_table,
    check_section_counts,
    _SWITCH_TABLE_START,
    _SWITCH_ROW,
    extract_switch_table,
    check_switch_table,
    _group_counts,
    _TRIPLE_COUNT,
    _GROUPED_COUNT,
    _GROUP_NAME_TO_KIND,
    _REPORT_BLOCK_COUNT,
    _TOTAL_COUNT,
    _count_finding,
    check_switch_counts,
    _DEFAULT_CLAIM,
    check_switch_default_claims,
    _CONFIG_ROW,
    check_config_defaults,
    _LLM_ROW,
    _TTL_TABLE_ROW,
    _HOURS_ROW,
    _ttl_default,
    check_llm_defaults,
    _PANEL_SECTION_START,
    _PANEL_SECTION_END,
    _PANEL_ROW,
    _REPORT_RANGE,
    _REPORT_ITEM,
    check_panel_numbering,
    _TEST_COVERAGE_ROW,
    _COUNT_CELL,
    _COUNT_NAME_ALIAS,
    check_test_coverage_counts,
    _TREE_ENTRY,
    parse_tree_paths,
    _actual_files,
    check_dir_tree,
    _STATS_ROW,
    _stats_actual,
    check_project_stats,
    _RF_ID,
    _PLAN_ID,
    _CHANGELOG_HEADER,
    _RF_ROW_ID,
    _PLAN_HEADING_ID,
    _PLAN_DONE_HEADING_ID,
    _ARCHIVE_INDEX_PAIRS,
    check_archive_index,
    audit_management_partitions,
    check_management_partitions,
    _THINKING_MANUAL,
    _THINKING_FAMILY_PREFIXES,
    _THINKING_FAMILY_LABELS,
    _thinking_families,
    check_thinking_support_matrix,
)


def run_checks(with_test_count: bool = False) -> list[str]:
    """跑全部检查，返回不一致描述列表（空 = 全部一致）。"""
    docs = _scan_docs()
    snapshot = _collect_test_snapshot() if with_test_count else {}
    findings: list[str] = []
    findings += check_section_table(docs[_REPORTS_MD])
    findings += check_section_counts(docs)
    findings += check_switch_table(docs[_HOW_TO_CONFIG_MD])
    findings += check_switch_counts(docs)
    findings += check_switch_default_claims(docs)
    findings += check_config_defaults(docs[_HOW_TO_CONFIG_MD])
    findings += check_llm_defaults(docs[_LLM_TECHNICAL_MD])
    findings += check_panel_numbering(docs[_TUI_MENU_MD])
    findings += check_dir_tree(docs[_FOLDERS_MD])
    findings += check_archive_index()
    findings += check_management_partitions()
    findings += check_thinking_support_matrix(docs.get(_THINKING_MANUAL))
    findings += check_project_stats(docs[_FOLDERS_MD], with_test_count=with_test_count, snapshot=snapshot)
    if with_test_count:
        findings += check_test_coverage_counts(docs[_TEST_COVERAGE_MD], snapshot)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验文档中的章节/开关/默认值/目录树/统计断言/归档索引/分区纪律/Thinking 支持矩阵与代码、配置文件、文件系统的一致性",
    )
    add_common_args(parser)
    parser.add_argument(
        "--with-test-count",
        action="store_true",
        help="附带 pytest 收集快照，核对 folders.md 「测试用例」行与 test-coverage.md 各计数表（较慢）",
    )
    args = parser.parse_args()

    findings = run_checks(with_test_count=args.with_test_count)

    if args.verbose:
        docs = _scan_docs()
        actual = _stats_actual()
        print(f"  受检文档 {len(docs)} 份（历史记录类 changelog/review-findings 不参与计数扫描）")
        print(
            f"  报告章节 {len(_REPORT_SECTION_DEFAULT)} 章 / 功能开关 {len(feature_switch_registry)} 项 {_group_counts()}"
        )
        print(f"  开关表解析 {len(extract_switch_table(docs[_HOW_TO_CONFIG_MD]))} 行")
        print(f"  目录树解析 {len(parse_tree_paths(docs[_FOLDERS_MD]))} 条 / 实测文件 {len(_actual_files())} 个")
        for label, (files, lines) in actual.items():
            print(f"    {label}: {files} 文件 / {lines} 行")

    sys.exit(
        report(
            findings,
            "[OK] 文档与实现一致性校验通过（章节/开关/默认值/面板编号/目录树/统计表/归档索引/分区纪律/Thinking 支持矩阵均与代码一致）",
            ci=args.ci,
            fail_message="[!] 发现 {n} 处文档与实现不一致，须修正后提交",
        )
    )


if __name__ == "__main__":
    main()
