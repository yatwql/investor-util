# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.3-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 修复归档索引被误删 + 新增归档索引完整性守卫（2026-09-24，rf-423）

**背景**（用户指出）：发布 v0.11.2 的版本切换提交把 changelog「已发布段至文件末尾」整段重写，而 `## 归档` 索引段位于文件末尾 → 11 条历史归档索引被一并删除。当时没有任何断言覆盖「管理文档归档索引 ↔ `docs-stm/archive/` 实际文件」的一致性，故门禁全绿也未拦下。

**变更**：
- `changelog.md`：从发布前版本取回 `## 归档` 索引段（11 条，0.11.x 条目更新为 v0.11.0 ~ v0.11.2），移除发布时临时添加的单条指针
- `scripts/check-doc-drift.py`：新增第 11 项**归档索引完整性**检查 `check_archive_index()`——changelog / plan / review-findings 三份管理文档的归档索引与 `docs-stm/archive/` 下对应 `archived_*` 文件**双向**比对（漏列 → 「缺少」；幽灵引用 → 「不存在」）；实现上**直接读文件**，不走 `_scan_docs()`（该扫描面排除历史记录类，changelog 正在其中——正是本次缺口的成因）
- 回归测试 +5：真实仓库一致、正反两向检出、被检面覆盖三份文档、以及一条端到端「真实仓库索引被删即报」用例

**验证**：`pytest src/test/unit/scripts/test_check_doc_drift.py` 73 passed；六项 `--ci` + ruff + 版本一致性全绿。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.2（2026-09-15 ~ 2026-09-24）
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
