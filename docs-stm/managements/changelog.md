# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.8]**（2026-09-29）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.9-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

---

### 交互优化：新增 [D] 配置目录信息子菜单（rf-471）

**背景**（用户要求）：持仓目录 / 持仓文件名 / 报告输出目录三个同属「路径配置」的入口平铺在主菜单占 3 个键位，而 `[D]` 已被系统自检占用，语义冲突。

**变更**：
- `tui_menu.MENU_ITEMS`：三项合并为 `[D] 配置目录信息`（20 → 18 项）；系统自检键 `D` → `T`（`FEATURE_GATED_ITEMS` 同步，仍受 `doctor_check` 门控）
- `handlers_config._cmd_config_dir_info()`：独立子菜单循环（`[C]` 持仓目录 / `[F]` 持仓文件名 / `[O]` 报告输出目录 / `[B]` 返回主菜单）——大小写归一、无效输入重提示、EOF/Ctrl+C 安全返回；子项在调用时取模块全局（便于打桩）
- 回归 +7 例（子菜单分发/大小写/返回/无效输入/EOF + 菜单键集与路由 D→`_cmd_config_dir_info`、T→`_cmd_run_doctor`）
- 文档同步：how-to-use-tui-menu / how-to-start / faq / how-to-config / how-to-config-llm / how-to-use-web-mode / how-to-use-cli-mode / requirements（R-TUI-02 18 项 + §3.2 菜单表 + R-DIAG-05）/ technical（§1.6.3 菜单体系）/ testplan / test-coverage / folders；代码内提示串（`handlers_log` docstring、`features.doctor_check` 说明）同步

---

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.8（2026-09-15 ~ 2026-09-29）
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
