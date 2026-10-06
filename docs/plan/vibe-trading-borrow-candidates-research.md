# Vibe-Trading 借鉴候选研究

> **性质**：借鉴批候选分析（对标 TradingAgents-CN 借鉴批的方法论：先研究 → 候选清单 → 立项前做本仓库现状比对，rf-510 教训）。
> **分析对象**：HKUDS/Vibe-Trading（2026-10-05 克隆于 `docs/tmp/Vibe-Trading`，1889 个 py 文件 / 46.5 万行）。
> **结论速览**：4 项立项（plan-76 持仓变动复盘 / plan-77 What-if 回放成本与基准 / plan-70 决策反思补设计 / plan-78 因子目录评测），6 项评估后不采纳。

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
| 持仓变动复盘 | `skills/trade-journal`（journal schema + 归因分析） | **部分**：输入只有持仓快照 Excel，但快照历史与差异引擎已内建（`data/history/snapshots/` + `HistoryDiff`）——买卖变动可由快照差分推断（decision_ledger 是 LLM 决策登记，非成交记录） | **plan-76**（holding_change_review，快照事件级） |
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
6. **迭代与验收纪律**：每项立项按「串行分迭代」实施（迭代表带前置依赖与产出物），
   每个迭代：① 配套测试用例先行并通过 P0 门禁；② 带**可量化验收标准**（数字阈值 +
   门禁命令，禁止「基本可用/大体正确」类模糊表述）；③ 同回合同步文档（`check-doc-drift` 绿）。
   迭代未验收不得进入下一迭代。

## 4. 文档索引

| 立项 | 设计文档 |
|---|---|
| plan-76 | `docs/archive/v0.12.x/holding-change-review/holding-change-review-design.md`（已实施，随完成态归档） |
| plan-77 | `docs/archive/v0.12.x/whatif-cost-benchmark/whatif-cost-benchmark-design.md` |
| plan-70 | `docs/plan/decision-reflection-shadow-design.md` |
| plan-78 | `docs/plan/factor-zoo-catalog-design.md` |

## 5. 架构定位与落点边界（4 项立项）

| 立项 | 生产落点层 | 依赖方向 | 不越界声明 |
|---|---|---|---|
| plan-76 持仓变动复盘 | analysis（快照读取 + 事件抽取/指标）+ report + llm | report→analysis；llm 只消费 pipeline_data 摘要 | 快照只读消费不自建存储；不写 decision_ledger/signal_ledger（只读对账）；读本地快照零网络，不进 provider 链路 |
| plan-77 What-if 成本与基准 | analysis + report + fetcher 扩展 | 只扩展 `whatif_backtest` 消费侧，不改其纯计算契约 | 不复制限购判定（plan-74 只读复用）；不新建第二套费率配置入口 |
| plan-70 决策反思 | core（账本写侧）+ analysis + report | report/doctor→analysis.decision_settlement；实验期经 `_experimental_seams` 挂载点 | 观测期零实施；转正前不进 `core/registry.py` 章节注册 |
| plan-78 因子目录 | 评测期仅 `scripts/`；转正后 analysis | 评测脚本→fetcher 网关；生产侧未过门槛零改动 | 评测产物只落 `docs/tmp/`；不搬算子代码 |

四项共同依赖底座（不重复建设）：`fetch_with_fallback` 多源降级与熔断、`cache/` TTL
与载荷语义版本、`core/trading_calendar.py` 交易日计数、`config/features.py` 开关注册表、
`module_fingerprint.py` 指纹单源。

## 6. 架构约束对照（对四项立项传导生效）

依据 `technical.md` §8「架构设计约束」；✓ = 传导适用且各设计已写入遵从方式；— = 不适用（附理由）。

