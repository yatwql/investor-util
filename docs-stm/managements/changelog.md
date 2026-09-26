# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.5]**（2026-09-26）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.6-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### CI 补齐守护 job + 门禁数字与注释痕迹整改（2026-09-26，rf-444、rf-445、rf-446）

**起因**：核对「git hook 包含哪些任务 / 守护包含哪些脚本」时发现三处不一致——门禁表数字少于实际、CI 未跑守护脚本、以及本地扫描循环漏跑 `check-code-traces`（导致本会话写入的 7 处任务编号引用/历史叙述一直未被拦下）。

**变更**：
- **CI 补全（`.github/workflows/ci.yml`）**：新增 **`guards` job（阻塞型）** 逐个 step 跑 7 个 `--ci` 守护脚本（`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-doc-drift` / `check-test-redundancy` / `check-requirement-trace`）；`format` job（仍为非阻塞 `continue-on-error`）补 `ruff check` 步骤；`test` job 与三档分流规则不变（并在文件头注释补「P2 → verify,regression」的准确模式名与新增 job 说明）
- **注释痕迹整改**：7 处改写为语义化描述——`core/check_sources.py`、`src/test/conftest.py`、`test_check_sources.py`、`test_report_backup_source.py`、`test_html_template.py`、`scripts/_doc_drift/_format.py`；`check-code-traces --ci` 恢复“未发现历史变更痕迹，注释干净”
- **文档同步**：开发者指南三级门禁表「4 个 check 脚本」→「**7 个**」并新增「**CI 同步执行**」段（分流/矩阵/两 job 职责与阻塞性）；编号保障表新增 `CI guards job` 行（“四层→五层”）；`CLAUDE.md` 的 CI 条目改为描述实际流水线（三档测试矩阵 + `guards` 阻塞 job + `format` 非阻塞 job）

**验证**：`check-code-traces` 由 7 处 finding 回落为 0；7 个 `--ci` 脚本 + `ruff check` + `ruff format --check` 全部 exit 0（本地等价演练 CI `guards`/`format` job 命令）；`ci.yml` YAML 解析通过（jobs: test / format / guards）。

### 清理无效 pre-push 桩 + 补 `--off` 提示（2026-09-26，rf-447）

**结论（先验证后动手）**：`.git/hooks/` 下三个 `pre-push` / `pre-push(1)` / `pre-push(1)(1)` 确实是**无效残留**，两层独立原因：
- **路径旁路**：`core.hooksPath = .githooks`（仅仓库本地 `.git/config`）——`git hook run pre-push` 在 `.git/hooks/pre-push` 存在的情况下报 `error: cannot find a hook named pre-push`，证明 Git 根本不查 `.git/hooks/`；
- **权限拦截**：三者均为 mode 644（非可执行）——`git -c core.hooksPath=.git/hooks hook run pre-push` 直接给 `hint: … ignored because it's not set as executable.`；
- 内容为 17 字节 `#!/bin/sh` + `exit 0`（无逻辑），mtime 相隔 3 秒，属云同步冲突副本；`git ls-files .git/hooks/` 为 0（不跟踪、不跨机器），全仓无脚本/文档引用。

**变更**：
- 删除三个本地残留（原件备份至 `/tmp/pre-push.bak` 以便回滚）——删除后可消除「回退默认路径时 Git 每次 push 的 not-executable 警告噪音」；
- `.githooks/install-hooks.sh` 的 `--off` 分支增两行说明：Git 回退到 `.git/hooks` 后本脚本**不会**在其中安装任何 hook，该目录内容也不随仓库同步（避免误以为回退默认路径会启用某些校验）。

**验证**：`sh -n` 语法通过；`--off` → `hooksPath` 未设置，再启用 → `.githooks`（往返正确）；启用态下 `git hook run pre-push` 仍为 not found（即确实不存在 pre-push 校验）、`git hook run pre-commit` exit 0。

---

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.5（2026-09-15 ~ 2026-09-26）
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
