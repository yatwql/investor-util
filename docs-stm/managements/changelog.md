# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.10-dev] - 2026-08-03

### Feat

- 调仓 What-if 模拟报告归档格式对齐主报告（用户建议）：最新版固定名 `调仓模拟.xlsx` / `调仓模拟.html`（每次覆盖为最新对比）+ 日期目录归档版 `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.xlsx/.html`（超 180 天自动清理），见 `report/whatif_writer.py`
- TUI 调仓模拟单文件场景增强（用户建议）：持仓目录只有基准一份时，`_select_candidate_file` 引导三选——`[1]` 自动复制基准为可编辑目标模板（`<基准名>-调仓后模板.xlsx`，同名追加序号不覆盖）/ `[2]` 手动输入目标文件完整路径 / 回车取消，见 `tui/handlers_whatif.py`

### Fix

- **rf-166** TUI 按 W 调仓模拟 output_dir 相对路径 bug：`get_config_cache()` 未初始化时回退 `{}` 导致输出目录依赖启动目录；改为回退 `get_config()`（absolutized 路径），与 CLI 一致
- **rf-165** TUI 按 W 调仓模拟单持仓文件场景：持仓目录只有基准一份文件时候选为空直接退出不生成报告；改为引导选择目标文件（自动复制模板 / 手动输入完整路径 / 取消），不再直接退出
- **rf-167** 缓存原子写测试隔离缺陷：`test_set_atomic_write_content` 误扫全局系统临时目录（断言对象与原子写实际目录/后缀不符），并行测试下偶发失败；改为扫描缓存目录内 `.tmp` 残留

### Docs

- 发布门禁（P2）补充代码/文档历史痕迹检查：`check-code-traces.py --ci` + `check-doc-traces.py --ci`（与 P0 一致），见 `testplan.md` §6.3 第 11 条与 `CLAUDE.md` 发布门禁（P2）

### Test

- 新增 `test_whatif_writer.py`（4 用例）：调仓模拟报告输出归档格式——Excel/HTML 最新版固定名 + 日期目录归档版 + 触发 `_cleanup_old_archives` + 最新版被占用抛 PermissionError / 归档版写失败仅告警
- `test_handlers_whatif.py` 增 3 用例：单文件场景选 `[1]` 自动复制模板返回模板路径 / 无效选择后复制 / 复制失败（OSError）返回 None
- `test_set_atomic_write_content` 隔离修复（rf-167 回归）：扫描缓存目录 `.tmp` 残留而非全局系统临时目录

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.9（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
