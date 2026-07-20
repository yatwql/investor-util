# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.7.8-dev

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

> 归档版本按从新到旧排列：

- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md) — v0.7.0 ~ v0.7.6
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md) — v0.6.0 ~ v0.6.7
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md) — v0.5.0 ~ v0.5.12
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md) — v0.4.0 ~ v0.4.5
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md) — v0.3.0 ~ v0.3.10
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md) — v0.2.0 ~ v0.2.91
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md) — 早期版本记录

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P4** = 实验功能（缺省关闭，需显式启用）

### P0 — 发布门禁

（待排期）

### P4 — 实验功能

> 实验性功能，缺省关闭，需通过配置项或 features.json 显式启用。启用不影响现有功能稳定性。

| # | 类别 | 实验功能项 | 状态 | 估时 | 阻塞 | 说明 |
|:-:|:-----|----------|:----:|:----:|:----:|------|
| 91 | **LLM策略** | **增强 LLM 策略——从"解读数据"到"模拟辩论"** | 🆕 | 24h | ←LLM管线 | 实验功能（缺省关闭）。3 种改进模式注入 config 控制的 prompt 模板：(1) 多人辩论——白脸/黑脸双 prompt 分轮生成后 LLM 综合；(2) 条件推理——分情景（涨/跌/震荡）给出建议；(3) 反问引导——识别高集中度品种反问用户是否值得。开关位于 `features.json`，缺省 `false`。配置文件见 `discussion-better-investment-advice.md` 第 6 层 |

