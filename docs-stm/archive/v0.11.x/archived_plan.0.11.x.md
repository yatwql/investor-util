# 实现计划归档 — v0.11.x

> 归档时间：2026-09-15（v0.11.0 发布当日并入；0.11 系列首份）
> 原始文件：`docs-stm/managements/plan.md（当前迭代部分）`
> 涵盖版本：v0.11.0（2026-09-15）
> 归档内容：本迭代已实现的计划项完成态记录（plan-44）；plan-42 / plan-43 摘要见 `../v0.10.x/archived_plan.0.10.x.md`

---
### P1 — 已完成（plan-44 完成态，2026-09-15 归档）

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
