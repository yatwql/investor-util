# 投资复盘助手 — 实现计划
> 文档版本：0.12.4-dev
> **编号源**：`plan-next = 81`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-80，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：在办 **plan-49 / plan-55**（用户侧待条件满足）；P3 纪律项 **plan-70/71**（实验功能撤销死线/转正判据，plan-70 已有落地设计 `decision-reflection-shadow-design.md`）；**Vibe-Trading 借鉴批：plan-76 已完成归档（先决门槛全过、四迭代落地）、plan-77/78 已立项**（持仓变动复盘 / What-if 回放成本与基准 / 因子目录评测，均带先决门槛，详见 `docs/plan/vibe-trading-borrow-candidates-research.md` 与各设计文档）；**gs-quant 借鉴批已立项：plan-79/80**（事件窗量化对照 / 调仓纪律回放，均带先决门槛，详见 `docs/plan/gs-quant-borrow-candidates-research.md`）。TradingAgents-CN 借鉴批已收口：plan-59~65 完成、plan-66~68 归档未采纳（详见下方 P3/P4 说明与归档文档）。

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

> **plan-72 已完成归档**（2026-10-03）：本期迭代 1~3（数据链路 → 展示集成 → 文档登记）P0 门禁十项全绿完成（手工真实抓取验收 HTTP 200 / 27,695 行 / `purchase_schema=1`），完成态见 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；迭代 4（合并/调仓联动）另立 `plan-74`（已完成归档），设计文档随完成态移入 [`fund-purchase-limit/`](../archive/v0.12.x/fund-purchase-limit/)。

> **plan-73 已完成归档**（2026-10-03）：四迭代（单源渲染器与契约字段 → 主路径四模块接线与指纹 → 辩论/自检/新闻批量覆盖核验 → 文档登记）P0 门禁十项全绿完成；全部 LLM 分析章（标准四模块 + 辩论 pro/con/synthesis + 生成后自检 + 新闻批量）的提示词与缓存指纹同源携带申购限购约束块（`constraint_block` 契约字段，`generate_all_llm` 提取同一实例交统一附录第 4 段），降级态提示词与缓存键双不变。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；设计文档 [`fund-purchase-limit-llm-context-design.md`](../archive/v0.12.x/fund-purchase-limit/fund-purchase-limit-llm-context-design.md) 已改「设计 + 已实施」随归档留存。

> **plan-74 已完成归档**（2026-10-03）：四迭代（受限索引与判定原语 → What-if 接线 → 回归网与零改动断言 → 文档登记）P0 门禁十项全绿完成；What-if 目标持仓申购受限提示落地（`restricted_index` 契约字段 + `evaluate_purchase_feasibility` 判定 + Excel/HTML 双端提示块，降级态逐字节回退）。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；设计文档 [`fund-purchase-limit-advice-design.md`](../archive/v0.12.x/fund-purchase-limit/fund-purchase-limit-advice-design.md) 已改「设计 + 已实施」随归档留存。

> **plan-75 已完成归档**（2026-10-03）：持仓分类汇总（Excel 区块②末列 + HTML 持仓分类表条件列，两端一致）追加「申购状态」——与区块①同一套单源原语（`purchase_column_visible` 判据 / `format_purchase_status_cell` 文案 / `stale_level` 时效），小计与总计行留空，开关复用 `fund_purchase_limit` 不新增；新增 6 用例，P0 门禁十项全绿。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)。

> **plan-76 已完成归档**（2026-10-05）：四迭代（快照事件抽取与契约 + 快照保留 60 → 180 天 → 指标纯计算与意图对账 + `detect_account_reorder` 账户重排双形态识别 → 双端复盘面板接线（Excel/HTML 单源，缺省关态逐字节不变）→ LLM 归因双轨（附录第 5 段随四模块+辩论+自检携带 / 串行模块 `holding_change_review` 写章内归因块））P0 门禁全绿；先决门槛三段全过（28 有效期 / 71 事件 / 结论人工认可「有启发」，10-02 全量清仓→10-03 同名新增判定为**疑似账户结构变更**、不作交易结论）。需求 R-HCR-01~06、测试 88 项。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；设计文档 [`holding-change-review-design.md`](../archive/v0.12.x/holding-change-review/holding-change-review-design.md) 为「已实施」状态随归档留存（含 §15 实施与验收记录）。

#### 🔲 `plan-70` 决策跨期反思闭环（decision_reflection）验证死线

**动机**：实验功能默认靠「真实数据验证后择机转正」，但 decision_reflection 的真实账本积累极少，闭环从未被真实数据跑通；长期挂着默认关的开关是纯维护成本。

