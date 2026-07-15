# 测试覆盖统计

> 文档版本：v0.6.0

> ⚠ 以下测试项数为撰写时的快照值，实际计数随版本迭代而变化。精确统计请以 `scripts/test_runner.py` 的 MODES 字典为准，或运行 `pytest src/test/ --collect-only -q` 获取实时计数。

按不同的 `--mode` / pytest 标记统计当前测试覆盖规模：

### 模式对应测试量

| `--mode` 值 | 覆盖项数 | 典型耗时 |
|:------------|:--------:|:--------:|
| `unit` | 2768 | ~25s |
| `standard` | 2285 | ~25s |
| `scenario` | **267** | **~6min** |
| `regression` | **267** | **~6min** |
| `dev-verify` | **862** | **~1min** |
| `verify` | **1832** | **~8min** |
| `integration` | 296 | ~50s |
| `edge` | 352 | ~15s |
| `data` | 69 | ~10s |
| `all` | **3073** | **~10min** |
| `smoke` | 24 | ~2s |
| `report` | **1013** | ~15s |
| `all_no_unit` | 305 | **~7min** |
| `scenario_extreme` | **9** | **~1min 45s** |

> 注：`all` 模式收集总数 3073 项，但因 12 项为 Linux 专用键盘测试（`test_tui.py::TestGetKeyLinux`），在 Windows 上实跑约为 3061 项。

### 功能域对应测试源

按被测试的源代码模块分组，方便定位"改了某段源码该跑什么测试"：

| 功能域 | 源模块（`src/python/`） | 对应测试文件（`src/test/`） | 覆盖项数 |
|:-------|:-----------------------|:---------------------------|:--------:|
| **数据源 Provider** | `providers/`(tencent, eastmoney, sina, tiantian, akshare_extras) | `unit/providers/test_{tencent,eastmoney,sina,tiantian,akshare_extras}.py` + `test_eastmoney_industry.py` | 191 |
| **数据源注册中心** | `provider_registry.py` | `unit/core/test_provider_registry.py` + `test_phase_timeout.py` + `test_market_value_strategy_edge.py` | 53 |
| **数据获取调度** | `fetcher/`(price, index, fund, industry, chain, history_diff) | `unit/fetcher/test_fetcher*.py` + `test_fund*.py` + `test_chain*.py` + `test_api_edge.py` | 204 |
| **新闻处理** | `providers/`(\*_news.py, news_aggregator, news_correlator, news_keywords, news_sources) | `unit/news/test_{akshare,cls,eastmoney,sina,wallstreetcn}_news.py` + `test_news_{aggregator,correlator,keywords,sources}.py` | 176 |
| **报告生成** | `report/`(excel_generator, excel_module_loader, excel_sheet_factory, excel_market_data, excel_content_sheets, excel_news_warning, excel_b_series, excel_llm_usage, html, category, penetration, fund_performance, market_value, summary, summary_llm_usage, early_warning, news_correlation, qdii_timezone, fund_concentration, fund_manager, fund_overlap, fund_style, portfolio_history, history_snapshot) | `unit/report/` 共 41 文件含 test_html_writer、test_html_template 等 | 1039 |
| **LLM 智能分析** | `llm/`(api, circuit_breaker, fingerprint, generators, markdown, pricing, prompts, session, skeleton, llm_content) | `unit/llm/`(19 文件) + `scenario/llm/test_llm_scenarios.py` | 512 |
| **核心基础设施** | `cache.py`, `models.py`, `reader.py`, `registry.py`, `http_client.py`, `market_hours.py` | `unit/core/test_{cache,models,reader,registry,http_client,market_hours}.py` + `*_edge.py` | 438 |
| **配置管理** | `config.py`, `constants.py` | `unit/config/test_config*.py` | 76 |
| **TUI 交互** | `tui*.py`, `handlers.py`, `main.py` | `unit/ui/test_{handlers,tui,tui_handlers,tui_menu,log_sanitize}.py` | 164 |
| **命令处理器** | `handlers_cache.py`, `handlers_report.py` | `unit/handlers/test_{handlers_cache,handlers_report}.py` | 31 |
| **端到端业务场景** | 多模块组合（菜单 E/B/L → 读取 → 计算 → 报告 → LLM） | `scenario/`(basic 含 6 文件, resilience, llm, datetime 共 10 文件) | 238 |

### 场景测试分组（scenario）

