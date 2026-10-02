# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.12]**（2026-10-02）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.13-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### Added

- **Web 标签页工作台排版**：首页从 7 卡单列堆叠重构为五区标签页（生成报告 / 调仓模拟 / 配置 / 运行状态 / 日志），粘顶导航、方向键与 `#hash` 深链；运行状态区新增**缓存卡**（文件数 / 占用 / 命中率 / 过期数 / 前缀分布 + 刷新 / 清理过期，`GET /api/cache` + `POST /api/cache/cleanup`，同源校验）。
- **Web 调仓 What-if 模拟区**（新页签 `POST /api/whatif`）：基准默认取配置正式持仓、可改上传，目标必传，生效日可选（联网回测 opt-in）；与 TUI `[W]` / CLI `whatif` 同链生成独立产物 `调仓模拟.xlsx` / `.html`，互斥锁 429，错误信封分支完整。
- **README 定位改版**：营销向首屏（卖点、徽章、三分钟上手、实际报告效果截图、参与贡献）、功能地图九域表、MIT `LICENSE`。
- **发布门禁升级**：`check-version-consistency --ci` 纳入 P0/P2 门禁与 CI `guards` job（7→8 个守护脚本），pre-commit 新增条件化版本一致性检查，`check-doc-drift` 新增「守护清单同源」断言。

### Changed

- Web 状态区网格由三列改自适应两列（760px 内容区下三列致名称/耗时竖排换行）。
- 架构 SVG（capabilities / architecture / llm-chain）事实性修订（九大功能域、17 页签、5 provider / 6 输出模块）。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.12（2026-09-15 ~ 2026-10-02）
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
