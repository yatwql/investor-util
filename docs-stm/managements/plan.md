# 投资复盘助手 — 实现计划
> 文档版本：0.11.10
> **编号源**：`plan-next = 70`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-68，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：在办 **plan-49 / plan-55**（用户侧待条件满足）；P3 仅余纪律项 **plan-69**（外部借鉴前置现状比对）。TradingAgents-CN 借鉴批已收口：plan-59~65 完成、plan-66~68 归档未采纳（详见下方 P3/P4 说明与归档文档）。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P1 — 当前待办

#### 🔲 `plan-49` 景气度框架诊断：转正评估（默认开启）

**前置条件（全部满足才转正）**：
1. 降级矩阵全绿（2026-09-16 已达成：6 场景无崩溃、块始终渲染、降级语义正确）；
2. 真实使用样本 ≥2 周，覆盖跨月快照（换手代理）、一次调仓、一次数据降级；
3. 用户确认「评分口径认可」（① 关键词表与 ⑤ 集中度目标 `concentration_target_pct` 是否按自身风格校准）；
4. 四个 `--ci` + `--mode verify,regression` + ruff + 版本一致性全绿。

**转正动作**：`features.py` 声明从 `GROUP_EXPERIMENTAL` 改 `GROUP_STANDARD` 且 `default=True`（`affects_report` 照实 `True`）；同步 `requirements.md`/`how-to-config.md`（分组计数）、`test_features.py` 转正用例、changelog；**不改评分口径**。

**当前结论**：**暂不转正**（保持实验组默认关；用户 `features.json` 已手工开启，功能可用）。

#### 🔲 `plan-55` 新闻关联判定接入 Jev（对照评测先决）

**动机**：该模块的关联度/情绪判定属典型**窄判断**（批量、选项有限、需校准概率），恰是 Jev 类型化判定接口的适用场景；而其他四个模块是长文生成，不适用。

**先决门槛（未过不接入）**：按 `docs-stm/plan/jev-news-correlation-evaluation.md` 跑三方对照（关键词确定性 / 现网生成模型 / Jev），预注册阈值见该文档判定表。**未达阈值则归档为已评估未采纳。**

**预检已确认的三条约束**（回收 48 条现网判定得出）：
1. `relevance` 已饱和（77% 标「高」、0% 标「无关」）→ 评测主指标改取 `sentiment`（利好 48% / 中性 40% / 利空 12%）；
2. 「无关」占比 0% → **「先用判定预筛、再削减生成侧输入」的动机被证伪**，两段式方案剔除；
3. 理由文本中位仅 23 字且为「主体 + 方向」型 → 可改由**确定性模板**渲染（不新增模型调用）。

**待评测结论确认后再实施的部分**：见 `docs-stm/plan/jev-news-correlation-design.md`（独立于对话链的类型化判定通道、问项版本参与缓存指纹、五键类型化通道下不读取、失败降级矩阵）。

**约束与红线**：① 不得作为用户可选的对话模型（该模型不生成文本）；② 不得做成「生成 + 判定」双供应商级联（无信息增量且多一个中间失败态）；③ 语料含真实持仓与新闻，冻结产物必须落 `docs-stm/tmp/`（git 忽略），仅脱敏样例可入库；④ 类型化通道故障不得拖垮生成链（熔断实例分离）；⑤ 新增配置键须按开关注册表统一纪律登记，默认值保持 `chat` 使缺省行为逐字节不变。

**预估成本**：低（评测脚本 + 模板渲染 + 一个独立客户端模块）；**价值**：中（仅影响一个出厂默认关闭的模块，收益以「更稳的解析 + 可校准概率」为主，不以成本节约为卖点）。

### P3 — 预期实施，有空时安排

> **本批 P3 已清空**。源 TradingAgents-CN 仓库研究的 10 项候选（详细分析见 [`tradingagents-cn-research.md`](../plan/tradingagents-cn-research.md)）中 plan-59 ~ plan-65 已完成（2026-10-01）：前四项见 [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md)，plan-63/64/65 见同文档「LLM 成本调节 / 生成后自检 / 调用级源指定」段；整体设计见 [`llm-depth-selfreview-source-override-design.md`](../plan/llm-depth-selfreview-source-override-design.md)。
>
> 剩余 P4 三项（plan-66 ~ plan-68）仍为候选；**立项前须先做本仓库现状比对**（rf-510 教训：plan-64 原立项前提「无生成后质检」即被 `llm/fact_checker` 既有实现部分推翻，最终按「分层不重叠」重新定位）。

### P4 — 实验功能

> **本批 P4 已清空**：plan-66 / plan-67 / plan-68 经现状比对后**全部归档为「已评估未采纳」**（2026-10-01，见 [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md)）——三项立项前提均被本仓库既有实现推翻（辩论模式已含「共识与分歧摘要」、prompt 已有 `system_prompt_*` 配置级整段覆盖、新闻已 5 源聚合 + 去重 + 反向标题检测）。TradingAgents-CN 借鉴批至此整体收口。

### P3 — 预期实施（纪律项）

#### 🔲 `plan-69` 外部借鉴前置现状比对（纪律固化）

**动机**：本轮 10 项借鉴中，plan-64/66/67/68 **四项**的立项前提均被「本仓库已有实现」推翻（勘察才发现），属可避免的往返成本。

**动作**：把「立项前先比对现状」固化为可执行清单，避免下次重复——清单落 `developer-guide.md`「外部借鉴前置比对清单」节（5 条：能力是否已存在 / 部分存在时缺口的语义边界 / 是否已有配置级或开关级替代 / 改动是否触及缓存指纹与已校准输出 / 是否已有真实消费者或需要新消费者），并在 `docs-stm/plan/` 的设计文档开头填写比对结论。

## 归档

- [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md) — v0.11.x 已完成项
- [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md) — v0.10.x 已完成项
- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
