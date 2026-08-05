# 测试覆盖统计
> 文档版本：0.10.6-dev

> ⚠ 以下测试项数为撰写时的快照值，实际计数随版本迭代而变化。精确统计请以 `scripts/test_runner.py` 的 MODES 字典为准，或运行 `pytest src/test/ --collect-only -q` 获取实时计数。

按不同的 `--mode` / pytest 标记统计当前测试覆盖规模：

## 模式对应测试量

| `--mode` 值 | 覆盖项数 | 典型耗时 |
|:------------|:--------:|:--------:|
| `unit` | **4672** | ~30s |
| `standard` | **4065** | ~30s |
| `scenario` | **241** | **~6min** |
| `regression` | **241** | **~6min** |
| `dev-verify` | **1706** | **~1min** |
| `verify` | **3016** | **~1min** |
| `integration` | **281** | **~50s** |
| `edge` | 540 | ~15s |
| `data` | 69 | ~10s |
| `all` | **4981** | **~10min** |
| `smoke` | 26 | ~2s |
| `report` | **1465** | ~15s |
| `all_no_unit` | 309 | **~7min** |
| `scenario_extreme` | **9** | **~1min 45s** |

> 注：以下统计为 `def test_` 函数级计数（不含参数化展开）。`all` 模式全量 4981 项（2026-08-05 实时收集快照，`scripts/collect-test-coverage.py` 生成，需在项目 `.venv` 环境运行以包含 pandas 依赖的测试文件）。

## 功能域对应测试源

按被测试的源代码模块分组，方便定位"改了某段源码该跑什么测试"：

