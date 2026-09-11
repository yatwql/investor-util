# 测试覆盖统计
> 文档版本：0.10.18-dev

> ⚠ 以下测试项数为撰写时的快照值，实际计数随版本迭代而变化。`模式对应测试量` 表由 `--mode bench --update-docs` 自动回填本机实测；功能域/分组等子表精确统计请运行 `scripts/collect-test-coverage.py`（或 `pytest src/test/ --collect-only -q`）获取实时计数。

按不同的 `--mode` / pytest 标记统计当前测试覆盖规模：

## 模式对应测试量

<!-- mode-count-table:start -->
| `--mode` 值 | 覆盖项数 | 典型耗时 |
|:------------|:--------:|:--------:|
| `unit` | **6365** | ~15s |
| `standard` | **5446** | ~15s |
| `scenario` | **244** | ~18s |
| `regression` | **244** | ~18s |
| `dev-verify` | **2499** | ~23s |
| `verify` | **4330** | ~11s |
| `integration` | **284** | ~14s |
| `edge` | **852** | ~13s |
| `data` | **69** | ~2s |
| `all` | **6677** | ~21s |
| `smoke` | **26** | ~2s |
| `report` | **1753** | ~11s |
| `all_no_unit` | **312** | ~14s |
| `scenario_extreme` | **9** | ~3s |
<!-- mode-count-table:end -->

> 注：典型耗时按 2026-09-10 当前开发机实测（Linux x86_64，Intel i5-13500H，12 核 16 线程，46.8 GiB 内存；pytest-xdist worker=8，即 medium 级别 = 50% 核数）。**耗时与硬件/操作系统/并行度强相关**——OS（调度器/文件系统/进程创建开销/电源管理）、CPU 或并行度不同时各模式耗时可能数倍于此，仅作相对量级参考。跨机器回填可用 `--mode bench --update-docs` 自动更新模式对应测试量 + 下方两张环境耗时对照表。
>
> 注：`模式对应测试量` 表覆盖项数为 pytest 实测执行计数（含参数化展开），由 `--mode bench --update-docs` 自动回填；功能域/场景分组/单元分组/跨类等子表为 `scripts/collect-test-coverage.py` 收集快照（仅收集不执行，需在项目 `.venv` 环境运行以包含 pandas 依赖的测试文件）。`perf`/`security` 为定向 mode（`scenario_perf`/`scenario_security` 独立标记，手工/发布前运行）**不进 bench**，故不在本表，计数见 `collect-test-coverage.py` 输出（perf: 5 / security: 9）。

### 环境耗时对照

测试耗时随**硬件配置、操作系统与并行度**变化显著。下表对两台已实测机器（dragonball 2026-09-10 采集、stallman-NB1 2026-08-06 采集）做逐模式对照，便于在不同环境下粗估耗时量级。

> 跨机器采集：在新机器上运行 `.venv/bin/python scripts/test-runner.py --mode bench --machine-info`，脚本输出「采集环境属性」表（见下）与各模式实测耗时表；追加 `--update-docs` 则自动将本机环境属性与实测耗时写入下方两张表（按主机名匹配/新增列，同机覆盖历史实测）。

#### 采集环境属性

<!-- env-table:start -->
| 环境属性 | dragonball（2026-09-10 实测） | stallman-NB1（2026-08-06 实测） |
|:---------|:---------------------------|:---|
| 操作系统 | Linux | Windows |
| 系统版本 | 6.18.25-x64v3-xanmod1 | 11 |
| 架构 | x86_64 | AMD64 |
| 主机名 | dragonball | stallman-NB1 |
| CPU 型号 | 13th Gen Intel(R) Core(TM) i5-13500H | Intel64 Family 6 Model 142 Stepping 10, GenuineIntel |
| 物理核数 | 12 | 8 |
| 逻辑线程 | 16 | 8 |
| 内存 | 46.8 GiB | 7.9 GiB |
| 磁盘类型 | NVMe SSD | 未知 |
| 文件系统 | btrfs | 未知 |
| Python 版本 | 3.13.5 | 3.13.0 |
| 并行级别 | medium | medium |
| worker 数 | 8 | 4 |
| 采集日期 | 2026-09-10 | 2026-08-06 |
<!-- env-table:end -->

#### 各模式耗时对照

