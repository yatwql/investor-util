# 投资复盘助手 — 实现计划
> 文档版本：0.12.5-dev
> **编号源**：`plan-next = 84`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-83，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：在办 **plan-49 / plan-55 / plan-83**（用户侧待条件满足）；P3 纪律项 **plan-70/71**（实验功能撤销死线/转正判据，plan-70 已有落地设计 `decision-reflection-shadow-design.md`）；**Vibe-Trading 借鉴批：plan-76/77/78/81 已完成归档（先决门槛全过；plan-76/77 四迭代落地、plan-78 三指标评测判定转正立项 → plan-81 转正实施落地）**（持仓变动复盘 / What-if 回放成本与基准 / 因子目录评测与实施，均带先决门槛，详见 `docs/plan/vibe-trading-borrow-candidates-research.md` 与各设计文档）；**gs-quant 借鉴批：plan-79/80 已完成归档（先决门槛三段全过、四迭代落地）**（事件窗量化对照 / 调仓纪律回放，均带先决门槛，详见 `docs/plan/gs-quant-borrow-candidates-research.md`）；**工程效能批：plan-82 已完成归档**（流程耗时优化：收尾触点清单、顺序依赖二分工具、执行纪律修订）。TradingAgents-CN 借鉴批已收口：plan-59~65 完成、plan-66~68 归档未采纳（详见下方 P3/P4 说明与归档文档）。

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

> **plan-77 已完成归档**（2026-10-05）：四迭代（`trade_cost_model` FIFO 批次成本模型 + 费率表选档下沉 `fee_schedule_model` → 费率数据三级可得性（`fund_fee` 链 F10 → akshare 备链 → 过期缓存 + 申购状态表手续费列 + `fund_fee_fallback` 配置兜底）→ `benchmark_index_resolver` 三阶基准映射 + `whatif_cost_panel` 双端面板（Excel 第 5 页签 + HTML⑧ 区，开关 `whatif_trade_cost` 默认关）→ 回归网与文档同步（关态 sha256 黄金断言/换手翻转/双端一致））P0 门禁全绿；先决门槛三段全过（抽样 20 只经真实链路复测两费率侧均 **95% ≥ 80%**、交易日口径与 FIFO 首见日下界三项经用户拍板、30% 换手 ×≈19.5bp 翻转案例人工复核入网）。需求 **R-WIF-12~14**、开关 31 项（实验 5）、TUI 12-28 号。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；设计文档 [`whatif-cost-benchmark-design.md`](../archive/v0.12.x/whatif-cost-benchmark/whatif-cost-benchmark-design.md) 为「已实施」状态随归档留存（含 §14 门槛与验收记录）。

#### 🔲 `plan-70` 决策跨期反思闭环（decision_reflection）验证死线

**动机**：实验功能默认靠「真实数据验证后择机转正」，但 decision_reflection 的真实账本积累极少，闭环从未被真实数据跑通；长期挂着默认关的开关是纯维护成本。

**动作**：在后续 2 个发布周期内（以 experiment_stats 启用计数与账本结算数为准）观察，若：① experiment_stats 中 decision_reflection 的启用次数未增长，或 ② `data/state/decision_ledger.jsonl` 已结算样本仍 <10 条（折叠统计 direction_accuracy 无法给出可信命中率），则撤销该实验功能（含 LLM 决策登记（`decision_llm_capture`）/行动章复盘块注入与对应需求条目）；若满足可信样本则据 doctor 账本概览评估转正。观测手段已就绪：`experiment_stats` 启用计数 + `doctor` 复盘账本概览（本批落地）。

**落地设计**：若判定转正，按 [`decision-reflection-shadow-design.md`](../plan/decision-reflection-shadow-design.md) 四迭代执行（决策条目结构化 → 到期结算器 → doctor 概览增强 → 报告内反思块），该设计以 Vibe-Trading `shadow_account`（extract→backtest→render）为参照；死线未过前不实施。plan-76 持仓变动复盘落地后与其构成「意图 vs 成交」对账（只读，不互写）。

> **plan-78 已完成归档**（2026-10-06）：先决门槛即评测本体，评测脚本 `scripts/factor_zoo_eval.py` 五阶段（目录冻结 → 字段可得 → 信号相关 → 耗时基线 → 判定汇总）实测三指标全过——**A 23/25 = 92% ≥ 80%、B 19/23 = 82.6% ≥ 30%（分母 23 ≥ 10，`rebalance_overflow` 族按设计降级）、C 冷启动 12.831s ÷ 报告基线 446.255s = 2.9% ≤ 20%** → **判定：转正立项**（评测产物 `docs/tmp/factor-zoo/`，判定书口径预注册与复算说明）；25 因子五族目录与门槛口径冻结于设计文档，40 项脚本单测入网；设计文档 [`factor-zoo-catalog-design.md`](../archive/v0.12.x/factor-zoo-catalog/factor-zoo-catalog-design.md) 为「已评测·判定转正立项」状态随归档留存（含 §13 判定记录）。实施转 **plan-81**；评测期自审 rf-591（对数市值非有限值）已修复、rf-592（push2 扩展字段空值待复核）挂待处理。

