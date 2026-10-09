# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.7]**（2026-10-09）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.8-dev] - 开发中（未发布）

- **样式/Web**：**Web 配置页 375px 横向滚动修复（rf-644，解除 rf-257 ④ 阻塞）**——`style.css` 三层钳制：路径文案 `overflow-wrap:anywhere` + `.generate-form > *` 行线宽按列封顶（flex 行线宽取 fit-content 不受列宽封顶是机制性根因）+ select/file input `min-width:0; max-width:100%`；真机 CDP 复验 375px 断言 35/0/2（修前 4.1/4.3 不过）、五页签×十二视口扫描 60/60、新旧 A/B scroll 404→375；新增 `test_web_responsive.py` 5 用例回归；另补标签页 favicon（`favicon.svg` + `link` 声明，消除 `/favicon.ico` 404）。
- **修复/报告侧**：**调试页窄视口溢出与打印 display 还原修复（rf-645，rf-113 附带发现）**——`test-chart.html` grid 列下限改 `minmax(min(420px,100%),1fr)`；`chart-print.js` beforeprint 记录 canvas 原内联 display、afterprint 按记录还原（未记录回退 block、周期末清空），替代置空串导致的 computed display 漂移；`test_feature_interactive.py` 补 4 回归用例。
- **文档/需求**：**事件窗量化对照需求登记补齐（rf-646）**——`requirements.md` §6.16 + `R-EW-01..06` 六条需求行（先读实现后如实登记），`testplan.md` §2.1 补 6 行载体映射，`check-requirement-trace` 纳入 R-EW 域（38/38 域全量双向一致，后续新增不再漏报）。
- **文档/结构**：**设计语言契约 DESIGN.md 迁入管理文档目录**——自仓库根移至 `docs/managements/DESIGN.md`（设计约束类文档归属管理文档区）；路径性引用同步（`check-style-guardrails.py` 真值路径、4 处契约测试路径、CLAUDE.md 设计契约入口与管理文档清单、developer-guide 设计契约链接、folders.md 目录树与统计口径；样式/模板中的注释性提及按文件名寻址，无需改动）。


（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.7（2026-10-03 ~ 2026-10-09）
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
