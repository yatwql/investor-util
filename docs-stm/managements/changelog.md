# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

### Changed



---

## [0.3.0] - 2026-07-08

### Changed

- **版本号统一更新**：0.2.91 → 0.3.0（constants.py / README.md / pyproject.toml / 管理文档 / 用户手册共 10 处同步）。
- **管理文档归档**：changelog.md / plan.md / review-findings.md 的 v0.2.x 详细记录迁移至 `docs-stm/archive/` 对应 `archived_*.0.2.x.md` 文件，主文件保留简洁归档引用。
- **datasource-and-folders.md**：目录树补入 3 个新存档文件描述。

### Added

- **testplan.md 8 个 gap 全量覆盖补齐（共 52 项新增测试）：**
  - **HTML 打印样式**（9 项）：`@media print` 规则完整性检测 — 黑白友好/隐藏导航/展开折叠/热力图覆盖
  - **首次运行引导**（4 项 edge）：配置缺失自动初始化/目录创建/损坏降级/菜单可用
  - **Excel 数字格式**（7 项 edge）：styles.py 常量验证 — 金额/百分比/份额千分位
  - **LLM 三态占位区分**（6 项 edge）：NOT_CONFIGURED/MODULE_DISABLED/API_ERROR 互斥 + 内容引导
  - **日志分级输出**（5 项）：INFO/WARNING/ERROR 均落盘 + 级别前缀
  - **错误隔离业务语义**（1 项）：sheet 失败后穿透/市值模块仍被调用
  - **新闻流水线全链路**（2 项 edge+integration）：聚合→去重→关联端到端 + 关联度排序
  - **TUI 错误友好提示**（18 项 edge）：_print_error_with_hint 7 种异常分类 + 菜单调度异常捕获，不暴露原始异常类型名

---

> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.2.x.md](../archive/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/archived_changelog.0.1.x.md](../archive/archived_changelog.0.1.x.md)。
