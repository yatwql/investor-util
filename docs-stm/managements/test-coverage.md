# 测试覆盖统计

> ⚠ 以下测试项数为撰写时的快照值，实际计数随版本迭代而变化。精确统计请以 `scripts/test_runner.py` 的 MODES 字典为准，或运行 `pytest src/test/ --collect-only -q` 获取实时计数。

按不同的 `--mode` / pytest 标记统计当前（2026-07-09）测试覆盖规模：

### 模式对应测试量

| `--mode` 值 | 覆盖项数 | 典型耗时 |
|:------------|:--------:|:--------:|
| `unit` | 2589 | ~22s |
| `standard` | 2204 | ~22s |
| `scenario` | 277 | ~35s |
| `regression` | 277 | ~35s |
| `verify` | 1057 | ~5min |
| `integration` | 306 | ~50s |
| `edge` | 318 | ~15s |
| `data` | 65 | ~10s |
| `all` | 2895 | ~85s |
| `smoke` | 24 | ~2s |
| `report` 🆕 | ≈958 | ~15s |
| `all_no_unit` 🆕 | 306 | ~55s |

> 注：`all` 模式收集总数 2889 项，但因 12 项为 Linux 专用键盘测试（`test_tui.py::TestGetKeyLinux`），在 Windows 上实跑结果为 2877 passed / 12 skipped。
> 🆕 `report` 模式为 A5 新增，标记 `unit_report`（≈958 项），供报告模块开发期快速验证。
> 🆕 `all_no_unit` 模式标记 `not unit`（306 项），包含 scenario/integration/edge/data/smoke/report 等非单元测试。
> 说明：单元密集型模式（`unit`/`standard`/`verify`/`all`/`report`）默认启用 `--parallel medium` 自动并行，"典型耗时"即 medium 并行耗时；场景/边缘/冒烟等轻量模式保持单线程（不并行），避免进程调度开销。
> v0.3.0 测试增量覆盖补全（52 项新增），全量 2721 项（2709 passed / 12 skipped for Windows）。
> v0.3.1 Provider Chain 熔断架构升级（13 项新增：熔断预检 9 项 + 冷却探针 4 项 edge），全量 2726 项（2714 passed / 12 skipped for Windows）。
> v0.3.2 核心模块单元测试补全（96 项新增：generators 21 + prompts 44 + handlers_cache 18 + handlers_report 13），全量 2822 项（2810 passed / 12 skipped for Windows）。
> v0.3.2e 数据降级重构 Step A~E（45 项新增：provider_registry 37 + phase_timeout 8；原 test_config 单元从 standard 迁移至 unit），全量 2895 项。
> v0.3.3 测试断言同步修复（R-192/R-193：6 项测试对齐实现文案），全量 2895 项。

### 功能域对应测试源

按被测试的源代码模块分组，方便定位"改了某段源码该跑什么测试"：

| 功能域 | 源模块（`src/python/`） | 对应测试文件（`src/test/`） | 覆盖项数 |
|:-------|:-----------------------|:---------------------------|:--------:|
| **数据源 Provider** | `providers/`(tencent, eastmoney, sina, tiantian, akshare_extras) | `unit/providers/test_{tencent,eastmoney,sina,tiantian,akshare_extras}.py` + `test_eastmoney_industry.py` | 166 |
| **数据源注册中心** | `provider_registry.py` | `unit/core/test_provider_registry.py` + `test_phase_timeout.py` + `test_market_value_strategy_edge.py` | 53 |
| **数据获取调度** | `fetcher/`(price, index, fund, industry, chain) | `unit/fetcher/test_fetcher*.py` + `test_fund*.py` + `test_chain*.py` + `test_api_edge.py` | 186 |
| **新闻处理** | `providers/`(\*_news.py, news_aggregator, news_correlator, news_keywords, news_sources) | `unit/news/test_{akshare,cls,eastmoney,sina,wallstreetcn}_news.py` + `test_news_{aggregator,correlator,keywords,sources}.py` | 176 |
| **报告生成** | `report/`(excel, html, category, penetration, fund_performance, market_value, summary, early_warning, news_correlation, qdii_timezone, fund_concentration, fund_manager, fund_overlap, fund_style) | `unit/report/` 共 25 文件含 test_html_writer、test_html_template 等 | ≈945 |
| **LLM 智能分析** | `llm/`(api, circuit_breaker, fingerprint, generators, markdown, pricing, prompts, session, skeleton, llm_content) | `unit/llm/`(12 文件) + `scenario/llm/test_llm_scenarios.py` | 440 |
| **核心基础设施** | `cache.py`, `models.py`, `reader.py`, `registry.py`, `http_client.py`, `market_hours.py` | `unit/core/test_{cache,models,reader,registry,http_client,market_hours}.py` + `*_edge.py` | 342 |
| **配置管理** | `config.py`, `constants.py` | `unit/config/test_config*.py` | 75 |
| **TUI 交互** | `tui*.py`, `handlers.py`, `main.py` | `unit/ui/test_{handlers,tui,tui_handlers,tui_menu,log_sanitize}.py` | 165 |
| **命令处理器** | `handlers_cache.py`, `handlers_report.py` | `unit/handlers/test_{handlers_cache,handlers_report}.py` | 31 |
| **端到端业务场景** | 多模块组合（菜单 E/H/B/L → 读取 → 计算 → 报告 → LLM） | `scenario/`(basic 含 5 文件, resilience, llm, datetime 共 9 文件) | 240 |

