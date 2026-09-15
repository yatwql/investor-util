# 投资复盘助手 — 实现计划
> 文档版本：0.11.1-dev
> **编号源**：`plan-next = 46`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-45，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）**已全部完成并发布**（P1 轮 1~11 + 阶段 D~G 轮 12~20，plan-17~plan-24，changelog v0.10.1/v0.10.3/v0.10.4）。详细设计、实施轮次、推荐实施顺序与发布门禁记录见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)（含设计文档索引：`plan-investment-features.md` 设计层 §4 章节归并方案与 §4.4 架构合规自查表 + `plan-investment-iteration.md` 实施层 21 轮每轮量化验收 + 已完成项摘要表 + 推荐实施顺序 ①~⑧ + P0 发布门禁记录）。本文档当前**无在办计划项**（P1 区 plan-42 / plan-43 已完成，P4 区无待办）；仅保留待办登记区与归档引用；v0.10.x 已完成项（plan-8、plan-17~plan-43）见 `archived_plan.0.10.x.md`，v0.11.x 已完成项（plan-44）见 `archived_plan.0.11.x.md`。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P1 — 当前待办

> 无待办项（plan-42 / plan-43 摘要见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)；plan-44 摘要见 [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md)）。


#### 🔲 `plan-45` 报告章节整合（注册表条目 21 → 17，重生成配置模板）

**动机**：注册表条目已有 21 个，其中若干同族/体量很薄/本是另一条目的子视图（市值核算明细与持仓分类同源；持仓关系矩阵与持仓集中度同属「持仓结构」；财报摘要是持仓基本面的叙事层；基金经理变更是基金业绩的子视图）。

**决定（用户）**：不做配置兼容，**重生成 `config.json` 与配置模板**；设计与实施须逐条对照 `technical.md` §8 架构约束。

**方案（保留吸收方主键，被吸收键移除）**：
1. `market_value` 吸收 `category` → 「持仓明细与分类」（两区块；均 `always`）
2. `position_relationship` 吸收 `fund_concentration` → 「持仓结构与集中度」（两区块；同 `type=fund_deep_analysis`；可见性取 OR）
3. `financial_indicator` 吸收 `financial_report_digest` → 「持仓基本面」（两区块；两个功能开关各控一块）
4. `fund_performance` 吸收 `fund_manager` → 「基金业绩分析」（经理变更为可选区块，board 门禁 `enable_fund_deep_analysis`；先例 `candidate_compare`）

**架构要点**：不新增 pipeline_data 键（pipeline_data 契约台账）；可见性模型最小扩展——注册表可选字段 `data_flag_any`（多契约 OR），未声明时行为不变；序号/显示名/页签名全部经注册表（注册表驱动）。

**批次**：① 模型扩展 + 守卫 → ② M1 → ③ M2 → ④ M3+M4；每批一次提交、每批门禁。

设计文档：[`section-consolidation-design.md`](section-consolidation-design.md)（含现状核实、合并方案、约束对照、测试与文档同步清单、批次验收标准）。

### P4 — 实验功能

> 无待办项（plan-30 ~ plan-41 全部完成，完成项摘要见归档）。

## 归档

- [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md) — v0.11.x 已完成项（plan-44）
- [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md) — v0.10.x 已完成项
- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
