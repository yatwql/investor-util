# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.6]**（2026-10-07）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.7-dev] - 开发中（未发布）

- **工程效能/发布**：**版本一致性 `--fix` 不再吞空行 + 消除脚本 SyntaxWarning**——`_auto_fix_header` 行首空白类改同行字符类（原 `\s` 含换行，MULTILINE 下吞掉版本头前空行，developer-guide 受损已恢复），docstring 改 raw 串消除 invalid escape 警告；回归补「空行保留 + 跨行不误判 + 无警告编译」用例 | rf-624
- **工程效能/发布**：**`release.py publish` 归一化 `--title`**——新增 `normalize_release_title()` 剥离 title 自带的 `release: v… —— ` 前缀，防双前缀 subject（v0.12.6 发布提交实测出现，历史不可变，修复防再犯） | rf-625
- **运行体验**：**生成进行中阶段 ETA 预估**——`core/perf` 新增同阶段历史中位数预估 `estimate_stage_eta`（最近 20 次运行同名阶段减已耗时、严格同报告类型筛样本、无样本与读档/计算异常一律静默降级）与阶段状态唯一格式器；`PerfCollector` 可选阶段广播回调（回调异常隔离，basic/both/full 三处管线构造点零调用点改动）；`ProgressReporter.stage_progress` 基类单一实现，CLI verbose / Web / TUI 同源（瞬时阶段不刷屏、历史不足先静默后仅显已耗时） | plan-97
- **运行体验**：**主菜单页头常驻状态仪表盘**——新增 `tui/status_line` 五项本地单源组装（上次报告时间 ← perf 历史末条 / 缓存过期数 ← 与 [4] 同口径统计 / 数据新鲜度 ← 最新价格缓存数据日期与自然日龄 / 降级源数 ← 健康历史末条 fail_count / LLM 状态点 ← llm_status 同源 ●○），逐项异常降级为「—」、整行永不抛、TTL 45s 记忆化随页头重绘零外部调用（新鲜度刻意不取交易日历：日历缓存未命中会走 akshare 触网），`print_header` 标题下常驻一行并附详情菜单指引 | plan-96

（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.6（2026-10-03 ~ 2026-10-07）
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
