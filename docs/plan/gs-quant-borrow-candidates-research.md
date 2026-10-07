# gs-quant 借鉴候选研究

> **性质**：借鉴批候选分析（方法论同 TradingAgents-CN / Vibe-Trading 批：先研究 → 候选清单 → 立项前逐条比对本仓库现状，rf-510 教训分层不重叠）。
> **分析对象**：goldmansachs/gs-quant（2026-10-06 经 codeload tarball 克隆于 `docs/tmp/gs-quant`；410 个 py / 157,405 行 + docs 207K 行）。
> **结论速览**：2 项立项（plan-79 事件窗量化对照 / plan-80 调仓纪律回放）、1 项参照输入（plan-77 成本模型分层）、10 项评估后不采纳。

## 1. 项目概况

高盛开源量化库，形态是「**Marquee 平台 API 客户端 + 离线计算内核**」混合体：

| 子系统 | 规模 | 内容 | 离线可用性 |
|---|---|---|---|
| `timeseries/` | 37f / 27.4K | 统计口径（sharpe/vol/beta/回撤/相关）、代数运算层、指标 measures（154 def + 族）、**事件研究**（`frame_timeseries_around_events` / `event_impact_analysis`） | 高（纯计算部分） |
| `target/` | 30f / 19.3K | 组合/指数/筛查 measures 封装 | 低（平台查询） |
| `markets/` | 22f / 16.8K | 期权/外汇/利率可定价对象与定价 | 中（部分定价逻辑离线） |
| `api/` | 59f / 10.6K | Marquee REST 客户端族（data/risk_models/indices/tca…） | 低（需 GS 认证） |
| `backtests/` | 20f / 5.7K | **事件驱动回测引擎**：`Backtest`/`DataHandler`/`SimulatedExecutionEngine` + Actions（`RebalanceAction`…）+ **`TransactionModel` 三件套（Constant/Scaled/Aggregate）** + `PnlAttribute` 分解 | 高（`GenericDataSource` 可注任意数据） |
| `analytics/` | 26f / 5.4K | DataGrid + **Processor 可组合管线**（Percentiles/Sharpe/Beta/Zscores/StdMove…） | 中（依赖查询层） |
| `models/` | 4f / 4.8K | `FactorRiskModel` 等风险模型（数据经平台）+ 流行病学模型（SIR/SEIR，开源史遗留） | 低 |
| `risk/` | 8f / 2.5K | `PnlExplain` 等风险度量与结果处理器 | 低（平台） |
| `mcp/` | 16f / 1.7K | MCP server（数据工具对外暴露，GS 会话认证） | 低 |
| `datetime/` | 7f / 1.5K | `GsCalendar` 交易日、business day 运算、rdate 相对日期规则（`bRule`/`dRule`/`FRule`…） | 中 |
| `skills/` | 2f / 0.2K | LLM skill 包安装器（install/uninstall 至各 scope） | 高 |

关键工程特征：① 回测引擎把**交易成本建模**（三档 TransactionModel）与 **PnL 归因分解**（`PnlAttribute`/`PnlDefinition`）作为一等公民；② 事件研究把「事件 × 时间序列」对齐、归一、影响度量拆成可单测的纯函数；③ 报表指标用 Processor 组合而非硬编码列。

## 2. 候选清单与本仓库现状比对

### 2.1 立项项（2）

| 候选 | gs-quant 参照物 | 本仓库现状 | 立项 |
|---|---|---|---|
| 事件窗量化对照 | `timeseries/event_study.py`：`frame_timeseries_around_events`（事件×序列对齐切窗）+ `event_impact_analysis`（窗口影响度量） | **空白**（实测 `事件窗/event_window/窗口收益` 全仓 0 命中）；`news_correlation` 是文本/LLM 关联，`crisis_annotation` 是图表注记——没有「事件日前后 N 日真实收益」的数据侧 | **plan-79**（event_window_impact） |
| 调仓纪律回放 | `backtests/`：`RebalanceAction` 规则触发 + `TransactionModel` 成本 + 引擎逐期回放 | `whatif_backtest` = **单次调仓窗口对比**；`rebalance.py` = 约束检查/建议——**「规则化多期回放（定期/阈值）vs 买入持有」缺口** | **plan-80**（schedule_replay） |

### 2.2 参照输入（1，不新立项）

| 内容 | 去向 |
|---|---|
| `TransactionModel` 三件套（Constant/Scaled/Aggregate 成本分层）与 `PnlAttribute` 分解语义 | **plan-77**（whatif 成本建模）`trade_cost_model` 的分层参照——已在 `whatif-cost-benchmark-design.md` 参照行补注，避免重复立项（分层不重叠） |

