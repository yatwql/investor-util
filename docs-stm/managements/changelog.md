# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.7.8-dev] - 未发布

### Changed
- **changelog.md**: v0.7.0~v0.7.7 详细变更记录归档至 `archive/v0.7.x/archived_changelog.0.7.x.md`，主文件仅保留当前版本 + 归档索引
- **better-investment-advice 完整归档**：目录从 `docs-stm/plan/` 移至 `docs-stm/archive/v0.7.x/`，所有外部引用（technical.md 3 处、plan.md 1 处、folders.md 1 处）同步更新
- **管理文档版本头同步**：llm-technical.md、test-coverage.md、folders.md 版本头更新至 v0.7.8-dev
- **reports-instruction.md**: 补充投资分析与风控/基金评价功能-报告位置对照表

### Docs
- **discussion-better-investment-advice.md**: Phase 3 状态（LLM 事实校验器从待办改为 ✅）、Phase 4 状态（从"11 项已交付+4 项待办"改为"全部 15 项 ✅"），版本头（v0.7.7 → v0.7.8-dev），顶部状态摘要同步
- **Phase 5（用户画像）+ Phase D（CAPM α）已关闭**：better-investment-task.md 全部 8 项标记 ❌ 已关闭，汇总表同步；discussion-better-investment-advice.md 总览表、风险表、依赖关系图、全量估时描述同步更新
- **plan.md**: 恢复概述节与归档索引（v0.1.x ~ v0.7.x）
- **review-findings.md**: 恢复历史审查记录链接 + 历史归档节

### Plan
- **task91-enhanced-llm-strategy.md D16 终轮一致性扫描修复**：
  - 修复目录编号偏移（§6/§7/§8 锚点与实际标题对齐）
  - I-09 cost_tracker.py 误引用→改为 `generate_debate_procon()` 内建 output token 守卫（D9 发现落地）
  - I-06 闭包变量捕获→改为 list-container 模式（D14 发现落地）
  - R6 第三层防线"综合阶段交叉校验"不存在→降为 2 层防线描述，添加注释（D16 发现）
  - R2 交叉引用错误（I-12→I-03）修复
  - I-03 session_cache 添加 threading.Lock 线程安全要求
  - §4.4 新增/修改文件清单补全遗漏文件（html_writer.py、orchestrator.py、llm_content.py 等）
  - 依赖图 I-12 连接分支修正（从 I-04/I-05 块移至独立节点）
  - I-06 文件变更补全 orchestrator.py

---

> v0.7.x 版本变更记录已归档：
>
> - [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.7（2026-07-18 ~ 2026-07-20）
>
> 更早版本归档：
>
> - [`v0.6.x`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
> - [`v0.5.x`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
> - [`v0.4.x`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
> - [`v0.3.x`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
> - [`v0.2.x`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
> - [`v0.1.x`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

