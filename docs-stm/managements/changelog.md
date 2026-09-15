# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.1-dev] - 开发中（未发布）

### plan-45 设计文档十轮复盘（第 7~8 轮：批次依赖与计数硬伤）（2026-09-15）

- **第 7 轮（批次依赖与可回退性）**：②③④ 共改 7 个文件（注册表 / 两侧可见性 / Excel 三处分派 / 模板 / 配置模板），**无法任意顺序单独回退**；新增 §6.4b「批次依赖与回退矩阵」——依赖链 ①→②→③→④（③④ 均改 `_compute_section_visibility` 与 fund 深度分组，④ 建立在 ③ 之后）、共享文件表、**逆序回退纪律**（④→③→②，每批一次提交）、版本身份（四批同属 0.11.1-dev）。
- **第 8 轮（计数一致性与非目标边界）——修正硬伤**：批次④ 实际含**两处合并**（财报两章合一 + `fund_manager` 并入 `fund_performance`），但 ④-1 未声明删除 `fund_manager` 条目、④-7/验收/§6.6b 仍写「条目数 18」。已修正为 **17**（21→20→19→17），④-1 显式删除 `fund_manager` 条目、④-2 补删除其页签名映射。非目标边界（LLM 条目不合并）经与注册表现状核对一致，予以保留。

### plan-45 设计文档十轮复盘（第 5~6 轮：接缝完整性与守卫）（2026-09-15）

- **第 5 轮（接缝完整性）**：新增 4 处漏登接缝——`excel_module_loader.py` 的模块表键与错误文案、`html_writer_display.py` 对 `market_value_sheet._weighted_avg_cost` 的**反向依赖**（删模块将 ImportError，须迁移保位）、partial 实况（全仓仅 4 个 partial，**只有 M3 需合并 partial**）、`chart_data_builder` 六图键不变但图归属章节变化；`features.py` 两个 `FeatureSwitchDef` 开关名保留。**处置**：接缝地图补 6 行、批次② 补 ②-4b/②-4c、批次④ 修正 partial 步骤、新增 §7.5 风险补充 3 条。
- **第 6 轮（守卫与可验证性）**：7 项既有守卫均在位但**无守卫清单**、**缺合并前基线方法**、「注册表 type 三处严格一致」缺正面自动化守卫。**处置**：新增 §6.6b「守卫清单与基线方法」——既有守卫表（标注每批变化处 21→20→19→18）、每批新增守卫（`test_section_type_flag_consistency`、模块加载器一致性、区块门禁、内容等价）、基线方法（批次② 前存 `docs-stm/tmp/` 快照，不入库；比对落成单测）。

### plan-45 设计文档十轮复盘（第 3~4 轮：测试面与配置面）（2026-09-15）

- **第 3 轮（测试与守卫）**：发现**同名混淆风险**——`market_value`/`category` 在 100+ 测试中属**领域层**（`DetailRow.market_value` 字段、`report/market_value.py` 市值计算、`report/category.py` 分类函数），而施工单原写「删除 `report/category.py`」会破坏领域层。修正：只迁移**纯章节写入器**，领域模块保留；新增 §6.7「领域层 vs 章节层边界」（含缓存类型域 `get_exact_type_map()` 的 `fund_manager_snapshot`/`fund_concentration_snapshot` 不改）；测试同步清单改为区分「章节键断言（逐文件行）」与「领域词（不在范围）」。
- **第 4 轮（配置与校验面）**：`_validation.py` 允许类型集合与 `config_edit.py` 硬编码处已列入 §3.2 下游清单；发现注册表 docstring「共 21 项」与架构约束表「报告 19 个模块」表述陈旧 → 收尾步骤新增「条目数表述同步」；确认 `_config_defaults.py` 的 `report_section_order` 模板随注册表自动派生（无需手改）。

### plan-45 设计文档十轮复盘（第 1~2 轮：命名链与架构约束）（2026-09-15）

- **第 1 轮（命名统一性）**：设计层新增 §3.2「命名统一的下游影响清单」——把注册表 `type` 的语义化、两侧 `board_flags` 映射键、`enable_*` 形参链、`config/_validation.py` 允许类型集合、Web 硬编码面列入同一张表，明确「三处严格一致」纪律；施工单补 ④-1b 步骤。
- **第 2 轮（架构约束符合性）**：核实代码侧接缝——两侧 `board_flags` 与 `_validation.py` 允许集合仍含旧 `type`，Web 面有硬编码；前端标签字典与 TUI 面板已按注册表派生（无需改）。**关键补充**：`enable_financial_report_digest` 形参在章节合并后必须删除（该章不再存在），涉及 `html_writer`/`excel_generator`/`_report_generation` 三处调用链。
- 施工单新增「允许保留的旧名白名单」（契约键 / 功能开关名 / 缓存前缀 / 数据源类别 / 历史记录）与「复盘记录」表。