| 功能域 | 源模块（`src/python/`） | 对应测试文件（`src/test/`） | 覆盖项数 |
|:-------|:-----------------------|:---------------------------|:--------:|
| **数据源 Provider** | `providers/`(tencent, eastmoney, sina, tiantian, akshare_extras) | `unit/providers/test_{tencent,eastmoney,sina,tiantian,akshare_extras}.py` + `test_eastmoney_industry.py`（含 push2 估值字段 PE/PB 提取）+ `test_eastmoney_industry_rest.py`（行业数据 REST 接口）+ `test_sina_edge.py`/`test_tencent_edge.py` | 211 |
| **数据获取调度** | `fetcher/`(price, index, fund, industry, chain, history_diff) | `unit/fetcher/test_fetcher*.py` + `test_fund*.py` + `test_chain*.py` + `test_fetcher_api_edge.py` | 248 |
| **新闻处理** | `providers/`(\*_news.py, news_aggregator, news_correlator, news_keywords, news_sources) | `unit/news/test_{akshare,cls,eastmoney,sina,wallstreetcn}_news.py` + `test_news_{aggregator,correlator,keywords,sources}.py` | 188 |
| **报告生成** | `report/`(excel_generator, excel_module_loader, excel_sheet_factory, excel_market_data, excel_content_sheets, excel_news_warning, excel_fund_deep_analysis, excel_llm_usage, html, chart_data_builder, category, penetration, fund_performance, fund_candidate, market_value, summary, summary_llm_usage, news_correlation, qdii_timezone, fund_concentration, fund_manager, style_factor_sheet, portfolio_history, portfolio_history_drawdown_sheet, history_snapshot, position_relationship_sheet, evolution_sheet, action_sheet, data_quality_sheet, whatif_operations, whatif_sheet, whatif_writer) | `unit/report/` 共 67 文件含 test_html_writer、test_html_template、test_html_report_structure（导航结构：章节锚点/目录折叠/五组分组导航）、test_correlation_sheet、test_correlation_html、test_drawdown_html_excel（组合历史走势与回撤章：走势表 + 回撤矩阵 + 危机区间标注）、test_tail_risk_wiring（尾部风险接线：pipeline 注入 + Excel 五行 + HTML 卡）、test_style_factor_sheet（风格与因子分析章：基金风格表 + 风格因子回归 + 行业 Beta 子表）、test_fund_candidate（基金业绩分析章候选基金比较子表：候选校验/截断/开关门控/比较维度/重合度复用）、test_valuation_temperature_wiring（估值分位+市场温度报告层接线：穿透估值列 + 汇总温度行）、test_whatif_operations、test_whatif_sheet、test_whatif_html、test_whatif_writer、test_evolution_sheet、test_evolution_html、test_action_sheet、test_action_html、test_data_quality_sheet、test_chart_data_builder、test_theme_js 等 | 1465 |
| **LLM 智能分析** | `llm/`(api, circuit_breaker, fingerprint, generators, markdown, pricing, prompts, session, skeleton, llm_content, cost_tracker, fallback) | `unit/llm/`(含 API 路由/熔断/重试/降级/骨架/prompts/generators/辩论/cache 等) | 728 |
| **配置管理** | `config/`, `core/constants.py` | `unit/config/test_config*.py` | 288 |
| **核心基础设施** | `core/`(cache, models, reader, registry, http_client, market_hours, code_utils, filesystem)、`provider_registry.py`、`tui/handlers_*.py` | `unit/core/` 全部 + `unit/cache/` + `unit/handlers/`（含 `*_edge.py`） | 565 |
| **分析计算** | `analysis/`(liquidity, rebalance, fx_exposure, bond_yield, alignment_correction, drawdown_warning, drawdown_events, factor_exposure, industry_beta, correlation, crisis_annotation, tail_risk, portfolio_evolution, snapshot_diff, action_advisor, trade_discipline, rebalance_advisor, return_attribution, cost_flow, whatif, whatif_backtest, valuation_percentile, market_temperature, metrics) | `unit/analysis/test_{liquidity,rebalance,bond_yield,fx_exposure,alignment_correction,drawdown_warning,drawdown_events,factor_exposure,industry_beta}*.py` + `test_correlation.py` + `test_correlation_edge.py` + `test_crisis_annotation.py` + `test_tail_risk.py` + `test_tail_risk_edge.py` + `test_portfolio_evolution.py` + `test_snapshot_diff.py` + `test_snapshot_diff_edge.py` + `test_action_advisor.py` + `test_trade_discipline.py` + `test_rebalance_advisor.py` + `test_return_attribution.py` + `test_cost_flow.py`（成本流水：XIRR/成本分档/分红累计） + `test_valuation_percentile.py`/`test_valuation_percentile_edge.py`（价格分位代理：收盘价提取/解析解/三档刻度）+ `test_market_temperature.py`/`test_market_temperature_edge.py`（三因子合成温度计）+ `test_metrics.py`/`test_metrics_edge.py`（量化指标：夏普/卡玛/集中度/胜率/换手/风险贡献/波动率/组合 Beta）+ `test_whatif.py` + `test_whatif_backtest.py` + `test_whatif_backtest_edge.py` | 667 |
| **TUI 交互** | `tui/tui*.py`, `tui/handlers*.py`, `tui/tui_keys.py` | `unit/ui/test_{tui_keys,tui_handlers,tui_menu}.py` + `test_tui_edge.py` + `unit/startup/test_startup_wizard.py`（unit_ui 标记） | 135 |
| **CLI 命令行模式** | `cli/cli.py`, `report/cli_progress.py` | `unit/cli/test_cli*.py` | 56 |
| **端到端业务场景** | 多模块组合（菜单 E/B/L → 读取 → 计算 → 报告 → LLM） | `scenario/`(basic/datetime/llm/perf/resilience/security 六子组，含 `scenario_extreme` 单列) + `integration/test_cli_integration.py` | 281 |

## 场景测试分组（scenario）

