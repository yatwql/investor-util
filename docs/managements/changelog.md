# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.5]**（2026-10-07）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.6-dev] - 开发中（未发布）

- **工程效能/测试**：**rf-621 影子双算毕业复核修正关闭**——流程优化批（rf-606 ~ rf-615）交付后复测初记「混合提交下结构性无法毕业」，机制复核证明为误判：共享语境变化的运行只跑单次全量（零影子加税、计数保持不推进），毕业由共享语境稳定的测试变更同步逐次推进；补 2 项行为锁定回归（混合提交「单次全量+计数保持+语境刷新」/ 毕业全生命周期 0 → 连续达标 → 测试变更零全量纯增量端到端可达），原拟「共享变化用旧计数做比对」方向因证据命题不同会削弱质量门、按质量前提不实施；结论与边界以用例固化 | rf-621
- **工程效能**：**ruff 探针入 pre-commit 钩子**——py 域新增 `ruff check`（E4/E7/E9/F 错误类，阻塞提交）与 `ruff format --check`（非阻塞探针仅提示，与 CI format job 同政策），与 file-length 同域后台并行；原「手动补 ruff」流程纪律由钩子自动化（CLAUDE/developer-guide 措辞同步）
- **门禁/发布**：**P2 发布门禁简化口径采纳**——发布测试档由 `--mode verify,regression` 改单档 `--mode regression`（场景回归）：发布流程强制 `dev → merge → tag master`，P1 合入门禁与 CI `master` 档（同提交 verify）已双重覆盖单元验证，tag 档 CI 同步只改单档；testplan §6.3 脚注由「可选建议」改「已采纳」并保留恢复条件，CLAUDE/developer-guide 门禁表与流程图、ci.yml 头注同源同步（`verify,regression` 组合模式本身保留供手动全量用）
- **工程效能/发布**：**发布流程分步编排脚本 `scripts/release.py`**——七个子命令把版本全链、changelog 发布段归档、演进对照快照、数据刷新、P2 门禁、release 提交 + P1 verify + `--no-ff` 合并打 tag、切开发版固化为可执行步骤（每步独立可审阅、失败即停；rf 归档迁移保留人工，推送 `--push` 可选）；测试载体 `test_release_tool.py` | plan-84


（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.5（2026-10-03 ~ 2026-10-07）
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