### 2.3 评估后不采纳（10）

| 候选 | 不采纳理由 |
|---|---|
| `FactorRiskModel` / `PnlExplain` 因子风险归因 | 本仓库已有 `style_factor_regression`（组合×3 风格 OLS）、`industry_beta`（逐行业 Beta）、`metrics_risk`（风险贡献）、`return_attribution`（品种贡献）四层覆盖；且 gs 侧数据经 Marquee 平台，离线不可得 |
| 事件驱动回测引擎整体引入 | 与 `whatif_backtest`（纯计算/降级契约）及 plan-77 分层；只借「规则触发 + 成本 + 逐期回放」语义给 plan-80，不搬引擎代码（本仓库不引入新回测框架） |
| MCP server | 离线个人工具无对外服务能力（与 Vibe-Trading 批同一结论） |
| skills 安装器 | 本项目 LLM 指引经 CLAUDE.md/管理文档承载，无 skill 分发诉求 |
| `api/` + `target/` measures 族 | GS Marquee 平台绑定、需机构认证，不可移植 |
| `GsCalendar` / rdate 规则引擎 | 已有交易日纪律（持有期按交易日）与既有日期工具；规则引擎为引入而引入 |
| DataGrid + Processor 报表架构 | 现有 Excel/HTML 生成为模板直出，整体重构收益不明确；仅「指标=Processor 可组合」思想留作观察，不立项 |
| `econometrics.py` 基础统计（sharpe/vol/beta/max_drawdown） | 与 `metrics_returns`/`metrics_risk`/`_math_utils` 重叠 |
| `models/epidemiology.py`（SIR/SEIR） | 范围外（开源史遗留，与金融复盘无关） |
| `risk/` 触发器预警族 | 与 `drawdown_warning`/`market_temperature`/熔断降级治理重叠 |

## 3. 立项约束（对 2 项立项生效）

1. **分层不重叠**：立项前逐条比对既有实现；既有能力覆盖的一律只写「重叠说明」。
2. **先决门槛**：plan-79/80 均设 go-no-go 评测（同 plan-55/76/77 模式），未过归档为「已评估未采纳」。
3. **语义名先行**：设计文档先定代码标识符，任务代号不进实现层。
4. **离线纪律**：新数据一律走 `fetcher/chain.py` 多源降级；回放/窗口计算缺数据 `available=false` 绝不硬算。
5. **迭代与验收纪律**：每项立项按「串行分迭代」实施（迭代表带前置依赖与产出物），
   每个迭代：① 配套测试用例先行并通过 P0 门禁；② 带**可量化验收标准**（数字阈值 +
   门禁命令，禁止「基本可用/大体正确」类模糊表述）；③ 同回合同步文档（`check-doc-drift` 绿）。
   迭代未验收不得进入下一迭代。

## 4. 文档索引

| 立项 | 设计文档 |
|---|---|
| plan-79 | `docs/plan/event-window-impact-design.md` |
| plan-80 | `docs/archive/v0.12.x/rebalance-schedule-replay/rebalance-schedule-replay-design.md`（已实施） |

## 5. 架构定位与落点边界（2 项立项 + 1 项参照输入）

| 条目 | 生产落点层 | 依赖方向 | 不越界声明 |
|---|---|---|---|
| plan-79 事件窗量化对照 | analysis + report + llm 注入 | report→analysis.event_window_impact（纯函数）←fetcher 备数 | 不做文本判定（归 Jev 通道）；不与 `crisis_annotation` 注记互写 |
| plan-80 调仓纪律回放 | analysis + report | report→analysis.schedule_replay；成本经 plan-77 同层软注入 | 不搬 gs-quant 引擎；与 `rebalance.py` 只读互链不互写 |
| plan-77 成本分层参照 | analysis（既有立项内） | 消费 `TransactionModel` 分层语义 | 不重复立项（分层不重叠），仅补注参照行 |

两项立项与参照输入共同依赖底座（不重复建设）：`fetch_with_fallback` 多源降级与熔断、
`core/trading_calendar.py` 交易日对齐（事件日→交易日映射、逐期调仓日、±N 窗口全部交易日计）、
`analysis/metrics*` 与 `whatif_backtest` 指标原语、`config/features.py` 开关注册表、
`module_fingerprint.py` 指纹单源。

## 6. 架构约束对照（对两项立项传导生效）

依据 `technical.md` §8「架构设计约束」；✓ = 传导适用且各设计已写入遵从方式；— = 不适用（附理由）。