| 约束 | 判定 | 传导方式 |
|---|---|---|
| 取数纪律（HTTP 工厂 + 多源降级） | ✓ | §3 第 5 条离线纪律：新数据一律 `fetch_with_fallback` 多源降级，禁裸调 provider（HTTP 经工厂，兼 cassette 回放） |
| 报告接入 | ✓ | 新章序号经注册表、pipeline_data 键先入附录 H（各设计「架构定位」节已列） |
| 日志统一 | ✓ | 新模块输出走 `logging.getLogger("invest")` |
| 测试纪律（marker / edge 文件隔离 / 数据隔离） | ✓ | 每迭代用例带 marker、edge 入 `*_edge.py`、真实持仓/日志/配置测试只读隔离 |
| 指纹单源 | ✓ | plan-76 归因、plan-70 反思块的提示词入参指纹一律 `module_fingerprint.py` 构造 |
| 实验挂载点 | ✓ | plan-70/76 默认关的报告接入经 `_experimental_seams.py` |
| 开关注册表 | ✓ | §3 第 4 条开关纪律：新增开关只在 `config/features.py` 登记 |
| 交易日计数 | ✓ | 持有期/信号对账/窗口回看一律交易日计 |
| 代码类型/缓存/原子写入/会话复用 | ✓（传导） | 判定复用 `code_utils`、缓存经 `cache/` 接口与原子原语、会话缓存复用（各设计遵从） |
| **不适用汇总** | — | 新闻召回不改（不改新闻召回）、着色不改（不改着色）、凭据源纪律（四批不新增凭据源）、重试统一/节流统一（无新增重试/节流点，由既有原语承担）；LLM 模块注册/路由/凭据分离 仅 plan-76 传导适用（其设计节已列双注册与凭据分离） |

## 7. 共享能力复用清单（四项立项的统一核查表）

| 能力 | 既有实现（符号） | 复用方式 | 双实现防线 |
|---|---|---|---|
| 取数与降级 | `fetch_with_fallback()` + `cache/` | 一切新增取数经 chain，缓存经 `cache/` 接口 | 设计评审时核对：新代码不得出现 `requests.`/`providers.` 直连 |
| 交易日计数 | `core/trading_calendar.py` | 持有期/窗口/对账时点全交易日计 | 禁自然日差表达式入代码 |
| 指标计算 | `analysis/metrics*` + `whatif_backtest` | 胜率外的收益/回撤/窗口指标一律原语拼装 | 新模块内不得出现第二套 sharpe/回撤实现 |
| diff/对账 | `analysis/whatif.py`（多账户合并、变动分类） | plan-70 意图↔成交对账（成交侧 = plan-76 变动事件）复用其合并原语 | 禁自写第二套持仓合并 |
| LLM 指纹与降级 | `module_fingerprint.py` + `skeleton.py` 降级矩阵 | 归因/反思块指纹单源、降级形态同构 | 指纹片段禁在生成器内手拼 |
| 报告接入 | `_experimental_seams.py` + `core/registry.py` | 实验期挂载点、转正后注册表 | 禁内联 try/except 守护、禁硬编码序号 |
| 开关登记 | `config/features.py` | 每项新增开关仅此一处登记 | 渠道/文档清单由注册表驱动，禁另写 |

## 8. 技术债防线（四项立项统一生效）

1. **研究快照冻结**：参照物版本（克隆日期 + 仓库状态）固定在本文档头部，结论可复现；不随上游更新而改写已归档判定。
2. **归档防回潮**：未采纳 6 项的不采纳理由入档，后续周期不重复研究同一批候选；立项项未过门槛同样归档「已评估未采纳」。
3. **评测代码不固化**：go-no-go 评测脚本只住 `scripts/`，不过门槛时 `src/python/` 零改动（防半成品沉淀死代码）。
4. **契约与载荷版本**：日志格式/账本契约等结构化输入一律带版本字段，读侧「版本不符」按未命中处理，不重写历史数据。
5. **单文件红线**：各设计新增模块受 800 行红线守护（`check-file-length --ci`），逼近即拆。
6. **测试卫生与计数同步**：新增用例过 `check-test-redundancy` 五类；删并后同步 `test-coverage.md`/`folders.md` 计数。
7. **文档同步即门禁**：各迭代落地同回合同步五份文档，`check-doc-drift --ci` 绿才算迭代完。
8. **迭代可独立合并**：每迭代 P0 门禁全绿再进下一迭代，不堆叠未验证改动；每迭代带可量化验收（见 §10）。

## 9. 测试纪律（四项立项逐迭代生效）

1. **测试先行**：每个迭代的配套用例与实现同迭代提交，不存在「先合实现后补测试」的欠账迭代。
2. **分层跑法**：便宜检查（ruff + 各 `--ci` 守护脚本）随改随跑；`test-runner.py --mode dev-verify`（P0）每迭代收尾必跑；合并 master 前 P1 `verify`。
3. **隔离强制**：LLM 调用 mock 强制（防费用/防依赖）、外网 socket 层守卫、配置/持仓/日志路径经 conftest 重定向（测试数据隔离）、输出目录临时化。
4. **边缘隔离**：极端/异常场景入 `*_edge.py` 并标 `edge`（edge 文件隔离），普通与 edge 不混文件（收集期强校验）。
5. **有效性门禁**：每迭代跑 `check-test-redundancy --ci`（五类硬禁止零违规）；删并用例后同步 `test-coverage.md`/`folders.md` 计数。
6. **patch 纪律**：跨模块 patch 打在调用点所在模块（函数内 import 时上游 patch 不生效），漏 patch 即网络守卫响亮失败。