**动作**：在后续 2 个发布周期内（以 experiment_stats 启用计数与账本结算数为准）观察，若：① experiment_stats 中 decision_reflection 的启用次数未增长，或 ② `data/state/decision_ledger.jsonl` 已结算样本仍 <10 条（折叠统计 direction_accuracy 无法给出可信命中率），则撤销该实验功能（含 LLM 决策登记（`decision_llm_capture`）/行动章复盘块注入与对应需求条目）；若满足可信样本则据 doctor 账本概览评估转正。观测手段已就绪：`experiment_stats` 启用计数 + `doctor` 复盘账本概览（本批落地）。

**落地设计**：若判定转正，按 [`decision-reflection-shadow-design.md`](../plan/decision-reflection-shadow-design.md) 四迭代执行（决策条目结构化 → 到期结算器 → doctor 概览增强 → 报告内反思块），该设计以 Vibe-Trading `shadow_account`（extract→backtest→render）为参照；死线未过前不实施。plan-76 持仓变动复盘落地后与其构成「意图 vs 成交」对账（只读，不互写）。

#### 🔲 `plan-77` What-if 回放交易成本建模与基准对比（whatif_trade_cost）

**动机**：既有 `whatif_backtest.py` 不计申赎成本（系统性高估调仓收益，持有期越短越严重）、无基准对比面板。参照 Vibe-Trading `factor_costs.py` / `benchmark.py`。

**先决门槛（未过降级或归档）**：① 目标基金费率字段取得率 ≥80%（否则降级为用户配置单源）；② 赎回费 FIFO 逐笔档位口径可判定；③ 成本计入须产生 ≥1 个方向性翻转案例（证明非无感装饰）。开关 `whatif_trade_cost` 默认关、关闭时输出逐字节不变。详见 [`whatif-cost-benchmark-design.md`](../plan/whatif-cost-benchmark-design.md)。

**预估成本**：中；**价值**：中高（修正回测偏差 + 基准参照）。

#### 🔲 `plan-78` 因子动物园目录评测（factor_zoo_catalog）

**动机**：`signal_ledger` 信号源全靠手写注册，边际成本高；Vibe-Trading Alpha Zoo 可借鉴的是「目录+元数据」形态（462 因子五来源族），不是算子代码本身（数据口径不同，移植即埋雷）。

**先决门槛（评测即本文档本体）**：25 个代表因子三项指标——A 字段可得率 ≥80%、B 与既有信号增量 ≥30% 低相关、C 耗时增量 ≤20%；任一不过即归档「已评估未采纳」，评测产物落 `docs/tmp/`。详见 [`factor-zoo-catalog-design.md`](../plan/factor-zoo-catalog-design.md)。

**预估成本**：低（纯评测脚本）；**价值**：中（评测过才谈得上实施）。

#### 🔲 `plan-79` 事件窗量化对照（event_window_impact）

**动机**：新闻关联只有文本/LLM 侧判定，无「事件日前后 N 交易日真实收益」的数据侧互证——LLM 说利好而事件窗为负的分歧点正是复盘最该暴露的，也是 fact_checker 的事实锚。参照 gs-quant `timeseries/event_study.py` 的对齐/切窗/影响度量纯函数拆分（本仓库全仓实测无任何事件窗能力）。

**先决门槛（未过归档未采纳）**：① 新闻日期字段结构化可用率 ≥80%；② 窗口口径（事件日→交易日映射、±5 交易日、基准对齐、LOCF）唯一可判定；③ 10 例样本量化结论与文本判定「方向一致或分歧可解释」≥7（人工比对）。详见 [`event-window-impact-design.md`](../plan/event-window-impact-design.md)。

**预估成本**：中；**价值**：中高（数据×文本互证，复盘可信度下沉）。

#### 🔲 `plan-80` 调仓纪律回放（rebalance_schedule_replay）

**动机**：`rebalance.py` 管「能不能调」、`whatif_backtest` 管「单次调了会怎样」，缺「长期坚持某纪律（定期/阈值触发）会怎样 vs 买入持有」的多期回放——「纪律 vs 放任」的量化回答。参照 gs-quant `backtests/` 的规则触发/成本分层/分期分解语义（只借语义不搬引擎）。

**先决门槛（未过归档未采纳）**：① 指标原语可全量复用 `metrics*`/`whatif_backtest`（不新造引擎）；② 成本联动软依赖 plan-77（未落地则出「未计成本」标注版，不双实现）；③ 2 个真实规则回放样例经用户确认「有启发、想持续看」。详见 [`rebalance-schedule-replay-design.md`](../plan/rebalance-schedule-replay-design.md)。

**预估成本**：中；**价值**：中高（行动建议章获得最有说服力的证据类型）。

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
