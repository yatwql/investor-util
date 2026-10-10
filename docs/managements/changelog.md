# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.9]**（2026-10-10）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.10-dev] - 开发中（未发布）

- **文档**：**需求文档模块清单补齐（rf-658）**——`requirements.md` §6.3 报告模块清单表补入「持仓变动复盘」「调仓纪律回放」两行（序号 15/16，开关默认关，原 15~17 顺延为 17~19），消除需求文档内部（与 R-OUT-05「页签 1~19」）及与技术文档/代码注册表（19 项）的不一致；两模块详细需求（§6.13/§6.15）早已存在，仅总清单表滞后。

- **重构/配置**：**联接基金穿透开关取消、穿透内置恒开（plan-117 完成）**——移除 `feeder_penetration` 功能开关（注册表 28→27 项、常规组 11→10；TUI [S] 面板常规块 12-21、报告块 22-34，面板编号文档同步）；`with_feeder_penetration` 删开关分支、穿透无条件执行（结果标注键 `feeder_penetration` 保留，报告「穿透自目标 ETF `XXXXXX`（未折算持有比例）」标注不变）。理由：联接基金本身不持有股票，不穿透即底层暴露恒空，属失真口径而非可选口径；开关默认即开且无真实关闭使用记录。`features.json` 残留该键按「无消费者开关」告警（先例 plan-115 `metrics_*` 口径）。同步：requirements R-PEN-01、technical（§联接基金穿透 + 语义命名表 + 开关声明计数）、how-to-config / how-to-use-tui-menu / how-to-use-web-mode（开关表删行、面板编号与影响报告清单）、how-to-config-llm（[S] 面板编号顺带校正为 8-11/12-21/22-34）。测试：删「开关关闭→不穿透」死用例；`test_switch_on_by_default` 改写为 `test_penetrates_unconditionally`（全仓开关置 False 仍穿透，防开关分支回潮）；`TestRegistryLiveness.REMOVED_STALE_FLAGS` 增列防复活

（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.9（2026-10-03 ~ 2026-10-10）
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
