# 投资复盘助手 — 实现计划
> 文档版本：0.10.16
> **编号源**：`plan-next = 39`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-38，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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

> **借用探索候选**（借鉴外部仓库 TradingAgents-astock + BruceLanLan/augur + OpenBB 的机制）：当前迭代已完整发布，以下为借鉴评估识别出的可借用点登记，均按 P4 实验级（缺省关闭、需显式启用）暂存，先设计评估后实施。TradingAgents 借鉴评估（2026-08-29）识别 4 条——**plan-30/31/32/33 均已深入分析**（**plan-30、plan-31、plan-32、plan-33 已实施完成**，见下）；augur 借鉴评估（2026-09-09）识别 3 条——**plan-30 合并评估 + plan-34、plan-35 已实施完成**；OpenBB Platform 借鉴评估（2026-09-09）识别 3 条——**plan-36/37/38 已深入分析**。分析文档见 `docs-stm/plan/`：`reflection-decision-loop-analysis.md`、`decision-reflection-implementation.md`、`llm-quality-signal-analysis.md`、`augur-borrowing-analysis.md`、`openbb-data-provider-analysis.md`。语义名为拟用名，落地前须按「先定语义名再设计」复核。已完成实验项见归档设计文档 `docs-stm/archive/v0.10.x/log-visualization/plan-log-visualization.md`（`plan-10` 日志可视化）与 `docs-stm/plan/decision-reflection-implementation.md`（`plan-30` 决策跨期反思闭环）。
>
> | # | 任务 | 优先级 | 状态 |
> |---|------|:------:|:----:|
> | **plan-30** | 决策跨期反思闭环（借鉴 TradingAgents-astock `agents/utils/memory.py` + `graph/reflection.py` 两阶段延迟反馈 + augur `learning.py`/`registry.py` 预测-真实结果结算）：对判断（含 LLM 看多看空与确定性再平衡/行动建议）不即时评判——当次记作 `pending` 决策；同标的再现时用真实后续行情结算（方向正确率、超额 alpha），产出教训回灌后续分析提示词。合并 augur 借鉴点 #1：结算改**确定性命中率统计**（augur：bullish 需 +2% 才算对、≥3 样本才生效、立即持久化防进程重启丢失、空 context 预测跳过），与 TradingAgents 的 LLM 反思回灌互补可合成一套。语义名（已落地）`decision_reflection`。分析见 `reflection-decision-loop-analysis.md` + `augur-borrowing-analysis.md` §建议A。 | P4 | 已完成（2026-09-10，默认关闭实验项；实现设计见 `docs-stm/plan/decision-reflection-implementation.md`） |
> | **plan-31** | 信号预消化（借鉴外部数据层信号文本 `Signal: … (bullish/bearish)` 前缀）：把资金流/涨跌等数值指标在进 LLM 前预消化为带方向标注的一句话信号（净流入=看多…），降低模型读裸数值自行解读的误判率。语义名（已落地）`signal_pre_digest`。分析见 `llm-quality-signal-analysis.md`。 | P4 | 已完成（2026-09-10）：**A 缺陷修复（无开关，默认路径生效）**——行业资金流向段改「主力净流入/主力净流出 + 非负量」并按净额分方向排名（原「主力净流入-5,000,000」label 与数值自相矛盾，且数据源无序导致前 5 行无排名语义）；**B 实验增强（`signal_pre_digest` 默认关）**——市场温度/估值分位/尾部风险预消化为 `信号：…` 行注入专家复盘与持仓体检提示词。实现设计见 `docs-stm/plan/signal-pre-digestion-implementation.md` |
> | **plan-32** | 模块级质量分级注入（借鉴 `agents/quality_gate.py` A~F 分级——劣级**不阻断不重试**，而是把「降级 C/D/F」说明注入下游模块）：把现有【数据质量降级】披露从数据源侧扩展到 LLM 输出侧，按完整性/一致性给单模块输出分级并透传到后续拼接。语义名（已落地）`module_quality_gate`。 | P4 | 已完成（2026-09-10）：**A 同域缺陷修复（无开关，默认路径生效）**——`rf-295` `report/_llm_news.py::_submit_llm_future` 漏传 `degradation_events`，致持仓体检第 5 维「数据质量」恒读「今日无降级记录，所有数据源正常」，与专家复盘降级摘要自相矛盾；**B 实验增强（`module_quality_gate` 默认关）**——`report/llm_quality.py` 对 4 个 LLM 模块输出按完整性/篇幅评 A~F，低评级中「内容在但存在缺陷」者（缺章节/偏短）随内容头部注入【内容质量提示】横幅，**只标注、不阻断、不重试、不写回缓存**（内容缺失型已有占位/空内容醒目提示，不叠加）。横幅复用模块 HTML 字符串作载体（与截断标记/缓存命中行同一载体，HTML+Excel 双路径生效）。分析见 `llm-quality-signal-analysis.md` §2 |
> | **plan-33** | 决策头结构化 + 确定性解析兜底（借鉴 `bind_structured` schema 输出 + `agents/utils/rating.py` 词边界确定性解析）：评级/决策头先走结构化输出，落空时用确定性规则兜底解析（防"评级静默误判/污染绩效统计"这类隐患）。语义名（已落地）`decision_header_parse`。 | P4 | 已完成（2026-09-10）：**A 缺陷修复（无开关，默认路径生效）**——决策词解析自子串包含改为带边界纪律的**归一解析器**（`core/decision_header.py`：标签优先 / 长词优先 / 否定守卫 / 复合词左边界 / 二义不猜 / 判不出返 None），`report/decision_llm_capture.py` 改走该解析器，「不建议加仓」「加仓或减仓」「暂不减仓」不再被判成相反方向写入决策账本；**B 实验增强（`decision_header_parse` 默认关）**——专家复盘提示词追加一行受控 JSON 决策头契约，抽取侧优先读结构化头（逐字段归一校验）、失败回落确定性表格解析，两路产物形状统一。缓存指纹读写两侧同调后缀函数。实现设计见 `docs-stm/plan/decision-header-parse-implementation.md` |
> | **plan-34** | 确定性数值信号沉淀 + live/demo 标签纪律（借鉴 augur `backtest.py` `data_source` 标签 + 排行榜默认 `live_only`）：把我方已有确定性算法评级——市场温度低估/合理/高估、估值分位 tier、尾部风险 VaR、风格因子、再平衡超限——沉淀为可回测记录并附真/合成标签，排行榜/统计默认只算真实，防合成数据冒充真实战绩；与 plan-30 决策记录可合并成一套。语义名（已落地）`signal_ledger`。分析见 `augur-borrowing-analysis.md` §建议B。 | P4 | 已完成（2026-09-10）：**A 缺陷修复：本项无**（五类评级输出确定性可复现，无「算错」可修；不制造缺陷凑 A/B 结构）；**B 实验增强（`signal_ledger` 默认关）**——`core/jsonl_store.py` 抽出已被重复两份的原子 JSONL 原语（`perf`/`decision_ledger` 改委托，不新增第三份拷贝）、`core/signal_ledger.py` 账本（登记幂等/折叠统计/**默认 `live_only`**/摘要与缓存后缀/非有限数值归一）、`report/signal_record.py` 适配器（唯一持有语义词表映射，`core/` 不依赖 `analysis/`）、报告第 5d 步 seam、专家复盘提示词注入账本上下文。**来源标签复用既有数据质量设施**（逐品种 `data_freshness` + 降级事件）而非新造合成数据开关；仅可证明为实时才算实时，无逐品种条目时乐观取实时但显式记理由。实现设计见 `docs-stm/plan/signal-ledger-implementation.md` |
> | **plan-35** | 健壮性三件套（借鉴 augur）：① `safe_num` 全链路数值归一（防 NaN/±inf 污染下游链）；② 数据源失败「错误即 UX」——provider 失败原因进可读 `data_error` 字段、主链路不中断；③ `doctor` 类自检命令（一次性盘点 key/连通性/缓存/路径，复用现有 `check_sources.py`）。语义名（拟）`robustness_suite`。分析见 `augur-borrowing-analysis.md` §建议C。 | P4 | 已完成（2026-09-10）：**A 缺陷修复（无开关，默认路径生效）**——① **数值归一防线**：`providers/_utils.safe_float` 及 tencent/sina_kline/akshare_extras/eastmoney_industry 各解析器对 `float("nan")`/`float("±inf")` 的 `try: float(x) except` 兜底完全失效（两者都不抛异常），脏值直入市值/收益序列/绘图数据；统一收敛到 `core.num_utils.safe_num` 显式拦下非有限值，合法输入行为逐字不变；② **失败原因可读**：provider 链路失败原因此前只留 `failure_type` 短标识（`transport`/`empty`），用户看不懂哪个源、为什么失败；新增 `fetcher/chain.FailureDiagnostics` 采集「展示名(原因)」序列随 `DegradationEvent.detail.message` 透传到 `data_source_matrix` 降级明细，无原因时回落原短标识保证既有输出逐字不变。**B 实验增强（`doctor_check` 默认关）**——`core/doctor.py` 一键自检（环境/配置/目录/功能开关/数据源六组，失败项附可执行修复建议）；零重依赖（不 import pandas，因 pandas 缺失正是它要报的场景）、自身永不抛异常。三面上屏：`doctor` CLI 子命令（`--offline`/`--timeout`，**不受开关约束**——配置损坏正是它要诊断的场景，若被开关拦住即成死锁）、TUI 菜单 `[D]`（受开关约束）、Web 运行状态区自检卡片 + `GET /api/doctor`。CLI 实验开关由 `--experiment doctor_check` 统一控制。实现设计见 `docs-stm/plan/robustness-suite-implementation.md`；自审记录 rf-299~rf-301 |
> | **plan-36** | 数据源适配契约（借鉴 OpenBB Fetcher 三段式 TET + 标准字段 schema + alias 声明式归一）：定义「数据域标准字段」一份 + 每数据源只实现「参数转译 → 抓取 → 映射到标准字段」三小函数；字段改名/换算用 alias/校验器在解析期归一，替代各 provider 手拼 dict。**只对新增数据源/加字段试点，不回改存量 provider**；不搬 OpenBB 的 Provider 注册元架构/覆盖矩阵/命令路由。语义名（拟）`provider_adapter_contract`。分析见 `openbb-data-provider-analysis.md` §建议A/B。 | P4 | 深入分析中（本条） |
> | **plan-37** | 数据源记录-回放测试（借鉴 OpenBB pytest-recorder/vcrpy cassette）：对高价值数据源（基金净值/持仓解析）录真实响应进 git 跟踪 cassette，无 `--record` 跑即离线回放——补上「真实响应体的解析/归一路径」的回归覆盖（现有 mock 测试测不到），不违反「测试不碰真网络」隔离纪律；需评估引依赖 vs 自研轻量回放。语义名（拟）`datasource_cassette_test`。分析见 `openbb-data-provider-analysis.md` §建议C。 | P4 | 深入分析中（本条） |
> | **plan-38** | 数据源凭据声明与就绪指引（借鉴 OpenBB `Provider(credentials=[...])` + 缺失 `"Missing credential ... Check <website>"` 可读报错）：若接入需 API key 的数据源，能声明「此源需 key」并在缺失时给可读指引与就绪提示，而非运行时裸报错。当前免费源为主，**远期/需 key 源时再启用**，可并入 `config` 层 + `check_sources.py`。语义名（拟）`datasource_credential_ready`。分析见 `openbb-data-provider-analysis.md` §建议D。 | P4 | 深入分析中（本条） |

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