| 标记 | 覆盖场景 | 覆盖项数 | 参考测试类 |
|:-------|:---------|:--------:|:-----------|
| `scenario`（父标记） | S0a/S0b/S0d + S1-S34 + T1-T21 全量业务场景（含 S0c+S10） | **276** | 见下 |
| ├─ `scenario_basic` | 基础业务链路 S1-S5 + S0a/S0b/S0d + S21-S34 + P1p | **122** | |
| │  ├ `scenario_stock` | S1: 纯股票组合 | 3 | `test_integration.py::TestScenarioS1` |
| │  ├ `scenario_fund` | S2: 纯基金组合 | 2 | `test_integration.py::TestScenarioS2` |
| │  ├ `scenario_mixed_accounts` | S3: 混合多账户 | 1 | `test_integration.py::TestScenarioS3` |
| │  ├ `scenario_new_holdings` | S4: 新持仓无缓存 | 1 | `test_integration.py::TestScenarioS4` |
| │  ├ `scenario_cache_hit` | S5: 缓存全命中 | 2 | `test_integration.py::TestScenarioS5` |
| │  ├ `scenario_special_securities` | S21-S28: 特殊品种（港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债） | 27 | `test_integration.py`（多类） |
| │  ├ `scenario_s0_holdings_quality` | S0a/S0b/S0d: 持仓质量（清仓/同名多份额/特殊字符；S0c 已移至 scenario_extreme） | **13** | `test_scenario_holdings_quality.py::TestS0a/TestS0b/TestS0d` |
| │  ├ `scenario_section_order` | C-P1b: 报告序号可配置合并场景（含自定义/部分配置/未知 key） | 6 | `test_scenario_section_order.py` |
| │  └ `—` | S29-S34: 操作行为（分红送转/定投摊薄/部分卖出/跨账户转仓/新股待上市）+ 组合历史走势基准指数对比 | 15 | `test_scenario_operational_behavior.py` |
| ├─ `scenario_resilience` | 异常容错场景 S6-S9（S10 已移至 scenario_extreme） | **13** | |
| │  ├ `scenario_bond` | S6: 纯债券基金组合 | 3 | `test_integration_scenarios.py::TestScenarioBond` |
| │  ├ `scenario_network_down` | S7: 网络中断降级 | 3 | `test_integration_scenarios.py::TestScenarioNetworkDown` |
| │  ├ `scenario_single_holding` | S8: 单账户单持仓 | 3 | `test_integration_scenarios.py::TestScenarioSingleHolding` |
| │  └ `scenario_zero_cost` | S9: 零成本持仓 | 4 | `test_integration_scenarios.py::TestScenarioZeroCost` |
| ├─ `scenario_extreme`（独立标记） | 极限场景 S0c+S10（超多持仓/极端份额/高精度净值/零值组合），不包含在 `scenario` 父标记中 | **9** | `test_scenario_extreme.py::TestS0cLargeHoldings/TestScenarioExtreme` |
| ├─ `scenario_llm` | LLM 场景组合 S11-S20（10 个类共 32 项，其中 24 项同时标记为 llm） | 32 | `test_llm_scenarios.py`（TestS11~S20，每场景一独立类） |
| └─ `scenario_datetime` | 日期/时间场景 T1-T21（含跨月/跨年/调休/港股通假期） | 100 | |
|    ├ T1-T2/T4-T5 | 交易时段 TTL（盘中短 TTL / 盘前/盘后/非交易日长 TTL） | 8 | `test_datetime_scenarios.py::TestGetTtlMarketAware` |
|    ├ T3 | 午间休市边界 | 7 | `test_datetime_scenarios.py::TestIsMiddayBreak` |
|    ├ T6 | 长假边界（国庆/跨年/缓存） | 6 | `test_datetime_scenarios.py::TestLastTradingDayExtended` + `TestGetTradingCalendarCache` |
|    ├ T7-T11 | 产品类型分类（场外/QDII/ETF/股票/混合） | 10 | `test_datetime_scenarios.py::TestClassifyHoldings` |
|    ├ T12 | 盘中转盘后 TTL 切换 | 2 | `test_datetime_scenarios.py::TestGetTtlTransition` |
|    ├ T13 | 时段切换缝隙边界 | — | `test_market_hours.py`（分钟级边界） |
|    ├ T14 | 首次启动+非交易日 | — | `test_datetime_scenarios.py::TestFirstLaunchNonTradingDay` |
|    ├ T15-T16 | 盘中断网/盘后断网 fetch TTL | — | `test_datetime_scenarios.py::TestFetchMarketDataMarketAware` |
|    ├ T17 | 国内/美股指数盘前盘后 | — | `test_market_hours.py::TestIndexMarketHours` |
|    └ T18-T21 | 跨境 ETF 溢价率、非 T 日汇率、港股通假期、多重 N/A 叠加 | — | `test_datetime_scenarios.py::TestCrossBorderEtfPremium` + `TestHolidayShiftCalculation` + `TestMultiHkConnectHoliday` + `TestMultiNAStacking` |

### 单元测试分组（unit）

| 标记 | 覆盖模块 | 覆盖项数 |
|:-------|:---------|:--------:|
| `unit`（父标记） | 9 子组合计 | **2768** |
| ├─ `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等） | 191 |
| ├─ `unit_fetcher` | 数据获取调度（价格/指数/基金/行业/API 异常/熔断预检/冷却恢复） | 204 |
| ├─ `unit_llm` | LLM 模块（API 路由/熔断/指纹/骨架/prompts/generators/llm_content 写入） | 480 |
| ├─ `unit_news` | 新闻源（新浪/东方财富/财联社/华尔街见闻） | 176 |
| ├─ `unit_report` | 报表生成（Excel/HTML 各页签写入、B 系列基金深度分析模块、数据降级/占位；含 65 项 data 标记测试） | 1039 |
| ├─ `unit_config` | 配置管理（config/llm_settings/llm_key；含报告序号配置校验） | 76 |
| ├─ `unit_core` | 核心基础设施（缓存/数据模型/读者/注册表/缓存命令处理器/报告命令处理器；含注册表测试） | 438 |
| └─ `unit_ui` | TUI 交互（菜单/键盘/进度/错误提示） | 164 |

### 跨类标记

| 标记 | 覆盖范围 | 覆盖项数 |
|:-------|:---------|:--------:|
| `llm` | 全部 LLM 相关（unit_llm 480 + scenario_llm 32，其中 432 项标有 llm 标记），**全部为 mock 测试，无需真实 API key** | **432** |
| `smoke` | 6 个关键节点各 4 项，共 24 项 | **24** |
| `edge` | 异常/边界场景（含熔断冷却探针） | **335** |
| `data` | 数据正确性验证 | **69** |

详细方法名和验证点见 `pytest src/test/ -m "smoke" -v` 输出。