| 约束 | 判定 | 传导方式 |
|---|---|---|
| 取数纪律（HTTP 工厂 + 多源降级） | ✓ | 窗口行情/历史行情一律 `fetch_with_fallback` 多源降级，禁裸调 provider（HTTP 经工厂，兼 cassette 回放） |
| 报告接入（序号注册表 / pipeline 契约 / 图下说明） | ✓ | 面板序号经注册表、pipeline_data 键先入附录 H、对照/回放图带 `.chart-caption` |
| 日志统一 | ✓ | 新模块输出走 `logging.getLogger("invest")` |
| 测试纪律（marker / edge 文件隔离 / 数据隔离） | ✓ | 每迭代用例带 marker、停牌/缺基准/未触发等 edge 入 `*_edge.py`、测试数据隔离 |
| 指纹单源 | ✓ | plan-79 分歧注入块的指纹由 `module_fingerprint.py` 构造 |
| 实验挂载点 | ✓ | 两项默认关的报告接入经 `_experimental_seams.py` |
| 开关注册表 | ✓ | 新开关只在 `config/features.py` 登记（同 Vibe 批立项约束 4 开关纪律） |
| 交易日计数 | ✓ | 事件日→交易日映射、±N 窗口、逐期调仓日全交易日对齐（`core/trading_calendar.py`） |
| 代码类型/缓存/原子写入/会话复用 | ✓（传导） | 判定复用 `code_utils`、缓存经 `cache/` 接口与原子原语、会话缓存复用 |
| **不适用汇总** | — | 新闻召回不改（不改新闻召回）、着色不改（不改着色）、凭据源纪律（不新增凭据源）、重试统一/节流统一（无新增重试/节流点，由既有原语承担）；LLM 模块注册/路由/凭据分离 仅注入既有 LLM 块时传导适用（设计节已列） |

## 7. 共享能力复用清单（两项立项的统一核查表）

| 能力 | 既有实现（符号） | 复用方式 | 双实现防线 |
|---|---|---|---|
| 取数与降级 | `fetch_with_fallback()` + `cache/` | 窗口/历史行情经 chain，缓存经 `cache/` 接口 | 设计评审核对：新代码不得出现 `requests.`/`providers.` 直连 |
| 对齐与 LOCF | `analysis/whatif_backtest.py`（并集+LOCF、基点归一） | plan-79 窗口对齐、plan-80 逐期回放对齐同源 | 禁第二套对齐/归一实现 |
| 指标原语 | `analysis/metrics*` | 超额收益、逐期指标一律原语拼装 | 新模块不得出现第二套 sharpe/回撤实现 |
| 交易日历 | `core/trading_calendar.py` | 事件窗与调仓日对齐全交易日计 | 禁自然日差、禁自建日历 |
| 指数/基准入口 | `fetcher/index.py`（双链路例外入口） | plan-79 基准序列经既有入口 | 禁自建指数取数 |
| 纪律建议语义 | `analysis/rebalance.py` | plan-80 触发阈值语义与其对齐、只读互链 | 禁两套阈值定义 |
| 报告与开关接入 | `_experimental_seams.py` / `core/registry.py` / `config/features.py` | 挂载点、注册表、开关三处各归其位 | 禁内联守护、硬编码序号、散写开关清单 |

## 8. 技术债防线（两项立项统一生效）

1. **研究快照冻结**：参照物版本（tarball 克隆日期 + 仓库状态）固定在本文档头部，结论可复现；不随上游更新改写已归档判定。
2. **归档防回潮**：不采纳 10 项的不采纳理由入档，后续周期不重复同一批研究；立项项未过门槛同样归档「已评估未采纳」。
3. **只借语义不搬代码**：gs-quant 引擎/规则引擎代码一律不入仓（§2.3 参照输入仅限分层语义）——搬代码即背负其平台假设与维护面。
4. **口径单源**：对齐/LOCF/指标/交易日历各只有一份实现（复用既有原语），plan-79/80 不得各写一份同名逻辑。
5. **单文件红线**：新增模块受 800 行红线守护（`check-file-length --ci`），逼近即拆。
6. **测试卫生与计数同步**：新增用例过 `check-test-redundancy` 五类；删并后同步 `test-coverage.md`/`folders.md` 计数。
7. **文档同步即门禁**：各迭代落地同回合同步五份文档，`check-doc-drift --ci` 绿才算迭代完。
8. **迭代可独立合并**：每迭代 P0 门禁全绿再进下一迭代；每迭代带可量化验收（见 §10）。

## 9. 测试纪律（两项立项逐迭代生效）

