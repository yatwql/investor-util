# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.1-dev] - 开发中（未发布）

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
