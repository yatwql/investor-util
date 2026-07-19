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

> **P0** = 必须完成才能发布 · **P1** = 当前迭代核心 · **P2** = 当前迭代辅助

### P0 — 发布门禁

（待排期）

### P1 — 立项前专项测试（当前迭代核心）

| 序号 | 任务 | 状态 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **PRE-01: Rf 东方财富 datacenter API 稳定性测试** | 待处理 | 1 天 | 验证 `datacenter-web.eastmoney.com RPTBOND_BOND_YIELD_AND_SPREAD` 接口长期可用性（50 次连续请求、24 小时限频测试、7 天连续采样）。结果决定 Phase 1 Rf 走 API 还是手动配置。详见 `better-investment-advice/better-investment-task.md` |
| 2 | **PRE-01-D: PRE-01 决策门** | 待处理 | 0h | 根据测试结果分两支：(1) API 可用→P1-01/P1-02/P1-15 按计划；(2) API 不可用→P1-03 手动配置兜底，释放 28h |
| 3 | **PRE-02: 偏股基金指数 885005 可用性测试** | 待处理 | 4h | 测试 ak share/东方财富/新浪双 API 是否能获取 885005 历史行情，每源 10 次连续测试。MVP 交付后立即执行 |
| 4 | **PRE-02-D: PRE-02 决策与 prompt 分支实现** | 待处理 | 2h | 根据结果实现 prompt 分支：可获取→三列对比表；不可获取→降级说明段落 |

### P2 — 基础设施前置 + 快速可见（当前迭代辅助）

| 序号 | 任务 | 状态 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **T0-01-A: DegradationTracker get_log() 查询接口封装** | 待处理 | 2h | 封装聚合查询接口 + 注入 record() 调用到所有 fetch_with_fallback 失败点 |
| 2 | **T0-01-B: f_context Pre-Schema 文档** | 待处理 | 2h | 定义现有管线键 Schema（~12 键），插入初始类型断言 checkpoint |
| 3 | **T0-01: DegradationTracker→LLM 接线** | 待处理 | 4h | 在 f_context 中注入 `data_degradation` 结构化降级状态 |
| 4 | **T0-02: 数据质量告警注入 LLM** | 待处理 | 4h | 扩展健康检查提示从 3 类→6 类 |
| 5 | **MVP-01: 收益归因计算与注入** | 待处理 | 4h | 品种收益贡献排序注入 LLM |
| 6 | **MVP-02: 概念板块占比注入 LLM** | 待处理 | 4h | Top 10 单品概念板块标注 |
| 7 | **MVP-03: 再平衡极简版（硬编码）** | 待处理 | 16h | 单品种超 15% 阈值告警，含去重聚合 |
| 8 | **MVP-04: 竞争语境极简版** | 待处理 | 8h | 组合 vs 沪深300 收益对比 |
| 9 | **MVP-05: LLM Prompt 整合串联** | 待处理 | 4h | 5 个新增段落集中整合到 prompts.py |
| 10 | **MVP-06: 条件推理场景块** | 待处理 | 4h | 上涨/下跌 20% 分情景建议（原 PD-01 提前） |

### P4 — 基础设施改善

| 序号 | 任务 | 状态 | 估时 | 说明 |
|:----:|------|:----:|:----:|------|
| 1 | **加密 API 密钥存储** | 待处理 | 4 小时 | 当前 `llm_key.json` 明文存储 API 密钥。改用对称加密（`cryptography.fernet`），运行时解密进内存。KEK 从环境变量 `INVESTOR_UTIL_KEY` 读取，首次使用自动生成并提示用户保存。包含加密/解密函数、存量密钥迁移脚本、启动时解密失败回退提示。独立于 better-investment-advice，为通用基础设施改善项。 |
