# 投资复盘助手 — 实现计划
> 文档版本：0.12.2-dev
> **编号源**：`plan-next = 75`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-74，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：在办 **plan-49 / plan-55**（用户侧待条件满足）；P3 纪律项 **plan-70/71**（实验功能撤销死线/转正判据，观测手段本批已落地）。TradingAgents-CN 借鉴批已收口：plan-59~65 完成、plan-66~68 归档未采纳（详见下方 P3/P4 说明与归档文档）。

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
4. 七个 `--ci` 守护脚本 + `--mode verify,regression` + ruff + 版本一致性全绿。

**转正动作**：`features.py` 声明从 `GROUP_EXPERIMENTAL` 改 `GROUP_STANDARD` 且 `default=True`（`affects_report` 照实 `True`）；同步 `requirements.md`/`how-to-config.md`（分组计数）、`test_features.py` 转正用例、changelog；**不改评分口径**。

**当前结论**：**暂不转正**（保持实验组默认关；用户 `features.json` 已手工开启，功能可用）。

#### 🔲 `plan-55` 新闻关联判定接入 Jev（对照评测先决）

**动机**：该模块的关联度/情绪判定属典型**窄判断**（批量、选项有限、需校准概率），恰是 Jev 类型化判定接口的适用场景；而其他四个模块是长文生成，不适用。

**先决门槛（未过不接入）**：按 `docs/plan/jev-news-correlation-evaluation.md` 跑三方对照（关键词确定性 / 现网生成模型 / Jev），预注册阈值见该文档判定表。**未达阈值则归档为已评估未采纳。**

**预检已确认的三条约束**（回收 48 条现网判定得出）：
1. `relevance` 已饱和（77% 标「高」、0% 标「无关」）→ 评测主指标改取 `sentiment`（利好 48% / 中性 40% / 利空 12%）；
2. 「无关」占比 0% → **「先用判定预筛、再削减生成侧输入」的动机被证伪**，两段式方案剔除；
3. 理由文本中位仅 23 字且为「主体 + 方向」型 → 可改由**确定性模板**渲染（不新增模型调用）。

**待评测结论确认后再实施的部分**：见 `docs/plan/jev-news-correlation-design.md`（独立于对话链的类型化判定通道、问项版本参与缓存指纹、五键类型化通道下不读取、失败降级矩阵）。

**约束与红线**：① 不得作为用户可选的对话模型（该模型不生成文本）；② 不得做成「生成 + 判定」双供应商级联（无信息增量且多一个中间失败态）；③ 语料含真实持仓与新闻，冻结产物必须落 `docs/tmp/`（git 忽略），仅脱敏样例可入库；④ 类型化通道故障不得拖垮生成链（熔断实例分离）；⑤ 新增配置键须按开关注册表统一纪律登记，默认值保持 `chat` 使缺省行为逐字节不变。

**预估成本**：低（评测脚本 + 模板渲染 + 一个独立客户端模块）；**价值**：中（仅影响一个出厂默认关闭的模块，收益以「更稳的解析 + 可校准概率」为主，不以成本节约为卖点）。

### P3 — 预期实施，有空时安排

> **本批 P3 已清空**。源 TradingAgents-CN 仓库研究的 10 项候选（详细分析见 [`tradingagents-cn-borrow-candidates-research.md`](../archive/v0.11.x/tradingagents-cn-borrow-research/tradingagents-cn-borrow-candidates-research.md)）中 plan-59 ~ plan-65 已完成（2026-10-01）：前四项见 [`archived_plan.0.11.x.md`](../archive/v0.11.x/archived_plan.0.11.x.md)，plan-63/64/65 见同文档「LLM 成本调节 / 生成后自检 / 调用级源指定」段；整体设计见 [`report-depth-selfreview-source-override-design.md`](../archive/v0.11.x/llm-depth-selfreview-source-override/report-depth-selfreview-source-override-design.md)。
>
> 剩余 P4 三项（plan-66 ~ plan-68）仍为候选；**立项前须先做本仓库现状比对**（rf-510 教训：plan-64 原立项前提「无生成后质检」即被 `llm/fact_checker` 既有实现部分推翻，最终按「分层不重叠」重新定位）。

> **plan-72 已完成归档**（2026-10-03）：本期迭代 1~3（数据链路 → 展示集成 → 文档登记）P0 门禁十项全绿完成（手工真实抓取验收 HTTP 200 / 27,695 行 / `purchase_schema=1`），完成态见 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；迭代 4（合并/调仓联动）另立 `plan-74`，设计文档保留在在办区供其消费 §6/§8。

#### 🔲 `plan-73` 限购信息接入 LLM 分析维度（智囊团复盘 / 穿透深析提示词扩展）