<!-- duration-table:start -->
| `--mode` | dragonball（2026-09-10 实测） | stallman-NB1（2026-08-06 实测） |
|:---------|:---------------------------:|:---:|
| `unit` | ~15s | ~4min |
| `standard` | ~15s | ~4min |
| `scenario` | ~18s | ~3min |
| `regression` | ~18s | ~3min |
| `verify,regression` | ~29s（verify+regression 顺序之和） | ~4min（verify+regression 顺序之和） |
| `dev-verify` | ~23s | ~2min |
| `verify` | ~11s | ~46s |
| `integration` | ~14s | ~1min |
| `edge` | ~13s | ~32s |
| `data` | ~2s | ~14s |
| `all` | ~21s | ~3min |
| `smoke` | ~2s | ~9s |
| `report` | ~11s | ~2min |
| `all_no_unit` | ~14s | ~1min |
| `scenario_extreme` | ~3s | ~9s |
| 数据更新时间 | 2026-09-10 | 2026-08-06 |
<!-- duration-table:end -->

> 两机差距因模式而异：多数模式 dragonball 较 stallman-NB1 快约 **10~20 倍**（如 `unit` ~13s vs ~4min、`all` ~22s vs ~3min），个别模式差约 4~20 倍（`edge` ~13s vs ~32s、`smoke` ~2s vs ~9s）。差距为 CPU 代差 + OS 差异 + 并行度差异的叠加（未逐项归因）。dragonball worker=8（medium=50% 核数），stallman-NB1 worker=4。

**其他环境量级参考**（估算，非实测）：
- **并行度**：耗时近似随 worker 数线性下降——当前 worker=8 改单线程执行时各并行模式约 ×5~8（`regression`/`edge`/`data`/`smoke`/`scenario_extreme` 等本为单线程的模式除外）
- **CPU 代差**：相同核数下较旧 CPU 慢约 1.5~3×
- **操作系统**：Windows 相对 Linux 慢约 1.5~3×（调度器/文件系统/进程创建开销/电源管理差异）
- **磁盘**：机械盘相对 NVMe SSD 慢约 2~4×（测试收集期密集读写 pyc/缓存/log 小文件）

## 功能域对应测试源

按被测试的源代码模块分组，方便定位"改了某段源码该跑什么测试"：

