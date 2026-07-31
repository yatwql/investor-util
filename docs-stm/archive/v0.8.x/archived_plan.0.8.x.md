# 实现计划归档 — v0.8.x

> 归档时间：2026-07-30
> 原始文件：`docs-stm/managements/plan.md`
> 涵盖版本：v0.8.0 ~ v0.8.10（2026-07-21 ~ 2026-07-30）

---

## v0.8.x 设计文档

v0.8.0 ~ v0.8.9 版本涉及的中间设计文档：

- [`datasource-reliability-documentation.md`](datasource-reliability-documentation/datasource-reliability-documentation.md) — plan-13（数据源可靠性文档✅）／ plan-14（ADR⏸）
- [`batch-parallel-design.md`](batch-parallel/batch-parallel-design.md) — 批量并行调度技术设计
- [`batch-parallel-iteration-plan.md`](batch-parallel/batch-parallel-iteration-plan.md) — 批量并行调度迭代计划
- [`perf-completion-summary.md`](perf-benchmark/perf-completion-summary.md) — 性能基准体系归档摘要
- [`perf-design-and-verification.md`](perf-benchmark/perf-design-and-verification.md) — 性能基准体系设计方案
- [`datasource-matrix.md`](datasource-matrix/datasource-matrix.md) — 数据源可用性矩阵实现记录
- [`tiantian-split.md`](tiantian-split/tiantian-split.md) — tiantian.py 大文件拆分记录
- [`fundstyle-split.md`](fundstyle-split/fundstyle-split.md) — fund_style_analysis.py 大文件拆分记录

## v0.8.10 已完成项

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| plan-12 | **错误友好提示/数据源可用性矩阵** | `data_source_matrix.py` 实现，作为报告章节 #17（always 类型页签）输出，在数据源不可用时给出友好提示 | 2d | ✅ 已完成 |
| plan-13 | **数据源可靠性文档** | 8 类数据源可靠性详表 + 降级路径 + 限流规则 + 历史故障 | 1-1.5d | ✅ 已完成 |
| plan-14 | **架构决策记录（ADR）** | ADR 目录/模板 + 补写 5-8 个关键决策 + 流程固化 | 2.5d | ⏸ 已搁置 |