> **plan-79 已完成归档**（2026-10-06）：先决门槛三段全过（① 日期可用率 **100%（22/22）≥ 80%**；② 严格 ±5 单源口径经 8 例窗口越界降级实证、半窗截断否决；③ 真实链路采样 10 例人工比对 **9/10 ≥ 7**，用户判定通过）；四迭代落地（`event_window_impact` 纯计算 → `event_impact_panel` 事件表编排 → 报告双端 + LLM 注入 → 文档与门禁）P0 门禁全绿。分歧例块经**统一 prompt 附录**随四模块+辩论+自检携带（开关开启时新闻先行串行注入，解决「极性由 LLM 产出、同轮须进 LLM」的鸡生蛋）；关态逐字节回退、隐藏章不消耗连续编号。开关 **32 项（实验 6）**、TUI 实验段 **8~13**、报告章节序列新增 `event_impact` 章（附录三项顺延）。自审 **rf-594**（Web 面板配置项表实验行缺 whatif 与编号段陈旧）已修复、**rf-593**（`debate_procon_fingerprint` 未并入统一附录块，pre-existing）挂待处理。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；设计文档 [`event-window-impact-design.md`](../archive/v0.12.x/event-window-impact/event-window-impact-design.md) 为「已实施」状态随归档留存（含 §14 判定记录）。

> **plan-82 已完成归档**（2026-10-06）：耗时分析定位主因为「触点数 × 往返轮次」（门禁机器时间 <3%）；四项落地——① `CLAUDE.md` 执行纪律修订（红线随每批代码跑 / **编辑与 `--sync`/检查永不同批**防竞态 / **提交前免重复十守护**，pre-commit 钩子内含 `--sync`+十守护 / **收尾一次性枚举全量 finding 批量修**）；② `developer-guide.md`「计划收尾：文档触点清单与一次性枚举」（按任务类型列触点全集 + 三步工作流）；③ `scripts/find-order-dependent-test.py` 顺序依赖污染源二分（单跑确认 → 复现门 → 记忆化前缀二分 → 配对确认/预算内精简，22 项单测含端到端）；④ guard 测试写死派生量全仓审计（12 处命中均为合成夹具/固定内容/结构不变量，无遗留）。不降低任何检查强度，完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)。

> **plan-81 已完成归档**（2026-10-06）：按设计 §3 语义命名落地四组件——`schemas/factor_catalog.py`（25 条五来源族冻结目录 + 中性点字典 + 字段类型路由，装载前完整性校验）、`fetcher/factor_catalog_loader.py`（装载校验拒载降级 + 四类输入备数逐类型失败入 unavailable 不外抛）、`analysis/_factor_formulas.py`（25 因子公式纯计算原语，无 I/O）、`analysis/factor_evaluator.py`（池构造：直接持仓 ∪ 穿透 A 股 → 逐因子池内横截面 → 中性相对与评级，全链 fail-soft）；`signal_ledger` 第 6 类 `factor_catalog`（「因子目录」，每日单条组合级快照）+ 报告呈现「风格与因子分析」章内**区块四**（Excel `_write_catalog_block` + HTML 模板块同源三态，关态产物逐字节不变）。开关第 33 项入实验组（实验 7），TUI 实验段 8~14、后续编号顺延；需求 **R-FCT-01~05** 入 §6.14、testplan 批 9 载体、三个新测试文件 + 四个既有文件用例扩充。前置 rf-592 复核结论入档（源侧字段策略变更 + 端点断连两次实测，`fund_pb`/`fund_size_log_cap` 判不可得-降级、目录条目保留待源恢复，归档已解决）。

> **plan-80 已完成归档**（2026-10-07）：先决门槛三段全过（① 指标原语复用核对 ≥3 处——LOCF/归一/指标/日历经 `whatif_backtest` 公共出口与 `metrics*`/`trading_calendar` 复用，零新造引擎；② 成本软依赖 `trade_cost_model` 声明并落地两态（可得逐笔 FIFO 计入 / 不可用「未计成本」双回显）；③ 真实样例 2 组——支付宝场外账户 7 只近 12 个月回放（A 月度定期 37.16% / B 阈值 5pp 38.78% vs 买入持有 32.85%，夏普 1.25/1.27 vs 1.14，缺口 ≤0.4%），用户判定「有启发、想持续看」）；四迭代落地（`replay_schedule` 契约与 `schedule_replay` 回放纯计算 → 成本软接入 → `schedule_replay_panel` 双端面板 + LLM 统一附录引用段 → 文档与门禁）P0 门禁全绿（`dev-verify` 5868 passed、十守护 0 finding）。开关 **34 项（实验 8）**、TUI 实验段 **8~15**、报告章节序列新增 `schedule_replay` 章（附录三项顺延至 18/19/20，隐藏章不消耗连续编号）。需求 **R-SR-01~05**、测试 58 项新用例 + 19 处既有同步。完成态并入 [`archived_plan.0.12.x.md`](../archive/v0.12.x/archived_plan.0.12.x.md)；设计文档 [`rebalance-schedule-replay-design.md`](../archive/v0.12.x/rebalance-schedule-replay/rebalance-schedule-replay-design.md) 为「已实施」状态随归档留存（含 §14 实施与门槛判定记录）。

#### 🔲 `plan-83` 章节类实验转正批次（holding_change_review / whatif_trade_cost / event_window_impact）

**动机**：三项章节级实验（plan-76/77/79 落地）先决门槛均已过审，但 `experiment_stats` 无真实报告启用记录、按「启用次数支撑观察」判据不足以转正；且旧转正定义对章节类形态过于激进（实验组转常规组即默认永远出章）。

**动作**：转正定义已扩展为「**移出实验组、目标组按功能形态选**——常驻读侧增强→常规组（默认开），章节/页签类→报告章节与增强组（默认关、按需开）」（注册表注释与三份手册同步）；待真实报告启用积累且用户确认产物质量后，三项分批执行注册表迁移（每批一次注册表改动 + TUI/Web 编号与分组行、`--experiment` 取值域、报告自述与需求条目同步；转正后产物自述与启用统计随实验组身份移除）。

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
