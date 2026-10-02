# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.11]**（2026-10-02）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.12-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 文档治理

- **check-code-traces 拆包（rf-533）**：1,016 行破 800 硬上限的唯一脚本，按「模式表/扫描/守卫」拆为 `scripts/_traces_code/` 六模块包，入口只留 CLI（185 行）与原面 re-export；`_traces_common.py` 并入包内 `exemptions.py` 并删兼容壳（测试改指向子模块）；check-task-numbering / check-test-markers / check-doc-traces 三脚本迁移 `_checklib` 契约（补 `-v`、统一输出与退出码，17 处 sys.path 样板文本统一）。scripts 单测 428 例全通。

- **已修复 rf 记录批量归档（发布后治理）**：review-findings.md 裁剪为纯待处理集——P2E 表 rf-522~527 六行已修复行与游离的 rf-532 行、P2C 的 rf-520 摘要引言原文迁入 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) 新增「v0.11.11 批次」段（rf-474 明细此前批次已在档）；归档头涵盖版本补 v0.11.11。主文件现仅存待处理项：P1 人工验证 rf-113/rf-114、P2A 八长文件复核行、P2B rf-257 用户复验、P2E rf-521 与 rf-528~531 五项。## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.11（2026-09-15 ~ 2026-10-02）
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
