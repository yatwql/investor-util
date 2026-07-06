# 测试覆盖统计

> ⚠ 以下测试项数为撰写时的快照值，实际计数随版本迭代而变化。精确统计请以 `scripts/test_runner.py` 的 MODES 字典为准，或运行 `pytest src/test/ --collect-only -q` 获取实时计数。

按不同的 `--mode` / pytest 标记统计当前（2026-07-06）测试覆盖规模：

### 模式对应测试量

| `--mode` 值 | 覆盖项数 | 优化前耗时 | 优化后耗时（parallel medium） | 加速比 |
|:------------|:--------:|:----------:|:----------------------------:|:------:|
| `unit` | 2270 | ~25min | **~20s** | 75x |
| `standard` | 1977 | ~25min | **~20s** | 75x |
| `scenario` | 277 | ~35s | ~35s（不并行）| — |
| `regression` | 277 | ~35s | ~35s（不并行）| — |
| `verify` | 958 | ~12min | **~49s** | 14.7x |
| `integration` | 302 | ~50s | — | — |
| `edge` | 228 | ~15s | ~15s（不并行）| — |
| `data` | 65 | ~10s | ~10s（不并行）| — |
| `all` | 2572 | ~26min | **~待测** | — |
| `smoke` | 24 | ~2s | ~2s（不并行）| — |
| `report` 🆕 | 855 | — | **~15s** | — |

> 注：`all` 模式收集总数 2572 项，但因 12 项为 Linux 专用键盘测试（`test_tui.py::TestGetKeyLinux`），在 Windows 上实跑结果为 2560 passed / 12 skipped。
> 🆕 `report` 模式为 A5 新增，标记 `unit_report`（774 项），供报告模块开发期快速验证。
> 说明：单元密集型模式（`unit`/`standard`/`verify`/`all`/`report`）启用 `--parallel medium`（默认）自动并行，场景/边缘/冒烟等轻量模式保持单线程避免进程调度开销。
> v0.2.89 价格缓存新鲜度校验 + 文档同步，全量 2572 项（2560 passed / 12 skipped for Windows）。

### 功能域对应测试源

按被测试的源代码模块分组，方便定位"改了某段源码该跑什么测试"：

| 功能域 | 源模块（`src/python/`） | 对应测试文件（`src/test/`） | 覆盖项数 |
|:-------|:-----------------------|:---------------------------|:--------:|
| **数据源 Provider** | `providers/`(tencent, eastmoney, sina, tiantian, akshare_extras) | `unit/providers/test_{tencent,eastmoney,sina,tiantian,akshare_extras}.py` + `test_eastmoney_industry.py` | 166 |
| **数据获取调度** | `fetcher/`(price, index, fund, industry, chain) | `unit/fetcher/test_fetcher*.py` + `test_fund*.py` + `test_chain*.py` + `test_api_edge.py` | 173 |
| **新闻处理** | `providers/`(\*_news.py, news_aggregator, news_correlator, news_keywords, news_sources) | `unit/news/test_{akshare,cls,eastmoney,sina,wallstreetcn}_news.py` + `test_news_{aggregator,correlator,keywords,sources}.py` | 176 |
| **报告生成** | `report/`(excel, html, category, penetration, fund_performance, market_value, summary, early_warning, news_correlation, qdii_timezone, fund_concentration, fund_manager, fund_overlap, fund_style) | `unit/report/` 共 20 文件含 test_html_writer、test_html_template 等 | 855 |
| **LLM 智能分析** | `llm/`(api, circuit_breaker, fingerprint, generators, markdown, pricing, prompts, session, skeleton, llm_content) | `unit/llm/`(10 文件) + `scenario/llm/test_llm_scenarios.py` | 377 |
| **核心基础设施** | `cache.py`, `models.py`, `reader.py`, `registry.py`, `http_client.py`, `market_hours.py` | `unit/core/test_{cache,models,reader,registry,http_client,market_hours}.py` + `*_edge.py` | 342 |
| **配置管理** | `config.py`, `constants.py` | `unit/config/test_config*.py` | 71 |
| **TUI 交互** | `tui*.py`, `handlers_*.py`, `main.py` | `unit/ui/test_{handlers,tui,tui_handlers,tui_menu,log_sanitize}.py` | 142 |
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
| `unit`（父标记） | 8 个子组合计 | **2270** |
| ├─ `unit_providers` | 数据源 Provider（腾讯/东方财富/天天基金等） | 166 |
| ├─ `unit_fetcher` | 数据获取调度（价格/指数/基金/行业/API 异常） | 173 |
| ├─ `unit_llm` | LLM 模块（API 路由/熔断/指纹/骨架/llm_content 写入） | 345 |
| ├─ `unit_news` | 新闻源（新浪/东方财富/财联社/华尔街见闻） | 176 |
| ├─ `unit_report` | 报表生成（Excel/HTML 各页签写入、B 系列模块、C 迭代序号可配置分支；含 65 项 data 标记测试） | 855 |
| ├─ `unit_config` | 配置管理（config/llm_settings/llm_key；含 C 迭代 report_section_order 校验） | 71 |
| ├─ `unit_core` | 核心基础设施（缓存/数据模型/读者/注册表；含 C 迭代注册表测试） | 342 |
| └─ `unit_ui` | TUI 交互（菜单/键盘/进度/错误提示） | 142 |

### 跨类标记

| 标记 | 覆盖范围 | 覆盖项数 |
|:-------|:---------|:--------:|
| `llm` | 全部 LLM 相关（unit_llm 345 + scenario_llm 32），**全部为 mock 测试，无需真实 API key** | **377** |
| `smoke` | 6 个关键节点各 4 项，共 24 项 | **24** |
| `edge` | 异常/边界场景 | **216** |
| `data` | 数据正确性验证 | **65** |

详细方法名和验证点见 `pytest src/test/ -m "smoke" -v` 输出。
