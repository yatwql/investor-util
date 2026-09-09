# 投资复盘助手 — 实现计划
> 文档版本：0.10.16-dev
> **编号源**：`plan-next = 36`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-35，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）**已全部完成并发布**（P1 轮 1~11 + 阶段 D~G 轮 12~20，plan-17~plan-24，changelog v0.10.1/v0.10.3/v0.10.4）。详细设计、实施轮次、推荐实施顺序与发布门禁记录见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)（含设计文档索引：`plan-investment-features.md` 设计层 §4 章节归并方案与 §4.4 架构合规自查表 + `plan-investment-iteration.md` 实施层 21 轮每轮量化验收 + 已完成项摘要表 + 推荐实施顺序 ①~⑧ + P0 发布门禁记录）。本文档当前仅收录**未完成计划项**（P4 实验功能）与归档引用。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P1 — 当前待办

| # | 任务 | 优先级 | 状态 |
|---|------|:------:|:----:|
| **plan-29** | DeepSeek 峰谷定价适配周末全天闲时规则（2026-08-23 官方方案）：工作日高峰时段 09:00–12:00、14:00–18:00 按 peak 价，其余时间（含周末全天）按 base 闲时价。新增 `pricing.weekend_always_idle` 配置（默认 true，可关闭恢复周末按钟点区分），`constants.py`/`pricing.py`/`_llm_settings_defaults.py`/用户 `llm_settings.json` 同步更新，测试与文档同步 | P1 | 完成（2026-08-28） |

### P4 — 实验功能

> **借用探索候选**（借鉴外部仓库 TradingAgents-astock + BruceLanLan/augur 的机制）：当前迭代已完整发布，以下为借鉴评估识别出的可借用点登记，均按 P4 实验级（缺省关闭、需显式启用）暂存，先设计评估后实施。TradingAgents 借鉴评估（2026-08-29）识别 4 条——**plan-30/31/32/33 均已深入分析**；augur 借鉴评估（2026-09-09）识别 3 条——**plan-30 合并评估 + plan-34/35 已深入分析**。分析文档见 `docs-stm/plan/`：`reflection-decision-loop-analysis.md`、`llm-quality-signal-analysis.md`、`augur-borrowing-analysis.md`。语义名为拟用名，落地前须按「先定语义名再设计」复核。已完成实验项见归档设计文档 `docs-stm/archive/v0.10.x/log-visualization/plan-log-visualization.md`（`plan-10` 日志可视化）。
>
> | # | 任务 | 优先级 | 状态 |
> |---|------|:------:|:----:|
> | **plan-30** | 决策跨期反思闭环（借鉴 TradingAgents-astock `agents/utils/memory.py` + `graph/reflection.py` 两阶段延迟反馈 + augur `learning.py`/`registry.py` 预测-真实结果结算）：对判断（含 LLM 看多看空与确定性再平衡/行动建议）不即时评判——当次记作 `pending` 决策；同标的再现时用真实后续行情结算（方向正确率、超额 alpha），产出教训回灌后续分析提示词。合并 augur 借鉴点 #1：结算改**确定性命中率统计**（augur：bullish 需 +2% 才算对、≥3 样本才生效、立即持久化防进程重启丢失、空 context 预测跳过），与 TradingAgents 的 LLM 反思回灌互补可合成一套。语义名（拟）`decision_reflection`。分析见 `reflection-decision-loop-analysis.md` + `augur-borrowing-analysis.md` §建议A。 | P4 | 深入分析中（本条；augur 合并评估） |
> | **plan-31** | 信号预消化（借鉴外部数据层信号文本 `Signal: … (bullish/bearish)` 前缀）：把资金流/涨跌等数值指标在进 LLM 前预消化为带方向标注的一句话信号（净流入=看多…），降低模型读裸数值自行解读的误判率。语义名（拟）`signal_pre_digest`。 | P4 | 深入分析中（分析见 `llm-quality-signal-analysis.md`） |
> | **plan-32** | 模块级质量分级注入（借鉴 `agents/quality_gate.py` A~F 分级——劣级**不阻断不重试**，而是把「降级 C/D/F」说明注入下游模块）：把现有【数据质量降级】披露从数据源侧扩展到 LLM 输出侧，按完整性/一致性给单模块输出分级并透传到后续拼接。语义名（拟）`module_quality_gate`。 | P4 | 深入分析中（分析见 `llm-quality-signal-analysis.md`；同域先例 `rf-295`） |
> | **plan-33** | 决策头结构化 + 确定性解析兜底（借鉴 `bind_structured` schema 输出 + `agents/utils/rating.py` 词边界确定性解析）：评级/决策头先走结构化输出，落空时用确定性规则兜底解析（防"评级静默误判/污染绩效统计"这类隐患）。语义名（拟）`decision_header_parse`。 | P4 | 深入分析中（分析见 `llm-quality-signal-analysis.md`） |
> | **plan-34** | 确定性数值信号沉淀 + live/demo 标签纪律（借鉴 augur `backtest.py` `data_source` 标签 + 排行榜默认 `live_only`）：把我方已有确定性算法评级——市场温度低估/合理/高估、估值分位 tier、尾部风险 VaR、风格因子、再平衡超限——沉淀为可回测记录并附真/合成标签，排行榜/统计默认只算真实，防合成数据冒充真实战绩；与 plan-30 决策记录可合并成一套。语义名（拟）`signal_ledger`。分析见 `augur-borrowing-analysis.md` §建议B。 | P4 | 深入分析中（本条） |
> | **plan-35** | 健壮性三件套（借鉴 augur）：① `safe_num` 全链路数值归一（防 NaN/±inf 污染下游链）；② 数据源失败「错误即 UX」——provider 失败原因进可读 `data_error` 字段、主链路不中断；③ `doctor` 类自检命令（一次性盘点 key/连通性/缓存/路径，复用现有 `check_sources.py`）。语义名（拟）`robustness_suite`。分析见 `augur-borrowing-analysis.md` §建议C。 | P4 | 深入分析中（本条） |

---

## 归档

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
