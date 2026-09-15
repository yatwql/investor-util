# 投资复盘助手 — 实现计划
> 文档版本：0.11.0
> **编号源**：`plan-next = 45`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-44，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）**已全部完成并发布**（P1 轮 1~11 + 阶段 D~G 轮 12~20，plan-17~plan-24，changelog v0.10.1/v0.10.3/v0.10.4）。详细设计、实施轮次、推荐实施顺序与发布门禁记录见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)（含设计文档索引：`plan-investment-features.md` 设计层 §4 章节归并方案与 §4.4 架构合规自查表 + `plan-investment-iteration.md` 实施层 21 轮每轮量化验收 + 已完成项摘要表 + 推荐实施顺序 ①~⑧ + P0 发布门禁记录）。本文档当前**无在办计划项**（P1 区 plan-42 / plan-43 已完成，P4 区无待办）；仅保留待办登记区与归档引用；v0.10.x 已完成项（plan-8、plan-17~plan-43）见上述归档文件。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P1 — 当前待办

> 无待办项（plan-42「持仓个股财报摘要」、plan-43「持仓个股基本面数据源主备与财务指标提取」均已完成；完成项摘要与设计文档见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)）。

#### ✅ `plan-44` 报告增强子模块并入功能开关注册表（面板统一，不做兼容）— 已完成（2026-09-15）

**动机**：`P` 面板（`report_submodules`，存 `config.json`）与 `S` 面板（`features.json` 注册表，20 项）是两套并列机制，两处都用裸数字编号 → 用户跨面板记编号（本次已因手册编号漂移误开错项）。统一为单一事实来源与单一面板。

**已核实现状（开工依据）**：
- 注册表：`config/features.py` — `FeatureSwitchDef(label, desc, group, default, affects_report)`、`GROUP_EXPERIMENTAL`/`GROUP_STANDARD`、`GROUP_LABELS`、`GROUP_ORDER=(EXPERIMENTAL, STANDARD)`、`switches_in_group()`/`is_feature_enabled()`/`set_feature_enabled()`/`save_feature_overrides()`；注册表 docstring 显式写着「各报告章节与增强子模块 → config.json 的 enable_* 键」，需同步改写。
- 默认值：`_config_defaults.py::_DEFAULT_CONFIG["report_submodules"]`（8 项：data_quality=True、market_temperature=True，其余 6 项 False）+ 配置模板 `_get_default_config_template()`。
- 访问器：`_core.py` 8 个 `is_enable_*`（各自硬编码缺键回落，须与默认值一致）。
- TUI：`handlers_config.py` — `S` 面板 `_cmd_config_llm_modules` **硬编码两组** `(GROUP_EXPERIMENTAL, GROUP_STANDARD)`；`P` 面板 `_cmd_config_report_boards` 第 6 项进子面板 `_cmd_config_report_submodules`（8 项，`REPORT_SUBMODULE_ITEMS` 模块级常量，写路径 `set_config("report_submodules", ...)`）。
- Web：`web/config_edit.py` — surface `features`（两组派生）与 `submodules`（现取 config.json 值）+ `_EDITABLE` 8 条 `report_submodules.*` → `writer: "submodule"`；前端 `static/web/main.js` 已有 `renderBoolGroup('submodules', '报告增强子模块', …, {prefix: 'report_submodules.'})`（**块已存在，可直接复用**）。

**不做兼容（用户决定）**：不读旧 `config.json` 的 `report_submodules` 段、不写迁移层；重新生成 config.json（删除该段）。

**改动清单（按批次，每批独立可验证）**：
1. **批次① 注册表与真源**：`features.py` 新增 `GROUP_REPORT`（标签「报告章节与增强」）+ `GROUP_ORDER` 追加 + 8 条 `FeatureSwitchDef`（default 同现状、`affects_report=True`）；`_core.py` 8 个访问器改为 `is_feature_enabled(<key>)`（保留 `config` 形参但不再读它）；`_config_defaults.py` 删除 `report_submodules` 段与模板行；重生成 `data/config/config.json`。
2. **批次② TUI**：`S` 面板加入 `GROUP_REPORT` 块（并考虑 P 子面板保留为薄壳或删除、`P` 顶层面板第 6 项文案调整）；`P` 子面板写路径改 `set_feature_enabled` + `save_feature_overrides`。
3. **批次③ Web/CLI**：`config_edit.py` 的 `submodules` 负载改为注册表派生、8 条 `_EDITABLE` 改走 feature writer（键名可保留 `report_submodules.*` 以减少前端改动）、前端补 `labels: surface.features.labels`；CLI `--feature` 自动放行 8 个新名（验证）。
4. **批次④ 文档与守卫**：`how-to-config`（两张开关表合并、删除全部「菜单 P → …」引用）、`requirements` 配置表、`technical`（注册表约束适用范围与语义表）、`reports-instruction`/README/`folders`/`testplan`/`changelog`；测试同步（`test_config`/`test_handlers_config`/`test_config_edit`/`test_features`/`test_check_semantic_index` 等 11 处）+ 新增「注册表 8 项默认值与访问器一致」「面板清单覆盖全部开关」「features.json 覆写生效、config.json 段不再被读」三条守卫。

**验收标准**：`report_submodules` 在代码与文档中**零残留**（`grep -r report_submodules src/ docs-stm/` 仅剩历史 changelog/归档）；`S` 面板与 Web 面板各出现「报告章节与增强」一块共 8 项、可开关且落 `features.json`；8 个开关行为与现状逐项等价；四个 `--ci` + `--mode verify` + ruff 全绿。

实施记录：见 `changelog.md`「报告增强子模块并入功能开关注册表（plan-44 完成，不做兼容）」条（本条目即设计记录；不再另建设计文档）。

### P4 — 实验功能

> 无待办项（plan-30 ~ plan-41 全部完成，完成项摘要见归档）。

## 归档

- [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md) — v0.10.x 已完成项
- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
