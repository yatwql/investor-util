# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.7.3

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

> 归档版本按从新到旧排列：

- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md) — v0.6.0 ~ v0.6.7
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md) — v0.5.0 ~ v0.5.12
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md) — v0.4.0 ~ v0.4.5
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md) — v0.3.0 ~ v0.3.10
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md) — v0.2.0 ~ v0.2.91
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md) — 早期版本记录

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P2** = 当前待办

### P0 — 发布门禁

（待排期）

### P2 — 基础设施前置 + 快速可见（Tier 0 + MVP）

> ✅ **全部完成（2026-07-20）**。10 项 P2 任务均已完成并测试验证通过（regression 266 passed, 0 failed）。
> 详细变更记录见 `changelog.md` v0.7.3。


### P4 — 基础设施改善

| 序号 | 任务 | 状态 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **加密 API 密钥存储** | 待处理 | 4 小时 | 当前 `llm_key.json` 明文存储 API 密钥。改用对称加密（`cryptography.fernet`），运行时解密进内存。KEK 从环境变量 `INVESTOR_UTIL_KEY` 读取，首次使用自动生成并提示用户保存。包含加密/解密函数、存量密钥迁移脚本、启动时解密失败回退提示。独立于 better-investment-advice，为通用基础设施改善项。 |