**动机**：plan-72 落地的申购限购数据（`purchase_status_data` 契约：申购状态 / 日累计限额 / 下一开放日 / 数据时效）目前只服务持仓展示与（二期）合并联动；分析类章节的提示词不含该维度——智囊团深度复盘、穿透深度分析在评估 QDII / 场外基金的加仓、合并与配置建议时，看不到「目标基金限大额 / 暂停申购」这一**可执行性硬约束**，可能给出实际下不了单的建议（与合并联动同一风险面，落在文本分析维度）。

**前置**：plan-72 迭代 2 完成（`purchase_status_data` 契约注入 pipeline 后才有稳定数据可传）。

**动作**：**本期只出设计文档**到 `docs/plan/`（同 plan-72 流程，2026-10-03 用户决策：先评审后实施）。设计文档需定清：

1. **注入范围 = 全部 LLM 分析章节**（用户确认，2026-10-03）：智囊团深度复盘（`_build_expert_review_prompt`）与穿透深度分析（`_build_penetration_deep_prompt`）为首批点名对象，行动建议 / what-if 等其余分析章节逐一盘点接线点，全部复用**同一份确定性摘要渲染**（单源，不逐章各写一份）；
2. **数据完备时**（契约 `available=true` 且开关 `fund_purchase_limit` 开）：以**确定性模板**渲染限购摘要（仅限大额 / 暂停申购的持仓：代码、状态、日限额、下一开放日 + 天天基金渠道口径声明），注入各章用户提示词；
3. **数据不可用 / 开关关 / 时效超限 → 提示词逐字节不变**（降级零影响，与展示层同口径；绝不因数据缺失让 LLM 猜测限购状态）；
4. 不新增模型调用、不建平行配置路径（开关复用 `fund_purchase_limit`）；prompt 变更对**模块指纹 / 缓存指纹**的影响按指纹唯一事实来源纪律处理，避免无谓全量重算或缓存失配。

**预估成本**：低~中（一个确定性摘要渲染函数 + 两处 prompt 接线 + 单测）；**价值**：中（补齐分析建议的可执行性维度，QDII 限购是高频现实约束）。

**产出**：设计文档 [`docs/plan/fund-purchase-limit-llm-context-design.md`](../plan/fund-purchase-limit-llm-context-design.md)（2026-10-03 提交，含现状比对/单源渲染/统一附录注入/指纹与降级矩阵/迭代拆分，**待评审**）；迭代实施按设计 §6 的**四迭代可验收结构**（渲染器+契约 → 主路径+指纹 → 覆盖面核验 → 文档门禁，每迭代独立出口检查与回滚）。

**进度**：2026-10-03 设计完成，待评审；评审通过后按设计 §6 迭代 1→4 实施。

> **plan-74 已完成归档**（2026-10-03）：四迭代（受限索引与判定原语 → What-if 接线 → 回归网与零改动断言 → 文档登记）P0 门禁十项全绿完成；What-if 目标持仓申购受限提示落地（`restricted_index` 契约字段 + `evaluate_purchase_feasibility` 判定 + Excel/HTML 双端提示块，降级态逐字节回退）。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；设计文档 [`fund-purchase-limit-advice-design.md`](../plan/fund-purchase-limit-advice-design.md) 已改「设计 + 已实施」随归档留存。

#### 🔲 `plan-70` 决策跨期反思闭环（decision_reflection）验证死线

**动机**：实验功能默认靠「真实数据验证后择机转正」，但 decision_reflection 的真实账本积累极少，闭环从未被真实数据跑通；长期挂着默认关的开关是纯维护成本。

**动作**：在后续 2 个发布周期内（以 experiment_stats 启用计数与账本结算数为准）观察，若：① experiment_stats 中 decision_reflection 的启用次数未增长，或 ② `data/state/decision_ledger.jsonl` 已结算样本仍 <10 条（折叠统计 direction_accuracy 无法给出可信命中率），则撤销该实验功能（含 LLM 决策登记（`decision_llm_capture`）/行动章复盘块注入与对应需求条目）；若满足可信样本则据 doctor 账本概览评估转正。观测手段已就绪：`experiment_stats` 启用计数 + `doctor` 复盘账本概览（本批落地）。

#### 🔲 `plan-71` 景气度框架诊断（prosperity_framework）转正判据明确化

**动机**：当前最重的实验功能（六维评分卡 + 基金层扩展），声明「需真实组合样本验证评分口径」但无可判定的验收条件，转正遥遥无期。

**动作**：定出可判定的转正条件（拟：① 六维中至少 5 维在真实持仓报告中有非「需核实」数据覆盖；② 评分结论经 1 个发布周期的真实复盘认可与人工比对无显著偏差；③ experiment_stats 记录的启用次数足够支撑观察），满足后按「转正 = 改注册表分组与默认值」流程执行（需求条目 R-PF 同步）。执行需采集用户真实复盘反馈，持用户确认后再动。

## 归档

- [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md) — v0.12.x 已完成项
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
