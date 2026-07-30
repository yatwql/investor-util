# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.2-dev] - 2026-07-30

### Feat

- **新闻去重新增 bg=2 梯度规则** — `news_dedup.py` 在跨源候选区新增 `bg=2 + ratio≥0.45` 合并规则（`cross_merge_bg2`），弥补 bg≥3 硬门槛遗漏的有实体重叠 + 中高 ratio 的重复对
- **英文专名 ratio 降权** — 跨源 ratio 比较前对英文词做占位化处理（`_tk_`），避免共享英文专名（Anthropic/Meta/AMD 等）导致 SequenceMatcher 比率虚高；英文专名重叠仍由 `_extract_entity_bigrams` 独立处理

### Fix

- **入口文件 sys.path 注入路径层数修复** — `tui/tui.py` 和 `cli/cli.py` 的 `_project_root` 从脚本路径上溯项目根时少算一次 `dirname`（子包重构后文件下沉了 `src/python/tui/` 层级但路径计算未同步更新），导致 `from src.python.config` 等导入因 `sys.path` 指向 `src/` 而非项目根目录而引发 `ModuleNotFoundError`

### Docs

- **全文档路径引用同步** — 子包重构后（`core/`、`tui/`、`cli/`、`config/`）过期路径集中清理：`technical.md`（~20 处）、`llm-technical.md`（5 处）、`test-coverage.md`（6 处）、`testplan.md`（6 处）、`review-findings.md`（3 处）、`how-to-schedule.md`（2 处）、`plan-correlation-drawdown.md`（4 处）、`plan-chartjs-report-upgrade.md`（2 处）、`plan-chartjs-risk-analysis.md`（11 处）
- **校准报告归档** — `calibrate-dedup-threshold.py` 输出保存至 `docs-stm/tmp/dedup-calibration-report.md`，含 `cross_merge_bg2` 新规则基线数据（119654 条锚点）

## [0.9.1] - 2026-07-30

### Refactor

- **src/python/ 根文件归入子包** — 将 17 个根目录文件分别迁入 `core/`（基础设施）、`tui/`（TUI 入口）、`cli/`（CLI 入口）、`config/`（配置模块）四个子包；`handlers_check_sources.py` 因 CLI/报告共享迁入 `core/check_sources.py`；新增 `__init__.py` re-export 保持导入兼容；新增 `__main__.py` 支持 `python -m`；移除死代码 `_breaker_state.py`

### Docs

- **folders.md 目录树同步** — 根文件迁移后目录树更新至子包结构（core/cli/tui/config）
- **文档路径引用同步** — `faq.md`、`how-to-config.md`、`how-to-start.md`、`how-to-use-registry.md`、`scripts-reference.md`、`requirements.md`、`technical.md` 中过期路径全部更新为子包路径（`src/python/constants.py` → `src/python/core/constants.py` 等）
- **technical.md 附录 A 目录树更新** — 替换为最新子包结构

### Fix

- **CLI 测试 patch 路径修复** — `__init__.py` re-export 导致 mock 路径需加 `.cli` 层级，`test_cli.py` 和 `test_cli_edge.py` 共 6 处 patch 路径修正
- **technical.md 附录 B 标题重复** — 附录替换脚本导致的重复标题修复

## [0.9.0] - 2026-07-30

### Chore

- **ruff 版本锁定 + 全量格式修正** — `pyproject.toml` 锁定 `ruff==0.15.20`（精确版本，避免版本升级导致格式噪音）；全量运行 `ruff format src/python/ scripts/`，修复 CI ruff 格式检查报错
- **版本格式统一** — 管理文档版本头统一去除 `v` 前缀（如 `v0.8.12-dev` → `0.8.12-dev`），`check-version-consistency.py` 模板同步（`v{v}` → `{v}`），涉及 9 份文档

### Docs

- **review-findings.md 归档整理** — 0.8.* 已发布版本的已修复记录（rf-1~rf-64、rf-66~rf-135、rf-106~rf-107）迁移至 `archived_review-findings.0.8.x.md`，归档链接路径修复（`archive/0.8.x/` → `archive/v0.8.x/`）
- **plan.md 归档整理** — 0.8.* 已完成项（plan-12 数据源可用性矩阵、plan-13 数据源可靠性文档、plan-14 ADR）迁移至 `archived_plan.0.8.x.md`
- **changelog.md 归档整理** — v0.8.11 变更记录迁移至 `archived_changelog.0.8.x.md`

## 归档

- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

