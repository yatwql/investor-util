# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.6.10-dev] - 未发布

### Changed
- **文档**: technical.md §5 LLM 集成层从 73 行简述重构为完整概要设计（5 子节），llm-technical.md 重组章节结构（§5 拆分为 3 子节、§14 内容归并、新增附录 A-C）
- **文档**: technical.md + llm-technical.md 技术债清理（删除 P1/旧格式等历史痕迹）
- **文档**: datasource.md 从 24 行极简表格扩展为完整参考手册（缓存前缀、数据质量说明、路由说明、常见问题）
- **文档**: how-to-start.md 新增 CLI 命令参考（全局参数 + report/cache 子命令完整参数表）
- **文档**: how-to-config-llm.md 新增 HTTP 代理配置章节
- **文档**: how-to-schedule.md 新增 "报告输出路径" 章节、完善 CLI 引用标注
- **文档**: faq.md 新增数据源代理配置问答
- **文档**: how-to-use-registry.md / how-to-test-my-code.md 补充指向 technical.md/requirements.md 的架构背景引用
- **文档**: plan.md / review-findings.md 归档版本列表统一为降序排列（从新到旧）
- **文档**: how-to-schedule.md 常用命令表补充 `cache --update position` 行
- **文档**: testplan.md 单元子组计数 8→9，对齐实际注册数
- **代码**: 提取 `get_llm_module_failure_reason()` 统一函数，消除 3 处重复的 dict 格式兼容判断；修复 `build_llm_module_info()` 对多链 dict 格式的 `TypeError: unhashable type: 'dict'` 崩溃

### Fixed
- **测试**: conftest.py `_KNOWN_MARKERS` 补入 `unit_cli`（已在 pytest_configure 注册但缺少校验项）

---

> v0.6.x 及更早版本变更记录已归档：
>
> - [`v0.6.x`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.9（2026-07-15 ~ 2026-07-18）
> - [`v0.5.x`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
> - [`v0.4.x`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
> - [`v0.3.x`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
> - [`v0.2.x`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
> - [`v0.1.x`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