| 功能域 | 源模块（`src/python/`） | 对应测试文件（`src/test/`） | 覆盖项数 |
|:-------|:-----------------------|:---------------------------|:--------:|
| **数据源 Provider** | `providers/`(tencent, eastmoney, sina, tiantian, akshare_extras) | `unit/providers/test_{tencent,eastmoney,sina,tiantian,akshare_extras}.py` + `test_eastmoney_industry.py`（含 push2 估值字段 PE/PB 提取）+ `test_eastmoney_industry_rest.py`（行业数据 REST 接口）+ `test_sina_edge.py`/`test_tencent_edge.py` + `test_numeric_guard_regression.py`（非有限数值归一防线：各解析器非有限值拦截 + 合法输入行为不变） | 250 |
| **数据获取调度** | `fetcher/`(price, index, fund, industry, chain, history_diff, source_adapter, quote_adapters) | `unit/fetcher/test_fetcher*.py` + `test_fund*.py` + `test_chain*.py` + `test_chain_diagnostics.py`（链路失败原因采集与可读渲染）+ `test_fetcher_api_edge.py` + `test_source_adapter*.py`/`test_quote_adapter_parity.py`（数据源适配契约三段式与行情域三源等价性）+ `test_fetcher_industry.py`（估值字段网关：Provider Chain 路由 + push2 会话复用与按代码去重） | 330 |
| **新闻处理** | `providers/`(\*_news.py, news_aggregator, news_correlator, news_keywords, news_sources) | `unit/news/test_{akshare,cls,eastmoney,sina,wallstreetcn}_news.py` + `test_news_{aggregator,correlator,keywords,sources}.py` | 206 |
| **报告生成** | `report/`(excel_generator, excel_module_loader, excel_sheet_factory, excel_market_data, excel_content_sheets, excel_news_warning, excel_fund_deep_analysis, excel_llm_usage, html, chart_data_builder, pipeline_data_builder, category, penetration, fund_performance, fund_candidate, market_value, summary, summary_llm_usage, news_correlation, qdii_timezone, fund_concentration, fund_manager, style_factor_sheet, portfolio_history, portfolio_history_drawdown_sheet, history_snapshot, position_relationship_sheet, evolution_sheet, action_sheet, data_quality_sheet, decision_record, decision_llm_capture, decision_settlement, decision_review_block, signal_record, llm_quality, whatif_operations, whatif_sheet, whatif_writer) | `unit/report/` 共 83 文件（含 `__init__.py`）含 test_html_writer、test_html_template、test_html_report_structure（导航结构：章节锚点/目录折叠/五组分组导航）、test_correlation_sheet、test_correlation_html、test_drawdown_html_excel（组合历史走势与回撤章：走势表 + 回撤矩阵 + 危机区间标注）、test_tail_risk_wiring（尾部风险接线：pipeline 注入 + Excel 五行 + HTML 卡）、test_style_factor_sheet（风格与因子分析章：基金风格表 + 风格因子回归 + 行业 Beta 子表）、test_fund_candidate（基金业绩分析章候选基金比较子表：候选校验/截断/开关门控/比较维度/重合度复用）、test_valuation_temperature_wiring（估值分位+市场温度报告层接线：穿透估值列 + 汇总温度行）、test_pipeline_data_builder（管线数据契约：crisis_annotation/tail_risk/snapshot_diff 三键注册 + 键台账与附录 H 同步校验）、test_whatif_operations、test_whatif_sheet、test_whatif_html、test_whatif_writer、test_evolution_sheet、test_evolution_html、test_action_sheet、test_action_html、test_decision_record（决策复盘·确定性登记）、test_decision_llm_capture（决策复盘·LLM 建议表解析登记：误导性操作格不登记回归 + 结构化决策头优先/回落矩阵，受 `decision_header_parse` 门控）、test_decision_settlement（决策复盘·结算）、test_decision_review_block（决策复盘·复盘区块）、test_signal_record（确定性信号沉淀适配器：五类抽取 / 不可用占位跳过 / 聚合行与无代码行跳过 / 持仓级与组合级实时-非实时判定 / 幂等与开关无感）、test_llm_quality（模块级质量分级：A~F 口径/横幅注入/Excel 载体契约/章节标记与提示词一致性锁）、test_data_quality_sheet、test_data_status_message（降级事件可读失败原因：message 透传 + 矩阵渲染优先取原因 + 无原因逐字回落）、test_experimental_seams（管线实验挂载点：开关关闭无感/开关开启生效/下游异常只告警不外抛 + 接线次序守卫）、test_chart_data_builder、test_theme_js 等 | 1753 |
| **LLM 智能分析** | `llm/`(api, circuit_breaker, fingerprint, module_fingerprint, generators, markdown, pricing, prompts, session, skeleton, llm_content, cost_tracker, fallback, prompts_signals) | `unit/llm/`(含 API 路由/熔断/重试/降级/骨架/prompts/generators/辩论/cache、DeepSeek 峰谷定价/时段/时区/周末全天闲时规则/V4.1-Flash 正式模型名定价与 effort 族判定、信号预消化与结构化决策头提示词契约、模块指纹唯一事实来源同源校验（含提示词承载段与辩论综合键全文进键） 等) | 951 |
| **配置管理** | `config/`, `core/constants.py` | `unit/config/test_config*.py` + `test_features.py`（实验功能名解析 + 开关注册表活性：每项开关须有消费者 / 陈旧开关不得回归 / 无消费者键加载时告警） | 327 |
| **核心基础设施** | `core/`(cache, models, reader, registry, circuit_breaker, http_client, atomic_write, jsonl_store, num_utils, cassette, datasource_credential, market_hours, code_utils, filesystem, log_reader, doctor, decision_ledger, signal_ledger, decision_header)、`provider_registry.py`、`tui/handlers_*.py` | `unit/core/` 全部（含 `test_decision_ledger.py`/`test_decision_ledger_edge.py` 决策账本、`test_signal_ledger.py`/`test_signal_ledger_edge.py` 确定性信号账本、`test_jsonl_store.py` JSONL 原子原语、`test_num_utils_edge.py` 数值归一、`test_cassette*.py` 请求回放、`test_datasource_credential*.py` 凭据就绪、`test_decision_header.py`/`test_decision_header_edge.py` 决策头解析、`test_doctor.py` 系统自检（七组检查 / 永不抛异常契约 / 只读探测不留残留）、`*_edge.py`、`test_log_reader.py` 日志可视化）+ `unit/cache/` + `unit/handlers/`（含配置面板盒线等宽回归） | 1154 |
| **分析计算** | `analysis/`(liquidity, rebalance, fx_exposure, bond_yield, alignment_correction, drawdown_warning, drawdown_events, factor_exposure, industry_beta, correlation, crisis_annotation, tail_risk, portfolio_evolution, snapshot_diff, action_advisor, trade_discipline, rebalance_advisor, return_attribution, cost_flow, whatif, whatif_backtest, valuation_percentile, market_temperature, metrics) | `unit/analysis/test_{liquidity,rebalance,bond_yield,fx_exposure,alignment_correction,drawdown_warning,drawdown_events,factor_exposure,industry_beta}*.py` + `test_correlation.py` + `test_correlation_edge.py` + `test_crisis_annotation.py` + `test_tail_risk.py` + `test_tail_risk_edge.py` + `test_portfolio_evolution.py` + `test_snapshot_diff.py` + `test_snapshot_diff_edge.py` + `test_action_advisor.py` + `test_trade_discipline.py` + `test_rebalance_advisor.py` + `test_return_attribution.py` + `test_cost_flow.py`（成本流水：XIRR/成本分档/分红累计） + `test_valuation_percentile.py`/`test_valuation_percentile_edge.py`（价格分位代理：收盘价提取/解析解/三档刻度）+ `test_market_temperature.py`/`test_market_temperature_edge.py`（三因子合成温度计）+ `test_metrics.py`/`test_metrics_edge.py`（量化指标：夏普/卡玛/集中度/胜率/换手/风险贡献/波动率/组合 Beta）+ `test_whatif.py` + `test_whatif_backtest.py` + `test_whatif_backtest_edge.py` | 700 |
| **TUI 交互** | `tui/tui*.py`, `tui/handlers*.py`, `tui/tui_keys.py`, `tui/text_layout.py` | `unit/ui/test_{tui_keys,tui_handlers,tui_menu}.py` + `test_text_layout.py`（显示宽度口径 + 盒线面板等宽不变式）+ `test_handlers_log.py`（日志可视化 + 系统自检）+ `test_tui_edge.py` + `unit/startup/test_startup_wizard.py`（unit_ui 标记） | 172 |
| **CLI 命令行模式** | `cli/cli.py`, `cli/__main__.py`, `report/cli_progress.py` | `unit/cli/test_cli*.py`（含 doctor 子命令解析/处理/分派、模块入口退出码传递） | 110 |
| **Web 服务** | `web/`(server, app, handlers, config_edit, upload, progress, runs) | `unit/web/test_{upload,upload_edge,progress,runs,handlers,server}.py` + `test_config_edit.py`/`test_config_edit_edge.py`（启动防护 output_dir 写锁/端口占用、上传安全、进度事件缓冲、RunManager 运行管理、Flask 路由全链路、配置编辑：白名单完备/写分派/校验守卫/写前备份/极端输入）+ `test_smoke_web.py`（11 项全链路断言）+ `test_handlers.py` 日志/健康历史/自检端点（/api/logs + /api/health/history + /api/doctor）+ `test_health_credential.py`（健康检查凭据跳过态与就绪摘要） | 215 |
| **端到端业务场景** | 多模块组合（菜单 E/B/L → 读取 → 计算 → 报告 → LLM） | `scenario/`(basic/datetime/llm/perf/resilience/security 六子组，含 `scenario_extreme` 单列) + `integration/test_cli_integration.py` | 284 |