### plan-45 实施层文档（迭代施工单）落地（2026-09-15）

- 新增 `docs-stm/plan/section-consolidation-iteration.md`（实施层，与设计层 `section-consolidation-design.md` 配套）：**命名统一总表**（旧名→新语义名，旧名全部删除留零 alias；契约层不改名）、**接缝地图**（注册表/页签名表/两侧可见性判定/Excel 分派点行号/HTML 锚点行号/页签写入器/契约写入点）、**批次②③④ 逐条施工步骤**（含命名 grep 检查、测试与文档同步清单）、收尾与门禁、风险与回退。
- `plan.md` 的 plan-45 条目补实施层文档引用并标注批次①已实施。

### 立项：报告章节整合（plan-45，重生成配置模板）（2026-09-15）

- 注册表条目 21 → 17 的四项合并（市值核算明细+持仓分类 / 持仓关系矩阵+持仓集中度 / 财报摘要并入持仓基本面 / 基金经理变更并入基金业绩），**保留吸收方主键**以免迁移 `report_section_order` pin 与开关名；按用户决定**重生成 `config.json` 与配置模板**（不做兼容）。
- **统一语义命名**（用户要求）：合并后一律用新语义名——新条目键 `holdings_detail` / `position_structure` / `fundamental_snapshot`（`fund_performance` 语义未变），页签名、页签写入器模块与函数、HTML 锚点与 partial 文件名同步改名；旧键/旧页签名/旧写入器/旧 partial **全部删除不留 alias**，配置模板与 `config.json` 重生成。**契约层保留各区块自己的契约键**（不造伪契约键）。
- 架构要点：可见性模型最小扩展——注册表可选字段 `data_flag_any`（多契约 OR，未声明时行为不变）；序号/显示名/页签名一律经注册表驱动；区块级门禁沿用「基金业绩分析章内候选比较子表」既有先例。
- 批次①（可见性模型扩展）已完成并提交：注册表字段契约注释 + Excel（`should_create_sheet`）与 HTML（`_compute_section_visibility`）两侧 OR 支持（悲观判定）+ 新增 `test_section_visibility.py` 12 例守卫；既有条目零变更、行为零变化。
- 设计文档 `docs-stm/plan/section-consolidation-design.md`（现状核实 / 四项合并方案 / 架构约束对照 / 测试与文档同步清单 / 四批次验收标准）；`plan-next` 45 → 46。

### 发布 v0.11.0 及已发布记录归档（2026-09-15）

- **发布**：`0.10.20-dev` → **v0.11.0**（本次跨越未发布的 0.10.20 编号，直接进入 0.11 系列）：`APP_VERSION`/`pyproject.toml`/README/9 份管理文档版本头/新版 changelog 段头全链同步（`check-version-consistency` [OK]）；发布数据文档按 `collect-test-coverage` 实时快照刷新（`test-coverage.md` 子表、`folders.md` 项目统计、`datasource.md` + `datasource-reliability.md` 逐类核对）；发布门禁（P2）`--mode verify,regression` 4,939 通过 / 0 失败 + 四个 `--ci` + ruff 全绿；打标签 `v0.11.0` 并推送。
- **归档（0.11 系列首份）**：`[0.11.0]` 已发布变更记录整体迁入新建的 `docs-stm/archive/v0.11.x/archived_changelog.0.11.x.md`；`plan.md` 的 plan-44 完成态迁入 `docs-stm/archive/v0.11.x/archived_plan.0.11.x.md`（P1 区自此仅保留「无待办项」与归档引用，概述补 v0.11.x 已完成项指向）；`folders.md` 目录树新增 `archive/v0.11.x/` 并刷新归档/项目文档统计；changelog 与 plan 的「归档」段各补一条链接。
- **开发版本**：打 tag 后即切换至 **0.11.1-dev**（`APP_VERSION` 与全部文档版本头），changelog 新增本轮开发段。

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。


## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0（2026-09-15，0.11 系列首份）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