### 场景测试分组（scenario）

| 标记 | 覆盖场景 | 覆盖项数 |
|:-------|:---------|:--------:|
| `scenario`（父标记） | S0a-S0d + S1-S33 + T1-T21 全量业务场景 | **277** |
| ├─ `scenario_basic` | 基础业务链路 S1-S5 + S0a-S0d + S21-S33 + P1p | 97 |
| │  ├ `scenario_stock` | S1: 纯股票组合 | 3 |
| │  ├ `scenario_fund` | S2: 纯基金组合 | 2 |
| │  ├ `scenario_mixed_accounts` | S3: 混合多账户 | 1 |
| │  ├ `scenario_new_holdings` | S4: 新持仓无缓存 | 1 |
| │  ├ `scenario_cache_hit` | S5: 缓存全命中 | 2 |
| │  ├ `scenario_special_securities` | S21-S28: 特殊品种（港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债） | 27 |
| │  ├ `scenario_s0_holdings_quality` | S0a-S0d: 持仓质量（清仓/同名多份额/超多持仓/特殊字符） | 16 |
| │  ├ `scenario_section_order` | C-P1b: 报告序号可配置合并场景（含自定义/部分配置/未知 key） | 6 |
| │  └ `—` | S29-S33: 操作行为（分红送转/定投摊薄/部分卖出/跨账户转仓/新股待上市），仅 `scenario_basic` 父标记 | 15 |
| ├─ `scenario_resilience` | 异常容错场景 S6-S10 | 18 |
| │  ├ `scenario_bond` | S6: 纯债券基金组合 | 3 |
| │  ├ `scenario_network_down` | S7: 网络中断降级 | 3 |
| │  ├ `scenario_single_holding` | S8: 单账户单持仓 | 3 |
| │  ├ `scenario_zero_cost` | S9: 零成本持仓 | 4 |
| │  └ `scenario_extreme` | S10: 极端值 | 5 |
| ├─ `scenario_llm` | LLM 场景组合 S11-S20（10 个类共 32 项，其中 24 项同时标记为 llm） | 32 |
| └─ `scenario_datetime` | 日期/时间场景 T1-T21（含跨月/跨年/调休/港股通假期） | 100 |

### 单元测试分组（unit）

| 标记 | 覆盖模块 | 覆盖项数 |
|:-------|:---------|:--------:|
| `unit`（父标记） | 9 个子组合计 | **2583** |
| ├─ `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等） | 166 |
| ├─ `unit_fetcher` | 数据获取调度（价格/指数/基金/行业/API 异常/熔断预检/冷却恢复） | 186 |
| ├─ `unit_llm` | LLM 模块（API 路由/熔断/指纹/骨架/prompts/generators/llm_content 写入） | 440 |
| ├─ `unit_news` | 新闻源（新浪/东方财富/财联社/华尔街见闻） | 176 |
| ├─ `unit_report` | 报表生成（Excel/HTML 各页签写入、B 系列模块、C/D 迭代降级/占位；含 65 项 data 标记测试） | ≈945 |
| ├─ `unit_config` | 配置管理（config/llm_settings/llm_key；含 C 迭代 report_section_order 校验） | 75 |
| ├─ `unit_core` | 核心基础设施（缓存/数据模型/读者/注册表/缓存命令处理器/报告命令处理器；含 C/D 迭代注册表测试） | 391 |
| └─ `unit_ui` | TUI 交互（菜单/键盘/进度/错误提示） | 165 |

### 跨类标记

| 标记 | 覆盖范围 | 覆盖项数 |
|:-------|:---------|:--------:|
| `llm` | 全部 LLM 相关（unit_llm 440 + scenario_llm 32），**全部为 mock 测试，无需真实 API key** | **440** |
| `smoke` | 6 个关键节点各 4 项，共 24 项 | **24** |
| `edge` | 异常/边界场景（含熔断冷却探针） | **316** |
| `data` | 数据正确性验证 | **65** |

详细方法名和验证点见 `pytest src/test/ -m "smoke" -v` 输出。