| 标记 | 覆盖场景 | 覆盖项数 | 参考测试类 |
|:-------|:---------|:--------:|:-----------|
| `scenario`（父标记） | 基础业务链路（S0a-S0d、S1-S33，其中基准指数对比由单元测试覆盖）+ 日期时间（T1-T21）+ LLM 场景/韧性场景子集 | **241** | 见下 |
| ├─ `scenario_basic` | 基础业务链路（S1-S5 + S0a/S0b/S0d + S21-S33 + C-P1b + 穿透分析 + 管线冒烟/指标注入 + 因子暴露管线） | **144** | |
| │  ├ `scenario_stock` | S1: 纯股票组合 | 3 | `test_scenario_basic_flows.py::TestScenarioStock` |
| │  ├ `scenario_fund` | S2: 纯基金组合 | 2 | `test_scenario_basic_flows.py::TestScenarioFund` |
| │  ├ `scenario_mixed_accounts` | S3: 混合多账户 | 1 | `test_scenario_basic_flows.py::TestScenarioMixedAccounts` |
| │  ├ `scenario_new_holdings` | S4: 新持仓无缓存 | 1 | `test_scenario_basic_flows.py::TestScenarioNewHoldings` |
| │  ├ `scenario_cache_hit` | S5: 缓存全命中 | 2 | `test_scenario_basic_flows.py::TestScenarioCacheHit` |
| │  └ 文件级分组 | S0a/S0b/S0d 持仓质量(13) · S21-S28 特殊品种(25) · S29-S33 操作行为(15) · SP1-SP10 穿透分析(37) · C-P1b 报告序号(17) · 管线冒烟(4) · 指标注入(14) · 因子暴露(5) · 基础链路其余(5) | 135 | `test_scenario_holdings_quality.py` 等 12 文件 |
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
| `unit`（父标记） | 11 子组合计 | **4672** |
| ├─ `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等，含 push2 估值字段 PE/PB 提取 + 行业数据 REST 接口） | 211 |
| ├─ `unit_fetcher` | 数据获取调度（价格/指数/基金/行业/API 异常/熔断预检/冷却恢复） | 248 |
| ├─ `unit_llm` | LLM 模块（API 路由/熔断/指纹/骨架/prompts/generators/llm_content 写入/Token 成本跟踪/降级回退） | 728 |
| ├─ `unit_news` | 新闻源（新浪/东方财富/财联社/华尔街见闻） | 188 |
| ├─ `unit_report` | 报表生成（Excel/HTML 各页签写入、基金深度分析模块、风格与因子分析章（风格表 + 因子回归 + 行业 Beta 子表）、基金业绩分析章候选基金比较子表（candidate_compare 默认关）、数据降级/占位/可用性矩阵、调仓 What-if/组合演进/行动建议双端呈现、数据质量仪表盘、尾部风险接线、估值分位+市场温度接线、HTML 分组导航折叠、Chart.js 图表数据构建/裁剪、暗色模式 theme.js） | 1465 |
| ├─ `unit_config` | 配置管理（config/llm_settings/llm_key；含报告序号配置校验、enable_action 等板层开关、candidate_compare 访问器/comparison_candidates 校验、成本流水 cost_lots 开关访问器） | 288 |
| ├─ `unit_core` | 核心基础设施（缓存/数据模型/读者/注册表/熔断/持仓追踪器/批处理调度/命令处理器） | 565 |
| ├─ `unit_analysis` | 分析计算（流动性/再平衡/汇率/口径修正/回撤预警/回撤事件/因子暴露/行业 Beta/相关性矩阵/危机区间标注/尾部风险统计/组合演进/快照差异摘要/行动建议/交易纪律/调仓建议可行化层/收益归因/成本流水（XIRR/成本分档/分红累计）/估值分位（价格分位代理）/市场温度（三因子合成）/量化指标（夏普/卡玛/集中度/胜率/换手/风险贡献/波动率/组合 Beta）/调仓 What-if 时序回测） | 667 |
| ├─ `unit_cli` | CLI 命令行模式（参数解析/路由/退出码/日志/whatif 子命令） | 56 |
| ├─ `unit_ui` | TUI 交互（菜单/键盘/进度/错误提示） | 135 |
| └─ `unit_scripts` | scripts/ 工程脚本（历史痕迹检查工具自检/豁免/补强模式/回归场景元描述豁免/多行 docstring 提取/任务编号一致性检查/3 类暗号匹配自检） | 121 |

## 跨类标记

| 标记 | 覆盖范围 | 覆盖项数 |
|:-------|:---------|:--------:|
| `llm` | 全部 LLM 相关（带 `llm` 跨类标记），**全部为 mock 测试，无需真实 API key** | **586** |
| `smoke` | 关键节点冒烟覆盖，共 26 项 | **26** |
| `edge` | 异常/边界场景（含熔断冷却探针） | **540** |
| `data` | 数据正确性验证 | **69** |

详细方法名和验证点见 `pytest src/test/ -m "smoke" -v` 输出。