1. **测试先行**：每个迭代的配套用例与实现同迭代提交，不存在「先合实现后补测试」的欠账迭代。
2. **分层跑法**：便宜检查（ruff + 各 `--ci` 守护脚本）随改随跑；`test-runner.py --mode dev-verify`（P0）每迭代收尾必跑；合并 master 前 P1 `verify`。
3. **隔离强制**：LLM 调用 mock 强制、外网 socket 层守卫、配置/持仓路径经 conftest 重定向（测试数据隔离）、输出目录临时化。
4. **边缘隔离**：停牌/缺基准/未触发/行情缺口等极端场景入 `*_edge.py` 并标 `edge`（edge 文件隔离）。
5. **有效性门禁**：每迭代跑 `check-test-redundancy --ci`（五类硬禁止零违规）；删并用例后同步 `test-coverage.md`/`folders.md` 计数。
6. **patch 纪律**：跨模块 patch 打在调用点所在模块，漏 patch 即网络守卫响亮失败、零静默降级。

## 10. 量化验收基准（两项立项传导，逐迭代适用）

| 立项 | 门槛与验收量化值（判定只认这些数字） |
|---|---|
| plan-79 事件窗量化对照 | 门槛：日期字段抽 20 条可用率 ≥80%、窗口口径唯一可判定（±5 交易日/基准对齐/LOCF 文档化）、10 例人工比对一致或可解释 ≥7；迭代验收：切窗手算容差 0（每类 ≥2 例）、缺失 >30% 不出行且告警计数准确、关态哈希不变 |
| plan-80 调仓纪律回放 | 门槛：指标原语可复用核对 ≥3 处、成本软依赖声明（未落地出标注版）、2 个真实样例用户确认；迭代验收：回放手算容差 0、`cost_note` 必现率 100%、关态哈希不变 |

通用逐迭代收口数字：P0 `test-runner.py --mode dev-verify` 0 失败；`check-test-redundancy --ci` 0 finding；`check-doc-drift --ci` 0 finding。禁止「基本可用/大体正确」类验收表述。

## 11. 外部数据依赖与稳定性考察（两项立项传导）

**批次结论**：两项立项均**不新增外部数据源与凭据**；核心外部依赖是**窗口/长回放期历史行情**，稳定性策略统一为「多源降级 + 缺口阈值不硬算 + 快照可复算」。

| 立项 | 外部数据依赖 | 稳定性考察要点 | 专项节位置 |
|---|---|---|---|
| plan-79 | 窗口行情（含基准指数）、上游新闻日期字段质量 | 窗口缺失率 >30% 不出行；日期可用率 ≥80% 首轮 + 迭代 2 复测；运行期跳过计数监测源漂移 | `event-window-impact-design.md` 外部数据节 |
| plan-80 | 长窗口历史行情（≥12 个月）、可选成本费率 | 缺口率 >30% 章隐藏；成本软依赖缺席时显式标注；失真样例不得用于价值门槛确认 | `../archive/v0.12.x/rebalance-schedule-replay/rebalance-schedule-replay-design.md` 外部数据节 |

**参照物稳定性（本批次自身）**：gs-quant 参照为 tarball 冻结快照（克隆日期见头部），结论可复现、不随上游漂移；`docs/tmp/` 克隆物不入库，研究判定以冻结快照为准。

**批次级判定动作**：任何 go-no-go 判定不得在数据缺口失真状态下出结论；稳定性监测指标与门槛数值一并写入判定记录，缺则判定无效。

## 12. 风险、回滚与归档纪律（两项立项统一）

| 风险 | 缓解 | 触发后的动作 |
|---|---|---|
| 任一立项不过先决门槛 | 门槛预注册（各设计文档即载体） | 归档「已评估未采纳」+ 实测数值与理由；`plan.md` 状态同步 |
| 搬入 gs-quant 代码/引擎 | 只借语义不搬代码（§2.3 仅限分层语义） | 代码评审拒绝；已入仓则回滚提交 |
| 半成品沉淀 | 每迭代独立验收、测试先行 | 不合入即无残留；已合入出问题单次 revert |
| 开关转正前僵尸分支 | 默认关 + experiment_stats 观测 | 观测不足 → 开关/需求条目整体摘除 |
| 参照结论被上游更新推翻 | tarball 快照冻结（克隆日期入档） | 结论以冻结快照为准，不随上游漂移 |
| 同批候选被重复研究 | 归档防回潮（不采纳理由入档） | 后续周期先检索归档再立项 |

**回滚原则**：功能级回滚 = 关闭开关（关态逐字节不变，各设计验收锁定）；迭代级回滚 = 单次 revert（每迭代独立提交、无跨迭代耦合）；数据级回滚 = 契约版本向后兼容，不删历史、不重写用户文件。

**文档同步义务（每迭代同回同）**：各立项同步 `requirements.md`/`technical.md`/`testplan.md`/`changelog.md` + `folders.md`/`test-coverage.md` 计数；本文档只追加判定结论。完成判据 = `check-doc-drift --ci` 0 finding。
