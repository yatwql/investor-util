# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.0]**（2026-10-03）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.1-dev] - 开发中（未发布）

### Added
- **报告章级 LLM 开关**：`llm_settings.json → enabled_llm` 禁用的分析模块（全球政经局势/智囊团深度复盘/持仓体检/穿透深度）在 HTML 章节与 Excel 页签**整章隐藏**（原仅跳过生成、章节仍保留「待生成」占位），后续章号连续递进；判定集合 `LLM_MODULE_GATED_SECTIONS` 单一来源，两端同调 `get_llm_chapter_disabled()` 同配置同逻辑推导；新闻关联（LLM 仅二次增强）与 API 用量章不受章级影响
- **报告正文大块默认折叠**：「组合历史走势与回撤」章内容默认收起，提示条显示累计收益/最大回撤/年化波动摘要；原生 `<details>` 键盘可达，新增 `fold.js`（锚点定位与打印自动展开、打印后恢复，beforeprint 以捕获阶段先于图表快照展开并同步 resize），打印稿不显示提示条
- **版本演进对照可标注发布 tag**：`check-doc-traces` 豁免上下文锚定的「最近（一次）发布 tag + 版本号」行（与日期同为随发布重跑刷新的滚动读数，属当前状态），行中版本号叙述（如"该功能在 vX.Y.Z 引入"）仍检出
- **版本演进对照「当前开发版」列标注版本号**：表头列头补版本号 + 更新时间（与「最新发布」列的 tag + 时间对称）；`check-version-consistency` 新增 `evolution_head` 断言，锚定列头版本号与 `APP_VERSION` 同步（与文档版本头双点校验，发版漏改即报错，`--fix` 可自动同步）；`doc-traces` 同步上下文锚定豁免，行中版本号叙述仍检出

### Fixed
- **报告目录展开序与正文线性序不一致**：目录分组由固定组序改为「组间按组内最小报告号动态排序」，分组映射按注册号段归组（数据源可用性矩阵/持仓基本面/LLM API 用量归入新增「附录」组），展开后严格 1..N 与正文（flex order = 报告号）逐位一致，消除「3→15→4」跳号回跳；`report_section_order` 自定义后组序随之自适应（兼容报告序号可配置机制）
- **测试质量**：JS 资产清单由两函数局部元组收敛为模块级 `JS_ASSETS` 单一来源（测试同源派生）；打印隐藏断言改为跨全部 `@media print` 块查找（不依赖块出现顺序）；章号/分组断言补「展开严格连续 1..N」结构不变式

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.12 + v0.12.0（2026-09-15 ~ 2026-10-03）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12)
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
