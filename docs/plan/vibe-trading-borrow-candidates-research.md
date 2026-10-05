# Vibe-Trading 借鉴候选研究

> **性质**：借鉴批候选分析（对标 TradingAgents-CN 借鉴批的方法论：先研究 → 候选清单 → 立项前做本仓库现状比对，rf-510 教训）。
> **分析对象**：HKUDS/Vibe-Trading（2026-10-05 克隆于 `docs/tmp/Vibe-Trading`，1889 个 py 文件 / 46.5 万行）。
> **结论速览**：4 项立项（plan-76 交易日志复盘 / plan-77 What-if 回放成本与基准 / plan-70 决策反思补设计 / plan-78 因子目录评测），6 项评估后不采纳。

## 1. 项目概况

Vibe-Trading 是港大 HKUDS 出品的「金融研究工具包」，以 MCP server 形态发布（`vibe-trading-mcp`），核心能力：

| 子系统 | 规模 | 内容 |
|---|---|---|
| `agent/src/tools` | 38.4K 行 | 研究工具集（行情/基本面/图表形态/研报阅读等） |
| `agent/src/factors` | 29.4K 行 | 因子分析框架 + **Alpha Zoo**（462 个预置 alpha：qlib158/alpha101/gtja191/academic/fundamental） |
| `agent/src/trading` | 21.6K 行 | 交易执行相关 |
| `agent/backtest` | ~30K 行 | **10 个回测引擎**（A股/期货/加密/外汇/期权等）+ loaders（28 数据源）+ metrics + benchmark 对比 |
| `agent/src/swarm` | 4.5K 行 | 30 个多智能体团队（`run_swarm`，需 LLM key） |
| `agent/src/skills` | 5.8K 行 | 90 个金融技能（含 trade-journal 交易日志分析） |
| `agent/src/shadow_account` | 3.2K 行 | **影子账户**：extract → codegen → backtest → render，把用户盈利 pattern 提取成可复跑影子 |
| `agent/src/memory` / `strategy_*` / `goal` / `governance` | ~9K 行 | 记忆/策略发现/目标/治理 |
| `agent/evals` + grounding 测试 | ~7K 行 | 工具结果接地校验（防 LLM 引用过期数据） |

关键工程特征：

1. ** loader 注册表 + 引擎分派**：`backtest/runner.py` 以 config.json 驱动，`source="auto"` 按代码格式路由 loader，`engine` 选引擎——配置驱动、来源无关。
2. **影子账户闭环**：`extract_shadow_profile`（journal → ShadowProfile 规则提取）→ `codegen.render_config` → `run_shadow_backtest`（多市场）→ `reporter` 归因报告（AttributionBreakdown）。核心思想：**把「人的行为」结构化成可回放、可归因的影子**。
3. **基准对比面板**：`benchmark.py` 按策略代码自动选基准指数、拉取并 resample，与回测结果同图对比（zero-dependency 设计）。
4. **成本建模**：`factor_costs.py` 把滑点/手续费作为成本因子计入回测；`constraints.py` 约束校验。
5. **事实校验文化**：grounding 测试强制「引用当前引擎输出与确切列表引用」（CHANGELOG 明示 grounding 修复项），与我们 `fact_checker` 同源理念。
6. **零 key 可用**：28 个数据源中 akshare/baostock/东财等免 key——与我们多源降级体系同思路但无熔断/降级治理（我们有）。

## 2. 候选清单与本仓库现状比对

### 2.1 立项项（4）

| 候选 | Vibe-Trading 参照物 | 本仓库现状 | 立项 |
|---|---|---|---|
| 交易日志复盘 | `skills/trade-journal`（journal schema + 归因分析） | **无**：输入只有持仓快照 Excel，买卖历史从未被结构化复盘（decision_ledger 是 LLM 决策登记，非成交记录） | **plan-76**（trade_journal_review） |
| 回放成本/基准 | `factor_costs.py` + `benchmark.py` + `constraints.py` | `whatif_backtest.py` 已有生效日窗口回测（收益/夏普/回撤），但 **不计申赎成本**（高估调仓收益）、**无基准对比面板** | **plan-77**（whatif 成本建模 + 基准对比） |
| 决策跨期反思 | `shadow_account`（extract→backtest→render 影子闭环） | plan-70 已立项但只是「撤销死线」，无落地设计；decision_reflection 实验真实账本积累极少 | **plan-70** 补设计文档（decision-reflection-shadow-design.md） |
| 因子目录 | `factors/zoo`（462 预置 alpha 元数据） | `signal_ledger`（确定性信号账本）+ 风格因子分析已有，但**信号源靠手写注册**，无外部因子目录蓝本 | **plan-78**（factor_zoo_catalog，评测先决） |

### 2.2 评估后不采纳（6）

| 候选 | 不采纳理由 |
|---|---|
| Swarm 30 多智能体团队 | 与我们 LLM 智囊团复盘（标准四模块 + 辩论 + 生成后自检）能力重叠；其面向交易执行的多团队协作与我们「复盘报告」定位不符；成本高收益低 |
| MCP server 打包 | 本项目定位离线个人工具（本地 Excel → 报告），无对外服务能力；打包形态不符 |
| grounding/evals  harness | 与 `llm/fact_checker` + 生成后自检重叠（分层不重叠原则，rf-510 教训） |
| loader_health / shadow evidence | 与既有「数据源可用性矩阵 + 熔断降级 + doctor 自检」重叠且我们治理更细（TTL/熔断/过期缓存三级降级） |
| 期权定价 / 10 引擎全家桶 | 产品范围外：本项目是基金持仓复盘，不触期货/期权/加密 |
| 90 skills 体系 | 泛金融技能集合，多数（开户/下单/经纪商对接）与复盘定位无关 |

## 3. 立项约束（对全部 4 项生效）

1. **分层不重叠**（rf-510 教训）：立项前逐条比对既有实现，凡既有能力覆盖的一律不立项、只写「重叠说明」。
2. **先决门槛**：plan-76/77/78 均设 go-no-go 评测（仿 plan-55 Jev 模式），未达阈值归档为「已评估未采纳」，不留半吊子实现。
3. **语义名先行**：设计文档先定代码标识符（禁任务代号进入实现层）。
4. **开关纪律**：新增功能一律按 `config/features.py` 开关注册表统一登记，默认关闭的实验功能须带 experiment_stats 观测。
5. **离线纪律**：全部新数据源接入须走 `fetcher/chain.py` 多源降级，禁裸调 provider。

## 4. 文档索引

| 立项 | 设计文档 |
|---|---|
| plan-76 | `docs/plan/trade-journal-review-design.md` |
| plan-77 | `docs/plan/whatif-cost-benchmark-design.md` |
| plan-70 | `docs/plan/decision-reflection-shadow-design.md` |
| plan-78 | `docs/plan/factor-zoo-catalog-design.md` |
