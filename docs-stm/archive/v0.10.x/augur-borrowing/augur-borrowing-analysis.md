# augur（多智能体投资分析）借鉴评估 — 深入分析

> 文档版本：0.10.16-dev
> 来源：外部仓库 [BruceLanLan/augur](https://github.com/BruceLanLan/augur) 借鉴评估（2026-09-09）
> 源码位置：`docs-stm/tmp/augur-main/`（浅层下载，非 git clone，未纳入版本库）
> 状态：**借鉴点已全部落地**——建议A 与既有决策反思分析合并为决策跨期反思闭环（`decision_reflection`）、建议B 落地为确定性信号账本（`signal_ledger`）、建议C 落地为健壮性三件套（数值归一防线 / 失败原因可读 / 系统自检）；三份实现设计见同目录 `signal-ledger-implementation.md`、`robustness-suite-implementation.md` 与 `../tradingagents-borrowing/decision-reflection-implementation.md`
> 外部版本：v10.15.0（MIT，518 star，114 源 py + 111 测试，2026-07 快照）
> 技术路线前提：augur 的「18 位投资大师」**核心是确定性规则打分器，非 LLM**；LLM 仅在外围聊天/抽取（详见 §1）

---

## 0. 结论先行（TL;DR）

augur 是一个「18 位人格化投资大师对同一标的独立打分 → 加权共识给裁决」的单标的分析系统，与「投资复盘助手」路线差异巨大，**但有三组高价值、低迁移成本的机制值得借鉴**。按「对本项目的增量价值」分档：

| 借鉴点 | 类别 | 对我方缺口 | 价值 | 落地代价 |
|---|---|---|---|---|
| **1. 决策记录→真实结果命中率闭环** | 学习/复盘 | 我方 action/再平衡有置信度与建议，但从不结算"后来涨没涨、建议对不对"，无法自我评估 | **高** | 低~中（复用已有 perf/回测基建） |
| **2. 确定性数值信号沉淀 + live_only 纪律** | 数据/诚实性 | LLM 文本复盘难以量化验证；把确定性算法评级沉淀为可回测记录，附真/合成标签 | **中高** | 中（需定义信号 schema + 记录表） |
| **3. 数据源失败「错误即 UX」+ 按需可选依赖 + doctor 自检** | 运维/健壮 | provider 多源已 fallback，但缺统一诊断入口与"失败原因可读、核心不受损"的文案 | 中 | 低（纯增量） |
| 4. `--json`/机器输出形态（CLI 面向人+机器） | 接口 | CLI 面向人，无机器可读输出；but Web/Excel 已是主力 | 低 | 低 |
| 5. NO_COLOR + emoji↔文本 双态信号映射 | 输出 | 我方已有 `[OK]/[!]/[ERR]` + 颜色前缀纪律 | 低 | 低（已覆盖） |
| 6. 用户子集 → 权重重归一化（enabled_personas） | 配置 | 我方 LLM 链多 provider 分发、无"只跑子集" | 中（若做多模型对比） | 中 |
| 7. MCP / 桌面 Agent 接入 | 接入 | 无 | 中（远期） | 中~高 |
| 8. 插件机制 / cron 守护 / bot 通知 | 工程 | 部分已有 | 低~中 | 中 |
| 9. "大师进化"/辩论/metamodel/校准器 | — | augur 自身空转/展示件，**不建议照搬** | 无 | — |

> 说明：docs-stm/plan 下既有 `llm-quality-signal-analysis.md`、`reflection-decision-loop-analysis.md` 两篇 TradingAgents-astock 借鉴分析，本文与它们同属外部借鉴评估系列，**未立项**，仅作候选池。

---

## 1. 外部机制解剖（借什么）

### 1.1 一个决定性的架构事实（先看这个）

**augur 的"大师"不是 LLM agent，是确定性规则评分函数。** 每个大师 `.analyze()` 读共享 `MarketContext`（~150 个真实数值字段）→ 按各自风格阈值打分 → 加权总分 → 三态信号。LLM 只在两处旁路：`chat.py` 闲聊、`edgar_guidance.py` 可选 MD&A 抽取（默认 OFF）。证据：

- `personas/buffett.py:42-166`、`dalio.py`、`duan_yongping.py` 全是 `if context.gross_margins > 0.4: moat_score += 3` 式硬编码打分。
- 并行调度 `registry.py analyze_with_all`（ThreadPool ≤8，单 agent 超时 30s→ERROR 降级）调纯函数，无模型调用。

**意义**：正因为打分是确定性的，augur 才能做 IC / 命中率 / "学习"——这是它全部质量机制的前提。我方路线（LLM 生成 + 事实校验器）**不能照搬"大师打分器"**（我方价值在生成式复盘），但可借鉴其"沉淀确定性记录、事后用真实行情结算"的诚实性骨架。

### 1.2 决策-结算学习闭环（最值得借鉴）

- `LearningEngine.record_prediction`（`learning.py:121`）：每次共识末尾把每 agent 的 (ticker, signal, score, conf, ts) **立即持久化**到 `~/.augur/learned_weights.json`（注释记录了根因：曾只在结算时存盘，进程重启即丢）。
- 自动结算 `registry.py:40-98 _check_and_record_outcomes`：对 pending >30 天的记录拉真实行情，`bullish` 需 +2% 才算对；结算→`_recalculate_weights`（50% 命中率 + 50% IC 贡献，clamp[0.1,3.0]，**每 agent ≥3 样本才生效**）→ engine 以 40% 权重合入下轮。
- 触发：每日 cron `run_watchlist_analysis` 末尾 piggyback `resolve_pending_outcomes` 清扫——避免"从不手动再分析的标的永远无法结算"。
- **`live_only` 纪律**（`backtest.py:29-47,450-479`）：每条记录打 `data_source="live"/"demo"` 标签；排行榜/IC 报告**默认只算 live**，合成记录绝不混入"真实战绩"。
- 数据源为 none/error 的空 context 预测被跳过，避免污染校准样本（`engine.py:390`）。

### 1.3 数据与健壮性（「错误即 UX」）

- **`safe_num`**（`datasources/base.py:28-54`）：`float('nan')` 是 truthy，`nan or 0` 仍返 nan → 污染评分链。`safe_num` 把 None/NaN/±inf/bool/非数值全归一为有限 float。**对接脏数据的通用防线**。
- **主链 + 专用源 overlay 分离**（`data.py:294-329`）：EDGAR 基本面不塞进"整体替换"provider 链（否则会清空其余字段），而在链后做**字段级非 0 覆盖** + `fundamentals_source` 标记 + 永不 raise。比"每源都是全量 provider"更稳。
- 失败不 raise：返回挂 `data_source="none"` + `data_error="all providers failed: ..."` 的结果，主链路照跑、标注降级。
- **按需可选依赖注册表**（`optional_deps.py`）：`模块名→(功能描述, pip extra)`，`require_optional()` 缺失抛"可操作 ImportError"（提示装哪个 extra、核心命令仍可用）。lazy import 兜底。
- provider_stats 的 `doctor` 探测历史是**刻意的非线上遥测**（docstring 明说不 live 影响报告）——反例提醒：别把健康度探测做成热路径 I/O。

### 1.4 待办/接入/工程（可部分借鉴）

- 统一内核管线 → 多出口（CLI/MCP/四 bot/cron 推送均复用 `DecisionCoordinator.analyze_with_all` + 同一 formatter）。
- CLI 子命令按域拆 `cli_commands/*` + 每条命令 `--json` 开关（人/机器双输出）。
- `NO_COLOR` 全局开关 + 信号 `emoji↔[BUY]文本` 双映射。
- `enabled_personas` 子集 → 注册侧过滤 → `restrict_weights_to_agents` 重归一化（`weighting.py:71-89`）。
- MCP：FastMCP + docstring 即 schema + 逻辑抽成无框架纯函数便于单测。
- 插件：entry-points group `augur.plugins`。
- cron 守护：pidfile 防重入 + SIGTERM 清 pidfile + APScheduler + yaml 深合并默认值。
- conftest 5 个 autouse 隔离 fixture（清 workspace/隔离学习引擎落盘/禁用 EDGAR overlay/归零节流/清限流桶）——保证上千测试不碰真网络真数据。

---

## 2. 我方现状盘点（借到哪 / 有没有重复）

| 借鉴点 | 我方已有 | 我方缺口 | 落点参考（现网文件） |
|---|---|---|---|
| 学习闭环 | ✗ 无预测-结算追踪 | action/再平衡建议不结算"后来对不对" | `src/python/analysis/action_advisor.py`、`rebalance.py`、`trade_discipline.py` |
| 确定性信号沉淀 | △ What-if 回测有 as-if 净值，但非"信号记录表" | 无带 live/demo 标签的信号→真实收益记录 | `src/python/analysis/whatif_backtest.py`、`report/whatif_operations.py` |
| safe_num 数值归一 | △ 多数接口有容错 | 无全链路 NaN/±inf 归一防线 | `src/python/core/code_utils.py`、`analysis/_math_utils.py`、`fetcher/*` |
| overlay 覆盖模式 | △ 已有多源 fallback | 字段级"专用源后置覆盖"模式未抽象 | `src/python/fetcher/chain.py`、`price.py`、`providers/*` |
| 错误即 UX | △ 已有降级/占位 | 无"失败原因可读、核心不受损"的统一诊断入口/doctor | `src/python/core/check_sources.py`、`cli/cli.py` |
| 可选依赖注册表 | ✗ requirements 全装 | 缺按特性分 extra + 可操作报错 | `pyproject.toml` |
| --json / 机器输出 | ✗ CLI 面向人 | 缺机器可读输出 | `src/python/cli/cli.py` |
| 已覆盖项 | `[OK]/[!]/[ERR]` 前缀、成本追踪、事实校验器、多 provider 链 | — | — |

---

## 3. 借鉴建议（候选池，未立项）

### 建议 A（推荐，高价值低代价）：决策记录→真实结果命中率闭环
- **动机**：我方再平衡/行动建议有置信度分级（`_compute_confidence` `rebalance.py:180`），但从不结算"N 日后建议对不对"——缺自我评估与迭代依据。augur/TradingAgents 都证明这是可落地的低 LLM 成本复盘。
- **借鉴点**：`record_prediction` 立即持久化 + 自动结算 sweep + ≥3 样本才生效 + live_only 纪律。
- **落点**：新增状态文件（按 CLAUDE.md 需在 conftest `_isolate_sensitive_paths` 重定向）；复用 perf_history / 历史净值基建结算。
- **注意**：我方"建议"多为调仓/减仓而非单标的买卖评级，需自定义"对/错"口径（如再平衡超限减仓后该品种占比是否回落），勿简单套 bullish→涨。

### 建议 B（中高价值）：确定性数值信号沉淀 + live/demo 标签纪律
- **动机**：LLM 文本复盘难量化验证；但我方"市场温度 低估/合理/高估、估值分位 tier、尾部风险 VaR、风格因子、再平衡超限"等确定性算法评级已产出却不沉淀为可回测记录。
- **借鉴点**：信号 schema + `data_source` 标签 + 排行榜默认 live_only。
- **落点**：新增 `data/state/` 下信号记录 JSONL；与建议 A 可合并成一套。

### 建议 C（中价值，纯增量）：健壮性三件套
- `safe_num` 全链路数值归一（防 NaN 污染下游链，成本极低）。
- 失败"错误即 UX"：provider 失败原因进 data_error 可读字段（我方 `chain.py` 已有降级，补齐"原因可读"）。
- `doctor` 类自检命令（一次性盘点 key/连通性/缓存/路径），复用现有 `check_sources.py`。

### 低价值 / 已覆盖 / 不建议
- emoji↔文本双态信号映射 → 我方 `[OK]/[!]/[ERR]` 已覆盖，不必引入 emoji。
- 大师进化/辩论/元模型/概率校准器 → augur 自证空转或展示件，**不照搬**。
- MCP/插件/bot/cron 守护 → 我方已有 Web/TUI/CLI + Windows 计划任务；MCP 作为远期可选，不列入本次。
- `enabled_personas` 子集权重重归一化 → 我方无"多模型家族对比打分"需求，暂缓（若将来做多模型对比再参考 `restrict_weights_to_agents`）。

---

## 4. 与既有借鉴系列的关系（不重复）

- 同目录 `reflection-decision-loop-analysis.md`（plan-30，TradingAgents）已覆盖「决策登记 + 延迟结算 + 反思回灌」，与本文建议 A **同域但更细**。若立项，应合并评估：建议 A 聚焦**确定性命中率统计**，plan-30 聚焦 **LLM 反思回灌**，两者互补可合成一套。
- 同目录 `llm-quality-signal-analysis.md`（plan-31/32/33）覆盖 LLM 输入/输出/决策头治理，与本文正交。
- 本文不重复已有门禁/测试纪律；引用 augur 的 conftest 隔离模式仅作为我方 conftest 已有 `_isolate_sensitive_paths` 的**补充对照**（我方已具备，无需照搬）。

---

## 5. 待讨论 / 未决问题

1. 建议 A 若立项，"建议对错"口径需业务定义——是否值得先做一轮小范围手工验证再立项？
2. 建议 A/B 的持久化文件落点与既有 `data/state/perf_history.jsonl`、`circuit_breaker.json` 的边界。
3. 是否将本分析（或提炼的候选建议）纳入 `docs-stm/managements/plan.md` 待办评估区。

## 附：augur 目录速览（供后续查阅）

- 源码 `src/augur/`：`personas/`（18 大师规则打分器）、`consensus/`（加权共识引擎）、`registry.py`（并行调度+懒加载）、`workflow.py`、`data.py` + `datasources/`（多源）、`learning.py`、`backtest.py`、`cli.py` + `cli_commands/`、`api.py` + `src/dashboard/`（FastAPI）、`mcp_server.py`、`plugins.py`、`bots/`、`cron.py`、`persona_evolution.py`
- 每大师独立 Hermes Skill（`src/skills/augur-*/SKILL.md`，YAML frontmatter + system_prompt）
