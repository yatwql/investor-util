# 实现计划归档 — v0.11.x

> 归档时间：2026-09-15（v0.11.0 发布当日并入，plan-44）；2026-09-16 增补（plan-45，v0.11.1-dev 开发期）
> 原始文件：`docs-stm/managements/plan.md（当前迭代部分）`
> 涵盖版本：v0.11.0（2026-09-15）/ v0.11.1-dev（plan-45 完成态）
> 归档内容：本迭代已实现的计划项完成态记录（plan-44 报告增强子模块并入功能开关注册表；plan-45 报告章节整合）；
> plan-42 / plan-43 摘要见 `../v0.10.x/archived_plan.0.10.x.md`
> 设计文档索引：plan-45 的设计层与实施层文档已随本条目归档至 `section-consolidation/`（见下）

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


---
### P1 — 已完成（plan-45 完成态，2026-09-16 归档）

#### ✅ `plan-45` 报告章节整合（注册表条目 21 → 17，重生成配置模板）— 已完成（2026-09-16）

**动机**：注册表条目已有 21 个，其中若干同族/体量很薄/本是另一条目的子视图（市值核算明细与持仓分类同源；持仓关系矩阵与持仓集中度同属「持仓结构」；财报摘要是持仓基本面的叙事层；基金经理变更是基金业绩的子视图）。

**决定（用户）**：不做配置兼容，**重生成 `config.json` 与配置模板**；设计与实施逐条对照 `technical.md` §8 架构约束。

**方案（统一新语义命名：旧键/旧页签名/旧写入器/旧 partial 全部删除，不留 alias）**：
1. 新条目 `holdings_detail`「持仓明细与分类」（= 市值核算明细 + 持仓分类；两区块，均 `always`）
2. 新条目 `position_structure`「持仓结构与集中度」（= 持仓关系矩阵 + 持仓集中度；同 `type=fund_deep_analysis`；可见性取 OR）
3. 新条目 `fundamental_snapshot`「持仓基本面」（= 财务指标 + 财报摘要；两区块；两个功能开关各控一块）
4. `fund_performance`「基金业绩分析」吸收基金经理变更为章末尾区块（键与显示名语义未变；块门禁 `enable_fund_deep_analysis`；先例 `candidate_compare`）

**架构要点**：不新增 pipeline_data 键（pipeline_data 契约台账不动）；可见性模型最小扩展——注册表可选字段 `data_flag_any`（多契约 OR，未声明时行为不变）；序号/显示名/页签名一律经注册表（注册表驱动）。

**已实施（四批，每批一次提交、每批门禁）**：
- 批次① 可见性模型扩展 + 守卫（`data_flag_any` 注册表字段 + Excel/HTML 两侧 OR 判定 + 12 例守卫，零行为变化）— `bce98ee2`
- 批次② M1 `holdings_detail`：注册表 21 → 20 条；市值明细与分类汇总合为同页签两区块（`holdings_detail_sheet.py`），领域层（`market_value.py` / `category.py` 分类函数）不改名不删除；新增合并页签测试与「章节 type ↔ board_flags ↔ 装配键」一致性守卫 — `a11db932`
- 批次③ M2 `position_structure`：注册表 20 → 19 条；重合度 + 相关性 + 集中度三区块合一同页签（`position_structure_sheet.py`），可见性 `data_flag_any` OR（Excel 侧同步登记两契约 flag，修正悲观判定吞页签缺陷 rf-367）— `b8c0d862`
- 批次④ M3 `fundamental_snapshot` + M4：注册表 19 → 17 条；财务指标与财报摘要合为同页签两区块（`fundamental_snapshot_sheet.py` + `partials/fundamental_snapshot_section.html`，两功能开关各控一块）；`fund_manager` 章节并入「基金业绩分析」章末尾区块（`fund_performance._write_manager_block`）；board 参数合并为 `enable_fundamental_snapshot` — `f2c1a23a`
- 收尾：统计快照刷新（`567c2273`）+ 管理/用户文档一致性与顺序整改（`317b4e48`，自查 rf-369）

**十轮复盘**：实施前对两份设计文档做十轮复盘（命名链/架构约束/测试面/配置面 → 接缝完整性/守卫与可验证性 → 批次依赖与计数硬伤 → 跨文档同步与自洽终检），逐轮整改并提交（`2453690c` / `a95312a7` / `da3e2e77` / `7db80963`）；复盘记录见设计文档索引项的实施层文档 §6.6。

**验收标准（达成）**：注册表条目 **17**、序号连续 1~17；被并章节的页签/章节各减 3；契约键（`position_relationship_data` / `concentration_data` / `manager_data` / `financial_indicator_data` / `financial_report_digest_data`）全部保留；`--mode verify,regression` 4939 passed / 0 failed；`dev-verify` 2748 passed；四个 `--ci` + ruff + 版本一致性全绿。

**实施记录**：见 `../../managements/changelog.md`「plan-45 章节整合·批次②/③/④ 实施」「plan-45 设计文档十轮复盘（第 1~4 / 5~6 / 7~8 / 9~10 轮）」「plan-45 四批后管理/用户文档一致性与顺序整改」条；设计文档索引见下。

**设计文档索引**（归档于 `section-consolidation/`）：
- `section-consolidation-design.md` — 报告章节整合设计（设计层：四项合并方案 / 可见性模型扩展 / 架构约束对照 / 测试与文档同步清单 / 四批次验收标准）
- `section-consolidation-iteration.md` — 报告章节整合实施层（迭代施工单：命名统一总表 / 接缝地图 / 逐批施工步骤与量化验收 / 十轮复盘记录 / 守卫清单与基线方法 / 领域层与章节层边界 / 文档同步清单）
