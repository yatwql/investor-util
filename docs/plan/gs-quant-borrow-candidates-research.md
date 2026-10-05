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

## 4. 文档索引

| 立项 | 设计文档 |
|---|---|
| plan-79 | `docs/plan/event-window-impact-design.md` |
| plan-80 | `docs/plan/rebalance-schedule-replay-design.md` |
