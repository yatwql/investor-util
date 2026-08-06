# 个人投资分析报告生成小助手 — 实现计划
> 文档版本：0.10.9
> **编号源**：`plan-next = 25`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-24，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）**已全部完成并发布**（P1 轮 1~11 + 阶段 D~G 轮 12~20，plan-17~plan-24，changelog v0.10.1/v0.10.3/v0.10.4）。详细设计、实施轮次、推荐实施顺序与发布门禁记录见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)（含设计文档索引：`plan-investment-features.md` 设计层 §4 章节归并方案与 §4.4 架构合规自查表 + `plan-investment-iteration.md` 实施层 21 轮每轮量化验收 + 已完成项摘要表 + 推荐实施顺序 ①~⑧ + P0 发布门禁记录）。本文档当前仅收录**未完成计划项**（P4 实验功能）与归档引用。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

**当前无 P0~P3 待办**（v0.10.x 已完成事项记录已整体归档至 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)：P0 发布门禁、推荐实施顺序 ①~⑧、P1~P3 已完成项详细段落）。

### P4 — 实验功能

> 实验性功能，缺省关闭，需通过配置项或 features.json 显式启用。启用不影响现有功能稳定性。**当前实验项**：日志可视化、轻量 Web UI（独立于本迭代，选做，无排期）。

#### `plan-10` 日志可视化（[`plan-web-ui.md §3`](../plan/plan-web-ui.md#3-日志可视化)）

结构化日志查看（`--view-logs` 命令 + 报告尾部数据源状态表）。**预估：1d**

#### `plan-8` 轻量 Web UI（[`plan-web-ui.md §1`](../plan/plan-web-ui.md#1-轻量-web-ui)）

Flask/FastAPI + 上传页面 + 触发管线 + 结果预览/下载。MVP 不做多用户/LLM 在线修改/实时日志流。**运维与安全成本最高，单人工具需谨慎，选做。**

> 详细评估与实施拆分见 [`plan-web-ui-implementation.md`](../plan/plan-web-ui-implementation.md)（收益/风险/架构约束符合性/`src/python/web/` 模块拆分/安全设计/API/测试/实施阶段）。

| 阶段 | 工作量 |
|------|:------:|
| MVP 核心 | 3d |
| 功能补齐 | 1.5d |
| 体验打磨 | 1d |

> **最新代码核查（2026-08-05）**：`src/python/web/` 尚未创建，依赖清单无 flask/fastapi/uvicorn，**无任何代码落地，仍为纯计划状态**。复用基础已确认存在——`report/orchestrator.py` 的 `prepare_report_data`（L61）与 `generate_report`（L717）接口未变，`src/python/cli/cli.py` 已具备 `report`/`cache`/`whatif`/`check-sources` 4 个子命令，Web 层可直接调用管线；架构约束符合性表（plan-web-ui-implementation.md §5）、安全设计（§6）、API 设计（§7）、测试设计（§9）、实施拆分（§10）均已备齐。工作量估算维持不变（MVP 3d + 功能补齐 1.5d + 体验打磨 1d），仍为 P4 选做、无排期。

---

## 归档

- [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md) — v0.10.x 已完成项（plan-17~plan-24，含设计文档索引：投资功能优化/章节归并 + 任务编号门禁）
- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