## 10. 量化验收基准（四项立项传导，逐迭代适用）

| 立项 | 门槛与验收量化值（判定只认这些数字） |
|---|---|
| plan-76 持仓变动复盘 | 门槛：去重后有效快照 ≥12 期且变动事件 ≥10 个、事件口径唯一且局限显式标注、结构级结论人工认可；迭代验收：差分事件/指标手算容差 0、「非逐笔」标注常驻、降级逐字节回退 |
| plan-77 What-if 成本与基准 | 门槛：抽 20 只费率取得率 ≥80%、FIFO 口径可判定、方向性翻转 ≥1；迭代验收：档位手算容差 0、关态哈希不变、未知费率不出伪数字 |
| plan-78 因子目录评测 | 门槛：A ≥80%（≥20/25）、B ≥30%、C ≤20%；迭代验收：判定值可复算且与入库结论逐字段一致 |
| plan-70 决策跨期反思 | 死线：已结算样本 ≥10 条方可谈转正；迭代验收：结算手算容差 0、关态哈希不变、异常注入不中断主链路 |

通用逐迭代收口数字：P0 `test-runner.py --mode dev-verify` 0 失败；`check-test-redundancy --ci` 0 finding；`check-doc-drift --ci` 0 finding；涉开关迭代「关态逐字节不变」哈希比对通过。禁止「基本可用/大体正确」类验收表述。

## 11. 外部数据依赖与稳定性考察（四项立项传导）

**批次结论**：四项立项均**不新增外部数据源与凭据**，全部复用既有链路；真正的稳定性风险在「字段口径可得性」与「用户维护节奏」两类，各设计已列专项节（见下）。

| 立项 | 外部数据依赖 | 稳定性考察要点 | 专项节位置 |
|---|---|---|---|
| plan-76 | 无新增源；本机自产快照 + 既有 LLM 链 | 有效快照期数/最早跨度回显、60 天滚动截断监测、LLM 降级矩阵 | `holding-change-review-design.md` 数据源稳定性节 |
| plan-77 | 申赎费率（天天基金链路）、基准指数行情 | 取得率 ≥80%、页面改版解析失败计数、cassette 回放防漂移、语义版本缓存 | `whatif-cost-benchmark-design.md` 外部数据节 |
| plan-78 | 行情/财务字段（评测期考察） | 字段可得率 ≥80% 与不可得原因分类（区分口径不可得 vs 源暂不可用） | `factor-zoo-catalog-design.md` 外部数据节 |
| plan-70 | 建议日窗口行情（既有链） | 窗口缺口率 >30% 判不足、未结算积压趋势作为稳定性前置信号 | `decision-reflection-shadow-design.md` 外部数据节 |

**批次级判定动作**：任何一项评测（go-no-go）不得在数据缺口失真状态下出结论；稳定性监测指标与门槛数值一并写入判定记录，缺则判定无效。

## 12. 风险、回滚与归档纪律（四项立项统一）

| 风险 | 缓解 | 触发后的动作 |
|---|---|---|
| 任一立项不过先决门槛 | 门槛预注册（各设计文档即载体） | 归档「已评估未采纳」+ 实测数值与理由；`plan.md` 状态同步 |
| 半成品沉淀 | 评测代码不进 `src/python/`；每迭代独立验收 | 不合入即无残留；已合入出问题单次 revert |
| 开关转正前僵尸分支 | 默认关 + experiment_stats 观测；转正才进章节注册 | 观测不足 → 开关/需求条目整体摘除 |
| 参照结论被上游更新推翻 | 参照快照冻结（克隆日期入档） | 结论以冻结快照为准，不随上游漂移 |
| 同批候选被重复研究 | 归档防回潮（不采纳理由入档） | 后续周期先检索归档再立项 |

**回滚原则**：功能级回滚 = 关闭开关（关态逐字节不变，各设计验收锁定）；迭代级回滚 = 单次 revert（每迭代独立提交、无跨迭代耦合）；数据级回滚 = 契约版本向后兼容，不删历史、不重写用户文件。

**文档同步义务（每迭代同回同）**：各立项同步 `requirements.md`/`technical.md`/`testplan.md`/`changelog.md` + `folders.md`/`test-coverage.md` 计数；本文档只追加判定结论。完成判据 = `check-doc-drift --ci` 0 finding。
