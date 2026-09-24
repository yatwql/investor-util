# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.3-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 测试用例全量审计：去冗余 + 26 处名实相符重命名 + 弱断言强化（2026-09-24，rf-425）

**背景**（用户要求）：核对全部测试用例的冗余、无效与命名语义。门禁 `check-test-redundancy`（死用例/无断言/完全重复/自证）零告警；另建 AST 级增强扫描（7,378 用例）核查门禁未覆盖的三类。

**变更**：
- **去冗余**：`TestSupportsExtendedThinking` / `TestIsEffortModel` 在 `test_llm_utils.py` 与 `test_llm_api_base.py` 重复存在且后者为严格子集——唯一独有断言（`gpt-4o → False`）迁入 utils 版新增 `test_non_llm_family_not_supported`，删除两个子集类（-5 例，零覆盖损失）
- **重命名 26 处**：`test_success` / `test_normal` / `test_basic` 等不承载内容的命名，逐例读函数体后按 docstring 语义改为描述性命名（`test_returns_standard_quote_record` / `test_parses_roll_data_items` / `test_parses_three_us_indices` / `test_formats_dividend_yield_percent` 等）
- **弱断言强化 1 处**：`test_missing_code_still_processes` 改为精确断言（`turnover_rate == 1.0`，由两期权重不相交可推导），消除「仅非空」在实现假化时仍通过的空间
- 数据快照同步：`test-coverage.md`（unit/standard/verify/all/unit_llm）、`folders.md`（测试用例 7,760、行数）

**判定为合规、不改的部分**（避免制造「名实不符」新缺陷）：跨文件同体对 1 组（`test_no_quotes` —— sina/tencent 两家解析器并行覆盖，符合既定口径）；输入条件式命名 26 处（`TestParseFloat::test_zero` 等，类上下文已带语义）；抽样 7 例「仅非空断言」中 6 例判别性充分（warning 字段被填充 / lookup 命中 / 映射存在 / 回调已绑定）。

**验证**：受影响模块 4,632 passed；`check-test-redundancy --ci` 零告警；六项 `--ci` + ruff + 版本一致性全绿。

### 新增管理文档分区纪律断言（2026-09-24，rf-424）

**背景**：本轮两次自审失误同源——待处理项被误置已解决区（rf-421）、发布时误删归档索引（rf-423），本质都是「管理文档分区/索引纪律无机器断言」，门禁全绿也拦不住。在 rf-423 已补「归档索引完整性」之后，本轮补齐「分区纪律」。

**变更**（`scripts/check-doc-drift.py` 第 12 项）：
- 新增纯函数 `audit_management_partitions()`（读文件薄封装为 `check_management_partitions()`），三条规则：
  - **A. review-findings 分区互斥 + 已解决须有据**：同一 rf 不得同时出现在「待处理」与「已解决」；且每个已解决项必须在 changelog（现行 + 归档）中出现——待处理项被误置已解决表时必然无修复记录，正是该类失误的可检特征
  - **B. plan 待办区纯度**：不得出现 ✅ 已完成项，也不得列已归档项（已归档项只认 `#### ✅ \`plan-N\`` 条目标题，归档文件正文提及——如「后续项：plan-49 转正评估」——不误判）
  - **C. changelog 段头纪律**：现行文件只允许一个版本段头且必须为 `-dev`（已发布版本段须随发布移入 `archived_changelog.*.md`）
- 检查项枚举同步 6 处：脚本 OK 文案与 argparse 描述、`folders.md` ×2、`developer-guide.md`、`testplan.md` ×2、`CLAUDE.md` ×2（门禁条目）

**回归 +10**：真实仓库一致、三类历史失误各自检出、归档 changelog 中的记录不误报、归档文件正文提及不误报、空文件不崩。

**验证**：`pytest src/test/unit/scripts/test_check_doc_drift.py` → 83 passed；六项 `--ci` + ruff + 版本一致性全绿。

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
