# 测试覆盖统计

> ⚠ 以下测试项数为撰写时的快照值，实际计数随版本迭代而变化。精确统计请以 `scripts/test_runner.py` 的 MODES 字典为准，或运行 `pytest src/test/ --collect-only -q` 获取实时计数。

按不同的 `--mode` / pytest 标记统计当前（2026-07-04）测试覆盖规模：

### 模式对应测试量

| `--mode` 值 | 覆盖项数 | 典型耗时 |
|:------------|:--------:|:---------|
| `unit` | 1993 | ~25min |
| `standard` | 1730 | ~25min |
| `scenario` | 207 | ~30s |
| `regression` | 207 | ~30s |
| `verify` | 824 | ~12min |
| `integration` | 232（场景 207 + 模块契约/缓存/TUI 25） | ~40s |
| `edge` | 198 | ~15s |
| `data` | 65 | ~10s |
| `all` | 2225 | ~26min |
| `smoke` | 24 | ~2s |

### 功能域对应测试源

按被测试的源代码模块分组，方便定位"改了某段源码该跑什么测试"：

| 功能域 | 源模块（`src/python/`） | 对应测试文件（`src/test/`） | 覆盖项数 |
|:-------|:-----------------------|:---------------------------|:--------:|
| **数据源 Provider** | `providers/`(tencent, eastmoney, sina, tiantian, akshare_extras) | `unit/providers/test_{tencent,eastmoney,sina,tiantian,akshare_extras}.py` + `test_eastmoney_industry.py` | 166 |
| **数据获取调度** | `fetcher/`(price, index, fund, industry, chain) | `unit/fetcher/test_fetcher*.py` + `test_fund.py` + `test_chain.py` + `test_api_edge.py` | 145 |
| **新闻处理** | `providers/`(\*_news.py, news_aggregator, news_correlator, news_keywords, news_sources) | `unit/news/test_{akshare,cls,eastmoney,sina,wallstreetcn}_news.py` + `test_news_{aggregator,correlator,keywords,sources}.py` | 176 |
| **报告生成** | `report/`(excel, html, category, penetration, fund_performance, market_value, summary, early_warning, news_correlation, qdii_timezone) | `unit/report/test_{excel_generator,excel_writer,html_writer,category,summary,market_value,penetration,fund_performance,early_warning,news_correlation,qdii_timezone,excel_roundtrip,html_template}.py` 等 17 文件 | 614 |
| **LLM 智能分析** | `llm/`(api, circuit_breaker, fingerprint, generators, markdown, pricing, prompts, session, skeleton) | `unit/llm/`(10 文件) + `scenario/llm/test_llm_scenarios.py` | 368 |
| **核心基础设施** | `cache.py`, `models.py`, `reader.py`, `registry.py`, `http_client.py`, `market_hours.py` | `unit/core/test_{cache,models,reader,registry,http_client,market_hours}.py` | 287 |
| **配置管理** | `config.py`, `constants.py` | `unit/config/test_config*.py` | 45 |
| **TUI 交互** | `tui*.py`, `handlers_*.py`, `main.py` | `unit/ui/test_{handlers,tui,tui_handlers,tui_menu,log_sanitize}.py` | 142 |
| **端到端业务场景** | 多模块组合（菜单 E/H/B/L → 读取 → 计算 → 报告 → LLM） | `scenario/`(basic, resilience, llm, datetime 共 4 文件) | 207 |

### 场景测试分组（scenario）