## 场景测试分组（scenario）

| 标记 | 覆盖场景 | 覆盖项数 | 参考测试类 |
|:-------|:---------|:--------:|:-----------|
| `scenario`（父标记） | 基础业务链路（S0a-S0d、S1-S33，其中基准指数对比由单元测试覆盖）+ 日期时间（T1-T21）+ LLM 场景/韧性场景子集 | **244** | 见下 |
| ├─ `scenario_basic` | 基础业务链路（S1-S5 + S0a/S0b/S0d + S21-S33 + C-P1b + 穿透分析 + 管线冒烟/指标注入 + 因子暴露管线） | **147** | |
| │  ├ `scenario_stock` | S1: 纯股票组合 | 3 | `test_scenario_basic_flows.py::TestScenarioStock` |
| │  ├ `scenario_fund` | S2: 纯基金组合 | 2 | `test_scenario_basic_flows.py::TestScenarioFund` |
| │  ├ `scenario_mixed_accounts` | S3: 混合多账户 | 1 | `test_scenario_basic_flows.py::TestScenarioMixedAccounts` |
| │  ├ `scenario_new_holdings` | S4: 新持仓无缓存 | 1 | `test_scenario_basic_flows.py::TestScenarioNewHoldings` |
| │  ├ `scenario_cache_hit` | S5: 缓存全命中 | 2 | `test_scenario_basic_flows.py::TestScenarioCacheHit` |
| │  └ 文件级分组 | S0a/S0b/S0d 持仓质量(13) · S21-S28 特殊品种(25) · S29-S33 操作行为(15) · SP1-SP10 穿透分析(37) · C-P1b 报告序号(17) · 管线冒烟(4) · 指标注入(17) · 因子暴露(5) · 基础链路其余(5) | 138 | `test_scenario_holdings_quality.py` 等 12 文件 |
| ├─ `scenario_resilience` | 异常容错 S6-S9 + 数据链路韧性 | **18** | |
| │  ├ `scenario_bond` | S6: 纯债券基金组合 | 3 | `test_scenario_resilience_flows.py::TestScenarioBond` |
| │  ├ `scenario_network_down` | S7: 网络中断降级 | 3 | `test_scenario_resilience_flows.py::TestScenarioNetworkDown` |
| │  ├ `scenario_single_holding` | S8: 单账户单持仓 | 3 | `test_scenario_resilience_flows.py::TestScenarioSingleHolding` |
| │  ├ `scenario_zero_cost` | S9: 零成本持仓 | 4 | `test_scenario_resilience_flows.py::TestScenarioZeroCost` |
| │  └ `test_chain_resilience.py` | 数据链路韧性（仅含 `scenario_resilience` 标记，不含 `scenario`） | 5 | `test_chain_resilience.py` |
| ├─ `scenario_llm` | LLM 场景组合 S11-S20（含 `scenario` 标记项 + 仅 `scenario_llm` 标记项） | **43** | `scenario/llm/test_llm_*.py` |
| └─ `scenario_datetime` | 日期/时间场景 T1-T21（跨月/跨年/调休/港股通假期/交易时段 TTL） | **41** | `test_datetime_scenarios.py` |
| `scenario_perf`（独立标记） | 端到端性能基准 | **5** | `test_e2e_perf.py` |
| `scenario_security`（独立标记） | 安全基线测试 | **9** | `test_security.py` |
| `scenario_extreme`（独立标记） | 极限场景 S0c/S10（超多持仓/极端份额/高精度净值/零值组合），不包含在 `scenario` 父标记中 | **9** | `test_scenario_extreme.py` |

