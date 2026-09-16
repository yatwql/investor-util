# 投资复盘助手 — 实现计划
> 文档版本：0.11.1-dev
> **编号源**：`plan-next = 50`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-49，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）**已全部完成并发布**（P1 轮 1~11 + 阶段 D~G 轮 12~20，plan-17~plan-24，changelog v0.10.1/v0.10.3/v0.10.4）。详细设计、实施轮次、推荐实施顺序与发布门禁记录见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)（含设计文档索引：`plan-investment-features.md` 设计层 §4 章节归并方案与 §4.4 架构合规自查表 + `plan-investment-iteration.md` 实施层 21 轮每轮量化验收 + 已完成项摘要表 + 推荐实施顺序 ①~⑧ + P0 发布门禁记录）。本文档当前在办 **plan-47 / plan-48 / plan-49**（均源自 plan-46 真实持仓复核与降级矩阵的剩余项，非阻塞）；P1 区已完成 plan-42 / plan-43 / plan-44 / plan-45 / plan-46；仅保留待办登记区与归档引用；v0.10.x 已完成项（plan-8、plan-17~plan-43）见 `archived_plan.0.10.x.md`，v0.11.x 已完成项（plan-44 / plan-45）见 `archived_plan.0.11.x.md`。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P1 — 当前待办

> 无待办项（plan-42 / plan-43 摘要见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)；plan-44 / plan-45 摘要见 [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md)，plan-45 的设计与实施层文档见 [`archive/v0.11.x/section-consolidation/`](../archive/v0.11.x/section-consolidation/)）。


#### ✅ `plan-46` 景气度框架诊断（借鉴 zhengxi-views 的投资分析方法，实验性功能）— 已实施（2026-09-16）

**动机**：上游 `zhengxi-views`（郑希观点库，MIT）把一位主动权益基金经理公开表述的方法蒸馏为「可操作流程 + 六维评分卡」。本项目只借鉴其**可计算骨架与评分口径**，转成对本仓持仓组合的诊断（不引入其语料/快照/检索）。

**方案**：新增实验性功能开关 `prosperity_framework`（默认关）+ 纯计算模块 `analysis/prosperity_framework.py` + 数据契约 `prosperity_framework_data`（数据契约台账）+ 行动建议章内嵌块（HTML/Excel）；六维 = 景气方向/通胀属性 25 + ROE 低位弹性 20 + 全球视野/中国比较优势 15 + 流动性 10 + 集中度与周期拼接 15 + 业绩与回撤印证 15；数据缺失维度独立降级进 `unverified`（不臆造得分）。

**不做**：不引入上游语料与基金快照、不做全市场基金检索/对比、不新增 LLM 调用、不新增外部数据源、不改变既有章节输出（开关关 → 零字节变化）。

设计文档：[`prosperity-framework-design.md`](prosperity-framework-design.md)（含上游归属与许可、数据映射、六维口径、契约结构、约束对照、测试与文档同步清单、验收标准）；实施层施工单见后续迭代文档。

**降级矩阵（实施后真实场景复核，2026-09-16）**：6 个场景（交易日基线 / 非交易日行情全零 / `history` 关闭 / 基本面契约缺失 / 关基金深度分析 / 快照 <2 期）均**报告生成成功且块始终渲染**，降级语义正确——非交易日：①③→0、④ `unverified`、总分 1/55；`history` 关闭：⑥ `unverified`（38/65，不崩）；快照 <2 期：⑤ `partial`（换手子项不计分，41/80）；其余场景与基线一致。**设计文档归档**：待 v0.11.1 发布时按惯例迁入 `docs-stm/archive/v0.11.x/`。

#### 🔲 `plan-47` 景气度框架诊断：基金持仓 ROE 加权（扩展 ② 维覆盖率）

**动机**：② ROE 低位弹性当前只覆盖 **A 股个股**（用户组合实测 21.91% 权重：长江电力/工行/建行/广发多因子），基金/ETF/QDII/债基无个股 ROE → 其余权重标「需核实」不计分。

**方案**：对基金持仓按其**重仓股 ROE 加权**（需先具备**全量穿透**能力：现穿透层仅保留 top10 底层，需扩展为按基金聚合全量持仓或新增独立取数路径），再对底层股票批量取基本面（`providers/akshare_financial` 支持一条调用多股）。

**约束与红线**：① 新契约字段须进数据契约台账 + 附录 H + 双端一致性测试；② 属**推演**而非方法原话（框架原意是选股层面的 ROE 弹性）→ 渲染文案必须标「按框架推演」；③ 不得因该扩展影响既有章节输出（开关关闭时零变化）。

**预估成本**：中高（穿透层扩展 + 新契约 + 报告耗时 +几秒）；**价值**中（②覆盖 21.9% → 60~80%）。

#### 🔲 `plan-48` 景气度框架诊断：场外流动性补齐（④ 维）

**动机**：④ 流动性当前只有场内 4 只可算（`check_liquidity` 近 20 日成交额），场外 4 只因未配 `redemption_limits` 标「场外基金」、6 只成交额缺失按「流动充足」假设降级。

**方案**：① 在 `config.json` 的 `redemption_limits` 提供用户可填的单日赎回上限（文档已述，属配置项）；② 或对场外品种给出**类型分级默认档**（货基/短债 T+0~T+1、纯债 T+2、QDII T+3~T+7），使该维在场外为主时有区分度。

**约束**：类型分级须走 `core/code_utils`（类型判定中心化），且默认档位须在证据中标注为「类型默认档（非实测）」。

#### 🔲 `plan-49` 景气度框架诊断：转正评估（默认开启）

**前置条件（全部满足才转正）**：
1. 降级矩阵全绿（2026-09-16 已达成：6 场景无崩溃、块始终渲染、降级语义正确）；
2. 真实使用样本 ≥2 周，覆盖跨月快照（换手代理）、一次调仓、一次数据降级；
3. 用户确认「评分口径认可」（① 关键词表与 ⑤ 集中度目标 `concentration_target_pct` 是否按自身风格校准）；
4. 四个 `--ci` + `--mode verify,regression` + ruff + 版本一致性全绿。

**转正动作**：`features.py` 声明从 `GROUP_EXPERIMENTAL` 改 `GROUP_STANDARD` 且 `default=True`（`affects_report` 照实 `True`）；同步 `requirements.md`/`how-to-config.md`（分组计数）、`test_features.py` 转正用例、changelog；**不改评分口径**。

**当前结论**：**暂不转正**（保持实验组默认关；用户 `features.json` 已手工开启，功能可用）。

### P4 — 实验功能

> 无待办项（plan-30 ~ plan-41 全部完成，完成项摘要见归档）。

## 归档

- [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md) — v0.11.x 已完成项（plan-44 / plan-45，含 plan-45 设计文档索引）
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