| 标记 | 覆盖场景 | 覆盖项数 | 典型耗时 |
|:-------|:---------|:--------:|:---------|
| `scenario`（父标记） | S0a-S0d + S1-S28 + T1-T21 全量业务场景 | **207** | ~30s |
| ├─ `scenario_basic` | 基础业务链路 S1-S5 + S0a-S0d + S21-S28 特殊品种 | 57 | ~5s |
| │  ├ `scenario_stock` | S1: 纯股票组合 | 3 | — |
| │  ├ `scenario_fund` | S2: 纯基金组合 | 2 | — |
| │  ├ `scenario_mixed_accounts` | S3: 混合多账户 | 1 | — |
| │  ├ `scenario_new_holdings` | S4: 新持仓无缓存 | 1 | — |
| │  ├ `scenario_cache_hit` | S5: 缓存全命中 | 2 | — |
| │  ├ `scenario_special_securities` | S21-S28: 特殊品种（港股通/可转债/REITs/货币基金/科创板/北交所/商品ETF/跨境ETF/纯债） | 27 | — |
| │  └ `scenario_s0_holdings_quality` | S0a-S0d: 持仓质量（清仓/同名多份额/超多持仓/特殊字符） | 16 | — |
| ├─ `scenario_resilience` | 异常容错场景 S6-S10 | 18 | ~5s |
| │  ├ `scenario_bond` | S6: 纯债券基金组合 | 3 | — |
| │  ├ `scenario_network_down` | S7: 网络中断降级 | 3 | — |
| │  ├ `scenario_single_holding` | S8: 单账户单持仓 | 3 | — |
| │  ├ `scenario_zero_cost` | S9: 零成本持仓 | 4 | — |
| │  └ `scenario_extreme` | S10: 极端值 | 5 | — |
| ├─ `scenario_llm` | LLM 场景组合 S11-S20（10 个类共 32 项，其中 24 项同时标记为 llm） | 32 | ~5s |
| └─ `scenario_datetime` | 日期/时间场景 T1-T21（含跨月/跨年/调休/港股通假期） | 100 | ~20s |

### 单元测试分组（unit）

| 标记 | 覆盖模块 | 覆盖项数 | 典型耗时 |
|:-------|:---------|:--------:|:---------|
| `unit`（父标记） | 8 个子组合计 | **1993** | ~25min |
| ├─ `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等） | 166 | ~2min |
| ├─ `unit_fetcher` | 数据获取调度（价格/指数/基金/行业/API 异常） | 145 | ~2min |
| ├─ `unit_llm` | LLM 模块（API 路由/熔断/指纹/骨架） | 336 | ~4min |
| ├─ `unit_news` | 新闻源（新浪/东方财富/财联社/华尔街见闻） | 176 | ~2min |
| ├─ `unit_report` | 报表生成（Excel/HTML 各页签写入；含 60 项 data 标记测试） | 667 | ~8min |
| ├─ `unit_config` | 配置管理（config/llm_settings/llm_key） | 55 | ~30s |
| ├─ `unit_core` | 核心基础设施（缓存/数据模型/读者/注册表） | 306 | ~4min |
| └─ `unit_ui` | TUI 交互（菜单/键盘/进度/错误提示） | 142 | ~2min |

### 跨类标记

| 标记 | 覆盖范围 | 覆盖项数 | 典型耗时 |
|:-------|:---------|:--------:|:---------|
| `llm` | 全部 LLM 相关（unit_llm 336 + scenario_llm 24） | **360** | ~4min |
| `smoke` | 6 个关键节点各 4 项，共 24 项 | **24** | ~2s |
| `edge` | 异常/边界场景 | **198** | ~15s |
| `data` | 数据正确性验证 | **65** | ~10s |

### LLM 标记说明

`llm` 标记覆盖 360 项测试（unit_llm 336 + scenario_llm 中 10 个类 24 项），**全部为 mock 测试，无需真实 API key**。`-m "not llm"` 跳过的是 LLM 模块而非真实 API 依赖。

### Smoke 测试明细

| 节点 | 测试文件 | 覆盖项数 |
|:-----|:---------|:--------:|
| **核心数据模型** | `unit/core/test_models.py` | 4 |
| **入口读取** | `unit/core/test_reader.py` | 4 |
| **分类计算** | `unit/report/test_category.py` | 4 |
| **报告输出** | `unit/report/test_excel_generator.py` | 4 |
| **启动依赖** | `unit/config/test_config.py` | 4 |
| **数据获取** | `unit/providers/test_eastmoney.py` | 4 |

详细方法名和验证点见 `pytest src/test/ -m "smoke" -v` 输出。