## 单元测试分组（unit）

| 标记 | 覆盖模块 | 覆盖项数 |
|:-------|:---------|:--------:|
| `unit`（父标记） | 12 子组合计 | **6365** |
| ├─ `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等，含 push2 估值字段 PE/PB 提取 + 行业数据 REST 接口、非有限数值归一防线 safe_num 拦截） | 250 |
| ├─ `unit_fetcher` | 数据获取调度（价格/指数/基金/行业/API 异常/熔断预检/冷却恢复/链路失败原因采集 FailureDiagnostics/数据源适配契约三段式与行情域三源等价性/估值字段网关（Provider Chain 路由 + push2 会话复用与按代码去重）） | 330 |
| ├─ `unit_llm` | LLM 模块（API 路由/熔断/指纹/骨架/prompts/generators/llm_content 写入/Token 成本跟踪/降级回退/DeepSeek 峰谷定价含时段判定/时段/时区/周末全天闲时规则设置/V4.1-Flash 正式模型名定价与 effort 族判定/信号预消化（资金流方向标注与排名/信号块/缓存后缀）/结构化决策头提示词契约（开关关闭逐字节不变/契约可解析/指纹换键）/模块指纹唯一事实来源同源校验（含提示词承载段与辩论综合键全文进键）） | 951 |
| ├─ `unit_news` | 新闻源（新浪/东方财富/财联社/华尔街见闻） | 206 |
| ├─ `unit_report` | 报表生成（Excel/HTML 各页签写入、基金深度分析模块、风格与因子分析章（风格表 + 因子回归 + 行业 Beta 子表）、基金业绩分析章候选基金比较子表（candidate_compare 默认关）、数据降级/占位/可用性矩阵、调仓 What-if/组合演进/行动建议双端呈现、数据质量仪表盘、尾部风险接线、估值分位+市场温度接线、管线数据契约（含键台账与附录 H 同步校验）、HTML 分组导航折叠、Chart.js 图表数据构建/裁剪、暗色模式 theme.js、JS 资产内嵌单文件自包含、决策复盘（确定性/LLM 登记 + 结算 + 复盘区块 + 误导性操作格不登记回归 + 结构化决策头优先/回落矩阵）、模块级质量分级（A~F 口径/横幅注入 + Excel 载体契约 + 章节标记与提示词一致性锁）、确定性信号沉淀适配器（五类抽取/不可用跳过/实时-非实时判定/幂等与开关）、降级事件可读失败原因（record message 透传 + 矩阵渲染优先取原因）、管线实验挂载点（开关关闭无感/开关开启生效/下游异常只告警不外抛 + 接线次序守卫）） | 1753 |
| ├─ `unit_config` | 配置管理（config/llm_settings/llm_key；含报告序号配置校验、enable_action 等板层开关、candidate_compare 访问器/comparison_candidates 校验、成本流水 cost_lots 开关访问器、实验功能名解析（注册表驱动）、开关注册表活性（每项开关须有消费者 / 陈旧开关不得回归 / 无消费者键加载时合并告警）、LLM Provider 凭据分离校验（内联 api_key 硬拒绝 / credentials_ref 必填 / model 条目级覆盖透传）） | 327 |
| ├─ `unit_core` | 核心基础设施（缓存/数据模型/读者/注册表/统一熔断网关/持仓追踪器/批处理调度/命令处理器/日志读取 read_log/tail_log/parse_log/决策账本 decision_ledger 事件持久化与结算折叠/信号账本 signal_ledger 五类评级登记与幂等折叠/JSONL 原子原语 jsonl_store/文件写入原子原语 atomic_write（新建/覆盖/父目录创建/失败返回 False 且保留原内容/Windows 占用回退）/数值归一原语 num_utils/请求回放引擎 cassette/数据源凭据声明 datasource_credential/决策头解析 decision_header 词表与归一判据/系统自检 doctor 环境-配置-目录-开关-数据源适配-数据源凭据-数据源七组检查（含「永不抛异常」契约与目录探针隔离）/配置面板盒线等宽回归） | 1154 |
| ├─ `unit_analysis` | 分析计算（流动性/再平衡/汇率/口径修正/回撤预警/回撤事件/因子暴露/行业 Beta/相关性矩阵/危机区间标注/尾部风险统计/组合演进/快照差异摘要/行动建议/交易纪律/调仓建议可行化层/收益归因/成本流水（XIRR/成本分档/分红累计）/估值分位（价格分位代理）/市场温度（三因子合成）/量化指标（夏普/卡玛/集中度/胜率/换手/风险贡献/波动率/组合 Beta）/调仓 What-if 时序回测） | 700 |
| ├─ `unit_cli` | CLI 命令行模式（参数解析/路由/退出码/日志/view-logs 子命令/whatif 子命令/doctor 子命令（--offline/--timeout、config 之前分派、_EXIT_PARTIAL 退出码）/模块入口退出码传递 run_cli/实验功能开关 `--experiment`（注册表驱动解析与本次运行增量启用，含早返回命令）） | 110 |
| ├─ `unit_ui` | TUI 交互（菜单/键盘/进度/错误提示/日志可视化查看日志与健康历史/受实验开关约束的菜单项门控 `_apply_feature_gates`/文本显示宽度与盒线面板等宽不变式） | 172 |
| ├─ `unit_scripts` | scripts/ 工程脚本（历史痕迹检查工具自检/豁免/补强模式/回归场景元描述豁免/多行 docstring 提取/任务编号一致性检查/语义命名索引双向校验/3 类暗号匹配自检/机器信息采集与耗时表格渲染/环境耗时对照文档自动更新/失败用例提取 data-jsonblob 回归） | 197 |
| └─ `unit_web` | Web 服务（启动防护 output_dir 写锁/端口占用、上传安全、进度事件缓冲、RunManager 运行管理、Flask 路由全链路、日志/健康历史端点（/api/logs + /api/health/history + /api/doctor）、Web 配置编辑（镜像 TUI 可编辑配置全集/白名单/备份/写入分派/实验开关注册表驱动）、状态区系统信息组装（含持仓/输出/新闻上限/匿名化/隐私摘要/自检卡片可见性）、首页标题应用名称+版本、Web 冒烟脚本载体） | 215 |

## 跨类标记

| 标记 | 覆盖范围 | 覆盖项数 |
|:-------|:---------|:--------:|
| `llm` | 全部 LLM 相关（带 `llm` 跨类标记），**全部为 mock 测试，无需真实 API key** | **753** |
| `smoke` | 关键节点冒烟覆盖，共 26 项 | **26** |
| `edge` | 异常/边界场景（含熔断冷却探针） | **852** |
| `data` | 数据正确性验证 | **69** |

详细方法名和验证点见 `pytest src/test/ -m "smoke" -v` 输出。



