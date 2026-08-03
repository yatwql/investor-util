# 高级分析功能：业绩归因（plan-4，已放弃）

> **⚠ plan-4 业绩归因（Brinson 分解）已于 2026-07-20 的 feasibility review 中确认放弃。**
> 4 个输入中 **3 个缺口不可突破**：
> 1. ❌ 行业指数 K 线 — 东方财富 BK 指数历史数据不稳定
> 2. ❌ 基准行业权重 — 无免费公开的行业配置权重参考（如沪深 300 行业权重分布）
> 3. ❌ 非 A 股分类 — 场外基金/QDII 无行业归属
> 4. ✅ 品种收益率 — 现有
>
> 详见 `archive/v0.7.x/better-investment-advice/discussion-better-investment-advice.md` §4.2 不做清单。
>
> **替代方案**：概念板块附加分析（已实现，利用 `industry.concepts` 缓存）+ 组合级超额收益（LLM 提示词中已有）。替代方案不做归因分解——概念板块分析回答的是"你投了什么板块"，不回答"超额收益从哪来"。
>
> **📦 已归档**：**plan-7（因子暴露分析）** 已于 2026-08-02 完成并归档至 `../archive/v0.9.x/factor-exposure/plan-factor-exposure.md`（本文档 §4 全部内容已迁移）；**plan-5（调仓 What-if 模拟）/ plan-6（多快照趋势追踪）** 已于 2026-08-03 完成并归档至 `../archive/v0.9.x/whatif-simulation/plan-whatif-simulation.md` 与 `../archive/v0.9.x/portfolio-evolution/plan-portfolio-evolution.md`。本文档仅保留 plan-4（已放弃）内容。

## 目录

1. ~~[业绩归因（Brinson 分解）](#1-业绩归因brinson-分解)~~ — ❌ 已放弃

> 📦 plan-7（因子暴露分析）设计已归档至 [`archive/v0.9.x/factor-exposure/plan-factor-exposure.md`](../archive/v0.9.x/factor-exposure/plan-factor-exposure.md)。
> 📦 plan-5（调仓 What-if 模拟）设计已归档至 [`archive/v0.9.x/whatif-simulation/plan-whatif-simulation.md`](../archive/v0.9.x/whatif-simulation/plan-whatif-simulation.md)。
> 📦 plan-6（多快照趋势追踪/组合演进）设计已归档至 [`archive/v0.9.x/portfolio-evolution/plan-portfolio-evolution.md`](../archive/v0.9.x/portfolio-evolution/plan-portfolio-evolution.md)。

---

## 1. 业绩归因（Brinson 分解）— ❌ 已放弃

### 概述

目前报告只能回答"你赚了/亏了多少钱"，不能回答"为什么"——赚的钱是市场涨了（Beta）？还是选对了行业（配置效应）？还是选对了股票（选股效应）？Brinson 归因将超额收益分解为三个分量。**但以下数据源缺口导致不可实现：**

#### 数据源缺口分析

| 输入 | 所需数据 | 可获取性 | 结论 |
|:-----|:---------|:--------:|:----:|
| 品种行业归属 | 各品种所属行业类别 | ✅ 已有（东方财富 push2 行业分类） | 可用（仅 A 股） |
| 品种收益率 | 各品种在归因期内的收益率 | ✅ 已有（`fetch_history_data`） | 可用 |
| 基准行业权重 | 基准指数中各行业的配置权重 | ❌ 无免费来源 | **不可突破** — 沪深 300 行业权重需 Wind/Bloomberg |
| 行业指数收益率 | 各行业指数在归因期内的收益率 | ❌ BK 指数 K 线不稳定 | **不可突破** — 东方财富 BK 指数免费 API 数据质量低 |

**结论：3/4 关键输入不可获取，Brinson 分解在免费数据源约束下不可实现。**

### 替代方案

已有实现的替代方案见 § 目录上方说明，此处保留原始设计文档供历史参考。

### 收益

- **回答核心问题**：跑赢大盘了吗？超额收益从哪来的？
- **指导调仓决策**：如果配置效应持续为正但选股效应为负，说明行业选对但标的选错了
- **形成完整叙事**：报告中"业绩归因"页签是对"量化指标"页签的最佳补充解释
- ~~**数据已有**：组合持仓权重 + 各品种收益 + 基准指数收益，都是现有数据源~~ → 实际仅部分数据可用

### 风险

- Brinson 模型假设持仓在归因期内固定不变，调仓频繁会引入误差
- 多期归因的连锁效应（Carino / Menchero 平滑算法）实现复杂度递增
- 基准选择对结果极度敏感：沪深 300 归因 vs 全市场归因结论不同

### 工作量估算

| 阶段 | 内容 | 天数 |
|------|------|------|
| 基础模型 | 单期 Brinson（配置+选股+交互） | 1 |
| 多期平滑 | Carino 或 Menchero 算法 | 1 |
| 报告输出 | Excel 页签 + HTML 图表 | 1 |
| 基准选择 | 用户可配置基准指数 + 自动匹配 | 1 |
| **合计** | | **4 天（已放弃）** |

### 实现路径

```
组合超额收益 R_p - R_b
  = 配置效应 Σ(w_pi - w_bi) × (R_bi - R_b)   [行业配重不同带来的收益差]
  + 选股效应 Σ(w_bi × (R_pi - R_bi))         [同行业内选股能力]
  + 交互效应 Σ(w_pi - w_bi) × (R_pi - R_bi)   [交叉效应，通常归入选股]
```
