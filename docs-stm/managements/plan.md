# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：0.9.11

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P0 — 发布门禁

（待排期）

### 推荐实施顺序

> 结合架构约束、收益/风险与最新依赖状态重排的推荐实施次序。①~③ 为推荐先后；括号内为计划项原有优先级归类（P3=预期实施）。plan-4 已放弃，不列入实施序列；

| 次序 | 计划项 | 归类 | 工作量 | 推荐理由 |
|:--:|:--|:--:|:--:|:--|
| ① | **plan-10** 日志可视化 | P3 | 1d | 独立低风险 |
| ② | **plan-8** 轻量 Web UI | P3 | 5-6d | 运维+安全成本最高，单人工具需谨慎，建议最后 |

> ✅ plan-11 **HTML 暗色模式**已实施完成（v0.9.11），详见 [`archive/v0.9.x/dark-mode/dark-mode-implementation.md`](../archive/v0.9.x/dark-mode/dark-mode-implementation.md)。
> ✅ plan-12 **组合演进纳入报告可选环节配置**已实施完成（v0.9.11）：新增独立开关 `enable_portfolio_evolution`（默认开启），控制 #19 组合演进章节显示/隐藏，与历史走势开关互相独立。

### P2 — 高级分析（已结项）


| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| ~~plan-4~~ | ~~**业绩归因（Brinson 分解）**~~ | ~~单期 Brinson（配置+选股+交互）+ 多期平滑 + 基准选择~~ | ~~4d~~ | ❌ **已放弃** — 3/4 关键数据源不可突破：① 行业指数 K 线不稳定 ② 无免费基准行业权重 ③ 非 A 股品种无行业归属。详见 `archive/v0.7.x/better-investment-advice/discussion-better-investment-advice.md` §4.2 不做清单 |

### P3 — 用户体验改进

> **P3** = 预期实施，有空时安排。待办项按推荐实施顺序排列（见上方总览）。

#### `plan-10` 日志可视化（[`plan-web-ui.md §3`](../plan/plan-web-ui.md#3-日志可视化)）— **推荐①**

结构化日志查看（`--view-logs` 命令 + 报告尾部数据源状态表）。**预估：1d**

#### ~~`plan-11` HTML 暗色模式~~ — ✅ **已完成（v0.9.11）**

CSS 变量 + localStorage 切换按钮（右上角浮动，首次默认浅色）。实施记录：[`archive/v0.9.x/dark-mode/dark-mode-implementation.md`](../archive/v0.9.x/dark-mode/dark-mode-implementation.md)

#### ~~`plan-12` 组合演进纳入报告可选环节配置~~ — ✅ **已完成（v0.9.11）**

组合演进（#19）原为 `always` 类型始终显示，现改为独立 `evolution` 类型，由新增配置项 `enable_portfolio_evolution`（默认 `true`）控制 board 层可见性。与 `enable_fund_deep_analysis`（#6~11）、`enable_history`（#17~18）相互独立：关闭历史走势开关不影响组合演进，反之亦然。持仓快照始终自动记录，开关仅影响报告展示。菜单 `P` 新增第 4 项切换。

#### `plan-8` 轻量 Web UI（[`plan-web-ui.md §1`](../plan/plan-web-ui.md#1-轻量-web-ui)）— **推荐②**

Flask/FastAPI + 上传页面 + 触发管线 + 结果预览/下载。MVP 不做多用户/LLM 在线修改/实时日志流。**运维与安全成本最高，单人工具需谨慎，建议作为 P3 最后项。**

| 阶段 | 工作量 |
|------|:------:|
| MVP 核心 | 3d |
| 功能补齐 | 1.5d |
| 体验打磨 | 1d |

### P4 — 实验功能

> 实验性功能，缺省关闭，需通过配置项或 features.json 显式启用。启用不影响现有功能稳定性。当前无排期项。

---

## 归档

- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
