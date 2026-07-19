# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.7.3-dev

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

### P2 — 基础设施前置 + 快速可见

> **依赖关系**：
> - 串行链 1：T0-01-A + T0-01-B → T0-01 → T0-02
> - 串行链 2：MVP-01~04（可并行） → MVP-05 → MVP-06
> - 交叉依赖：MVP-02 ← T0-01（概念降级感知依赖 data_degradation）

| 序号 | 任务 | 依赖 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **T0-01-A: DegradationTracker get_log() 接口封装 + record() 注入** | — | **4h** | 审计 4 文件 6 降级点注入 record() + 封装 get_log() 接口 |
| 2 | **T0-01-B: f_context Pre-Schema 文档** | — | 2h | 定义 ~12 个已有管线键 Schema + 初始类型断言 checkpoint |
| 3 | **T0-01: DegradationTracker→LLM 接线** | ←①+② | 4h | 注入 f_context["data_degradation"] |
| 4 | **T0-02: 数据质量告警注入 LLM** | ←③ | 4h | 健康检查 3 类→5 类（缓存在 Phase 4 实现） |
| 5 | **MVP-01: 收益归因计算与注入** | — | 4h | profit 贡献排序注入 LLM |
| 6 | **MVP-02: 概念板块占比注入 LLM** | ←③ | 4h | Top 10 单品概念标注，依赖 data_degradation 做降级兜底 |
| 7 | **MVP-03: 再平衡极简版（硬编码）** | — | **6h** | 单品种超 15% 阈值告警+去重聚合 ⚠️ 禁止导入 report/ 包（C1/P1-22） |
| 8 | **MVP-04: 竞争语境极简版** | — | 8h | 组合 vs 沪深300 收益对比 |
| 9 | **MVP-05: LLM Prompt 整合串联** | ←⑤⑥⑦⑧ | 4h | 5 个段落集中整合到 prompts.py |
| 10 | **MVP-06: 条件推理场景块** | ←⑨ | 4h | 上涨/下跌 20% 分情景建议 |
| | **合计** | | **44h** | 较调整前 -6h（MVP-03 从 16h 降至 6h）+ 2h（T0-01-A 从 2h 升至 4h）= 净减 4h |

### P4 — 基础设施改善

| 序号 | 任务 | 状态 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **加密 API 密钥存储** | 待处理 | 4 小时 | 当前 `llm_key.json` 明文存储 API 密钥。改用对称加密（`cryptography.fernet`），运行时解密进内存。KEK 从环境变量 `INVESTOR_UTIL_KEY` 读取，首次使用自动生成并提示用户保存。包含加密/解密函数、存量密钥迁移脚本、启动时解密失败回退提示。独立于 better-investment-advice，为通用基础设施改善项。 |
